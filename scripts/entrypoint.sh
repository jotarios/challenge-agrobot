#!/bin/bash
# Run migrations, seed data, then start the app
set -e
export PYTHONPATH=/app

echo "Running database migrations..."
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from src.models.base import Base
import src.models
import os

async def migrate():
    engine = create_async_engine(os.environ['AGROBOT_DATABASE_URL'])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(migrate())
"
echo "Migrations complete."

echo "Seeding database..."
python scripts/seed.py
echo "Seed complete."

exec "$@"
