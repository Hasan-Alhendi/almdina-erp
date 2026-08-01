app_name = "almdina_erp"
app_title = "Almdina ERP"
app_publisher = "Horizon Tech"
app_description = "MDF cutting, optimization, production and customer costing"
app_email = ""
app_license = "Proprietary"
app_version = "1.0.0-dev"

add_to_apps_screen = [
    {
        "name": "almdina_erp",
        "logo": "/assets/almdina_erp/images/factory-app.svg",
        "title": "Factory Management",
        "route": "/desk/almdina-erp",
    }
]

after_install = "almdina_erp.lifecycle.after_install"
after_migrate = "almdina_erp.lifecycle.after_migrate"

app_include_js = [
    "/assets/almdina_erp/js/permission_context.js",
    "/assets/almdina_erp/js/arabic_operator_ui.js",
    "/assets/almdina_erp/js/input_stability.js",
    "/assets/almdina_erp/js/shop_floor_desk.js",
    "/assets/almdina_erp/js/order_entry_desk.js",
    "/assets/almdina_erp/js/door_cutting_order_special_shape_geometry.js",
    "/assets/almdina_erp/js/door_cutting_order_shape_output_contract.js",
    "/assets/almdina_erp/js/secure_dxf_export.js",
    "/assets/almdina_erp/js/door_cutting_order_drawing_plan_ux.js",
]

doctype_js = {
    "Door Cutting Order": [
        "public/js/door_cutting_order_document_context.js",
        "public/js/door_cutting_order_special_shape_geometry.js",
        "public/js/door_cutting_order_shape_output_contract.js",
        "public/js/door_cutting_order_cutting_plan_renderer.js",
        "public/js/door_cutting_order_workflow.js",
        "public/js/order_lifecycle.js",
        "public/js/door_cutting_order_defaults.js",
        "public/js/door_cutting_order_clipped_corner_ux.js",
        "public/js/door_cutting_order_shape_print.js",
        "public/js/door_cutting_order_operator_ux.js",
        "public/js/door_cutting_order_operator_ux_patch.js",
        "public/js/door_cutting_order_bulk_rows_ux.js",
        "public/js/door_cutting_order_keyboard_columns_ux.js",
        "public/js/door_cutting_order_compact_measurements_ux.js",
        "public/js/door_cutting_order_measurement_actions_ux.js",
        "public/js/door_cutting_order_sketch_engine.js",
        "public/js/door_cutting_order_sketch_interaction.js",
        "public/js/door_cutting_order_sketch_history.js",
        "public/js/door_cutting_order_sketch_renderer.js",
        "public/js/door_cutting_order_inline_note_editor.js",
        "public/js/door_cutting_order_special_shape_ux.js",
        "public/js/door_cutting_order_special_shape_close_ux.js",
        "public/js/door_cutting_order_measurement_resilience_ux.js",
        "public/js/door_cutting_order_table_performance_ux.js",
        "public/js/door_cutting_order_multi_edge_ux.js",
        "public/js/door_cutting_order_edge_profile_controls_ux.js",
        "public/js/door_cutting_order_edge_profile_double_click_guard.js",
        "public/js/door_cutting_order_cut_dimensions_ux.js",
        "public/js/door_cutting_order_cost_invoice_ux.js",
        "public/js/door_cutting_order_document_print_theme.js",
        "public/js/door_cutting_order_document_print_presenter.js",
        "public/js/door_cutting_order_multi_edge_documents_ux.js",
        "public/js/door_cutting_order_document_compactness_ux.js",
        "public/js/door_cutting_order_cost_permissions_ux.js",
        "public/js/door_cutting_order_financial_documents_ux.js",
        "public/js/door_cutting_order_edge_color_ux.js",
        "public/js/door_cutting_order_board_text_ux.js",
        "public/js/door_cutting_order_save_render_performance_ux.js",
        "public/js/door_cutting_order_plan_ux.js",
        "public/js/door_cutting_order_text_board_plan_ux.js",
        "public/js/door_cutting_order_fast_save_ux.js",
        "public/js/door_cutting_order_plan_controls_ux.js",
        "public/js/door_cutting_order_plan_content_ux.js",
        "public/js/door_cutting_order_plan_tabs_ux.js",
        "public/js/door_cutting_order_drawing_plan_ux.js",
        "public/js/door_cutting_order_header_ux.js",
        "public/js/shop_floor_order_ux.js",
        "public/js/door_cutting_order_drawing_approval_ux.js",
        "public/js/secure_dxf_export.js",
        "public/js/door_cutting_order_toolbar_stability_ux.js",
        "public/js/door_cutting_order_revision_ux.js",
        "public/js/input_stability.js",
    ],
    "Edge Banding Type": "public/js/edge_banding_type_ux.js",
    "Production Stage": "public/js/production_stage.js",
    "Replacement Piece": "public/js/replacement_piece.js",
}

