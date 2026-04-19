"""DocAgent API router — agentic document generation endpoints."""

import logging
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc

from app.dependencies import ApprovedUser, DbSession
from app.models.docagent import DocAgentJob, DocAgentStatus
from app.schemas.docagent import (
    DocAgentCreateRequest,
    DocAgentFromSourceRequest,
    DocAgentJobRead,
    DocAgentJobListResponse,
)
from app.services.docagent import DocAgentService
from app.services.docx_formatter import DocxFormatter
from app.services.file_parser import (
    parse_pdf,
    parse_excel,
    parse_csv,
    parse_text,
    get_file_type,
)
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/docagent", tags=["DocAgent"])

# ── Pre-defined color palettes (must match frontend) ──
COLOR_PALETTES = {
    "ocean": {"primary": "#1A5276", "secondary": "#2E86C1", "accent": "#1B4F72", "text": "#1C1C1C"},
    "forest": {"primary": "#1E6F50", "secondary": "#28A745", "accent": "#145A38", "text": "#1C1C1C"},
    "royal": {"primary": "#5B2C8B", "secondary": "#7D3AC1", "accent": "#4A1D78", "text": "#1C1C1C"},
    "ember": {"primary": "#C0392B", "secondary": "#E67E22", "accent": "#A93226", "text": "#1C1C1C"},
    "slate": {"primary": "#2C3E50", "secondary": "#5D6D7E", "accent": "#1C2833", "text": "#1C1C1C"},
    "teal": {"primary": "#008080", "secondary": "#E07A5F", "accent": "#006666", "text": "#1C1C1C"},
}


def _sse_event(event: str, data: dict | str) -> str:
    """Format a Server-Sent Event."""
    payload = json.dumps(data) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


async def _extract_text(content: bytes, filename: str, mime_type: str) -> str:
    """Extract text from uploaded file bytes."""
    file_type = get_file_type(filename, mime_type)

    if file_type == "pdf":
        text, _ = await parse_pdf(content)
    elif file_type == "excel":
        text, _ = await parse_excel(content, filename)
    elif file_type == "csv":
        text, _ = await parse_csv(content)
    else:
        text, _ = await parse_text(content)

    return text or ""


# ─────────────────────────────────────────────────────────────────
#  SSE streaming endpoint — main generation flow
# ─────────────────────────────────────────────────────────────────


