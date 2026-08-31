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
PAGE_EDIT = DCO_JS / "core" / "door_cutting_order_page_edit_action_ux.js"
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


def test_plan_backend_validates_workspace_aliases_against_domain_contracts():
    source = PLAN_SERVICE.read_text(encoding="utf-8")

    assert 'frappe.get_meta("Cutting Plan")' in source
    assert '"packing_mode": "optimization_mode"' in source
    assert '"cutting_machine_type": "machine_type"' in source
    assert "normalize_plan_settings(" in source
    assert "canonical_default_plan_settings()" in source
    assert "_allowed_select_values" not in source
    assert "doc.meta.get_field(fieldname)" not in source
    assert "save_system_plan_settings(doc, updates)" in source
    assert "doc.save(" not in source


def test_cost_edit_scope_remains_independent_from_plan_scope():
    source = COST_EDIT.read_text(encoding="utf-8")
    fields = _js_constant_fields(source, "COST_SETTING_FIELDS")

    assert fields == COST_FIELDS
    assert fields.isdisjoint(PLAN_FIELDS)
    assert "store.cancelEdit()" in source
    assert "const captured = captureCostSettings(frm, state.draft || {});" in source
    assert "store.replaceDraft(payload);" in source
    assert "api.saveSettings(frm.doc.name, payload)" in source
    assert "owner.commit(frm, saved);" in source
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


def test_each_tab_has_its_own_local_edit_save_cancel_toolbar():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    assert 'order_tab: "order"' in source
    assert 'results_tab: "plan"' in source
    assert 'cost_tab: "cost"' in source
    assert "function toolbarSlotHost(frm)" in source
    assert "function ensureToolbarSlot(frm)" in source
    assert "slot.replaceChildren(toolbar)" in source
    assert 'const EDIT_LABEL = "تعديل"' in source
    assert 'const SAVE_LABEL = "حفظ"' in source
    assert 'const CANCEL_LABEL = "إلغاء"' in source
    assert 'data-almdina-tab-edit-kind' in source
    assert 'dco-tab-edit-start' in source
    assert 'dco-tab-edit-save' in source
    assert 'dco-tab-edit-cancel' in source
    assert "renderToolbar(frm, activeKind(frm));" in source


def test_persisted_dco_no_longer_uses_global_primary_action_for_tab_editing():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    assert ".page-actions .primary-action" in source
    assert "display:none !important" in source
    assert "sync(frm);" in source
    assert "Synchronous sync prevents the legacy global primary action" in source
    assert "set_primary_action" not in source
    assert "clear_primary_action" not in source
    assert "data-almdina-context-edit-mode" not in source
    assert "dco-plan-settings-edit-toolbar { display:none" not in source


def test_tab_local_actions_delegate_to_existing_independent_session_owners():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    assert "window.AlmdinaOrderRevisionUX" in source
    assert "window.AlmdinaPlanEditSessionUX" in source
    assert "window.AlmdinaCostEditSessionUX" in source
    assert "api.enterEditSession(frm)" in source
    assert "api.startEditing(frm)" in source
    assert "api.commitEditSession(frm)" in source
    assert "api.saveEditing(frm)" in source
    assert "api.cancelEditing(frm)" in source
    assert "cancelOrder(frm)" in source
    assert "activeEditingKind(frm)" in source
    assert "احفظ أو ألغِ التعديل المفتوح في القسم الآخر أولًا" in source
    assert "frappe.call" not in source


def test_tab_local_edit_buttons_fail_closed_against_each_session_permission_policy():
    page_source = PAGE_EDIT.read_text(encoding="utf-8")
    plan_source = PLAN_EDIT.read_text(encoding="utf-8")
    cost_source = COST_EDIT.read_text(encoding="utf-8")
    order_source = ORDER_EDIT.read_text(encoding="utf-8")

    assert "permissionsResolved() && canEdit(frm, kind)" in page_source
    assert 'can(frm, "edit_optimizer_settings")' in plan_source
    assert 'can(frm, "view_costs") && can(frm, "edit_cost_settings")' in cost_source
    assert 'can(frm, "approve_special_price") || can(frm, "edit_special_price")' in cost_source
    assert "canEditCostSettings(frm) || canEditPiecePrices(frm)" in cost_source
    assert 'typeof api.canEditCostWorkspace === "function"' in page_source
    assert 'can(frm, "edit_order")' in order_source
    assert "لا تملك صلاحية تعديل إعدادات خطة القص" in page_source
    assert "تعديل التكلفة أو تسعير الدرف الخاصة" in page_source


def test_plan_read_mode_restores_canonical_settings_without_restoring_dco_fields():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    assert "dco-plan-settings-readonly" in source
    assert "data-almdina-plan-settings-readonly" in source
    assert "window.AlmdinaPlanWorkspaceState" in source
    assert 'owner.activePlan(frm, "System")' in source
    assert "const settings = row.settings || {}" in source
    for label in (
        "الخوارزمية",
        "آلة القص",
        "سماكة القص Kerf",
        "هامش التشذيب",
        "مهلة التحسين",
    ):
        assert label in source
    assert "board_length_cm" not in source
    assert "board_width_cm" not in source


def test_plan_result_summary_is_reexposed_without_schema_resurrection():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    assert '"plan_result_section", "plan_controls_intro"' in source
    assert 'frm.set_df_property(fieldname, "hidden", 0)' in source
    assert "AlmdinaDoorCuttingPlanUX" in source
    assert "planUx.refresh(frm)" in source
    assert "frappe.get_meta" not in source
