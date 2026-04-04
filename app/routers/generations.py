"""Generations history router."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, ApprovedUser
from app.models.generation import Generation, GenerationSource
from app.models.source import InputSource
from app.schemas.generation import GenerationRead, GenerationListResponse

router = APIRouter(prefix="/api/generations", tags=["Generations"])


@router.get("", response_model=GenerationListResponse)
async def list_generations(
    user: ApprovedUser,
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """List user's generation history."""
    # Get generations with sources
    result = await db.execute(
        select(Generation)
        .options(
            selectinload(Generation.generation_sources).selectinload(GenerationSource.source)
        )
        .where(Generation.user_id == user.id)
        .order_by(Generation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    generations = result.scalars().all()
    
    # Get total count
    count_result = await db.execute(
        select(func.count(Generation.id)).where(Generation.user_id == user.id)
    )
    total = count_result.scalar() or 0
    
    # Transform to response format
    generation_reads = []
    for gen in generations:
        sources = [gs.source for gs in gen.generation_sources if gs.source]
        gen_dict = GenerationRead.model_validate(gen).model_dump()
        gen_dict["sources"] = sources
        generation_reads.append(GenerationRead(**gen_dict))
    
    return GenerationListResponse(generations=generation_reads, total=total)


@router.get("/{generation_id}", response_model=GenerationRead)
async def get_generation(
    generation_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Get a specific generation with details."""
    result = await db.execute(
        select(Generation)
        .options(
            selectinload(Generation.generation_sources).selectinload(GenerationSource.source)
        )
        .where(
            Generation.id == generation_id,
            Generation.user_id == user.id
        )
    )
    generation = result.scalar_one_or_none()
    
    if not generation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    
    sources = [gs.source for gs in generation.generation_sources if gs.source]
    gen_dict = GenerationRead.model_validate(generation).model_dump()
    gen_dict["sources"] = sources
    
    return GenerationRead(**gen_dict)


@router.delete("/{generation_id}")
async def delete_generation(
    generation_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Delete a generation."""
    result = await db.execute(
        select(Generation).where(
            Generation.id == generation_id,
            Generation.user_id == user.id
        )
    )
    generation = result.scalar_one_or_none()
    
    if not generation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    
    await db.delete(generation)
    await db.commit()
    
    return {"success": True}
