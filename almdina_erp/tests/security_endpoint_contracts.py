from __future__ import annotations

from types import MappingProxyType


class EndpointAuthorizationContract:
    """Static authorization ownership for one Frappe-whitelisted endpoint."""

    CAPABILITY = "capability"
    DELEGATE = "delegate"
    FAIL_CLOSED = "fail_closed"
    SELF_CONTEXT = "self_context"


def _contracts(module: str, contract: str, *functions: str) -> dict[str, str]:
    return {f"{module}.{function}": contract for function in functions}


C = EndpointAuthorizationContract.CAPABILITY
D = EndpointAuthorizationContract.DELEGATE
F = EndpointAuthorizationContract.FAIL_CLOSED
S = EndpointAuthorizationContract.SELF_CONTEXT

_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("almdina_erp.almdina_erp.api", C, ("get_approved_cutting_plan_snapshot", "preview_door_cutting_order")),
    ("almdina_erp.almdina_erp.doctype.door_cutting_order.door_cutting_order", D, ("recalculate_order",)),
    ("almdina_erp.almdina_erp.services.approval_queue_service", C, ("approve_order_safely", "get_approval_queue_context", "get_pending_review_orders", "reject_order_safely")),
    ("almdina_erp.almdina_erp.services.archive_service", C, ("archive_approved_plan_pdf", "get_archive_context")),
    ("almdina_erp.almdina_erp.services.cost_document_service", C, ("get_customer_invoice_document", "get_internal_cost_report_document")),
    ("almdina_erp.almdina_erp.services.cost_permission_service", C, ("approve_special_piece_price", "get_order_cost_snapshot", "update_clipped_corner_edge_price", "update_order_cost_settings")),
    ("almdina_erp.almdina_erp.services.cost_service", C, ("refresh_order_costs",)),
    ("almdina_erp.almdina_erp.services.cutting_plan_command_service", C, ("recalculate_order_plan",)),
    ("almdina_erp.almdina_erp.services.cutting_plan_preview_service", C, ("commit_cutting_plan_preview", "preview_cutting_plan")),
    ("almdina_erp.almdina_erp.services.cutting_plan_workspace_query_service", C, ("get_plan_workspace_snapshot",)),
    ("almdina_erp.almdina_erp.services.cutting_plan_service", D, ("approve_order", "lock_cutting_plan", "reject_order", "send_order_to_production", "submit_order_for_review")),
    ("almdina_erp.almdina_erp.services.drawing_approval_service", C, ("approve_production_dxf", "cancel_production_plan_approval")),
    ("almdina_erp.almdina_erp.services.dxf_export_service", C, ("get_validated_dxf_plan",)),
    ("almdina_erp.almdina_erp.services.edge_banding_lookup_service", C, ("get_order_edge_banding_options", "save_order_edge_banding_override")),
    ("almdina_erp.almdina_erp.services.export_validation_service", D, ("get_validated_dxf_plan",)),
    ("almdina_erp.almdina_erp.services.legacy_endpoint_service", D, ("cancel_legacy_replacement", "finish_legacy_stage", "start_legacy_stage")),
    ("almdina_erp.almdina_erp.services.legacy_endpoint_service", F, ("retired_product_endpoint",)),
    ("almdina_erp.almdina_erp.services.master_data_service", C, ("delete_master_data_record", "delete_production_routing", "get_master_data_console", "get_production_routing_console", "save_production_routing", "search_operational_roles", "set_master_data_disabled", "set_production_routing_disabled")),
    ("almdina_erp.almdina_erp.services.master_data_service", S, ("can_open_master_data",)),
    ("almdina_erp.almdina_erp.services.order_approval_service", C, ("approve_order",)),
    ("almdina_erp.almdina_erp.services.order_cancellation", C, ("cancel_order",)),
    ("almdina_erp.almdina_erp.services.order_defaults_service", C, ("get_order_defaults",)),
    ("almdina_erp.almdina_erp.services.order_dispatch_service", C, ("dispatch_order", "validate_order_for_dispatch")),
    ("almdina_erp.almdina_erp.services.order_lifecycle_permission_service", C, ("get_order_lifecycle_context", "submit_order_for_review")),
    ("almdina_erp.almdina_erp.services.order_lifecycle_service", C, ("cancel_order", "return_order_to_draft")),
    ("almdina_erp.almdina_erp.services.order_plan_permission_service", C, ("recalculate_order", "simulate_optimizer_plan")),
    ("almdina_erp.almdina_erp.services.plan_settings_edit_service", C, ("save_plan_settings",)),
    ("almdina_erp.almdina_erp.services.order_review_service", C, ("reject_order",)),
    ("almdina_erp.almdina_erp.services.order_revision_service", C, ("create_order_revision", "return_order_to_draft")),
    ("almdina_erp.almdina_erp.services.permission_context_service", S, ("get_permission_context",)),
    ("almdina_erp.almdina_erp.services.permission_management_service", C, ("export_permission_bundle", "export_role_permissions", "get_permission_audit", "get_permission_console", "get_role_permissions", "import_permission_bundle", "preview_permission_bundle_import", "preview_permission_import", "preview_role_permissions", "update_role_permissions")),
    ("almdina_erp.almdina_erp.services.production_service", D, ("finish_stage", "start_stage")),
    ("almdina_erp.almdina_erp.services.production_service", F, ("pause_stage", "resume_stage")),
    ("almdina_erp.almdina_erp.services.production_settings_service", C, ("get_factory_settings_audit", "get_print_identity", "get_production_settings", "update_production_settings")),
    ("almdina_erp.almdina_erp.services.production_worker_service", C, ("get_reassignment_workers",)),
    ("almdina_erp.almdina_erp.services.replacement_approval", C, ("approve_replacement",)),
    ("almdina_erp.almdina_erp.services.replacement_completion", C, ("complete_replacement",)),
    ("almdina_erp.almdina_erp.services.replacement_creation_service", C, ("create_replacement_from_incident", "record_incident")),
    ("almdina_erp.almdina_erp.services.replacement_execution", C, ("cancel_replacement", "start_replacement")),
    ("almdina_erp.almdina_erp.services.replacement_permission_service", C, ("get_replacement_context",)),
    ("almdina_erp.almdina_erp.services.replacement_service", D, ("approve_replacement", "cancel_replacement", "complete_replacement", "create_replacement_from_incident", "record_incident", "start_replacement")),
    ("almdina_erp.almdina_erp.services.report_permission_service", C, ("get_report_access_context",)),
    ("almdina_erp.almdina_erp.services.shop_floor_commands", C, ("dispatch_order", "get_handoff_context", "get_handoff_workers", "handoff_to_next", "mark_delivered", "reassign_worker", "return_order_to_draft", "revert_department", "start_my_stage")),
    ("almdina_erp.almdina_erp.services.shop_floor_dxf_service", C, ("approve_production_dxf", "mark_dxf_exported", "recalculate_drawing_plan", "upload_production_dxf")),
    ("almdina_erp.almdina_erp.services.shop_floor_query_service", C, ("get_current_stage_context", "get_dispatch_options", "get_my_archive", "get_my_inbox", "get_order_operational_role_flags", "get_revert_targets", "get_shop_floor_context")),
    ("almdina_erp.almdina_erp.services.special_shape_service", D, ("approve_special_piece_price",)),
    ("almdina_erp.almdina_erp.services.special_shape_workspace_service", C, ("get_drawing_workspace", "remove_reference_image", "save_documentation_workspace", "upload_reference_image")),
    ("almdina_erp.almdina_erp.services.workforce_service", C, ("adopt_workforce_user", "create_workforce_user", "get_workforce_console", "get_workforce_user_audit", "reset_workforce_password", "set_workforce_user_enabled", "update_workforce_user")),
)

_CONTRACTS: dict[str, str] = {}
for module, contract, functions in _GROUPS:
    _CONTRACTS.update(_contracts(module, contract, *functions))

WHITELISTED_ENDPOINT_CONTRACTS = MappingProxyType(_CONTRACTS)


__all__ = [
    "EndpointAuthorizationContract",
    "WHITELISTED_ENDPOINT_CONTRACTS",
]
