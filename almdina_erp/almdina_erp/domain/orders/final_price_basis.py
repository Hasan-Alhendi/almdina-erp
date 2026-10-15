"""Canonical pricing-basis payload and fingerprint for final-price approval.

Reusable by phase-2 approval and phase-3 invalidation. Framework-free.
The fingerprint covers inputs that change commercial price, not display notes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.orders.costing import round_value
from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
)


COST_SETTINGS_FIELDS = (
    "board_rate_usd",
    "cutting_cost_per_board_usd",
    "offcut_price_usd",
)

# Commercial inputs that invalidate approval even when the invoice total is unchanged.
_PIECE_INPUT_FIELDS = (
    "width_cm",
    "length_cm",
    "allow_rotation",
    "edge_long_right",
    "edge_long_left",
    "edge_width_top",
    "edge_width_bottom",
    "edge_break_length_cm",
    "clipped_corner_position",
    "clipped_corner_width_cm",
    "clipped_corner_length_cm",
    "special_shape_geometry_token",
)

_PIECE_BASIS_FIELDS = (
    "piece_no",
    "piece_type",
    "qty",
    "factory_execution_qty",
    "edge_type",
    "edge_meters",
    "edge_rate_usd",
    "edge_cost_usd",
    "edge_break",
    "edge_break_only",
    "edge_break_meters",
    "edge_break_rate_usd",
    "edge_break_cost_usd",
    "special_shape_custom_unit_price_usd",
    "special_shape_final_unit_price_usd",
    "special_shape_price_status",
    "clipped_corner_edge_price_usd",
    "clipped_corner_edge_price_status",
    "extra_double",
    "extra_double_unit_price_usd",
    "extra_double_total_usd",
    "extra_full_door_double",
    "extra_full_door_double_unit_price_usd",
    "extra_full_door_double_total_usd",
    "extra_liner",
    "extra_liner_unit_price_usd",
    "extra_liner_total_usd",
    "extra_back_groove",
    "extra_back_groove_unit_price_usd",
    "extra_back_groove_total_usd",
    "extra_recessed_handle_cutout",
    "extra_recessed_handle_cutout_unit_price_usd",
    "extra_recessed_handle_cutout_total_usd",
    "extra_addons_total_usd",
    *_PIECE_INPUT_FIELDS,
)

# Order-owned commercial inputs only (no plan-derived board counts / totals).
_ORDER_INPUT_PIECE_FIELDS = (
    "piece_no",
    "piece_type",
    "qty",
    "width_cm",
    "length_cm",
    "allow_rotation",
    "edge_type",
    "edge_long_right",
    "edge_long_left",
    "edge_width_top",
    "edge_width_bottom",
    "edge_long_right_type_override",
    "edge_long_left_type_override",
    "edge_width_top_type_override",
    "edge_width_bottom_type_override",
    "edge_break",
    "edge_break_only",
    "edge_break_length_cm",
    "clipped_corner_position",
    "clipped_corner_width_cm",
    "clipped_corner_length_cm",
    "special_shape_geometry_token",
    "special_shape_custom_unit_price_usd",
    "special_shape_price_status",
    "clipped_corner_edge_price_usd",
    "clipped_corner_edge_price_status",
    "extra_double",
    "extra_full_door_double",
    "extra_liner",
    "extra_back_groove",
    "extra_recessed_handle_cutout",
)

_MONEY_KEYS = frozenset(
    {
        "board_rate_usd",
        "cutting_cost_per_board_usd",
        "offcut_price_usd",
        "mdf_cost_usd",
        "cutting_cost_usd",
        "edge_cost_usd",
        "total_cost_usd",
        "edge_rate_usd",
        "edge_meters",
        "edge_break_meters",
        "edge_break_rate_usd",
        "edge_break_cost_usd",
        "special_shape_custom_unit_price_usd",
        "special_shape_final_unit_price_usd",
        "clipped_corner_edge_price_usd",
        "extra_double_unit_price_usd",
        "extra_double_total_usd",
        "extra_full_door_double_unit_price_usd",
        "extra_full_door_double_total_usd",
        "extra_liner_unit_price_usd",
        "extra_liner_total_usd",
        "extra_back_groove_unit_price_usd",
        "extra_back_groove_total_usd",
        "extra_recessed_handle_cutout_unit_price_usd",
        "extra_recessed_handle_cutout_total_usd",
        "extra_addons_total_usd",
        "approved_amount_usd",
        "customer_quote_total_usd",
        "invoice_preview_total_usd",
    }
)


def normalize_money(value: Any, *, decimals: int = 3) -> float:
    """Normalize finite money/metrics; missing becomes 0 without treating 0 as absent."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if not math.isfinite(number):
        number = 0.0
    return round_value(number, decimals)


_DIMENSION_KEYS = frozenset(
    {
        "width_cm",
        "length_cm",
        "clipped_corner_width_cm",
        "clipped_corner_length_cm",
        "edge_break_length_cm",
        "full_board_width_mm",
        "full_board_length_mm",
    }
)


def geometry_token(value: Any) -> str:
    """Stable short token for special-shape geometry without embedding raw JSON."""

    text = str(value or "").strip()
    if not text:
        return ""
    return fingerprint_payload({"geometry": text})


