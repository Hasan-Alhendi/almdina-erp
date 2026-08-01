from __future__ import annotations

from collections.abc import Iterable, Mapping


class Capability:
    """Stable business capabilities independent from Frappe role APIs.

    Capabilities describe what a user may do. They intentionally do not encode
    document state, assignment, or Frappe UI concerns; adapters combine those
    runtime rules with this role policy before allowing an action.
    """

    # Order lifecycle
    CREATE_ORDER = "create_order"
    EDIT_ORDER = "edit_order"
    CREATE_ORDER_REVISION = "create_order_revision"
    SUBMIT_ORDER = "submit_order"
    APPROVE_ORDER = "approve_order"

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


ALL_CAPABILITIES = frozenset(
    value
    for name, value in vars(Capability).items()
    if name.isupper() and isinstance(value, str)
)

SHOP_FLOOR_ROLES = frozenset({"عامل رسم", "عامل شريون", "عامل CNC", "عامل تقشيط"})
ADMIN_CONTEXT_ROLES = frozenset(
    {
        "System Manager",
        "Production Manager",
        "Order Entry",
        "Accounts Management",
    }
)

# This is the default product policy. Frappe adapters may later merge explicit
# Custom Permission Types, but the domain vocabulary and safe defaults remain
# centralized here so UI and server actions cannot invent separate role rules.
ROLE_CAPABILITIES: Mapping[str, frozenset[str]] = {
    "Order Entry": frozenset(
        {
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.CREATE_ORDER_REVISION,
            Capability.SUBMIT_ORDER,
            Capability.VIEW_CUTTING_PLAN,
            Capability.PRINT_MEASUREMENTS,
            Capability.PRINT_CUSTOMER_INVOICE,
        }
    ),
    "Production Manager": frozenset(
        {
            Capability.EDIT_ORDER,
            Capability.CREATE_ORDER_REVISION,
            Capability.SUBMIT_ORDER,
            Capability.APPROVE_ORDER,
            Capability.VIEW_COSTS,
            Capability.EDIT_COST_SETTINGS,
            Capability.EDIT_SPECIAL_PRICE,
            Capability.APPROVE_SPECIAL_PRICE,
            Capability.PRINT_MEASUREMENTS,
            Capability.PRINT_CUSTOMER_INVOICE,
            Capability.PRINT_INTERNAL_COST_REPORT,
            Capability.VIEW_CUTTING_PLAN,
            Capability.RECALCULATE_PLAN,
            Capability.EDIT_OPTIMIZER_SETTINGS,
            Capability.PRINT_CUTTING_PLAN,
            Capability.VIEW_DRAWING_WORKSPACE,
            Capability.EDIT_SPECIAL_DRAWING,
            Capability.EXPORT_DXF,
            Capability.UPLOAD_DXF,
            Capability.REPLACE_DXF,
            Capability.APPROVE_DXF,
            Capability.DISPATCH_ORDER,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
            Capability.REVERT_DEPARTMENT,
            Capability.RETURN_ORDER_TO_DRAFT,
            Capability.MARK_DELIVERED,
            Capability.REASSIGN_WORKER,
            Capability.MANAGE_FACTORY_SETTINGS,
        }
    ),
    "عامل رسم": frozenset(
        {
            Capability.VIEW_CUTTING_PLAN,
            Capability.RECALCULATE_PLAN,
            Capability.PRINT_CUTTING_PLAN,
            Capability.VIEW_DRAWING_WORKSPACE,
            Capability.EDIT_SPECIAL_DRAWING,
            Capability.EXPORT_DXF,
            Capability.UPLOAD_DXF,
            Capability.REPLACE_DXF,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
    ),
    "عامل شريون": frozenset(
        {
            Capability.VIEW_CUTTING_PLAN,
            Capability.PRINT_CUTTING_PLAN,
            Capability.PRINT_MEASUREMENTS,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
    ),
    "عامل CNC": frozenset(
        {
            Capability.VIEW_CUTTING_PLAN,
            Capability.PRINT_CUTTING_PLAN,
            Capability.VIEW_DRAWING_WORKSPACE,
            Capability.EXPORT_DXF,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
    ),
    "عامل تقشيط": frozenset(
        {
            Capability.PRINT_MEASUREMENTS,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
    ),
    "Cutting Operator": frozenset(
        {
            Capability.VIEW_CUTTING_PLAN,
            Capability.PRINT_CUTTING_PLAN,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
    ),
    "Edge Operator": frozenset(
        {
            Capability.PRINT_MEASUREMENTS,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
    ),
    "Accounts Management": frozenset(
        {
            Capability.VIEW_COSTS,
            Capability.EDIT_SPECIAL_PRICE,
            Capability.APPROVE_SPECIAL_PRICE,
            Capability.PRINT_CUSTOMER_INVOICE,
            Capability.PRINT_INTERNAL_COST_REPORT,
        }
    ),
}


def normalize_roles(roles: Iterable[str] | None) -> frozenset[str]:
    return frozenset(str(role) for role in (roles or ()) if role)


def capabilities_for_roles(roles: Iterable[str] | None) -> frozenset[str]:
    normalized = normalize_roles(roles)
    if normalized.intersection({"System Manager", "Administrator"}):
        return ALL_CAPABILITIES

    granted: set[str] = set()
    for role in normalized:
        granted.update(ROLE_CAPABILITIES.get(role, ()))
    return frozenset(granted)


def capability_flags_for_roles(roles: Iterable[str] | None) -> dict[str, bool]:
    """Return a deterministic JSON-safe capability map for presentation adapters."""

    granted = capabilities_for_roles(roles)
    return {capability: capability in granted for capability in sorted(ALL_CAPABILITIES)}


def has_capability(roles: Iterable[str] | None, capability: str) -> bool:
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"Unknown capability: {capability}")
    return capability in capabilities_for_roles(roles)


def is_order_entry_profile(roles: Iterable[str] | None) -> bool:
    """Return whether Desk should use the order-entry navigation profile."""

    normalized = normalize_roles(roles)
    if normalized.intersection({"System Manager", "Administrator"}):
        return False
    return "Order Entry" in normalized


def is_shop_floor_only(roles: Iterable[str] | None) -> bool:
    """Return whether the user is an operator without an administrative context."""

    normalized = normalize_roles(roles)
    if normalized.intersection(ADMIN_CONTEXT_ROLES):
        return False
    return bool(normalized.intersection(SHOP_FLOOR_ROLES))
