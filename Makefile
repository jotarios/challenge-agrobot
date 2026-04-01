# Typical workflow:

  # make nuke              # fresh start
  # make watch             # terminal 1: watch the pipeline
  # make simulate-normal   # terminal 2: send events
  # make sqs-depth         # check how many alerts queued
  # make dashboard         # open browser dashboard

.PHONY: help up down restart build logs watch simulate-normal simulate-heat simulate-cold simulate-storm seed shell db-shell test lint clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker Compose ───────────────────────────────────────────

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

restart: ## Restart all services
	docker compose restart

build: ## Rebuild all images (no cache)
	docker compose build --no-cache

nuke: ## Stop everything, wipe DB volume, rebuild and start fresh
	docker compose down -v
	docker compose build --no-cache
	docker compose up -d

# ── Logs ─────────────────────────────────────────────────────

logs: ## Tail all service logs
	docker compose logs -f

watch: ## Tail matching-engine and dispatcher logs
	docker compose logs -f matching-engine dispatcher

logs-api: ## Tail API logs
	docker compose logs -f api

# ── Simulator ────────────────────────────────────────────────

DSN := postgresql://postgres:postgres@postgres:5432/agrobot
KINESIS := http://localstack:4566

simulate-normal: ## Run NORMAL scenario (30s, all cities)
	docker compose run --rm simulator python -m simulator.ingest \
		--scenario NORMAL --duration 30 --dsn $(DSN) --kinesis-endpoint $(KINESIS)

simulate-heat: ## Run HEAT_WAVE scenario (10s, Buenos Aires)
	docker compose run --rm simulator python -m simulator.ingest \
		--scenario HEAT_WAVE --duration 10 --dsn $(DSN) --kinesis-endpoint $(KINESIS)

simulate-cold: ## Run COLD_SNAP scenario (10s, Sao Paulo)
	docker compose run --rm simulator python -m simulator.ingest \
		--scenario COLD_SNAP --duration 10 --dsn $(DSN) --kinesis-endpoint $(KINESIS)

simulate-storm: ## Run SEVERE_STORM scenario (100 events burst)
	docker compose run --rm simulator python -m simulator.ingest \
		--scenario SEVERE_STORM --events 100 --dsn $(DSN) --kinesis-endpoint $(KINESIS)

# ── Database ─────────────────────────────────────────────────

seed: ## Re-run seed script
	docker compose exec api python scripts/seed.py

db-shell: ## Open psql shell
	docker compose exec postgres psql -U postgres -d agrobot

# ── Dev tools ────────────────────────────────────────────────

shell: ## Open a bash shell in the API container
	docker compose exec api bash

dashboard: ## Open the dashboard in your browser
	open http://localhost:8000/dashboard

docs: ## Open the API docs in your browser
	open http://localhost:8000/docs

# ── Testing ──────────────────────────────────────────────────

test: ## Run all tests
	pip install -e ".[dev]" -q && pytest -v

test-unit: ## Run unit tests only
	pip install -e ".[dev]" -q && pytest tests/unit -v

test-integration: ## Run integration tests only
	pip install -e ".[dev]" -q && pytest tests/integration -v

# ── AWS / LocalStack ────────────────────────────────────────

sqs-depth: ## Check SQS queue message counts
	@docker compose exec localstack aws --endpoint-url=http://localhost:4566 --region us-east-1 --no-sign-request \
		sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/agrobot-alerts \
		--attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --output table
	@docker compose exec localstack aws --endpoint-url=http://localhost:4566 --region us-east-1 --no-sign-request \
		sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/agrobot-alerts-dlq \
		--attribute-names ApproximateNumberOfMessages --output table

kinesis-shards: ## List Kinesis stream shards
	@docker compose exec localstack aws --endpoint-url=http://localhost:4566 --region us-east-1 --no-sign-request \
		kinesis describe-stream --stream-name weather-events --query 'StreamDescription.{Status:StreamStatus,Shards:length(Shards)}' --output table

# ── Cleanup ──────────────────────────────────────────────────

clean: ## Remove all containers, volumes, and build cache
	docker compose down -v --rmi local --remove-orphans
