from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType


class Capability:
    """Stable business capability keys used by UI and server authorization."""

    # Order lifecycle
    VIEW_ORDERS = "view_orders"
    CREATE_ORDER = "create_order"
    EDIT_ORDER = "edit_order"
    CREATE_ORDER_REVISION = "create_order_revision"
    SUBMIT_ORDER = "submit_order"
    APPROVE_ORDER = "approve_order"
    REJECT_ORDER = "reject_order"
    CANCEL_ORDER = "cancel_order"

    # Costing and customer documents
    VIEW_COSTS = "view_costs"
    EDIT_COST_SETTINGS = "edit_cost_settings"
    EDIT_SPECIAL_PRICE = "edit_special_price"
    APPROVE_SPECIAL_PRICE = "approve_special_price"
    EDIT_REPLACEMENT_COST = "edit_replacement_cost"
    PRINT_MEASUREMENTS = "print_measurements"
    PRINT_CUSTOMER_INVOICE = "print_customer_invoice"
    PRINT_INTERNAL_COST_REPORT = "print_internal_cost_report"

    # Cutting plans, drawings, and DXF
    VIEW_CUTTING_PLAN = "view_cutting_plan"
    RECALCULATE_PLAN = "recalculate_plan"
    EDIT_OPTIMIZER_SETTINGS = "edit_optimizer_settings"
    PRINT_CUTTING_PLAN = "print_cutting_plan"
    VIEW_DRAWING_WORKSPACE = "view_drawing_workspace"
    EDIT_SPECIAL_DRAWING = "edit_special_drawing"
    EXPORT_DXF = "export_dxf"
    UPLOAD_DXF = "upload_dxf"
    REPLACE_DXF = "replace_dxf"
    APPROVE_DXF = "approve_dxf"

    # Production workflow
    DISPATCH_ORDER = "dispatch_order"
    START_ASSIGNED_STAGE = "start_assigned_stage"
    HANDOFF_ASSIGNED_STAGE = "handoff_assigned_stage"
    REVERT_DEPARTMENT = "revert_department"
    RETURN_ORDER_TO_DRAFT = "return_order_to_draft"
    MARK_DELIVERED = "mark_delivered"
    REASSIGN_WORKER = "reassign_worker"

    # Control center and quality
    ARCHIVE_APPROVED_PLAN = "archive_approved_plan"
    VIEW_PRODUCTION_INCIDENTS = "view_production_incidents"
    RECORD_INCIDENT = "record_incident"
    CREATE_REPLACEMENT = "create_replacement"
    VIEW_REPLACEMENTS = "view_replacements"
    APPROVE_REPLACEMENT = "approve_replacement"
    START_REPLACEMENT = "start_replacement"
    COMPLETE_REPLACEMENT = "complete_replacement"
    CANCEL_REPLACEMENT = "cancel_replacement"

    # Reports
    VIEW_OPERATIONAL_REPORTS = "view_operational_reports"
    VIEW_FINANCIAL_REPORTS = "view_financial_reports"

    # Workforce administration
    VIEW_USERS = "view_users"
    CREATE_USERS = "create_users"
    EDIT_USERS = "edit_users"
    ASSIGN_USER_ROLES = "assign_user_roles"
    ENABLE_USERS = "enable_users"
    DISABLE_USERS = "disable_users"
    RESET_USER_PASSWORD = "reset_user_password"

    # Factory settings sections
    VIEW_FACTORY_SETTINGS = "view_factory_settings"
    EDIT_FACTORY_CUTTING_DEFAULTS = "edit_factory_cutting_defaults"
    EDIT_FACTORY_COST_DEFAULTS = "edit_factory_cost_defaults"
    EDIT_FACTORY_PRODUCTION_CONTROLS = "edit_factory_production_controls"

    # Master data
    VIEW_PRODUCTION_ROUTINGS = "view_production_routings"
    CREATE_PRODUCTION_ROUTINGS = "create_production_routings"
    EDIT_PRODUCTION_ROUTINGS = "edit_production_routings"
    DELETE_PRODUCTION_ROUTINGS = "delete_production_routings"
    VIEW_CUSTOMERS = "view_customers"
    VIEW_EDGE_BANDING_TYPES = "view_edge_banding_types"
    CREATE_EDGE_BANDING_TYPES = "create_edge_banding_types"
    EDIT_EDGE_BANDING_TYPES = "edit_edge_banding_types"
    DELETE_EDGE_BANDING_TYPES = "delete_edge_banding_types"

    # Administration
    MANAGE_PERMISSIONS = "manage_permissions"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Framework-independent metadata for one assignable business capability."""

    key: str
    permission_type: str
    applies_to: str
    category: str
    custom: bool = True


_ORDER_DOCTYPE = "Door Cutting Order"
_REPLACEMENT_DOCTYPE = "Replacement Piece"
_INCIDENT_DOCTYPE = "Production Incident"
_SETTINGS_DOCTYPE = "Almdina ERP Settings"
_ROUTING_DOCTYPE = "Production Routing"
_CUSTOMER_DOCTYPE = "Customer"
_EDGE_DOCTYPE = "Edge Banding Type"

_CAPABILITY_DEFINITIONS = (
    CapabilityDefinition(Capability.VIEW_ORDERS, "read", _ORDER_DOCTYPE, "order", False),
    CapabilityDefinition(Capability.CREATE_ORDER, "create", _ORDER_DOCTYPE, "order", False),
    CapabilityDefinition(Capability.EDIT_ORDER, "write", _ORDER_DOCTYPE, "order", False),
    CapabilityDefinition(Capability.CREATE_ORDER_REVISION, Capability.CREATE_ORDER_REVISION, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.SUBMIT_ORDER, Capability.SUBMIT_ORDER, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.APPROVE_ORDER, Capability.APPROVE_ORDER, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.REJECT_ORDER, Capability.REJECT_ORDER, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.CANCEL_ORDER, Capability.CANCEL_ORDER, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.VIEW_COSTS, Capability.VIEW_COSTS, _ORDER_DOCTYPE, "costing"),
    CapabilityDefinition(Capability.EDIT_COST_SETTINGS, Capability.EDIT_COST_SETTINGS, _ORDER_DOCTYPE, "costing"),
    CapabilityDefinition(Capability.EDIT_SPECIAL_PRICE, Capability.EDIT_SPECIAL_PRICE, _ORDER_DOCTYPE, "costing"),
    CapabilityDefinition(Capability.APPROVE_SPECIAL_PRICE, Capability.APPROVE_SPECIAL_PRICE, _ORDER_DOCTYPE, "costing"),
    CapabilityDefinition(Capability.EDIT_REPLACEMENT_COST, Capability.EDIT_REPLACEMENT_COST, _REPLACEMENT_DOCTYPE, "costing"),
    CapabilityDefinition(Capability.PRINT_MEASUREMENTS, Capability.PRINT_MEASUREMENTS, _ORDER_DOCTYPE, "documents"),
    CapabilityDefinition(Capability.PRINT_CUSTOMER_INVOICE, Capability.PRINT_CUSTOMER_INVOICE, _ORDER_DOCTYPE, "documents"),
    CapabilityDefinition(Capability.PRINT_INTERNAL_COST_REPORT, Capability.PRINT_INTERNAL_COST_REPORT, _ORDER_DOCTYPE, "documents"),
    CapabilityDefinition(Capability.VIEW_CUTTING_PLAN, Capability.VIEW_CUTTING_PLAN, _ORDER_DOCTYPE, "cutting_plan"),
    CapabilityDefinition(Capability.RECALCULATE_PLAN, Capability.RECALCULATE_PLAN, _ORDER_DOCTYPE, "cutting_plan"),
    CapabilityDefinition(Capability.EDIT_OPTIMIZER_SETTINGS, Capability.EDIT_OPTIMIZER_SETTINGS, _ORDER_DOCTYPE, "cutting_plan"),
    CapabilityDefinition(Capability.PRINT_CUTTING_PLAN, Capability.PRINT_CUTTING_PLAN, _ORDER_DOCTYPE, "cutting_plan"),
    CapabilityDefinition(Capability.VIEW_DRAWING_WORKSPACE, Capability.VIEW_DRAWING_WORKSPACE, _ORDER_DOCTYPE, "drawing"),
    CapabilityDefinition(Capability.EDIT_SPECIAL_DRAWING, Capability.EDIT_SPECIAL_DRAWING, _ORDER_DOCTYPE, "drawing"),
    CapabilityDefinition(Capability.EXPORT_DXF, Capability.EXPORT_DXF, _ORDER_DOCTYPE, "drawing"),
    CapabilityDefinition(Capability.UPLOAD_DXF, Capability.UPLOAD_DXF, _ORDER_DOCTYPE, "drawing"),
    CapabilityDefinition(Capability.REPLACE_DXF, Capability.REPLACE_DXF, _ORDER_DOCTYPE, "drawing"),
    CapabilityDefinition(Capability.APPROVE_DXF, Capability.APPROVE_DXF, _ORDER_DOCTYPE, "drawing"),
    CapabilityDefinition(Capability.DISPATCH_ORDER, Capability.DISPATCH_ORDER, _ORDER_DOCTYPE, "production"),
    CapabilityDefinition(Capability.START_ASSIGNED_STAGE, Capability.START_ASSIGNED_STAGE, _ORDER_DOCTYPE, "production"),
    CapabilityDefinition(Capability.HANDOFF_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE, _ORDER_DOCTYPE, "production"),
    CapabilityDefinition(Capability.REVERT_DEPARTMENT, Capability.REVERT_DEPARTMENT, _ORDER_DOCTYPE, "production"),
    CapabilityDefinition(Capability.RETURN_ORDER_TO_DRAFT, Capability.RETURN_ORDER_TO_DRAFT, _ORDER_DOCTYPE, "production"),
    CapabilityDefinition(Capability.MARK_DELIVERED, Capability.MARK_DELIVERED, _ORDER_DOCTYPE, "production"),
    CapabilityDefinition(Capability.REASSIGN_WORKER, Capability.REASSIGN_WORKER, _ORDER_DOCTYPE, "production"),
    CapabilityDefinition(Capability.ARCHIVE_APPROVED_PLAN, Capability.ARCHIVE_APPROVED_PLAN, _ORDER_DOCTYPE, "control_center"),
    CapabilityDefinition(Capability.VIEW_PRODUCTION_INCIDENTS, "read", _INCIDENT_DOCTYPE, "control_center", False),
    CapabilityDefinition(Capability.RECORD_INCIDENT, Capability.RECORD_INCIDENT, _ORDER_DOCTYPE, "control_center"),
    CapabilityDefinition(Capability.CREATE_REPLACEMENT, Capability.CREATE_REPLACEMENT, _ORDER_DOCTYPE, "control_center"),
    CapabilityDefinition(Capability.VIEW_REPLACEMENTS, Capability.VIEW_REPLACEMENTS, _REPLACEMENT_DOCTYPE, "control_center"),
    CapabilityDefinition(Capability.APPROVE_REPLACEMENT, Capability.APPROVE_REPLACEMENT, _REPLACEMENT_DOCTYPE, "control_center"),
    CapabilityDefinition(Capability.START_REPLACEMENT, Capability.START_REPLACEMENT, _REPLACEMENT_DOCTYPE, "control_center"),
    CapabilityDefinition(Capability.COMPLETE_REPLACEMENT, Capability.COMPLETE_REPLACEMENT, _REPLACEMENT_DOCTYPE, "control_center"),
    CapabilityDefinition(Capability.CANCEL_REPLACEMENT, Capability.CANCEL_REPLACEMENT, _REPLACEMENT_DOCTYPE, "control_center"),
    CapabilityDefinition(Capability.VIEW_OPERATIONAL_REPORTS, Capability.VIEW_OPERATIONAL_REPORTS, _ORDER_DOCTYPE, "reports"),
    CapabilityDefinition(Capability.VIEW_FINANCIAL_REPORTS, Capability.VIEW_FINANCIAL_REPORTS, _ORDER_DOCTYPE, "reports"),
    CapabilityDefinition(Capability.VIEW_USERS, Capability.VIEW_USERS, _SETTINGS_DOCTYPE, "workforce"),
    CapabilityDefinition(Capability.CREATE_USERS, Capability.CREATE_USERS, _SETTINGS_DOCTYPE, "workforce"),
    CapabilityDefinition(Capability.EDIT_USERS, Capability.EDIT_USERS, _SETTINGS_DOCTYPE, "workforce"),
    CapabilityDefinition(Capability.ASSIGN_USER_ROLES, Capability.ASSIGN_USER_ROLES, _SETTINGS_DOCTYPE, "workforce"),
    CapabilityDefinition(Capability.ENABLE_USERS, Capability.ENABLE_USERS, _SETTINGS_DOCTYPE, "workforce"),
    CapabilityDefinition(Capability.DISABLE_USERS, Capability.DISABLE_USERS, _SETTINGS_DOCTYPE, "workforce"),
    CapabilityDefinition(Capability.RESET_USER_PASSWORD, Capability.RESET_USER_PASSWORD, _SETTINGS_DOCTYPE, "workforce"),
    CapabilityDefinition(Capability.VIEW_FACTORY_SETTINGS, "read", _SETTINGS_DOCTYPE, "factory_settings", False),
    CapabilityDefinition(Capability.EDIT_FACTORY_CUTTING_DEFAULTS, Capability.EDIT_FACTORY_CUTTING_DEFAULTS, _SETTINGS_DOCTYPE, "factory_settings"),
    CapabilityDefinition(Capability.EDIT_FACTORY_COST_DEFAULTS, Capability.EDIT_FACTORY_COST_DEFAULTS, _SETTINGS_DOCTYPE, "factory_settings"),
    CapabilityDefinition(Capability.EDIT_FACTORY_PRODUCTION_CONTROLS, Capability.EDIT_FACTORY_PRODUCTION_CONTROLS, _SETTINGS_DOCTYPE, "factory_settings"),
    CapabilityDefinition(Capability.VIEW_PRODUCTION_ROUTINGS, "read", _ROUTING_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.CREATE_PRODUCTION_ROUTINGS, "create", _ROUTING_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.EDIT_PRODUCTION_ROUTINGS, "write", _ROUTING_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.DELETE_PRODUCTION_ROUTINGS, "delete", _ROUTING_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.VIEW_CUSTOMERS, "read", _CUSTOMER_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.VIEW_EDGE_BANDING_TYPES, "read", _EDGE_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.CREATE_EDGE_BANDING_TYPES, "create", _EDGE_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.EDIT_EDGE_BANDING_TYPES, "write", _EDGE_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.DELETE_EDGE_BANDING_TYPES, "delete", _EDGE_DOCTYPE, "master_data", False),
    CapabilityDefinition(Capability.MANAGE_PERMISSIONS, Capability.MANAGE_PERMISSIONS, _SETTINGS_DOCTYPE, "administration"),
)

CAPABILITY_CATALOG = MappingProxyType(
    {definition.key: definition for definition in _CAPABILITY_DEFINITIONS}
)
ALL_CAPABILITIES = frozenset(CAPABILITY_CATALOG)
CUSTOM_PERMISSION_DEFINITIONS = tuple(
    definition for definition in _CAPABILITY_DEFINITIONS if definition.custom
)


def _category_capabilities(*categories: str) -> frozenset[str]:
    requested = frozenset(categories)
    return frozenset(
        capability
        for capability, definition in CAPABILITY_CATALOG.items()
        if definition.category in requested
    )


ORDER_CAPABILITIES = _category_capabilities("order")
COSTING_CAPABILITIES = _category_capabilities("costing", "documents")
PLANNING_CAPABILITIES = _category_capabilities("cutting_plan")
DRAWING_CAPABILITIES = _category_capabilities("drawing")
PRODUCTION_CAPABILITIES = _category_capabilities("production")
CONTROL_CENTER_CAPABILITIES = _category_capabilities("control_center") | frozenset(
    {Capability.APPROVE_ORDER, Capability.REJECT_ORDER}
)
REPORTING_CAPABILITIES = _category_capabilities("reports")
WORKFORCE_CAPABILITIES = _category_capabilities("workforce")
FACTORY_SETTINGS_CAPABILITIES = _category_capabilities("factory_settings")
MASTER_DATA_CAPABILITIES = _category_capabilities("master_data")
ADMINISTRATION_CAPABILITIES = (
    _category_capabilities("administration")
    | FACTORY_SETTINGS_CAPABILITIES
    | MASTER_DATA_CAPABILITIES
)

PRODUCTION_OPERATOR_CAPABILITIES = frozenset(
    {
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
        Capability.VIEW_CUTTING_PLAN,
        Capability.PRINT_CUTTING_PLAN,
        Capability.VIEW_DRAWING_WORKSPACE,
        Capability.EDIT_SPECIAL_DRAWING,
        Capability.EXPORT_DXF,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.APPROVE_DXF,
        Capability.RECALCULATE_PLAN,
        Capability.RECORD_INCIDENT,
        Capability.START_REPLACEMENT,
        Capability.COMPLETE_REPLACEMENT,
    }
)
PRODUCTION_SUPERVISOR_CAPABILITIES = frozenset(
    {
        Capability.DISPATCH_ORDER,
        Capability.REVERT_DEPARTMENT,
        Capability.MARK_DELIVERED,
        Capability.REASSIGN_WORKER,
        Capability.RETURN_ORDER_TO_DRAFT,
        Capability.CREATE_REPLACEMENT,
        Capability.APPROVE_REPLACEMENT,
        Capability.CANCEL_REPLACEMENT,
    }
)
SHOP_FLOOR_ACCESS_CAPABILITIES = frozenset(
    PRODUCTION_OPERATOR_CAPABILITIES | PRODUCTION_SUPERVISOR_CAPABILITIES
)


def capability_definition(capability: str) -> CapabilityDefinition:
    try:
        return CAPABILITY_CATALOG[capability]
    except KeyError as exc:
        raise ValueError(f"Unknown capability: {capability}") from exc


def normalize_capabilities(capabilities: Iterable[str] | None) -> frozenset[str]:
    normalized = frozenset(str(value) for value in (capabilities or ()) if value)
    unknown = normalized.difference(ALL_CAPABILITIES)
    if unknown:
        raise ValueError(f"Unknown capabilities: {', '.join(sorted(unknown))}")
    return normalized


def capability_flags(capabilities: Iterable[str] | None) -> dict[str, bool]:
    granted = normalize_capabilities(capabilities)
    return {
        capability: capability in granted for capability in sorted(ALL_CAPABILITIES)
    }


def has_capability(capabilities: Iterable[str] | None, capability: str) -> bool:
    capability_definition(capability)
    return capability in normalize_capabilities(capabilities)


def normalize_roles(roles: Iterable[str] | None) -> frozenset[str]:
    return frozenset(str(role) for role in (roles or ()) if role)


__all__ = [
    "ADMINISTRATION_CAPABILITIES",
    "ALL_CAPABILITIES",
    "CAPABILITY_CATALOG",
    "CONTROL_CENTER_CAPABILITIES",
    "COSTING_CAPABILITIES",
    "CUSTOM_PERMISSION_DEFINITIONS",
    "DRAWING_CAPABILITIES",
    "FACTORY_SETTINGS_CAPABILITIES",
    "MASTER_DATA_CAPABILITIES",
    "ORDER_CAPABILITIES",
    "PLANNING_CAPABILITIES",
    "PRODUCTION_CAPABILITIES",
    "PRODUCTION_OPERATOR_CAPABILITIES",
    "PRODUCTION_SUPERVISOR_CAPABILITIES",
    "REPORTING_CAPABILITIES",
    "SHOP_FLOOR_ACCESS_CAPABILITIES",
    "WORKFORCE_CAPABILITIES",
    "Capability",
    "CapabilityDefinition",
    "capability_definition",
    "capability_flags",
    "has_capability",
    "normalize_capabilities",
    "normalize_roles",
]
