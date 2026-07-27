from __future__ import annotations

from collections.abc import Iterable


class Capability:
    """Stable business capabilities independent from Frappe role APIs."""

    CREATE_ORDER = "create_order"
    EDIT_ORDER = "edit_order"
    SUBMIT_ORDER = "submit_order"
    APPROVE_ORDER = "approve_order"
    DISPATCH_ORDER = "dispatch_order"
    START_ASSIGNED_STAGE = "start_assigned_stage"
    HANDOFF_ASSIGNED_STAGE = "handoff_assigned_stage"
    REVERT_DEPARTMENT = "revert_department"
    RETURN_ORDER_TO_DRAFT = "return_order_to_draft"
    MARK_DELIVERED = "mark_delivered"
    VIEW_COSTS = "view_costs"
    EDIT_SPECIAL_PRICE = "edit_special_price"
    MANAGE_STOCK = "manage_stock"
    MANAGE_USERS = "manage_users"


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
        "Stock Manager",
        "Accounts Management",
    }
)

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "Order Entry": frozenset(
        {
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.SUBMIT_ORDER,
        }
    ),
    "Production Manager": frozenset(
        {
            Capability.EDIT_ORDER,
            Capability.SUBMIT_ORDER,
            Capability.APPROVE_ORDER,
            Capability.DISPATCH_ORDER,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
            Capability.REVERT_DEPARTMENT,
            Capability.RETURN_ORDER_TO_DRAFT,
            Capability.MARK_DELIVERED,
            Capability.VIEW_COSTS,
        }
    ),
    "عامل رسم": frozenset(
        {Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE}
    ),
    "عامل شريون": frozenset(
        {Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE}
    ),
    "عامل CNC": frozenset(
        {Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE}
    ),
    "عامل تقشيط": frozenset(
        {Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE}
    ),
    "Cutting Operator": frozenset(
        {Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE}
    ),
    "Edge Operator": frozenset(
        {Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE}
    ),
    "Accounts Management": frozenset(
        {Capability.VIEW_COSTS, Capability.EDIT_SPECIAL_PRICE}
    ),
    "Stock Manager": frozenset({Capability.MANAGE_STOCK}),
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
