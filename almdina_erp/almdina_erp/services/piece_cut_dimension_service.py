from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable

from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    CutDimensionError,
    CutDimensionResult,
    SIDE_LONG_LEFT,
    SIDE_LONG_RIGHT,
    SIDE_WIDTH_BOTTOM,
    SIDE_WIDTH_TOP,
    calculate_cut_dimensions,
    decimal_value,
)

_SIDE_CONFIG = {
    SIDE_LONG_RIGHT: (
        "edge_long_right",
        "edge_long_right_type_override",
        "الطول الأيمن",
    ),
    SIDE_LONG_LEFT: (
        "edge_long_left",
        "edge_long_left_type_override",
        "الطول الأيسر",
    ),
    SIDE_WIDTH_TOP: (
        "edge_width_top",
        "edge_width_top_type_override",
        "العرض العلوي",
    ),
    SIDE_WIDTH_BOTTOM: (
        "edge_width_bottom",
        "edge_width_bottom_type_override",
        "العرض السفلي",
    ),
}


@dataclass(frozen=True)
class OrderPieceCutSpec:
    row_index: int
    finished_width_cm: Decimal
    finished_length_cm: Decimal
    cut_width_cm: Decimal
    cut_length_cm: Decimal
    width_deduction_mm: Decimal
    length_deduction_mm: Decimal
    allow_rotation: int
    piece_type: str
    qty: int
    side_profiles: tuple[dict[str, Any], ...]


def _is_selected(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no"}
    return bool(value)


def _effective_type(order: Any, row: Any, side: str) -> str:
    selected_field, override_field, _ = _SIDE_CONFIG[side]
    if not _is_selected(getattr(row, selected_field, 0)):
        return ""
    override = str(getattr(row, override_field, "") or "").strip()
    return override or str(getattr(order, "default_edge_type", "") or "").strip()


def _default_profile_loader(names: Iterable[str]) -> dict[str, dict[str, Any]]:
    import frappe

    names = sorted({str(name).strip() for name in names if str(name).strip()})
    if not names:
        return {}
    rows = frappe.get_all(
        "Edge Banding Type",
        filters={"name": ["in", names]},
        fields=["name", "thickness_mm", "disabled"],
    )
    return {
        str(row.name): {
            "name": str(row.name),
            "thickness_mm": row.thickness_mm,
            "disabled": row.disabled,
        }
        for row in rows
    }


def build_order_piece_cut_specs(
    order: Any,
    *,
    profile_loader: Callable[[Iterable[str]], dict[str, dict[str, Any]]] | None = None,
) -> list[OrderPieceCutSpec]:
    loader = profile_loader or _default_profile_loader
    rows = list(getattr(order, "pieces", None) or [])

    effective_names: set[str] = set()
    for row in rows:
        for side in _SIDE_CONFIG:
            edge_type = _effective_type(order, row, side)
            if edge_type:
                effective_names.add(edge_type)

    profiles = loader(effective_names)
    specs: list[OrderPieceCutSpec] = []
    errors: list[str] = []

    for row_index, row in enumerate(rows, start=1):
        side_thickness: dict[str, Decimal] = {}
        side_profiles: list[dict[str, Any]] = []
        row_errors: list[str] = []

        for side, (selected_field, _override_field, side_label) in _SIDE_CONFIG.items():
            if not _is_selected(getattr(row, selected_field, 0)):
                side_thickness[side] = Decimal("0")
                continue

            edge_type = _effective_type(order, row, side)
            if not edge_type:
                row_errors.append(
                    f"الدرفة رقم {row_index}: ضلع {side_label} عليه قشاط لكن لم يتم تحديد نوع القشاط."
                )
                side_thickness[side] = Decimal("0")
                continue

            profile = profiles.get(edge_type)
            if not profile:
                row_errors.append(
                    f"الدرفة رقم {row_index}: نوع القشاط «{edge_type}» المستخدم على ضلع {side_label} غير موجود."
                )
                side_thickness[side] = Decimal("0")
                continue
            if _is_selected(profile.get("disabled")):
                row_errors.append(
                    f"الدرفة رقم {row_index}: نوع القشاط «{edge_type}» المستخدم على ضلع {side_label} معطّل."
                )
                side_thickness[side] = Decimal("0")
                continue

            try:
                thickness = decimal_value(
                    profile.get("thickness_mm"),
                    label=f"سماكة القشاط «{edge_type}»",
                )
            except CutDimensionError as exc:
                row_errors.append(f"الدرفة رقم {row_index}: {exc}")
                side_thickness[side] = Decimal("0")
                continue
            if thickness < 0:
                row_errors.append(
                    f"الدرفة رقم {row_index}: سماكة القشاط «{edge_type}» لا يمكن أن تكون سالبة."
                )
                side_thickness[side] = Decimal("0")
                continue

            side_thickness[side] = thickness
            side_profiles.append(
                {
                    "side": side,
                    "side_label": side_label,
                    "edge_type": edge_type,
                    "thickness_mm": thickness,
                }
            )

        if row_errors:
            errors.extend(row_errors)
            continue

        try:
            result: CutDimensionResult = calculate_cut_dimensions(
                finished_width_cm=getattr(row, "width_cm", 0),
                finished_length_cm=getattr(row, "length_cm", 0),
                side_thickness_mm=side_thickness,
            )
        except CutDimensionError as exc:
            errors.append(f"الدرفة رقم {row_index}: {exc}")
            continue

        qty = int(getattr(row, "qty", 0) or 0)
        if qty <= 0:
            errors.append(f"الدرفة رقم {row_index}: الكمية يجب أن تكون أكبر من صفر.")
            continue

        specs.append(
            OrderPieceCutSpec(
                row_index=row_index,
                finished_width_cm=result.finished_width_cm,
                finished_length_cm=result.finished_length_cm,
                cut_width_cm=result.cut_width_cm,
                cut_length_cm=result.cut_length_cm,
                width_deduction_mm=result.width_deduction_mm,
                length_deduction_mm=result.length_deduction_mm,
                allow_rotation=1 if _is_selected(getattr(row, "allow_rotation", 0)) else 0,
                piece_type=str(getattr(row, "piece_type", "") or "Regular"),
                qty=qty,
                side_profiles=tuple(side_profiles),
            )
        )

    if errors:
        raise CutDimensionError(errors)
    return specs


def sync_order_cut_dimension_fields(
    order: Any,
    specs: list[OrderPieceCutSpec] | None = None,
) -> list[OrderPieceCutSpec]:
    """Persist only derived raw-cut fields; finished dimensions are never changed."""
    specs = specs or build_order_piece_cut_specs(order)
    by_index = {spec.row_index: spec for spec in specs}
    for row_index, row in enumerate(getattr(order, "pieces", None) or [], start=1):
        spec = by_index[row_index]
        row.cut_width_cm = float(spec.cut_width_cm)
        row.cut_length_cm = float(spec.cut_length_cm)
        row.cut_size_label = f"{spec.cut_width_cm} × {spec.cut_length_cm}"
    return specs
