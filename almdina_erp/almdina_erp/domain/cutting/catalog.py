from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_OPTIMIZATION_MODE_ID = "auto_pro"


class UnsupportedOptimizationModeError(ValueError):
    """Raised when a value is outside the public and historical contracts."""


class OptimizationModeUnavailableError(ValueError):
    """Raised when a canonical mode has no current engine implementation."""

    def __init__(self, mode_id: str) -> None:
        self.mode_id = str(mode_id or "").strip()
        super().__init__(f"optimization_mode_not_implemented:{self.mode_id}")


@dataclass(frozen=True, slots=True)
class OptimizationMode:
    """Public optimization-mode contract kept separate from engine internals."""

    id: str
    label: str
    engine_mode: str | None

    @property
    def implemented(self) -> bool:
        return self.engine_mode is not None

    @property
    def executable(self) -> bool:
        """Whether this public mode can execute through the current engine."""

        return self.implemented

    def as_public_dict(self) -> dict[str, Any]:
        # ``available`` is retained for frontend/backward compatibility. It must
        # mean the same thing as executable so a name-only mode is never offered
        # as a selectable choice while still remaining visible in the catalog.
        return {
            "id": self.id,
            "label": self.label,
            "available": self.executable,
            "implemented": self.implemented,
            "executable": self.executable,
        }


@dataclass(frozen=True, slots=True)
class MachineType:
    id: str
    label: str

    def as_public_dict(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label}


# Public IDs are a stable product contract. Keep executable modes first so every
# consumer receives the same native ordering without a duplicated UI catalog.
# engine_mode is only a compatibility adapter to the current optimizer; None
# means the public ID is known/persistable for compatibility but is not runnable.
OPTIMIZATION_MODES = (
    OptimizationMode("auto", "تلقائي", "Auto"),
    OptimizationMode("auto_pro", "تلقائي متقدم (موصى به)", "Auto Pro"),
    OptimizationMode("deep_search", "بحث معمّق", "Deep Search"),
    OptimizationMode("optimal", "بحث أمثل", "Optimal Search"),
    OptimizationMode("maxrects", "تعبئة المستطيلات القصوى", "MaxRects Best Short Side"),
    OptimizationMode("guillotine", "القص المقصلي", "Guillotine Short Axis"),
    OptimizationMode("shelf", "التعبئة بالرفوف", "Shelf Horizontal"),
    OptimizationMode("skyline", "التعبئة بخط الأفق", "Skyline Bottom Left"),
    OptimizationMode("cp_sat_ortools", "البرمجة بالقيود — CP-SAT", None),
    OptimizationMode("mip_cbc", "البرمجة الصحيحة المختلطة — CBC", None),
    OptimizationMode("scip", "محلّل SCIP", None),
    OptimizationMode("highs", "محلّل HiGHS", None),
    OptimizationMode("gecode", "محلّل القيود Gecode", None),
    OptimizationMode("chuffed", "محلّل القيود Chuffed", None),
    OptimizationMode("genetic", "الخوارزمية الجينية", None),
    OptimizationMode("simulated_annealing", "التلدين المُحاكى", None),
)

MACHINE_TYPES = (
    MachineType("Auto", "تلقائي"),
    MachineType("CNC Router", "CNC Router"),
    MachineType("Panel Saw", "منشار ألواح"),
)

_OPTIMIZATION_BY_ID = {mode.id: mode for mode in OPTIMIZATION_MODES}
_MACHINE_BY_ID = {machine.id: machine for machine in MACHINE_TYPES}
_ENGINE_TO_PUBLIC_ID = {
    mode.engine_mode: mode.id
    for mode in OPTIMIZATION_MODES
    if mode.engine_mode is not None
}

# Existing documents can contain one of the old low-level strategy variants.
# They remain valid compatibility inputs so opening or recalculating historical
# plans never changes their packing behavior implicitly.
LEGACY_ENGINE_MODES = frozenset(
    {
        "MaxRects Best Area",
        "MaxRects Bottom Left",
        "MaxRects Contact Point",
        "MaxRects Width",
        "MaxRects Length",
        "Shelf Vertical",
        "Shelf First Fit",
        "Shelf Next Fit",
        "Guillotine Long Axis",
        "Guillotine Best Area Fit",
        "Guillotine Best Short Side Fit",
        "Guillotine Best Long Side Fit",
        "Skyline Best Fit",
    }
)


