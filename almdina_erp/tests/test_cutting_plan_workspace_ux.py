from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_JSON = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
PLAN_DOCTYPE_JSON = APP_ROOT / "almdina_erp" / "doctype" / "cutting_plan" / "cutting_plan.json"
CUTTING_PLAN = APP_ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
CONTENT_UX = CUTTING_PLAN / "door_cutting_order_plan_content_ux.js"
CONTEXT_UX = CUTTING_PLAN / "door_cutting_order_plan_context_actions_ux.js"
TABS_UX = CUTTING_PLAN / "door_cutting_order_plan_tabs_ux.js"


def _schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cut_execution_settings_live_on_cutting_plan_not_dco():
    order_fields = {row["fieldname"] for row in _schema(DOCTYPE_JSON)["fields"]}
    plan = _schema(PLAN_DOCTYPE_JSON)
    plan_order = plan["field_order"]

    for retired in ("kerf_mm", "trim_margin_mm", "cut_geometry_section", "cut_geometry_column"):
        assert retired not in order_fields

    settings_column = plan_order.index("settings_column")
    assert plan_order.index("board_section") < settings_column
    assert settings_column < plan_order.index("kerf_mm") < plan_order.index("working_section")
    assert settings_column < plan_order.index("trim_margin_mm") < plan_order.index("working_section")


def test_optimizer_settings_are_grouped_on_cutting_plan_and_actions_stay_on_dco_surface():
    order = _schema(DOCTYPE_JSON)
    order_fields = {row["fieldname"] for row in order["fields"]}
    plan = _schema(PLAN_DOCTYPE_JSON)
    plan_order = plan["field_order"]

    for retired in ("optimizer_section", "packing_mode", "cutting_machine_type", "optimization_time_limit_sec"):
        assert retired not in order_fields

    engine = plan_order.index("engine_section")
    board = plan_order.index("board_section")
    for fieldname in ("optimization_mode", "machine_type", "optimization_time_limit_sec"):
        assert engine < plan_order.index(fieldname) < board, fieldname

    assert order["field_order"].index("plan_actions_section") + 1 == order["field_order"].index("plan_control_actions")


def test_machine_type_is_canonical_read_only_and_legacy_result_container_is_removed():
    order = _schema(DOCTYPE_JSON)
    order_fields = {row["fieldname"]: row for row in order["fields"]}
    plan_fields = {row["fieldname"]: row for row in _schema(PLAN_DOCTYPE_JSON)["fields"]}

    assert "cutting_machine_type" not in order_fields
    assert plan_fields["machine_type"].get("default") == "Auto"
    assert plan_fields["machine_type"].get("read_only") == 1
    assert "plan_result_section" not in order_fields
    assert "plan_controls_intro" not in order_fields
    assert "plan_result_section" not in order["field_order"]
    assert "plan_controls_intro" not in order["field_order"]


def test_board_layout_is_not_prefaced_by_duplicate_measurement_summary_on_screen():
    js = CONTENT_UX.read_text(encoding="utf-8")
    assert ".dco-piece-groups" in js
    assert ".dco-summary-grid" in js
    assert "طريقة الترتيب:" in js
    assert "isDuplicatedHeader" in js
    assert ".remove()" in js


def test_plan_workspace_commands_are_contextual_to_the_active_plan():
    context = CONTEXT_UX.read_text(encoding="utf-8")
    tabs = TABS_UX.read_text(encoding="utf-8")

    assert 'class="dco-plan-context-actions-host"' in tabs
    assert "renderContextActions(frm, wrapper)" in tabs
    assert "frm.__almdina_active_plan_tab" in context
    assert "استبدال الخطة المعتمدة بخطة النظام" in context
    assert "استبدال الخطة المعتمدة بالخطة المرفوعة" in context
    assert "إلغاء اعتماد الخطة" in context
    assert "export_order_dxf(frm.doc.name, activeTab(frm))" in context
    assert "tabs.printActivePlan(frm)" in context
    assert "frappe.call" not in context
