from __future__ import annotations

from types import SimpleNamespace
from typing import Any


INTERNAL_STAGE_WRITE_FLAG = "almdina_internal_stage_write"


def authorize_internal_stage_write(document: Any) -> Any:
    """Mark one in-memory stage mutation as owned by the command repository.

    ``ignore_permissions=True`` is intentionally insufficient: it bypasses
    Frappe's role checks but not this explicit application boundary.
    """

    flags = getattr(document, "flags", None)
    if flags is None:
        flags = SimpleNamespace()
        document.flags = flags
    setattr(flags, INTERNAL_STAGE_WRITE_FLAG, True)
    return document


def is_internal_stage_write(document: Any) -> bool:
    flags = getattr(document, "flags", None)
    return bool(
        flags
        and getattr(flags, INTERNAL_STAGE_WRITE_FLAG, False)
    )


__all__ = [
    "INTERNAL_STAGE_WRITE_FLAG",
    "authorize_internal_stage_write",
    "is_internal_stage_write",
]
