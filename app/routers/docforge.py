"""DocForge router – template upload, document generation, folder management."""

import time
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.dependencies import ApprovedUser, DbSession
from app.models.docforge import DocForgeDocument, DocForgeFolder, DocForgeTemplate
from app.schemas.docforge import (
    DocumentListResponse,
    DocumentRead,
    FolderCreate,
    FolderListResponse,
    FolderRead,
    GenerateDocumentRequest,
    PlaceholderDef,
    PreviewRequest,
    TemplateListResponse,
    TemplateRead,
)
from app.services.docforge import (
    convert_docx_to_html,
    create_template_docx,
    generate_document,
    generate_html_preview,
)
from app.services.storage import StorageService

router = APIRouter(prefix="/api/docforge", tags=["DocForge"])
settings = get_settings()

DOCFORGE_BUCKET = settings.exports_bucket  # reuse exports bucket with docforge/ prefix


def _sanitize(name: str) -> str:
    """Produce a filesystem-safe slug from an arbitrary name."""
    import re
    safe = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
    return safe[:200] or "file"


# ═══════════════════════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/templates", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    user: ApprovedUser,
    db: DbSession,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(None),
    placeholders: str = Form("[]"),  # JSON string of PlaceholderDef[]
):
    """Upload a DOCX and save it as a reusable template with placeholders."""
    import json

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .docx files are supported",
        )

    original_bytes = await file.read()
    if len(original_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")

    # Parse placeholders
    try:
        ph_list = json.loads(placeholders)
        parsed_placeholders = [PlaceholderDef(**p).model_dump() for p in ph_list]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid placeholders JSON",
        )

    # Convert original DOCX → HTML preview
    html_preview = convert_docx_to_html(original_bytes)

    # Inject placeholder markers into HTML for display
    for ph in parsed_placeholders:
        html_preview = html_preview.replace(
            ph["original_text"],
            "{{" + ph["name"] + "}}",
        )

    # Build template DOCX with {{…}} markers
    template_bytes = create_template_docx(original_bytes, parsed_placeholders) if parsed_placeholders else original_bytes

    timestamp = int(time.time() * 1000)
    safe_name = _sanitize(name)

    original_path = f"{user.id}/docforge/templates/{safe_name}/{timestamp}_original.docx"
    template_path = f"{user.id}/docforge/templates/{safe_name}/{timestamp}_template.docx"

    storage = StorageService()
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    await storage.upload(DOCFORGE_BUCKET, original_path, original_bytes, docx_mime)
    await storage.upload(DOCFORGE_BUCKET, template_path, template_bytes, docx_mime)

    template = DocForgeTemplate(
        user_id=user.id,
        name=name,
        description=description,
        original_filename=file.filename,
        original_storage_path=original_path,
        template_storage_path=template_path,
        html_preview=html_preview,
        placeholders=parsed_placeholders,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return TemplateRead.model_validate(template)


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    user: ApprovedUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List the current user's templates."""
    q = (
        select(DocForgeTemplate)
        .where(DocForgeTemplate.user_id == user.id)
        .order_by(DocForgeTemplate.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(q)
    templates = result.scalars().all()

    count = await db.execute(
        select(func.count(DocForgeTemplate.id)).where(DocForgeTemplate.user_id == user.id)
    )
    total = count.scalar() or 0

    return TemplateListResponse(
        templates=[TemplateRead.model_validate(t) for t in templates],
        total=total,
    )


@router.get("/templates/{template_id}", response_model=TemplateRead)
async def get_template(template_id: UUID, user: ApprovedUser, db: DbSession):
    """Return a single template with its HTML preview and placeholder definitions."""
    result = await db.execute(
        select(DocForgeTemplate).where(
            DocForgeTemplate.id == template_id,
            DocForgeTemplate.user_id == user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return TemplateRead.model_validate(template)


@router.put("/templates/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: UUID,
    user: ApprovedUser,
    db: DbSession,
    name: str | None = Form(None),
    description: str | None = Form(None),
    placeholders: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    """Update template metadata, placeholders, or re-upload the DOCX."""
    import json

    result = await db.execute(
        select(DocForgeTemplate).where(
            DocForgeTemplate.id == template_id,
            DocForgeTemplate.user_id == user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    if name is not None:
        template.name = name
    if description is not None:
        template.description = description

    storage = StorageService()
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    # If a new file is uploaded or placeholders changed, rebuild template DOCX + HTML
    new_original_bytes: bytes | None = None
    if file is not None:
        new_original_bytes = await file.read()
        template.original_filename = file.filename or template.original_filename

    parsed_placeholders = None
    if placeholders is not None:
        try:
            ph_list = json.loads(placeholders)
            parsed_placeholders = [PlaceholderDef(**p).model_dump() for p in ph_list]
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid placeholders JSON")

    if new_original_bytes is not None or parsed_placeholders is not None:
        # Need original bytes
        if new_original_bytes is None:
            new_original_bytes = await storage.download(DOCFORGE_BUCKET, template.original_storage_path)

        phs = parsed_placeholders if parsed_placeholders is not None else template.placeholders

        html_preview = convert_docx_to_html(new_original_bytes)
        for ph in phs:
            html_preview = html_preview.replace(ph["original_text"], "{{" + ph["name"] + "}}")
        template.html_preview = html_preview

        template_bytes = create_template_docx(new_original_bytes, phs) if phs else new_original_bytes

        timestamp = int(time.time() * 1000)
        safe_name = _sanitize(template.name)
        original_path = f"{user.id}/docforge/templates/{safe_name}/{timestamp}_original.docx"
        template_path = f"{user.id}/docforge/templates/{safe_name}/{timestamp}_template.docx"

        await storage.upload(DOCFORGE_BUCKET, original_path, new_original_bytes, docx_mime)
        await storage.upload(DOCFORGE_BUCKET, template_path, template_bytes, docx_mime)

        template.original_storage_path = original_path
        template.template_storage_path = template_path

        if parsed_placeholders is not None:
            template.placeholders = parsed_placeholders

    await db.commit()
    await db.refresh(template)
    return TemplateRead.model_validate(template)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: UUID, user: ApprovedUser, db: DbSession):
    """Delete a template and its storage files."""
    result = await db.execute(
        select(DocForgeTemplate).where(
            DocForgeTemplate.id == template_id,
            DocForgeTemplate.user_id == user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    storage = StorageService()
    try:
        await storage.delete(
            DOCFORGE_BUCKET,
            [template.original_storage_path, template.template_storage_path],
        )
    except Exception:
        pass

    await db.delete(template)
    await db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════════
# Template preview & document generation
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/templates/{template_id}/preview")
async def preview_template(
    template_id: UUID,
    body: PreviewRequest,
    user: ApprovedUser,
    db: DbSession,
):
    """Return an HTML preview of the template with placeholder values filled in."""
    result = await db.execute(
        select(DocForgeTemplate).where(
            DocForgeTemplate.id == template_id,
            DocForgeTemplate.user_id == user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    html = generate_html_preview(template.html_preview or "", body.placeholder_values)
    return {"html": html}


@router.post("/templates/{template_id}/generate", response_model=DocumentRead)
async def generate_from_template(
    template_id: UUID,
    body: GenerateDocumentRequest,
    user: ApprovedUser,
    db: DbSession,
):
    """Fill placeholders and produce a DOCX document, optionally saving to a folder."""
    result = await db.execute(
        select(DocForgeTemplate).where(
            DocForgeTemplate.id == template_id,
            DocForgeTemplate.user_id == user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    # Download template DOCX from storage
    storage = StorageService()
    template_bytes = await storage.download(DOCFORGE_BUCKET, template.template_storage_path)

    # Generate final document
    final_bytes = generate_document(template_bytes, body.placeholder_values)

    # Resolve folder
    folder_id = body.folder_id
    if not folder_id and body.folder_name:
        # Find or create folder
        existing = await db.execute(
            select(DocForgeFolder).where(
                DocForgeFolder.user_id == user.id,
                DocForgeFolder.name == body.folder_name,
            )
        )
        folder = existing.scalar_one_or_none()
        if not folder:
            folder = DocForgeFolder(user_id=user.id, name=body.folder_name)
            db.add(folder)
            await db.flush()
        folder_id = folder.id

    # Upload generated document
    safe_filename = _sanitize(body.filename)
    if not safe_filename.endswith(".docx"):
        safe_filename += ".docx"

    timestamp = int(time.time() * 1000)
    storage_path = f"{user.id}/docforge/documents/{timestamp}_{safe_filename}"
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    await storage.upload(DOCFORGE_BUCKET, storage_path, final_bytes, docx_mime)

    doc = DocForgeDocument(
        user_id=user.id,
        template_id=template.id,
        folder_id=folder_id,
        name=safe_filename,
        placeholder_values=body.placeholder_values,
        storage_path=storage_path,
        file_size=len(final_bytes),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc, attribute_names=["folder", "template"])

    read = DocumentRead.model_validate(doc)
    read.folder_name = doc.folder.name if doc.folder else None
    read.template_name = doc.template.name if doc.template else None
    return read


# ═══════════════════════════════════════════════════════════════════════════
# Folders
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    user: ApprovedUser,
    db: DbSession,
    search: str | None = Query(None, description="Search folder names"),
):
    """List DocForge folders, optionally filtered by search term."""
    q = select(DocForgeFolder).where(DocForgeFolder.user_id == user.id)
    count_q = select(func.count(DocForgeFolder.id)).where(DocForgeFolder.user_id == user.id)

    if search:
        q = q.where(DocForgeFolder.name.ilike(f"%{search}%"))
        count_q = count_q.where(DocForgeFolder.name.ilike(f"%{search}%"))

    q = q.order_by(DocForgeFolder.name)
    result = await db.execute(q)
    folders = result.scalars().all()

    total = (await db.execute(count_q)).scalar() or 0

    # Compute document counts
    folder_reads: list[FolderRead] = []
    for f in folders:
        doc_count_q = select(func.count(DocForgeDocument.id)).where(
            DocForgeDocument.folder_id == f.id
        )
        doc_count = (await db.execute(doc_count_q)).scalar() or 0
        fr = FolderRead.model_validate(f)
        fr.document_count = doc_count
        folder_reads.append(fr)

    return FolderListResponse(folders=folder_reads, total=total)


@router.post("/folders", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
async def create_folder(body: FolderCreate, user: ApprovedUser, db: DbSession):
    """Create a new DocForge folder."""
    # Check for duplicate
    exists = await db.execute(
        select(DocForgeFolder).where(
            DocForgeFolder.user_id == user.id,
            DocForgeFolder.name == body.name,
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Folder already exists")

    folder = DocForgeFolder(user_id=user.id, name=body.name)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    fr = FolderRead.model_validate(folder)
    fr.document_count = 0
    return fr


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: UUID, user: ApprovedUser, db: DbSession):
    """Delete a folder. Documents inside are unlinked (folder_id set to NULL)."""
    result = await db.execute(
        select(DocForgeFolder).where(
            DocForgeFolder.id == folder_id,
            DocForgeFolder.user_id == user.id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    await db.delete(folder)
    await db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════════
# Documents
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    user: ApprovedUser,
    db: DbSession,
    folder_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List generated DocForge documents, optionally filtered by folder."""
    q = select(DocForgeDocument).where(DocForgeDocument.user_id == user.id)
    count_q = select(func.count(DocForgeDocument.id)).where(DocForgeDocument.user_id == user.id)

    if folder_id is not None:
        q = q.where(DocForgeDocument.folder_id == folder_id)
        count_q = count_q.where(DocForgeDocument.folder_id == folder_id)

    q = (
        q.options(selectinload(DocForgeDocument.folder), selectinload(DocForgeDocument.template))
        .order_by(DocForgeDocument.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(q)
    docs = result.scalars().all()

    total = (await db.execute(count_q)).scalar() or 0

    reads = []
    for d in docs:
        r = DocumentRead.model_validate(d)
        r.folder_name = d.folder.name if d.folder else None
        r.template_name = d.template.name if d.template else None
        reads.append(r)

    return DocumentListResponse(documents=reads, total=total)


@router.get("/documents/{document_id}/download")
async def download_document(document_id: UUID, user: ApprovedUser, db: DbSession):
    """Download a generated DocForge document."""
    result = await db.execute(
        select(DocForgeDocument).where(
            DocForgeDocument.id == document_id,
            DocForgeDocument.user_id == user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if not doc.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not available")

    storage = StorageService()
    content = await storage.download(DOCFORGE_BUCKET, doc.storage_path)

    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{doc.name}"'},
    )


@router.delete("/documents/{document_id}")
async def delete_document(document_id: UUID, user: ApprovedUser, db: DbSession):
    """Delete a generated document and its storage file."""
    result = await db.execute(
        select(DocForgeDocument).where(
            DocForgeDocument.id == document_id,
            DocForgeDocument.user_id == user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if doc.storage_path:
        storage = StorageService()
        try:
            await storage.delete(DOCFORGE_BUCKET, [doc.storage_path])
        except Exception:
            pass

    await db.delete(doc)
    await db.commit()
    return {"success": True}
