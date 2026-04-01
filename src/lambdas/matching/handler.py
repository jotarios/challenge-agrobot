"""Matching Engine Lambda handler.

Consumes Kinesis batches of weather events from DMS CDC, matches against
user alert rules using H3 spatial indexing, and publishes Claim Check
payloads to SQS.

Data flow:
  Kinesis (DMS CDC) → Parse envelope → H3 lookup → Fetch rules from DB
  → Filter by threshold in Python → Publish matched rules to SQS

Uses aws-lambda-powertools Batch Processor for partial batch failure handling.
"""

import json
import logging
import uuid

import boto3
import h3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    batch_processor,
)
from aws_lambda_powertools.utilities.data_classes.kinesis_stream_event import (
    KinesisStreamRecord,
)
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from src.lambdas.matching.parser import parse_dms_record
from src.models.alert_rule import AlertRule
from src.models.latest_reading import LatestReading
from src.models.rule_group import RuleGroup
from src.shared.config import settings
from src.shared.constants import H3_RESOLUTION
from src.shared.threshold import evaluate_threshold

logger = Logger()
tracer = Tracer()
metrics = Metrics()
processor = BatchProcessor(event_type=EventType.KinesisDataStreams)

# Synchronous engines for Lambda
# Replica for reads (matching queries)
_replica_url = (settings.replica_database_url or settings.database_url).replace(
    "postgresql+asyncpg://", "postgresql://"
)
_engine = create_engine(_replica_url, pool_pre_ping=True, pool_size=2)

# Primary for writes (latest_readings upsert)
_primary_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
_primary_engine = create_engine(_primary_url, pool_pre_ping=True, pool_size=2)

_sqs = boto3.client(
    "sqs",
    region_name=settings.aws_region,
    endpoint_url=settings.aws_endpoint_url,
)


def _upsert_latest_reading(h3_index: str, metric_type: str, value: float):
    """Upsert the latest weather value for composite rule evaluation."""
    from datetime import datetime, timezone
    from sqlalchemy.orm import Session

    with Session(_primary_engine) as session:
        stmt = pg_insert(LatestReading).values(
            h3_index=h3_index,
            metric_type=metric_type,
            value=value,
            recorded_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["h3_index", "metric_type"],
            set_={"value": stmt.excluded.value, "recorded_at": stmt.excluded.recorded_at},
        )
        session.execute(stmt)
        session.commit()


def _evaluate_composite_rules(h3_index: str, metric_type: str) -> list[dict]:
    """Evaluate composite RuleGroups that have a condition on the given metric.

    Returns list of {rule_group_id, user_id, triggered_values} for matched groups.
    """
    from sqlalchemy.orm import Session

    with Session(_engine) as session:
        # Find RuleGroups at this H3 cell
        groups = session.execute(
            select(RuleGroup)
            .options(selectinload(RuleGroup.conditions))
            .where(RuleGroup.location_h3_index == h3_index)
        ).scalars().all()

        # Filter to groups that have a condition on the incoming metric_type
        relevant_groups = [
            g for g in groups
            if any(c.metric_type == metric_type for c in g.conditions)
        ]

        if not relevant_groups:
            return []

        # Fetch all latest readings for this H3 cell
        readings = session.execute(
            select(LatestReading).where(LatestReading.h3_index == h3_index)
        ).scalars().all()

        reading_map = {r.metric_type: float(r.value) for r in readings}

        # Evaluate all groups within the session scope
        matched = []
        for group in relevant_groups:
            results = []
            triggered_values = {}
            for cond in group.conditions:
                current_value = reading_map.get(cond.metric_type)
                if current_value is None:
                    results.append(False)
                    continue
                passed = evaluate_threshold(cond.operator, current_value, float(cond.threshold_value))
                results.append(passed)
                if passed:
                    triggered_values[cond.metric_type] = current_value

            if group.logic == "and" and all(results):
                matched.append({
                    "rule_group_id": group.id,
                    "user_id": group.user_id,
                    "triggered_values": triggered_values,
                })
            elif group.logic == "or" and any(results):
                matched.append({
                    "rule_group_id": group.id,
                    "user_id": group.user_id,
                    "triggered_values": triggered_values,
                })

    return matched


