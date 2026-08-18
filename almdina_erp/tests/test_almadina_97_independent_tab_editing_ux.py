from __future__ import annotations

import json
import re
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DCO_SCHEMA = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
PLAN_SCHEMA = APP_ROOT / "almdina_erp" / "doctype" / "cutting_plan" / "cutting_plan.json"
DCO_JS = APP_ROOT / "public" / "js" / "door_cutting_order"
PLAN_EDIT = DCO_JS / "cutting_plan" / "door_cutting_order_plan_edit_session_ux.js"
PLAN_API = DCO_JS / "cutting_plan" / "door_cutting_order_plan_workspace_api.js"
COST_EDIT = DCO_JS / "costing" / "door_cutting_order_cost_edit_session_ux.js"
ORDER_EDIT = DCO_JS / "core" / "door_cutting_order_revision_ux.js"
PLAN_SERVICE = APP_ROOT / "almdina_erp" / "services" / "plan_settings_edit_service.py"

PLAN_FIELDS = {
    "packing_mode",
    "cutting_machine_type",
    "kerf_mm",
    "trim_margin_mm",
    "optimization_time_limit_sec",
}
COST_FIELDS = {"board_rate_usd", "cutting_cost_per_board_usd"}
DEFERRED_BOARD_FIELDS = {"board_length_cm", "board_width_cm"}


def _schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _js_constant_fields(source: str, constant: str) -> set[str]:
    match = re.search(
        rf"const\s+{re.escape(constant)}\s*=\s*Object\.freeze\(\[(.*?)\]\);",
        source,
        re.DOTALL,
    )
    assert match, f"missing JavaScript field contract: {constant}"
    return set(re.findall(r'"([a-z0-9_]+)"', match.group(1)))


def _plain_js_array_fields(source: str, constant: str) -> set[str]:
    match = re.search(
        rf"const\s+{re.escape(constant)}\s*=\s*\[(.*?)\];",
        source,
        re.DOTALL,
    )
    assert match, f"missing JavaScript field contract: {constant}"
    return set(re.findall(r'"([a-z0-9_]+)"', match.group(1)))


def test_plan_edit_owns_only_optimizer_settings_and_excludes_deferred_board_dimensions():
    source = PLAN_EDIT.read_text(encoding="utf-8")
    fields = _js_constant_fields(source, "PLAN_SETTING_FIELDS")

    assert fields == PLAN_FIELDS
    assert fields.isdisjoint(COST_FIELDS)
    assert fields.isdisjoint(DEFERRED_BOARD_FIELDS)
    for forbidden in ("pieces", "default_edge_type", "edge_color"):
        assert forbidden not in fields


def test_plan_editor_is_detached_from_retired_dco_plan_fields():
    source = PLAN_EDIT.read_text(encoding="utf-8")

    assert "dco-plan-settings-editor" in source
    assert "data-almdina-plan-setting" in source
    assert "store.patchDraft" in source
    assert "validateDraft" in source
    assert "AlmdinaWorkspaceFieldEditor" not in source
    assert "fieldEditor.mount(frm, PLAN_SETTING_FIELDS" not in source
    assert 'frm.fields_dict[fieldname]' not in source


def test_plan_save_and_cancel_are_workspace_scoped_without_broad_order_save():
    source = PLAN_EDIT.read_text(encoding="utf-8")
    api_source = PLAN_API.read_text(encoding="utf-8")

    assert "store.cancelEdit()" in source
    assert "api.saveSettings(frm.doc.name, state.draft || {})" in source
    assert "owner.load(frm, { force: true })" in source
    assert "frm.save(" not in source
    assert "order.save(" not in source

    for fieldname in PLAN_FIELDS:
        assert fieldname in api_source
    for forbidden in COST_FIELDS | DEFERRED_BOARD_FIELDS | {"pieces", "edge_color"}:
        assert forbidden not in api_source


def test_plan_backend_validates_workspace_aliases_against_canonical_cutting_plan_schema():
    source = PLAN_SERVICE.read_text(encoding="utf-8")

    assert 'frappe.get_meta("Cutting Plan")' in source
    assert '"packing_mode": "optimization_mode"' in source
    assert '"cutting_machine_type": "machine_type"' in source
    assert "_allowed_select_values(plan_meta, fieldname)" in source
    assert "doc.meta.get_field(fieldname)" not in source
    assert "save_system_plan_settings(doc, updates)" in source
    assert "doc.save(" not in source


def test_cost_edit_scope_remains_independent_from_plan_scope():
    source = COST_EDIT.read_text(encoding="utf-8")
    fields = _js_constant_fields(source, "COST_SETTING_FIELDS")

    assert fields == COST_FIELDS
    assert fields.isdisjoint(PLAN_FIELDS)
    assert "store.cancelEdit()" in source
    assert "api.saveSettings(frm.doc.name, state.draft || {})" in source
    assert 'field.df[STATUS_KEY] = "Read"' in source
    assert "frm.save(" not in source


def test_board_dimensions_are_explicitly_deferred_and_remain_order_owned():
    dco_fields = {row["fieldname"] for row in _schema(DCO_SCHEMA)["fields"]}
    order_source = ORDER_EDIT.read_text(encoding="utf-8")
    order_fields = _plain_js_array_fields(order_source, "ORDER_INPUT_FIELDS")
    plan_source = PLAN_EDIT.read_text(encoding="utf-8")
    plan_fields = _js_constant_fields(plan_source, "PLAN_SETTING_FIELDS")

    assert DEFERRED_BOARD_FIELDS <= dco_fields
    assert DEFERRED_BOARD_FIELDS <= order_fields
    assert DEFERRED_BOARD_FIELDS.isdisjoint(plan_fields)
    assert order_fields.isdisjoint(PLAN_FIELDS)
    assert order_fields.isdisjoint(COST_FIELDS)
    assert "ORDER_CUT_GEOMETRY_FIELDS" not in order_source


def test_retired_plan_settings_are_not_restored_to_dco_schema():
    dco_fields = {row["fieldname"] for row in _schema(DCO_SCHEMA)["fields"]}
    plan_fields = {row["fieldname"] for row in _schema(PLAN_SCHEMA)["fields"]}

    assert PLAN_FIELDS.isdisjoint(dco_fields)
    assert {"optimization_mode", "machine_type", "kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"} <= plan_fields
