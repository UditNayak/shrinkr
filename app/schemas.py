"""Shapes of API requests and responses, with their validation rules."""

import re
from datetime import UTC, date, datetime

from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, field_validator
from pydantic_core import PydanticCustomError

MAX_URL_LENGTH = 2048
MAX_CLICKS_LIMIT = 1_000_000_000

# 3-32 characters: letters, digits, "-" and "_", starting with a letter or digit.
ALIAS_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,31}")
# Paths the app uses now or will use; an alias with these names would hide a real page.
RESERVED_ALIASES = {
    "admin", "api", "assets", "docs", "health", "healthz", "livez", "login",
    "metrics", "qr", "readyz", "redoc", "static", "stats", "version",
}


# PydanticCustomError is used throughout: its message reaches the user as-is (a 422 response).


class LinkSettings(BaseModel):
    """Fields and checks shared by creating and updating a link."""

    # AwareDatetime: must include a timezone (e.g. "2026-12-31T23:59:00Z"), so it's unambiguous.
    expires_at: AwareDatetime | None = None
    max_clicks: int | None = Field(default=None, ge=1, le=MAX_CLICKS_LIMIT)

    @field_validator("url", check_fields=False)
    @classmethod
    def check_url_length(cls, url: HttpUrl | None) -> HttpUrl | None:
        if url is not None and len(str(url)) > MAX_URL_LENGTH:
            raise PydanticCustomError("url_too_long", "URL is too long")
        return url

    @field_validator("expires_at")
    @classmethod
    def check_expires_at(cls, expires_at: datetime | None) -> datetime | None:
        if expires_at is None:
            return None
        expires_at = expires_at.astimezone(UTC)  # store everything in UTC
        if expires_at <= datetime.now(UTC):
            raise PydanticCustomError("expires_in_past", "Expiry time must be in the future")
        return expires_at


class LinkIn(LinkSettings):
    """Body of POST /api/links."""

    url: HttpUrl
    alias: str | None = None

    @field_validator("alias")
    @classmethod
    def check_alias(cls, alias: str | None) -> str | None:
        if alias is None:
            return None
        if not ALIAS_PATTERN.fullmatch(alias):
            raise PydanticCustomError(
                "alias_format",
                "Alias must be 3-32 characters: letters, digits, '-' or '_', "
                "starting with a letter or digit",
            )
        if alias.lower() in RESERVED_ALIASES:
            raise PydanticCustomError(
                "alias_reserved", "'{alias}' is reserved and cannot be used as an alias", {"alias": alias}
            )
        return alias


class LinkUpdate(LinkSettings):
    """Body of PATCH /api/links/{code}. Only the fields sent are changed.

    expires_at / max_clicks may be sent as null to remove that limit.
    """

    url: HttpUrl | None = None
    is_disabled: bool | None = None

    @field_validator("url", "is_disabled")
    @classmethod
    def not_null(cls, value):
        # Validators only run on fields that were actually sent, so None here means
        # the client explicitly sent null, which these fields don't allow.
        if value is None:
            raise PydanticCustomError("not_null", "This field cannot be null")
        return value


class LinkOut(BaseModel):
    code: str
    short_url: str
    target_url: str
    is_custom: bool
    is_disabled: bool
    clicks: int
    created_at: datetime
    expires_at: datetime | None
    max_clicks: int | None


class LinkCreated(LinkOut):
    """Response to creating a link: the only time the management token is ever shown."""

    manage_token: str


class DayCount(BaseModel):
    day: date  # a UTC day
    clicks: int


class LinkStats(BaseModel):
    """Response of GET /api/links/{code}/stats."""

    code: str
    total_clicks: int
    daily: list[DayCount]  # oldest first, one entry per day, zero-filled
