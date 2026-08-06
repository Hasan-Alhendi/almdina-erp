from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


def normalize_eligible_roles(values: Iterable[str] | str | None) -> tuple[str, ...]:
    """Return unique role names in stable order without inventing defaults."""

    source = (values,) if isinstance(values, str) else tuple(values or ())
    normalized: list[str] = []
    seen: set[str] = set()
    for value in source:
        role = " ".join(str(value or "").split())
        if not role or role in seen:
            continue
        seen.add(role)
        normalized.append(role)
    return tuple(normalized)


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class RoutingStage:
    """One immutable executable stage definition inside a production route.

    A stage may be assigned to a worker who owns any one of its eligible roles.
    Role names and stage codes are configuration data; this domain contains no
    role catalog, route catalog, or stage-to-role defaults.
    """

    sequence: int
    stage_type: str
    department_label: str
    eligible_roles: tuple[str, ...] | str

    def __post_init__(self) -> None:
        try:
            sequence = int(self.sequence)
        except (TypeError, ValueError) as error:
            raise ValueError("Production route stage sequence must be an integer.") from error
        object.__setattr__(self, "sequence", sequence)
        object.__setattr__(self, "stage_type", _clean_text(self.stage_type))
        object.__setattr__(
            self,
            "department_label",
            _clean_text(self.department_label),
        )
        object.__setattr__(
            self,
            "eligible_roles",
            normalize_eligible_roles(self.eligible_roles),
        )

    @property
    def operational_role(self) -> str:
        """Compatibility view for old callers while plural roles are rolled out."""

        return self.eligible_roles[0] if self.eligible_roles else ""

    def accepts_any_role(self, roles: Iterable[str] | None) -> bool:
        return bool(set(normalize_eligible_roles(roles)).intersection(self.eligible_roles))


@dataclass(frozen=True, slots=True)
class ProductionRoute:
    """Validated route used by application services without Frappe coupling."""

    name: str
    label: str
    stages: tuple[RoutingStage, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean_text(self.name))
        object.__setattr__(self, "label", _clean_text(self.label) or self.name)
        object.__setattr__(self, "stages", tuple(self.stages or ()))
        if not self.name:
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
        if any(not stage.stage_type for stage in self.stages):
            raise ValueError("Production route stage type is required.")
        if any(not stage.department_label for stage in self.stages):
            raise ValueError("Every production route stage requires a department label.")
        if any(not stage.eligible_roles for stage in self.stages):
            raise ValueError("Every production route stage requires an eligible role.")
        if tuple(sequences) != tuple(sorted(sequences)):
            raise ValueError("Production route stages must be ordered by sequence.")

    @property
    def first_stage(self) -> RoutingStage:
        return self.stages[0]

    def stage(self, stage_type: str) -> RoutingStage:
        resolved = _clean_text(stage_type)
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
        resolved = _clean_text(stage_type)
        return any(stage.stage_type == resolved for stage in self.stages)


__all__ = [
    "ProductionRoute",
    "RoutingStage",
    "normalize_eligible_roles",
]
