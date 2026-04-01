# Agrobot - Weather Notification System

**Document Version:** 1.0

**Date:** March 31, 2026

**Status:** Approved for Architecture Design

---

## 1. Executive Summary

The objective is to build a highly scalable, asynchronous backend system that allows users to configure personal weather thresholds (e.g., "temperature > 35°C in Buenos Aires") and receive near real-time notifications when those thresholds are exceeded. The system must ingest live meteorological data from an existing, immutable data pipeline and evaluate it against millions of potential user configurations without bottlenecking.

## 2. Goals & Constraints

### 2.1. System Goals

- Provide a RESTful API for users to manage their notification profiles and alert rules.
- Evaluate incoming weather data against user rules in near real-time.
- Deliver notifications (via third-party APIs like [Kapso](https://kapso.ai/)) reliably.
- Ensure 100% accuracy in notifications (avoiding "ghost" and duplicated notifications due to stale state).

### 2.2. Architectural Constraints

- **Locked Ingestion:** The existing data pipeline inserting weather data into PostgreSQL is a "black box" and **cannot be modified**. No triggers, no structural changes to the ingestion process but we can model the data.
- **AWS Native:** The infrastructure must be hosted primarily on AWS using managed, serverless, or native cloud components where cost-effective.
- **Decoupling:** The ingestion, matching, and notification delivery phases must be strictly isolated to scale independently and prevent cascading failures.

---

## 3. System Architecture & Data Flow

The system utilizes an Event-Driven Architecture, relying heavily on Change Data Capture (CDC) to bridge the gap between the immutable ingestion pipeline and our dynamic matching engine.

### 3.1. Infrastructure Mapping (AWS Native)

- **Primary Database:** Amazon RDS (PostgreSQL) - Stores both weather data and user configurations.
- **Event Bridge (CDC):** AWS DMS (Database Migration Service) - Reads the PostgreSQL Write-Ahead Log (WAL).
- **Message Brokers:**
    - Amazon Kinesis Data Streams (High-throughput weather event streaming).
    - Amazon SQS (Reliable queue for triggered alerts).
- **Compute:**
    - Amazon ECS on AWS Fargate (Core API hosting).
    - AWS Lambda (Matching Engine & Notification Dispatcher).
- **Networking / DB Scaling:** Amazon RDS Read Replica + Amazon RDS Proxy.
### 3.2. Data Flow

1. **Ingestion:** The black-box pipeline writes to the `weather_data` table in RDS.
2. **Capture:** AWS DMS continuously reads the RDS WAL and streams new insert events to Kinesis.
3. **Evaluation:** The **Matching Engine Lambda** consumes batches from Kinesis, queries the RDS database for matching user rules (using spatial indexing), and publishes "Claim Check" payloads to SQS.
4. **Dispatch:** The **Notification Dispatcher Lambda** polls SQS, executes the Claim Check against the RDS Read Replica to ensure the rule is still valid, and triggers the external delivery API.

---

## 4. Core Components & Logic

### 4.1. Core API (Rule Management)

- **Framework:** FastAPI (Python), SQLAlchemy Async.
- **Hosting:** Dockerized on Amazon ECS (Fargate) behind an Amazon API Gateway.
- **Responsibility:** CRUD operations for user profiles and `AlertRules`.
- **Data Model Note:** Locations should be translated into spatial indices (e.g., Uber's H3 hexagons) at the API level before saving to the database to optimize the Matching Engine's query speed.

### 4.2. The Claim Check Pattern (State Validation)

To prevent race conditions where a user updates a threshold while an alert is sitting in the SQS queue, the system implements a Just-In-Time (JIT) validation.

- The SQS payload only contains references: `{"user_id": 123, "rule_id": 456, "triggered_value": 36}`
- Before calling the external delivery API, the Dispatcher Lambda queries the **RDS Read Replica** via **RDS Proxy** to confirm the user's current threshold is still `<= 36`. If the rule was updated or deleted, the message is silently dropped.

---

## 5. Non-Functional Requirements (NFRs)

- **Scalability:** The system must handle sudden, massive spikes in weather events (e.g., a severe storm triggering 100,000 rules simultaneously). Kinesis and SQS provide infinite buffering, while Lambda provides auto-scaling compute.
- **Fault Tolerance:** Third-party delivery APIs will fail. SQS must be configured with Dead Letter Queues (DLQs) and exponential backoff.
- **Performance:** The Matching Engine queries must return in under 50ms. The `AlertRules` table requires heavy composite indexing (e.g., on `location_h3_index`, `metric_type`, `threshold_value`).
- **Idempotency / Rate Limiting:** To prevent spamming users if a weather condition persists, the system must implement an `alert_lock` mechanism (e.g., storing a TTL key in Redis/ElastiCache or tracking `last_notified_at` in the DB) to enforce a cooldown period per rule.

---

## 6. Observability & Monitoring

Because the architecture is highly distributed, observability must follow the "Three Pillars" specifically tailored for AWS serverless.

### 6.1. Metrics & Alarms (AWS CloudWatch)

Alarms will be configured to page the engineering team via PagerDuty/Slack for the following critical thresholds:

- **Kinesis `IteratorAgeMilliseconds`:** Alarm if > 60 seconds (indicates the Matching Engine is falling behind real-time).
- **SQS `ApproximateNumberOfMessagesVisible`:** Alarm if queue depth exceeds expected burst capacity.
- **SQS DLQ Depth:** Alarm if messages are entering the Dead Letter Queue (indicates persistent Dispatcher failures).
- **Lambda `Errors` & `Throttles`:** Alarm on execution failures or concurrency limits being hit.

### 6.2. Distributed Tracing & Logging

- **AWS X-Ray:** Enabled across API Gateway, Lambda, and SQS to visualize request execution paths and identify latency bottlenecks.
- **Structured Logging:** All Lambda functions and FastAPI containers must use `aws-lambda-powertools` to output JSON logs.
- **Correlation IDs:** Every matched event must generate a UUID (`correlation_id`). This ID is passed into SQS and logged by the Dispatcher, allowing engineers to query CloudWatch Logs Insights for the entire lifecycle of a specific alert.

### 6.3. Code-Level Error Tracking (Sentry)

- **Integration:** Sentry SDK deployed in FastAPI and as a Lambda Layer for the async workers.
- **Storm Spike Protection:** The Dispatcher Lambda must use `try/except` to catch expected external API timeouts/503s and log them as warnings to CloudWatch, allowing SQS to retry normally. **Only unhandled code crashes** should be routed to Sentry to prevent quota exhaustion during a massive weather event.
    

---

## 7. Testing Strategy

### 7.1. Local Development Environment

Engineers will test the entire event-driven flow locally without incurring AWS costs using **Docker Compose**.

- **PostgreSQL Container:** Acts as the primary DB with PostGIS
- **LocalStack Container:** Mocks AWS Kinesis, SQS, and SES endpoints locally.
- **Python Simulators:**
    - `ingest.py`: Mocks the black-box pipeline by inserting randomized weather data.
    - Matching and Dispatcher logic run as local continuous Python processes, configured via `boto3` to point to LocalStack (`http://localhost:4566`).

### 7.2. Automated Testing

- **Unit Tests:** Pytest for FastAPI routes, Pydantic validation, and core threshold comparison logic.
- **Integration Tests:** Deployed via CI/CD pipeline against an ephemeral AWS sandbox environment to verify IAM roles, DMS replication, and SQS DLQ redrive policies.
- **Load Testing:** Simulate a "Severe Weather Event" using a tool like Locust or Artillery to flood the DB with updates and verify RDS Read Replica CPU usage, RDS Proxy connection pooling, and Lambda concurrency limits.

