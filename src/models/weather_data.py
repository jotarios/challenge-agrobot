"""WeatherData model (read-only, populated by black-box pipeline).

This table is owned by the ingestion pipeline and MUST NOT be modified.
The schema here reflects the assumed contract from the PRD spike.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class WeatherData(Base):
    __tablename__ = "weather_data"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    location_lat: Mapped[float] = mapped_column(Float, nullable=False)
    location_lon: Mapped[float] = mapped_column(Float, nullable=False)
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
