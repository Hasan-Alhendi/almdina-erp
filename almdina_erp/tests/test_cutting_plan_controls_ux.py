from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
PLAN_DOCTYPE = ROOT / "almdina_erp" / "doctype" / "cutting_plan" / "cutting_plan.json"
DETAIL_DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order_detail" / "door_cutting_order_detail.json"
HOOKS = ROOT / "frontend_assets.py"
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
REGISTRY = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_workspace_asset_registry.js"
PLAN_UX = CUTTING_PLAN / "door_cutting_order_plan_ux.js"
CONTROLS_UX = CUTTING_PLAN / "door_cutting_order_plan_controls_ux.js"
PLAN_WORKSPACE_API = CUTTING_PLAN / "door_cutting_order_plan_workspace_api.js"
TEXT_BOARD_PLAN_UX = CUTTING_PLAN / "door_cutting_order_text_board_plan_ux.js"
FAST_SAVE_UX = CUTTING_PLAN / "door_cutting_order_fast_save_ux.js"
PLAN_TABS_UX = CUTTING_PLAN / "door_cutting_order_plan_tabs_ux.js"
ACTION_GUARD_UX = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_action_permission_guard.js"
REMOVED_PALETTE = ROOT / "public" / "js" / "door_cutting_order_algorithm_palette_ux.js"
PLAN_PERMISSION_SERVICE = (
    ROOT / "almdina_erp" / "services" / "order_plan_permission_service.py"
)


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_advanced_algorithms_remain_in_the_canonical_plan_optimization_select():
    order_payload = json.loads(source(DOCTYPE))
    order_fields = {field.get("fieldname") for field in order_payload["fields"]}
    assert "packing_mode" not in order_fields

    payload = json.loads(source(PLAN_DOCTYPE))
    optimization_mode = next(
        field for field in payload["fields"] if field.get("fieldname") == "optimization_mode"
    )
    options = set(optimization_mode["options"].splitlines())
    assert {"Auto Pro", "Deep Search", "Optimal Search"}.issubset(options)
    assert optimization_mode.get("read_only") == 1


def test_duplicate_algorithm_palette_is_removed_and_simple_controls_load_last():
    hooks = source(HOOKS)
    registry = source(REGISTRY)
    plan = "door_cutting_order_plan_ux.js"
    text_board = "door_cutting_order_text_board_plan_ux.js"
    fast_save = "door_cutting_order_fast_save_ux.js"
    controls = "door_cutting_order_plan_controls_ux.js"

    assert not REMOVED_PALETTE.exists()
    assert "door_cutting_order_algorithm_palette_ux.js" not in hooks
    assert "door_cutting_order_algorithm_palette_ux.js" not in registry

    # The persistence/staleness tracker must observe measurement changes before
    # the first Plan visit. Keep it eager, while the actual Plan presentation
    # chain remains lazy and preserves its established dependency order.
    assert fast_save in hooks
    assert fast_save not in registry
    for asset in (plan, text_board, controls):
        assert asset in registry
        assert asset not in hooks
    assert registry.index(plan) < registry.index(text_board) < registry.index(controls)


def test_simple_controls_keep_only_current_settings_recalculation_action():
    controls = source(CONTROLS_UX)
    plan = source(PLAN_UX)

    for selector in (".dco-auto-pro-plan", ".dco-deep-plan", ".dco-optimal-plan", ".dco-algorithm-palette"):
        assert selector in controls
    assert "find(DUPLICATED_ACTIONS)" in controls
    assert "duplicated.remove()" in controls
    assert "إعادة الحساب بالإعدادات الحالية" in controls
    assert "إعادة الحساب بالإعدادات الحالية" in plan


def test_recalculation_button_uses_preview_session_without_full_document_plan_save():
    controls = source(CONTROLS_UX)
    plan_api = source(PLAN_WORKSPACE_API)

    # The legacy recalculation route remains transport-compatible, but the active
    # form action delegates to the non-persisting preview session.
    assert (
        '"almdina_erp.almdina_erp.services.order_plan_permission_service.recalculate_order"'
        in plan_api
    )
    assert "RECALCULATE_METHOD" in plan_api
    assert "AlmdinaPlanWorkspaceAPI" in controls
    assert "AlmdinaPlanPreviewSession" in controls
    assert "await previews.preview(frm, settings)" in controls
    assert "transport.recalculate(frm.doc.name, settings)" not in controls
    assert "frappe.call" not in controls
    assert "frm.reload_doc" not in controls
    assert "frm.save" not in controls
    assert (
        '"almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order.recalculate_order"'
        not in controls
    )
    assert "__almdinaPlanCommandBound" in controls
    assert "scheduleSimplify" in controls
    assert "setTextIfChanged" in controls
    assert "preparePlanInputs" in controls
    assert "await preparePlanInputs(frm)" in controls
    assert "await persistPendingOrderInputs(frm)" in controls
    assert 'can(frm, "recalculate_plan")' in controls
    assert 'can(frm, "edit_optimizer_settings")' in controls
    assert "canMutateCurrentStage(frm)" in controls
    assert "canTuneCuttingAlgorithm(frm)" in controls
    assert "frm.doc.current_production_stage" in controls


