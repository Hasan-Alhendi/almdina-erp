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
]

doctype_js = {
    "Door Cutting Order": [
        "public/js/door_cutting_order_workflow.js",
        "public/js/order_lifecycle.js",
        "public/js/door_cutting_order_defaults.js",
        "public/js/door_cutting_order_operator_ux.js",
        "public/js/door_cutting_order_operator_ux_patch.js",
        "public/js/door_cutting_order_header_ux.js",
        "public/js/secure_dxf_export.js",
    ],
    "Production Stage": "public/js/production_stage.js",
    "Replacement Piece": "public/js/replacement_piece.js",
    "Material Consumption Log": "public/js/material_consumption_log.js",
}

doc_events = {
    "Replacement Piece": {
        "on_update": "almdina_erp.almdina_erp.services.cost_service.on_replacement_update",
    },
    "Cutting Plan": {
        "on_update": "almdina_erp.almdina_erp.services.cost_service.on_order_plan_update",
    },
}

override_whitelisted_methods = {
    "almdina_erp.almdina_erp.services.replacement_service.approve_replacement":
        "almdina_erp.almdina_erp.services.replacement_approval.approve_replacement",
    "almdina_erp.almdina_erp.services.replacement_service.start_replacement":
        "almdina_erp.almdina_erp.services.replacement_execution.start_replacement",
    "almdina_erp.almdina_erp.services.replacement_service.complete_replacement":
        "almdina_erp.almdina_erp.services.replacement_completion.complete_replacement",
}

# Keep v1.0 business logic inside the app package. Client-side scripts are used
# for interaction and preview only; authoritative calculations are server-side.
