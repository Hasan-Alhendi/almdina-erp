from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RoutingStage:
    """One immutable stage definition inside a production route."""

    sequence: int
    stage_type: str
    department_label: str
    operational_role: str


@dataclass(frozen=True, slots=True)
class ProductionRoute:
    """Validated route used by application services without Frappe coupling."""

    name: str
    label: str
    stages: tuple[RoutingStage, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Production route name is required.")
        if not self.stages:
            raise ValueError("Production route requires at least one stage.")

        sequences = [stage.sequence for stage in self.stages]
        stage_types = [stage.stage_type for stage in self.stages]
        if any(sequence <= 0 for sequence in sequences):
            raise ValueError("Production route stage sequences must be positive.")
        if len(sequences) != len(set(sequences)):
            raise ValueError("Production route stage sequences must be unique.")
        if len(stage_types) != len(set(stage_types)):
            raise ValueError("Production route stage types must be unique.")
        if any(not stage.stage_type.strip() for stage in self.stages):
            raise ValueError("Production route stage type is required.")
        if any(not stage.operational_role.strip() for stage in self.stages):
            raise ValueError("Every production route stage requires an operational role.")
        if tuple(sequences) != tuple(sorted(sequences)):
            raise ValueError("Production route stages must be ordered by sequence.")

    @property
    def first_stage(self) -> RoutingStage:
        return self.stages[0]

    def stage(self, stage_type: str) -> RoutingStage:
        resolved = str(stage_type or "").strip()
        for stage in self.stages:
            if stage.stage_type == resolved:
                return stage
        raise ValueError(
            f"Stage {resolved or '<empty>'} is not part of route {self.name}."
        )

    def next_stage(self, stage_type: str) -> RoutingStage | None:
        current = self.stage(stage_type)
        index = self.stages.index(current)
        return self.stages[index + 1] if index + 1 < len(self.stages) else None

    def contains(self, stage_type: str) -> bool:
        resolved = str(stage_type or "").strip()
        return any(stage.stage_type == resolved for stage in self.stages)


__all__ = ["ProductionRoute", "RoutingStage"]
