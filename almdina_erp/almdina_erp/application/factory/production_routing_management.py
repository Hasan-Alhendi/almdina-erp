from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class ProductionRoutingManagementError(ValueError):
    """Raised when a routing-management command violates a business rule."""


class ProductionRoutingManagementConflict(ProductionRoutingManagementError):
    """Raised when the editor is based on a stale routing snapshot."""


class ProductionRoutingManagementPermissionDenied(PermissionError):
    """Raised when the actor cannot execute a routing-management command."""


@dataclass(frozen=True, slots=True)
class RoutingStageCommand:
    sequence: int
    workflow_stage: str
    operational_role: str
    is_planning_stage: bool = False
    legacy_stage_label: str | None = None


@dataclass(frozen=True, slots=True)
class SaveProductionRoutingCommand:
    name: str | None
    routing_name: str
    disabled: bool
    expected_modified: str | None
    stages: tuple[RoutingStageCommand, ...]


class ProductionRoutingManagementPort(Protocol):
    def save_routing(
        self,
        command: SaveProductionRoutingCommand,
    ) -> Mapping[str, Any]: ...

    def set_routing_disabled(
        self,
        name: str,
        *,
        disabled: bool,
        expected_modified: str,
    ) -> Mapping[str, Any]: ...

    def delete_routing(self, name: str, *, expected_modified: str) -> None: ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _stage_command(value: Any, index: int) -> RoutingStageCommand:
    if not isinstance(value, Mapping):
        raise ProductionRoutingManagementError(
            f"بيانات المرحلة رقم {index + 1} غير صالحة."
        )
    # stage_type remains accepted as a compatibility input while the existing
    # editor migrates its payload key. Production Workflow Stage uses the
    # immutable stage_code as its document identity, so this value is still the
    # real Link identity rather than a duplicated label/code source of truth.
    explicit_workflow_stage = _text(value.get("workflow_stage"))
    legacy_stage_code = _text(value.get("stage_type"))
    workflow_stage = explicit_workflow_stage or legacy_stage_code
    return RoutingStageCommand(
        sequence=(index + 1) * 10,
        workflow_stage=workflow_stage,
        operational_role=_text(value.get("operational_role")),
        is_planning_stage=_boolean(value.get("is_planning_stage")),
        legacy_stage_label=(
            None
            if explicit_workflow_stage
            else (_text(value.get("department_label")) or legacy_stage_code)
        ),
    )


def _validate_route_shape(
    *,
    name: str | None,
    routing_name: str,
    stages: tuple[RoutingStageCommand, ...],
) -> None:
    normalized_stage_ids = [stage.workflow_stage.casefold() for stage in stages]
    if len(normalized_stage_ids) != len(set(normalized_stage_ids)):
        raise ProductionRoutingManagementError(
            "لا يمكن تكرار المرحلة داخل مسار الإنتاج."
        )

    try:
        ProductionRoute(
            name=name or routing_name,
            label=routing_name,
            stages=tuple(
                RoutingStage(
                    sequence=stage.sequence,
                    stage_type=stage.workflow_stage,
                    department_label=stage.workflow_stage,
                    operational_role=stage.operational_role,
                    is_planning_stage=stage.is_planning_stage,
                )
                for stage in stages
            ),
        )
    except ValueError as error:
        raise ProductionRoutingManagementError(str(error)) from error


def routing_command(payload: Mapping[str, Any]) -> SaveProductionRoutingCommand:
    if not isinstance(payload, Mapping):
        raise ProductionRoutingManagementError("بيانات مسار الإنتاج غير صالحة.")

    name = _text(payload.get("name")) or None
    routing_name = _text(payload.get("routing_name"))
    expected_modified = _text(payload.get("expected_modified")) or None
    raw_stages = payload.get("stages")
    if not isinstance(raw_stages, (list, tuple)):
        raise ProductionRoutingManagementError("قائمة مراحل مسار الإنتاج مطلوبة.")
    stages = tuple(
        _stage_command(stage, index) for index, stage in enumerate(raw_stages)
    )

    if not routing_name:
        raise ProductionRoutingManagementError("اسم مسار الإنتاج مطلوب.")
    if name and not expected_modified:
        raise ProductionRoutingManagementConflict(
            "نسخة المسار غير محددة. حدّث الصفحة ثم أعد المحاولة."
        )
    if any(not stage.workflow_stage for stage in stages):
        raise ProductionRoutingManagementError("مرحلة الإنتاج مطلوبة.")

    _validate_route_shape(name=name, routing_name=routing_name, stages=stages)

    return SaveProductionRoutingCommand(
        name=name,
        routing_name=routing_name,
        disabled=_boolean(payload.get("disabled")),
        expected_modified=expected_modified,
        stages=stages,
    )


def save_production_routing(
    repository: ProductionRoutingManagementPort,
    capabilities: frozenset[str] | set[str],
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    command = routing_command(payload)
    required_capability = (
        Capability.EDIT_PRODUCTION_ROUTINGS
        if command.name
        else Capability.CREATE_PRODUCTION_ROUTINGS
    )
    if required_capability not in capabilities:
        action = "تعديل" if command.name else "إنشاء"
        raise ProductionRoutingManagementPermissionDenied(
            f"لا تملك صلاحية {action} مسارات الإنتاج."
        )
    return repository.save_routing(command)


def set_production_routing_disabled(
    repository: ProductionRoutingManagementPort,
    capabilities: frozenset[str] | set[str],
    *,
    name: str,
    disabled: Any,
    expected_modified: str,
) -> Mapping[str, Any]:
    if Capability.EDIT_PRODUCTION_ROUTINGS not in capabilities:
        raise ProductionRoutingManagementPermissionDenied(
            "لا تملك صلاحية تعديل مسارات الإنتاج."
        )
    resolved_name = _text(name)
    resolved_version = _text(expected_modified)
    if not resolved_name:
        raise ProductionRoutingManagementError("اسم مسار الإنتاج مطلوب.")
    if not resolved_version:
        raise ProductionRoutingManagementConflict(
            "نسخة المسار غير محددة. حدّث الصفحة ثم أعد المحاولة."
        )
    return repository.set_routing_disabled(
        resolved_name,
        disabled=_boolean(disabled),
        expected_modified=resolved_version,
    )


def delete_production_routing(
    repository: ProductionRoutingManagementPort,
    capabilities: frozenset[str] | set[str],
    *,
    name: str,
    expected_modified: str,
) -> None:
    if Capability.DELETE_PRODUCTION_ROUTINGS not in capabilities:
        raise ProductionRoutingManagementPermissionDenied(
            "لا تملك صلاحية حذف مسارات الإنتاج."
        )
    resolved_name = _text(name)
    resolved_version = _text(expected_modified)
    if not resolved_name:
        raise ProductionRoutingManagementError("اسم مسار الإنتاج مطلوب.")
    if not resolved_version:
        raise ProductionRoutingManagementConflict(
            "نسخة المسار غير محددة. حدّث الصفحة ثم أعد المحاولة."
        )
    repository.delete_routing(
        resolved_name,
        expected_modified=resolved_version,
    )


__all__ = [
    "ProductionRoutingManagementConflict",
    "ProductionRoutingManagementError",
    "ProductionRoutingManagementPermissionDenied",
    "ProductionRoutingManagementPort",
    "RoutingStageCommand",
    "SaveProductionRoutingCommand",
    "delete_production_routing",
    "routing_command",
    "save_production_routing",
    "set_production_routing_disabled",
]
