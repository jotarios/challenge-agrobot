"""Admin-only CRUD for metric types."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin
from src.api.validators import invalidate_metric_cache
from src.models.metric_type import MetricType
from src.shared.db import get_primary_session

router = APIRouter(prefix="/metric-types", tags=["metric-types"])


class MetricTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50, pattern="^[a-z][a-z0-9_]*$")


class MetricTypeResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[MetricTypeResponse])
async def list_metric_types(db: AsyncSession = Depends(get_primary_session)):
    """Public: anyone can see available metric types."""
    result = await db.execute(select(MetricType).order_by(MetricType.name))
    return result.scalars().all()


@router.post("", response_model=MetricTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_metric_type(
    body: MetricTypeCreate,
    _admin: int = Depends(require_admin),
    db: AsyncSession = Depends(get_primary_session),
):
    existing = await db.execute(select(MetricType).where(MetricType.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Metric type already exists")

    mt = MetricType(name=body.name)
    db.add(mt)
    await db.commit()
    await db.refresh(mt)
    invalidate_metric_cache()
    return mt


@router.delete("/{metric_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metric_type(
    metric_type_id: int,
    _admin: int = Depends(require_admin),
    db: AsyncSession = Depends(get_primary_session),
):
    result = await db.execute(select(MetricType).where(MetricType.id == metric_type_id))
    mt = result.scalar_one_or_none()
    if not mt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metric type not found")
    await db.delete(mt)
    await db.commit()
    invalidate_metric_cache()