@router.post("/generate")
async def generate_document(
    user: ApprovedUser,
    db: DbSession,
    file: UploadFile = File(...),
    user_prompt: str = Form(...),
    model: str = Form("anthropic/claude-sonnet-4"),
    title: str = Form(None),
    subject: str = Form(None),
    class_level: str = Form(None),
    chapter_number: int = Form(None),
    color_palette: str = Form("ocean"),
):
    """Upload a document and generate a formatted .docx via the 4-step agent pipeline.

    Returns an SSE stream with progress events:
      - status: {step, message}
      - analysis: {analysis result JSON}
      - plan: {plan result JSON}
      - done: {job_id, filename}
      - error: {message}
    """

    # Read file
    file_content = await file.read()
    filename = file.filename or "document"
    mime = file.content_type or "application/octet-stream"

    # Extract text
    source_text = await _extract_text(file_content, filename, mime)
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from the uploaded file.")

    # Upload source to storage
    storage = StorageService()
    source_path = f"docagent/{user.id}/{uuid.uuid4()}/{filename}"
    await storage.upload("input-files", source_path, file_content, mime)

    # Create job record
    job = DocAgentJob(
        user_id=user.id,
        title=title or f"DocAgent: {filename}",
        user_prompt=user_prompt,
        model_used=model,
        source_filename=filename,
        source_storage_path=source_path,
        source_extracted_text=source_text[:100_000],  # cap storage
        status=DocAgentStatus.pending,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    job_id = job.id
    resolved_palette = COLOR_PALETTES.get(color_palette, COLOR_PALETTES["ocean"])

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            agent = DocAgentService(model=model)

            # Step 1 — Analyze
            yield _sse_event("status", {"step": "analyzing", "message": "Analyzing source document..."})

            # Need a fresh session inside the generator
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                analysis = await agent.analyze(source_text)
                yield _sse_event("analysis", analysis.model_dump())

                # Persist
                stmt = select(DocAgentJob).where(DocAgentJob.id == job_id)
                result = await session.execute(stmt)
                db_job = result.scalar_one()
                db_job.analysis_result = analysis.model_dump()
                db_job.status = DocAgentStatus.planning
                await session.commit()

                # Step 2 — Plan
                yield _sse_event("status", {"step": "planning", "message": "Designing document layout..."})

                plan = await agent.plan(
                    analysis, user_prompt, source_text,
                    class_level=class_level, subject=subject, chapter_number=chapter_number,
                    color_palette=resolved_palette,
                )
                yield _sse_event("plan", plan.model_dump())

                db_job.plan_result = plan.model_dump()
                db_job.status = DocAgentStatus.generating
                await session.commit()

                # Step 3 — Generate
                yield _sse_event("status", {"step": "generating", "message": "Generating document content..."})

                document = await agent.generate(
                    plan, analysis, user_prompt, source_text,
                    class_level=class_level, subject=subject, chapter_number=chapter_number,
                    color_palette=resolved_palette,
                )

                db_job.content_result = document.model_dump()
                db_job.status = DocAgentStatus.formatting
                await session.commit()

                # Step 4 — Format
                yield _sse_event("status", {"step": "formatting", "message": "Building Word document..."})

                formatter = DocxFormatter()
                docx_bytes = formatter.format(document)

                # Upload .docx to storage
                # Build output filename: G{class}-{SUBJECT}-CH{chapter} or fallback
                if class_level and subject and chapter_number:
                    output_name = f"G{class_level}-{subject.upper().replace(' ', '_')}-CH{chapter_number}.docx"
                elif title:
                    output_name = f"{title}.docx".replace(" ", "_")
                else:
                    output_name = "DocAgent_Output.docx"
                output_path = f"docagent/{user.id}/{job_id}/{output_name}"
                await storage.upload("exports", output_path, docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

                db_job.output_storage_path = output_path
                db_job.output_filename = output_name
                db_job.file_size = len(docx_bytes)
                db_job.status = DocAgentStatus.completed
                await session.commit()

                yield _sse_event("done", {
                    "job_id": str(job_id),
                    "filename": output_name,
                    "file_size": len(docx_bytes),
                })

        except Exception as exc:
            logger.exception("DocAgent pipeline error for job %s", job_id)
            # Update job with error
            try:
                from app.database import AsyncSessionLocal
                async with AsyncSessionLocal() as err_session:
                    stmt = select(DocAgentJob).where(DocAgentJob.id == job_id)
                    result = await err_session.execute(stmt)
                    db_job = result.scalar_one()
                    db_job.status = DocAgentStatus.error
                    db_job.error_message = str(exc)[:2000]
                    await err_session.commit()
            except Exception:
                logger.exception("Failed to update job error status")

            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────
#  Generate from existing source (by source_id)
# ─────────────────────────────────────────────────────────────────


@router.post("/generate-from-source")
async def generate_from_source(
    data: DocAgentFromSourceRequest,
    user: ApprovedUser,
    db: DbSession,
):
    """Generate a document from an already-uploaded source."""
    from app.models.source import InputSource

    result = await db.execute(
        select(InputSource).where(
            InputSource.id == data.source_id,
            InputSource.user_id == user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source_text = source.extracted_text or ""
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="Source has no extracted text")

    # Create job
    job = DocAgentJob(
        user_id=user.id,
        title=data.title or f"DocAgent: {source.name}",
        user_prompt=data.user_prompt,
        model_used=data.model,
        source_filename=source.name,
        source_storage_path=source.storage_path,
        source_extracted_text=source_text[:100_000],
        status=DocAgentStatus.pending,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    job_id = job.id
    storage = StorageService()

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            agent = DocAgentService(model=data.model)
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                yield _sse_event("status", {"step": "analyzing", "message": "Analyzing source document..."})
                analysis = await agent.analyze(source_text)
                yield _sse_event("analysis", analysis.model_dump())

                stmt = select(DocAgentJob).where(DocAgentJob.id == job_id)
                result = await session.execute(stmt)
                db_job = result.scalar_one()
                db_job.analysis_result = analysis.model_dump()
                db_job.status = DocAgentStatus.planning
                await session.commit()

                yield _sse_event("status", {"step": "planning", "message": "Designing document layout..."})
                plan = await agent.plan(analysis, data.user_prompt, source_text)
                yield _sse_event("plan", plan.model_dump())
                db_job.plan_result = plan.model_dump()
                db_job.status = DocAgentStatus.generating
                await session.commit()

                yield _sse_event("status", {"step": "generating", "message": "Generating document content..."})
                document = await agent.generate(plan, analysis, data.user_prompt, source_text)
                db_job.content_result = document.model_dump()
                db_job.status = DocAgentStatus.formatting
                await session.commit()

                yield _sse_event("status", {"step": "formatting", "message": "Building Word document..."})
                formatter = DocxFormatter()
                docx_bytes = formatter.format(document)

                output_name = f"{data.title or 'DocAgent_Output'}.docx".replace(" ", "_")
                output_path = f"docagent/{user.id}/{job_id}/{output_name}"
                await storage.upload("exports", output_path, docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

                db_job.output_storage_path = output_path
                db_job.output_filename = output_name
                db_job.file_size = len(docx_bytes)
                db_job.status = DocAgentStatus.completed
                await session.commit()

                yield _sse_event("done", {
                    "job_id": str(job_id),
                    "filename": output_name,
                    "file_size": len(docx_bytes),
                })
        except Exception as exc:
            logger.exception("DocAgent pipeline error for job %s", job_id)
            try:
                from app.database import AsyncSessionLocal
                async with AsyncSessionLocal() as err_session:
                    stmt = select(DocAgentJob).where(DocAgentJob.id == job_id)
                    result = await err_session.execute(stmt)
                    db_job = result.scalar_one()
                    db_job.status = DocAgentStatus.error
                    db_job.error_message = str(exc)[:2000]
                    await err_session.commit()
            except Exception:
                logger.exception("Failed to update job error status")
            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────
#  Download the generated .docx
# ─────────────────────────────────────────────────────────────────


@router.get("/jobs/{job_id}/download")
async def download_document(job_id: str, user: ApprovedUser, db: DbSession):
    """Download the generated .docx file for a completed job."""
    result = await db.execute(
        select(DocAgentJob).where(
            DocAgentJob.id == uuid.UUID(job_id),
            DocAgentJob.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != DocAgentStatus.completed:
        raise HTTPException(status_code=400, detail="Job is not completed yet")
    if not job.output_storage_path:
        raise HTTPException(status_code=400, detail="No output file available")

    storage = StorageService()
    content = await storage.download("exports", job.output_storage_path)

    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{job.output_filename or "document.docx"}"',
            "Content-Length": str(len(content)),
        },
    )


# ─────────────────────────────────────────────────────────────────
#  List jobs / Get job detail
# ─────────────────────────────────────────────────────────────────


@router.get("/jobs", response_model=DocAgentJobListResponse)
async def list_jobs(user: ApprovedUser, db: DbSession, limit: int = 50, offset: int = 0):
    """List DocAgent jobs for the current user."""
    count_result = await db.execute(
        select(func.count(DocAgentJob.id)).where(DocAgentJob.user_id == user.id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(DocAgentJob)
        .where(DocAgentJob.user_id == user.id)
        .order_by(desc(DocAgentJob.created_at))
        .offset(offset)
        .limit(limit)
    )
    jobs = result.scalars().all()

    return DocAgentJobListResponse(
        jobs=[DocAgentJobRead.model_validate(j) for j in jobs],
        total=total,
    )


@router.get("/jobs/{job_id}", response_model=DocAgentJobRead)
async def get_job(job_id: str, user: ApprovedUser, db: DbSession):
    """Get a specific DocAgent job."""
    result = await db.execute(
        select(DocAgentJob).where(
            DocAgentJob.id == uuid.UUID(job_id),
            DocAgentJob.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return DocAgentJobRead.model_validate(job)


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, user: ApprovedUser, db: DbSession):
    """Delete a DocAgent job."""
    result = await db.execute(
        select(DocAgentJob).where(
            DocAgentJob.id == uuid.UUID(job_id),
            DocAgentJob.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Clean up storage files
    storage = StorageService()
    paths_to_delete = []
    if job.source_storage_path:
        paths_to_delete.append(job.source_storage_path)
    if job.output_storage_path:
        paths_to_delete.append(job.output_storage_path)

    if paths_to_delete:
        try:
            await storage.delete("exports", [p for p in paths_to_delete if p.startswith("docagent/")])
            await storage.delete("input-files", [p for p in paths_to_delete if p.startswith("docagent/")])
        except Exception:
            logger.warning("Failed to clean up storage for job %s", job_id)

    await db.delete(job)
    await db.commit()
    return {"status": "deleted"}
