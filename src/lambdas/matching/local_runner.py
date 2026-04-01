"""Local runner for the Matching Engine.

Polls LocalStack Kinesis and invokes the Lambda handler logic directly.
Used for local development via Docker Compose.

Usage: python -m src.lambdas.matching.local_runner
"""

import json
import logging
import time

import boto3

from src.shared.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [matching] %(message)s")
logger = logging.getLogger(__name__)


def main():
    kinesis = boto3.client(
        "kinesis",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
    )

    stream_name = settings.kinesis_stream_name
    logger.info("Waiting for Kinesis stream '%s'...", stream_name)

    # Wait for stream to be ready
    while True:
        try:
            resp = kinesis.describe_stream(StreamName=stream_name)
            if resp["StreamDescription"]["StreamStatus"] == "ACTIVE":
                break
        except Exception:
            pass
        time.sleep(2)

    logger.info("Stream active. Starting to poll shards...")

    # Get shard iterators
    shards = resp["StreamDescription"]["Shards"]
    iterators = {}
    for shard in shards:
        shard_id = shard["ShardId"]
        it_resp = kinesis.get_shard_iterator(
            StreamName=stream_name,
            ShardId=shard_id,
            ShardIteratorType="LATEST",
        )
        iterators[shard_id] = it_resp["ShardIterator"]

    # Import handler after config is loaded
    from src.lambdas.matching.parser import parse_dms_record
    from src.lambdas.matching.handler import record_handler, _upsert_latest_reading, _evaluate_composite_rules, _publish_to_sqs, evaluate_threshold
    from src.lambdas.matching.handler import _engine, h3, uuid, AlertRule, metrics
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.shared.constants import H3_RESOLUTION

    while True:
        for shard_id, iterator in list(iterators.items()):
            try:
                resp = kinesis.get_records(ShardIterator=iterator, Limit=100)
                iterators[shard_id] = resp["NextShardIterator"]

                for record in resp["Records"]:
                    # boto3 returns Data as bytes already, no base64 decode needed
                    raw_data = record["Data"].decode("utf-8") if isinstance(record["Data"], bytes) else record["Data"]
                    logger.info("Received record: %s", raw_data[:200])

                    # Process inline (same logic as Lambda handler)
                    weather_event = parse_dms_record(raw_data)
                    if weather_event is None:
                        continue

                    lat = weather_event.get("location_lat")
                    lon = weather_event.get("location_lon")
                    metric_type = weather_event.get("metric_type")
                    value = weather_event.get("value")

                    if None in (lat, lon, metric_type, value):
                        logger.error("Missing fields: %s", weather_event)
                        continue

                    try:
                        h3_index = h3.latlng_to_cell(float(lat), float(lon), H3_RESOLUTION)
                    except Exception:
                        logger.error("H3 failed: lat=%s lon=%s", lat, lon)
                        continue

                    try:
                        _upsert_latest_reading(h3_index, metric_type, float(value))
                    except Exception as e:
                        logger.warning("latest_reading upsert failed: %s", e)

                    # Single rules
                    with Session(_engine) as session:
                        rules = session.execute(
                            select(AlertRule).where(
                                AlertRule.location_h3_index == h3_index,
                                AlertRule.metric_type == metric_type,
                            )
                        ).scalars().all()

                    matched = [r for r in rules if evaluate_threshold(r.operator, float(value), float(r.threshold_value))]
                    correlation_id = str(uuid.uuid4())

                    if matched:
                        _publish_to_sqs([
                            {"user_id": r.user_id, "rule_id": r.id, "triggered_value": float(value),
                             "metric_type": metric_type, "correlation_id": correlation_id}
                            for r in matched
                        ])
                        logger.info("Matched %d single rules, correlation_id=%s", len(matched), correlation_id)

                    # Composite rules
                    try:
                        composites = _evaluate_composite_rules(h3_index, metric_type)
                        if composites:
                            _publish_to_sqs([
                                {"user_id": m["user_id"], "rule_group_id": m["rule_group_id"],
                                 "triggered_values": m["triggered_values"], "correlation_id": correlation_id}
                                for m in composites
                            ])
                            logger.info("Matched %d composite rules", len(composites))
                    except Exception as e:
                        logger.error("Composite eval failed: %s", e)

            except Exception as e:
                logger.error("Shard %s error: %s", shard_id, e)

        time.sleep(1)


if __name__ == "__main__":
    main()
