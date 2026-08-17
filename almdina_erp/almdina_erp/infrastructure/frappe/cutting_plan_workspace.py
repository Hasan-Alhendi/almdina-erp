from __future__ import annotations

from typing import Any

import frappe
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


def _input_fingerprint(order: Any, plan: Any) -> str:
    width_mm, length_mm = _board_dimensions_mm(order)
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
                "optimization_mode": str(plan.optimization_mode or "Auto Pro"),
                "machine_type": str(plan.machine_type or "Auto"),
                "time_limit_sec": flt(plan.optimization_time_limit_sec),
                "kerf_mm": flt(plan.kerf_mm),
                "trim_margin_mm": flt(plan.trim_margin_mm),
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
    settings = frappe.get_cached_doc("Almdina ERP Settings")
    fingerprint = _input_fingerprint(order, plan)
    outcome = optimize_order_plan(
        OptimizeOrderPlanCommand(
            engine_version=ENGINE_VERSION,
            input_fingerprint=fingerprint,
            board=BoardGeometry(
                full_width_cm=width_mm / 10,
                full_length_cm=length_mm / 10,
                trim_cm=flt(plan.trim_margin_mm) / 10,
                kerf_cm=flt(plan.kerf_mm) / 10,
            ),
            optimizer=OptimizerOptions(
                selected_mode=str(plan.optimization_mode or "Auto Pro"),
                machine_type=str(plan.machine_type or "Auto"),
                time_limit_sec=flt(plan.optimization_time_limit_sec) or 10,
                exact_piece_limit=cint(settings.optimal_search_piece_limit) or 40,
                min_remnant_width_cm=flt(settings.min_remnant_width_mm) / 10,
                min_remnant_length_cm=flt(settings.min_remnant_length_mm) / 10,
                min_remnant_area_m2=flt(settings.min_remnant_area_m2),
            ),
            piece_rows=_piece_rows(order),
        ),
        engine=domain_cutting_engine,
    )
    apply_calculation_outcome(order, plan, outcome, fingerprint=fingerprint)
    return outcome


def apply_calculation_outcome(
    order: Any,
    plan: Any,
    outcome: OptimizationOutcome,
    *,
    fingerprint: str,
) -> None:
    snapshot = sanitize_plan_snapshot(outcome.snapshot)
    validation = snapshot.get("validation") or {}
    metrics = snapshot.get("industrial_metrics") or {}
    width_mm, length_mm = _board_dimensions_mm(order)

    plan.board_description = str(order.board_description or "").strip()
    plan.full_board_width_mm = width_mm
    plan.full_board_length_mm = length_mm
    plan.usable_board_width_mm = flt(snapshot.get("usable_board_width_cm")) * 10
    plan.usable_board_length_mm = flt(snapshot.get("usable_board_length_cm")) * 10
    plan.method_key = snapshot.get("method_key") or ""
    plan.method_label = snapshot.get("method_label") or outcome.method_label or ""
    plan.ordering_strategy = snapshot.get("ordering_strategy") or ""
    plan.score = flt(snapshot.get("score"))
    plan.engine_version = snapshot.get("engine_version") or ENGINE_VERSION
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


__all__ = ["apply_calculation_outcome", "calculate_system_plan"]
