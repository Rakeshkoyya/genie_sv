"""Export router for DOCX/TXT document generation."""

import time
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, ApprovedUser
from app.models.export import ExportedDocument, ExportFormat
from app.models.source import Dataset
from app.schemas.export import ExportRead, ExportListResponse, ExportDocxRequest, ExportTxtRequest
from app.services.document_export import DocumentExportService, sanitize_filename
from app.services.storage import StorageService
from app.config import get_settings

router = APIRouter(prefix="/api/exports", tags=["Exports"])
settings = get_settings()


@router.get("", response_model=ExportListResponse)
async def list_exports(
    user: ApprovedUser,
    db: DbSession,
    dataset_id: UUID | None = Query(None, description="Filter by dataset ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """List user's exported documents, optionally filtered by dataset."""
    query = select(ExportedDocument).where(ExportedDocument.user_id == user.id)
    count_query = select(func.count(ExportedDocument.id)).where(ExportedDocument.user_id == user.id)
    
    if dataset_id:
        query = query.where(ExportedDocument.dataset_id == dataset_id)
        count_query = count_query.where(ExportedDocument.dataset_id == dataset_id)
    
    result = await db.execute(
        query
        .options(selectinload(ExportedDocument.dataset))
        .order_by(ExportedDocument.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    exports = result.scalars().all()
    
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    # Build response with dataset_name populated
    export_reads = []
    for exp in exports:
        read = ExportRead.model_validate(exp)
        read.dataset_name = exp.dataset.name if exp.dataset else None
        export_reads.append(read)
    
    return ExportListResponse(exports=export_reads, total=total)


async def _get_storage_path(user_id: UUID, dataset_id: UUID | None, filename: str, db: DbSession) -> str:
    """Generate storage path, organized by dataset if provided."""
    timestamp = int(time.time() * 1000)
    
    if dataset_id:
        # Get dataset name for folder organization
        result = await db.execute(
            select(Dataset.name).where(Dataset.id == dataset_id)
        )
        dataset_name = result.scalar_one_or_none()
        if dataset_name:
            safe_dataset_name = sanitize_filename(dataset_name)
            return f"{user_id}/{safe_dataset_name}/{timestamp}_{filename}"
    
    # Default: user folder only
    return f"{user_id}/{timestamp}_{filename}"


@router.post("/docx")
async def create_docx_export(
    data: ExportDocxRequest,
    user: ApprovedUser,
    db: DbSession
):
    """Generate and store a DOCX document."""
    export_service = DocumentExportService()
    storage = StorageService()
    
    if not data.results:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No results to export"
        )
    
    # Generate DOCX
    doc_bytes = export_service.create_docx(data.title, data.results)
    safe_filename = sanitize_filename(data.title)
    filename = f"{safe_filename}.docx"
    
    # Upload to storage (organized by dataset if provided)
    storage_path = await _get_storage_path(user.id, data.dataset_id, filename, db)
    await storage.upload(
        settings.exports_bucket,
        storage_path,
        doc_bytes,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    
    # Create export record
    export = ExportedDocument(
        user_id=user.id,
        dataset_id=data.dataset_id,
        generation_id=data.generation_id,
        format=ExportFormat.docx,
        storage_path=storage_path,
        filename=filename,
        file_size=len(doc_bytes)
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)
    
    # Return the file directly
    return Response(
        content=doc_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/txt")
async def create_txt_export(
    data: ExportTxtRequest,
    user: ApprovedUser,
    db: DbSession
):
    """Generate and store a TXT document."""
    export_service = DocumentExportService()
    storage = StorageService()
    
    # Generate TXT
    txt_bytes = export_service.create_txt(data.title, data.content)
    safe_filename = sanitize_filename(data.title)
    filename = f"{safe_filename}.txt"
    
    # Upload to storage (organized by dataset if provided)
    storage_path = await _get_storage_path(user.id, data.dataset_id, filename, db)
    await storage.upload(
        settings.exports_bucket,
        storage_path,
        txt_bytes,
        "text/plain; charset=utf-8"
    )
    
    # Create export record
    export = ExportedDocument(
        user_id=user.id,
        dataset_id=data.dataset_id,
        generation_id=data.generation_id,
        format=ExportFormat.txt,
        storage_path=storage_path,
        filename=filename,
        file_size=len(txt_bytes)
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)
    
    # Return the file directly
    return Response(
        content=txt_bytes,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/{export_id}/download")
async def download_export(
    export_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Download an exported document."""
    result = await db.execute(
        select(ExportedDocument).where(
            ExportedDocument.id == export_id,
            ExportedDocument.user_id == user.id
        )
    )
    export = result.scalar_one_or_none()
    
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    
    storage = StorageService()
    content = await storage.download(settings.exports_bucket, export.storage_path)
    
    # Determine content type
    content_type = {
        ExportFormat.docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ExportFormat.txt: "text/plain; charset=utf-8",
        ExportFormat.pdf: "application/pdf",
        ExportFormat.png: "image/png",
    }.get(export.format, "application/octet-stream")
    
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{export.filename}"'
        }
    )


@router.patch("/{export_id}", response_model=ExportRead)
async def rename_export(
    export_id: UUID,
    filename: str,
    user: ApprovedUser,
    db: DbSession
):
    """Rename an exported document."""
    result = await db.execute(
        select(ExportedDocument).where(
            ExportedDocument.id == export_id,
            ExportedDocument.user_id == user.id
        )
    )
    export = result.scalar_one_or_none()
    
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    
    # Ensure correct extension
    ext = export.format
    if not filename.endswith(f".{ext}"):
        filename = f"{filename}.{ext}"
    
    export.filename = filename
    await db.commit()
    await db.refresh(export)
    
    return export


@router.delete("/{export_id}")
async def delete_export(
    export_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Delete an exported document."""
    result = await db.execute(
        select(ExportedDocument).where(
            ExportedDocument.id == export_id,
            ExportedDocument.user_id == user.id
        )
    )
    export = result.scalar_one_or_none()
    
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    
    # Delete from storage
    storage = StorageService()
    try:
        await storage.delete(settings.exports_bucket, [export.storage_path])
    except Exception:
        pass  # Continue even if storage delete fails
    
    await db.delete(export)
    await db.commit()
    
    return {"success": True}
