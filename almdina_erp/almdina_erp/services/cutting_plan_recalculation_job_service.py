from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.application.cutting.system_plan_recalculation_job import (
    COMPLETED,
    ENQUEUE,
    FAILED,
    MARK_PENDING_RERUN,
    QUEUED,
    RUNNING,
    RecalculationFacts,
    decide_after_system_plan_recalculation_job,
    decide_enqueue_system_plan_recalculation,
    has_cuttable_pieces,
    job_presentation,
    system_draft_is_stale,
    JobState,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import DRAFT, SYSTEM
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    cutting_plan_capability_allowed,
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    plan_input_fingerprint,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_plan_recalculation_job_store import (
    FrappeSystemPlanRecalculationJobStore,
)
from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
    recalculate_system_plan,
    recalculation_is_allowed,
)


_MIN_JOB_TIMEOUT_SEC = 300
_JOB_TIMEOUT_MULTIPLIER = 6
_JOB_TIMEOUT_BUFFER_SEC = 60


def _store() -> FrappeSystemPlanRecalculationJobStore:
    return FrappeSystemPlanRecalculationJobStore()


def _authorized_order(order_name: str) -> Any:
    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    return order


def _job_id(order_name: str, generation: int) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in str(order_name or ""))
    return f"almdina-sys-plan-recalc-{safe}-{int(generation or 0)}"


def _latest_system_draft(order_name: str) -> Any | None:
    names = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order_name,
            "plan_kind": "Order",
            "source_type": SYSTEM,
            "status": DRAFT,
        },
        pluck="name",
        order_by="revision desc, modified desc",
        limit=1,
    )
    if not names:
        return None
    return frappe.get_doc("Cutting Plan", names[0])


def _facts_for(order: Any) -> RecalculationFacts:
    plan = _latest_system_draft(order.name)
    expected = plan_input_fingerprint(order, plan) if plan else ""
    return RecalculationFacts(
        has_recalculate_capability=cutting_plan_capability_allowed(
            order,
            Capability.RECALCULATE_PLAN,
        ),
        lifecycle_allows=recalculation_is_allowed(order),
        has_cuttable_pieces=has_cuttable_pieces(getattr(order, "pieces", None)),
        has_system_draft=plan is not None,
        system_draft_is_stale=system_draft_is_stale(
            has_system_draft=plan is not None,
            needs_recalculation=bool(cint(getattr(plan, "plan_needs_recalculation", 0))),
            stored_fingerprint=str(getattr(plan, "input_fingerprint", None) or ""),
            expected_fingerprint=expected,
        ),
    )


def _still_stale(order: Any) -> bool:
    facts = _facts_for(order)
    return (not facts.has_system_draft) or facts.system_draft_is_stale


def _job_timeout_sec(order: Any) -> int:
    plan = _latest_system_draft(order.name)
    time_limit = flt(getattr(plan, "optimization_time_limit_sec", 0) or 0)
    if time_limit <= 0:
        settings = frappe.get_cached_doc("Almdina ERP Settings")
        time_limit = flt(getattr(settings, "default_optimization_time_limit_sec", 0) or 10)
    return max(
        _MIN_JOB_TIMEOUT_SEC,
        int(time_limit * _JOB_TIMEOUT_MULTIPLIER) + _JOB_TIMEOUT_BUFFER_SEC,
    )


def _persist(state: JobState, *, notify: bool = True) -> JobState:
    store = _store()
    store.put(state)
    if notify:
        store.publish(state)
    return state


def _enqueue_worker(order: Any, requested_by: str, generation: int) -> None:
    frappe.enqueue(
        "almdina_erp.almdina_erp.services.cutting_plan_recalculation_job_service."
        "run_system_plan_recalculation_job",
        queue="long",
        timeout=_job_timeout_sec(order),
        enqueue_after_commit=True,
        job_id=_job_id(order.name, generation),
        order_name=order.name,
        requested_by=requested_by,
        generation=int(generation),
    )


def overlay_background_recalculation(order_name: str) -> dict[str, Any]:
    """Progress overlay for the plan workspace. Contains no cost scalars."""

    return job_presentation(_store().get(str(order_name or "").strip()))


@frappe.whitelist()
def get_system_plan_recalculation_status(order_name: str) -> dict[str, Any]:
    order = _authorized_order(order_name)
    if not (
        cutting_plan_capability_allowed(order, Capability.VIEW_CUTTING_PLAN)
        or cutting_plan_capability_allowed(order, Capability.RECALCULATE_PLAN)
        or cutting_plan_capability_allowed(order, Capability.VIEW_COSTS)
    ):
        frappe.throw(
            _("لا تملك صلاحية متابعة حساب خطة القص لهذا الطلب."),
            frappe.PermissionError,
        )
    return overlay_background_recalculation(order.name)