def optimization_catalog() -> list[dict[str, Any]]:
    return [mode.as_public_dict() for mode in OPTIMIZATION_MODES]


def machine_type_catalog() -> list[dict[str, str]]:
    return [machine.as_public_dict() for machine in MACHINE_TYPES]


def optimization_mode(mode_id: str) -> OptimizationMode | None:
    return _OPTIMIZATION_BY_ID.get(str(mode_id or "").strip())


def is_known_optimization_mode(mode_id: str) -> bool:
    return optimization_mode(mode_id) is not None


def engine_mode_for(mode_id: str) -> str | None:
    mode = optimization_mode(mode_id)
    return mode.engine_mode if mode else None


def public_mode_value(stored_mode: str | None) -> str:
    """Project persisted engine values to the stable public contract when safe.

    Non-representative historical strategy variants are returned unchanged. This
    prevents a read from silently changing the algorithm selected by old plans.
    """

    normalized = str(stored_mode or "").strip()
    if not normalized:
        return DEFAULT_OPTIMIZATION_MODE_ID
    if normalized in _OPTIMIZATION_BY_ID:
        return normalized
    return _ENGINE_TO_PUBLIC_ID.get(normalized, normalized)


def persisted_mode_value(mode_value: str | None) -> str:
    """Return the canonical persisted ID while preserving exact historical modes."""

    normalized = str(mode_value or "").strip()
    if not normalized:
        return DEFAULT_OPTIMIZATION_MODE_ID
    public_value = public_mode_value(normalized)
    if public_value in _OPTIMIZATION_BY_ID:
        return public_value
    if normalized in LEGACY_ENGINE_MODES:
        return normalized
    raise UnsupportedOptimizationModeError(
        f"unsupported_optimization_mode:{normalized}"
    )


def engine_mode_for_request(mode_value: str) -> str | None:
    """Resolve a public ID or a preserved current/historical engine value.

    Returning None means the ID is known by the product contract but has no
    independent implementation in the current optimizer yet, or the input is
    unknown. New execution code should prefer ``require_engine_mode`` so these
    two cases cannot be confused.
    """

    normalized = str(mode_value or "").strip()
    mode = _OPTIMIZATION_BY_ID.get(normalized)
    if mode:
        return mode.engine_mode
    if normalized in _ENGINE_TO_PUBLIC_ID or normalized in LEGACY_ENGINE_MODES:
        return normalized
    return None


def require_engine_mode(mode_value: str | None) -> str:
    """Translate a persisted public ID to the existing engine at execution time."""

    persisted = persisted_mode_value(mode_value)
    mode = _OPTIMIZATION_BY_ID.get(persisted)
    if mode is None:
        return persisted
    if not mode.executable:
        raise OptimizationModeUnavailableError(mode.id)
    return mode.engine_mode  # type: ignore[return-value]


def is_legacy_engine_mode(mode_value: str) -> bool:
    return str(mode_value or "").strip() in LEGACY_ENGINE_MODES


def is_machine_type(machine_type: str) -> bool:
    return str(machine_type or "").strip() in _MACHINE_BY_ID


__all__ = [
    "DEFAULT_OPTIMIZATION_MODE_ID",
    "LEGACY_ENGINE_MODES",
    "MACHINE_TYPES",
    "OPTIMIZATION_MODES",
    "MachineType",
    "OptimizationMode",
    "OptimizationModeUnavailableError",
    "UnsupportedOptimizationModeError",
    "engine_mode_for",
    "engine_mode_for_request",
    "is_known_optimization_mode",
    "is_legacy_engine_mode",
    "is_machine_type",
    "machine_type_catalog",
    "optimization_catalog",
    "optimization_mode",
    "persisted_mode_value",
    "public_mode_value",
    "require_engine_mode",
]
