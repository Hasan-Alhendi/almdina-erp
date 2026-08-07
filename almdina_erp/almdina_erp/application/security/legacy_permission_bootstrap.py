from __future__ import annotations

from types import MappingProxyType

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import ALL_CAPABILITIES, Capability


_ORDER_ENTRY = frozenset(
    {
        Capability.VIEW_ORDERS,
        Capability.CREATE_ORDER,
        Capability.EDIT_ORDER,
        Capability.SUBMIT_ORDER,
        Capability.PRINT_MEASUREMENTS,
        Capability.PRINT_CUSTOMER_INVOICE,
    }
)
_PLANNER_DESIGNER = frozenset(
    {
        Capability.VIEW_ORDERS,
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
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
    }
)
_PRODUCTION_OPERATOR = frozenset(
    {
        Capability.VIEW_ORDERS,
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
        Capability.VIEW_CUTTING_PLAN,
        Capability.PRINT_CUTTING_PLAN,
        Capability.RECORD_INCIDENT,
        Capability.VIEW_REPLACEMENTS,
        Capability.START_REPLACEMENT,
        Capability.COMPLETE_REPLACEMENT,
    }
)
_PRODUCTION_SUPERVISOR = frozenset(
    {
        Capability.VIEW_ORDERS,
        Capability.VIEW_CUTTING_PLAN,
        Capability.DISPATCH_ORDER,
        Capability.REVERT_DEPARTMENT,
        Capability.RETURN_ORDER_TO_DRAFT,
        Capability.MARK_DELIVERED,
        Capability.REASSIGN_WORKER,
        Capability.CREATE_REPLACEMENT,
        Capability.VIEW_REPLACEMENTS,
        Capability.APPROVE_REPLACEMENT,
        Capability.CANCEL_REPLACEMENT,
        Capability.VIEW_OPERATIONAL_REPORTS,
    }
)
_PRICING_AND_DOCUMENTS = frozenset(
    {
        Capability.VIEW_ORDERS,
        Capability.VIEW_COSTS,
        Capability.EDIT_COST_SETTINGS,
        Capability.EDIT_SPECIAL_PRICE,
        Capability.APPROVE_SPECIAL_PRICE,
        Capability.EDIT_REPLACEMENT_COST,
        Capability.PRINT_MEASUREMENTS,
        Capability.PRINT_CUSTOMER_INVOICE,
        Capability.PRINT_INTERNAL_COST_REPORT,
        Capability.VIEW_FINANCIAL_REPORTS,
    }
)
_CONTROL_CENTER = frozenset(
    {
        Capability.VIEW_ORDERS,
        Capability.APPROVE_ORDER,
        Capability.REJECT_ORDER,
        Capability.VIEW_CUTTING_PLAN,
        Capability.PRINT_CUTTING_PLAN,
        Capability.ARCHIVE_APPROVED_PLAN,
        Capability.CREATE_REPLACEMENT,
        Capability.VIEW_REPLACEMENTS,
        Capability.APPROVE_REPLACEMENT,
        Capability.CANCEL_REPLACEMENT,
        Capability.VIEW_OPERATIONAL_REPORTS,
    }
)


LEGACY_ROLE_CAPABILITIES = MappingProxyType(
    {
        "Order Entry": _ORDER_ENTRY,
        "Cutting Operator": _PRODUCTION_OPERATOR,
        "Edge Operator": _PRODUCTION_OPERATOR,
        "Production Manager": frozenset(
            _ORDER_ENTRY | _PLANNER_DESIGNER | _PRODUCTION_SUPERVISOR | _CONTROL_CENTER
        ),
        "Accounts Management": _PRICING_AND_DOCUMENTS,
        "عامل رسم": _PLANNER_DESIGNER,
        "عامل شريون": _PRODUCTION_OPERATOR,
        "عامل CNC": _PRODUCTION_OPERATOR,
        "عامل تقشيط": _PRODUCTION_OPERATOR,
    }
)
FULL_ACCESS_LEGACY_ROLES = frozenset({"System Manager"})


def legacy_role_state(role: str) -> dict[str, bool]:
    """Return a one-time migration state for a historical Almdina role."""

    resolved = str(role or "").strip()
    if resolved in FULL_ACCESS_LEGACY_ROLES:
        return normalize_capability_state(
            {capability: True for capability in ALL_CAPABILITIES}
        )
    try:
        capabilities = LEGACY_ROLE_CAPABILITIES[resolved]
    except KeyError as exc:
        raise ValueError(f"Unknown legacy Almdina role: {resolved}") from exc
    return normalize_capability_state(
        {capability: True for capability in capabilities}
    )


def legacy_roles() -> tuple[str, ...]:
    return tuple(sorted((*LEGACY_ROLE_CAPABILITIES, *FULL_ACCESS_LEGACY_ROLES)))


__all__ = [
    "FULL_ACCESS_LEGACY_ROLES",
    "LEGACY_ROLE_CAPABILITIES",
    "legacy_role_state",
    "legacy_roles",
]
