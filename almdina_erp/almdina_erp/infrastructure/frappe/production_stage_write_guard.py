from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any


INTERNAL_STAGE_WRITE_FLAG = "almdina_internal_stage_write"


def authorize_internal_stage_write(document: Any) -> Any:
    """Mark an in-memory stage mutation as owned by the command repository.

    This low-level primitive exists for the context manager below. Runtime code
    outside the production-stage repository must not call it directly.
    ``ignore_permissions=True`` is intentionally insufficient: it bypasses
    Frappe's role checks but not this explicit application boundary.
    """

    flags = getattr(document, "flags", None)
    if flags is None:
        flags = SimpleNamespace()
        document.flags = flags
    setattr(flags, INTERNAL_STAGE_WRITE_FLAG, True)
    return document


def revoke_internal_stage_write(document: Any) -> Any:
    """Remove the transient write authority from an in-memory stage document."""

    flags = getattr(document, "flags", None)
    if flags is not None:
        setattr(flags, INTERNAL_STAGE_WRITE_FLAG, False)
    return document


def is_internal_stage_write(document: Any) -> bool:
    flags = getattr(document, "flags", None)
    return bool(
        flags
        and getattr(flags, INTERNAL_STAGE_WRITE_FLAG, False)
    )


@contextmanager
def internal_stage_write(document: Any) -> Iterator[Any]:
    """Grant transient, nest-safe authority for one repository action.

    The previous authority state is restored in ``finally``. This means an
    inner repository helper cannot revoke the still-active authority of an
    outer helper, while the outermost context always removes authority before
    returning the document to its caller. Exception paths receive the same
    cleanup guarantee.
    """

    was_authorized = is_internal_stage_write(document)
    authorize_internal_stage_write(document)
    try:
        yield document
    finally:
        if was_authorized:
            authorize_internal_stage_write(document)
        else:
            revoke_internal_stage_write(document)


__all__ = [
    "INTERNAL_STAGE_WRITE_FLAG",
    "authorize_internal_stage_write",
    "internal_stage_write",
    "is_internal_stage_write",
    "revoke_internal_stage_write",
]
