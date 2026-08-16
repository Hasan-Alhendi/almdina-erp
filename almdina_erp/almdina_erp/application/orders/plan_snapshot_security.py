from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


# Cutting-plan snapshots are shared with planning, drawing, production, print,
# and DXF surfaces. They are therefore an operational geometry artifact, never a
# financial transport. Financial approval values live in protected permlevel-1
# fields and the dedicated costing services instead.
_FINANCIAL_PLAN_KEYS = frozenset(
    {
        "approved_cost",
        "costing_currency",
        "customer_quote_status",
        "special_shape_price_status",
        "special_shape_price_note",
        "special_shape_price_approved_by",
        "special_shape_price_approved_on",
        "clipped_corner_edge_price_status",
        "clipped_corner_edge_price_note",
        "clipped_corner_edge_price_set_by",
        "clipped_corner_edge_price_set_on",
    }
)
_FINANCIAL_PLAN_PREFIXES = (
    "special_shape_price_",
    "clipped_corner_edge_price_",
)


def is_financial_plan_key(key: Any) -> bool:
    """Return whether one JSON key belongs to the financial data boundary."""

    normalized = str(key or "").strip().lower()
    if not normalized:
        return False
    if normalized in _FINANCIAL_PLAN_KEYS:
        return True
    if normalized.endswith("_usd"):
        return True
    return normalized.startswith(_FINANCIAL_PLAN_PREFIXES)


def sanitize_plan_snapshot(value: Any) -> Any:
    """Deep-copy JSON-compatible plan data while removing financial metadata.

    The sanitizer is deliberately recursive because optimization engines may
    copy piece metadata into nested sheets. A top-level-only filter would leave
    edge rates, piece costs, or special-shape prices reachable through a plan
    endpoint even when scalar DocType fields are protected by permlevel 1.
    """

    if isinstance(value, Mapping):
        return {
            key: sanitize_plan_snapshot(item)
            for key, item in value.items()
            if not is_financial_plan_key(key)
        }
    if isinstance(value, list):
        return [sanitize_plan_snapshot(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_plan_snapshot(item) for item in value]
    return value


def sanitize_plan_snapshot_json(raw: Any) -> str:
    """Sanitize serialized plan JSON without rewriting already-safe payloads."""

    text = "" if raw is None else str(raw)
    if not text.strip():
        return text

    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        # Do not destructively rewrite malformed historical data here. Callers
        # that parse the snapshot already fail closed; the migration preserves
        # invalid source text for forensic recovery rather than guessing.
        return text

    sanitized = sanitize_plan_snapshot(parsed)
    if sanitized == parsed:
        return text
    return json.dumps(
        sanitized,
        ensure_ascii=False,
        separators=(",", ":"),
    )


__all__ = [
    "is_financial_plan_key",
    "sanitize_plan_snapshot",
    "sanitize_plan_snapshot_json",
]
