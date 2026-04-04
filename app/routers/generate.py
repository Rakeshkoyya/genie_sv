"""Generation router for LLM content generation."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, ApprovedUser
from app.models.source import InputSource
from app.models.prompt import PromptChain, PromptChainStep
from app.models.generation import Generation, GenerationSource, GenerationStatus
from app.schemas.generation import GenerateRequest, GenerateResponse
from app.services.llm import LLMService
from app.services.storage import StorageService
from app.utils.prompt_builder import format_sources_text, prepare_media_parts
from app.config import get_settings

router = APIRouter(prefix="/api/generate", tags=["Generate"])
settings = get_settings()


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
                .selectinload(PromptChainStep.prompt),
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
            # Execute chain steps
            steps = [
                {
                    "prompt": step.prompt.text,
                    "format": step.response_format.template_text if step.response_format else None
                }
                for step in sorted(chain.steps, key=lambda s: s.step_order)
            ]
            
            results = await llm.generate_chain(
                sources=sources_text,
                steps=steps,
                model=data.model,
                media_parts=image_parts if image_parts else None
            )
            
            combined_content = "\n\n---\n\n".join(results)
            
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
