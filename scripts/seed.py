"""Seed the database with test data for local development.

Creates:
- Admin user (admin@agrobot.com / admin123)
- Regular user (user@agrobot.com / password123)
- Default metric types
- Sample alert rules across all 5 cities (thresholds aligned with simulator ranges)
- 2 composite rule groups (AND + OR logic)
"""

import asyncio
import os

import h3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.deps import hash_password
from src.models.alert_rule import AlertRule
from src.models.metric_type import MetricType
from src.models.rule_group import RuleCondition, RuleGroup
from src.models.user import User
from src.shared.constants import H3_RESOLUTION

DATABASE_URL = os.environ.get(
    "AGROBOT_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/agrobot",
)

DEFAULT_METRICS = ["temperature", "humidity", "wind_speed", "pressure", "precipitation"]

# Thresholds aligned with simulator ranges:
#   NORMAL:  temp 15-35, humidity 30-80, wind 5-40, pressure 1000-1025, precip 0-20
#   HEAT_WAVE: temp 38-45, humidity 5-19 (Buenos Aires)
#   COLD_SNAP: temp -15 to -5.5, wind 61-120 (Sao Paulo)
SAMPLE_RULES = [
    # Buenos Aires — will match NORMAL (temp often > 25) and HEAT_WAVE
    {"lat": -34.6037, "lon": -58.3816, "metric": "temperature", "op": "gt", "threshold": 25.0},
    {"lat": -34.6037, "lon": -58.3816, "metric": "humidity", "op": "gt", "threshold": 60.0},
    {"lat": -34.6037, "lon": -58.3816, "metric": "wind_speed", "op": "gte", "threshold": 20.0},
    # Sao Paulo — will match NORMAL and COLD_SNAP
    {"lat": -23.5505, "lon": -46.6333, "metric": "temperature", "op": "gt", "threshold": 28.0},
    {"lat": -23.5505, "lon": -46.6333, "metric": "precipitation", "op": "gt", "threshold": 10.0},
    # Mexico City — will match NORMAL
    {"lat": 19.4326, "lon": -99.1332, "metric": "temperature", "op": "gt", "threshold": 22.0},
    # Bogota — will match NORMAL (humidity often < 50)
    {"lat": 4.7110, "lon": -74.0721, "metric": "humidity", "op": "lt", "threshold": 50.0},
    # Lima — will match NORMAL (wind often > 15)
    {"lat": -12.0464, "lon": -77.0428, "metric": "wind_speed", "op": "gt", "threshold": 15.0},
]


async def seed():
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # Check if already seeded
        existing = await db.execute(select(User).where(User.email == "admin@agrobot.com"))
        if existing.scalar_one_or_none():
            print("Database already seeded, skipping.")
            await engine.dispose()
            return

        # Metric types
        for name in DEFAULT_METRICS:
            existing_mt = await db.execute(select(MetricType).where(MetricType.name == name))
            if not existing_mt.scalar_one_or_none():
                db.add(MetricType(name=name))
        await db.flush()
        print(f"  Metric types: {', '.join(DEFAULT_METRICS)}")

        # Users
        admin = User(email="admin@agrobot.com", password_hash=hash_password("admin123"), is_admin=True)
        user = User(email="user@agrobot.com", password_hash=hash_password("password123"), is_admin=False)
        db.add_all([admin, user])
        await db.flush()
        print(f"  Admin: admin@agrobot.com / admin123")
        print(f"  User:  user@agrobot.com / password123")

        # Alert rules
        for r in SAMPLE_RULES:
            h3_index = h3.latlng_to_cell(r["lat"], r["lon"], H3_RESOLUTION)
            db.add(AlertRule(
                user_id=user.id,
                location_h3_index=h3_index,
                metric_type=r["metric"],
                operator=r["op"],
                threshold_value=r["threshold"],
            ))
        await db.flush()
        print(f"  Alert rules: {len(SAMPLE_RULES)} rules across 3 cities")

        # Composite rule: temp > 25 AND humidity > 50 in Buenos Aires
        # NORMAL sends temp 15-35 and humidity 30-80, so this fires when both are in upper range
        ba_h3 = h3.latlng_to_cell(-34.6037, -58.3816, H3_RESOLUTION)
        group1 = RuleGroup(
            user_id=user.id,
            location_h3_index=ba_h3,
            logic="and",
            conditions=[
                RuleCondition(metric_type="temperature", operator="gt", threshold_value=25.0),
                RuleCondition(metric_type="humidity", operator="gt", threshold_value=50.0),
            ],
        )
        db.add(group1)
        print(f"  Composite rule 1: temperature > 25 AND humidity > 50 (Buenos Aires)")

        # Composite rule: temp > 38 OR wind > 60 in Sao Paulo
        # Matches HEAT_WAVE (temp) or COLD_SNAP (wind)
        sp_h3 = h3.latlng_to_cell(-23.5505, -46.6333, H3_RESOLUTION)
        group2 = RuleGroup(
            user_id=user.id,
            location_h3_index=sp_h3,
            logic="or",
            conditions=[
                RuleCondition(metric_type="temperature", operator="gt", threshold_value=38.0),
                RuleCondition(metric_type="wind_speed", operator="gt", threshold_value=60.0),
            ],
        )
        db.add(group2)
        print(f"  Composite rule 2: temperature > 38 OR wind_speed > 60 (Sao Paulo)")

        await db.commit()

    await engine.dispose()
    print("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
