from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "mbi_http_requests_total",
    "HTTP requests processed by the API.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "mbi_http_request_duration_seconds",
    "HTTP request duration.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 120),
)
HTTP_IN_FLIGHT = Gauge("mbi_http_requests_in_flight", "Current in-flight API requests.")
BUILD_OPERATIONS = Counter("mbi_build_operations_total", "Build operations.", ("operation", "outcome"))
AI_OPERATIONS = Counter("mbi_ai_runs_total", "AI runs.", ("provider", "outcome"))


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("MBI_LOG_LEVEL", "INFO").upper(),
        format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    )


def configure_opentelemetry(app) -> bool:
    """Install OTLP tracing when the optional SDK/exporter is present and configured."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logging.getLogger(__name__).warning("OpenTelemetry endpoint configured but optional packages are unavailable")
        return False
    provider = TracerProvider(resource=Resource.create({"service.name": "mbi-api"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    return True


def install_observability_middleware(app) -> None:
    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        HTTP_IN_FLIGHT.inc()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_label = getattr(route, "path", None) or "unmatched"
            elapsed = time.perf_counter() - start
            HTTP_REQUESTS.labels(request.method, route_label, str(status)).inc()
            HTTP_DURATION.labels(request.method, route_label).observe(elapsed)
            HTTP_IN_FLIGHT.dec()


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
