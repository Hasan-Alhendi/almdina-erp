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
            raise ValueError("اسم مسار الإنتاج مطلوب.")
        if not self.stages:
            raise ValueError("يجب أن يحتوي مسار الإنتاج على مرحلة واحدة على الأقل.")

        sequences = [stage.sequence for stage in self.stages]
        stage_types = [stage.stage_type for stage in self.stages]
        if any(sequence <= 0 for sequence in sequences):
            raise ValueError("ترتيب مراحل مسار الإنتاج يجب أن يكون رقمًا موجبًا.")
        if len(sequences) != len(set(sequences)):
            raise ValueError("ترتيب مراحل مسار الإنتاج يجب ألا يحتوي على تكرار.")
        if len(stage_types) != len(set(stage_types)):
            raise ValueError("لا يمكن تكرار رمز المرحلة داخل مسار الإنتاج.")
        if any(not stage.stage_type.strip() for stage in self.stages):
            raise ValueError("رمز مرحلة الإنتاج مطلوب.")
        if any(not stage.department_label.strip() for stage in self.stages):
            raise ValueError("الاسم الظاهر لكل مرحلة إنتاج مطلوب.")
        if any(not stage.operational_role.strip() for stage in self.stages):
            raise ValueError("يجب تحديد الدور التشغيلي لكل مرحلة إنتاج.")
        if tuple(sequences) != tuple(sorted(sequences)):
            raise ValueError("يجب أن تكون مراحل مسار الإنتاج مرتبة حسب التسلسل.")

    @property
    def first_stage(self) -> RoutingStage:
        return self.stages[0]

    def stage(self, stage_type: str) -> RoutingStage:
        resolved = str(stage_type or "").strip()
        for stage in self.stages:
            if stage.stage_type == resolved:
                return stage
        raise ValueError(
            f"المرحلة {resolved or '<فارغ>'} ليست ضمن المسار {self.name}."
        )

    def next_stage(self, stage_type: str) -> RoutingStage | None:
        current = self.stage(stage_type)
        index = self.stages.index(current)
        return self.stages[index + 1] if index + 1 < len(self.stages) else None

    def contains(self, stage_type: str) -> bool:
        resolved = str(stage_type or "").strip()
        return any(stage.stage_type == resolved for stage in self.stages)


__all__ = ["ProductionRoute", "RoutingStage"]
