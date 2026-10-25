"""Read-only Bench audit; permission-scoped, with no repair or approval commands.

Legacy invalidation uses db.set_value(update_modified=False) without a reason or
Version entry. A current compatible hash cannot prove the origin of a saved flag
(e.g. dimensions changed and later reverted). Never infer repair eligibility.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
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


def _dxf_attachment_status(plan: Any, source: str, *, verify_files: bool) -> str:
    if source != UPLOADED_DXF:
        return "NOT_APPLICABLE"
    url = str(getattr(plan, "dxf_file", "") or "").strip()
    if not url:
        return "MISSING"
    if not verify_files:
        return "NOT_CHECKED"
    # Reuse the exact scoped attachment and disk-path checks used by download.
    from almdina_erp.almdina_erp.services.dxf_export_service import (
        _dxf_file_row, _existing_dxf_disk_path,
    )
    row = _dxf_file_row(url)
    if not row or not url.startswith("/private/files/") or ".." in url:
        return "MISSING"
    if not (cint(row.is_private)
            and str(row.attached_to_doctype or "") == "Cutting Plan"
            and str(row.attached_to_name or "") == str(plan.name)
            and str(row.attached_to_field or "") == "dxf_file"):
        return "UNSCOPED"
    return "AVAILABLE" if _existing_dxf_disk_path(url) else "MISSING"


def _value(row: Any, key: str, default: Any = None) -> Any:
    return row.get(key, default) if isinstance(row, Mapping) else getattr(row, key, default)


def _plan_pages(*, include_system: bool, order_names: tuple[str, ...] = (),
                page_size: int = 200) -> Iterator[list[Any]]:
    if not 1 <= page_size <= 500:
        raise ValueError("page_size must be between 1 and 500")
    sources = (SYSTEM, UPLOADED_DXF) if include_system else (UPLOADED_DXF,)
    start = 0
    while True:
        filters: dict[str, Any] = {
            "plan_kind": "Order",
            "source_type": sources[0] if len(sources) == 1 else ["in", list(sources)],
        }
        if order_names:
            filters["door_cutting_order"] = ["in", list(order_names)]
        page = frappe.get_list(
            "Cutting Plan",
            filters=filters,
            fields=["name", "door_cutting_order", "revision", "status", "source_type", "modified"],
            order_by=(
                "door_cutting_order asc, revision desc, modified desc, creation desc"
                if include_system else "name asc"
            ),
            limit_start=start,
            limit_page_length=page_size,
        )
        if not page:
            break
        yield page
        start += len(page)


def _audit_group(rows: list[Any], *, include_system: bool,
                 verify_files: bool = False,
                 current_drafts: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
    # The first Draft in each source is current. Never let a newer System
    # revision hide an independent Uploaded DXF Draft (or vice versa).
    if current_drafts is None:
        current_drafts = {}
    if include_system:
        for row in rows:
            if _value(row, "status") == DRAFT:
                current_drafts.setdefault(str(_value(row, "source_type")), str(_value(row, "name")))
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

        current_draft = current_drafts.get(source) == plan_name
        candidate = current_draft or current_approval
        compatible = state in {"MATCH", "COMPATIBLE"}
        stale = bool(cint(plan.plan_needs_recalculation))
        file_status = _dxf_attachment_status(plan, source, verify_files=verify_files) if include_system else "NOT_CHECKED"
        if include_system and not candidate:
            state, reason = "HISTORICAL_REVIEW_REQUIRED", "historical_revision"
        elif not include_system and status in {"Cancelled", "Superseded"}:
            state, reason = "HISTORICAL_REVIEW_REQUIRED", reason
        elif stale and compatible:
            state, reason = "PERSISTED_STALE", "stale_origin_not_recorded"

        entry = {
            "order": order_name, "plan": plan_name,
            "revision": cint(_value(row, "revision")), "status": status,
            "classification": state, "reason": reason, "contract": contract,
        }
        if include_system:
            entry.update(
                audit_schema_version=1,
                source_type=source,
                current_draft=current_draft,
                current_approval=current_approval,
                manufacturing_candidate=candidate,
                plan_needs_recalculation=stale,
                lifecycle_candidate=candidate,
                fingerprint_compatible=compatible,
                # Plan-level eligibility; the shop-floor stage/capability gate
                # still makes the final decision for each manufacturing action.
                manufacturing_authorized=bool(current_approval and compatible and not stale
                                              and str(getattr(plan, "snapshot_json", "") or "").strip()
                                              and str(getattr(plan, "validation_status", "") or "") == "Valid"
                                              and (source != UPLOADED_DXF or file_status == "AVAILABLE")),
                snapshot_present=bool(str(getattr(plan, "snapshot_json", "") or "").strip()),
                dxf_file_present=bool(str(getattr(plan, "dxf_file", "") or "").strip()),
                dxf_attachment_status=file_status,
            )
        yield entry


def iter_cutting_plan_audit(*, order_names: tuple[str, ...] = (), page_size: int = 200,
                            verify_files: bool = False) -> Iterator[dict[str, Any]]:
    """Stream a permission-scoped, read-only inventory, one order at a time."""
    current_drafts: dict[str, str] = {}
    group_order = ""
    for page in _plan_pages(include_system=True, order_names=order_names, page_size=page_size):
        for row in page:
            order_name = str(_value(row, "door_cutting_order") or "")
            if order_name != group_order:
                current_drafts.clear()
            group_order = order_name
            yield from _audit_group([row], include_system=True,
                                    verify_files=verify_files, current_drafts=current_drafts)


def audit_uploaded_plan_fingerprints(*, include_system: bool = False) -> list[dict[str, Any]]:
    """Legacy list interface; use the streaming iterator for large sites."""
    if include_system:
        return list(iter_cutting_plan_audit())
    result: list[dict[str, Any]] = []
    for page in _plan_pages(include_system=False):
        for row in page:
            result.extend(_audit_group([row], include_system=False))
    return result


def audit_cutting_plan_summary(*, order_names: tuple[str, ...] = (), page_size: int = 200,
                               verify_files: bool = False) -> dict[str, Any]:
    """Bounded-memory Bench summary; no customer fields or database writes."""
    counts: Counter[str] = Counter()
    last_order = None
    order_count = 0
    for entry in iter_cutting_plan_audit(order_names=order_names, page_size=page_size,
                                         verify_files=verify_files):
        if entry["order"] != last_order:
            order_count += 1
            last_order = entry["order"]
        counts["plans"] += 1
        counts[f"status:{entry['status']}"] += 1
        counts[f"contract:{entry['contract'] or 'unknown'}"] += 1
        counts[f"classification:{entry['classification']}"] += 1
        counts[f"dxf_attachment:{entry['dxf_attachment_status']}"] += 1
        counts[f"source:{entry['source_type']}"] += 1
        for key in ("lifecycle_candidate", "fingerprint_compatible", "manufacturing_authorized",
                    "snapshot_present", "dxf_file_present", "plan_needs_recalculation"):
            counts[key] += int(entry[key])
    total_orders = (frappe.db.count("Door Cutting Order")
                    if frappe.session.user == "Administrator" and not order_names else None)
    return {"orders_total": total_orders, "orders_with_plans": order_count, "counts": dict(counts)}


def compare_upgrade_audits(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare inventories from the same isolated DB before and after code change."""
    old = {item["plan"]: item for item in before}
    new = {item["plan"]: item for item in after}
    regressions = sorted(name for name, item in old.items()
                         if item.get("manufacturing_authorized")
                         and (name not in new or not new[name].get("manufacturing_authorized")
                              or item.get("dxf_attachment_status") == "AVAILABLE"
                              and new[name].get("dxf_attachment_status") != "AVAILABLE"))
    changed = sorted(name for name in old.keys() & new.keys()
                     if any(old[name].get(key) != new[name].get(key) for key in
                            ("classification", "status", "dxf_attachment_status")))
    incomplete = len(old) != len(before) or len(new) != len(after) or any(
                     item.get("audit_schema_version") != 1 or
                     item.get("dxf_attachment_status") in {"NOT_CHECKED", "UNKNOWN"}
                     for item in [*before, *after])
    return {"result": "BLOCKED_BY_REGRESSION" if regressions else
            "REVIEW_REQUIRED" if incomplete or changed or old.keys() != new.keys() else "PASS",
            "lost_manufacturing_eligibility": len(regressions),
            "classification_changes": len(changed), "missing_or_new_plans": len(old.keys() ^ new.keys()),
            "incomplete_evidence": incomplete}


def audit_cutting_plan_lifecycles() -> list[dict[str, Any]]:
    """Read-only lifecycle report for System and Uploaded plans, with no repairs."""
    return audit_uploaded_plan_fingerprints(include_system=True)
