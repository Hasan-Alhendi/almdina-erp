"""Central frontend asset manifest for Almdina ERP.

The ordering in these lists is runtime-significant. Keep feature ownership here and
change ordering only with an explicit dependency/behavior change and regression
coverage.
"""

app_include_css = [
    "/assets/almdina_erp/css/door_cutting_order_responsive.css",
    "/assets/almdina_erp/css/door_cutting_order_extra_addons.css",
]

app_include_js = [
    "/assets/almdina_erp/js/permission_context.js",
    "/assets/almdina_erp/js/frontend_foundation.js",
    "/assets/almdina_erp/js/page_revisit_refresh.js",
    "/assets/almdina_erp/js/responsive_device.js",
    "/assets/almdina_erp/js/shop_floor_quick_actions.js",
    "/assets/almdina_erp/js/shared_shell.js",
    "/assets/almdina_erp/js/arabic_operator_ui.js",
    "/assets/almdina_erp/js/input_stability.js",
    "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js",
    "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js",
]

doctype_js = {
    "Door Cutting Order": [
        # Critical bootstrap only. The document context must exist before any
        # surface or lifecycle owner registers cancellable work with it.
        "public/js/door_cutting_order/core/door_cutting_order_document_context.js",
        "public/js/permission_context.js",
        "public/js/door_cutting_order/core/door_cutting_order_workspace_store.js",
        "public/js/door_cutting_order/core/door_cutting_order_workspace_sync_coordinator.js",
        "public/js/door_cutting_order/core/door_cutting_order_workspace_field_editor.js",
        # Plan/Cost transport + state stay eager and lightweight so workspace
        # registration/freshness remain deterministic. Their renderers/actions are
        # loaded only when the corresponding tab is activated.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js",
        "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_api.js",
        "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js",
        "public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js",
        "public/js/door_cutting_order/core/door_cutting_order_workspace_asset_status_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_workspace_activation_lifecycle.js",
        # DCO-specific dependency policy is deliberately separate from the shared
        # freshness primitive: only this feature knows which inputs affect Plan,
        # Cost, or the special-price basis.
        "public/js/door_cutting_order/order_entry/door_cutting_order_mutation_impact_policy.js",
        "public/js/door_cutting_order/printing/door_cutting_order_print_identity.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js",
        "public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_shape_print.js",
        # Extra-door selection owns only customer requirements and cost impact;
        # it is evaluated before the operator renderer consumes its type-cell API.
        "public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_extra_addons_ux.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js",
        # Presentation-only owner for the native Order tab fields. It does not
        # duplicate document state or save commands; it only arranges the existing
        # Frappe controls into the compact intake/material/measurements hierarchy.
        "public/js/door_cutting_order/order_entry/door_cutting_order_order_tab_layout_ux.js",
        # Qty+Enter is a focused keyboard behavior layered on the operator's
        # existing row materialization/model-sync contract; it owns no rendering.
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js",
        # Measurement features keep their existing Frappe hook order; this owner
        # only centralizes cancellable frame/timer work for FE-ARCH-008.
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_lifecycle.js",
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
        # Multi-edge/profile modules keep their feature APIs, while one structural
        # runtime owner prevents their historical broad observers from competing.
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_render_owner.js",
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_cut_dimensions_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_print_theme.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_compactness_ux.js",
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_color_ux.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_board_text_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_save_render_performance_ux.js",
        # Permission navigation/recovery stays on the critical path. Hidden Plan
        # and Cost HTML are not readiness failures; their feature bundles own them.
        "public/js/door_cutting_order/core/door_cutting_order_tab_permissions_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_permission_refresh_ux.js",
        "public/js/door_cutting_order/responsive/door_cutting_order_header_ux.js",
        "public/js/door_cutting_order/production/shop_floor_order_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js",
        # Explicit Order-save intent must win over any transient plan-checkpoint
        # preserve marker before Frappe evaluates after_save.
        "public/js/door_cutting_order/core/door_cutting_order_edit_save_intent_ux.js",
        "public/js/door_cutting_order/core/order_lifecycle.js",
        "public/js/input_stability.js",
        "public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js",
        # The page coordinator reads feature APIs dynamically. On Plan/Cost first
        # activation the workspace-updated event re-renders it after lazy assets load.
        "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_plan_cost_workspace_visual_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_workspace_freshness_ux.js",
    ],
    "Edge Banding Type": "public/js/edge_banding_type_ux.js",
    "Production Routing": "public/js/production_routing_ux.js",
    "Replacement Piece": [
        "public/js/permission_context.js",
        "public/js/replacement_piece.js",
    ],
}

doctype_list_js = {
    "Door Cutting Order": "public/js/door_cutting_order/list_view/door_cutting_order_list.js",
}
