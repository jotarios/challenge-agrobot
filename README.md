# Agrobot

Weather notification system. Users configure weather thresholds ("temperature > 35 in Buenos Aires") and receive near real-time notifications when exceeded.

Uses an event-driven architecture with CDC (Change Data Capture) to bridge an immutable ingestion pipeline with a dynamic matching engine.

## Architecture

```
  Black-box Pipeline                    Matching Engine              Dispatcher
  (writes weather_data)                 (Lambda / local poller)      (Lambda / local poller)
         |                                     |                           |
         v                                     v                           v
  +-----------+    WAL    +-------+  Kinesis  +------------------+  SQS  +------------------+
  | PostgreSQL |--------->|  DMS  |---------->| Parse event      |------>| Claim Check      |
  | (RDS)      |          +-------+           | H3 lookup        |       | Cooldown check   |
  +-----------+                               | Fetch rules      |       | Send notification|
                                              | Filter threshold |       | Update cooldown  |
                                              +------------------+       +------------------+
                                                     |                          |
                                              +------v------+           +------v------+
                                              | latest_      |           | Kapso API   |
                                              | readings     |           | (or mock)   |
                                              | (composite)  |           +-------------+
                                              +-------------+
```

**Key components:**

| Component | Tech | Purpose |
|-----------|------|---------|
| API | FastAPI + SQLAlchemy Async | Rule CRUD, auth, health checks |
| Matching Engine | Lambda (Powertools Batch Processor) | Evaluate weather events against user rules |
| Dispatcher | Lambda | Validate and deliver notifications |
| Database | PostgreSQL + PostGIS | Users, rules, weather data, latest readings |
| Streaming | Kinesis (2 shards) | Weather event stream from CDC |
| Queue | SQS + DLQ | Alert delivery with retry |
| IaC | AWS CDK | All infrastructure as code |
| Local dev | Docker Compose + LocalStack | Full stack locally |

## Scale Assumptions

- **500k+ weather events per day** ingested from the black-box pipeline
- Average weather event:
    - Payload size: ~200 bytes (lat, lon, metric, value, timestamp)
    - One event triggers evaluation against all rules in that H3 cell
    - Hot cells (major cities) may have 1,000-10,000 rules
- **Burst capacity:** Severe weather events can produce 10,000+ events in 30 seconds across adjacent H3 cells
- **Matching Engine throughput:** <50ms per rule evaluation query at 100k rules (verified via EXPLAIN ANALYZE)
- **Notification volume:** ~5-10% of weather events trigger at least one rule match, producing ~25k-50k notifications/day
- **Cooldown impact:** 15-minute cooldown per rule reduces actual Kapso API calls by ~80% during sustained weather events
- **Data retention:**
    - `weather_data`: Owned by pipeline, retention managed externally
    - `latest_readings`: One row per (H3 cell, metric), bounded by geographic coverage (~50k rows at scale)
    - `alert_rules` + `rule_groups`: Grows with user base, target 1M+ rules
- **Growth:** Designed for 10x current load without architectural changes (add Kinesis shards + Lambda concurrency)

## Prerequisites

- **Docker** >= 24.0 and **Docker Compose** >= 2.20
- **Make** (pre-installed on macOS/Linux)
- **Python 3.11+** (only needed if running tests locally outside Docker)

## Quick Start

```bash

# Start everything (postgres, localstack, api, matching-engine, dispatcher)
make up

# Open the dashboard
make dashboard
# -> http://localhost:8000/dashboard

# Open the API docs
make docs
# -> http://localhost:8000/docs
```

The API starts with seed data: 2 users, 8 alert rules across 5 cities, 2 composite rules, and 5 metric types.

**Seed accounts:**

| Email | Password | Role |
|-------|----------|------|
| admin@agrobot.com | admin123 | Admin |
| user@agrobot.com | password123 | User |

## Simulate Weather Events

```bash
# Watch the matching engine and dispatcher process events
make watch

# In another terminal, run a scenario:
make simulate-normal    # 30s steady-state across all cities
make simulate-heat      # 10s heat wave in Buenos Aires (temp > 38)
make simulate-cold      # 10s cold snap in Sao Paulo (temp < -5)
make simulate-storm     # 100-event burst across Buenos Aires region
```

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | /auth/register | Register a new user |
| POST | /auth/login | Get JWT token |

### Alert Rules (single-metric)
| Method | Path | Description |
|--------|------|-------------|
| POST | /rules | Create a rule |
| GET | /rules | List your rules |
| GET | /rules/{id} | Get a rule |
| PUT | /rules/{id} | Update a rule |
| DELETE | /rules/{id} | Delete a rule |

