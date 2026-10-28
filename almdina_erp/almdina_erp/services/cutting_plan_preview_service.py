from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.application.cutting.plan_preview_session import (
    CuttingPlanPreviewSession,
    optimizer_settings_fingerprint,
    merge_preview_candidates,
)
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import DRAFT, SYSTEM
from almdina_erp.almdina_erp.domain.cutting.plan_settings import settings_for_system_search
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import OptimizationOutcome
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import seed_plan_settings
from almdina_erp.almdina_erp.services.export_validation_service import validate_cutting_plan_issues
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    cutting_plan_capability_allowed,
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_repository import (
    FrappeCuttingPlanCommandRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    apply_plan_costs,
    factory_execution_edge_cost,
    initialize_draft_plan_cost_snapshot,
    refresh_order_commercial_totals,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_preview_commit import (
    apply_exact_system_preview,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_preview_store import (
    FrappeCuttingPlanPreviewStore,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    calculate_system_plan,
    apply_calculation_outcome,
    plan_input_fingerprint,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_assignment_access import (
    require_stage_assignment_access,
)
from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
    _assert_recalculation_state,
    _settings_from_plan,
    _changed_settings,
    plan_payload,
)
from almdina_erp.almdina_erp.services.plan_settings_edit_service import (
    assert_plan_settings_edit_lifecycle,
    normalize_plan_settings_updates,
)


_SETTING_TO_PLAN_FIELD = {
    "packing_mode": "optimization_mode",
    "cutting_machine_type": "machine_type",
    "kerf_mm": "kerf_mm",
    "trim_margin_mm": "trim_margin_mm",
    "optimization_time_limit_sec": "optimization_time_limit_sec",
}


def _require_preview_capabilities(order: Any) -> None:
    require_cutting_plan_capability(
        order,
        Capability.RECALCULATE_PLAN,
        message=_("لا تملك صلاحية معاينة خطة القص لهذا الطلب."),
    )


def _normalized_settings(values: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_plan_settings_updates(values)
    missing = [name for name in _SETTING_TO_PLAN_FIELD if name not in normalized]
    if missing:
        frappe.throw(
            _("إعدادات معاينة خطة القص غير مكتملة. أعد تحميل الصفحة ثم حاول مرة أخرى."),
            frappe.ValidationError,
        )
    return normalized


def _apply_settings(plan: Any, settings: dict[str, Any]) -> None:
    for setting_name, plan_field in _SETTING_TO_PLAN_FIELD.items():
        setattr(plan, plan_field, settings[setting_name])


def _preview_cost_summary(plan: Any) -> dict[str, float]:
    return {
        "board_rate_usd": flt(plan.board_rate_usd),
        "cutting_cost_per_board_usd": flt(plan.cutting_cost_per_board_usd),
        "mdf_cost_usd": flt(plan.mdf_cost_usd),
        "cutting_cost_usd": flt(plan.cutting_cost_usd),
        "edge_cost_usd": flt(plan.edge_cost_usd),
        "total_cost_usd": flt(plan.total_cost_usd),
    }


def _preview_summary(
    plan: Any,
    *,
    include_cost: bool = False,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "settings": {
            "packing_mode": str(plan.optimization_mode or ""),
            "cutting_machine_type": str(plan.machine_type or ""),
            "kerf_mm": plan.kerf_mm,
            "trim_margin_mm": plan.trim_margin_mm,
            "optimization_time_limit_sec": plan.optimization_time_limit_sec,
        },
        "engine": {
            "method_key": str(plan.method_key or ""),
            "method_label": str(plan.method_label or ""),
            "attempts": int(plan.attempts or 0),
            "solver_status": str(plan.solver_status or ""),
            "elapsed_sec": float(plan.search_elapsed_sec or 0),
        },
        "quality": {
            "estimated_cut_count": int(plan.estimated_cut_count or 0),
            "estimated_cut_length_m": float(plan.estimated_cut_length_m or 0),
            "largest_reusable_free_area_m2": float(
                plan.largest_reusable_free_area_m2 or 0
            ),
            "rotation_count": int(plan.rotation_count or 0),
        },
        "totals": {
            "required_boards": int(plan.required_boards or 0),
            "used_area_m2": float(plan.used_area_m2 or 0),
            "total_source_area_m2": float(plan.total_source_area_m2 or 0),
            "waste_area_m2": float(plan.waste_area_m2 or 0),
            "waste_percent": float(plan.waste_percent or 0),
        },
        "validation": {
            "status": str(plan.validation_status or ""),
            "errors": str(plan.validation_errors or ""),
            "needs_recalculation": bool(plan.plan_needs_recalculation),
        },
    }
    if include_cost:
        summary["cost"] = _preview_cost_summary(plan)
    return summary


def _system_draft(order: Any, capability: str) -> Any:
    repository = FrappeCuttingPlanCommandRepository(capability)
    plan = repository.latest_document(order.name,source_type=SYSTEM,status=DRAFT)
    if plan:
        return plan
    # Initial preview is entirely detached: no revision, cost or geometry is
    # persisted until the selected candidate is committed under the order lock.
    latest = repository._latest_plan_row(order.name,plan_kind="Order")
    approved = repository._latest_plan_row(order.name,plan_kind="Order",status="Approved")
    settings = settings_for_system_search(seed_plan_settings(order.name))
    plan = frappe.new_doc("Cutting Plan")
    plan.name = "__new_system__"
    plan.door_cutting_order = order.name
    plan.source_type, plan.status, plan.plan_kind = SYSTEM,DRAFT,"Order"
    plan.revision = int((approved or latest or {}).get('revision') or 0)+1
    _apply_settings(plan,dict(packing_mode=settings.optimization_mode,cutting_machine_type=settings.machine_type,
        kerf_mm=settings.kerf_mm,trim_margin_mm=settings.preferred_trim_mm,
        optimization_time_limit_sec=settings.optimization_time_limit_sec))
    from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
    plan.modified = "new:"+fingerprint_payload(dict(latest=latest,approved=approved,settings=_settings_from_plan(plan).__dict__
        if hasattr(settings,'__dict__') else {k:getattr(plan,v) for k,v in _SETTING_TO_PLAN_FIELD.items()}))
    return plan


def _settings_authority(order, source, settings):
    physical = {k:v for k,v in settings.items() if k!='packing_mode'}
    if _changed_settings(source,physical):
        require_cutting_plan_capability(order,Capability.EDIT_OPTIMIZER_SETTINGS,
            message=_("لا تملك صلاحية تعديل إعدادات خطة القص لهذا الطلب."))


def _session(order, preview_id):
    session = FrappeCuttingPlanPreviewStore().get(str(preview_id or ''))
    if not session or session.version not in (1, 2) or (session.expires_at and now_datetime()>=datetime.fromisoformat(session.expires_at)):
        frappe.throw(_("The cutting plan preview expired. Create a new preview."),frappe.ValidationError)
    if session.order_name!=order.name or session.user!=frappe.session.user:
        frappe.throw(_("معاينة خطة القص لا تخص هذا المستخدم أو الطلب."),frappe.PermissionError)
    source = _system_draft(order,Capability.RECALCULATE_PLAN)
    if source.name!=session.source_plan_name or str(source.modified or '')!=session.source_plan_modified or (
        session.source_revision and int(source.revision or 0)!=session.source_revision):
        frappe.throw(_("تغيّرت نسخة خطة القص بعد المعاينة. أعد المعاينة قبل الحفظ."),frappe.ValidationError)
    if optimizer_settings_fingerprint(session.settings)!=session.settings_fingerprint:
        frappe.throw(_("معاينة خطة القص غير صالحة للحفظ."),frappe.ValidationError)
    _settings_authority(order,source,session.settings)
    check = frappe.copy_doc(source)
    _apply_settings(check,session.settings)
    if session.snapshot.get('generation_input_fingerprint')!=plan_input_fingerprint(order,check):
        frappe.throw(_("تغيّرت نسخة خطة القص بعد المعاينة. أعد المعاينة قبل الحفظ."),frappe.ValidationError)
    return session,source


def _candidate(session,candidate_id):
    if session.version == 1 and not session.candidates and not candidate_id:
        # Existing short-lived v1 tokens retain their original single-plan flow.
        return dict(snapshot=session.snapshot,summary={},candidate_id='')
    if not candidate_id:
        frappe.throw(_("Invalid cutting plan candidate."),frappe.ValidationError)
    key = str(candidate_id)
    candidate = session.candidates.get(key)
    if not candidate:
        frappe.throw(_("Invalid cutting plan candidate."),frappe.ValidationError)
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    if (candidate.get('candidate_id') != key
            or candidate.get('manufacturing_status') != 'Validated'
            or geometry_signature(candidate['snapshot']) != candidate.get('geometry_fingerprint')):
        frappe.throw(_("Invalid cutting plan candidate."),frappe.ValidationError)
    return candidate


def _selected_summary(order, source_plan, session, candidate):
    """Estimate only the displayed candidate, on a detached document."""
    include_cost = cutting_plan_capability_allowed(order, Capability.VIEW_COSTS)
    if include_cost:
        preview_plan = frappe.copy_doc(source_plan)
        initialize_draft_plan_cost_snapshot(order, preview_plan)
        apply_exact_system_preview(order, preview_plan, settings=session.settings,
            snapshot=candidate['snapshot'], expected_input_fingerprint=session.input_fingerprint)
        apply_plan_costs(preview_plan, edge_cost_usd=factory_execution_edge_cost(order, preview_plan))
        return _preview_summary(preview_plan, include_cost=True)
    return candidate['summary']


def _response(session,source,order):
    candidates = list(session.candidates.values())
    first = candidates[0]
    return dict(preview_version=session.version,preview_id=session.preview_id,order_name=session.order_name,
        source_plan_name=session.source_plan_name,source_plan_revision=int(source.revision or 0),
        source_plan_modified=session.source_plan_modified,settings_fingerprint=session.settings_fingerprint,
        input_fingerprint=session.input_fingerprint,plan=first['snapshot'],summary=_selected_summary(order,source,session,first),
        candidate_id=first['candidate_id'],candidates=[{k:v for k,v in c.items() if k!='snapshot'} for c in candidates],
        is_first_system=source.name=='__new_system__',is_preview=True,search_round=session.search_round,
        can_continue=session.search_round<2,search_budget_sec=session.settings['optimization_time_limit_sec'],
        expires_at=session.expires_at,expires_in_sec=max(0,(datetime.fromisoformat(session.expires_at)-now_datetime()).total_seconds()) if session.expires_at else 900)


def _build_session(order,source,settings,*,previous=None):
    preview_plan = frappe.copy_doc(source)
    _apply_settings(preview_plan,settings)
    outcome = calculate_system_plan(order,preview_plan,**(
        dict(seed_plans=previous.search_seeds,search_round=previous.search_round+1) if previous else {}))
    candidates = {}
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    seen = set()
    eligible_seeds = []
    for index,snapshot in enumerate(outcome.candidate_snapshots or (outcome.snapshot,)):
        if not (snapshot.get('validation') or {}).get('is_valid'):
            continue
        trial = frappe.copy_doc(source)
        _apply_settings(trial,settings)
        apply_calculation_outcome(order,trial,OptimizationOutcome(dict(snapshot),'',len(snapshot['sheets']),
            str(snapshot.get('method_label') or ''),outcome.expanded_pieces),
            fingerprint=snapshot.get('input_fingerprint') or plan_input_fingerprint(order,trial))
        if validate_cutting_plan_issues(trial):
            continue
        key = frappe.generate_hash(length=24)
        saved_snapshot = sanitize_plan_snapshot(frappe.parse_json(trial.snapshot_json))
        saved_snapshot['preview_candidate_id'] = key
        signature = geometry_signature(saved_snapshot)
        if signature in seen:
            continue
        seen.add(signature)
        if index<len(outcome.search_seeds):
            eligible_seeds.append(outcome.search_seeds[index])
        candidates[key] = dict(candidate_id=key,geometry_fingerprint=signature,
            manufacturing_status='Validated',snapshot=saved_snapshot,
            summary=_preview_summary(trial,include_cost=False))
        if len(candidates)==5:
            break
    if previous:
        candidates = merge_preview_candidates(candidates,previous.candidates)
    if not candidates:
        frappe.throw(_("No manufacturing-valid cutting plan was found."),frappe.ValidationError)
    first = next(iter(candidates.values()))
    session = CuttingPlanPreviewSession(preview_id=frappe.generate_hash(length=32),order_name=order.name,
        user=frappe.session.user,source_plan_name=source.name,source_plan_modified=str(source.modified or ''),
        source_revision=int(source.revision or 0),input_fingerprint=str(first['snapshot']['input_fingerprint']),
        settings_fingerprint=optimizer_settings_fingerprint(settings),settings=dict(settings),
        snapshot=first['snapshot'],candidates=candidates,search_seeds=tuple(eligible_seeds),
        search_round=previous.search_round+1 if previous else 0,created_at=str(now_datetime()),
        expires_at=previous.expires_at if previous else str(now_datetime()+timedelta(minutes=15)))
    FrappeCuttingPlanPreviewStore().put(session)
    return session


@frappe.whitelist()
def preview_cutting_plan(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Calculate a disposable System-plan preview without any DB mutation."""

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)

    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    _require_preview_capabilities(order)
    require_stage_assignment_access(order)
    assert_plan_settings_edit_lifecycle(order)
    _assert_recalculation_state(order)

    source_plan = _system_draft(order, Capability.RECALCULATE_PLAN)
    requested_settings = {
        "packing_mode": packing_mode,
        "cutting_machine_type": cutting_machine_type,
        "kerf_mm": kerf_mm,
        "trim_margin_mm": trim_margin_mm,
        "optimization_time_limit_sec": optimization_time_limit_sec,
    }
    # Validate any explicit historical API mode, then apply the same trusted
    # server policy used by calculation before creating the preview fingerprint.
    settings = _normalized_settings({
        **requested_settings,
        "packing_mode": (packing_mode if packing_mode is not None else
                         settings_for_system_search(_settings_from_plan(source_plan)).optimization_mode),
    })
    settings["packing_mode"] = settings_for_system_search(
        _settings_from_plan(source_plan, settings)
    ).optimization_mode

    _settings_authority(order,source_plan,settings)
    session = _build_session(order,source_plan,settings)
    return _response(session,source_plan,order)


def _preview_order(order_name):
    order = frappe.get_doc('Door Cutting Order',str(order_name or '').strip())
    order.check_permission('read')
    _require_preview_capabilities(order)
    require_stage_assignment_access(order)
    assert_plan_settings_edit_lifecycle(order)
    _assert_recalculation_state(order)
    return order


@frappe.whitelist()
def select_cutting_plan_candidate(order_name: str,preview_id: str,candidate_id: str):
    order = _preview_order(order_name)
    session,source = _session(order,preview_id)
    candidate = _candidate(session,candidate_id)
    return dict(preview_id=session.preview_id,candidate_id=candidate['candidate_id'],
                order_name=order.name,plan=candidate['snapshot'],summary=_selected_summary(order,source,session,candidate),
                geometry_fingerprint=candidate.get('geometry_fingerprint',''))


@frappe.whitelist()
def continue_cutting_plan_search(order_name: str,preview_id: str):
    # Per-order transaction lock serializes continuation and commit. Each explicit
    # request authorizes one additional batch; three batches and original TTL max.
    frappe.db.sql('select name from `tabDoor Cutting Order` where name = %s for update',(order_name,))
    order = _preview_order(order_name)
    previous,source = _session(order,preview_id)
    if previous.search_round>=2:
        frappe.throw(_("The search batch limit was reached. Create a new preview."),frappe.ValidationError)
    session = _build_session(order,source,previous.settings,previous=previous)
    FrappeCuttingPlanPreviewStore().discard(previous.preview_id)
    return _response(session,source,order)


@frappe.whitelist()
def discard_cutting_plan_preview(order_name: str,preview_id: str):
    order = _preview_order(order_name)
    session = FrappeCuttingPlanPreviewStore().get(preview_id)
    if session and session.order_name==order.name and session.user==frappe.session.user:
        FrappeCuttingPlanPreviewStore().discard(preview_id)
    return {'discarded': True}


@frappe.whitelist()
def commit_cutting_plan_preview(order_name: str, preview_id: str, candidate_id: str | None = None) -> dict[str, Any]:
    """Commit exactly one trusted preview; never execute the optimizer again."""

    name = str(order_name or "").strip()
    token = str(preview_id or "").strip()
    if not name or not token:
        frappe.throw(_("معاينة خطة القص غير صالحة للحفظ."), frappe.ValidationError)

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    _require_preview_capabilities(order)
    require_stage_assignment_access(order)
    assert_plan_settings_edit_lifecycle(order)
    _assert_recalculation_state(order)

    session,source = _session(order,token)
    candidate = _candidate(session,candidate_id)
    consumed = FrappeCuttingPlanPreviewStore().consume(token)
    if not consumed:
        frappe.throw(_("The cutting plan preview expired. Create a new preview."),frappe.ValidationError)
    repository = FrappeCuttingPlanCommandRepository(Capability.RECALCULATE_PLAN)
    plan = source if source.name!='__new_system__' else repository.ensure_system_draft(order)
    if int(plan.revision or 0)!=int(source.revision or 0):
        frappe.throw(_("تغيّرت نسخة خطة القص بعد المعاينة. أعد المعاينة قبل الحفظ."),frappe.ValidationError)
    initialize_draft_plan_cost_snapshot(order, plan)
    apply_exact_system_preview(
        order,
        plan,
        settings=session.settings,
        snapshot=candidate["snapshot"],
        expected_input_fingerprint=session.input_fingerprint,
    )
    apply_plan_costs(plan, edge_cost_usd=factory_execution_edge_cost(order, plan))
    repository.save_document(plan)
    refresh_order_commercial_totals(order, plan)
    from almdina_erp.almdina_erp.services.final_price_approval_service import (
        maybe_invalidate_final_price_approval,
    )

    maybe_invalidate_final_price_approval(
        order.name,
        reason="cost_plan_basis_changed",
        only_if_basis_changed=True,
        order=order,
    )
    order.add_comment(
        "Info",
        text=_("تم حفظ معاينة خطة القص {0} بواسطة {1}.").format(
            plan.name,
            frappe.session.user,
        ),
    )

    result = plan_payload(plan, order)
    result["committed_preview_id"] = token
    result["exact_preview_commit"] = True
    result["committed_candidate_id"] = candidate["candidate_id"]
    result["candidate_geometry_fingerprint"] = candidate.get("geometry_fingerprint", "")
    return result


__all__ = ["commit_cutting_plan_preview", "preview_cutting_plan", "select_cutting_plan_candidate",
           "continue_cutting_plan_search", "discard_cutting_plan_preview"]
