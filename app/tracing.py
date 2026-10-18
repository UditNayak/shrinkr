import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup(app) -> None:
    # off unless an endpoint is set, so tests and local runs don't try to send traces
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    # service name and pod name come from OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    # skip the per-message "http send" spans, they only add noise
    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="healthz,metrics", exclude_spans=["send", "receive"]
    )
    # the database driver; the SQLAlchemy instrumentation doesn't support 2.1 yet
    PsycopgInstrumentor().instrument()
    RedisInstrumentor().instrument()