### Rule Groups (composite, AND/OR)
| Method | Path | Description |
|--------|------|-------------|
| POST | /rule-groups | Create a composite rule (min 2 conditions) |
| GET | /rule-groups | List your composite rules |
| GET | /rule-groups/{id} | Get a composite rule |
| PUT | /rule-groups/{id} | Update a composite rule |
| DELETE | /rule-groups/{id} | Delete a composite rule |

### Metric Types (admin-configurable)
| Method | Path | Description |
|--------|------|-------------|
| GET | /metric-types | List all metric types (public) |
| POST | /metric-types | Add a metric type (admin only) |
| DELETE | /metric-types/{id} | Remove a metric type (admin only) |

### Operations
| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Liveness check |
| GET | /status | System metrics (admin only) |
| GET | /dashboard | Local dev dashboard (HTML) |

## API Usage Examples

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@agrobot.com","password":"password123"}' | jq -r .access_token)

# Create a single rule: temperature > 30 in Buenos Aires
curl -s -X POST http://localhost:8000/rules \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"latitude":-34.6037,"longitude":-58.3816,"metric_type":"temperature","operator":"gt","threshold_value":30.0}' | jq

# Create a composite rule: temperature > 35 AND humidity < 20
curl -s -X POST http://localhost:8000/rule-groups \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "latitude": -34.6037,
    "longitude": -58.3816,
    "logic": "and",
    "conditions": [
      {"metric_type": "temperature", "operator": "gt", "threshold_value": 35.0},
      {"metric_type": "humidity", "operator": "lt", "threshold_value": 20.0}
    ]
  }' | jq

# Add a new metric type (admin only)
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@agrobot.com","password":"admin123"}' | jq -r .access_token)

curl -s -X POST http://localhost:8000/metric-types \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name":"uv_index"}' | jq
```

## Project Structure

```
src/
  api/                    FastAPI application
    routers/              Route handlers (auth, rules, rule-groups, health, etc.)
    middleware/            Rate limiting
    schemas.py            Pydantic request/response models
    validators.py         DB-backed metric type validation (cached)
    deps.py               JWT auth dependencies
  lambdas/
    matching/             Matching Engine (Kinesis consumer)
      handler.py          Lambda handler (Powertools Batch Processor)
      local_runner.py     Local dev poller
    dispatcher/           Notification Dispatcher (SQS consumer)
      handler.py          Lambda handler
      local_runner.py     Local dev poller
  models/                 SQLAlchemy models
    user.py               User (JWT auth)
    alert_rule.py         Single-metric alert rules
    rule_group.py         Composite rules (RuleGroup + RuleCondition)
    latest_reading.py     Latest weather value per H3 cell + metric
    metric_type.py        Admin-configurable metric types
    weather_data.py       Black-box pipeline table (read-only)
  providers/              Notification providers
    base.py               Abstract NotificationProvider interface
    kapso.py              Kapso HTTP provider (production)
    mock.py               Mock provider (local dev, logs instead of sending)
  shared/                 Shared utilities
    config.py             Pydantic Settings (env vars)
    constants.py          H3_RESOLUTION, ALERT_COOLDOWN_MINUTES
    db.py                 Dual engine setup (primary + replica)
    threshold.py          Threshold comparison logic
simulator/
  ingest.py               Weather simulator for local dev (writes to DB + Kinesis)
  db_only.py              DB-only simulator for cloud (writes to RDS, DMS picks up via CDC)
infra/
  stacks/
    network_stack.py      VPC (rarely changes)
    data_stack.py         RDS, RDS Proxy, Kinesis, SQS
    app_stack.py          Lambdas, ECS Fargate, ALB (deploys fast)
tests/
  unit/                   Threshold logic, H3, auth, schemas, parser, providers
  integration/            API CRUD, IDOR prevention, health/status
scripts/
  entrypoint.sh           Docker entrypoint (migrations + seed)
  seed.py                 Database seed data
  localstack-init.sh      LocalStack resource creation
  simulate-cloud.sh       Run simulator as ECS task against cloud RDS
  test-cloud.sh           Integration tests against deployed AWS stack
