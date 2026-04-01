"""Async validators that check dynamic data against the database.

Metric type validation uses an in-memory cache with 60s TTL to avoid
hitting the DB on every rule create/update. The metric_types table
changes rarely (admin action only), so staleness is acceptable.
"""

import time

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.metric_type import MetricType

_metric_cache: set[str] = set()
_cache_ts: float = 0.0
_CACHE_TTL = 60.0


async def _refresh_cache(db: AsyncSession) -> set[str]:
    global _metric_cache, _cache_ts
    result = await db.execute(select(MetricType.name))
    _metric_cache = {row[0] for row in result.all()}
    _cache_ts = time.monotonic()
    return _metric_cache


async def get_valid_metric_types(db: AsyncSession) -> set[str]:
    """Return the set of valid metric type names, cached for 60s."""
    if time.monotonic() - _cache_ts > _CACHE_TTL or not _metric_cache:
        return await _refresh_cache(db)
    return _metric_cache


def invalidate_metric_cache() -> None:
    """Call after admin creates/deletes a metric type."""
    global _cache_ts
    _cache_ts = 0.0


async def validate_metric_type(metric_type: str, db: AsyncSession) -> None:
    """Raise 422 if metric_type is not in the metric_types table."""
    valid = await get_valid_metric_types(db)
    if metric_type not in valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown metric_type '{metric_type}'. Valid types: {', '.join(sorted(valid))}",
        )
