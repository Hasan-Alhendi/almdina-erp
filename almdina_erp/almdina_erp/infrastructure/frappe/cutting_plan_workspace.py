from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    OptimizationOutcome,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.application.cutting.version import ENGINE_VERSION
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.catalog import DEFAULT_OPTIMIZATION_MODE_ID
from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    build_manufacturing_requirements,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    DEFAULT_KERF_MM,
    DEFAULT_MACHINE_TYPE,
    DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
    DEFAULT_PREFERRED_TRIM_MM,
    PlanSettings,
    PlanSettingsValidationError,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
from almdina_erp.almdina_erp.infrastructure.frappe.orders.cut_dimension_plan_adapter import (
    FrappeCutDimensionPlanAdapter,
)


def _board_dimensions_mm(order: Any) -> tuple[float, float]:
    width = flt(getattr(order, "full_board_width_mm", 0)) or (
        flt(getattr(order, "board_width_cm", 0)) * 10
    )
    length = flt(getattr(order, "full_board_length_mm", 0)) or (
        flt(getattr(order, "board_length_cm", 0)) * 10
    )
    return width, length


def _piece_rows(order: Any) -> tuple[dict[str, Any], ...]:
    return tuple(
        FrappeCutDimensionPlanAdapter.piece_row_as_dict(row)
        for row in (order.pieces or [])
    )


def _manufacturing_requirements(order: Any) -> dict[str, Any]:
    """Capture persisted cut requirements for the exact plan revision."""

    requirements: list[dict[str, Any]] = []
    for source_piece_no, row in enumerate(order.pieces or [], start=1):
        piece = FrappeCutDimensionPlanAdapter.piece_row_as_dict(row)
        for copy_no in range(1, cint(row.qty) + 1):
            requirements.append(
                {
                    "label": f"{source_piece_no}.{copy_no}",
                    "source_piece_no": source_piece_no,
                    "copy_no": copy_no,
                    "cut_width_cm": piece["width_cm"],
                    "cut_length_cm": piece["length_cm"],
                    "allow_rotation": bool(cint(row.allow_rotation)),
                    "piece_type": str(row.piece_type or "Regular"),
                }
            )
    return build_manufacturing_requirements(requirements)


def _numeric_or_default(value: Any, default: float) -> Any:
    return default if value is None else value


def _validated_plan_settings(plan: Any) -> PlanSettings:
    """Translate Frappe storage fields into the canonical PlanSettings contract."""

    try:
        return normalize_plan_settings(
            optimization_mode=(
                str(getattr(plan, "optimization_mode", None) or "").strip()
                or DEFAULT_OPTIMIZATION_MODE_ID
            ),
            machine_type=(
                str(getattr(plan, "machine_type", None) or "").strip()
                or DEFAULT_MACHINE_TYPE
            ),
            optimization_time_limit_sec=_numeric_or_default(
                getattr(plan, "optimization_time_limit_sec", None),
                DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
            ),
            kerf_mm=_numeric_or_default(
                getattr(plan, "kerf_mm", None),
                DEFAULT_KERF_MM,
            ),
            preferred_trim_mm=_numeric_or_default(
                getattr(plan, "trim_margin_mm", None),
                DEFAULT_PREFERRED_TRIM_MM,
            ),
        )
    except PlanSettingsValidationError:
        frappe.throw(_("إعدادات خطة القص الحالية غير صالحة."), frappe.ValidationError)
        raise AssertionError("unreachable")


def plan_input_fingerprint(order: Any, plan: Any) -> str:
    """Fingerprint only the order requirements and validated plan-owned settings."""

    width_mm, length_mm = _board_dimensions_mm(order)
    settings = _validated_plan_settings(plan)
    return fingerprint_payload(
        {
            "version": 1,
            "order": order.name,
            "order_revision": cint(getattr(order, "revision", 1)) or 1,
            "board": {
                "description": str(order.board_description or "").strip(),
                "width_mm": width_mm,
                "length_mm": length_mm,
            },
            "settings": {
                "optimization_mode": settings.optimization_mode,
                "machine_type": settings.machine_type,
                "time_limit_sec": settings.optimization_time_limit_sec,
                "kerf_mm": settings.kerf_mm,
                "trim_margin_mm": settings.preferred_trim_mm,
            },
            "pieces": list(_piece_rows(order)),
        }
    )


