from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import HttpUrl
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import cache, events, metrics, pages, qr, tracing
from .db import get_session
from .models import DailyClicks, Link
from .ratelimit import create_limit, manage_limit, qr_limit
from .safety import unsafe_reason
from .schemas import DayCount, LinkCreated, LinkIn, LinkOut, LinkStats, LinkUpdate
from .shortcode import generate_code
from .tokens import hash_token, new_token, token_matches

STATIC_DIR = Path(__file__).parent / "static"
MAX_CODE_ATTEMPTS = 5

app = FastAPI(title="shrinkr")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.middleware("http")(metrics.record)
tracing.setup(app)

bearer = HTTPBearer(auto_error=False, description="The manage_token returned when the link was created")

# Evaluated by the database, so every app instance uses the same clock.
IS_ACTIVE = and_(
    Link.is_disabled.is_(False),
    or_(Link.expires_at.is_(None), Link.expires_at > func.now()),
    or_(Link.max_clicks.is_(None), Link.clicks < Link.max_clicks),
)


def short_url_for(code: str, request: Request) -> str:
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
    """Insert the link; False if the code is already taken."""
    session.add(link)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return False
    session.refresh(link)
    return True


def ensure_safe_target(url: HttpUrl, request: Request) -> None:
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


# Used for both probes. It doesn't check Postgres or Redis: they're shared by every pod,
# so failing on them would take all pods out of service at once.
@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


# Scraped by Prometheus
@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
        "token_hash": hash_token(token),
    }

    if payload.alias:
        link = Link(code=payload.alias, is_custom=True, **fields)
        if not save(session, link):
            raise HTTPException(status_code=409, detail=f"Alias '{payload.alias}' is already taken")
    else:
        # random codes can collide, so retry a few times
        for _ in range(MAX_CODE_ATTEMPTS):
            link = Link(code=generate_code(), **fields)
            if save(session, link):
                break
        else:
            raise HTTPException(status_code=503, detail="Could not allocate a short code, try again")

    return LinkCreated(**to_out(link, request).model_dump(), manage_token=token)


# the rate limit runs before owned_link, so wrong tokens count against it too
@app.get("/api/links/{code}", response_model=LinkOut, dependencies=[Depends(manage_limit)])
def get_link(request: Request, link: Link = Depends(owned_link)):
    return to_out(link, request)


@app.get("/api/links/{code}/stats", response_model=LinkStats, dependencies=[Depends(manage_limit)])
def get_link_stats(
    link: Link = Depends(owned_link),
    session: Session = Depends(get_session),
    days: int = Query(default=30, ge=1, le=365),
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
    daily = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        daily.append(DayCount(day=day, clicks=stored.get(day, 0)))
    return LinkStats(code=link.code, total_clicks=link.clicks, daily=daily)


@app.get(
    "/api/links/{code}/qr",
    dependencies=[Depends(qr_limit)],
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}, "image/png": {}}}},
)
def get_qr_code(
    code: str,
    request: Request,
    session: Session = Depends(get_session),
    image_format: Literal["svg", "png"] = Query(default="svg", alias="format"),
    scale: int = Query(default=10, ge=1, le=40),
    download: bool = False,
):
    if session.scalar(select(Link.id).where(Link.code == code)) is None:
        raise HTTPException(status_code=404, detail="Short link not found")

    # The short URL, not the target, so printed codes survive edits to the target.
    image, media_type = qr.render(short_url_for(code, request), image_format, scale)
    headers = {"Cache-Control": "public, max-age=86400"}
    if download:
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
    # only the fields the client sent
    for field, value in changes.model_dump(exclude_unset=True).items():
        if field == "url":
            field, value = "target_url", str(value)
        setattr(link, field, value)
    session.commit()
    cache.invalidate(link.code)  # after the commit, so the next read sees the change
    return to_out(link, request)


@app.delete("/api/links/{code}", status_code=204, dependencies=[Depends(manage_limit)])
def delete_link(link: Link = Depends(owned_link), session: Session = Depends(get_session)):
    session.delete(link)
    session.commit()
    cache.invalidate(link.code)


# reason: (status, API detail, page title, page text)
UNAVAILABLE = {
    "missing": (404, "Short link not found", "Link not found",
                "This short link doesn't exist. Check it for typos; it may also have been deleted."),
    "disabled": (410, "This short link has been disabled", "Link disabled",
                 "The owner of this short link has switched it off."),
    "expired": (410, "This short link has expired", "Link expired",
                "This short link has expired and no longer leads anywhere."),
}


def link_unavailable(request: Request, reason: str):
    status_code, detail, title, message = UNAVAILABLE[reason]
    if pages.wants_html(request.headers.get("accept")):
        return pages.error_page(status_code, title, message)
    raise HTTPException(status_code=status_code, detail=detail)


def redirect(target_url: str) -> RedirectResponse:
    # 302 and no-store so every click reaches the server and gets counted.
    return RedirectResponse(target_url, status_code=302, headers={"Cache-Control": "no-store"})


@app.get("/{code}", include_in_schema=False)
def follow_link(code: str, request: Request, session: Session = Depends(get_session)):
    # fast path: cached target and a queued click, no database
    target = cache.get_target(code)
    if target is not None and events.record_click(code):
        return redirect(target)

    row = session.execute(
        select(Link, IS_ACTIVE.label("is_active")).where(Link.code == code)
    ).first()
    if row is None:
        return link_unavailable(request, "missing")
    link, is_active = row
    if not is_active:
        return link_unavailable(request, "disabled" if link.is_disabled else "expired")

    if link.max_clicks is None:
        cache.store(code, link.target_url, link.expires_at)
        if events.record_click(code):
            return redirect(link.target_url)

    # Click-limited links (or Redis down): check and count in one statement so concurrent
    # clicks can't go over max_clicks.
    target = session.scalar(
        update(Link)
        .where(Link.code == code, IS_ACTIVE)
        .values(clicks=Link.clicks + 1)
        .returning(Link.target_url)
    )
    if target is None:
        return link_unavailable(request, "expired")
    session.commit()
    events.record_click(code, counted=True)
    return redirect(target)
