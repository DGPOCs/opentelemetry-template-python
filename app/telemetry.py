"""Telemetry configuration utilities for exporting data to MongoDB."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricsData,
    PeriodicExportingMetricReader,
    MetricExportResult,  
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ReadableSpan, SpanExporter, SpanExportResult
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

# Cargar .env ANTES de cualquier uso de os.getenv o configure_telemetry
load_dotenv(dotenv_path=os.getenv("ENV_FILE", ".env"), override=False)

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None


def _mongo_client() -> MongoClient:
    """Create and cache a MongoDB client using environment variables."""
    global _client
    if _client is not None:
        return _client

    uri = os.getenv("MONGO_URI")
    if uri:
        logger.debug("Connecting to MongoDB using URI")
        _client = MongoClient(uri, tz_aware=True)
        return _client

    host = os.getenv("MONGO_HOST", "localhost")
    port = int(os.getenv("MONGO_PORT", "27017"))
    username = os.getenv("MONGO_USERNAME")
    password = os.getenv("MONGO_PASSWORD")
    auth_source = os.getenv("MONGO_AUTH_SOURCE")

    client_kwargs = {"host": host, "port": port, "tz_aware": True}
    if username and password:
        client_kwargs.update({"username": username, "password": password})
    if auth_source:
        client_kwargs["authSource"] = auth_source

    _client = MongoClient(**client_kwargs)
    return _client


def _mongo_database() -> Database:
    client = _mongo_client()
    db_name = os.getenv("MONGO_DB_NAME", "telemetry")
    return client[db_name]


def _configure_logging(collection: Collection) -> None:
    """Attach a MongoDB logging handler to the root logger."""

    class MongoLoggingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # noqa: D401 - inherited docstring
            try:
                collection.insert_one(
                    {
                        "logger": record.name,
                        "level": record.levelname,
                        "message": record.getMessage(),
                        "created_at": datetime.utcfromtimestamp(record.created),
                        "pathname": record.pathname,
                        "lineno": record.lineno,
                        "funcName": record.funcName,
                        "process": record.process,
                        "thread": record.thread,
                        "module": record.module,
                        "processName": record.processName,
                        "args": list(record.args) if isinstance(record.args, tuple) else record.args,
                        "exception": self.formatException(record.exc_info) if record.exc_info else None,
                    }
                )
            except PyMongoError:
                self.handleError(record)

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
    handler = MongoLoggingHandler()
    handler.setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger().addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").propagate = False
    logging.getLogger("uvicorn.access").propagate = False


def _serialize_attributes(attributes: Dict[str, object]) -> Dict[str, object]:
    serialized: Dict[str, object] = {}
    for key, value in attributes.items():
        if isinstance(value, (list, tuple)):
            serialized[key] = list(value)
        else:
            serialized[key] = value
    return serialized


class MongoSpanExporter(SpanExporter):
    """Custom span exporter that writes spans to MongoDB."""

    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:  # noqa: D401
        documents: List[Dict[str, object]] = []
        for span in spans:
            span_context = span.get_span_context()
            parent = span.parent
            documents.append(
                {
                    "name": span.name,
                    "context": {
                        "trace_id": format(span_context.trace_id, "032x"),
                        "span_id": format(span_context.span_id, "016x"),
                        "trace_state": span_context.trace_state.to_header(),
                    },
                    "parent_span_id": None
                    if parent is None
                    else format(parent.span_id, "016x"),
                    "kind": span.kind.name,
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "status": {
                        "status_code": span.status.status_code.name,
                        "description": span.status.description,
                    },
                    "attributes": _serialize_attributes(dict(span.attributes)),
                    "events": [
                        {
                            "name": event.name,
                            "timestamp": event.timestamp,
                            "attributes": _serialize_attributes(dict(event.attributes)),
                        }
                        for event in span.events
                    ],
                    "links": [
                        {
                            "context": {
                                "trace_id": format(link.context.trace_id, "032x"),
                                "span_id": format(link.context.span_id, "016x"),
                            },
                            "attributes": _serialize_attributes(dict(link.attributes or {})),
                        }
                        for link in span.links
                    ],
                }
            )

        if not documents:
            return SpanExportResult.SUCCESS

        try:
            self._collection.insert_many(documents)
        except PyMongoError as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to export spans to MongoDB: %s", exc)
            return SpanExportResult.FAILURE

        return SpanExportResult.SUCCESS


class MongoMetricExporter(MetricExporter):
    """Custom metric exporter that writes metric data to MongoDB."""

    def __init__(self, collection: Collection) -> None:
        super().__init__()
        self._collection = collection

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs: object,
    ) -> MetricExportResult:
        documents: List[Dict[str, object]] = []

        for resource_metrics in metrics_data.resource_metrics:
            resource_attributes = _serialize_attributes(dict(resource_metrics.resource.attributes))
            for scope_metrics in resource_metrics.scope_metrics:
                scope_info = {
                    "name": scope_metrics.scope.name,
                    "version": scope_metrics.scope.version,
                }
                for metric in scope_metrics.metrics:
                    datapoints: List[Dict[str, object]] = []
                    for point in metric.data.data_points:  # type: ignore[attr-defined]
                        point_payload: Dict[str, object] = {
                            "time_unix_nano": getattr(point, "time_unix_nano", None),
                            "start_time_unix_nano": getattr(point, "start_time_unix_nano", None),
                            "attributes": _serialize_attributes(dict(getattr(point, "attributes", {}))),
                        }
                        for attr_name in ("value", "count", "sum", "min", "max", "last", "bucket_counts", "boundaries"):
                            if hasattr(point, attr_name):
                                value = getattr(point, attr_name)
                                point_payload[attr_name] = list(value) if isinstance(value, (list, tuple)) else value
                        datapoints.append(point_payload)

                    documents.append(
                        {
                            "name": metric.name,
                            "description": metric.description,
                            "unit": metric.unit,
                            "resource": resource_attributes,
                            "instrumentation_scope": scope_info,
                            "data": datapoints,
                        }
                    )

        if not documents:
            return MetricExportResult.SUCCESS

        try:
            self._collection.insert_many(documents)
        except PyMongoError as exc:
            logger.exception("Failed to export metrics to MongoDB: %s", exc)
            return MetricExportResult.FAILURE

        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: object) -> None:
        return None



def configure_telemetry() -> tuple[TracerProvider, MeterProvider]:
    """Configure logging, tracing and metrics to export data into MongoDB."""
    log_collection_name = os.getenv("MONGO_LOG_COLLECTION", "logs")
    trace_collection_name = os.getenv("MONGO_TRACE_COLLECTION", "traces")
    metric_collection_name = os.getenv("MONGO_METRIC_COLLECTION", "metrics")

    try:
        database = _mongo_database()
        log_collection = database[log_collection_name]
        trace_collection = database[trace_collection_name]
        metric_collection = database[metric_collection_name]
    except PyMongoError as exc:  # pragma: no cover - fallback for unavailable MongoDB
        logging.basicConfig(level=logging.INFO)
        logger.exception("Unable to configure MongoDB telemetry backend: %s", exc)
        resource = Resource.create({"service.name": "devto-news-service"})
        tracer_provider = TracerProvider(resource=resource)
        meter_provider = MeterProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)
        metrics.set_meter_provider(meter_provider)
        return tracer_provider, meter_provider

    _configure_logging(log_collection)

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "devto-news-service"),
            "service.version": os.getenv("OTEL_SERVICE_VERSION", "1.0.0"),
            "service.instance.id": os.getenv("OTEL_SERVICE_INSTANCE_ID", "local-instance"),
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    span_exporter = MongoSpanExporter(trace_collection)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_exporter = MongoMetricExporter(metric_collection)
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    return tracer_provider, meter_provider
