from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
MANIFEST = ROOT / "frontend_assets.py"

EXPECTED_APP_INCLUDE_JS = [
    "/assets/almdina_erp/js/permission_context.js",
    "/assets/almdina_erp/js/page_revisit_refresh.js",
    "/assets/almdina_erp/js/responsive_device.js",
    "/assets/almdina_erp/js/shop_floor_quick_actions.js",
    "/assets/almdina_erp/js/shared_shell.js",
    "/assets/almdina_erp/js/arabic_operator_ui.js",
    "/assets/almdina_erp/js/input_stability.js",
    "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js",
    "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js",
    "/assets/almdina_erp/js/door_cutting_order/cutting_plan/secure_dxf_export.js",
    "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js",
]

EXPECTED_DOOR_CUTTING_ORDER_JS = [
    "public/js/door_cutting_order/core/door_cutting_order_document_context.js",
    "public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js",
    "public/js/permission_context.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_store.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_sync_coordinator.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_field_editor.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js",
    "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_api.js",
    "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js",
    "public/js/door_cutting_order/recovery/application/door_cutting_order_recovery_projection.js",
    "public/js/door_cutting_order/recovery/infrastructure/door_cutting_order_recovery_indexeddb.js",
    "public/js/door_cutting_order/recovery/infrastructure/door_cutting_order_local_draft_repository.js",
    "public/js/door_cutting_order/recovery/infrastructure/door_cutting_order_local_asset_repository.js",
    "public/js/door_cutting_order/recovery/infrastructure/door_cutting_order_recovery_api.js",
    "public/js/door_cutting_order/recovery/application/door_cutting_order_checkpoint_session.js",
    "public/js/door_cutting_order/recovery/application/door_cutting_order_new_recovery.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_asset_status_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_activation_lifecycle.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_recalculation_job.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_mutation_impact_policy.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_fast_save_ux.js",
    "public/js/door_cutting_order/printing/door_cutting_order_print_identity.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js",
    "public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js",
    "public/js/door_cutting_order/printing/door_cutting_order_shape_print.js",
    "public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_extra_addons_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_order_tab_layout_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_cutting_machine_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_lifecycle.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_presentation_owner.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_bulk_rows_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_keyboard_columns_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_compact_measurements_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_toolbar_ux.js",
    "public/js/door_cutting_order/drawing/special_shape_facade.js",
    "public/js/door_cutting_order/core/door_cutting_order_action_permission_guard.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_resilience_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_table_performance_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_double_click_guard.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_render_owner.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_cut_dimensions_ux.js",
    "public/js/door_cutting_order/printing/door_cutting_order_document_print_theme.js",
    "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js",
    "public/js/door_cutting_order/printing/door_cutting_order_document_compactness_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_color_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_board_text_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_save_render_performance_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_tab_permissions_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_permission_refresh_ux.js",
    "public/js/door_cutting_order/responsive/door_cutting_order_header_ux.js",
    "public/js/door_cutting_order/notes/door_cutting_order_notes_ux.js",
    "public/js/door_cutting_order/production/shop_floor_order_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js",
    "public/js/door_cutting_order/recovery/presentation/door_cutting_order_local_checkpoint.js",
    "public/js/door_cutting_order/core/door_cutting_order_edit_save_intent_ux.js",
    "public/js/door_cutting_order/core/order_lifecycle.js",
    "public/js/input_stability.js",
    "public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_tab_edit_lifecycle_guard.js",
    "public/js/door_cutting_order/core/door_cutting_order_plan_cost_workspace_visual_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_workspace_freshness_ux.js",
]


def test_hooks_delegate_frontend_assets_to_one_manifest():
    hooks_source = HOOKS.read_text(encoding="utf-8")
    assert "from almdina_erp.frontend_assets import (" in hooks_source
    assert "app_include_js = [" not in hooks_source
    assert "doctype_js = {" not in hooks_source
    assert "doctype_list_js = {" not in hooks_source

    hooks = runpy.run_path(str(HOOKS))
    manifest = runpy.run_path(str(MANIFEST))
    for name in ("app_include_css", "app_include_js", "doctype_js", "doctype_list_js"):
        assert hooks[name] == manifest[name]


def test_global_asset_order_is_frozen_during_manifest_extraction():
    manifest = runpy.run_path(str(MANIFEST))
    assert manifest["app_include_css"] == [
        "/assets/almdina_erp/css/door_cutting_order_responsive.css",
    ]
    assert manifest["app_include_js"] == EXPECTED_APP_INCLUDE_JS


def test_door_cutting_order_asset_order_is_frozen_during_manifest_extraction():
    manifest = runpy.run_path(str(MANIFEST))
    assert manifest["doctype_js"]["Door Cutting Order"] == EXPECTED_DOOR_CUTTING_ORDER_JS
    assert manifest["doctype_js"]["Edge Banding Type"] == "public/js/edge_banding_type_ux.js"
    assert manifest["doctype_js"]["Production Routing"] == "public/js/production_routing_ux.js"
    assert manifest["doctype_js"]["Replacement Piece"] == [
        "public/js/permission_context.js",
        "public/js/replacement_piece.js",
    ]
    assert manifest["doctype_list_js"] == {
        "Door Cutting Order": "public/js/door_cutting_order/list_view/door_cutting_order_list.js",
    }
