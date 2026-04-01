"""Health and status endpoints."""

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin
from src.shared.config import settings
from src.shared.db import get_primary_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_primary_session)):
    checks = {"db": "ok"}

    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        checks["db"] = "unavailable"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "checks": checks},
        )

    if settings.environment != "development":
        try:
            kinesis = boto3.client(
                "kinesis",
                region_name=settings.aws_region,
                endpoint_url=settings.aws_endpoint_url,
            )
            kinesis.describe_stream(StreamName=settings.kinesis_stream_name)
            checks["kinesis"] = "ok"
        except Exception:
            checks["kinesis"] = "unavailable"

    return {"status": "healthy", "checks": checks}


@router.get("/status")
async def system_status(
    _admin_user_id: int = Depends(require_admin),
):
    """Operational metrics. Admin-scoped."""
    metrics = {}

    try:
        boto_kwargs = {
            "region_name": settings.aws_region,
        }
        if settings.aws_endpoint_url:
            boto_kwargs["endpoint_url"] = settings.aws_endpoint_url

        sqs = boto3.client("sqs", **boto_kwargs)

        if settings.sqs_queue_url:
            attrs = sqs.get_queue_attributes(
                QueueUrl=settings.sqs_queue_url,
                AttributeNames=["ApproximateNumberOfMessagesVisible"],
            )
            metrics["sqs_queue_depth"] = int(
                attrs["Attributes"].get("ApproximateNumberOfMessagesVisible", 0)
            )

        if settings.sqs_dlq_url:
            dlq_attrs = sqs.get_queue_attributes(
                QueueUrl=settings.sqs_dlq_url,
                AttributeNames=["ApproximateNumberOfMessagesVisible"],
            )
            metrics["dlq_depth"] = int(
                dlq_attrs["Attributes"].get("ApproximateNumberOfMessagesVisible", 0)
            )
    except Exception as e:
        metrics["sqs_error"] = str(e)

    return {"status": "ok", "metrics": metrics}
