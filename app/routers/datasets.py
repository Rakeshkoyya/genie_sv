"""Dataset management router."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, ApprovedUser
from app.models.source import Dataset, InputSource
from app.schemas.source import DatasetRead, DatasetCreate, DatasetUpdate, DatasetListResponse, SourceRead

router = APIRouter(prefix="/api/datasets", tags=["Datasets"])


@router.get("", response_model=DatasetListResponse)
async def list_datasets(
    user: ApprovedUser,
    db: DbSession,
    include_sources: bool = Query(False, description="Include input sources in response")
):
    """List user's datasets with source counts and optionally input sources."""
    if include_sources:
        # Fetch datasets with input_sources eagerly loaded
        result = await db.execute(
            select(Dataset)
            .options(selectinload(Dataset.input_sources))
            .where(Dataset.user_id == user.id)
            .order_by(Dataset.created_at.desc())
        )
        datasets_orm = result.scalars().all()
        
        datasets = []
        for ds in datasets_orm:
            dataset_dict = {
                "id": ds.id,
                "user_id": ds.user_id,
                "name": ds.name,
                "description": ds.description,
                "created_at": ds.created_at,
                "updated_at": ds.updated_at,
                "sources_count": len(ds.input_sources),
                "input_sources": [SourceRead.model_validate(s) for s in ds.input_sources]
            }
            datasets.append(DatasetRead(**dataset_dict))
        
        return DatasetListResponse(datasets=datasets, total=len(datasets))
    
    # Original behavior: just get counts
    source_count = (
        select(func.count(InputSource.id))
        .where(InputSource.dataset_id == Dataset.id)
        .correlate(Dataset)
        .scalar_subquery()
    )
    
    result = await db.execute(
        select(Dataset, source_count.label("sources_count"))
        .where(Dataset.user_id == user.id)
        .order_by(Dataset.created_at.desc())
    )
    rows = result.all()
    
    datasets = []
    for dataset, count in rows:
        dataset_dict = DatasetRead.model_validate(dataset).model_dump()
        dataset_dict["sources_count"] = count or 0
        datasets.append(DatasetRead(**dataset_dict))
    
    return DatasetListResponse(datasets=datasets, total=len(datasets))


@router.post("", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    data: DatasetCreate,
    user: ApprovedUser,
    db: DbSession
):
    """Create a new dataset."""
    dataset = Dataset(
        user_id=user.id,
        name=data.name,
        description=data.description
    )
    db.add(dataset)
    await db.commit()
    
    # Re-fetch with input_sources eagerly loaded to avoid lazy-load outside async context
    result = await db.execute(
        select(Dataset)
        .options(selectinload(Dataset.input_sources))
        .where(Dataset.id == dataset.id)
    )
    return result.scalar_one()


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset(
    dataset_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Get a specific dataset."""
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.user_id == user.id
        )
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    
    # Get source count
    count_result = await db.execute(
        select(func.count(InputSource.id)).where(InputSource.dataset_id == dataset_id)
    )
    count = count_result.scalar() or 0
    
    dataset_dict = DatasetRead.model_validate(dataset).model_dump()
    dataset_dict["sources_count"] = count
    
    return DatasetRead(**dataset_dict)


@router.put("/{dataset_id}", response_model=DatasetRead)
async def update_dataset(
    dataset_id: UUID,
    data: DatasetUpdate,
    user: ApprovedUser,
    db: DbSession
):
    """Update a dataset."""
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.user_id == user.id
        )
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dataset, field, value)
    
    await db.commit()
    
    # Re-fetch with input_sources eagerly loaded to avoid lazy-load outside async context
    result = await db.execute(
        select(Dataset)
        .options(selectinload(Dataset.input_sources))
        .where(Dataset.id == dataset.id)
    )
    return result.scalar_one()


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Delete a dataset and its sources."""
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.user_id == user.id
        )
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    
    await db.delete(dataset)
    await db.commit()
    
    return {"success": True}
