from __future__ import annotations

from typing import Any, NoReturn

import frappe
from frappe import _


_RETIRED_PRODUCT_MESSAGE = _(
    "This legacy endpoint belongs to inventory or stage controls that are not "
    "active in the current Almdina product. Use the supported Almdina workflow."
)
_REMOVED_ROLE_GATE_MESSAGE = _(
    "This legacy role-based authorization path has been removed. "
    "Use the capability-protected Almdina service."
)


def reject_legacy_role_gate(*_roles: str) -> NoReturn:
    """Fail closed when historical Python code reaches a removed role gate."""

    frappe.throw(_REMOVED_ROLE_GATE_MESSAGE, frappe.PermissionError)
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def retired_product_endpoint(*_args: Any, **_kwargs: Any) -> NoReturn:
    """Close obsolete inventory/remnant/preflight HTTP methods explicitly."""

    frappe.throw(_RETIRED_PRODUCT_MESSAGE, frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def start_legacy_stage(
    stage_name: str,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    """Map the historical start endpoint to assigned-stage authorization."""

    del assigned_to
    from almdina_erp.almdina_erp.services.shop_floor_commands import (
        start_my_stage,
    )

    return start_my_stage(stage_name)


@frappe.whitelist()
def finish_legacy_stage(
    stage_name: str,
    completed_qty: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Map historical finish to the canonical handoff/final completion command."""

    del completed_qty, notes
    from almdina_erp.almdina_erp.services.shop_floor_commands import (
        handoff_to_next,
    )

    return handoff_to_next(stage_name)


__all__ = [
    "finish_legacy_stage",
    "reject_legacy_role_gate",
    "retired_product_endpoint",
    "start_legacy_stage",
]
