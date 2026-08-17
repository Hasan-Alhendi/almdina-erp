from __future__ import annotations

from dataclasses import dataclass


PRELIMINARY = "Preliminary"
APPROVED = "Approved"
SUPERSEDED = "Superseded"


class CostingLifecycleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CostingVersion:
    kind: str
    based_on_plan: str
    status: str


def normalize_kind(value: str | None) -> str:
    kind = str(value or PRELIMINARY).strip() or PRELIMINARY
    if kind not in {PRELIMINARY, APPROVED}:
        raise CostingLifecycleError(f"unsupported_costing_kind:{kind}")
    return kind


def costing_status_for_plan(*, plan_status: str) -> str:
    return APPROVED if str(plan_status or "") == APPROVED else PRELIMINARY


def replacement_status(current_status: str | None) -> str:
    normalized = str(current_status or "").strip()
    if normalized not in {PRELIMINARY, APPROVED}:
        raise CostingLifecycleError(f"costing_not_replaceable:{normalized}")
    return SUPERSEDED


__all__ = [
    "APPROVED",
    "PRELIMINARY",
    "SUPERSEDED",
    "CostingLifecycleError",
    "CostingVersion",
    "costing_status_for_plan",
    "normalize_kind",
    "replacement_status",
]
