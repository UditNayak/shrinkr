# shrinkr

A URL shortener built with FastAPI, PostgreSQL and Redis.

## Running

Requires Docker with Docker Compose.

```bash
docker compose up -d --build
```

The app is at http://localhost:8000 and the API docs at http://localhost:8000/docs.

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f app` / `docker compose logs -f worker` |
| Stop (keep data) | `docker compose down` |
| Stop and delete data | `docker compose down -v` |
| Delete expired links | `docker compose run --rm app python -m app.cleanup` |

## Running on Kubernetes (kind + Argo CD)

The tools (kind, kubectl, helm) run in a container, so only Docker is needed. One-time setup:

```bash
./toolbox/run.sh k8s/up.sh       # cluster, database secret, Argo CD and its Applications
```

From then on Argo CD deploys from git: a push to `devops-improvements` is tested and built
by CI, CI commits the new image tag to `charts/shrinkr/values.yaml`, and Argo CD syncs it.
The app is at http://localhost.

| Path | What Argo CD deploys from it |
|---|---|
| `k8s/databases/` | PostgreSQL and Redis StatefulSets (Application `databases`) |
| `charts/shrinkr/` | App, worker and a migration Job run before each sync (Application `shrinkr`) |

```bash
./toolbox/run.sh kubectl -n argocd get applications     # sync and health status
./toolbox/argocd-ui.sh                                  # web UI at https://localhost:8080
./toolbox/run.sh kind delete cluster --name shrinkr     # remove everything
```

The database password is generated on the first setup and stored only in the `shrinkr-db`
Secret in the cluster.

## CI

`.github/workflows/ci.yml` runs on every push to `main` and `devops-improvements` and on pull
requests:

- `test`: the test suite against PostgreSQL, and `helm lint`
- `build` (pushes only, after `test` passes): builds the image for arm64, pushes it to
  `ghcr.io/uditnayak/shrinkr:<commit sha>`, and commits that tag to `charts/shrinkr/values.yaml`
  (with `[skip ci]`), which Argo CD then deploys

## Services

| Service | Purpose |
|---|---|
| `app` | Web UI and API (`uvicorn app.main:app`) |
| `worker` | Counts queued clicks into PostgreSQL (`python -m app.worker`) |
| `migrate` | Applies database migrations (`alembic upgrade head`) and exits |
| `db` | PostgreSQL |
| `redis` | Redirect cache, click queue, rate-limit counters |

Redirects are served from the Redis cache when possible, and clicks are queued in a Redis
stream for the worker. Links with a click limit are counted directly in PostgreSQL. If Redis
is down, redirects fall back to PostgreSQL.

## API

| Endpoint | Description | Token |
|---|---|---|
| `POST /api/links` | Create a short link | |
| `GET /{code}` | Redirect to the target URL | |
| `GET /api/links/{code}` | Link details | yes |
| `PATCH /api/links/{code}` | Change URL, expiry, click limit or disable | yes |
| `DELETE /api/links/{code}` | Delete the link | yes |
| `GET /api/links/{code}/stats?days=30` | Clicks per day | yes |
| `GET /api/links/{code}/qr?format=svg` | QR code (`svg` or `png`) | |

Create request:

```json
{"url": "https://example.com/", "alias": "my-link", "expires_at": "2026-12-31T23:59:00Z", "max_clicks": 100}
```

Only `url` is required. The response contains a `manage_token`, shown once; send it as
`Authorization: Bearer <token>` for the endpoints marked above.

```bash
curl -X POST localhost:8000/api/links -H 'content-type: application/json' -d '{"url": "https://example.com/"}'
curl localhost:8000/api/links/<code> -H "Authorization: Bearer <token>"
```

Rules:

- Aliases: 3-32 letters, digits, `-` or `_`; some names (`api`, `docs`, ...) are reserved.
- Targets on private or local networks, other URL shorteners, URLs with credentials and links
  to shrinkr itself are rejected.
- Rate limits per client IP and minute: 10 creates, 60 management requests, 60 QR requests.

## Configuration

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://shrinkr:shrinkr@localhost:5432/shrinkr` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `CACHE_TTL_SECONDS` | `300` |
| `BLOCKED_DOMAINS` | none (comma-separated, added to the built-in list) |
| `RATE_LIMIT_CREATE_PER_MINUTE` | `10` |
| `RATE_LIMIT_MANAGE_PER_MINUTE` | `60` |
| `RATE_LIMIT_QR_PER_MINUTE` | `60` |

## Migrations

Migrations live in `migrations/versions/` and are applied by the `migrate` service. To create
one after changing `app/models.py`:

```bash
docker compose run --rm -v "$PWD/app:/code/app" -v "$PWD/migrations:/code/migrations" \
  migrate alembic revision --autogenerate --rev-id 0006 -m "describe the change"
```

## Tests

```bash
docker run --rm -v "$PWD":/src -w /src python:3.14-slim \
  sh -c "pip install -q -r requirements.txt -r requirements-dev.txt && pytest"
```

The tests use SQLite and an in-memory fake Redis, so no services need to be running.
