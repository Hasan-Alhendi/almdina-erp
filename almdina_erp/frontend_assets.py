"""Central frontend asset manifest for Almdina ERP.

The ordering in these lists is runtime-significant. Keep feature ownership here and
change ordering only with an explicit dependency/behavior change and regression
coverage.
"""

app_include_css = [
    "/assets/almdina_erp/css/door_cutting_order_responsive.css",
]

app_include_js = [
    "/assets/almdina_erp/js/permission_context.js",
    "/assets/almdina_erp/js/page_revisit_refresh.js",
    "/assets/almdina_erp/js/permission_action_visibility_guard.js",
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

doctype_js = {
    "Door Cutting Order": [
        # The document context owns the surface-readiness registry, so it must be
        # evaluated before any module that registers a probe with it.
        "public/js/door_cutting_order/core/door_cutting_order_document_context.js",
        "public/js/permission_context.js",
        "public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js",
        "public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js",
        "public/js/door_cutting_order/printing/door_cutting_order_print_identity.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js",
        "public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_shape_print.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux_patch.js",
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
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_cut_dimensions_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_print_theme.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js",
        "public/js/door_cutting_order/costing/door_cutting_order_multi_edge_documents_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_compactness_ux.js",
        "public/js/door_cutting_order/costing/door_cutting_order_cost_presenter.js",
        "public/js/door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js",
        "public/js/door_cutting_order/costing/door_cutting_order_financial_documents_ux.js",
        "public/js/door_cutting_order/costing/door_cutting_order_customer_invoice_toolbar_ux.js",
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_color_ux.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_board_text_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_save_render_performance_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_text_board_plan_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_fast_save_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_content_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_surface_bootstrap.js",
        "public/js/door_cutting_order/core/door_cutting_order_tab_permissions_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_permission_refresh_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js",
        "public/js/door_cutting_order/responsive/door_cutting_order_header_ux.js",
        "public/js/door_cutting_order/production/shop_floor_order_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_approval_ux.js",
        "public/js/door_cutting_order/cutting_plan/secure_dxf_export.js",
        "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js",
        "public/js/door_cutting_order/core/order_lifecycle.js",
        "public/js/input_stability.js",
        "public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js",
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
