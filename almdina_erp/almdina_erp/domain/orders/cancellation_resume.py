from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    ACTIVE_STAGE_STATUSES,
    department_status_for_stage_status,
    normalize_order_status,
    order_status_for_stage,
)


SNAPSHOT_VERSION = 1


@dataclass(frozen=True, slots=True)
class CancelledStageSnapshot:
    name: str
    previous_status: str
    stage_type: str | None = None
    department_label: str | None = None


@dataclass(frozen=True, slots=True)
class CancellationSnapshot:
    order_status: str
    department_status: str | None
    current_production_stage: str | None
    current_assignee: str | None
    current_department: str | None
    production_path: str | None
    approved_plan: str | None
    approved_plan_status: str | None
    restore_plan: bool
    stages: tuple[CancelledStageSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ResumeStageTarget:
    name: str
    target_status: str


@dataclass(frozen=True, slots=True)
class ResumePlan:
    order_status: str
    department_status: str | None
    restore_plan: bool
    approved_plan: str | None
    stages: tuple[ResumeStageTarget, ...]


@dataclass(frozen=True, slots=True)
class StageResumeFact:
    name: str
    status: str
    sequence: int
    stage_type: str | None = None
    department_label: str | None = None


def can_resume_cancelled_order(
    status: str | None,
    revision_state: str | None = None,
) -> bool:
    if str(revision_state or "Current") == "Superseded":
        return False
    return normalize_order_status(status) == "Cancelled"


def restore_cancelled_stage(current_status: str, previous_status: str) -> str:
    if current_status != "Cancelled":
        raise ValueError(f"Cannot restore stage from {current_status}")
    if previous_status not in ACTIVE_STAGE_STATUSES:
        raise ValueError(f"Cannot restore cancelled stage to {previous_status}")
    return previous_status


def build_cancellation_snapshot(
    *,
    order_status: str | None,
    department_status: str | None,
    current_production_stage: str | None,
    current_assignee: str | None,
    current_department: str | None,
    production_path: str | None,
    approved_plan: str | None,
    approved_plan_status: str | None,
    cancellable_stages: Iterable[CancelledStageSnapshot],
) -> CancellationSnapshot:
    plan_name = str(approved_plan or "").strip() or None
    plan_status = str(approved_plan_status or "").strip() or None
    return CancellationSnapshot(
        order_status=normalize_order_status(order_status),
        department_status=str(department_status or "").strip() or None,
        current_production_stage=str(current_production_stage or "").strip() or None,
        current_assignee=str(current_assignee or "").strip() or None,
        current_department=str(current_department or "").strip() or None,
        production_path=str(production_path or "").strip() or None,
        approved_plan=plan_name,
        approved_plan_status=plan_status,
        restore_plan=bool(plan_name) and plan_status == "Approved",
        stages=tuple(cancellable_stages),
    )


def snapshot_to_mapping(snapshot: CancellationSnapshot) -> dict[str, object]:
    return {
        "version": SNAPSHOT_VERSION,
        "order_status": snapshot.order_status,
        "department_status": snapshot.department_status,
        "current_production_stage": snapshot.current_production_stage,
        "current_assignee": snapshot.current_assignee,
        "current_department": snapshot.current_department,
        "production_path": snapshot.production_path,
        "approved_plan": snapshot.approved_plan,
        "approved_plan_status": snapshot.approved_plan_status,
        "restore_plan": snapshot.restore_plan,
        "stages": [
            {
                "name": stage.name,
                "previous_status": stage.previous_status,
                "stage_type": stage.stage_type,
                "department_label": stage.department_label,
            }
            for stage in snapshot.stages
        ],
    }


def snapshot_from_mapping(payload: object) -> CancellationSnapshot | None:
    if not isinstance(payload, Mapping):
        return None
    order_status = str(payload.get("order_status") or "").strip()
    if not order_status:
        return None
    stages: list[CancelledStageSnapshot] = []
    for row in payload.get("stages") or ():
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "").strip()
        previous_status = str(row.get("previous_status") or "").strip()
        if not name or not previous_status:
            continue
        stages.append(
            CancelledStageSnapshot(
                name=name,
                previous_status=previous_status,
                stage_type=str(row.get("stage_type") or "").strip() or None,
                department_label=str(row.get("department_label") or "").strip() or None,
            )
        )
    restore_plan = payload.get("restore_plan")
    approved_plan = str(payload.get("approved_plan") or "").strip() or None
    approved_plan_status = str(payload.get("approved_plan_status") or "").strip() or None
    if restore_plan is None:
        restore_plan = bool(approved_plan) and approved_plan_status == "Approved"
    return CancellationSnapshot(
        order_status=order_status,
        department_status=str(payload.get("department_status") or "").strip() or None,
        current_production_stage=str(payload.get("current_production_stage") or "").strip()
        or None,
        current_assignee=str(payload.get("current_assignee") or "").strip() or None,
        current_department=str(payload.get("current_department") or "").strip() or None,
        production_path=str(payload.get("production_path") or "").strip() or None,
        approved_plan=approved_plan,
        approved_plan_status=approved_plan_status,
        restore_plan=bool(restore_plan),
        stages=tuple(stages),
    )


