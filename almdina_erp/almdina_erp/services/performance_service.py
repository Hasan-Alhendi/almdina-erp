from __future__ import annotations

from time import perf_counter
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.services.advanced_cutting_optimizer import optimize_plan
from almdina_erp.almdina_erp.services.cutting_engine import expand_piece_groups
from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


MAX_EXPANDED_PIECES = 200
MAX_REPEATS = 5


def _piece_rows(order: Any) -> list[dict[str, Any]]:
    return [
        {
            "width_cm": flt(row.width_cm),
            "length_cm": flt(row.length_cm),
            "qty": cint(row.qty),
            "allow_rotation": cint(row.allow_rotation),
            "edge_long_right": cint(row.edge_long_right),
            "edge_long_left": cint(row.edge_long_left),
            "edge_width_top": cint(row.edge_width_top),
            "edge_width_bottom": cint(row.edge_width_bottom),
            "edge_type": row.edge_type or "",
            "edge_rate_usd": flt(row.edge_rate_usd),
            "edge_cost_usd": flt(row.edge_cost_usd),
            "notes": row.notes or "",
        }
        for row in (order.pieces or [])
    ]


@frappe.whitelist()
def benchmark_order_cutting_engine(
    order_name: str,
    repeats: int = 3,
    packing_mode: str | None = None,
) -> dict[str, Any]:
    """Benchmark the optimizer on a real order without saving or moving stock."""
    require_any_role("Production Manager")
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")

    mode = packing_mode or order.packing_mode or "Auto Pro"
    requested_repeats = max(1, min(MAX_REPEATS, cint(repeats)))
    repeat_count = 1 if mode in {"Deep Search", "Optimal Search"} else requested_repeats
    expanded = expand_piece_groups(_piece_rows(order))
    if not expanded:
        frappe.throw(_("Order has no valid expanded pieces to benchmark."))
    if len(expanded) > MAX_EXPANDED_PIECES:
        frappe.throw(
            _("Benchmark is limited to {0} expanded pieces; this order has {1}.").format(
                MAX_EXPANDED_PIECES,
                len(expanded),
            )
        )

    trim_cm = flt(order.trim_margin_mm) / 10
    board_w_cm = flt(order.full_board_width_mm) / 10 - (trim_cm * 2)
    board_h_cm = flt(order.full_board_length_mm) / 10 - (trim_cm * 2)
    kerf_cm = flt(order.kerf_mm) / 10
    if board_w_cm <= 0 or board_h_cm <= 0:
        frappe.throw(_("Order has invalid usable board dimensions."))

    settings = frappe.get_single("Almdina ERP Settings")
    elapsed_ms: list[float] = []
    last_result: dict[str, Any] | None = None
    for _index in range(repeat_count):
        started = perf_counter()
        last_result = optimize_plan(
            expanded,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            selected_mode=mode,
            machine_type=order.cutting_machine_type or settings.default_cutting_machine_type or "Auto",
            time_limit_sec=flt(order.optimization_time_limit_sec) or flt(settings.default_optimization_time_limit_sec) or 10,
            exact_piece_limit=cint(settings.optimal_search_piece_limit) or 40,
            min_remnant_width_cm=flt(settings.min_remnant_width_mm) / 10,
            min_remnant_length_cm=flt(settings.min_remnant_length_mm) / 10,
            min_remnant_area_m2=flt(settings.min_remnant_area_m2),
        )
        elapsed_ms.append((perf_counter() - started) * 1000)

    assert last_result is not None
    average_ms = sum(elapsed_ms) / len(elapsed_ms)
    worst_ms = max(elapsed_ms)
    metrics = last_result.get("industrial_metrics") or {}
    target_ms = 5000 if mode in {"Auto", "Auto Pro"} else (flt(order.optimization_time_limit_sec) or 10) * 1000 + 1500
    return {
        "order": order.name,
        "packing_mode_requested": mode,
        "machine_type": order.cutting_machine_type or "Auto",
        "method_selected": last_result.get("method_label"),
        "solver_status": last_result.get("solver_status") or "",
        "optimization_attempts": cint(last_result.get("attempts")),
        "expanded_pieces": len(expanded),
        "repeats": repeat_count,
        "elapsed_ms": [round(value, 3) for value in elapsed_ms],
        "average_ms": round(average_ms, 3),
        "worst_ms": round(worst_ms, 3),
        "target_ms": target_ms,
        "meets_target_on_this_run": worst_ms <= target_ms,
        "required_boards": len(last_result.get("sheets") or []),
        "unplaced_count": len(last_result.get("unplaced") or []),
        "waste_area_m2": flt(last_result.get("waste_area_m2")),
        "largest_reusable_free_area_m2": flt(metrics.get("largest_reusable_free_area_m2")),
        "estimated_cut_count": cint(metrics.get("estimated_cut_count")),
        "estimated_cut_length_m": flt(metrics.get("estimated_cut_length_cm")) / 100,
        "rotation_count": cint(metrics.get("rotation_count")),
    }