def _normalize_value(key: str, value: Any) -> Any:
    if key in _MONEY_KEYS:
        return normalize_money(value)
    if key in _DIMENSION_KEYS:
        return normalize_money(value, decimals=3)
    if key in {
        "qty",
        "factory_execution_qty",
        "piece_no",
        "required_boards",
        "extra_double",
        "extra_full_door_double",
        "extra_liner",
        "extra_back_groove",
        "extra_recessed_handle_cutout",
        "edge_break",
        "edge_break_only",
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
    }:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0
    if isinstance(value, bool):
        return value
    if value is None:
        return ""
    return str(value).strip()


def build_final_price_basis_payload(
    *,
    cutting_plan: str,
    currency: str,
    plan_costs: Mapping[str, Any],
    required_boards: int,
    pieces: Sequence[Mapping[str, Any]],
    offcut_applicable: bool,
    offcut_assignments: Sequence[Mapping[str, Any]],
    invoice_preview_total_usd: float,
    customer_quote_total_usd: float,
    formula_version: str = PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
) -> dict[str, Any]:
    """Build the stable pricing-basis document that phase 2/3 hash and compare."""

    plan_block = {
        fieldname: normalize_money(plan_costs.get(fieldname))
        for fieldname in (
            "board_rate_usd",
            "cutting_cost_per_board_usd",
            "offcut_price_usd",
            "mdf_cost_usd",
            "cutting_cost_usd",
            "edge_cost_usd",
            "total_cost_usd",
        )
    }
    plan_block["required_boards"] = int(required_boards or 0)

    piece_rows: list[dict[str, Any]] = []
    for piece in pieces:
        row = {
            fieldname: _normalize_value(fieldname, piece.get(fieldname))
            for fieldname in _PIECE_BASIS_FIELDS
        }
        piece_rows.append(row)
    piece_rows.sort(key=lambda row: (row.get("piece_no") or 0, row.get("piece_type") or ""))

    assignments = []
    for item in offcut_assignments:
        assignments.append(
            {
                "source_owner": str(item.get("source_owner") or item.get("source") or "").strip(),
                "execution_owner": str(
                    item.get("execution_owner") or item.get("execution") or ""
                ).strip(),
                "piece_number": str(item.get("piece_number") or "").strip(),
            }
        )
    assignments.sort(
        key=lambda row: (row["piece_number"], row["source_owner"], row["execution_owner"])
    )

    invoice_total = normalize_money(invoice_preview_total_usd, decimals=2)
    quote_total = normalize_money(customer_quote_total_usd, decimals=3)

    return {
        "formula_version": str(formula_version or PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION),
        "currency": str(currency or "USD").strip() or "USD",
        "cutting_plan": str(cutting_plan or "").strip(),
        "plan": plan_block,
        "pieces": piece_rows,
        "offcut": {
            "applicable": bool(offcut_applicable),
            "assignments": assignments,
        },
        # Card/invoice commercial total is the amount being approved.
        "approved_amount_usd": invoice_total,
        "invoice_preview_total_usd": invoice_total,
        # Stored quote aggregate is included so a silent divergence still changes the token.
        "customer_quote_total_usd": quote_total,
    }


def fingerprint_final_price_basis(payload: Mapping[str, Any]) -> str:
    return fingerprint_payload(dict(payload))


def build_order_pricing_input_payload(
    *,
    pieces: Sequence[Mapping[str, Any]],
    full_board_width_mm: float = 0,
    full_board_length_mm: float = 0,
) -> dict[str, Any]:
    """Order-owned commercial inputs used to detect basis-affecting saves.

    Excludes display notes, operational status, and plan-derived totals so a
    notes-only save or derived recalculation with identical inputs does not
    look like a pricing change.
    """

    piece_rows: list[dict[str, Any]] = []
    for piece in pieces:
        row = {
            fieldname: _normalize_value(fieldname, piece.get(fieldname))
            for fieldname in _ORDER_INPUT_PIECE_FIELDS
        }
        # Accept either a precomputed token or raw geometry JSON from adapters.
        raw_geometry = piece.get("special_shape_geometry_json")
        if raw_geometry and not str(piece.get("special_shape_geometry_token") or "").strip():
            row["special_shape_geometry_token"] = geometry_token(raw_geometry)
        piece_rows.append(row)
    piece_rows.sort(key=lambda row: (row.get("piece_no") or 0, row.get("piece_type") or ""))
    return {
        "board": {
            "full_board_width_mm": normalize_money(full_board_width_mm, decimals=3),
            "full_board_length_mm": normalize_money(full_board_length_mm, decimals=3),
        },
        "pieces": piece_rows,
    }


def fingerprint_order_pricing_inputs(payload: Mapping[str, Any]) -> str:
    return fingerprint_payload(dict(payload))


def price_basis_token(fingerprint: str, *, formula_version: str | None = None) -> str:
    version = str(formula_version or PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION).strip()
    digest = str(fingerprint or "").strip()
    if not digest:
        return ""
    return f"{version}:{digest}"


def parse_price_basis_token(token: str | None) -> tuple[str, str]:
    text = str(token or "").strip()
    if not text or ":" not in text:
        return "", ""
    version, digest = text.split(":", 1)
    return version.strip(), digest.strip()


__all__ = [
    "COST_SETTINGS_FIELDS",
    "build_final_price_basis_payload",
    "build_order_pricing_input_payload",
    "fingerprint_final_price_basis",
    "fingerprint_order_pricing_inputs",
    "geometry_token",
    "normalize_money",
    "parse_price_basis_token",
    "price_basis_token",
]
