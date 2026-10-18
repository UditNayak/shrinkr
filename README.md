# shrinkr

A small URL shortener: paste a long URL, get a short link. Following the short link redirects
to the original URL and counts the click.

Built with Python (FastAPI), PostgreSQL and Redis.

## Features

| Endpoint | Description |
|---|---|
| `GET /` | Web app: create links, see their stats and QR codes, edit, disable and delete them |
| `POST /api/links` | Create a short link (see body fields below). Returns a `manage_token` |
| `GET /api/links/{code}` | Link details and click count 🔑 |
| `GET /api/links/{code}/stats` | Clicks per day 🔑 |
| `GET /api/links/{code}/qr` | QR code image of the short link (SVG or PNG) |
| `PATCH /api/links/{code}` | Change the target URL, expiry or click limit, or disable/enable the link 🔑 |
| `DELETE /api/links/{code}` | Delete the link 🔑 |
| `GET /{code}` | Redirect (302) to the target URL and count the click; `410 Gone` if the link has expired or is disabled (browsers get a friendly page, API clients JSON) |

🔑 = requires the link's management token (see below).

Interactive API docs are served at `/docs`.

Request body for `POST /api/links`:

| Field | Required | Description |
|---|---|---|
| `url` | yes | The http(s) URL to shorten (max 2048 characters) |
| `alias` | no | Custom code: 3–32 characters (letters, digits, `-`, `_`), starting with a letter or digit. Case-sensitive. Names used by the app (such as `api`, `docs`, `metrics`) are reserved. |
| `expires_at` | no | When the link stops working. ISO 8601 with a timezone, e.g. `2026-12-31T23:59:00Z` |
| `max_clicks` | no | Number of redirects allowed before the link stops working (≥ 1) |

```bash
curl -X POST localhost:8000/api/links -H 'content-type: application/json' \
  -d '{"url": "https://example.com/", "alias": "my-link", "max_clicks": 5}'
```

A taken alias returns `409 Conflict`; invalid input returns `422`.

### Which URLs are accepted

To avoid shrinkr being used to reach private networks, hide destinations or create loops,
a target URL is rejected (`422`) if it:

- contains a username or password (`https://user:pass@host/`)
- is a non-public IP address: loopback, private, link-local (including `169.254.169.254`), etc.
- is a local name: `localhost`, `*.local`, `*.internal`, or a name without a dot
- points to shrinkr itself
- is on the domain blocklist: other URL shorteners by default, plus any domains listed in the
  `BLOCKED_DOMAINS` environment variable (comma-separated, subdomains included)

These checks look at the URL only; they don't resolve DNS.

### Rate limits

Each client IP may make, per minute:

| Routes | Default | Environment variable |
|---|---|---|
| `POST /api/links` | 10 | `RATE_LIMIT_CREATE_PER_MINUTE` |
| `GET`/`PATCH`/`DELETE /api/links/{code}` and `/stats` | 60 | `RATE_LIMIT_MANAGE_PER_MINUTE` |
| `GET /api/links/{code}/qr` | 60 | `RATE_LIMIT_QR_PER_MINUTE` |

Over the limit, the API answers `429 Too Many Requests` with a `Retry-After` header (seconds).
Redirects are not rate limited. Counters live in Redis (`REDIS_URL`, default
`redis://localhost:6379/0`); if Redis is unavailable, requests are allowed and a warning is logged.

### Managing a link

Creating a link returns a `manage_token`. **It is shown only once**: shrinkr stores only a
SHA-256 hash of it. Send it as a bearer token to view, change or delete that link:

```bash
TOKEN=...   # the manage_token from the create response

curl localhost:8000/api/links/my-link -H "Authorization: Bearer $TOKEN"

curl -X PATCH localhost:8000/api/links/my-link -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"is_disabled": true}'

curl -X DELETE localhost:8000/api/links/my-link -H "Authorization: Bearer $TOKEN"
```

`PATCH` accepts any of `url`, `expires_at`, `max_clicks` (send `null` to remove a limit) and
`is_disabled`; fields not sent are left unchanged. A missing token returns `401`, a wrong one `403`.
In the API docs at `/docs`, use the **Authorize** button to enter a token.

### Clicks per day

`GET /api/links/{code}/stats?days=30` (owner only; `days` 1–365, default 30):

```json
{
  "code": "my-link",
  "total_clicks": 10,
  "daily": [{"day": "2026-10-17", "clicks": 0}, {"day": "2026-10-18", "clicks": 10}]
}
```

`daily` has one entry per **UTC** day, oldest first, including days without clicks. The totals
are kept by the worker; clicks made while Redis was unavailable count in `total_clicks` only.

### QR codes

`GET /api/links/{code}/qr` returns a QR code that encodes the **short** URL, so printed codes
keep working (and their scans are counted) even if the target changes. No token is needed.

| Parameter | Default | Values |
|---|---|---|
| `format` | `svg` | `svg` (vector, any print size) or `png` |
| `scale` | `10` | 1–40: pixels (PNG) or units (SVG) per QR module |
| `download` | `false` | `true` makes the browser save it as `shrinkr-<code>.<format>` |

