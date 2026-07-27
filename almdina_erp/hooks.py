app_name = "almdina_erp"
app_title = "Almdina ERP"
app_publisher = "Horizon Tech"
app_description = "MDF cutting, optimization, production and inventory management"
app_email = ""
app_license = "Proprietary"
app_version = "1.0.0-dev"

# Frappe v16 desktop/apps screen entry point. The title is translated through
# translations/ar.csv so Arabic users see "إدارة المعمل" while English users
# keep the English label. The route opens the root Almdina ERP workspace.
add_to_apps_screen = [
    {
        "name": "almdina_erp",
        "logo": "/assets/almdina_erp/images/factory-app.svg",
        "title": "Factory Management",
        "route": "/desk/almdina-erp",
    }
]

after_install = "almdina_erp.install.after_install"
after_migrate = "almdina_erp.install.after_migrate"

# Keep only genuinely global Desk behaviour here. Door Cutting Order scripts are
# loaded through doctype_js below, which Frappe reads from the app source and
# injects into FormMeta server-side. This avoids production UX depending on a
# sites/assets symlink being present in the frontend container.
app_include_js = [
    "/assets/almdina_erp/js/arabic_operator_ui.js",
    "/assets/almdina_erp/js/shop_floor_desk.js",
    "/assets/almdina_erp/js/order_entry_desk.js",
    # Loaded app-wide so the shop-floor page can reuse the validated DXF exporter.
    "/assets/almdina_erp/js/secure_dxf_export.js",
    "/assets/almdina_erp/js/door_cutting_order_drawing_plan_ux.js",
]

doctype_js = {
    "Door Cutting Order": [
        "public/js/door_cutting_order_workflow.js",
        "public/js/order_lifecycle.js",
        "public/js/door_cutting_order_defaults.js",
        "public/js/door_cutting_order_clipped_corner_ux.js",
        "public/js/door_cutting_order_special_shape_geometry.js",
        "public/js/door_cutting_order_shape_print.js",
        "public/js/door_cutting_order_operator_ux.js",
        "public/js/door_cutting_order_operator_ux_patch.js",
        "public/js/door_cutting_order_bulk_rows_ux.js",
        "public/js/door_cutting_order_keyboard_columns_ux.js",
        "public/js/door_cutting_order_compact_measurements_ux.js",
        "public/js/door_cutting_order_measurement_actions_ux.js",
        "public/js/door_cutting_order_special_shape_ux.js",
        "public/js/door_cutting_order_special_shape_close_ux.js",
        "public/js/door_cutting_order_measurement_resilience_ux.js",
        "public/js/door_cutting_order_table_performance_ux.js",
        "public/js/door_cutting_order_cost_invoice_ux.js",
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
        "public/js/secure_dxf_export.js",
        "public/js/door_cutting_order_toolbar_stability_ux.js",
    ],
    "Production Stage": "public/js/production_stage.js",
    "Replacement Piece": "public/js/replacement_piece.js",
    "Material Consumption Log": "public/js/material_consumption_log.js",
}

doctype_list_js = {
    "Door Cutting Order": "public/js/door_cutting_order_list.js",
}

# Keep the optimized controller as the authoritative business base, then add the
# free-text board input layer used by order-entry operators.
override_doctype_class = {
    "Door Cutting Order":
        "almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order_text_board.TextBoardDoorCuttingOrder",
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

# Boot hooks are deliberately read-only. User provisioning and role assignment
# happen only through explicit administrative commands.
boot_session = "almdina_erp.boot.boot_session"
extend_bootinfo = ["almdina_erp.boot.extend_bootinfo"]

override_whitelisted_methods = {
    "almdina_erp.almdina_erp.services.replacement_service.approve_replacement":
        "almdina_erp.almdina_erp.services.replacement_approval.approve_replacement",
    "almdina_erp.almdina_erp.services.replacement_service.start_replacement":
        "almdina_erp.almdina_erp.services.replacement_execution.start_replacement",
    "almdina_erp.almdina_erp.services.replacement_service.complete_replacement":
        "almdina_erp.almdina_erp.services.replacement_completion.complete_replacement",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_handoff_workers":
        "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_workers",
    "almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order":
        "almdina_erp.almdina_erp.services.shop_floor_commands.dispatch_order",
    "almdina_erp.almdina_erp.services.shop_floor_service.start_my_stage":
        "almdina_erp.almdina_erp.services.shop_floor_commands.start_my_stage",
    "almdina_erp.almdina_erp.services.shop_floor_service.handoff_to_next":
        "almdina_erp.almdina_erp.services.shop_floor_commands.handoff_to_next",
    "almdina_erp.almdina_erp.services.shop_floor_service.mark_delivered":
        "almdina_erp.almdina_erp.services.shop_floor_commands.mark_delivered",
    "almdina_erp.almdina_erp.services.shop_floor_service.revert_department":
        "almdina_erp.almdina_erp.services.shop_floor_commands.revert_department",
    "almdina_erp.almdina_erp.services.shop_floor_service.return_order_to_draft":
        "almdina_erp.almdina_erp.services.shop_floor_commands.return_order_to_draft",
}

# Keep v1.0 business logic inside the app package. Client-side scripts are used
# for interaction and preview only; authoritative calculations are server-side.