def _publish_to_sqs(entries_data: list[dict]):
    """Publish messages to SQS in batches of 10.

    SQS requires unique IDs within each SendMessageBatch call.
    We use the position within the current batch (0-9), reset per call.
    """
    batch = []
    for data in entries_data:
        batch.append({"Id": str(len(batch)), "MessageBody": json.dumps(data)})
        if len(batch) == 10:
            _sqs.send_message_batch(QueueUrl=settings.sqs_queue_url, Entries=batch)
            batch = []
    if batch:
        _sqs.send_message_batch(QueueUrl=settings.sqs_queue_url, Entries=batch)


@tracer.capture_method
def record_handler(record: KinesisStreamRecord):
    """Process a single Kinesis record.

    Two evaluation paths:
    1. Single-metric AlertRules (existing)
    2. Composite RuleGroups (new) via latest_readings
    """
    raw_data = record.kinesis.data_as_text()
    weather_event = parse_dms_record(raw_data)
    if weather_event is None:
        return

    lat = weather_event.get("location_lat")
    lon = weather_event.get("location_lon")
    metric_type = weather_event.get("metric_type")
    value = weather_event.get("value")

    if lat is None or lon is None or metric_type is None or value is None:
        logger.error("Missing required fields in weather event: %s", weather_event)
        return

    try:
        h3_index = h3.latlng_to_cell(float(lat), float(lon), H3_RESOLUTION)
    except Exception:
        logger.error("H3 conversion failed for coords: lat=%s, lon=%s", lat, lon)
        return

    # ── Upsert latest reading (for composite rule evaluation) ────
    try:
        _upsert_latest_reading(h3_index, metric_type, float(value))
    except Exception as e:
        logger.warning("Failed to upsert latest_reading: %s", e)
        # Non-fatal: single-metric rules still work without this

    # ── Path 1: Single-metric AlertRules ─────────────────────────
    from sqlalchemy.orm import Session

    with Session(_engine) as session:
        result = session.execute(
            select(AlertRule).where(
                AlertRule.location_h3_index == h3_index,
                AlertRule.metric_type == metric_type,
            )
        )
        rules = result.scalars().all()

    metrics.add_metric(name="rules_evaluated", unit=MetricUnit.Count, value=len(rules))

    matched_singles = []
    for rule in rules:
        if evaluate_threshold(rule.operator, float(value), float(rule.threshold_value)):
            matched_singles.append(rule)

    correlation_id = str(uuid.uuid4())

    if matched_singles:
        sqs_entries = [
            {
                "user_id": rule.user_id,
                "rule_id": rule.id,
                "triggered_value": float(value),
                "metric_type": metric_type,
                "correlation_id": correlation_id,
            }
            for rule in matched_singles
        ]
        _publish_to_sqs(sqs_entries)

    # ── Path 2: Composite RuleGroups ─────────────────────────────
    try:
        composite_matches = _evaluate_composite_rules(h3_index, metric_type)
    except Exception as e:
        logger.error("Composite rule evaluation failed: %s", e)
        composite_matches = []

    if composite_matches:
        sqs_entries = [
            {
                "user_id": m["user_id"],
                "rule_group_id": m["rule_group_id"],
                "triggered_values": m["triggered_values"],
                "correlation_id": correlation_id,
            }
            for m in composite_matches
        ]
        _publish_to_sqs(sqs_entries)

    total = len(matched_singles) + len(composite_matches)
    metrics.add_metric(name="matches_found", unit=MetricUnit.Count, value=total)

    if total > 0:
        logger.info(
            "Published %d matches (%d single, %d composite) correlation_id=%s h3=%s",
            total, len(matched_singles), len(composite_matches), correlation_id, h3_index,
        )
    else:
        logger.debug("No matches for h3=%s metric=%s value=%s", h3_index, metric_type, value)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
@batch_processor(record_handler=record_handler, processor=processor)
def lambda_handler(event, context):
    return processor.response()
