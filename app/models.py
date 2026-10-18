from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)  # random code or custom alias
    target_url: Mapped[str] = mapped_column(String(2048))
    is_custom: Mapped[bool] = mapped_column(Boolean, server_default=false())
    is_disabled: Mapped[bool] = mapped_column(Boolean, server_default=false())
    token_hash: Mapped[str | None] = mapped_column(String(64))  # sha256 of the manage token
    clicks: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # indexed for the cleanup job
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    max_clicks: Mapped[int | None] = mapped_column(Integer)


# one row per link per day instead of one row per click
class DailyClicks(Base):
    __tablename__ = "daily_clicks"

    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    clicks: Mapped[int] = mapped_column(Integer)
