"""Composite rule group CRUD routes. All queries scoped to authenticated user."""

import h3
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_current_user_id
from src.api.schemas import RuleGroupCreate, RuleGroupResponse, RuleGroupUpdate
from src.api.validators import validate_metric_type
from src.models.rule_group import RuleCondition, RuleGroup
from src.shared.constants import H3_RESOLUTION
from src.shared.db import get_primary_session

router = APIRouter(prefix="/rule-groups", tags=["rule-groups"])


def _lat_lon_to_h3(lat: float, lon: float) -> str:
    try:
        return h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid coordinates: lat={lat}, lon={lon}",
        )


async def _get_group_or_404(
    group_id: int, user_id: int, db: AsyncSession
) -> RuleGroup:
    result = await db.execute(
        select(RuleGroup)
        .options(selectinload(RuleGroup.conditions))
        .where(RuleGroup.id == group_id, RuleGroup.user_id == user_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule group not found")
    return group


@router.post("", response_model=RuleGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_rule_group(
    body: RuleGroupCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    for c in body.conditions:
        await validate_metric_type(c.metric_type, db)
    h3_index = _lat_lon_to_h3(body.latitude, body.longitude)
    group = RuleGroup(
        user_id=user_id,
        location_h3_index=h3_index,
        logic=body.logic,
        conditions=[
            RuleCondition(
                metric_type=c.metric_type,
                operator=c.operator.value,
                threshold_value=c.threshold_value,
            )
            for c in body.conditions
        ],
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.get("", response_model=list[RuleGroupResponse])
async def list_rule_groups(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    result = await db.execute(
        select(RuleGroup)
        .options(selectinload(RuleGroup.conditions))
        .where(RuleGroup.user_id == user_id)
        .order_by(RuleGroup.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{group_id}", response_model=RuleGroupResponse)
async def get_rule_group(
    group_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    return await _get_group_or_404(group_id, user_id, db)


@router.put("/{group_id}", response_model=RuleGroupResponse)
async def update_rule_group(
    group_id: int,
    body: RuleGroupUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    group = await _get_group_or_404(group_id, user_id, db)

    if body.latitude is not None and body.longitude is not None:
        group.location_h3_index = _lat_lon_to_h3(body.latitude, body.longitude)

    if body.logic is not None:
        group.logic = body.logic

    if body.conditions is not None:
        for c in body.conditions:
            await validate_metric_type(c.metric_type, db)
        # Replace all conditions
        for old in group.conditions:
            await db.delete(old)
        group.conditions = [
            RuleCondition(
                metric_type=c.metric_type,
                operator=c.operator.value,
                threshold_value=c.threshold_value,
            )
            for c in body.conditions
        ]

    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule_group(
    group_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_primary_session),
):
    group = await _get_group_or_404(group_id, user_id, db)
    await db.delete(group)
    await db.commit()
