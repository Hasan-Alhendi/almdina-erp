from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .costing import round_value


EXTRA_PIECE_TYPE = "Extra"
EXTRA_ADDON_CODES = (
    "double",
    "full_door_double",
    "liner",
    "back_groove",
    "recessed_handle_cutout",
)
EXTRA_ADDON_FIELD_BY_CODE = {
    "double": "extra_double",
    "full_door_double": "extra_full_door_double",
    "liner": "extra_liner",
    "back_groove": "extra_back_groove",
    "recessed_handle_cutout": "extra_recessed_handle_cutout",
}
FULL_DOOR_DOUBLE_CUT_MULTIPLIER = 2
EXTRA_OVERLAY_LAYER_BY_KIND = {
    "liner": "Liner",
    "back_groove": "Rear Groove",
    "recessed_handle_cutout": "Handle Recess",
}
EXTRA_OVERLAY_LAYER_NAMES = frozenset(EXTRA_OVERLAY_LAYER_BY_KIND.values())
EXTRA_OVERLAY_KIND_BY_LAYER = {
    layer.strip().upper(): kind
    for kind, layer in EXTRA_OVERLAY_LAYER_BY_KIND.items()
}


class ExtraAddonError(ValueError):
    """Raised when an Extra-door selection or price violates a domain rule."""

    def __init__(self, code: str, addon_code: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.addon_code = addon_code


@dataclass(frozen=True, slots=True)
class ExtraAddonRates:
    double_usd: float = 0
    full_door_double_usd: float = 0
    liner_usd: float = 0
    back_groove_usd: float = 0
    recessed_handle_cutout_usd: float = 0


@dataclass(frozen=True, slots=True)
class ExtraAddonPieceInput:
    piece_type: str
    qty: int
    notes: str = ""
    double: bool = False
    full_door_double: bool = False
    liner: bool = False
    back_groove: bool = False
    recessed_handle_cutout: bool = False
    double_snapshot_unit_price_usd: float | None = None
    full_door_double_snapshot_unit_price_usd: float | None = None
    liner_snapshot_unit_price_usd: float | None = None
    back_groove_snapshot_unit_price_usd: float | None = None
    recessed_handle_cutout_snapshot_unit_price_usd: float | None = None


@dataclass(frozen=True, slots=True)
class ExtraAddonPieceResult:
    applicable: bool
    selected_codes: tuple[str, ...]
    double_unit_price_usd: float
    double_total_usd: float
    full_door_double_unit_price_usd: float
    full_door_double_total_usd: float
    liner_unit_price_usd: float
    liner_total_usd: float
    back_groove_unit_price_usd: float
    back_groove_total_usd: float
    recessed_handle_cutout_unit_price_usd: float
    recessed_handle_cutout_total_usd: float
    total_usd: float


@dataclass(frozen=True, slots=True)
class ExtraAddonPricingSummary:
    pieces: tuple[ExtraAddonPieceResult, ...]
    total_usd: float


def extra_overlay_kind_for_layer(layer: str) -> str | None:
    """Map a DXF layer name to an Extra overlay kind after case/whitespace normalize."""

    return EXTRA_OVERLAY_KIND_BY_LAYER.get(str(layer or "").strip().upper())


def extra_overlay_layer_for_kind(kind: str) -> str:
    """Return the canonical DXF layer name for one Extra overlay kind."""

    return EXTRA_OVERLAY_LAYER_BY_KIND[str(kind)]


def physical_cut_quantity(qty: int, *, full_door_double: bool) -> int:
    """Return optimizer/cut-list quantity without mutating customer qty."""

    resolved = max(0, int(qty or 0))
    if full_door_double and resolved > 0:
        return resolved * FULL_DOOR_DOUBLE_CUT_MULTIPLIER
    return resolved


def calculate_extra_addon_pricing(
    pieces: Iterable[ExtraAddonPieceInput],
    *,
    rates: ExtraAddonRates,
) -> ExtraAddonPricingSummary:
    """Validate selections and snapshot unit/total sales prices per row."""

    resolved_rates = {
        "double": _finite_non_negative(rates.double_usd),
        "full_door_double": _finite_non_negative(rates.full_door_double_usd),
        "liner": _finite_non_negative(rates.liner_usd),
        "back_groove": _finite_non_negative(rates.back_groove_usd),
        "recessed_handle_cutout": _finite_non_negative(
            rates.recessed_handle_cutout_usd
        ),
    }
    results: list[ExtraAddonPieceResult] = []
    order_total = 0.0

    for piece in pieces:
        selected = tuple(
            code
            for code, enabled in (
                ("double", piece.double),
                ("full_door_double", piece.full_door_double),
                ("liner", piece.liner),
                ("back_groove", piece.back_groove),
                ("recessed_handle_cutout", piece.recessed_handle_cutout),
            )
            if bool(enabled)
        )
        piece_type = str(piece.piece_type or "Regular")
        if piece_type != EXTRA_PIECE_TYPE:
            if selected:
                raise ExtraAddonError("non_extra_addon_selection", selected[0])
            results.append(_empty_result())
            continue

        if not selected:
            raise ExtraAddonError("extra_addon_required")
        if not str(piece.notes or "").strip():
            raise ExtraAddonError("extra_notes_required")

        qty = int(piece.qty or 0)
        if qty <= 0:
            raise ExtraAddonError("extra_quantity_invalid")
        snapshots = {
            "double": piece.double_snapshot_unit_price_usd,
            "full_door_double": piece.full_door_double_snapshot_unit_price_usd,
            "liner": piece.liner_snapshot_unit_price_usd,
            "back_groove": piece.back_groove_snapshot_unit_price_usd,
            "recessed_handle_cutout": (
                piece.recessed_handle_cutout_snapshot_unit_price_usd
            ),
        }
        effective_rates = {
            code: (
                _finite_non_negative(snapshots[code])
                if snapshots[code] is not None
                else resolved_rates[code]
            )
            for code in EXTRA_ADDON_CODES
        }
        for code in selected:
            if effective_rates[code] <= 0:
                raise ExtraAddonError("extra_addon_rate_not_configured", code)

        unit_values = {
            code: effective_rates[code] if code in selected else 0.0
            for code in EXTRA_ADDON_CODES
        }
        total_values = {
            code: _money(unit_values[code] * qty)
            for code in EXTRA_ADDON_CODES
        }
        row_total = _money(sum(total_values.values()))
        order_total += row_total
        results.append(
            ExtraAddonPieceResult(
                applicable=True,
                selected_codes=selected,
                double_unit_price_usd=unit_values["double"],
                double_total_usd=total_values["double"],
                full_door_double_unit_price_usd=unit_values["full_door_double"],
                full_door_double_total_usd=total_values["full_door_double"],
                liner_unit_price_usd=unit_values["liner"],
                liner_total_usd=total_values["liner"],
                back_groove_unit_price_usd=unit_values["back_groove"],
                back_groove_total_usd=total_values["back_groove"],
                recessed_handle_cutout_unit_price_usd=unit_values[
                    "recessed_handle_cutout"
                ],
                recessed_handle_cutout_total_usd=total_values[
                    "recessed_handle_cutout"
                ],
                total_usd=row_total,
            )
        )

    return ExtraAddonPricingSummary(
        pieces=tuple(results),
        total_usd=_money(order_total),
    )


def _empty_result() -> ExtraAddonPieceResult:
    return ExtraAddonPieceResult(
        applicable=False,
        selected_codes=(),
        double_unit_price_usd=0,
        double_total_usd=0,
        full_door_double_unit_price_usd=0,
        full_door_double_total_usd=0,
        liner_unit_price_usd=0,
        liner_total_usd=0,
        back_groove_unit_price_usd=0,
        back_groove_total_usd=0,
        recessed_handle_cutout_unit_price_usd=0,
        recessed_handle_cutout_total_usd=0,
        total_usd=0,
    )


def _finite_non_negative(value: float) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError) as error:
        raise ExtraAddonError("extra_addon_rate_invalid") from error
    if not math.isfinite(number) or number < 0:
        raise ExtraAddonError("extra_addon_rate_invalid")
    return number


