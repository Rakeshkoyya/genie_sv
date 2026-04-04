"""Source management router."""

import time
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select, func, delete

from app.dependencies import DbSession, ApprovedUser
from app.models.source import InputSource, SourceType
from app.schemas.source import SourceRead, SourceListResponse
from app.services.file_parser import FileParserService, get_file_type
from app.services.storage import StorageService
from app.config import get_settings

router = APIRouter(prefix="/api/sources", tags=["Sources"])
settings = get_settings()


@router.get("", response_model=SourceListResponse)
async def list_sources(
    user: ApprovedUser,
    db: DbSession,
    dataset_id: UUID | None = None
):
    """List user's input sources."""
    query = select(InputSource).where(InputSource.user_id == user.id)
    
    if dataset_id:
        query = query.where(InputSource.dataset_id == dataset_id)
    
    query = query.order_by(InputSource.created_at.desc())
    result = await db.execute(query)
    sources = result.scalars().all()
    
    count_query = select(func.count(InputSource.id)).where(InputSource.user_id == user.id)
    if dataset_id:
        count_query = count_query.where(InputSource.dataset_id == dataset_id)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    return SourceListResponse(sources=list(sources), total=total)


@router.post("", response_model=SourceRead)
async def create_source(
    user: ApprovedUser,
    db: DbSession,
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    name: str | None = Form(None),
    dataset_id: UUID | None = Form(None)
):
    """Upload a file or create a text source."""
    storage = StorageService()
    parser = FileParserService()
    
    # Handle raw text input
    if text:
        source = InputSource(
            user_id=user.id,
            dataset_id=dataset_id,
            name=name or "Text Input",
            type=SourceType.text,
            extracted_text=text,
            file_size=len(text.encode("utf-8"))
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        return source
    
    # Handle file upload
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file or text provided"
        )
    
    content = await file.read()
    file_type = get_file_type(file.filename, file.content_type or "")
    
    # Parse file to extract text
    extracted_text, metadata = await parser.parse(
        content, 
        file.filename, 
        file.content_type or ""
    )
    
    # Upload to storage
    storage_path = f"{user.id}/{int(time.time() * 1000)}_{file.filename}"
    await storage.upload(
        settings.input_files_bucket,
        storage_path,
        content,
        file.content_type or "application/octet-stream"
    )
    
    # Create source record
    source = InputSource(
        user_id=user.id,
        dataset_id=dataset_id,
        name=name or file.filename,
        type=SourceType(file_type),
        original_filename=file.filename,
        storage_path=storage_path,
        extracted_text=extracted_text,
        file_size=len(content),
        metadata=metadata
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    
    return source


@router.delete("/{source_id}")
async def delete_source(
    source_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Delete a source."""
    result = await db.execute(
        select(InputSource).where(
            InputSource.id == source_id,
            InputSource.user_id == user.id
        )
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    
    # Delete from storage if exists
    if source.storage_path:
        storage = StorageService()
        try:
            await storage.delete(settings.input_files_bucket, [source.storage_path])
        except Exception:
            pass  # Continue even if storage delete fails
    
    await db.delete(source)
    await db.commit()
    
    return {"success": True}
