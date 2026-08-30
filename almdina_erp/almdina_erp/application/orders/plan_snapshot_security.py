from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    canonicalize_snapshot_geometries,
)


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


def _sanitize_plan_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _sanitize_plan_value(item)
            for key, item in value.items()
            if not is_financial_plan_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_plan_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_plan_value(item) for item in value]
    return value


def sanitize_plan_snapshot(value: Any) -> Any:
    """Return safe operational plan data with trusted persisted DXF geometry.

    Financial metadata is removed recursively. If a public DXF ``geometry``
    contract is present it is validated and canonicalized; malformed geometry is
    rejected instead of being silently discarded and reinterpreted as a rectangle.
    Legacy plans without ``geometry`` remain unchanged.
    """

    sanitized = _sanitize_plan_value(value)
    return canonicalize_snapshot_geometries(sanitized)


def sanitize_plan_snapshot_json(raw: Any) -> str:
    """Return a safe serialized plan, failing closed on malformed JSON."""

    text = "" if raw is None else str(raw)
    if not text.strip():
        return text

    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        # A malformed payload cannot be proven non-financial. Never return or
        # persist the raw text through an operational plan surface.
        return "{}"

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