def calculate_system_plan(order: Any, plan: Any) -> OptimizationOutcome:
    """Calculate one Draft System plan without mutating Door Cutting Order.

    Door Cutting Order is only the source of customer requirements. Optimizer
    settings and every calculated plan artifact are owned by Cutting Plan.
    """

    width_mm, length_mm = _board_dimensions_mm(order)
    factory_settings = frappe.get_cached_doc("Almdina ERP Settings")
    plan_settings = _validated_plan_settings(plan)
    fingerprint = plan_input_fingerprint(order, plan)
    outcome = optimize_order_plan(
        OptimizeOrderPlanCommand(
            engine_version=ENGINE_VERSION,
            input_fingerprint=fingerprint,
            plan_settings=plan_settings,
            board=BoardGeometry(
                full_width_cm=width_mm / 10,
                full_length_cm=length_mm / 10,
                trim_cm=plan_settings.preferred_trim_mm / 10,
                kerf_cm=plan_settings.kerf_mm / 10,
            ),
            optimizer=OptimizerOptions(
                selected_mode=plan_settings.optimization_mode,
                machine_type=plan_settings.machine_type,
                time_limit_sec=plan_settings.optimization_time_limit_sec,
                exact_piece_limit=cint(factory_settings.optimal_search_piece_limit) or 40,
                min_remnant_width_cm=flt(factory_settings.min_remnant_width_mm) / 10,
                min_remnant_length_cm=flt(factory_settings.min_remnant_length_mm) / 10,
                min_remnant_area_m2=flt(factory_settings.min_remnant_area_m2),
            ),
            piece_rows=_piece_rows(order),
        ),
        engine=domain_cutting_engine,
    )
    apply_calculation_outcome(order, plan, outcome, fingerprint=fingerprint)
    return outcome


