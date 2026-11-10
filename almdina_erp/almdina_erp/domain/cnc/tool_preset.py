"""Reusable CNC tool preset rules.

One physical tool stays mounted for a board in this version. Several presets
may describe that tool, but they must share its number and diameter inside
one operational file. This module does not model an automatic tool changer.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from almdina_erp.almdina_erp.domain.security.authorization import Capability


_TOOL_NUMBER = re.compile(r"^T[1-9][0-9]{0,2}$")
_NAME_LIMIT = 140

MAX_DIAMETER_MM = 200.0
MAX_DEPTH_MM = 200.0
MAX_SPINDLE_RPM = 120_000
MAX_FEED_MM_MIN = 100_000.0
MAX_PLUNGE_MM_MIN = 100_000.0


class ToolPresetError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ToolPresetValues:
    preset_name: str
    tool_name: str
    tool_number: str
    tool_diameter_mm: float
    final_depth_mm: float | None
    spindle_speed_rpm: int
    feed_rate_mm_min: float
    plunge_rate_mm_min: float
    pass_depth_mm: float | None
    enabled: bool


def _text(value: Any, *, required_code: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ToolPresetError(required_code)
    if len(text) > _NAME_LIMIT:
        raise ToolPresetError(required_code)
    return text


def _positive(value: Any, code: str, *, upper: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ToolPresetError(code) from exc
    if not math.isfinite(number) or number <= 0 or number > upper:
        raise ToolPresetError(code)
    return number


def mm_per_min_from_sec(value: Any) -> float:
    """Convert a stored mm/sec rate into the mm/min value motion code already uses."""

    return round(float(value) * 60.0, 1)


def mm_per_sec_from_min(value: Any) -> float:
    """Convert a legacy mm/min rate into the stored mm/sec value."""

    return round(float(value) / 60.0, 3)


def _rate_pair(raw: Mapping[str, Any], *, sec_key: str, min_key: str, code: str, upper_per_min: float) -> tuple[float, float]:
    """Return ``(mm/sec, mm/min)``. Stored tools supply seconds; older payloads supply minutes."""

    seconds = raw.get(sec_key)
    minutes = raw.get(min_key)
    if seconds not in (None, ""):
        per_sec = _positive(seconds, code, upper=upper_per_min / 60.0)
        return round(per_sec, 3), mm_per_min_from_sec(per_sec)
    if minutes not in (None, ""):
        per_min = _positive(minutes, code, upper=upper_per_min)
        return mm_per_sec_from_min(per_min), round(per_min, 1)
    raise ToolPresetError(code)


def catalog_tool_number(value: Any) -> tuple[str, int]:
    """Accept a positive tool index and the NC token derived from it.

    The stored and entered value is the whole number, for example ``9``.
    Callers that speak NC receive the same index as ``T9``. A ``T`` prefix on
    input is accepted and is not required.
    """

    if isinstance(value, bool) or value in (None, ""):
        raise ToolPresetError("tool_number_invalid")
    if isinstance(value, int):
        token = f"T{value}"
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ToolPresetError("tool_number_invalid")
        token = f"T{int(value)}"
    else:
        raw = str(value).strip().upper()
        if not raw:
            raise ToolPresetError("tool_number_invalid")
        if raw.startswith("T"):
            token = raw
        elif raw.isdigit():
            token = f"T{int(raw)}"
        else:
            raise ToolPresetError("tool_number_invalid")
    if _TOOL_NUMBER.fullmatch(token) is None:
        raise ToolPresetError("tool_number_invalid")
    return token, int(token[1:])


def _optional_final_depth(value: Any) -> float | None:
    """A tool definition may omit Final Depth. Zero is the empty stored value."""

    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ToolPresetError("final_depth_invalid") from exc
    if not math.isfinite(number):
        raise ToolPresetError("final_depth_invalid")
    if number == 0:
        return None
    return round(_positive(number, "final_depth_invalid", upper=MAX_DEPTH_MM), 3)


_MISSING = object()


def normalize_tool_preset(
    raw: Mapping[str, Any],
    *,
    machining_depth_mm: Any = _MISSING,
) -> ToolPresetValues:
    """Normalize a tool definition. Final depth is not a tool property.

    ``machining_depth_mm`` is the operational depth supplied by a profile or an
    existing board program. A stored tool payload cannot provide it.
    """

    identity = raw.get("preset_name") or raw.get("tool_name")
    display = raw.get("tool_name") or identity
    preset_name = _text(identity, required_code="tool_name_required")
    tool_name = _text(display, required_code="tool_name_required")
    tool_number, _tool_index = catalog_tool_number(raw.get("tool_number"))

    final_depth = None if machining_depth_mm is _MISSING else _optional_final_depth(machining_depth_mm)
    pass_raw = raw.get("stepdown_mm")
    if pass_raw in (None, ""):
        pass_raw = raw.get("pass_depth_mm")
    pass_depth: float | None
    if pass_raw in (None, ""):
        pass_depth = None
    else:
        pass_depth = _positive(pass_raw, "pass_depth_invalid", upper=MAX_DEPTH_MM)
        if final_depth is not None and pass_depth > final_depth + 1e-9:
            raise ToolPresetError("pass_depth_exceeds_final_depth")

    raw_spindle = raw.get("spindle_speed_rpm")
    if isinstance(raw_spindle, bool):
        raise ToolPresetError("spindle_speed_invalid")
    try:
        spindle_number = float(raw_spindle)
    except (TypeError, ValueError) as exc:
        raise ToolPresetError("spindle_speed_invalid") from exc
    if (
        not math.isfinite(spindle_number)
        or not spindle_number.is_integer()
        or spindle_number <= 0
        or spindle_number > MAX_SPINDLE_RPM
    ):
        raise ToolPresetError("spindle_speed_invalid")
    spindle = int(spindle_number)
    _feed_sec, feed_min = _rate_pair(
        raw,
        sec_key="feed_rate_mm_sec",
        min_key="feed_rate_mm_min",
        code="feed_rate_invalid",
        upper_per_min=MAX_FEED_MM_MIN,
    )
    _plunge_sec, plunge_min = _rate_pair(
        raw,
        sec_key="plunge_rate_mm_sec",
        min_key="plunge_rate_mm_min",
        code="plunge_rate_invalid",
        upper_per_min=MAX_PLUNGE_MM_MIN,
    )

    return ToolPresetValues(
        preset_name=preset_name,
        tool_name=tool_name,
        tool_number=tool_number,
        tool_diameter_mm=round(
            _positive(raw.get("tool_diameter_mm"), "tool_diameter_invalid", upper=MAX_DIAMETER_MM),
            3,
        ),
        final_depth_mm=final_depth,
        spindle_speed_rpm=spindle,
        feed_rate_mm_min=feed_min,
        plunge_rate_mm_min=plunge_min,
        pass_depth_mm=None if pass_depth is None else round(pass_depth, 3),
        enabled=bool(raw.get("enabled", True)),
    )


def resolve_selected_presets(
    names: Sequence[str],
    known_presets: Mapping[str, Mapping[str, Any]],
) -> list[ToolPresetValues]:
    selected: list[ToolPresetValues] = []
    for name in names:
        preset_name = str(name or "").strip()
        if not preset_name:
            continue
        raw = known_presets.get(preset_name)
        if raw is None:
            raise ToolPresetError("preset_not_found")
        preset = normalize_tool_preset({**dict(raw), "preset_name": raw.get("preset_name") or preset_name})
        if not preset.enabled:
            raise ToolPresetError("preset_disabled")
        selected.append(preset)
    assert_single_tool_for_file(selected)
    return selected


def tool_preset_write_allowed(capabilities: Iterable[str] | None) -> bool:
    """Return whether these grants may create or change a tool preset."""

    return Capability.EDIT_FACTORY_CNC_DEFAULTS in set(capabilities or ())


_DELETE_REASONS = {
    "operational_file": "This tool is selected on a CNC operational file.",
    "factory_default": "This tool is selected as a factory default.",
    "profile": "This tool is used by a machining profile.",
    "association": "This tool is used by a vector association.",
    "active_snapshot": "This tool is used by an active toolpath snapshot.",
}


def tool_delete_blockers(
    *,
    operation_uses: int = 0,
    path_uses: int = 0,
    factory_uses: int = 0,
    profile_uses: int = 0,
    association_uses: int = 0,
    active_snapshot_uses: int = 0,
) -> tuple[str, ...]:
    """Name the live references that forbid deletion.

    Historical toolpath snapshots keep their own copy and do not execute, so
    they are not a deletion blocker. This function does not remove references.
    """

    blockers: list[str] = []
    if int(operation_uses) or int(path_uses):
        blockers.append("operational_file")
    if int(factory_uses):
        blockers.append("factory_default")
    if int(profile_uses):
        blockers.append("profile")
    if int(association_uses):
        blockers.append("association")
    if int(active_snapshot_uses):
        blockers.append("active_snapshot")
    return tuple(blockers)


def tool_delete_reason(code: str) -> str:
    return _DELETE_REASONS.get(str(code or ""), "This tool cannot be deleted.")


def unused_tool_preset_can_be_deleted(
    *,
    operation_uses: int,
    path_uses: int,
    factory_uses: int,
    machining_uses: int = 0,
) -> bool:
    """A preset that still labels a sheet, a path, a factory default, or a copy stays."""

    return (
        int(operation_uses) == 0
        and int(path_uses) == 0
        and int(factory_uses) == 0
        and int(machining_uses) == 0
    )


def assert_single_tool_for_file(presets: Sequence[ToolPresetValues]) -> None:
    """Reject a board file that would require another physical cutter."""

    selected = list(presets)
    if len(selected) < 2:
        return
    numbers = {preset.tool_number for preset in selected}
    if len(numbers) != 1:
        raise ToolPresetError("tool_identity_conflict")
    diameters = {preset.tool_diameter_mm for preset in selected}
    if len(diameters) != 1:
        raise ToolPresetError("tool_diameter_conflict")


__all__ = [
    "MAX_DEPTH_MM",
    "MAX_DIAMETER_MM",
    "MAX_FEED_MM_MIN",
    "MAX_PLUNGE_MM_MIN",
    "MAX_SPINDLE_RPM",
    "ToolPresetError",
    "ToolPresetValues",
    "assert_single_tool_for_file",
    "normalize_tool_preset",
    "tool_delete_blockers",
    "tool_delete_reason",
    "tool_preset_write_allowed",
    "unused_tool_preset_can_be_deleted",
]
