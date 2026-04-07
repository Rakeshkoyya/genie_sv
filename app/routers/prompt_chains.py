"""Prompt chain management router."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, ApprovedUser
from app.models.prompt import Prompt, PromptChain, PromptChainStep
from app.schemas.prompt import (
    PromptChainRead, PromptChainCreate, PromptChainUpdate, PromptChainStepCreate
)

router = APIRouter(prefix="/api/prompt-chains", tags=["Prompt Chains"])


@router.get("", response_model=list[PromptChainRead])
async def list_chains(user: ApprovedUser, db: DbSession):
    """List user's prompt chains."""
    result = await db.execute(
        select(PromptChain)
        .options(
            selectinload(PromptChain.steps).selectinload(PromptChainStep.prompt).selectinload(Prompt.response_format),
            selectinload(PromptChain.steps).selectinload(PromptChainStep.response_format)
        )
        .where(PromptChain.user_id == user.id)
        .order_by(PromptChain.created_at.desc())
    )
    chains = result.scalars().all()
    return list(chains)


@router.post("", response_model=PromptChainRead, status_code=status.HTTP_201_CREATED)
async def create_chain(
    data: PromptChainCreate,
    user: ApprovedUser,
    db: DbSession
):
    """Create a new prompt chain with steps."""
    chain = PromptChain(
        user_id=user.id,
        name=data.name,
        description=data.description
    )
    db.add(chain)
    await db.flush()  # Get the chain ID
    
    # Add steps
    for step_data in data.steps:
        step = PromptChainStep(
            chain_id=chain.id,
            prompt_id=step_data.prompt_id,
            step_order=step_data.step_order,
            response_format_id=step_data.response_format_id
        )
        db.add(step)
    
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(PromptChain)
        .options(
            selectinload(PromptChain.steps).selectinload(PromptChainStep.prompt).selectinload(Prompt.response_format),
            selectinload(PromptChain.steps).selectinload(PromptChainStep.response_format)
        )
        .where(PromptChain.id == chain.id)
    )
    chain = result.scalar_one()
    
    return chain


@router.get("/{chain_id}", response_model=PromptChainRead)
async def get_chain(
    chain_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Get a specific prompt chain."""
    result = await db.execute(
        select(PromptChain)
        .options(
            selectinload(PromptChain.steps).selectinload(PromptChainStep.prompt).selectinload(Prompt.response_format),
            selectinload(PromptChain.steps).selectinload(PromptChainStep.response_format)
        )
        .where(
            PromptChain.id == chain_id,
            PromptChain.user_id == user.id
        )
    )
    chain = result.scalar_one_or_none()
    
    if not chain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found")
    
    return chain


@router.patch("/{chain_id}", response_model=PromptChainRead)
async def update_chain(
    chain_id: UUID,
    data: PromptChainUpdate,
    user: ApprovedUser,
    db: DbSession
):
    """Update a prompt chain and optionally its steps."""
    result = await db.execute(
        select(PromptChain).where(
            PromptChain.id == chain_id,
            PromptChain.user_id == user.id
        )
    )
    chain = result.scalar_one_or_none()
    
    if not chain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found")
    
    # Update basic fields
    if data.name is not None:
        chain.name = data.name
    if data.description is not None:
        chain.description = data.description
    
    # Update steps if provided
    if data.steps is not None:
        # Delete existing steps
        await db.execute(
            delete(PromptChainStep).where(PromptChainStep.chain_id == chain_id)
        )
        
        # Add new steps
        for step_data in data.steps:
            step = PromptChainStep(
                chain_id=chain_id,
                prompt_id=step_data.prompt_id,
                step_order=step_data.step_order,
                response_format_id=step_data.response_format_id
            )
            db.add(step)
    
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(PromptChain)
        .options(
            selectinload(PromptChain.steps).selectinload(PromptChainStep.prompt).selectinload(Prompt.response_format),
            selectinload(PromptChain.steps).selectinload(PromptChainStep.response_format)
        )
        .where(PromptChain.id == chain_id)
    )
    chain = result.scalar_one()
    
    return chain


@router.delete("/{chain_id}")
async def delete_chain(
    chain_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Delete a prompt chain."""
    result = await db.execute(
        select(PromptChain).where(
            PromptChain.id == chain_id,
            PromptChain.user_id == user.id
        )
    )
    chain = result.scalar_one_or_none()
    
    if not chain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found")
    
    await db.delete(chain)
    await db.commit()
    
    return {"success": True}
