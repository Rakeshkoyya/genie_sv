"""Workflow router – start, list and poll workflow runs."""

import asyncio
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func

from app.dependencies import DbSession, ApprovedUser
from app.models.workflow import WorkflowRun, WorkflowStatus
from app.schemas.workflow import WorkflowRunCreate, WorkflowRunRead, WorkflowRunListResponse
from app.services.workflow import run_workflow

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


@router.post("", response_model=WorkflowRunRead, status_code=status.HTTP_201_CREATED)
async def start_workflow(
    data: WorkflowRunCreate,
    user: ApprovedUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
):
    """Create and start a workflow run in the background."""
    if not data.source_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No source files selected")
    if data.output_format not in ("docx", "txt"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Output format must be docx or txt")

    workflow = WorkflowRun(
        user_id=user.id,
        dataset_id=data.dataset_id,
        chain_id=data.chain_id,
        output_format=data.output_format,
        filename_prefix=data.filename_prefix,
        model=data.model,
        status=WorkflowStatus.pending,
        source_ids=[str(sid) for sid in data.source_ids],
        total_files=len(data.source_ids),
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    # Fire and forget – runs in its own DB session
    background_tasks.add_task(run_workflow, workflow.id)

    return workflow


@router.get("", response_model=WorkflowRunListResponse)
async def list_workflows(
    user: ApprovedUser,
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List user's workflow runs."""
    query = (
        select(WorkflowRun)
        .where(WorkflowRun.user_id == user.id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    workflows = result.scalars().all()

    count_result = await db.execute(
        select(func.count(WorkflowRun.id)).where(WorkflowRun.user_id == user.id)
    )
    total = count_result.scalar() or 0

    return WorkflowRunListResponse(workflows=workflows, total=total)


@router.get("/{workflow_id}", response_model=WorkflowRunRead)
async def get_workflow(
    workflow_id: UUID,
    user: ApprovedUser,
    db: DbSession,
):
    """Get workflow status/progress (polling endpoint)."""
    result = await db.execute(
        select(WorkflowRun).where(
            WorkflowRun.id == workflow_id,
            WorkflowRun.user_id == user.id,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: UUID,
    user: ApprovedUser,
    db: DbSession,
):
    """Cancel a running workflow (marks as cancelled; in-flight LLM calls finish)."""
    result = await db.execute(
        select(WorkflowRun).where(
            WorkflowRun.id == workflow_id,
            WorkflowRun.user_id == user.id,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    if workflow.status in (WorkflowStatus.completed, WorkflowStatus.error, WorkflowStatus.cancelled):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workflow already finished")

    workflow.status = WorkflowStatus.cancelled
    await db.commit()
    return {"success": True}
