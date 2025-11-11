"""Telemetry configuration utilities for exporting data to an OTEL Collector."""

from __future__ import annotations

import logging
import os
from typing import Dict

from dotenv import load_dotenv
from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Load .env before any other configuration takes place
load_dotenv(dotenv_path=os.getenv("ENV_FILE", ".env"), override=False)

logger = logging.getLogger(__name__)


def _load_otlp_headers() -> Dict[str, str]:
    """Parse OTLP headers from the environment."""

    raw_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
    if not raw_headers:
        return {}

    headers: Dict[str, str] = {}
    for item in raw_headers.split(","):
        if not item:
            continue
        if "=" not in item:
            logger.warning("Ignoring malformed OTLP header entry: %s", item)
            continue
        key, value = item.split("=", 1)
        headers[key.strip()] = value.strip()
    return headers


def _collector_endpoint(path: str, env_var: str) -> str:
    """Build an OTLP endpoint for a given signal."""

    base = os.getenv(env_var)
    if base:
        return base.rstrip("/")

    collector_url = os.getenv("OTEL_COLLECTOR_URL", "http://localhost:4318").rstrip("/")
    return f"{collector_url}{path}"


def configure_telemetry() -> tuple[TracerProvider, MeterProvider]:
    """Configure logging, tracing and metrics to export data into an OTEL Collector."""

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    service_name = os.getenv("OTEL_SERVICE_NAME", "devto-news-service")
    service_version = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")
    service_instance = os.getenv("OTEL_SERVICE_INSTANCE_ID", "local-instance")

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "service.instance.id": service_instance,
        }
    )

    otlp_headers = _load_otlp_headers()

    # Configure tracing
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(
        endpoint=_collector_endpoint("/v1/traces", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"),
        headers=otlp_headers or None,
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Configure metrics
    metric_exporter = OTLPMetricExporter(
        endpoint=_collector_endpoint("/v1/metrics", "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"),
        headers=otlp_headers or None,
    )
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Configure logs
    logger_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(
        endpoint=_collector_endpoint("/v1/logs", "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"),
        headers=otlp_headers or None,
    )
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    _logs.set_logger_provider(logger_provider)

    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").propagate = False
    logging.getLogger("uvicorn.access").propagate = False

    otel_handler = LoggingHandler(level=getattr(logging, log_level, logging.INFO), logger_provider=logger_provider)
    logging.getLogger().addHandler(otel_handler)

    return tracer_provider, meter_provider
