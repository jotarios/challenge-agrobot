"""Application configuration loaded from environment variables."""

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agrobot"
    replica_database_url: str | None = None

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # AWS
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None  # LocalStack override
    kinesis_stream_name: str = "weather-events"
    sqs_queue_url: str = ""
    sqs_dlq_url: str = ""

    # Kapso
    kapso_api_url: str = ""
    kapso_api_key: str = ""

    # Rate limiting
    rate_limit_per_minute: int = 60

    # Environment
    environment: str = "development"

    model_config = {"env_prefix": "AGROBOT_"}

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.environment == "production" and self.jwt_secret_key == "dev-secret-change-in-production":
            raise ValueError(
                "AGROBOT_JWT_SECRET_KEY must be set to a secure value in production. "
                "Do not use the default dev secret."
            )
        return self


settings = Settings()
