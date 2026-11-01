from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from sqlalchemy.ext.asyncio import AsyncEngine

from tess_chat.application.ports.tracing import AttributeValue, Span


class OtelTracer:
    def __init__(self) -> None:
        self._tracer = trace.get_tracer("tess_chat")

    def span(self, name: str, **attributes: AttributeValue) -> AbstractContextManager[Span]:
        return self._span(name, attributes)

    @contextmanager
    def _span(self, name: str, attributes: dict[str, AttributeValue]) -> Iterator[Span]:
        with self._tracer.start_as_current_span(name, attributes=attributes) as span:
            yield span


def setup_tracing(exporter: str, project_id: str) -> None:
    if exporter == "none":
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "tess-chat"}))
    if exporter == "gcp":
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

        span_exporter = CloudTraceSpanExporter(project_id)  # type: ignore[no-untyped-call]
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()


def instrument(app: FastAPI, engine: AsyncEngine, exporter: str) -> None:
    if exporter == "none":
        return
    FastAPIInstrumentor.instrument_app(app, excluded_urls="api/health")
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def add_trace_context(project_id: str) -> Any:
    def processor(_: Any, __: str, event: dict[str, Any]) -> dict[str, Any]:
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            trace_id = format(context.trace_id, "032x")
            event["trace_id"] = trace_id
            event["span_id"] = format(context.span_id, "016x")
            if project_id:
                event["logging.googleapis.com/trace"] = f"projects/{project_id}/traces/{trace_id}"
        return event

    return processor
