from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_JSON = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
PLAN_UX = APP_ROOT / "public" / "js" / "door_cutting_order_plan_ux.js"
CONTENT_UX = APP_ROOT / "public" / "js" / "door_cutting_order_plan_content_ux.js"


def _field_order() -> list[str]:
    return json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))["field_order"]


def test_cut_execution_fields_are_grouped_together():
    order = _field_order()
    section = order.index("cut_geometry_section")
    optimizer = order.index("optimizer_section")
    assert section < order.index("kerf_mm") < optimizer
    assert section < order.index("trim_margin_mm") < optimizer
    assert order.index("cut_geometry_column") < order.index("trim_margin_mm")


def test_optimizer_controls_and_actions_are_one_group():
    order = _field_order()
    section = order.index("optimizer_section")
    result = order.index("plan_result_section")
    for fieldname in (
        "packing_mode",
        "cutting_machine_type",
        "optimization_time_limit_sec",
        "plan_control_actions",
    ):
        assert section < order.index(fieldname) < result, fieldname


def test_board_layout_is_not_prefaced_by_duplicate_measurement_summary_on_screen():
    js = CONTENT_UX.read_text(encoding="utf-8")
    assert ".dco-piece-groups" in js
    assert ".dco-summary-grid" in js
    assert "طريقة الترتيب:" in js
    assert "isDuplicatedHeader" in js
    assert ".remove()" in js


def test_plan_workspace_uses_distinct_visual_groups():
    js = PLAN_UX.read_text(encoding="utf-8")
    for class_name in (
        "dco-cut-settings-card",
        "dco-optimizer-card",
        "dco-result-card",
        "dco-layout-card",
    ):
        assert class_name in js
    assert "أوامر خطة القص" in js
    assert "إعادة الحساب بالإعدادات الحالية" in js
