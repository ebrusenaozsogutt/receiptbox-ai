from datetime import date

from sqlalchemy import CheckConstraint, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AiDailyRequests(Base):
    """D-016 (free tier only): real Gemini requests per Google quota day and model. Not user data
    (no user id, no content): only a counter, see app/ai/usage.py."""

    __tablename__ = "ai_daily_requests"
    __table_args__ = (CheckConstraint("count >= 0", name="count_nonneg"),)

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    model: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
