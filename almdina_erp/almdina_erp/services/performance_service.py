from __future__ import annotations

from time import perf_counter
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.services.cutting_engine import choose_best_plan, expand_piece_groups
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
    """Benchmark the pure packing engine on a real order without saving anything."""
    require_any_role("Production Manager")
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")

    repeat_count = max(1, min(MAX_REPEATS, cint(repeats)))
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
    mode = packing_mode or order.packing_mode or "Auto"
    if board_w_cm <= 0 or board_h_cm <= 0:
        frappe.throw(_("Order has invalid usable board dimensions."))

    elapsed_ms: list[float] = []
    last_result: dict[str, Any] | None = None
    for _index in range(repeat_count):
        started = perf_counter()
        last_result = choose_best_plan(
            expanded,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mode,
        )
        elapsed_ms.append((perf_counter() - started) * 1000)

    assert last_result is not None
    average_ms = sum(elapsed_ms) / len(elapsed_ms)
    worst_ms = max(elapsed_ms)
    return {
        "order": order.name,
        "packing_mode_requested": mode,
        "method_selected": last_result.get("method_label"),
        "expanded_pieces": len(expanded),
        "repeats": repeat_count,
        "elapsed_ms": [round(value, 3) for value in elapsed_ms],
        "average_ms": round(average_ms, 3),
        "worst_ms": round(worst_ms, 3),
        "target_ms": 5000,
        "meets_target_on_this_run": worst_ms <= 5000,
        "required_boards": len(last_result.get("sheets") or []),
        "unplaced_count": len(last_result.get("unplaced") or []),
        "waste_area_m2": flt(last_result.get("waste_area_m2")),
    }
