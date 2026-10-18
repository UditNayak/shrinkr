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

## Running on Kubernetes (kind)

The tools (kind, kubectl, helm) run in a container, so only Docker is needed:

```bash
./toolbox/run.sh k8s/up.sh       # create the cluster if needed, build and deploy
```

The app is then at http://localhost. Run `./toolbox/run.sh` without arguments for a shell with
the tools, e.g. `kubectl -n shrinkr get pods`. To remove the cluster:
`./toolbox/run.sh kind delete cluster --name shrinkr`.

- `k8s/postgres.yaml`, `k8s/redis.yaml`: StatefulSets with a persistent volume each.
- `charts/shrinkr`: Helm chart with the app (Deployment and NodePort Service on port 80), the
  worker, and a migration Job that runs as a pre-install/pre-upgrade hook.
- The database password is generated on the first deploy and stored only in the `shrinkr-db`
  Secret in the cluster.

Each deploy builds an image with a new tag and upgrades the Helm release:

```bash
helm -n shrinkr history shrinkr          # releases
helm -n shrinkr rollback shrinkr <rev>   # go back to a release
```

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
