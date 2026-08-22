from almdina_erp.frontend_assets import (
    app_include_css,
    app_include_js,
    doctype_js,
    doctype_list_js,
)

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

override_doctype_class = {
    "Door Cutting Order":
        "almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order_controller.DoorCuttingOrderController",
}

doc_events = {
    "Door Cutting Order": {
        "before_validate":
            "almdina_erp.almdina_erp.services.order_plan_permission_service.enforce_plan_and_drawing_permissions",
    },
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
    "Production Incident": "almdina_erp.permissions.production_incident_query",
    "Cutting Plan": "almdina_erp.permissions.cutting_plan_query",
    "Replacement Piece": "almdina_erp.permissions.replacement_piece_query",
    "Customer": "almdina_erp.resource_permissions.customer_query",
    "Edge Banding Type": "almdina_erp.resource_permissions.edge_banding_type_query",
    "Production Routing": "almdina_erp.resource_permissions.production_routing_query",
}

has_permission = {
    "Door Cutting Order": "almdina_erp.almdina_erp.infrastructure.frappe.native_document_permissions.door_cutting_order_has_permission",
    "Production Stage": "almdina_erp.almdina_erp.infrastructure.frappe.native_document_permissions.production_stage_has_permission",
    "Production Incident": "almdina_erp.almdina_erp.infrastructure.frappe.native_document_permissions.production_incident_has_permission",
    "Cutting Plan": "almdina_erp.almdina_erp.infrastructure.frappe.native_document_permissions.cutting_plan_has_permission",
    "Replacement Piece": "almdina_erp.almdina_erp.infrastructure.frappe.native_document_permissions.replacement_piece_has_permission",
    "Customer": "almdina_erp.resource_permissions.customer_has_permission",
    "Edge Banding Type": "almdina_erp.resource_permissions.edge_banding_type_has_permission",
    "Production Routing": "almdina_erp.resource_permissions.production_routing_has_permission",
    "Almdina ERP Settings": "almdina_erp.resource_permissions.factory_settings_has_permission",
}

boot_session = "almdina_erp.boot.boot_session"
extend_bootinfo = ["almdina_erp.boot.extend_bootinfo"]

override_whitelisted_methods = {
    "frappe.desk.desktop.get_desktop_page":
        "almdina_erp.workspace_api.get_desktop_page",
    "almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order.recalculate_order":
        "almdina_erp.almdina_erp.services.order_plan_permission_service.recalculate_order",
    "almdina_erp.almdina_erp.services.cutting_plan_service.submit_order_for_review":
        "almdina_erp.almdina_erp.services.order_lifecycle_permission_service.submit_order_for_review",
    "almdina_erp.almdina_erp.services.cutting_plan_service.approve_order":
        "almdina_erp.almdina_erp.services.order_approval_service.approve_order",
    "almdina_erp.almdina_erp.services.cutting_plan_service.reject_order":
        "almdina_erp.almdina_erp.services.order_review_service.reject_order",
    "almdina_erp.almdina_erp.services.cutting_plan_service.send_order_to_production":
        "almdina_erp.almdina_erp.services.order_dispatch_service.validate_order_for_dispatch",
    "almdina_erp.almdina_erp.services.cutting_plan_service.lock_cutting_plan":
        "almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf",
    "almdina_erp.almdina_erp.services.special_shape_service.approve_special_piece_price":
        "almdina_erp.almdina_erp.services.cost_permission_service.approve_special_piece_price",
    "almdina_erp.almdina_erp.services.export_validation_service.get_validated_dxf_plan":
        "almdina_erp.almdina_erp.services.dxf_export_service.get_validated_dxf_plan",
    "almdina_erp.almdina_erp.services.actual_consumption_reversal.reverse_actual_consumption":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.actual_consumption_service.record_actual_consumption":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.order_creation_service.create_door_cutting_order":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.order_creation_service.get_new_order_defaults":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.performance_service.benchmark_order_cutting_engine":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.preflight_service.run_factory_preflight":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.remnant_service.generate_order_remnants":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.replacement_cancellation_service.cancel_replacement":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.cancel_legacy_replacement",
    "almdina_erp.almdina_erp.services.settings_access_service.get_stock_settings":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.settings_access_service.update_stock_settings":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.stock_availability_service.check_order_stock":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.stock_service.check_order_stock":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.stock_service.consume_order_materials":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.production_service.start_stage":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.start_legacy_stage",
    "almdina_erp.almdina_erp.services.production_service.finish_stage":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.finish_legacy_stage",
    "almdina_erp.almdina_erp.services.production_service.pause_stage":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.production_service.resume_stage":
        "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_shop_floor_context":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_shop_floor_context",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_dispatch_options":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_dispatch_options",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_revert_targets":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_revert_targets",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_my_inbox":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_inbox",
    "almdina_erp.almdina_erp.services.shop_floor_service.get_my_archive":
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_archive",
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
    "almdina_erp.almdina_erp.services.shop_floor_service.get_handoff_context":
        "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_context",
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
        "almdina_erp.almdina_erp.services.order_revision_service.return_order_to_draft",
    "almdina_erp.almdina_erp.services.shop_floor_commands.return_order_to_draft":
        "almdina_erp.almdina_erp.services.order_revision_service.return_order_to_draft",
}
