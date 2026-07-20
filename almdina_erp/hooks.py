app_name = "almdina_erp"
app_title = "Almdina ERP"
app_publisher = "Horizon Tech"
app_description = "MDF cutting, optimization, production and inventory management"
app_email = ""
app_license = "Proprietary"
app_version = "1.0.0-dev"

after_install = "almdina_erp.install.after_install"
after_migrate = "almdina_erp.install.after_migrate"

app_include_js = [
    "/assets/almdina_erp/js/order_lifecycle.js",
]

doctype_js = {
    "Door Cutting Order": "public/js/door_cutting_order_workflow.js",
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
    "almdina_erp.almdina_erp.services.replacement_service.complete_replacement":
        "almdina_erp.almdina_erp.services.replacement_completion.complete_replacement",
}

# Keep v1.0 business logic inside the app package. Client-side scripts are used
# for interaction and preview only; authoritative calculations are server-side.