def resume_from_snapshot(snapshot: CancellationSnapshot) -> ResumePlan:
    stages = tuple(
        ResumeStageTarget(
            name=stage.name,
            target_status=restore_cancelled_stage("Cancelled", stage.previous_status),
        )
        for stage in snapshot.stages
    )
    return ResumePlan(
        order_status=snapshot.order_status,
        department_status=snapshot.department_status,
        restore_plan=snapshot.restore_plan,
        approved_plan=snapshot.approved_plan if snapshot.restore_plan else None,
        stages=stages,
    )


def resume_without_snapshot(
    *,
    current_production_stage: str | None,
    stages: Iterable[StageResumeFact],
    approved_plan: str | None,
    approved_plan_status: str | None,
) -> ResumePlan:
    stage_list = tuple(stages)
    current_name = str(current_production_stage or "").strip() or None
    current = next((stage for stage in stage_list if stage.name == current_name), None)
    plan_name = str(approved_plan or "").strip() or None
    restore_plan = bool(plan_name) and str(approved_plan_status or "") == "Cancelled"

    if current is None:
        return ResumePlan(
            order_status="Draft",
            department_status=None,
            restore_plan=restore_plan,
            approved_plan=plan_name if restore_plan else None,
            stages=(),
        )

    targets = tuple(
        ResumeStageTarget(name=stage.name, target_status="Pending")
        for stage in stage_list
        if stage.status == "Cancelled" and stage.sequence >= current.sequence
    )
    if targets:
        order_status = order_status_for_stage(current.stage_type, current.department_label)
        department_status = department_status_for_stage_status("Pending")
    else:
        order_status = "Ready for Delivery"
        department_status = department_status_for_stage_status("Completed")
    return ResumePlan(
        order_status=order_status,
        department_status=department_status,
        restore_plan=restore_plan,
        approved_plan=plan_name if restore_plan else None,
        stages=targets,
    )


def select_resume_plan(
    snapshot: CancellationSnapshot | None,
    *,
    current_production_stage: str | None,
    stages: Iterable[StageResumeFact],
    approved_plan: str | None,
    approved_plan_status: str | None,
) -> ResumePlan:
    if snapshot is not None:
        return resume_from_snapshot(snapshot)
    return resume_without_snapshot(
        current_production_stage=current_production_stage,
        stages=stages,
        approved_plan=approved_plan,
        approved_plan_status=approved_plan_status,
    )


__all__ = [
    "SNAPSHOT_VERSION",
    "CancellationSnapshot",
    "CancelledStageSnapshot",
    "ResumePlan",
    "ResumeStageTarget",
    "StageResumeFact",
    "build_cancellation_snapshot",
    "can_resume_cancelled_order",
    "restore_cancelled_stage",
    "resume_from_snapshot",
    "resume_without_snapshot",
    "select_resume_plan",
    "snapshot_from_mapping",
    "snapshot_to_mapping",
]
