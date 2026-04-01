# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agrobot is a weather notification system: users configure weather thresholds (e.g., "temperature > 35°C in Buenos Aires") and receive near real-time notifications when exceeded. It uses an event-driven architecture with CDC (Change Data Capture) to bridge an immutable ingestion pipeline with a dynamic matching engine.

## Architecture

The system has three strictly decoupled phases:

1. **Ingestion** — Black-box pipeline writes to `weather_data` table in RDS PostgreSQL. This pipeline is immutable and cannot be modified.
2. **Capture & Evaluation** — AWS DMS reads the PostgreSQL WAL, streams to Kinesis. A Matching Engine Lambda consumes batches, queries RDS for matching user rules (using H3 spatial indexing), and publishes "Claim Check" payloads to SQS.
3. **Dispatch** — Notification Dispatcher Lambda polls SQS, performs JIT validation against RDS Read Replica (Claim Check pattern to prevent stale notifications), and calls external delivery API (Kapso).

### Key Infrastructure

- **Database:** Amazon RDS PostgreSQL with PostGIS, Read Replica, RDS Proxy
- **Streaming:** Kinesis Data Streams (weather events), SQS (alert queue with DLQ)
- **Compute:** ECS Fargate (API), Lambda (Matching Engine + Dispatcher)
- **API:** FastAPI + SQLAlchemy Async, Dockerized behind API Gateway

### Critical Design Decisions

- Locations are translated to H3 hexagon indices at the API level before DB storage
- Claim Check pattern: SQS payloads contain only references (`user_id`, `rule_id`, `triggered_value`), not full state. Dispatcher re-validates before sending.
- Alert cooldown via `alert_lock` (Redis/ElastiCache TTL or `last_notified_at` in DB) to prevent notification spam
- Matching Engine queries must return in <50ms; `AlertRules` table needs composite indexes on `(location_h3_index, metric_type, threshold_value)`

## Tech Stack

- **Language:** Python
- **API Framework:** FastAPI with Pydantic validation
- **ORM:** SQLAlchemy Async
- **Testing:** Pytest
- **Observability:** aws-lambda-powertools (structured JSON logging), AWS X-Ray, Sentry
- **Local Dev:** Docker Compose with PostgreSQL+PostGIS, LocalStack (mocks Kinesis/SQS/SES)

## Local Development

Local environment uses Docker Compose:
- PostgreSQL container with PostGIS
- LocalStack container at `http://localhost:4566` for AWS services
- `ingest.py` simulator mocks the black-box pipeline
- Matching/Dispatcher run as local Python processes pointing to LocalStack

## Testing

- **Unit tests:** `pytest` — FastAPI routes, Pydantic validation, threshold comparison logic
- **Integration tests:** Run against ephemeral AWS sandbox (CI/CD)
- **Load tests:** Locust or Artillery to simulate severe weather events

## Important Constraints

- The ingestion pipeline is a black box: no triggers, no structural changes to the ingestion process
- AWS-native infrastructure only
- Sentry should only capture unhandled crashes, not expected API timeouts/503s (to prevent quota exhaustion during weather spikes)
- Every matched event needs a `correlation_id` UUID passed through the entire pipeline for traceability
