from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Holds either a random code or a user-chosen alias; both share one namespace.
    code: Mapped[str] = mapped_column(String(32), unique=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    is_custom: Mapped[bool] = mapped_column(Boolean, server_default=false())
    is_disabled: Mapped[bool] = mapped_column(Boolean, server_default=false())
    # SHA-256 of the management token; NULL for links created before tokens existed.
    token_hash: Mapped[str | None] = mapped_column(String(64))
    clicks: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Optional limits; NULL means "no limit". Indexed for the cleanup job's lookup.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    max_clicks: Mapped[int | None] = mapped_column(Integer)


# Analytics: a running total per day, not one row per click, so the table stays small
# however popular a link gets. Rows disappear with their link (ON DELETE CASCADE).


class DailyClicks(Base):
    """Clicks per link per UTC day."""

    __tablename__ = "daily_clicks"

    link_id: Mapped[int] = mapped_column(ForeignKey("links.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    clicks: Mapped[int] = mapped_column(Integer)
