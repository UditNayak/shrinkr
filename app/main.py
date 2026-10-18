from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import HttpUrl
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import cache, events, pages, qr
from .db import get_session
from .models import DailyClicks, Link
from .ratelimit import create_limit, manage_limit, qr_limit
from .safety import unsafe_reason
from .schemas import DayCount, LinkCreated, LinkIn, LinkOut, LinkStats, LinkUpdate
from .shortcode import generate_code
from .tokens import hash_token, new_token, token_matches

STATIC_DIR = Path(__file__).parent / "static"
MAX_CODE_ATTEMPTS = 5

# The schema is managed by Alembic migrations (alembic upgrade head), not by the app.
app = FastAPI(title="shrinkr")
# The web UI's CSS and JavaScript ("static" is a reserved alias, so no link can hide this).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Reads "Authorization: Bearer <token>". auto_error=False so we can answer 401 ourselves.
bearer = HTTPBearer(auto_error=False, description="The manage_token returned when the link was created")

# A link can be followed if it is enabled, has not expired and has clicks left. Evaluated by
# the database, with the database's clock, so every app instance agrees.
IS_ACTIVE = and_(
    Link.is_disabled.is_(False),
    or_(Link.expires_at.is_(None), Link.expires_at > func.now()),
    or_(Link.max_clicks.is_(None), Link.clicks < Link.max_clicks),
)


def short_url_for(code: str, request: Request) -> str:
    # Built from the address the request came in on (e.g. http://localhost:8000).
    return f"{str(request.base_url).rstrip('/')}/{code}"


def to_out(link: Link, request: Request) -> LinkOut:
    return LinkOut(
        code=link.code,
        short_url=short_url_for(link.code, request),
        target_url=link.target_url,
        is_custom=link.is_custom,
        is_disabled=link.is_disabled,
        clicks=link.clicks,
        created_at=link.created_at,
        expires_at=link.expires_at,
        max_clicks=link.max_clicks,
    )


def save(session: Session, link: Link) -> bool:
    """Insert the link. Returns False if its code is already taken (unique constraint)."""
    session.add(link)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return False
    session.refresh(link)
    return True


def ensure_safe_target(url: HttpUrl, request: Request) -> None:
    """Reject unsafe targets with the same 422 shape as any other validation error."""
    reason = unsafe_reason(url, own_host=request.url.hostname)
    if reason:
        raise RequestValidationError(
            [{"type": "unsafe_url", "loc": ("body", "url"), "msg": reason, "input": str(url)}]
        )