```

## Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Matching strategy | Fetch-and-filter in Lambda | Simpler SQL, flexible operators, threshold logic in Python |
| H3 resolution | 7 (~5.16 km2 per cell) | Balances precision and index cardinality |
| H3 adjacency | Exact cell match | Simpler. Users create rules per cell. |
| Alert cooldown | 15 min via `last_notified_at` in DB | DB-only for v1, Redis upgrade path exists |
| Auth | JWT issued by FastAPI | Self-contained, signing secret in Secrets Manager |
| Composite rules | RuleGroup + RuleCondition + latest_readings | Metric-agnostic, supports any AND/OR combination |
| Notification provider | Pluggable interface | KapsoProvider in prod, MockProvider in dev |
| Batch failures | Powertools Batch Processor | Handles partial Kinesis batch failures automatically |
| DB read/write split | Dual RDS Proxy (primary + replica) | Matching Engine reads replica, Dispatcher writes primary |

## Makefile Commands

```
make help               Show all commands
make up                 Start all services
make down               Stop all services
make nuke               Wipe everything and start fresh
make build              Rebuild all images
make watch              Tail matching-engine + dispatcher logs
make logs               Tail all logs
make logs-api           Tail API logs
make simulate-normal    Run NORMAL scenario (30s)
make simulate-heat      Run HEAT_WAVE scenario (10s)
make simulate-cold      Run COLD_SNAP scenario (10s)
make simulate-storm     Run SEVERE_STORM scenario (100 events)
make seed               Re-run seed script
make db-shell           Open psql shell
make shell              Open bash in API container
make dashboard          Open dashboard in browser
make docs               Open API docs in browser
make test               Run all tests
make test-unit          Run unit tests
make test-integration   Run integration tests
make sqs-depth          Check SQS queue message counts
make kinesis-shards     Show Kinesis stream info
make clean              Remove everything including volumes

# AWS Deploy
make deploy             Deploy all 3 stacks (Network → Data → App)
make deploy-app         Redeploy only App stack (~3 min)
make deploy-destroy     Destroy all AWS infrastructure
make deploy-status      Check all stack statuses
make deploy-test        Run integration tests against cloud
make deploy-simulate    Run simulator as ECS task (SCENARIO=HEAT_WAVE DURATION=10)
make deploy-url         Print the deployed API URL
```

## Testing

```bash
# Install dev dependencies locally
pip install -e ".[dev]"

# All tests
make test

# Unit tests only (fast, no DB needed)
make test-unit

# Integration tests (needs running postgres)
make test-integration
```

## AWS Deployment

Infrastructure is split into 3 CDK stacks for independent updates:

| Stack | What | Deploy time |
|-------|------|-------------|
| AgrobotNetworkStack | VPC | ~2 min (rarely changes) |
| AgrobotDataStack | RDS, RDS Proxy, Kinesis, SQS | ~12 min |
| AgrobotAppStack | Lambdas, ECS Fargate, ALB | ~3 min |

```bash
# First time: deploy everything
make deploy

# App-only changes (Dockerfile, code): fast redeploy
make deploy-app

# Simulate weather events against cloud RDS
make deploy-simulate SCENARIO=HEAT_WAVE DURATION=10
make deploy-simulate SCENARIO=SEVERE_STORM EVENTS=100

# Run integration tests against cloud
make deploy-test

# IMPORTANT: tear down when done (~$240/month if left running)
make deploy-destroy
```

### DMS Setup (Manual, not in CDK)

DMS bridges RDS → Kinesis via CDC. It's not included in CDK because DMS resources are notoriously fragile to automate. Setup requires:

1. Create a DMS replication instance (dms.t3.medium, ~$50/month)
2. Create a source endpoint pointing to the RDS PostgreSQL instance
3. Create a target endpoint pointing to the `weather-events` Kinesis stream
4. Create an IAM role allowing DMS to write to Kinesis
5. Create a CDC replication task filtering on `public.weather_data`
6. Start the task and verify events flow to the Matching Engine Lambda

The RDS parameter group already has `rds.logical_replication = 1` enabled (set by CDK). See `docs/designs/weather-notifications.md` for details.

**Without DMS:** Use the local Docker Compose setup where the simulator pushes directly to LocalStack Kinesis for full pipeline testing.

**RDS credentials** are managed automatically via AWS Secrets Manager (created by CDK). The ECS tasks and Lambdas read credentials at deploy time.

**Required env vars in production (beyond CDK-managed):**
- `AGROBOT_JWT_SECRET_KEY` - Override the default in Secrets Manager
- `AGROBOT_KAPSO_API_URL` - Real Kapso endpoint
- `AGROBOT_KAPSO_API_KEY` - Kapso API key

## Tech Stack

- **Python 3.11** - FastAPI, SQLAlchemy Async, Pydantic v2
- **PostgreSQL 16** - PostGIS, H3 spatial indexing
- **AWS** - Lambda, Kinesis, SQS, RDS, ECS Fargate, API Gateway, CDK
- **aws-lambda-powertools** - Structured logging, metrics (EMF), batch processing
- **Docker Compose + LocalStack** - Full local development environment
