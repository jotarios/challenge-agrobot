"""Composite rule models: RuleGroup and RuleCondition.

A RuleGroup combines multiple metric conditions with AND/OR logic.
Example: "temperature > 30 AND wind_speed < 10 in Buenos Aires"

  RuleGroup (user_id, h3_index, logic="and")
    ├── RuleCondition (metric_type="temperature", operator="gt", threshold=30)
    └── RuleCondition (metric_type="wind_speed", operator="lt", threshold=10)
"""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Logic(str, enum.Enum):
    AND = "and"
    OR = "or"


class RuleGroup(Base):
    __tablename__ = "rule_groups"
    __table_args__ = (
        Index("ix_rule_groups_h3", "location_h3_index"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_h3_index: Mapped[str] = mapped_column(String(20), nullable=False)
    logic: Mapped[str] = mapped_column(String(5), nullable=False, default="and")
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    conditions: Mapped[list["RuleCondition"]] = relationship(
        back_populates="rule_group", cascade="all, delete-orphan", lazy="selectin"
    )
    user = relationship("User")


class RuleCondition(Base):
    __tablename__ = "rule_conditions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rule_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    operator: Mapped[str] = mapped_column(String(10), nullable=False)
    threshold_value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

    rule_group: Mapped["RuleGroup"] = relationship(back_populates="conditions")
