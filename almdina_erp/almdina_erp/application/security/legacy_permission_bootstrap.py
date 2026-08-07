from __future__ import annotations

from types import MappingProxyType

from almdina_erp.almdina_erp.application.security.permission_matrix import normalize_capability_state
from almdina_erp.almdina_erp.domain.security.authorization import ALL_CAPABILITIES, Capability


# Historical grants are migration compatibility only. They are never exposed as
# templates, never selectable in the UI, and never applied to newly created roles.
_ORDER_ENTRY_GRANTS = frozenset(
    {
        Capability.VIEW_ORDERS,
        Capability.CREATE_ORDER,
        Capability.EDIT_ORDER,
        Capability.SUBMIT_ORDER,
        Capability.PRINT_MEASUREMENTS,
        Capability.PRINT_CUSTOMER_INVOICE,
        Capability.VIEW_CUSTOMERS,
        Capability.VIEW_EDGE_BANDING_TYPES,
    }
)
_PLANNING_AND_DRAWING_GRANTS = frozenset(
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
_PRODUCTION_OPERATOR_GRANTS = frozenset(
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
_PRODUCTION_SUPERVISOR_GRANTS = frozenset(
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
_PRICING_AND_DOCUMENT_GRANTS = frozenset(
    {
        Capability.VIEW_ORDERS,
        Capability.VIEW_COSTS,
        Capability.EDIT_COST_SETTINGS,
        Capability.EDIT_SPECIAL_PRICE,
        Capability.APPROVE_SPECIAL_PRICE,
        Capability.VIEW_REPLACEMENTS,
        Capability.EDIT_REPLACEMENT_COST,
        Capability.PRINT_MEASUREMENTS,
        Capability.PRINT_CUSTOMER_INVOICE,
        Capability.PRINT_INTERNAL_COST_REPORT,
        Capability.VIEW_OPERATIONAL_REPORTS,
        Capability.VIEW_FINANCIAL_REPORTS,
    }
)
_CONTROL_CENTER_GRANTS = frozenset(
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
        "Order Entry": _ORDER_ENTRY_GRANTS,
        "Cutting Operator": _PRODUCTION_OPERATOR_GRANTS,
        "Edge Operator": _PRODUCTION_OPERATOR_GRANTS,
        "Production Manager": frozenset(
            _ORDER_ENTRY_GRANTS
            | _PLANNING_AND_DRAWING_GRANTS
            | _PRODUCTION_SUPERVISOR_GRANTS
            | _CONTROL_CENTER_GRANTS
        ),
        "Accounts Management": _PRICING_AND_DOCUMENT_GRANTS,
        "عامل رسم": _PLANNING_AND_DRAWING_GRANTS,
        "عامل شريون": _PRODUCTION_OPERATOR_GRANTS,
        "عامل CNC": _PRODUCTION_OPERATOR_GRANTS,
        "عامل تقشيط": _PRODUCTION_OPERATOR_GRANTS,
    }
)
FULL_ACCESS_LEGACY_ROLES = frozenset({"System Manager"})


def legacy_role_state(role: str) -> dict[str, bool]:
    resolved = str(role or "").strip()
    if resolved in FULL_ACCESS_LEGACY_ROLES:
        capabilities = ALL_CAPABILITIES
    else:
        try:
            capabilities = LEGACY_ROLE_CAPABILITIES[resolved]
        except KeyError as exc:
            raise ValueError(f"Unknown legacy Almdina role: {resolved}") from exc
    return normalize_capability_state({capability: True for capability in capabilities})


def legacy_roles() -> tuple[str, ...]:
    return tuple(sorted((*LEGACY_ROLE_CAPABILITIES, *FULL_ACCESS_LEGACY_ROLES)))


__all__ = [
    "FULL_ACCESS_LEGACY_ROLES",
    "LEGACY_ROLE_CAPABILITIES",
    "legacy_role_state",
    "legacy_roles",
]