def extra_double_text_flags(
    *,
    piece_type: str,
    extra_double: bool,
    extra_full_door_double: bool,
) -> dict[str, int]:
    """Return Extra double checkboxes that DXF/plan TEXT marks may copy.

    These flags are operational workshop marks, not prices. Regular/Special
    rows stay empty even if a checkbox leaked onto the row.
    """

    if str(piece_type or "").strip() != EXTRA_PIECE_TYPE:
        return {}
    flags: dict[str, int] = {}
    if extra_double:
        flags["extra_double"] = 1
    if extra_full_door_double:
        flags["extra_full_door_double"] = 1
    return flags


def extra_double_text_flags_by_source_no(rows: Iterable[Any]) -> dict[int, dict[str, int]]:
    flags: dict[int, dict[str, int]] = {}
    for index, row in enumerate(rows or [], start=1):
        attached = extra_double_text_flags(
            piece_type=str(_row_field(row, "piece_type", "Regular") or "Regular"),
            extra_double=_truthy_flag(_row_field(row, "extra_double", 0)),
            extra_full_door_double=_truthy_flag(
                _row_field(row, "extra_full_door_double", 0)
            ),
        )
        if attached:
            flags[index] = attached
    return flags


def apply_extra_double_text_flags_to_snapshot(
    snapshot: Any,
    rows: Iterable[Any],
) -> Any:
    """Copy Extra double checkboxes onto matching snapshot pieces for DXF TEXT."""

    if not isinstance(snapshot, dict):
        return snapshot
    flags = extra_double_text_flags_by_source_no(rows)
    if not flags:
        return snapshot
    for sheet in snapshot.get("sheets") or []:
        if not isinstance(sheet, dict):
            continue
        for piece in sheet.get("pieces") or []:
            if not isinstance(piece, dict):
                continue
            attached = flags.get(_source_piece_no(piece))
            if attached:
                piece.update(attached)
    return snapshot


