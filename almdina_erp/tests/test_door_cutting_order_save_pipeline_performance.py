from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from almdina_erp.almdina_erp.application.orders.save_order import SaveDoorCuttingOrder
from almdina_erp.almdina_erp.infrastructure.frappe.orders.save_gateway import (
    FrappeDoorCuttingOrderSaveGateway,
)
from almdina_erp.almdina_erp.services.cutting_domain import (
    MaterialSettings,
    OptimizerSettings,
    PlanOptimizerSettings,
    PlanPieceInput,
    PlanRequest,
)


ROOT = Path(__file__).resolve().parents[1]
SAVE_RENDER_UX = ROOT / "public" / "js" / "door_cutting_order_save_render_performance_ux.js"
HOOKS = ROOT / "hooks.py"


def _order(**changes):
    values = {
        "docstatus": 0,
        "status": "Draft",
        "board_description": "MDF 18mm White",
        "board_length_cm": 244,
        "board_width_cm": 122,
        "kerf_mm": 3,
        "trim_margin_mm": 5,
        "packing_mode": "Auto Pro",
        "cutting_machine_type": "Auto",
        "optimization_time_limit_sec": 10,
        "pieces": [],
        "plan_needs_recalculation": 0,
        "modified": "2026-07-29 12:00:00",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _detail(**changes):
    values = {
        "name": "ROW-1",
        "idx": 1,
        "piece_no": 1,
        "width_cm": 60,
        "length_cm": 80,
        "qty": 1,
        "allow_rotation": 1,
        "piece_type": "Regular",
        "clipped_corner_position": "Top Right",
        "clipped_corner_width_cm": 0,
        "clipped_corner_length_cm": 0,
        "special_shape_geometry_json": "",
        "special_shape_drawing_json": "",
    }
    values.update(changes)
    return SimpleNamespace(**values)


class _Gateway:
    def __init__(self):
        self.calls = []

    def validate(self):
        self.calls.append("validate")

    def normalize(self):
        self.calls.append("normalize")

    def apply_cut_dimensions(self):
        self.calls.append("cut_dimensions")

    def calculate_cost(self):
        self.calls.append("cost")

    def update_workflow(self):
        self.calls.append("workflow")

    def update_revision(self):
        self.calls.append("revision")

    def mark_plan_stale(self):
        self.calls.append("stale")



def test_save_pipeline_skips_heavy_optimizer_but_keeps_core_business_steps():
    gateway = _Gateway()
    SaveDoorCuttingOrder(gateway).execute()
    assert gateway.calls == [
        "validate",
        "normalize",
        "cut_dimensions",
        "cost",
        "workflow",
        "revision",
        "stale",
    ]


def test_plan_request_preserves_clipped_corner_geometry_for_explicit_recalculation():
    order = _order(pieces=[_detail(piece_type="Clipped Corner", clipped_corner_width_cm=12, clipped_corner_length_cm=18)])
    gateway = FrappeDoorCuttingOrderSaveGateway(order)
    request = PlanRequest(
        material=MaterialSettings(
            board_width_mm=1220,
            board_length_mm=2440,
            kerf_mm=3,
            trim_margin_mm=5,
            packing_mode="Auto Pro",
            machine_type="Auto",
            time_limit_sec=10,
        ),
        optimizer=PlanOptimizerSettings(
            exact_piece_limit=40,
            min_remnant_width_mm=0,
            min_remnant_length_mm=0,
            min_remnant_area_m2=0,
        ),
        pieces=[
            PlanPieceInput(
                index=1,
                width_cm=60,
                length_cm=80,
                qty=1,
                allow_rotation=1,
                piece_type="Clipped Corner",
                clipped_corner_position="Top Right",
                clipped_corner_width_cm=12,
                clipped_corner_length_cm=18,
            )
        ],
    )
    payload = request.as_dict()
    piece = payload["pieces"][0]
    assert piece["piece_type"] == "Clipped Corner"
    assert piece["clipped_corner_position"] == "Top Right"
    assert piece["clipped_corner_width_cm"] == 12
    assert piece["clipped_corner_length_cm"] == 18


def test_post_save_dom_layer_reuses_unchanged_measurement_table():
    source = SAVE_RENDER_UX.read_text(encoding="utf-8")
    assert "sameRows(frm, root)" in source
    assert "syncExistingTable(frm, root)" in source
    assert "return originalHtml.apply(this, arguments)" in source
    assert "dco-fast-entry-shell" in source
    assert "wrapper._dcoFastHtmlGuardForm = frm" in source
    assert "root._dcoDeferredRenderForm = frm" in source
    assert "window.AlmdinaOrderCostUX.render(currentFrm)" in source


def test_post_save_dom_layer_loads_after_table_and_invoice_renderers():
    hooks = HOOKS.read_text(encoding="utf-8")
    operator = '"public/js/door_cutting_order_operator_ux.js"'
    table = '"public/js/door_cutting_order_table_performance_ux.js"'
    invoice = '"public/js/door_cutting_order_cost_invoice_ux.js"'
    performance = '"public/js/door_cutting_order_save_render_performance_ux.js"'
    assert hooks.index(operator) < hooks.index(performance)
    assert hooks.index(table) < hooks.index(performance)
    assert hooks.index(invoice) < hooks.index(performance)
