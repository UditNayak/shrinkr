import time

from fastapi import Request
from prometheus_client import Counter, Histogram

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["route"])


async def record(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # the route template ("/{code}"), not the path, so each short link isn't its own series
        route = request.scope.get("route")
        path = route.path if route else "unmatched"
        REQUESTS.labels(request.method, path, status).inc()
        LATENCY.labels(path).observe(time.perf_counter() - start)
