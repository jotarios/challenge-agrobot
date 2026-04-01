"""Alert rule CRUD routes. All queries scoped to authenticated user (IDOR prevention)."""

import h3
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user_id
from src.api.schemas import RuleCreate, RuleResponse, RuleUpdate
from src.api.validators import validate_metric_type
from src.models.alert_rule import AlertRule
from src.shared.constants import H3_RESOLUTION
from src.shared.db import get_primary_session

router = APIRouter(prefix="/rules", tags=["rules"])


def _lat_lon_to_h3(lat: float, lon: float) -> str:
    try:
        return h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid coordinates: lat={lat}, lon={lon}",
        )


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    await validate_metric_type(body.metric_type, db)
    h3_index = _lat_lon_to_h3(body.latitude, body.longitude)
    rule = AlertRule(
        user_id=user_id,
        location_h3_index=h3_index,
        metric_type=body.metric_type,
        operator=body.operator.value,
        threshold_value=body.threshold_value,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("", response_model=list[RuleResponse])
async def list_rules(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    result = await db.execute(
        select(AlertRule).where(AlertRule.user_id == user_id).order_by(AlertRule.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: int,
    body: RuleUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    if body.latitude is not None or body.longitude is not None:
        lat = body.latitude if body.latitude is not None else None
        lon = body.longitude if body.longitude is not None else None
        if lat is not None and lon is not None:
            rule.location_h3_index = _lat_lon_to_h3(lat, lon)

    if body.metric_type is not None:
        await validate_metric_type(body.metric_type, db)
        rule.metric_type = body.metric_type
    if body.operator is not None:
        rule.operator = body.operator.value
    if body.threshold_value is not None:
        rule.threshold_value = body.threshold_value

    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    await db.delete(rule)
    await db.commit()
