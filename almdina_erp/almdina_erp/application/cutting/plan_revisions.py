from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    CuttingPlanLifecycleError,
    ensure_draft_editable,
    normalize_source_type,
    revision_from_approved,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    PlanSettings,
    PlanSettingsValidationError,
    normalize_plan_settings,
)


@dataclass(frozen=True, slots=True)
class PlanRecord:
    name: str
    order_name: str
    revision: int
    status: str
    source_type: str
    based_on_plan: str | None
    settings: PlanSettings


class CuttingPlanRepository(Protocol):
    def get(self, plan_name: str) -> PlanRecord: ...

    def create_draft(
        self,
        *,
        order_name: str,
        revision: int,
        status: str,
        source_type: str,
        based_on_plan: str | None,
        settings: PlanSettings,
    ) -> PlanRecord: ...

    def save_settings(self, plan_name: str, settings: PlanSettings) -> PlanRecord: ...


@dataclass(frozen=True, slots=True)
class CreatePlanRevisionCommand:
    approved_plan_name: str
    source_type: str | None = None


@dataclass(frozen=True, slots=True)
class UpdatePlanSettingsCommand:
    plan_name: str
    settings: PlanSettings


def create_revision(
    command: CreatePlanRevisionCommand,
    repository: CuttingPlanRepository,
) -> PlanRecord:
    approved = repository.get(command.approved_plan_name)
    revision = revision_from_approved(
        current_name=approved.name,
        current_revision=approved.revision,
        current_status=approved.status,
        source_type=command.source_type or approved.source_type,
    )
    return repository.create_draft(
        order_name=approved.order_name,
        revision=revision.revision,
        status=revision.status,
        source_type=revision.source_type,
        based_on_plan=revision.based_on_plan,
        settings=approved.settings,
    )


def update_settings(
    command: UpdatePlanSettingsCommand,
    repository: CuttingPlanRepository,
) -> PlanRecord:
    plan = repository.get(command.plan_name)
    ensure_draft_editable(plan.status)
    try:
        normalized = normalize_plan_settings(
            optimization_mode=command.settings.optimization_mode,
            machine_type=command.settings.machine_type,
            optimization_time_limit_sec=command.settings.optimization_time_limit_sec,
            kerf_mm=command.settings.kerf_mm,
            preferred_trim_mm=command.settings.preferred_trim_mm,
        )
    except PlanSettingsValidationError as error:
        raise CuttingPlanLifecycleError(str(error)) from error
    return repository.save_settings(plan.name, normalized)


def assert_approvable(plan: PlanRecord) -> None:
    if plan.status != DRAFT:
        raise CuttingPlanLifecycleError("only_draft_plan_can_be_approved")
    normalize_source_type(plan.source_type)


def assert_revision_source(plan: PlanRecord) -> None:
    if plan.status != APPROVED:
        raise CuttingPlanLifecycleError("revision_source_must_be_approved")


__all__ = [
    "CreatePlanRevisionCommand",
    "CuttingPlanRepository",
    "PlanRecord",
    "PlanSettings",
    "UpdatePlanSettingsCommand",
    "assert_approvable",
    "assert_revision_source",
    "create_revision",
    "update_settings",
]
