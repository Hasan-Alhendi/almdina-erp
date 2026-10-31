"""Reusable CNC tool preset rules.

One physical tool stays mounted for a board in this version. Several presets
may describe that tool, but they must share its number and diameter inside
one operational file. This module does not model an automatic tool changer.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


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
    final_depth_mm: float
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


def normalize_tool_preset(raw: Mapping[str, Any]) -> ToolPresetValues:
    tool_number = _text(raw.get("tool_number"), required_code="tool_number_invalid").upper()
    if _TOOL_NUMBER.fullmatch(tool_number) is None:
        raise ToolPresetError("tool_number_invalid")

    final_depth = _positive(raw.get("final_depth_mm"), "final_depth_invalid", upper=MAX_DEPTH_MM)
    pass_raw = raw.get("pass_depth_mm")
    pass_depth: float | None
    if pass_raw in (None, ""):
        pass_depth = None
    else:
        pass_depth = _positive(pass_raw, "pass_depth_invalid", upper=MAX_DEPTH_MM)
        if pass_depth > final_depth + 1e-9:
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

    return ToolPresetValues(
        preset_name=_text(raw.get("preset_name"), required_code="preset_name_required"),
        tool_name=_text(raw.get("tool_name"), required_code="tool_name_required"),
        tool_number=tool_number,
        tool_diameter_mm=round(
            _positive(raw.get("tool_diameter_mm"), "tool_diameter_invalid", upper=MAX_DIAMETER_MM),
            3,
        ),
        final_depth_mm=round(final_depth, 3),
        spindle_speed_rpm=spindle,
        feed_rate_mm_min=round(
            _positive(raw.get("feed_rate_mm_min"), "feed_rate_invalid", upper=MAX_FEED_MM_MIN),
            1,
        ),
        plunge_rate_mm_min=round(
            _positive(raw.get("plunge_rate_mm_min"), "plunge_rate_invalid", upper=MAX_PLUNGE_MM_MIN),
            1,
        ),
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
]