def _row_field(row: Any, field: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(field, default)
    return getattr(row, field, default)


def _truthy_flag(value: Any) -> bool:
    if value in (None, "", False):
        return False
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return bool(value)


def _source_piece_no(piece: Mapping[str, Any]) -> int:
    try:
        source = int(piece.get("source_piece_no") or 0)
    except (TypeError, ValueError):
        source = 0
    if source >= 1:
        return source
    label = str(piece.get("label") or "").strip()
    head = label.split(".", 1)[0].strip()
    try:
        group = int(float(head))
    except (TypeError, ValueError):
        return 0
    return group if group >= 1 else 0


def _money(value: float) -> float:
    return round_value(value, 3)


__all__ = [
    "EXTRA_ADDON_CODES",
    "EXTRA_ADDON_FIELD_BY_CODE",
    "EXTRA_OVERLAY_KIND_BY_LAYER",
    "EXTRA_OVERLAY_LAYER_BY_KIND",
    "EXTRA_OVERLAY_LAYER_NAMES",
    "EXTRA_PIECE_TYPE",
    "FULL_DOOR_DOUBLE_CUT_MULTIPLIER",
    "ExtraAddonError",
    "ExtraAddonPieceInput",
    "ExtraAddonPieceResult",
    "ExtraAddonPricingSummary",
    "ExtraAddonRates",
    "apply_extra_double_text_flags_to_snapshot",
    "calculate_extra_addon_pricing",
    "extra_double_text_flags",
    "extra_double_text_flags_by_source_no",
    "extra_overlay_kind_for_layer",
    "extra_overlay_layer_for_kind",
    "physical_cut_quantity",
]
