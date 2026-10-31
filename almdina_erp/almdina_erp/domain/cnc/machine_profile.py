"""Factory machine profile used later when an NC file is generated.

The stored sample comes from previous ArtCAM files. It is not a confirmed
controller, origin, or travel-limit specification, and it is not approved
for production until a factory manager marks it so.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


_TOKEN = re.compile(r"^G[0-9]{1,3}$")
_NOTE_LIMIT = 140
_MAX_LINEAR_MM = 500.0
_MAX_SPEED = 120_000.0

SAMPLE_MACHINE_PROFILE: dict[str, Any] = {
    "cnc_machine_tool_number": "T9",
    "cnc_machine_spindle_speed_rpm": 15000,
    "cnc_machine_cutting_feed_mm_min": 10200.0,
    "cnc_machine_plunge_feed_mm_min": 1800.0,
    "cnc_machine_retract_z_mm": 20.0,
    "cnc_machine_distance_mode": "G90",
    "cnc_machine_work_offset": "G54",
    "cnc_machine_example_depth_a_mm": 7.0,
    "cnc_machine_example_depth_b_mm": 18.5,
    "cnc_machine_profile_production_approved": 0,
    "cnc_machine_profile_source": "ArtCAM sample — not approved for production",
}


class MachineProfileError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class MachineProfileValues:
    tool_number: str
    spindle_speed_rpm: int
    cutting_feed_mm_min: float
    plunge_feed_mm_min: float
    retract_z_mm: float
    distance_mode: str
    work_offset: str
    example_depth_a_mm: float
    example_depth_b_mm: float
    production_approved: bool
    source_note: str

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "tool_number": self.tool_number,
            "spindle_speed_rpm": self.spindle_speed_rpm,
            "cutting_feed_mm_min": self.cutting_feed_mm_min,
            "plunge_feed_mm_min": self.plunge_feed_mm_min,
            "retract_z_mm": self.retract_z_mm,
            "distance_mode": self.distance_mode,
            "work_offset": self.work_offset,
            "example_depth_a_mm": self.example_depth_a_mm,
            "example_depth_b_mm": self.example_depth_b_mm,
            "production_approved": self.production_approved,
            "source_note": self.source_note,
        }


def _token(value: Any) -> str:
    token = str(value or "").strip().upper()
    if _TOKEN.fullmatch(token) is None:
        raise MachineProfileError("machine_profile_token_invalid")
    return token


def _number(value: Any, *, lower: float, upper: float, inclusive_lower: bool) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MachineProfileError("machine_profile_value_invalid") from exc
    if not math.isfinite(number) or number > upper:
        raise MachineProfileError("machine_profile_value_invalid")
    if inclusive_lower:
        if number < lower:
            raise MachineProfileError("machine_profile_value_invalid")
    elif number <= lower:
        raise MachineProfileError("machine_profile_value_invalid")
    return number


def normalize_machine_profile(raw: Mapping[str, Any]) -> MachineProfileValues:
    from almdina_erp.almdina_erp.domain.cnc.tool_preset import normalize_tool_preset

    tool_number = normalize_tool_preset(
        {
            "preset_name": "machine-profile",
            "tool_name": "machine-profile",
            "tool_number": raw.get("cnc_machine_tool_number"),
            "tool_diameter_mm": 1,
            "final_depth_mm": 1,
            "spindle_speed_rpm": 1,
            "feed_rate_mm_min": 1,
            "plunge_rate_mm_min": 1,
            "enabled": True,
        }
    ).tool_number
    spindle = _number(
        raw.get("cnc_machine_spindle_speed_rpm"),
        lower=0,
        upper=_MAX_SPEED,
        inclusive_lower=False,
    )
    if not spindle.is_integer():
        raise MachineProfileError("machine_profile_value_invalid")
    note = str(raw.get("cnc_machine_profile_source") or "").strip()
    if not note or len(note) > _NOTE_LIMIT:
        raise MachineProfileError("machine_profile_value_invalid")
    approved = raw.get("cnc_machine_profile_production_approved")
    if approved not in (0, 1, True, False, "0", "1"):
        raise MachineProfileError("machine_profile_value_invalid")
    return MachineProfileValues(
        tool_number=tool_number,
        spindle_speed_rpm=int(spindle),
        cutting_feed_mm_min=round(
            _number(
                raw.get("cnc_machine_cutting_feed_mm_min"),
                lower=0,
                upper=_MAX_SPEED,
                inclusive_lower=False,
            ),
            1,
        ),
        plunge_feed_mm_min=round(
            _number(
                raw.get("cnc_machine_plunge_feed_mm_min"),
                lower=0,
                upper=_MAX_SPEED,
                inclusive_lower=False,
            ),
            1,
        ),
        retract_z_mm=round(
            _number(
                raw.get("cnc_machine_retract_z_mm"),
                lower=0,
                upper=_MAX_LINEAR_MM,
                inclusive_lower=True,
            ),
            3,
        ),
        distance_mode=_token(raw.get("cnc_machine_distance_mode")),
        work_offset=_token(raw.get("cnc_machine_work_offset")),
        example_depth_a_mm=round(
            _number(
                raw.get("cnc_machine_example_depth_a_mm"),
                lower=0,
                upper=_MAX_LINEAR_MM,
                inclusive_lower=False,
            ),
            3,
        ),
        example_depth_b_mm=round(
            _number(
                raw.get("cnc_machine_example_depth_b_mm"),
                lower=0,
                upper=_MAX_LINEAR_MM,
                inclusive_lower=False,
            ),
            3,
        ),
        production_approved=approved in (1, True, "1"),
        source_note=note,
    )


def machine_profile_seed_updates(current: Mapping[str, Any] | None) -> dict[str, Any]:
    """Fill only missing sample values. A later edit is left untouched."""

    stored = dict(current or {})
    updates: dict[str, Any] = {}
    for field, default in SAMPLE_MACHINE_PROFILE.items():
        value = stored.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            updates[field] = default
    return updates


__all__ = [
    "SAMPLE_MACHINE_PROFILE",
    "MachineProfileError",
    "MachineProfileValues",
    "machine_profile_seed_updates",
    "normalize_machine_profile",
]
