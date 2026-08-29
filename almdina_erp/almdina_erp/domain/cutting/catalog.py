from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_OPTIMIZATION_MODE_ID = "auto_pro"


@dataclass(frozen=True, slots=True)
class OptimizationMode:
    """Public optimization-mode contract kept separate from engine internals."""

    id: str
    label: str
    engine_mode: str | None

    @property
    def available(self) -> bool:
        return self.engine_mode is not None

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "available": self.available,
        }


@dataclass(frozen=True, slots=True)
class MachineType:
    id: str
    label: str

    def as_public_dict(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label}


# Keep this catalog intentionally independent of optimizer.py. Public IDs are a
# stable product contract; engine_mode is a compatibility adapter to the current
# engine and may evolve without changing the public IDs.
OPTIMIZATION_MODES = (
    OptimizationMode("auto", "تلقائي", "Auto"),
    OptimizationMode("auto_pro", "تلقائي متقدم (موصى به)", "Auto Pro"),
    OptimizationMode("deep_search", "بحث معمق", "Deep Search"),
    OptimizationMode("optimal", "بحث أمثل", "Optimal Search"),
    OptimizationMode("cp_sat_ortools", "OR-Tools CP-SAT", None),
    OptimizationMode("mip_cbc", "MIP / CBC", None),
    OptimizationMode("scip", "SCIP", None),
    OptimizationMode("highs", "HiGHS", None),
    OptimizationMode("gecode", "Gecode", None),
    OptimizationMode("chuffed", "Chuffed", None),
    OptimizationMode("maxrects", "MaxRects", "MaxRects Best Short Side"),
    OptimizationMode("guillotine", "Guillotine", "Guillotine Short Axis"),
    OptimizationMode("shelf", "Shelf", "Shelf Horizontal"),
    OptimizationMode("skyline", "Skyline", "Skyline Bottom Left"),
    OptimizationMode("genetic", "Genetic Algorithm", None),
    OptimizationMode("simulated_annealing", "Simulated Annealing", None),
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


def engine_mode_for_request(mode_value: str) -> str | None:
    """Resolve a public ID or a preserved historical engine value.

    Returning None means the ID is known by the product contract but has no
    independent implementation in the current optimizer yet.
    """

    normalized = str(mode_value or "").strip()
    mode = _OPTIMIZATION_BY_ID.get(normalized)
    if mode:
        return mode.engine_mode
    if normalized in LEGACY_ENGINE_MODES:
        return normalized
    return None


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
    "engine_mode_for",
    "engine_mode_for_request",
    "is_known_optimization_mode",
    "is_legacy_engine_mode",
    "is_machine_type",
    "machine_type_catalog",
    "optimization_catalog",
    "optimization_mode",
    "public_mode_value",
]
