"""Add metric_types table with default seed data.

Revision ID: 003
Revises: 002
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_METRICS = ["temperature", "humidity", "wind_speed", "pressure", "precipitation"]


def upgrade() -> None:
    op.create_table(
        "metric_types",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metric_types_name", "metric_types", ["name"], unique=True)

    # Seed default metrics
    metric_types = sa.table("metric_types", sa.column("name", sa.String))
    op.bulk_insert(metric_types, [{"name": m} for m in DEFAULT_METRICS])


def downgrade() -> None:
    op.drop_table("metric_types")
