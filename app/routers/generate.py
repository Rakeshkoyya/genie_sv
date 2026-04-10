"""Generation router for LLM content generation."""

import json
import logging
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, ApprovedUser
from app.models.source import InputSource
from app.models.prompt import Prompt, PromptChain, PromptChainStep
from app.models.generation import Generation, GenerationSource, GenerationStatus
from app.schemas.generation import GenerateRequest, GenerateResponse
from app.services.llm import LLMService
from app.services.storage import StorageService
from app.utils.prompt_builder import format_sources_text, prepare_media_parts
from app.config import get_settings

router = APIRouter(prefix="/api/generate", tags=["Generate"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("", response_model=GenerateResponse)
async def generate_content(
    data: GenerateRequest,
    user: ApprovedUser,
    db: DbSession
):
    """Generate content using LLM.
    
    Supports:
    - Single prompt generation
    - Prompt chain execution (multiple prompts in sequence)
    - Multimodal input (text + images)
    """
    llm = LLMService()
    storage = StorageService()
    
    # Gather source content
    source_texts = []
    media_parts = []
    
    if data.source_ids:
        result = await db.execute(
            select(InputSource).where(
                InputSource.id.in_(data.source_ids),
                InputSource.user_id == user.id
            )
        )
        sources = result.scalars().all()
        
        for source in sources:
            # PDFs and text: use extracted text
            if source.type in ("pdf", "text", "excel", "csv"):
                if source.extracted_text:
                    source_texts.append({
                        "name": source.name,
                        "extracted_text": source.extracted_text
                    })
            
            # Images: download and prepare for multimodal
            elif source.type == "image" and source.storage_path:
                try:
                    content = await storage.download(
                        settings.input_files_bucket,
                        source.storage_path
                    )
                    # Check size - use extracted text for large images
                    if len(content) <= 5 * 1024 * 1024:  # 5MB limit
                        media_parts.append({
                            "type": "image",
                            "content": content,
                            "metadata": source.file_metadata or {}
                        })
                    elif source.extracted_text:
                        source_texts.append({
                            "name": source.name,
                            "extracted_text": source.extracted_text
                        })
                except Exception:
                    # Fallback to extracted text
                    if source.extracted_text:
                        source_texts.append({
                            "name": source.name,
                            "extracted_text": source.extracted_text
                        })
            elif source.extracted_text:
                source_texts.append({
                    "name": source.name,
                    "extracted_text": source.extracted_text
                })
    
    sources_text = format_sources_text(source_texts)
    image_parts = prepare_media_parts(media_parts)
    
    # Chain generation
    if data.chain_id:
        result = await db.execute(
            select(PromptChain)
            .options(
                selectinload(PromptChain.steps)
                .selectinload(PromptChainStep.prompt)
                .selectinload(Prompt.response_format),
                selectinload(PromptChain.steps)
                .selectinload(PromptChainStep.response_format)
            )
            .where(
                PromptChain.id == data.chain_id,
                PromptChain.user_id == user.id
            )
        )
        chain = result.scalar_one_or_none()
        
        if not chain or not chain.steps:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chain not found or empty"
            )
        
        # Create generation record
        generation = Generation(
            user_id=user.id,
            title=data.title or chain.name,
            prompt_text=" → ".join(s.prompt.name for s in chain.steps),
            model_used=data.model,
            status=GenerationStatus.processing,
            prompt_chain_id=data.chain_id
        )
        db.add(generation)
        await db.flush()
        
        # Link sources
        for source_id in data.source_ids:
            gs = GenerationSource(
                generation_id=generation.id,
                source_id=source_id
            )
            db.add(gs)
        
        try:
            # Execute chain steps — fall back to prompt's own format if step has none
            steps = [
                {
                    "prompt": step.prompt.text,
                    "name": step.prompt.name,
                    "format": (
                        step.response_format.template_text if step.response_format
                        else (step.prompt.response_format.template_text if step.prompt.response_format else None)
                    )
                }
                for step in sorted(chain.steps, key=lambda s: s.step_order)
            ]
            
            results = await llm.generate_chain(
                sources=sources_text,
                steps=steps,
                model=data.model,
                media_parts=image_parts if image_parts else None,
                chain_name=chain.name,
                chain_description=chain.description,
            )
            
            combined_content = "\n<pagebreak/>\n".join(results)
            
            generation.status = GenerationStatus.completed
            generation.response_content = combined_content
            
            await db.commit()
            
            return GenerateResponse(
                content=combined_content,
                generation_id=generation.id
            )
            
        except Exception as e:
            generation.status = GenerationStatus.error
            generation.error_message = str(e)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    # Single prompt generation
    else:
        # Create generation record
        generation = Generation(
            user_id=user.id,
            title=data.title or "Generation",
            prompt_text=data.prompt_text,
            response_format_text=data.format_text,
            model_used=data.model,
            status=GenerationStatus.processing
        )
        db.add(generation)
        await db.flush()
        
        # Link sources
        for source_id in data.source_ids:
            gs = GenerationSource(
                generation_id=generation.id,
                source_id=source_id
            )
            db.add(gs)
        
        try:
            content = await llm.generate(
                sources=sources_text,
                prompt=data.prompt_text,
                format_text=data.format_text,
                model=data.model,
                media_parts=image_parts if image_parts else None
            )
            
            generation.status = GenerationStatus.completed
            generation.response_content = content
            
            await db.commit()
            
            return GenerateResponse(
                content=content,
                generation_id=generation.id
            )
            
        except Exception as e:
            generation.status = GenerationStatus.error
            generation.error_message = str(e)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chain-stream")
async def generate_chain_stream(
    data: GenerateRequest,
    user: ApprovedUser,
    db: DbSession
):
    """Generate content using a prompt chain with SSE progress streaming.

    Uses a two-call architecture:
      1. Master planner call — analyses source and optimises all prompts/formats
      2. Single mega generation call — generates ALL sections in one shot

    Streams events:
      - phase: {phase: "planning"|"generating"|"processing", message}
      - done: {content, generation_id}
      - error: {message}
    """
    if not data.chain_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chain_id is required for chain-stream"
        )

    llm = LLMService()
    storage = StorageService()

    # ── Gather source content ──
    source_texts = []
    media_parts_list = []

    if data.source_ids:
        result = await db.execute(
            select(InputSource).where(
                InputSource.id.in_(data.source_ids),
                InputSource.user_id == user.id
            )
        )
        sources = result.scalars().all()

        for source in sources:
            if source.type in ("pdf", "text", "excel", "csv"):
                if source.extracted_text:
                    source_texts.append({"name": source.name, "extracted_text": source.extracted_text})
            elif source.type == "image" and source.storage_path:
                try:
                    content = await storage.download(settings.input_files_bucket, source.storage_path)
                    if len(content) <= 5 * 1024 * 1024:
                        media_parts_list.append({"type": "image", "content": content, "metadata": source.file_metadata or {}})
                    elif source.extracted_text:
                        source_texts.append({"name": source.name, "extracted_text": source.extracted_text})
                except Exception:
                    if source.extracted_text:
                        source_texts.append({"name": source.name, "extracted_text": source.extracted_text})
            elif source.extracted_text:
                source_texts.append({"name": source.name, "extracted_text": source.extracted_text})

    sources_text = format_sources_text(source_texts)
    image_parts = prepare_media_parts(media_parts_list)

    # ── Load chain ──
    result = await db.execute(
        select(PromptChain)
        .options(
            selectinload(PromptChain.steps).selectinload(PromptChainStep.prompt).selectinload(Prompt.response_format),
            selectinload(PromptChain.steps).selectinload(PromptChainStep.response_format)
        )
        .where(PromptChain.id == data.chain_id, PromptChain.user_id == user.id)
    )
    chain = result.scalar_one_or_none()

    if not chain or not chain.steps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found or empty")

    sorted_steps = sorted(chain.steps, key=lambda s: s.step_order)
    steps_data = [
        {
            "prompt": step.prompt.text,
            "format": (
                step.response_format.template_text if step.response_format
                else (step.prompt.response_format.template_text if step.prompt.response_format else None)
            ),
            "name": step.prompt.name,
        }
        for step in sorted_steps
    ]
    step_names = [s["name"] for s in steps_data]

    # ── Create generation record ──
    generation = Generation(
        user_id=user.id,
        title=data.title or chain.name,
        prompt_text=" → ".join(s.prompt.name for s in sorted_steps),
        model_used=data.model,
        status=GenerationStatus.processing,
        prompt_chain_id=data.chain_id,
    )
    db.add(generation)
    await db.flush()

    for source_id in data.source_ids:
        db.add(GenerationSource(generation_id=generation.id, source_id=source_id))
    await db.commit()
    await db.refresh(generation)

    gen_id = str(generation.id)
    chain_name = chain.name
    chain_description = chain.description

    async def event_stream():
        total = len(steps_data)

        # Phase 1: Planning
        yield _sse_event("phase", {
            "phase": "planning",
            "message": "Analysing chapter & designing workbook...",
            "total_sections": total,
            "section_names": step_names,
        })

        try:
            plan = await llm.create_workbook_plan(
                sources=sources_text,
                steps=steps_data,
                chain_name=chain_name,
                chain_description=chain_description,
                model=data.model,
            )
            planned_steps = plan["steps"]
        except Exception as exc:
            logger.warning("Workbook planner failed, using original prompts: %s", exc)
            planned_steps = [{"prompt": s["prompt"], "format": s.get("format")} for s in steps_data]

        # Phase 2: Generating (single mega-call)
        yield _sse_event("phase", {
            "phase": "generating",
            "message": f"Generating all {total} sections in one shot...",
            "total_sections": total,
            "section_names": step_names,
        })

        try:
            results = await llm.generate_all_sections(
                sources=sources_text,
                planned_steps=planned_steps,
                step_names=step_names,
                model=data.model,
                media_parts=image_parts if image_parts else None,
            )
        except Exception as exc:
            yield _sse_event("error", {"message": str(exc)})
            generation.status = GenerationStatus.error
            generation.error_message = str(exc)
            await db.commit()
            return

        # Phase 3: Processing
        yield _sse_event("phase", {
            "phase": "processing",
            "message": "Processing response & preparing output...",
            "total_sections": total,
        })

        combined = "\n<pagebreak/>\n".join(results)

        generation.status = GenerationStatus.completed
        generation.response_content = combined
        await db.commit()

        yield _sse_event("done", {
            "content": combined,
            "generation_id": gen_id,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
