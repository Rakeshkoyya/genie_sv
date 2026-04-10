"""Workflow service – runs a prompt chain per file in the background."""

import asyncio
import logging
import time
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.source import InputSource
from app.models.prompt import Prompt, PromptChain, PromptChainStep
from app.models.export import ExportedDocument, ExportFormat
from app.models.workflow import WorkflowRun, WorkflowStatus
from app.services.llm import LLMService
from app.services.storage import StorageService
from app.services.document_export import create_docx, create_txt, create_pdf, sanitize_filename
from app.utils.prompt_builder import format_sources_text, prepare_media_parts
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def _update_progress(
    db: AsyncSession,
    workflow_id: uuid.UUID,
    *,
    status: WorkflowStatus | None = None,
    total_files: int | None = None,
    total_steps: int | None = None,
    completed_files: int | None = None,
    current_file_index: int | None = None,
    current_step_index: int | None = None,
    current_file_name: str | None = None,
    error_message: str | None = None,
    results: list[dict] | None = None,
) -> None:
    """Update workflow progress fields atomically."""
    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
    if total_files is not None:
        values["total_files"] = total_files
    if total_steps is not None:
        values["total_steps"] = total_steps
    if completed_files is not None:
        values["completed_files"] = completed_files
    if current_file_index is not None:
        values["current_file_index"] = current_file_index
    if current_step_index is not None:
        values["current_step_index"] = current_step_index
    if current_file_name is not None:
        values["current_file_name"] = current_file_name
    if error_message is not None:
        values["error_message"] = error_message
    if results is not None:
        values["results"] = results
    if not values:
        return
    await db.execute(
        update(WorkflowRun).where(WorkflowRun.id == workflow_id).values(**values)
    )
    await db.commit()


async def _gather_source_content(
    source: InputSource,
    storage: StorageService,
) -> tuple[list[dict], list[dict]]:
    """Return (source_texts, media_parts) for a single source."""
    source_texts: list[dict] = []
    media_parts: list[dict] = []

    if source.type in ("pdf", "text", "excel", "csv"):
        if source.extracted_text:
            source_texts.append({"name": source.name, "extracted_text": source.extracted_text})
    elif source.type == "image" and source.storage_path:
        try:
            content = await storage.download(settings.input_files_bucket, source.storage_path)
            if len(content) <= 5 * 1024 * 1024:
                media_parts.append({"type": "image", "content": content, "metadata": source.file_metadata or {}})
            elif source.extracted_text:
                source_texts.append({"name": source.name, "extracted_text": source.extracted_text})
        except Exception:
            if source.extracted_text:
                source_texts.append({"name": source.name, "extracted_text": source.extracted_text})
    elif source.extracted_text:
        source_texts.append({"name": source.name, "extracted_text": source.extracted_text})

    return source_texts, media_parts