doctype_list_js = {
    "Door Cutting Order": "public/js/door_cutting_order_list.js",
}

override_doctype_class = {
    "Door Cutting Order":
        "almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order_controller.DoorCuttingOrderController",
}

doc_events = {
    "Replacement Piece": {
        "on_update": "almdina_erp.almdina_erp.services.cost_service.on_replacement_update",
    },
    "Cutting Plan": {
        "on_update": "almdina_erp.almdina_erp.services.cost_service.on_order_plan_update",
    },
}

permission_query_conditions = {
    "Door Cutting Order": "almdina_erp.permissions.door_cutting_order_query",
    "Production Stage": "almdina_erp.permissions.production_stage_query",
    "Cutting Plan": "almdina_erp.permissions.cutting_plan_query",
}

boot_session = "almdina_erp.boot.boot_session"
extend_bootinfo = ["almdina_erp.boot.extend_bootinfo"]

override_whitelisted_methods = {
    "almdina_erp.almdina_erp.services.cutting_plan_service.approve_order":
        "almdina_erp.almdina_erp.services.order_approval_service.approve_order",
    "almdina_erp.almdina_erp.services.cutting_plan_service.send_order_to_production":
        "almdina_erp.almdina_erp.services.order_dispatch_service.validate_order_for_dispatch",
    # Keep the legacy route while applying role-managed drawing approval.
    "almdina_erp.almdina_erp.services.cutting_plan_service.lock_cutting_plan":
        "almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf",
    "almdina_erp.almdina_erp.services.special_shape_service.approve_special_piece_price":
        "almdina_erp.almdina_erp.services.cost_permission_service.approve_special_piece_price",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_dispatch_options":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_dispatch_options",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_revert_targets":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_revert_targets",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_my_inbox":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_inbox",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_my_archive":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_archive",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_order_shop_floor_detail":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_order_shop_floor_detail",
    "almdina_erp.almdina_erp.services.shop_floor_service.mark_dxf_exported":
        "almdina_erp.almdina_erp.services.shop_floor_dxf_service.mark_dxf_exported",
    "almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf":
        "almdina_erp.almdina_erp.services.shop_floor_dxf_service.upload_production_dxf",
    "almdina_erp.almdina_erp.services.shop_floor_service.recalculate_drawing_plan":
        "almdina_erp.almdina_erp.services.shop_floor_dxf_service.recalculate_drawing_plan",
    "almdina_erp.almdina_erp.services.shop_floor_service.approve_production_dxf":
        "almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_handoff_workers":
        "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_workers",
    "almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order":
        "almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order",
    "almdina_erp.almdina_erp.services.shop_floor_commands.dispatch_order":
        "almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order",
    "almdina_erp.almdina_erp.services.shop_floor_service.start_my_stage":
        "almdina_erp.almdina_erp.services.shop_floor_commands.start_my_stage",
    "almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next":
        "almdina_erp.almdina_erp.services.shop_floor_commands.handoff_to_next",
    "almdina_erp.almdina_erp.services.shop_floor_service.mark_delivered":
        "almdina_erp.almdina_erp.services.shop_floor_commands.mark_delivered",
    "almdina_erp.almdina_erp.services.shop_floor_service.revert_department":
        "almdina_erp.almdina_erp.services.shop_floor_commands.revert_department",
    "almdina_erp.almdina_erp.services.shop_floor_service.return_order_to_draft":
        "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision",
    "almdina_erp.almdina_erp.services.shop_floor_commands.return_order_to_draft":
        "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision",
}
