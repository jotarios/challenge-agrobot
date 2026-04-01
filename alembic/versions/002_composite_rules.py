"""Add composite rules: rule_groups, rule_conditions, latest_readings.

Revision ID: 002
Revises: 001
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rule groups
    op.create_table(
        "rule_groups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("location_h3_index", sa.String(20), nullable=False),
        sa.Column("logic", sa.String(5), nullable=False, server_default="and"),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rule_groups_user_id", "rule_groups", ["user_id"])
    op.create_index("ix_rule_groups_h3", "rule_groups", ["location_h3_index"])

    # Rule conditions
    op.create_table(
        "rule_conditions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_group_id", sa.BigInteger(), nullable=False),
        sa.Column("metric_type", sa.String(50), nullable=False),
        sa.Column("operator", sa.String(10), nullable=False),
        sa.Column("threshold_value", sa.Numeric(10, 4), nullable=False),
        sa.ForeignKeyConstraint(
            ["rule_group_id"], ["rule_groups.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rule_conditions_group_id", "rule_conditions", ["rule_group_id"])

    # Latest readings (composite PK)
    op.create_table(
        "latest_readings",
        sa.Column("h3_index", sa.String(20), nullable=False),
        sa.Column("metric_type", sa.String(50), nullable=False),
        sa.Column("value", sa.Numeric(10, 4), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("h3_index", "metric_type"),
    )


def downgrade() -> None:
    op.drop_table("latest_readings")
    op.drop_table("rule_conditions")
    op.drop_table("rule_groups")