async def run_workflow(workflow_id: uuid.UUID) -> None:
    """Execute the full workflow in the background.

    Opens its own DB session so the caller can return immediately.
    """
    async with AsyncSessionLocal() as db:
        try:
            # Load workflow
            result = await db.execute(
                select(WorkflowRun).where(WorkflowRun.id == workflow_id)
            )
            workflow = result.scalar_one_or_none()
            if not workflow:
                logger.error("Workflow %s not found", workflow_id)
                return

            # Load prompt chain with steps
            chain_result = await db.execute(
                select(PromptChain)
                .options(
                    selectinload(PromptChain.steps).selectinload(PromptChainStep.prompt).selectinload(Prompt.response_format),
                    selectinload(PromptChain.steps).selectinload(PromptChainStep.response_format),
                )
                .where(PromptChain.id == workflow.chain_id)
            )
            chain = chain_result.scalar_one_or_none()
            if not chain or not chain.steps:
                await _update_progress(db, workflow_id, status=WorkflowStatus.error, error_message="Chain not found or empty")
                return

            sorted_steps = sorted(chain.steps, key=lambda s: s.step_order)
            steps_data = [
                {
                    "prompt": step.prompt.text,
                    "name": step.prompt.name,
                    "format": (
                        step.response_format.template_text if step.response_format
                        else (step.prompt.response_format.template_text if step.prompt.response_format else None)
                    )
                }
                for step in sorted_steps
            ]
            chain_name = chain.name
            chain_description = chain.description

            # Load sources
            source_id_list = [uuid.UUID(str(sid)) for sid in workflow.source_ids]
            src_result = await db.execute(
                select(InputSource).where(
                    InputSource.id.in_(source_id_list),
                    InputSource.user_id == workflow.user_id,
                )
            )
            sources = {str(s.id): s for s in src_result.scalars().all()}

            await _update_progress(
                db,
                workflow_id,
                status=WorkflowStatus.running,
                total_files=len(source_id_list),
                total_steps=len(steps_data),
            )

            llm = LLMService()
            storage = StorageService()
            file_results: list[dict] = []

            for file_idx, sid in enumerate(source_id_list):
                # Check for cancellation
                cancel_check = await db.execute(
                    select(WorkflowRun.status).where(WorkflowRun.id == workflow_id)
                )
                current_status = cancel_check.scalar_one()
                if current_status == WorkflowStatus.cancelled:
                    logger.info("Workflow %s cancelled by user", workflow_id)
                    return
                source = sources.get(str(sid))
                if not source:
                    file_results.append({"source_id": str(sid), "status": "error", "error": "Source not found"})
                    continue

                await _update_progress(
                    db,
                    workflow_id,
                    current_file_index=file_idx,
                    current_step_index=0,
                    current_file_name=source.name,
                )

                try:
                    source_texts, media_parts_raw = await _gather_source_content(source, storage)
                    sources_text = format_sources_text(source_texts)
                    image_parts = prepare_media_parts(media_parts_raw)

                    # Create workbook plan for this file — optimise prompts/formats
                    try:
                        plan = await llm.create_workbook_plan(
                            sources=sources_text,
                            steps=steps_data,
                            chain_name=chain_name,
                            chain_description=chain_description,
                            model=workflow.model,
                        )
                        planned_steps = plan["steps"]
                    except Exception as plan_exc:
                        logger.warning("Workbook planner failed for file %s, using originals: %s", source.name, plan_exc)
                        planned_steps = [{"prompt": s["prompt"], "format": s.get("format")} for s in steps_data]

                    # Generate all sections in a single LLM call
                    step_names = [s.get("name", f"Section {i+1}") for i, s in enumerate(steps_data)]
                    step_results = await llm.generate_all_sections(
                        sources=sources_text,
                        planned_steps=planned_steps,
                        step_names=step_names,
                        model=workflow.model,
                        media_parts=image_parts if image_parts else None,
                    )

                    combined = "\n\n---\n\n".join(step_results)

                    # Export
                    file_number = file_idx + 1
                    safe_prefix = sanitize_filename(workflow.filename_prefix)
                    fmt = workflow.output_format
                    filename = f"{safe_prefix}-{file_number}.{fmt}"
                    timestamp = int(time.time() * 1000)
                    storage_path = f"{workflow.user_id}/workflows/{workflow_id}/{timestamp}_{filename}"

                    if fmt == "docx":
                        doc_bytes = create_docx(filename, [{"name": source.name, "content": combined}])
                        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    elif fmt == "pdf":
                        doc_bytes = create_pdf(filename, [{"name": source.name, "content": combined}])
                        content_type = "application/pdf"
                    else:
                        doc_bytes = create_txt(filename, combined)
                        content_type = "text/plain; charset=utf-8"

                    await storage.upload(settings.exports_bucket, storage_path, doc_bytes, content_type)

                    # Create export record
                    format_map = {"docx": ExportFormat.docx, "pdf": ExportFormat.pdf, "txt": ExportFormat.txt}
                    export = ExportedDocument(
                        user_id=workflow.user_id,
                        dataset_id=workflow.dataset_id,
                        format=format_map.get(fmt, ExportFormat.txt),
                        storage_path=storage_path,
                        filename=filename,
                        file_size=len(doc_bytes),
                    )
                    db.add(export)
                    await db.flush()

                    file_results.append({
                        "source_id": str(sid),
                        "source_name": source.name,
                        "filename": filename,
                        "export_id": str(export.id),
                        "status": "completed",
                    })

                except Exception as e:
                    logger.exception("Workflow %s file %s error", workflow_id, source.name)
                    file_results.append({
                        "source_id": str(sid),
                        "source_name": source.name,
                        "status": "error",
                        "error": str(e),
                    })

                # Update completed count after each file
                await _update_progress(
                    db,
                    workflow_id,
                    completed_files=file_idx + 1,
                    results=file_results,
                )

            # Mark complete
            final_status = WorkflowStatus.completed
            if all(r.get("status") == "error" for r in file_results):
                final_status = WorkflowStatus.error
            await _update_progress(
                db,
                workflow_id,
                status=final_status,
                results=file_results,
            )
            logger.info("Workflow %s finished with status %s", workflow_id, final_status)

        except Exception as e:
            logger.exception("Workflow %s fatal error", workflow_id)
            try:
                await _update_progress(db, workflow_id, status=WorkflowStatus.error, error_message=str(e))
            except Exception:
                pass
