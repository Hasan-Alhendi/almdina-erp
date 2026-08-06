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


@contextmanager
def internal_stage_write(document: Any) -> Iterator[Any]:
    """Grant write authority only for the duration of one repository action.

    The flag is always revoked, including when Frappe validation or persistence
    raises. This prevents a returned document from retaining reusable write
    authority after the repository call completes.
    """

    authorize_internal_stage_write(document)
    try:
        yield document
    finally:
        revoke_internal_stage_write(document)


def is_internal_stage_write(document: Any) -> bool:
    flags = getattr(document, "flags", None)
    return bool(
        flags
        and getattr(flags, INTERNAL_STAGE_WRITE_FLAG, False)
    )


__all__ = [
    "INTERNAL_STAGE_WRITE_FLAG",
    "authorize_internal_stage_write",
    "internal_stage_write",
    "is_internal_stage_write",
    "revoke_internal_stage_write",
]
