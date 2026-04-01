"""LatestReading model: most recent weather value per H3 cell + metric.

Upserted by the Matching Engine on every weather event. Used to evaluate
composite rules that span multiple metric types.

One row per (h3_index, metric_type). Updated via INSERT ON CONFLICT UPDATE.
"""

from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class LatestReading(Base):
    __tablename__ = "latest_readings"

    h3_index: Mapped[str] = mapped_column(String(20), primary_key=True)
    metric_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
