"""Optional, request-local observation port. No storage or presentation here."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import time
from typing import Any, Protocol


class SearchTraceSink(Protocol):
    def emit(self, kind: str, **data: Any) -> Any: ...
    def failure(self, boundary: str, error: Exception) -> None: ...


class NullSink:
    def emit(self, kind: str, **data: Any) -> None:
        return None

    def failure(self, boundary: str, error: Exception) -> None:
        return None


NULL_SINK = NullSink()
_sink: ContextVar[SearchTraceSink] = ContextVar(
    "cutting_search_sink", default=NULL_SINK
)
_span: ContextVar[str | None] = ContextVar("cutting_search_span", default=None)


def trace_enabled() -> bool:
    return _sink.get() is not NULL_SINK


def trace_event(kind: str, **data: Any) -> Any:
    sink = _sink.get()
    if sink is NULL_SINK:
        return None
    try:
        return sink.emit(kind, span_id=_span.get(), **data)
    except Exception as error:
        # Observer failure cannot change a manufacturing result. The collector
        # keeps a separate loss counter, independent of the event quota.
        try:
            sink.failure(kind, error)
        except Exception:
            pass  # Even a broken external observer cannot affect manufacturing.
        return None


@contextmanager
def observe_search(sink: SearchTraceSink | None):
    token = _sink.set(sink or NULL_SINK)
    parent = _span.set(None)
    try:
        yield sink
    finally:
        _span.reset(parent)
        _sink.reset(token)


def traced(name: str, *, kind: str = "stage"):
    """Observe only real calls/yields; preserve signatures and disabled results."""

    def decorate(function):
        signature = inspect.signature(function)

        @contextmanager
        def scope(args, kwargs):
            values = signature.bind(*args, **kwargs).arguments
            span_id = trace_event(
                "span_start",
                name=name,
                span_kind=kind,
                parent_span_id=_span.get(),
                inputs=values,
            )
            token = _span.set(span_id)
            try:
                yield
            except BaseException as error:
                trace_event(
                    "span_end",
                    name=name,
                    stop_reason=(
                        "generator_exhausted"
                        if isinstance(error, StopIteration)
                        else "exception:" + type(error).__name__
                    ),
                )
                raise
            finally:
                _span.reset(token)

        if inspect.isgeneratorfunction(function):

            @wraps(function)
            def generator(*args, **kwargs):
                if not trace_enabled():
                    yield from function(*args, **kwargs)
                    return
                # Never leave a generator's context installed while suspended:
                # the consumer may call another stage before requesting next().
                iterator = function(*args, **kwargs)
                with scope(args, kwargs):
                    own_span = _span.get()
                    trace_event("generator_open", name=name)
                exhausted = False
                failure_reason = None
                try:
                    while True:
                        token = _span.set(own_span)
                        try:
                            result = next(iterator)
                            trace_event("generated", name=name, result=result)
                        except StopIteration:
                            exhausted = True
                            break
                        finally:
                            _span.reset(token)
                        yield result
                except BaseException as error:
                    if not isinstance(error, GeneratorExit):
                        failure_reason = "exception:" + type(error).__name__
                    raise
                finally:
                    iterator.close()
                    token = _span.set(own_span)
                    try:
                        trace_event(
                            "span_end",
                            name=name,
                            stop_reason=failure_reason
                            or (
                                "generator_exhausted"
                                if exhausted
                                else "consumer_stopped"
                            ),
                        )
                    finally:
                        _span.reset(token)

            return generator

        @wraps(function)
        def wrapper(*args, **kwargs):
            if not trace_enabled():
                return function(*args, **kwargs)
            with scope(args, kwargs):
                result = function(*args, **kwargs)
                returned_at = time.monotonic()
                trace_event("result", name=name, result=result)
                values = signature.bind(*args, **kwargs).arguments
                deadline = values.get(
                    "deadline_monotonic",
                    values.get("deadline", values.get("search_deadline")),
                )
                # An expired budget does not prove what caused a return.
                # Only explicit engine diagnostics may supply a stop cause.
                reason = "returned"
                if (
                    isinstance(result, tuple)
                    and len(result) == 2
                    and isinstance(result[1], dict)
                ):
                    reason = str(result[1].get("stop") or reason)
                trace_event(
                    "span_end",
                    name=name,
                    stop_reason=reason,
                    budget_expired_at_return=isinstance(deadline, (int, float))
                    and returned_at >= deadline,
                )
                return result

        return wrapper

    return decorate