```bash
curl -o my-link.png "localhost:8000/api/links/my-link/qr?format=png&scale=20"
```

Responses can be cached for a day. Limited to `RATE_LIMIT_QR_PER_MINUTE` (default 60) per client.

### Cleaning up expired links

Expired links keep answering `410 Gone` for a grace period, then can be deleted:

```bash
docker compose run --rm app python -m app.cleanup                  # default grace: 7 days
docker compose run --rm app python -m app.cleanup --grace-days 30
```

Run it periodically (for example once a day). Links limited only by `max_clicks` are not deleted.

## Web app

The page at `/` is plain HTML, CSS and JavaScript (`app/static/`), with no build step.

- Links you create are remembered **in your browser** (localStorage), together with their
  management tokens; "Add a link you created elsewhere" imports one by code and token.
- Each link's panel shows its clicks (all time, last 7 days, today) and a chart of clicks per
  day over 7, 30 or 90 days, and lets you change the target, expiry and click limit,
  disable/enable or delete it.
- The page is served with a strict Content Security Policy (scripts and styles only from
  shrinkr itself, no inline code), and user data is only ever inserted as text.
- Opening an unknown, expired or disabled link in a browser shows an explanatory page.

## How it works

```
GET /{code} ─► app ─► Redis cache ── hit ──► 302 redirect   (+ click event queued in Redis)
                 │        miss
                 └──────► PostgreSQL ──────► 302 redirect   (+ cached for next time)

worker ─► reads click events from the Redis stream in batches ─► adds clicks and daily totals to PostgreSQL
```

| Component | Role |
|---|---|
| `app` | FastAPI web app and API (`uvicorn app.main:app`) |
| `worker` | Counts queued click events into PostgreSQL (`python -m app.worker`) |
| PostgreSQL | Source of truth: links, click counts and clicks per day |
| Redis | Cache of `code → target`, click event stream, rate-limit counters |

- **Cache:** links without a click limit are cached for up to `CACHE_TTL_SECONDS` (default 300),
  never beyond their expiry. Edits and deletes remove the cached entry.
- **Clicks** on cached links are queued in a Redis Stream (`clicks`) and counted by the worker,
  usually within a second. Several workers can run at once (consumer group `click-counters`).
- **Click-limited links** (`max_clicks`) skip the cache and are counted directly in PostgreSQL,
  so the limit is exact.
- **If Redis is unavailable**, redirects fall back to PostgreSQL and count clicks there directly.

## Running locally

Prerequisite: Docker (with Docker Compose).

```bash
docker compose up -d --build   # build the image, start PostgreSQL + Redis, run migrations, start the app
```

Open http://localhost:8000.

| Task | Command |
|---|---|
| See running containers | `docker compose ps` |
| Follow the app logs | `docker compose logs -f app` |
| Stop (data is kept) | `docker compose down` |
| Stop and delete all data | `docker compose down -v` |
| Rebuild after code changes | `docker compose up -d --build` |
| Follow the worker | `docker compose logs -f worker` |
| Click events waiting to be counted | `docker compose exec redis redis-cli xlen clicks` |
| Run two workers | `docker compose up -d --scale worker=2` |

The app reads its database connection from `DATABASE_URL`
(default: `postgresql+psycopg://shrinkr:shrinkr@localhost:5432/shrinkr`).

## Database migrations

The schema is managed with [Alembic](https://alembic.sqlalchemy.org/); migration scripts live in
`migrations/versions/`. With Docker Compose, the `migrate` service runs `alembic upgrade head`
before the app starts, and the app only starts if the migrations succeed.

To add a migration after changing `app/models.py`:

```bash
docker compose run --rm -v "$PWD/app:/code/app" -v "$PWD/migrations:/code/migrations" \
  migrate alembic revision --autogenerate --rev-id 0002 -m "describe the change"
```

Use the next number for `--rev-id` so migrations stay in readable order.

Review the generated file, then `docker compose up -d --build` applies it.

### Without Docker

With Python 3.12+, a PostgreSQL server and a Redis server available:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
python -m app.worker        # in a second terminal
```

## Tests

Run in a throwaway Python container (nothing installed on the host):

```bash
docker run --rm -v "$PWD":/src -w /src python:3.14-slim \
  sh -c "pip install -q -r requirements.txt -r requirements-dev.txt && pytest"
```

Or, inside a virtualenv: `pip install -r requirements-dev.txt && pytest`.

Tests build a temporary SQLite database by running the migrations, and check that the models
and migrations are in sync. Redis is replaced by an in-memory fake ([fakeredis](https://github.com/cunla/fakeredis-py)). Set `TEST_DATABASE_URL` to run them against PostgreSQL instead.

### Browser check

With the stack running (`docker compose up -d`), this clicks through the web app in a headless
Chromium (in a throwaway container) and saves screenshots to `e2e/screenshots/`:

```bash
./e2e/run.sh
```

It creates and deletes its own test links, and fails on any JavaScript error or Content Security
Policy violation.