def _apply_snapshot(
    order: Any,
    plan: Any,
    snapshot: dict[str, Any],
    *,
    fingerprint: str,
    method_label_fallback: str = "",
    engine_version_fallback: str = "",
) -> None:
    snapshot = dict(snapshot)
    snapshot["manufacturing_requirements"] = _manufacturing_requirements(order)
    validation = snapshot.get("validation") or {}
    metrics = snapshot.get("industrial_metrics") or {}
    width_mm, length_mm = _board_dimensions_mm(order)

    plan.board_description = str(order.board_description or "").strip()
    plan.full_board_width_mm = width_mm
    plan.full_board_length_mm = length_mm
    plan.usable_board_width_mm = flt(snapshot.get("usable_board_width_cm")) * 10
    plan.usable_board_length_mm = flt(snapshot.get("usable_board_length_cm")) * 10
    plan.method_key = snapshot.get("method_key") or ""
    plan.method_label = snapshot.get("method_label") or method_label_fallback
    plan.ordering_strategy = snapshot.get("ordering_strategy") or ""
    plan.score = flt(snapshot.get("score"))
    plan.engine_version = snapshot.get("engine_version") or engine_version_fallback
    plan.attempts = cint(snapshot.get("attempts"))
    plan.solver_status = snapshot.get("solver_status") or ""
    plan.search_elapsed_sec = flt(snapshot.get("search_elapsed_sec"))
    plan.estimated_cut_count = cint(metrics.get("estimated_cut_count"))
    plan.estimated_cut_length_m = flt(metrics.get("estimated_cut_length_cm")) / 100
    plan.largest_reusable_free_area_m2 = flt(
        metrics.get("largest_reusable_free_area_m2")
    )
    plan.rotation_count = cint(metrics.get("rotation_count"))
    plan.validation_status = "Valid" if validation.get("is_valid") else "Invalid"
    plan.validation_errors = "\n".join(validation.get("errors") or [])
    plan.required_boards = len(snapshot.get("sheets") or [])
    plan.used_area_m2 = flt(snapshot.get("used_area_m2"))
    plan.total_source_area_m2 = flt(snapshot.get("total_board_area_m2"))
    plan.waste_area_m2 = flt(snapshot.get("waste_area_m2"))
    plan.waste_percent = (
        (plan.waste_area_m2 / plan.total_source_area_m2 * 100)
        if plan.total_source_area_m2
        else 0
    )
    plan.input_fingerprint = fingerprint
    plan.plan_needs_recalculation = 0
    plan.snapshot_json = frappe.as_json(snapshot)

    plan.set("sources", [])
    plan.set("placed_pieces", [])
    for sheet in snapshot.get("sheets") or []:
        sheet_no = cint(sheet.get("sheet_no"))
        source_width_mm = flt(
            sheet.get("full_width_cm") or snapshot.get("full_board_width_cm")
        ) * 10
        source_length_mm = flt(
            sheet.get("full_length_cm") or snapshot.get("full_board_length_cm")
        ) * 10
        usable_width_mm = flt(
            sheet.get("usable_width_cm")
            or sheet.get("w")
            or snapshot.get("usable_board_width_cm")
        ) * 10
        usable_length_mm = flt(
            sheet.get("usable_length_cm")
            or sheet.get("h")
            or snapshot.get("usable_board_length_cm")
        ) * 10
        source_area = flt(sheet.get("source_area_m2")) or (
            usable_width_mm * usable_length_mm / 1_000_000
        )
        used_area = sum(
            flt(piece.get("area_m2")) for piece in (sheet.get("pieces") or [])
        )
        plan.append(
            "sources",
            {
                "sheet_no": sheet_no,
                "source_type": "Full Board",
                "board_description": str(order.board_description or "").strip(),
                "full_width_mm": source_width_mm,
                "full_length_mm": source_length_mm,
                "usable_width_mm": usable_width_mm,
                "usable_length_mm": usable_length_mm,
                "source_area_m2": source_area,
                "used_area_m2": used_area,
                "waste_area_m2": max(0, source_area - used_area),
            },
        )
        for piece in sheet.get("pieces") or []:
            plan.append(
                "placed_pieces",
                {
                    "sheet_no": sheet_no,
                    "piece_id": piece.get("id"),
                    "piece_label": piece.get("label"),
                    "source_piece_no": cint(piece.get("source_piece_no")),
                    "copy_no": cint(piece.get("copy_no")),
                    "x_mm": flt(piece.get("x")) * 10,
                    "y_mm": flt(piece.get("y")) * 10,
                    "width_mm": flt(piece.get("w")) * 10,
                    "height_mm": flt(piece.get("h")) * 10,
                    "original_width_cm": flt(piece.get("original_w")),
                    "original_length_cm": flt(piece.get("original_h")),
                    "piece_type": piece.get("piece_type") or "Regular",
                    "clipped_corner_position": piece.get("clipped_corner_position") or "",
                    "clipped_corner_width_cm": flt(piece.get("clipped_corner_width_cm")),
                    "clipped_corner_length_cm": flt(piece.get("clipped_corner_length_cm")),
                    "special_shape_geometry_json": piece.get("special_shape_geometry_json") or "",
                    "rotated": 1 if piece.get("rotated") else 0,
                    "edge_long_right": 1 if piece.get("edge_long_right") else 0,
                    "edge_long_left": 1 if piece.get("edge_long_left") else 0,
                    "edge_width_top": 1 if piece.get("edge_width_top") else 0,
                    "edge_width_bottom": 1 if piece.get("edge_width_bottom") else 0,
                    "edge_type": piece.get("edge_type") or "",
                    "notes": piece.get("notes") or "",
                },
            )


def apply_calculation_outcome(
    order: Any,
    plan: Any,
    outcome: OptimizationOutcome,
    *,
    fingerprint: str,
) -> None:
    snapshot = sanitize_plan_snapshot(outcome.snapshot)
    _apply_snapshot(
        order,
        plan,
        snapshot,
        fingerprint=fingerprint,
        method_label_fallback=outcome.method_label or "",
        engine_version_fallback=ENGINE_VERSION,
    )


def apply_validated_dxf_snapshot(
    order: Any,
    plan: Any,
    raw_snapshot: dict[str, Any],
) -> None:
    """Map one already-validated DXF snapshot into the Draft Cutting Plan."""

    snapshot = sanitize_plan_snapshot(raw_snapshot)
    validation = snapshot.get("validation") or {}
    if not snapshot.get("sheets") or not validation.get("is_valid"):
        frappe.throw(
            _("لا يمكن حفظ ملف DXF كخطة قص قبل نجاح التحقق الهندسي."),
            frappe.ValidationError,
        )

    fingerprint = plan_input_fingerprint(order, plan)
    _apply_snapshot(
        order,
        plan,
        snapshot,
        fingerprint=fingerprint,
        method_label_fallback="DXF",
        engine_version_fallback="DXF Import",
    )


__all__ = [
    "apply_calculation_outcome",
    "apply_validated_dxf_snapshot",
    "calculate_system_plan",
    "plan_input_fingerprint",
]
