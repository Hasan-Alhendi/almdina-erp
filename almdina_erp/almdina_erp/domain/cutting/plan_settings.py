from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.catalog import (
    DEFAULT_OPTIMIZATION_MODE_ID,
    UnsupportedOptimizationModeError,
    is_machine_type,
    persisted_mode_value,
)


DEFAULT_MACHINE_TYPE = "Auto"
DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC = 10.0
DEFAULT_KERF_MM = 3.0
DEFAULT_PREFERRED_TRIM_MM = 5.0


class PlanSettingsValidationError(ValueError):
    """Raised when optimizer settings violate the canonical product contract."""


@dataclass(frozen=True, slots=True, init=False)
class PlanSettings:
    """Canonical Cutting Plan settings value.

    ``preferred_trim_mm`` is the product/domain name. Frappe still persists the
    same value as ``trim_margin_mm``; the constructor/property alias keeps that
    storage vocabulary compatible while callers migrate to the canonical name.
    Validation is owned exclusively by ``normalize_plan_settings``.
    """

    optimization_mode: str
    machine_type: str
    optimization_time_limit_sec: float
    kerf_mm: float
    preferred_trim_mm: float

    def __init__(
        self,
        optimization_mode: str,
        machine_type: str,
        optimization_time_limit_sec: float,
        kerf_mm: float,
        preferred_trim_mm: float | None = None,
        *,
        trim_margin_mm: float | None = None,
    ) -> None:
        resolved_trim = preferred_trim_mm
        if resolved_trim is None:
            resolved_trim = trim_margin_mm
        object.__setattr__(self, "optimization_mode", optimization_mode)
        object.__setattr__(self, "machine_type", machine_type)
        object.__setattr__(self, "optimization_time_limit_sec", optimization_time_limit_sec)
        object.__setattr__(self, "kerf_mm", kerf_mm)
        object.__setattr__(self, "preferred_trim_mm", resolved_trim)  # type: ignore[arg-type]

    @property
    def trim_margin_mm(self) -> float:
        """Compatibility alias for the current Frappe storage field name."""

        return self.preferred_trim_mm


def _finite_number(value: Any, fieldname: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as error:
        raise PlanSettingsValidationError(
            f"invalid_plan_setting:{fieldname}"
        ) from error
    if not math.isfinite(normalized):
        raise PlanSettingsValidationError(f"invalid_plan_setting:{fieldname}")
    return normalized


def normalize_plan_settings(
    *,
    optimization_mode: Any,
    machine_type: Any,
    optimization_time_limit_sec: Any,
    kerf_mm: Any,
    preferred_trim_mm: Any,
) -> PlanSettings:
    """Validate one complete settings value without silently replacing zero.

    Kerf and preferred trim explicitly allow zero. Optimization time must be
    strictly positive. Callers decide when defaults apply; once values enter
    this contract they are preserved exactly apart from numeric type coercion
    and canonical optimization-mode normalization.
    """

    requested_mode = str(optimization_mode or "").strip()
    if not requested_mode:
        raise PlanSettingsValidationError("missing_plan_setting:optimization_mode")
    try:
        canonical_mode = persisted_mode_value(requested_mode)
    except UnsupportedOptimizationModeError as error:
        raise PlanSettingsValidationError(str(error)) from error

    canonical_machine = str(machine_type or "").strip()
    if not canonical_machine or not is_machine_type(canonical_machine):
        raise PlanSettingsValidationError(
            f"unsupported_machine_type:{canonical_machine}"
        )

    time_limit = _finite_number(
        optimization_time_limit_sec,
        "optimization_time_limit_sec",
    )
    if time_limit <= 0:
        raise PlanSettingsValidationError(
            "plan_setting_must_be_positive:optimization_time_limit_sec"
        )

    kerf = _finite_number(kerf_mm, "kerf_mm")
    if kerf < 0:
        raise PlanSettingsValidationError("plan_setting_cannot_be_negative:kerf_mm")

    preferred_trim = _finite_number(preferred_trim_mm, "preferred_trim_mm")
    if preferred_trim < 0:
        raise PlanSettingsValidationError(
            "plan_setting_cannot_be_negative:preferred_trim_mm"
        )

    return PlanSettings(
        optimization_mode=canonical_mode,
        machine_type=canonical_machine,
        optimization_time_limit_sec=time_limit,
        kerf_mm=kerf,
        preferred_trim_mm=preferred_trim,
    )


def canonical_default_plan_settings() -> PlanSettings:
    """Product defaults used only when a storage value is genuinely missing."""

    return normalize_plan_settings(
        optimization_mode=DEFAULT_OPTIMIZATION_MODE_ID,
        machine_type=DEFAULT_MACHINE_TYPE,
        optimization_time_limit_sec=DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
        kerf_mm=DEFAULT_KERF_MM,
        preferred_trim_mm=DEFAULT_PREFERRED_TRIM_MM,
    )


__all__ = [
    "DEFAULT_KERF_MM",
    "DEFAULT_MACHINE_TYPE",
    "DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC",
    "DEFAULT_PREFERRED_TRIM_MM",
    "PlanSettings",
    "PlanSettingsValidationError",
    "canonical_default_plan_settings",
    "normalize_plan_settings",
]
