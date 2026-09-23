from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cutting.plan_freshness import (
    decide_approved_plan_freshness,
    decide_draft_plan_freshness,
    decide_uploaded_plan_mismatch,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    DRAFT,
    UPLOADED_DXF,
    cancel_approval_transition,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    freshness_expected_fingerprint,
)


def _mark_plan_needs_recalculation(plan_name: str) -> None:
    frappe.db.set_value(
        "Cutting Plan",
        plan_name,
        "plan_needs_recalculation",
        1,
        update_modified=False,
    )
    frappe.clear_document_cache("Cutting Plan", plan_name)


def _sync_drawing_dxf_status(order: Any) -> None:
    if not hasattr(order, "drawing_dxf_status"):
        return

    uploaded = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order.name,
            "plan_kind": "Order",
            "source_type": UPLOADED_DXF,
        },
        fields=["dxf_file", "dxf_status"],
        order_by="revision desc, creation desc",
        limit_page_length=1,
    )
    row = uploaded[0] if uploaded else None
    has_valid_uploaded_dxf = bool(
        row
        and str(row.get("dxf_file") or "").strip()
        and str(row.get("dxf_status") or "") == "Validated"
    )
    order.drawing_dxf_status = "Uploaded" if has_valid_uploaded_dxf else "None"


def _expected_fingerprint(order: Any, plan: Any) -> str:
    return freshness_expected_fingerprint(
        order,
        plan,
        str(getattr(plan, "input_fingerprint", None) or ""),
    )


def _cancel_stale_approved_plan(order: Any) -> str | None:
    """Clear a stale production approval on the in-memory order.

    The caller must persist Door Cutting Order itself. This function never
    ``set_value``s the parent document, so a normal form save cannot race its
    own ``modified`` timestamp.
    """

    approved_name = str(getattr(order, "approved_plan", None) or "").strip()
    if not approved_name:
        return None

    if not frappe.db.exists("Cutting Plan", approved_name):
        order.approved_plan = None
        _sync_drawing_dxf_status(order)
        return None

    plan = frappe.get_doc("Cutting Plan", approved_name)
    if str(getattr(plan, "door_cutting_order", None) or "") != str(order.name):
        order.approved_plan = None
        _sync_drawing_dxf_status(order)
        return None

    decision = decide_approved_plan_freshness(
        status=str(plan.status or ""),
        stored_fingerprint=str(plan.input_fingerprint or ""),
        expected_fingerprint=_expected_fingerprint(order, plan),
    )
    if not decision.should_invalidate:
        return None

    _, after = cancel_approval_transition(getattr(plan, "status", None))
    frappe.db.set_value(
        "Cutting Plan",
        plan.name,
        "status",
        after,
        update_modified=False,
    )
    _mark_plan_needs_recalculation(plan.name)
    order.approved_plan = None
    _sync_drawing_dxf_status(order)
    return plan.name


def apply_stale_approved_plan_cancellation(order: Any) -> str | None:
    """Cancel a stale Approved plan before Door Cutting Order is written.

    Must run in ``validate``/``before_save`` so ``approved_plan`` is cleared by
    the same parent ``db_update``. Calling this from ``on_update`` would issue a
    second parent UPDATE after the save timestamp was already sent to the client.
    """

    if not getattr(order, "name", None) or getattr(order, "is_new", lambda: False)():
        return None
    return _cancel_stale_approved_plan(order)


def _mark_stale_uploaded_plan(order: Any, skipped: tuple[str, ...]) -> str | None:
    rows = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order.name,
            "plan_kind": "Order",
            "source_type": UPLOADED_DXF,
        },
        fields=["name", "status", "revision"],
        order_by="revision desc, creation desc",
    )
    if not rows:
        return None

    draft = next((row for row in rows if str(row.get("status") or "") == DRAFT), None)
    target = draft or rows[0]
    plan_name = str(target.get("name") or "")
    if not plan_name or plan_name in skipped:
        return None

    plan = frappe.get_doc("Cutting Plan", plan_name)
    already_stale = bool(cint(plan.plan_needs_recalculation))
    decision = decide_uploaded_plan_mismatch(
        source_type=str(plan.source_type or ""),
        stored_fingerprint=str(plan.input_fingerprint or ""),
        expected_fingerprint=_expected_fingerprint(order, plan),
        already_needs_recalculation=already_stale,
    )
    if not decision.should_invalidate:
        return None

    _mark_plan_needs_recalculation(plan.name)
    return plan.name


def invalidate_stale_draft_plans(order: Any) -> tuple[str, ...]:
    """Mark stale Cutting Plan revisions after the order row is persisted.

    Drafts and uploaded DXF history are flagged here. Approved-plan cancellation
    is owned by ``apply_stale_approved_plan_cancellation`` so the parent document
    is not written again after ``modified`` has already changed.
    """

    if not getattr(order, "name", None) or getattr(order, "is_new", lambda: False)():
        return ()

    plan_names = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order.name,
            "plan_kind": "Order",
            "status": DRAFT,
        },
        pluck="name",
        order_by="revision desc, creation desc",
    )

    invalidated: list[str] = []
    for plan_name in plan_names:
        plan = frappe.get_doc("Cutting Plan", plan_name)
        already_stale = bool(cint(plan.plan_needs_recalculation))
        decision = decide_draft_plan_freshness(
            status=str(plan.status or ""),
            stored_fingerprint=str(plan.input_fingerprint or ""),
            expected_fingerprint=_expected_fingerprint(order, plan),
            already_needs_recalculation=already_stale,
        )
        if not decision.should_invalidate:
            continue

        _mark_plan_needs_recalculation(plan.name)
        invalidated.append(plan.name)

    uploaded = _mark_stale_uploaded_plan(order, tuple(invalidated))
    if uploaded:
        invalidated.append(uploaded)

    return tuple(invalidated)


__all__ = [
    "apply_stale_approved_plan_cancellation",
    "invalidate_stale_draft_plans",
]
