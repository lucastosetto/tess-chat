from contextlib import AbstractContextManager, nullcontext
from typing import Protocol

AttributeValue = str | int | float | bool


class Span(Protocol):
    def set_attribute(self, key: str, value: AttributeValue) -> None: ...


class Tracer(Protocol):
    def span(self, name: str, **attributes: AttributeValue) -> AbstractContextManager[Span]: ...


class _NoopSpan:
    def set_attribute(self, key: str, value: AttributeValue) -> None:
        return None


class NoopTracer:
    def span(self, name: str, **attributes: AttributeValue) -> AbstractContextManager[Span]:
        return nullcontext(_NoopSpan())
