from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
)


# Historical migration data only. These groups reproduce the grants that were
# shipped for legacy roles before the permission system became fully dynamic.
# They are intentionally not exposed to the UI and are not reusable templates.
_LEGACY_CAPABILITY_GROUPS = MappingProxyType(
    {
        "order_entry": frozenset(
            {
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.EDIT_ORDER,
                Capability.SUBMIT_ORDER,
                Capability.PRINT_MEASUREMENTS,
                Capability.PRINT_CUSTOMER_INVOICE,
            }
        ),
        "planner_designer": frozenset(
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
        ),
        "production_operator": frozenset(
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
        ),
        "production_supervisor": frozenset(
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
        ),
        "pricing_and_documents": frozenset(
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
        ),
        "control_center": frozenset(
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
        ),
    }
)

LEGACY_ROLE_GROUP_KEYS = MappingProxyType(
    {
        "Order Entry": ("order_entry",),
        "Cutting Operator": ("production_operator",),
        "Edge Operator": ("production_operator",),
        "Production Manager": (
            "order_entry",
            "planner_designer",
            "production_supervisor",
            "control_center",
        ),
        "Accounts Management": ("pricing_and_documents",),
        "عامل رسم": ("planner_designer",),
        "عامل شريون": ("production_operator",),
        "عامل CNC": ("production_operator",),
        "عامل تقشيط": ("production_operator",),
    }
)
FULL_ACCESS_LEGACY_ROLES = frozenset({"System Manager"})


def combine_legacy_groups(group_keys: Iterable[str]) -> dict[str, bool]:
    """Combine immutable historical grant groups for one migration role."""

    enabled: dict[str, bool] = {}
    for group_key in group_keys:
        try:
            capabilities = _LEGACY_CAPABILITY_GROUPS[group_key]
        except KeyError as exc:
            raise ValueError(f"Unknown legacy capability group: {group_key}") from exc
        enabled.update({capability: True for capability in capabilities})
    return normalize_capability_state(enabled)


def legacy_role_state(role: str) -> dict[str, bool]:
    """Return the least-surprise upgrade state for one historical Almdina role."""

    resolved = str(role or "").strip()
    if resolved in FULL_ACCESS_LEGACY_ROLES:
        return normalize_capability_state(
            {capability: True for capability in ALL_CAPABILITIES}
        )
    try:
        group_keys = LEGACY_ROLE_GROUP_KEYS[resolved]
    except KeyError as exc:
        raise ValueError(f"Unknown legacy Almdina role: {resolved}") from exc
    return combine_legacy_groups(group_keys)


def legacy_roles() -> tuple[str, ...]:
    return tuple(sorted((*LEGACY_ROLE_GROUP_KEYS, *FULL_ACCESS_LEGACY_ROLES)))


__all__ = [
    "FULL_ACCESS_LEGACY_ROLES",
    "LEGACY_ROLE_GROUP_KEYS",
    "combine_legacy_groups",
    "legacy_role_state",
    "legacy_roles",
]