def owned_link(
    code: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> Link:
    """Dependency: the link with this code, if the request carries its management token."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing management token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    link = session.scalar(select(Link).where(Link.code == code))
    if link is None:
        raise HTTPException(status_code=404, detail="Short link not found")
    if link.token_hash is None or not token_matches(credentials.credentials, link.token_hash):
        raise HTTPException(status_code=403, detail="Invalid management token for this link")
    return link


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html", headers=pages.PAGE_HEADERS)


@app.post("/api/links", status_code=201, response_model=LinkCreated, dependencies=[Depends(create_limit)])
def create_link(payload: LinkIn, request: Request, session: Session = Depends(get_session)):
    ensure_safe_target(payload.url, request)
    token = new_token()
    fields = {
        "target_url": str(payload.url),
        "expires_at": payload.expires_at,
        "max_clicks": payload.max_clicks,
        "token_hash": hash_token(token),  # only the hash is stored
    }

    if payload.alias:
        link = Link(code=payload.alias, is_custom=True, **fields)
        if not save(session, link):
            raise HTTPException(status_code=409, detail=f"Alias '{payload.alias}' is already taken")
    else:
        # Codes are random, so a collision is possible (if unlikely): retry with a new code.
        for _ in range(MAX_CODE_ATTEMPTS):
            link = Link(code=generate_code(), **fields)
            if save(session, link):
                break
        else:
            raise HTTPException(status_code=503, detail="Could not allocate a short code, try again")

    return LinkCreated(**to_out(link, request).model_dump(), manage_token=token)


# Rate limits are listed in `dependencies`, which run before owned_link checks the token,
# so failed token guesses are counted too.
@app.get("/api/links/{code}", response_model=LinkOut, dependencies=[Depends(manage_limit)])
def get_link(request: Request, link: Link = Depends(owned_link)):
    return to_out(link, request)


@app.get("/api/links/{code}/stats", response_model=LinkStats, dependencies=[Depends(manage_limit)])
def get_link_stats(
    link: Link = Depends(owned_link),
    session: Session = Depends(get_session),
    days: int = Query(default=30, ge=1, le=365, description="How many days of daily clicks"),
):
    today = datetime.now(UTC).date()
    first_day = today - timedelta(days=days - 1)
    stored = dict(
        session.execute(
            select(DailyClicks.day, DailyClicks.clicks).where(
                DailyClicks.link_id == link.id, DailyClicks.day >= first_day
            )
        ).all()
    )
    # Every day in the range, including days without clicks, so a chart has no gaps.
    daily = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        daily.append(DayCount(day=day, clicks=stored.get(day, 0)))
    return LinkStats(code=link.code, total_clicks=link.clicks, daily=daily)


@app.get(
    "/api/links/{code}/qr",
    dependencies=[Depends(qr_limit)],
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}, "image/png": {}}, "description": "QR code image"}},
)
def get_qr_code(
    code: str,
    request: Request,
    session: Session = Depends(get_session),
    # alias: the URL says ?format=, but "format" would hide Python's built-in in this function.
    image_format: Literal["svg", "png"] = Query(default="svg", alias="format"),
    scale: int = Query(default=10, ge=1, le=40, description="Pixels (png) or units (svg) per module"),
    download: bool = Query(default=False, description="Save as a file instead of showing it"),
):
    # Public: the short URL isn't secret. But only for existing links, so shrinkr can't be
    # used as a general-purpose QR generator.
    if session.scalar(select(Link.id).where(Link.code == code)) is None:
        raise HTTPException(status_code=404, detail="Short link not found")

    # Encode the SHORT url, not the target: printed codes keep working after the owner edits
    # the target, and their scans are counted.
    image, media_type = qr.render(short_url_for(code, request), image_format, scale)
    headers = {"Cache-Control": "public, max-age=86400"}  # a link's QR code never changes
    if download:
        # Safe to put in a header: codes only contain letters, digits, "-" and "_".
        headers["Content-Disposition"] = f'attachment; filename="shrinkr-{code}.{image_format}"'
    return Response(image, media_type=media_type, headers=headers)


@app.patch("/api/links/{code}", response_model=LinkOut, dependencies=[Depends(manage_limit)])
def update_link(
    changes: LinkUpdate,
    request: Request,
    link: Link = Depends(owned_link),
    session: Session = Depends(get_session),
):
    if changes.url is not None:
        ensure_safe_target(changes.url, request)
    # exclude_unset: only fields the client actually sent, so "not sent" != "sent as null".
    for field, value in changes.model_dump(exclude_unset=True).items():
        if field == "url":
            field, value = "target_url", str(value)
        setattr(link, field, value)
    session.commit()
    cache.invalidate(link.code)  # after the commit, so the next lookup reads the new values
    return to_out(link, request)


@app.delete("/api/links/{code}", status_code=204, dependencies=[Depends(manage_limit)])
def delete_link(link: Link = Depends(owned_link), session: Session = Depends(get_session)):
    session.delete(link)
    session.commit()
    cache.invalidate(link.code)


# Why a link can't be followed: (status, detail for API clients, title and text for browsers).
UNAVAILABLE = {
    "missing": (404, "Short link not found", "Link not found",
                "This short link doesn't exist. Check it for typos; it may also have been deleted."),
    "disabled": (410, "This short link has been disabled", "Link disabled",
                 "The owner of this short link has switched it off."),
    "expired": (410, "This short link has expired", "Link expired",
                "This short link has expired and no longer leads anywhere."),
}


def link_unavailable(request: Request, reason: str):
    """A friendly HTML page for browsers; the usual JSON error for everyone else."""
    status_code, detail, title, message = UNAVAILABLE[reason]
    if pages.wants_html(request.headers.get("accept")):
        return pages.error_page(status_code, title, message)
    raise HTTPException(status_code=status_code, detail=detail)


def redirect(target_url: str) -> RedirectResponse:
    # 302 (temporary), not 301: browsers cache 301s and would skip us, losing click counts.
    # no-store makes that explicit: every click reaches shrinkr, and edits apply at once.
    return RedirectResponse(target_url, status_code=302, headers={"Cache-Control": "no-store"})


@app.get("/{code}", include_in_schema=False)
def follow_link(code: str, request: Request, session: Session = Depends(get_session)):
    # 1. Fast path: target from the cache, click queued as an event. No database at all.
    target = cache.get_target(code)
    if target is not None and events.record_click(code):
        return redirect(target)

    # 2. Cache miss: one read from Postgres (IS_ACTIVE is evaluated with the database clock).
    row = session.execute(
        select(Link, IS_ACTIVE.label("is_active")).where(Link.code == code)
    ).first()
    if row is None:
        return link_unavailable(request, "missing")
    link, is_active = row
    if not is_active:
        return link_unavailable(request, "disabled" if link.is_disabled else "expired")

    if link.max_clicks is None:
        # No click limit: cache it for next time and queue the click.
        cache.store(code, link.target_url, link.expires_at)
        if events.record_click(code):
            return redirect(link.target_url)

    # 3. Exact path, for click-limited links (and whenever Redis is unavailable).
    # One statement checks the limits AND counts the click, so concurrent clicks can't
    # exceed max_clicks: the database locks the row, and each UPDATE re-checks the condition.
    target = session.scalar(
        update(Link)
        .where(Link.code == code, IS_ACTIVE)
        .values(clicks=Link.clicks + 1)
        .returning(Link.target_url)
    )
    if target is None:  # the last allowed click was just taken by someone else
        return link_unavailable(request, "expired")
    session.commit()
    # Already counted above; the event only adds it to the daily totals (best effort).
    events.record_click(code, counted=True)
    return redirect(target)
