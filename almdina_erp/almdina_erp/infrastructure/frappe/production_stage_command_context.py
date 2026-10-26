"""Ephemeral persistence marker; never a capability or a client-supplied grant."""
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_FLAG = '_almdina_stage_activation'
_TOKEN = object()


def is_authorized_stage_activation(stage: Any) -> bool:
    return getattr(stage, 'flags', {}).get(_FLAG) is _TOKEN


@contextmanager
def authorized_stage_activation(stage: Any) -> Iterator[None]:
    previous = stage.flags.get(_FLAG)
    stage.flags[_FLAG] = _TOKEN
    try:
        yield
    finally:
        if previous is None:
            stage.flags.pop(_FLAG, None)
        else:
            stage.flags[_FLAG] = previous
