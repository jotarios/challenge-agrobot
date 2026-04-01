"""Database engine and session management.

Supports dual engines for read/write split:
- Primary engine: writes (cooldown updates, API CRUD)
- Replica engine: reads (matching queries, claim check validation)

Architecture:
  ┌─────────────┐     ┌──────────────────┐
  │ FastAPI API  │────▶│ Primary (RDS)    │  writes + reads
  └─────────────┘     └──────────────────┘
  ┌─────────────┐     ┌──────────────────┐
  │ Matching    │────▶│ Replica (RDS RR) │  reads only
  │ Engine      │     └──────────────────┘
  └─────────────┘
  ┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
  │ Dispatcher  │────▶│ Replica (reads)  │     │ Primary (writes) │
  │             │────▶│                  │     │                  │
  └─────────────┘     └──────────────────┘     └──────────────────┘
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.shared.config import settings

_primary_engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=settings.environment == "development",
)

_replica_engine = None
if settings.replica_database_url:
    _replica_engine = create_async_engine(
        settings.replica_database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=settings.environment == "development",
    )

PrimarySessionLocal = async_sessionmaker(
    bind=_primary_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

ReplicaSessionLocal = async_sessionmaker(
    bind=_replica_engine or _primary_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_primary_session():
    """Dependency for FastAPI routes and write operations."""
    async with PrimarySessionLocal() as session:
        yield session


async def get_replica_session():
    """Dependency for read-only operations (matching, claim check)."""
    async with ReplicaSessionLocal() as session:
        yield session
