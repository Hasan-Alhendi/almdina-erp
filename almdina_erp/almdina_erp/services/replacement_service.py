"""Backward-compatible replacement API facade.

New code should import the focused creation, approval, execution, completion,
snapshot, plan, or status service directly. This module preserves the public
API paths used by existing clients without owning business logic.
"""

from __future__ import annotations

from typing import Any

import frappe


@frappe.whitelist()
def record_incident(
    order_name: str,
    piece_label: str,
    reason: str,
    description: str,
    production_stage: str | None = None,
    requires_replacement: int | bool = 1,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.replacement_creation_service import (
        record_incident as execute,
    )

    return execute(
        order_name=order_name,
        piece_label=piece_label,
        reason=reason,
        description=description,
        production_stage=production_stage,
        requires_replacement=requires_replacement,
    )


@frappe.whitelist()
def create_replacement_from_incident(
    incident_name: str,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.replacement_creation_service import (
        create_replacement_from_incident as execute,
    )

    return execute(incident_name)


@frappe.whitelist()
def approve_replacement(replacement_name: str) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.replacement_approval import (
        approve_replacement as execute,
    )

    return execute(replacement_name)


@frappe.whitelist()
def start_replacement(replacement_name: str) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.replacement_execution import (
        start_replacement as execute,
    )

    return execute(replacement_name)


@frappe.whitelist()
def complete_replacement(
    replacement_name: str,
    internal_loss_cost_usd: float | None = None,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.replacement_completion import (
        complete_replacement as execute,
    )

    return execute(
        replacement_name,
        internal_loss_cost_usd=internal_loss_cost_usd,
    )


@frappe.whitelist()
def cancel_replacement(
    replacement_name: str,
    reason: str | None = None,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.replacement_execution import (
        cancel_replacement as execute,
    )

    return execute(replacement_name, reason=reason)
