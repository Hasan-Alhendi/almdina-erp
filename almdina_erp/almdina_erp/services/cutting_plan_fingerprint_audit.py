"""Read-only Bench audit; permission-scoped, with no repair or approval commands.

Legacy invalidation uses db.set_value(update_modified=False) without a reason or
Version entry. A current compatible hash cannot prove the origin of a saved flag
(e.g. dimensions changed and later reverted). Never infer repair eligibility.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import ManufacturingRequirementsError
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    cutting_plan_capability_allowed,
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import plan_fingerprint_compatibility


def _value(row: Any, key: str, default: Any = None) -> Any:
    return row.get(key, default) if isinstance(row, Mapping) else getattr(row, key, default)


def audit_uploaded_plan_fingerprints(*, include_system: bool = False) -> list[dict[str, Any]]:
    """Classify visible uploaded plans; optionally include System lifecycle rows."""
    sources = (SYSTEM, UPLOADED_DXF) if include_system else (UPLOADED_DXF,)
    rows: list[Any] = []
    start = 0
    while True:
        page = frappe.get_list(
            "Cutting Plan",
            filters={
                "plan_kind": "Order",
                "source_type": sources[0] if len(sources) == 1 else ["in", list(sources)],
            },
            fields=["name", "door_cutting_order", "revision", "status", "source_type", "modified"],
            order_by=(
                "door_cutting_order asc, revision desc, modified desc, creation desc"
                if include_system else "name asc"
            ),
            limit_start=start,
            limit_page_length=200,
        )
        if not page:
            break
        rows.extend(page)
        start += len(page)

    current_drafts: dict[str, str] = {}
    if include_system:
        for row in rows:
            order_name = str(_value(row, "door_cutting_order") or "")
            if order_name and _value(row, "status") == DRAFT:
                current_drafts.setdefault(order_name, str(_value(row, "name") or ""))

    result: list[dict[str, Any]] = []
    for row in rows:
        plan_name = str(_value(row, "name") or "")
        status = str(_value(row, "status") or "")
        source = str(_value(row, "source_type") or UPLOADED_DXF)
        order_name = str(_value(row, "door_cutting_order") or "")
        if source == SYSTEM:
            source_capability = Capability.VIEW_SYSTEM_CUTTING_PLAN
        elif source == UPLOADED_DXF:
            source_capability = Capability.VIEW_UPLOADED_CUTTING_PLAN
        else:
            continue

        order = frappe.get_doc("Door Cutting Order", order_name)
        order.check_permission("read")
        if include_system:
            if not cutting_plan_capability_allowed(order, source_capability):
                continue
        else:
            require_cutting_plan_capability(order, source_capability)
        plan = frappe.get_doc("Cutting Plan", plan_name)
        current_approval = (
            str(getattr(order, "approved_plan", None) or "") == plan_name
            and status == APPROVED
        )
        if current_approval and include_system and not cutting_plan_capability_allowed(
            order, Capability.VIEW_APPROVED_CUTTING_PLAN
        ):
            continue

        try:
            decision = plan_fingerprint_compatibility(
                order, plan, str(plan.input_fingerprint or "")
            )
            state, reason, contract = decision.state, decision.reason, decision.contract
        except (ManufacturingRequirementsError, frappe.ValidationError):
            state, reason, contract = "REVIEW_REQUIRED", "unverifiable_inputs", ""

        current_draft = current_drafts.get(order_name) == plan_name
        candidate = current_draft or current_approval
        if include_system and not candidate:
            state, reason = "HISTORICAL_REVIEW_REQUIRED", "historical_revision"
        elif not include_system and status in {"Cancelled", "Superseded"}:
            state, reason = "HISTORICAL_REVIEW_REQUIRED", reason
        elif cint(plan.plan_needs_recalculation) and state in {"MATCH", "COMPATIBLE"}:
            state, reason = "PERSISTED_STALE", "stale_origin_not_recorded"

        entry = {
            "order": order_name, "plan": plan_name,
            "revision": cint(_value(row, "revision")), "status": status,
            "classification": state, "reason": reason, "contract": contract,
        }
        if include_system:
            entry.update(
                source_type=source,
                current_draft=current_draft,
                current_approval=current_approval,
                manufacturing_candidate=candidate,
                plan_needs_recalculation=bool(cint(plan.plan_needs_recalculation)),
            )
        result.append(entry)
    return result


def audit_cutting_plan_lifecycles() -> list[dict[str, Any]]:
    """Read-only lifecycle report for System and Uploaded plans, with no repairs."""
    return audit_uploaded_plan_fingerprints(include_system=True)
