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
    CANCEL_ORDER = "cancel_order"

    # Costing and customer documents
    VIEW_COSTS = "view_costs"
    EDIT_COST_SETTINGS = "edit_cost_settings"
    EDIT_SPECIAL_PRICE = "edit_special_price"
    APPROVE_SPECIAL_PRICE = "approve_special_price"
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

    # Administration
    MANAGE_FACTORY_SETTINGS = "manage_factory_settings"
    MANAGE_USERS = "manage_users"
    MANAGE_PERMISSIONS = "manage_permissions"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Framework-independent metadata for one assignable business capability.

    ``permission_type`` is the Frappe permission checked by the infrastructure
    adapter. Standard rights such as ``read``, ``create`` and ``write`` are
    reused instead of adding confusing duplicate columns to Role Permission
    Manager.
    """

    key: str
    permission_type: str
    applies_to: str
    category: str
    custom: bool = True


_ORDER_DOCTYPE = "Door Cutting Order"
_SETTINGS_DOCTYPE = "Almdina ERP Settings"

_CAPABILITY_DEFINITIONS = (
    CapabilityDefinition(Capability.VIEW_ORDERS, "read", _ORDER_DOCTYPE, "order", False),
    CapabilityDefinition(Capability.CREATE_ORDER, "create", _ORDER_DOCTYPE, "order", False),
    CapabilityDefinition(Capability.EDIT_ORDER, "write", _ORDER_DOCTYPE, "order", False),
    CapabilityDefinition(Capability.CREATE_ORDER_REVISION, Capability.CREATE_ORDER_REVISION, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.SUBMIT_ORDER, Capability.SUBMIT_ORDER, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.APPROVE_ORDER, Capability.APPROVE_ORDER, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.CANCEL_ORDER, Capability.CANCEL_ORDER, _ORDER_DOCTYPE, "order"),
    CapabilityDefinition(Capability.VIEW_COSTS, Capability.VIEW_COSTS, _ORDER_DOCTYPE, "costing"),
    CapabilityDefinition(Capability.EDIT_COST_SETTINGS, Capability.EDIT_COST_SETTINGS, _ORDER_DOCTYPE, "costing"),
    CapabilityDefinition(Capability.EDIT_SPECIAL_PRICE, Capability.EDIT_SPECIAL_PRICE, _ORDER_DOCTYPE, "costing"),
    CapabilityDefinition(Capability.APPROVE_SPECIAL_PRICE, Capability.APPROVE_SPECIAL_PRICE, _ORDER_DOCTYPE, "costing"),
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
    CapabilityDefinition(Capability.MANAGE_FACTORY_SETTINGS, Capability.MANAGE_FACTORY_SETTINGS, _SETTINGS_DOCTYPE, "administration"),
    CapabilityDefinition(Capability.MANAGE_USERS, Capability.MANAGE_USERS, _SETTINGS_DOCTYPE, "administration"),
    CapabilityDefinition(Capability.MANAGE_PERMISSIONS, Capability.MANAGE_PERMISSIONS, _SETTINGS_DOCTYPE, "administration"),
)

CAPABILITY_CATALOG = MappingProxyType(
    {definition.key: definition for definition in _CAPABILITY_DEFINITIONS}
)
ALL_CAPABILITIES = frozenset(CAPABILITY_CATALOG)
CUSTOM_PERMISSION_DEFINITIONS = tuple(
    definition for definition in _CAPABILITY_DEFINITIONS if definition.custom
)

ORDER_CAPABILITIES = frozenset(
    capability
    for capability, definition in CAPABILITY_CATALOG.items()
    if definition.category == "order"
)
COSTING_CAPABILITIES = frozenset(
    capability
    for capability, definition in CAPABILITY_CATALOG.items()
    if definition.category in {"costing", "documents"}
)
PLANNING_CAPABILITIES = frozenset(
    capability
    for capability, definition in CAPABILITY_CATALOG.items()
    if definition.category == "cutting_plan"
)
DRAWING_CAPABILITIES = frozenset(
    capability
    for capability, definition in CAPABILITY_CATALOG.items()
    if definition.category == "drawing"
)
PRODUCTION_CAPABILITIES = frozenset(
    capability
    for capability, definition in CAPABILITY_CATALOG.items()
    if definition.category == "production"
)
ADMINISTRATION_CAPABILITIES = frozenset(
    capability
    for capability, definition in CAPABILITY_CATALOG.items()
    if definition.category == "administration"
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
    }
)
PRODUCTION_SUPERVISOR_CAPABILITIES = frozenset(
    {
        Capability.DISPATCH_ORDER,
        Capability.REVERT_DEPARTMENT,
        Capability.MARK_DELIVERED,
        Capability.REASSIGN_WORKER,
        Capability.RETURN_ORDER_TO_DRAFT,
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
    """Return a complete deterministic flag map for presentation adapters."""

    granted = normalize_capabilities(capabilities)
    return {capability: capability in granted for capability in sorted(ALL_CAPABILITIES)}


def has_capability(capabilities: Iterable[str] | None, capability: str) -> bool:
    capability_definition(capability)
    return capability in normalize_capabilities(capabilities)


def normalize_roles(roles: Iterable[str] | None) -> frozenset[str]:
    """Compatibility helper for operational adapters; never drives navigation."""

    return frozenset(str(role) for role in (roles or ()) if role)


__all__ = [
    "ADMINISTRATION_CAPABILITIES",
    "ALL_CAPABILITIES",
    "CAPABILITY_CATALOG",
    "COSTING_CAPABILITIES",
    "CUSTOM_PERMISSION_DEFINITIONS",
    "DRAWING_CAPABILITIES",
    "ORDER_CAPABILITIES",
    "PLANNING_CAPABILITIES",
    "PRODUCTION_CAPABILITIES",
    "PRODUCTION_OPERATOR_CAPABILITIES",
    "PRODUCTION_SUPERVISOR_CAPABILITIES",
    "SHOP_FLOOR_ACCESS_CAPABILITIES",
    "Capability",
    "CapabilityDefinition",
    "capability_definition",
    "capability_flags",
    "has_capability",
    "normalize_capabilities",
    "normalize_roles",
]
