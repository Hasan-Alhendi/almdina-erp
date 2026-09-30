from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    Capability,
)


ContextualRule = Literal[
    "none",
    "lifecycle",
    "assignment",
    "operational_role",
    "permlevel",
    "document_scope",
]


@dataclass(frozen=True, slots=True)
class CapabilityFrappeMapEntry:
    capability: str
    applies_to: str
    permission_type: str
    standard: bool
    contextual_rules: tuple[ContextualRule, ...]


_CONTEXTUAL_RULES: dict[str, tuple[ContextualRule, ...]] = {
    Capability.EDIT_ORDER: ("lifecycle", "document_scope"),
    Capability.CREATE_ORDER_REVISION: ("lifecycle", "document_scope"),
    Capability.SUBMIT_ORDER: ("lifecycle", "document_scope"),
    Capability.APPROVE_ORDER: ("lifecycle", "document_scope"),
    Capability.REJECT_ORDER: ("lifecycle", "document_scope"),
    Capability.CANCEL_ORDER: ("lifecycle", "document_scope"),
    Capability.RESUME_CANCELLED_ORDER: ("lifecycle", "document_scope"),
    Capability.EDIT_SPECIAL_PRICE: ("lifecycle", "document_scope"),
    Capability.APPROVE_SPECIAL_PRICE: ("lifecycle", "document_scope"),
    Capability.VIEW_COSTS: ("permlevel", "document_scope"),
    Capability.EDIT_COST_SETTINGS: ("permlevel", "document_scope"),
    Capability.VIEW_ORDERS: ("document_scope",),
    Capability.VIEW_ALL_ORDERS: ("document_scope",),
    Capability.VIEW_CUTTING_PLAN: ("document_scope",),
    Capability.VIEW_SYSTEM_CUTTING_PLAN: ("document_scope",),
    Capability.VIEW_UPLOADED_CUTTING_PLAN: ("document_scope",),
    Capability.VIEW_APPROVED_CUTTING_PLAN: ("document_scope",),
    Capability.RECALCULATE_PLAN: ("lifecycle", "document_scope"),
    Capability.EDIT_OPTIMIZER_SETTINGS: ("lifecycle", "document_scope"),
    Capability.APPROVE_DXF: ("lifecycle", "document_scope"),
    Capability.UPLOAD_DXF: ("lifecycle", "document_scope"),
    Capability.REPLACE_DXF: ("lifecycle", "document_scope"),
    Capability.EXPORT_DXF: ("document_scope",),
    Capability.EDIT_SPECIAL_DRAWING: ("lifecycle", "document_scope"),
    Capability.DISPATCH_ORDER: ("lifecycle", "document_scope"),
    Capability.START_ASSIGNED_STAGE: (
        "assignment",
        "operational_role",
        "lifecycle",
        "document_scope",
    ),
    Capability.HANDOFF_ASSIGNED_STAGE: (
        "assignment",
        "operational_role",
        "lifecycle",
        "document_scope",
    ),
    Capability.REVERT_DEPARTMENT: ("lifecycle", "document_scope"),
    Capability.RETURN_ORDER_TO_DRAFT: ("lifecycle", "document_scope"),
    Capability.MARK_DELIVERED: ("lifecycle", "document_scope"),
    Capability.REASSIGN_WORKER: ("lifecycle", "document_scope"),
    Capability.VIEW_SHOP_FLOOR_HISTORY: ("document_scope",),
    Capability.PRINT_CUTTING_PLAN: ("document_scope",),
    Capability.PRINT_MEASUREMENTS: ("document_scope",),
    Capability.PRINT_CUSTOMER_INVOICE: ("document_scope",),
    Capability.PRINT_INTERNAL_COST_REPORT: ("document_scope", "permlevel"),
    Capability.ARCHIVE_APPROVED_PLAN: ("document_scope",),
    Capability.SET_OFFCUT_EXECUTION_OWNER: ("lifecycle", "document_scope"),
}


def capability_frappe_map() -> tuple[CapabilityFrappeMapEntry, ...]:
    """Framework-free map of every catalog capability to its Frappe grant column."""

    return tuple(
        CapabilityFrappeMapEntry(
            capability=definition.key,
            applies_to=definition.applies_to,
            permission_type=definition.permission_type,
            standard=not definition.custom,
            contextual_rules=_CONTEXTUAL_RULES.get(definition.key, ("none",)),
        )
        for definition in CAPABILITY_CATALOG.values()
    )


__all__ = [
    "CapabilityFrappeMapEntry",
    "ContextualRule",
    "capability_frappe_map",
]
