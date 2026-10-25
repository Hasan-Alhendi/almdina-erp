"""Read-only Bench audit; permission-scoped, with no repair or approval commands.

Legacy invalidation uses db.set_value(update_modified=False) without a reason or
Version entry. A current compatible hash cannot prove the origin of a saved flag
(e.g. dimensions changed and later reverted). Never infer repair eligibility.
"""
from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import ManufacturingRequirementsError
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import require_cutting_plan_capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import plan_fingerprint_compatibility


def audit_uploaded_plan_fingerprints() -> list[dict[str, Any]]:
    """Classify every visible uploaded revision. This function never writes data."""
    result: list[dict[str, Any]] = []
    start = 0
    while True:
        rows = frappe.get_list(
            "Cutting Plan", filters={"plan_kind": "Order", "source_type": "Uploaded DXF"},
            fields=["name", "door_cutting_order", "revision", "status"],
            order_by="name asc", limit_start=start, limit_page_length=200,
        )
        if not rows:
            return result
        for row in rows:
            order = frappe.get_doc("Door Cutting Order", row.door_cutting_order)
            order.check_permission("read")
            require_cutting_plan_capability(order, Capability.VIEW_UPLOADED_CUTTING_PLAN)
            plan = frappe.get_doc("Cutting Plan", row.name)
            try:
                decision = plan_fingerprint_compatibility(order, plan, str(plan.input_fingerprint or ""))
                state, reason, contract = decision.state, decision.reason, decision.contract
            except (ManufacturingRequirementsError, frappe.ValidationError):
                state, reason, contract = "REVIEW_REQUIRED", "unverifiable_inputs", ""
            if row.status in {"Cancelled", "Superseded"}:
                state = "HISTORICAL_REVIEW_REQUIRED"
            elif cint(plan.plan_needs_recalculation) and state in {"MATCH", "COMPATIBLE"}:
                state, reason = "PERSISTED_STALE", "stale_origin_not_recorded"
            result.append({
                "order": row.door_cutting_order, "plan": row.name,
                "revision": cint(row.revision), "status": row.status,
                "classification": state, "reason": reason, "contract": contract,
            })
        start += len(rows)