def test_legacy_helpers_never_intercept_or_save_cutting_plan_commands():
    fast_save = source(FAST_SAVE_UX)
    text_board = source(TEXT_BOARD_PLAN_UX)

    for legacy in (fast_save, text_board):
        assert "frm.save" not in legacy
        assert 'addEventListener("click"' not in legacy
        assert "stopImmediatePropagation" not in legacy
        assert ".dco-recalculate-plan" not in legacy

    assert "validateCurrentPlanInputs" in fast_save
    assert "preparePlanInputs" in text_board
    assert "door_cutting_order_plan_controls_ux.js" in text_board


def test_cutting_plan_browser_authority_never_depends_on_cost_visibility():
    controls = source(CONTROLS_UX)
    tabs = source(PLAN_TABS_UX)
    guard = source(ACTION_GUARD_UX)

    for module in (controls, tabs, guard):
        assert 'can(frm, "view_costs")' not in module
        assert 'can("view_costs")' not in module

    assert '"view_system_cutting_plan"' in tabs
    assert '"view_uploaded_cutting_plan"' in tabs
    assert '"view_approved_cutting_plan"' in tabs
    assert '"recalculate_plan"' in controls
    assert '"edit_optimizer_settings"' in controls


def test_kerf_and_trim_are_optimizer_fields_in_the_frontend_permission_owner():
    controls = source(CONTROLS_UX)
    plan = source(PLAN_UX)

    optimizer_block = controls.split("const OPTIMIZER_FIELDS = [", 1)[1].split("];", 1)[0]
    for fieldname in (
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ):
        assert f'"{fieldname}"' in optimizer_block

    assert 'can(frm, "edit_optimizer_settings")' in controls
    assert "function activeSettings(frm)" in controls
    assert "row && row.settings" in controls
    assert "kerf_mm: frm.doc.kerf_mm" not in controls
    assert "trim_margin_mm: frm.doc.trim_margin_mm" not in controls

    read_only_body = plan.split("function applyReadOnlyState(frm)", 1)[1].split(
        "function refreshPlanUX(frm)", 1
    )[0]
    assert '"kerf_mm"' not in read_only_body
    assert '"trim_margin_mm"' not in read_only_body
    assert '"packing_mode"' in read_only_body


def test_server_treats_kerf_and_trim_as_optimizer_settings():
    service = source(PLAN_PERMISSION_SERVICE)
    optimizer_block = service.split("_OPTIMIZER_FIELDS = (", 1)[1].split(")", 1)[0]

    assert '"kerf_mm"' in optimizer_block
    assert '"trim_margin_mm"' in optimizer_block
    assert '"kerf_mm": "default_kerf_mm"' in service
    assert '"trim_margin_mm": "default_trim_margin_mm"' in service
    assert "_CUT_GEOMETRY_FIELDS" not in service
    assert "Capability.EDIT_OPTIMIZER_SETTINGS" in service


def test_piece_financial_fields_are_protected_at_cost_permission_level():
    payload = json.loads(source(DETAIL_DOCTYPE))
    fields = {field["fieldname"]: field for field in payload["fields"]}
    for fieldname in (
        "edge_long_rate_usd",
        "edge_width_rate_usd",
        "edge_long_cost_usd",
        "edge_width_cost_usd",
        "edge_cost_usd",
        "edge_rate_usd",
        "special_shape_estimated_unit_price_usd",
        "special_shape_custom_unit_price_usd",
        "special_shape_final_unit_price_usd",
        "clipped_corner_edge_price_usd",
    ):
        assert fields[fieldname].get("permlevel") == 1


def test_advanced_algorithm_labels_are_applied_inside_the_primary_select():
    controls = source(CONTROLS_UX)
    for value, label in (
        ("Auto Pro", "أفضل توزيع متقدم"),
        ("Deep Search", "بحث معمق"),
        ("Optimal Search", "بحث أمثل"),
    ):
        assert f'{{ value: "{value}", label: "{label}" }}' in controls
    assert 'if (!field || !field.df) return;' in controls
    assert 'field.$input' in controls
    assert 'option.text(label)' in controls
