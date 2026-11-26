from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cutting.plan_freshness import (
    decide_approved_plan_freshness,
    decide_draft_plan_freshness,
    decide_uploaded_manufacturing_trim_mismatch,
    decide_uploaded_plan_mismatch,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    BOARD_EDITOR,
    DRAFT,
    UPLOADED_DXF,
    cancel_approval_transition,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    manufacturing_plan_settings,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    manufacturing_baseline_v4,
    plan_fingerprint_compatibility,
)


def _set_plan_needs_recalculation(plan_name: str, value: int) -> None:
    frappe.db.set_value(
        "Cutting Plan",
        plan_name,
        "plan_needs_recalculation",
        1 if value else 0,
        update_modified=False,
    )
    frappe.clear_document_cache("Cutting Plan", plan_name)


def _mark_plan_needs_recalculation(plan_name: str) -> None:
    _set_plan_needs_recalculation(plan_name, 1)


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


def _expected_fingerprint(order: Any, plan: Any) -> str | None:
    # Share the decision used by freshness_expected_fingerprint; uncertainty blocks
    # new use through runtime gates, but must not rewrite an immutable approval.
    previous = getattr(order, "get_doc_before_save", lambda: None)()
    stored = str(getattr(plan, "input_fingerprint", None) or "")
    decision = plan_fingerprint_compatibility(
        order, plan, stored, previous_order=previous,
    )
    if decision.state == "MISMATCH" and previous is not None:
        before = plan_fingerprint_compatibility(previous, plan, stored)
        if (before.compatible
                and manufacturing_baseline_v4(previous, plan, historical=True)
                == manufacturing_baseline_v4(order, plan, historical=True)):
            # A historical hash includes order revision/optimizer provenance.
            # Preserve the immutable approval record when this save changed no
            # manufacturing input. Its runtime gate remains fail-closed until
            # durable evidence for the old contract can be established.
            return None
    if decision.state == "REVIEW_REQUIRED":
        return None
    return decision.expected_fingerprint


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

    expected = _expected_fingerprint(order, plan)
    if expected is None:
        return None
    decision = decide_approved_plan_freshness(
        status=str(plan.status or ""),
        stored_fingerprint=str(plan.input_fingerprint or ""),
        expected_fingerprint=expected,
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
    expected = _expected_fingerprint(order, plan)
    if expected is None:
        return None
    decision = decide_uploaded_plan_mismatch(
        source_type=str(plan.source_type or ""),
        stored_fingerprint=str(plan.input_fingerprint or ""),
        expected_fingerprint=expected,
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
        # Manual Board Editor copies keep their frozen layout until an explicit
        # recreate. Auto-invalidation must not flag them as optimizer work.
        if str(getattr(plan, "source_type", None) or "") == BOARD_EDITOR:
            continue
        already_stale = bool(cint(plan.plan_needs_recalculation))
        expected = _expected_fingerprint(order, plan)
        if expected is None:
            continue
        decision = decide_draft_plan_freshness(
            status=str(plan.status or ""),
            stored_fingerprint=str(plan.input_fingerprint or ""),
            expected_fingerprint=expected,
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


def sync_uploaded_draft_manufacturing_trim(order: Any) -> str | None:
    """Keep Uploaded DXF Draft staleness aligned with manufacturing trim.

    System plan fingerprints include that plan's own trim, so editing System
    trim never stale-marks an Uploaded Draft through the order-input path.
    This sync compares manufacturing trim to the trim stored on the Uploaded
    Draft (the value used at DXF validation) and only flips
    ``plan_needs_recalculation``. It never rewrites uploaded geometry, trim,
    or Approved/historical revisions.

    When trim rematches, the stale flag clears only if fingerprint freshness
    still allows it — restoring trim alone does not waive other staleness.
    """

    if not getattr(order, "name", None) or getattr(order, "is_new", lambda: False)():
        return None

    rows = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order.name,
            "plan_kind": "Order",
            "source_type": UPLOADED_DXF,
            "status": DRAFT,
        },
        fields=["name", "status", "source_type", "trim_margin_mm", "input_fingerprint", "plan_needs_recalculation"],
        order_by="revision desc, creation desc",
        limit_page_length=1,
    )
    if not rows:
        return None

    row = rows[0]
    plan_name = str(row.get("name") or "")
    if not plan_name:
        return None

    manufacturing = manufacturing_plan_settings(order.name)
    decision = decide_uploaded_manufacturing_trim_mismatch(
        source_type=str(row.get("source_type") or ""),
        status=str(row.get("status") or ""),
        uploaded_trim_mm=row.get("trim_margin_mm"),
        manufacturing_trim_mm=manufacturing.preferred_trim_mm,
    )
    already_stale = bool(cint(row.get("plan_needs_recalculation")))

    if decision.should_invalidate:
        if not already_stale:
            _mark_plan_needs_recalculation(plan_name)
        return plan_name

    if not already_stale:
        return None

    plan = frappe.get_doc("Cutting Plan", plan_name)
    expected = _expected_fingerprint(order, plan)
    if expected is None:
        return None
    fingerprint = decide_uploaded_plan_mismatch(
        source_type=str(plan.source_type or ""),
        stored_fingerprint=str(plan.input_fingerprint or ""),
        expected_fingerprint=expected,
        already_needs_recalculation=False,
    )
    if fingerprint.should_invalidate:
        return None

    _set_plan_needs_recalculation(plan_name, 0)
    return None


__all__ = [
    "apply_stale_approved_plan_cancellation",
    "invalidate_stale_draft_plans",
    "sync_uploaded_draft_manufacturing_trim",
]
