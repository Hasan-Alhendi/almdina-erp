from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.security.authorization import Capability


class ProductionStageDefinitionError(ValueError):
    """Raised when a stage-library command violates a business rule."""


class ProductionStageDefinitionConflict(ProductionStageDefinitionError):
    """Raised when a stage definition is edited from a stale snapshot."""


class ProductionStageDefinitionPermissionDenied(PermissionError):
    """Raised when the actor cannot manage the stage library."""


@dataclass(frozen=True, slots=True)
class ProductionStageDefinitionSnapshot:
    name: str
    stage_code: str
    stage_label: str
    description: str
    is_planning_default: bool
    disabled: bool
    modified: str


@dataclass(frozen=True, slots=True)
class SaveProductionStageDefinitionCommand:
    name: str | None
    stage_code: str
    stage_label: str
    description: str
    is_planning_default: bool
    expected_modified: str | None


class ProductionStageDefinitionPort(Protocol):
    def list_definitions(self) -> Sequence[ProductionStageDefinitionSnapshot]: ...

    def get_definitions(
        self,
        names: Sequence[str],
    ) -> Mapping[str, ProductionStageDefinitionSnapshot]: ...

    def save_definition(
        self,
        command: SaveProductionStageDefinitionCommand,
    ) -> ProductionStageDefinitionSnapshot: ...

    def set_disabled(
        self,
        name: str,
        *,
        disabled: bool,
        expected_modified: str,
    ) -> ProductionStageDefinitionSnapshot: ...

    def is_in_use(self, name: str) -> bool: ...

    def delete_definition(self, name: str, *, expected_modified: str) -> None: ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _require_management_permission(capabilities: frozenset[str] | set[str]) -> None:
    if Capability.EDIT_PRODUCTION_ROUTINGS not in capabilities:
        raise ProductionStageDefinitionPermissionDenied(
            "لا تملك صلاحية إدارة مكتبة مراحل الإنتاج."
        )


def stage_definition_command(
    payload: Mapping[str, Any],
) -> SaveProductionStageDefinitionCommand:
    if not isinstance(payload, Mapping):
        raise ProductionStageDefinitionError("بيانات المرحلة غير صالحة.")

    name = _text(payload.get("name")) or None
    stage_code = _text(payload.get("stage_code"))
    stage_label = _text(payload.get("stage_label"))
    description = _text(payload.get("description"))
    expected_modified = _text(payload.get("expected_modified")) or None

    if not stage_code:
        raise ProductionStageDefinitionError("رمز المرحلة مطلوب.")
    if not stage_label:
        raise ProductionStageDefinitionError("اسم المرحلة مطلوب.")
    if name and name != stage_code:
        raise ProductionStageDefinitionError(
            "رمز المرحلة ثابت بعد الإنشاء. أنشئ مرحلة جديدة إذا احتجت رمزًا مختلفًا."
        )
    if name and not expected_modified:
        raise ProductionStageDefinitionConflict(
            "نسخة المرحلة غير محددة. حدّث الصفحة ثم أعد المحاولة."
        )

    return SaveProductionStageDefinitionCommand(
        name=name,
        stage_code=stage_code,
        stage_label=stage_label,
        description=description,
        is_planning_default=_boolean(payload.get("is_planning_default")),
        expected_modified=expected_modified,
    )


def save_production_stage_definition(
    repository: ProductionStageDefinitionPort,
    capabilities: frozenset[str] | set[str],
    payload: Mapping[str, Any],
) -> ProductionStageDefinitionSnapshot:
    _require_management_permission(capabilities)
    return repository.save_definition(stage_definition_command(payload))


def set_production_stage_definition_disabled(
    repository: ProductionStageDefinitionPort,
    capabilities: frozenset[str] | set[str],
    *,
    name: str,
    disabled: Any,
    expected_modified: str,
) -> ProductionStageDefinitionSnapshot:
    _require_management_permission(capabilities)
    resolved_name = _text(name)
    resolved_version = _text(expected_modified)
    if not resolved_name:
        raise ProductionStageDefinitionError("رمز المرحلة مطلوب.")
    if not resolved_version:
        raise ProductionStageDefinitionConflict(
            "نسخة المرحلة غير محددة. حدّث الصفحة ثم أعد المحاولة."
        )
    return repository.set_disabled(
        resolved_name,
        disabled=_boolean(disabled),
        expected_modified=resolved_version,
    )


def delete_production_stage_definition(
    repository: ProductionStageDefinitionPort,
    capabilities: frozenset[str] | set[str],
    *,
    name: str,
    expected_modified: str,
) -> None:
    _require_management_permission(capabilities)
    resolved_name = _text(name)
    resolved_version = _text(expected_modified)
    if not resolved_name:
        raise ProductionStageDefinitionError("رمز المرحلة مطلوب.")
    if not resolved_version:
        raise ProductionStageDefinitionConflict(
            "نسخة المرحلة غير محددة. حدّث الصفحة ثم أعد المحاولة."
        )
    if repository.is_in_use(resolved_name):
        raise ProductionStageDefinitionError(
            "هذه المرحلة مستخدمة في مسار إنتاج. عطّلها بدل حذفها."
        )
    repository.delete_definition(
        resolved_name,
        expected_modified=resolved_version,
    )


__all__ = [
    "ProductionStageDefinitionConflict",
    "ProductionStageDefinitionError",
    "ProductionStageDefinitionPermissionDenied",
    "ProductionStageDefinitionPort",
    "ProductionStageDefinitionSnapshot",
    "SaveProductionStageDefinitionCommand",
    "delete_production_stage_definition",
    "save_production_stage_definition",
    "set_production_stage_definition_disabled",
    "stage_definition_command",
]
