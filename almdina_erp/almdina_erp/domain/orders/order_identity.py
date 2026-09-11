from __future__ import annotations

import re


ORDER_NAME_SERIES = "YY.-.#####"

_LEGACY_ORDER_NAME_RE = re.compile(r"^DCO-(?P<year>\d{4})-(?P<number>\d{5})$")
_COMPACT_ORDER_NAME_RE = re.compile(r"^(?P<year>\d{2})-(?P<number>\d{5})$")


def compact_legacy_order_name(name: str) -> str | None:
    """Return the canonical compact name for a legacy DCO identifier."""

    match = _LEGACY_ORDER_NAME_RE.fullmatch(str(name or "").strip())
    if not match:
        return None
    return f"{match.group('year')[-2:]}-{match.group('number')}"


def compact_order_sequence(name: str) -> tuple[str, int] | None:
    """Return ``(two_digit_year, sequence)`` for a canonical compact name."""

    match = _COMPACT_ORDER_NAME_RE.fullmatch(str(name or "").strip())
    if not match:
        return None
    return match.group("year"), int(match.group("number"))


__all__ = [
    "ORDER_NAME_SERIES",
    "compact_legacy_order_name",
    "compact_order_sequence",
]