@frappe.whitelist()
def enqueue_system_plan_recalculation(order_name: str) -> dict[str, Any]:
    """Queue a System plan + cost recalculation after an explicit order save."""

    order = _authorized_order(order_name)
    require_cutting_plan_capability(
        order,
        Capability.RECALCULATE_PLAN,
        message=_("لا تملك صلاحية إعادة حساب خطة القص لهذا الطلب."),
    )

    store = _store()
    current = store.get(order.name)
    decision = decide_enqueue_system_plan_recalculation(_facts_for(order), current)
    if decision.action == MARK_PENDING_RERUN:
        if current is None:
            return {
                "queued": False,
                "reason": decision.reason,
                **job_presentation(current),
            }
        state = JobState(
            order_name=current.order_name,
            status=current.status,
            generation=current.generation,
            pending_rerun=True,
            queued_at=current.queued_at,
            error=current.error,
        )
        _persist(state, notify=False)
        return {"queued": False, "reason": decision.reason, **job_presentation(state)}

    if decision.action != ENQUEUE:
        return {
            "queued": False,
            "reason": decision.reason,
            **job_presentation(current),
        }

    state = JobState(
        order_name=order.name,
        status=QUEUED,
        generation=int(decision.next_generation),
        pending_rerun=False,
        queued_at=str(now_datetime()),
        error="",
    )
    _persist(state)
    try:
        _enqueue_worker(order, frappe.session.user, state.generation)
    except Exception as exc:
        failed = JobState(
            order_name=order.name,
            status=FAILED,
            generation=state.generation,
            pending_rerun=False,
            queued_at=state.queued_at,
            error=str(exc),
        )
        _persist(failed)
        frappe.log_error(str(exc), "System plan recalculation enqueue failed")
        return {"queued": False, "reason": "enqueue_failed", **job_presentation(failed)}

    return {"queued": True, "reason": decision.reason, **job_presentation(state)}


def run_system_plan_recalculation_job(
    order_name: str,
    requested_by: str,
    generation: int,
) -> None:
    """RQ worker: persist a fresh System plan and its operational costs."""

    name = str(order_name or "").strip()
    user = str(requested_by or "").strip()
    expected_generation = int(generation or 0)
    store = _store()
    current = store.get(name)
    if current is None or int(current.generation or 0) != expected_generation:
        return
    if current.status not in {QUEUED, RUNNING}:
        return

    running = JobState(
        order_name=name,
        status=RUNNING,
        generation=expected_generation,
        pending_rerun=current.pending_rerun,
        queued_at=current.queued_at,
        error="",
    )
    _persist(running)

    if user:
        frappe.set_user(user)

    try:
        order = frappe.get_doc("Door Cutting Order", name)
        order.check_permission("read")
        require_cutting_plan_capability(
            order,
            Capability.RECALCULATE_PLAN,
            message=_("لا تملك صلاحية إعادة حساب خطة القص لهذا الطلب."),
        )
        if not recalculation_is_allowed(order):
            raise frappe.ValidationError(
                _("لا يمكن إعادة حساب خطة القص في الحالة الحالية للطلب.")
            )
        if not has_cuttable_pieces(getattr(order, "pieces", None)):
            raise frappe.ValidationError(_("لا توجد قطع صالحة لحساب خطة القص."))

        if _still_stale(order):
            frappe.db.sql(
                "select name from `tabDoor Cutting Order` where name = %s for update",
                (name,),
            )
            order = frappe.get_doc("Door Cutting Order", name)
            recalculate_system_plan(order)

        latest = store.get(name) or running
        if int(latest.generation or 0) != expected_generation:
            return
        pending = bool(latest.pending_rerun)
        order = frappe.get_doc("Door Cutting Order", name)
        next_action = decide_after_system_plan_recalculation_job(
            succeeded=True,
            pending_rerun=pending,
            still_stale=_still_stale(order),
        )
        if next_action == ENQUEUE:
            follow = JobState(
                order_name=name,
                status=QUEUED,
                generation=expected_generation + 1,
                pending_rerun=False,
                queued_at=str(now_datetime()),
                error="",
            )
            _persist(follow)
            _enqueue_worker(order, user or frappe.session.user, follow.generation)
            return
        _persist(
            JobState(
                order_name=name,
                status=COMPLETED,
                generation=expected_generation,
                pending_rerun=False,
                queued_at=latest.queued_at,
                error="",
            )
        )
    except Exception as exc:
        latest = store.get(name) or running
        if int(latest.generation or 0) != expected_generation:
            return
        message = str(exc)
        frappe.log_error(message, "System plan recalculation job failed")
        pending = bool(latest.pending_rerun)
        retry = pending
        if retry:
            try:
                order = frappe.get_doc("Door Cutting Order", name)
                retry = _still_stale(order)
            except Exception:
                retry = False
        next_action = decide_after_system_plan_recalculation_job(
            succeeded=False,
            pending_rerun=retry,
            still_stale=retry,
        )
        if next_action == ENQUEUE:
            order = frappe.get_doc("Door Cutting Order", name)
            follow = JobState(
                order_name=name,
                status=QUEUED,
                generation=expected_generation + 1,
                pending_rerun=False,
                queued_at=str(now_datetime()),
                error="",
            )
            _persist(follow)
            _enqueue_worker(order, user or frappe.session.user, follow.generation)
            return
        _persist(
            JobState(
                order_name=name,
                status=FAILED,
                generation=expected_generation,
                pending_rerun=False,
                queued_at=latest.queued_at,
                error=message,
            )
        )


__all__ = [
    "enqueue_system_plan_recalculation",
    "get_system_plan_recalculation_status",
    "overlay_background_recalculation",
    "run_system_plan_recalculation_job",
]
