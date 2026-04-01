"""Notification Dispatcher Lambda handler.

Consumes SQS messages containing Claim Check payloads, validates rules
against the DB, checks cooldown, and dispatches notifications via the
pluggable NotificationProvider interface.

Data flow:
  SQS (Claim Check) → Validate rule exists (replica) → Check cooldown (replica)
  → Send notification (Kapso) → Update last_notified_at (primary)

Uses dual DB connections:
  - Replica: Claim Check reads, cooldown reads
  - Primary: cooldown writes (last_notified_at update)
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from src.models.alert_rule import AlertRule
from src.models.rule_group import RuleGroup
from src.providers.kapso import KapsoClientError, KapsoServerError
from src.shared.config import settings
from src.shared.constants import ALERT_COOLDOWN_MINUTES

logger = Logger()
tracer = Tracer()
metrics = Metrics()

# Dual DB engines: replica for reads, primary for writes
_replica_url = (settings.replica_database_url or settings.database_url).replace(
    "postgresql+asyncpg://", "postgresql://"
)
_primary_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

_replica_engine = create_engine(_replica_url, pool_pre_ping=True, pool_size=2)
_primary_engine = create_engine(_primary_url, pool_pre_ping=True, pool_size=2)

if settings.kapso_api_url:
    from src.providers.kapso import KapsoProvider
    _provider = KapsoProvider()
else:
    from src.providers.mock import MockProvider
    _provider = MockProvider()

# Semaphore to limit concurrent Kapso calls within a batch
_kapso_semaphore = asyncio.Semaphore(5)


async def _send_with_semaphore(user_id, rule_id, triggered_value, correlation_id, metric_type):
    async with _kapso_semaphore:
        return await _provider.send(user_id, rule_id, triggered_value, correlation_id, metric_type)


def _update_cooldown(table_class, record_id: int, correlation_id: str):
    """Update last_notified_at on primary with retries."""
    retries = 2
    for attempt in range(retries + 1):
        try:
            with Session(_primary_engine) as session:
                session.execute(
                    update(table_class)
                    .where(table_class.id == record_id)
                    .values(last_notified_at=datetime.now(timezone.utc))
                )
                session.commit()
            return
        except Exception as e:
            if attempt < retries:
                logger.warning(
                    "DB write failed (attempt %d/%d) for %s %d: %s",
                    attempt + 1, retries + 1, table_class.__tablename__, record_id, e,
                )
            else:
                logger.critical(
                    "DB write failed after %d attempts for %s %d. "
                    "Notification sent but cooldown not updated. correlation_id=%s",
                    retries + 1, table_class.__tablename__, record_id, correlation_id,
                )


def _send_notification(user_id, rule_id, triggered_value, correlation_id, metric_type=""):
    """Call the notification provider. Raises on transient errors for SQS retry."""
    try:
        asyncio.run(
            _send_with_semaphore(user_id, rule_id, triggered_value, correlation_id, metric_type)
        )
    except KapsoClientError:
        return "dropped"
    except KapsoServerError:
        raise
    except Exception as e:
        logger.error("Unexpected error sending notification: %s", e)
        raise
    return "sent"


def _process_single_rule(body: dict) -> str:
    """Process a single-metric AlertRule Claim Check."""
    user_id = body["user_id"]
    rule_id = body["rule_id"]
    triggered_value = body["triggered_value"]
    correlation_id = body["correlation_id"]
    metric_type = body.get("metric_type", "")

    with Session(_replica_engine) as session:
        rule = session.execute(
            select(AlertRule).where(AlertRule.id == rule_id)
        ).scalar_one_or_none()

    if rule is None:
        logger.info("Rule %d deleted, dropping. correlation_id=%s", rule_id, correlation_id)
        metrics.add_metric(name="claim_check_miss", unit=MetricUnit.Count, value=1)
        return "dropped"

    if rule.user_id != user_id:
        logger.warning("Rule %d user mismatch, dropping. correlation_id=%s", rule_id, correlation_id)
        return "dropped"

    metrics.add_metric(name="claim_check_hit", unit=MetricUnit.Count, value=1)

    if rule.last_notified_at is not None:
        cooldown_until = rule.last_notified_at + timedelta(minutes=ALERT_COOLDOWN_MINUTES)
        if datetime.now(timezone.utc) < cooldown_until:
            metrics.add_metric(name="cooldown_skip", unit=MetricUnit.Count, value=1)
            return "dropped"

    result = _send_notification(user_id, rule_id, triggered_value, correlation_id, metric_type)
    if result == "sent":
        _update_cooldown(AlertRule, rule_id, correlation_id)
    return result


def _process_composite_rule(body: dict) -> str:
    """Process a composite RuleGroup Claim Check."""
    user_id = body["user_id"]
    rule_group_id = body["rule_group_id"]
    triggered_values = body.get("triggered_values", {})
    correlation_id = body["correlation_id"]

    with Session(_replica_engine) as session:
        group = session.execute(
            select(RuleGroup).where(RuleGroup.id == rule_group_id)
        ).scalar_one_or_none()

    if group is None:
        logger.info("RuleGroup %d deleted, dropping. correlation_id=%s", rule_group_id, correlation_id)
        metrics.add_metric(name="claim_check_miss", unit=MetricUnit.Count, value=1)
        return "dropped"

    if group.user_id != user_id:
        logger.warning("RuleGroup %d user mismatch, dropping. correlation_id=%s", rule_group_id, correlation_id)
        return "dropped"

    metrics.add_metric(name="claim_check_hit", unit=MetricUnit.Count, value=1)

    if group.last_notified_at is not None:
        cooldown_until = group.last_notified_at + timedelta(minutes=ALERT_COOLDOWN_MINUTES)
        if datetime.now(timezone.utc) < cooldown_until:
            metrics.add_metric(name="cooldown_skip", unit=MetricUnit.Count, value=1)
            return "dropped"

    # Use the first triggered value for the notification payload
    first_metric = next(iter(triggered_values), "")
    first_value = triggered_values.get(first_metric, 0.0)

    result = _send_notification(
        user_id, rule_group_id, first_value, correlation_id, first_metric
    )
    if result == "sent":
        _update_cooldown(RuleGroup, rule_group_id, correlation_id)
    return result


def _process_message(body: dict) -> str:
    """Route to single or composite handler based on payload shape."""
    if "rule_group_id" in body:
        return _process_composite_rule(body)
    return _process_single_rule(body)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event, context):
    """Process SQS batch. Returns batchItemFailures for partial failure handling."""
    failures = []

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            result = _process_message(body)
            logger.info("Message result=%s message_id=%s", result, record["messageId"])
        except Exception as e:
            logger.error("Failed to process message %s: %s", record["messageId"], e)
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}
