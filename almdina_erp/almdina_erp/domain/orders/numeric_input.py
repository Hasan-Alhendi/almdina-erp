from __future__ import annotations

from typing import Any


def default_if_missing(value: Any, default: Any) -> Any:
    """Apply a default only when an input is genuinely missing.

    Numeric zero is an explicit value. Validation may reject it later, but it
    must never be silently replaced by a positive default.
    """

    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return value


__all__ = ["default_if_missing"]
