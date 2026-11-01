"""Translate a ready intermediate CNC program into simulation NC text.

This module never recalculates cutter centers. It consumes motions already
prepared by the board program. The default dialect is simulation-only and is
not a workshop controller approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


SIMULATION_DIALECT = "almadina_simulation_v1"
POST_PROCESSOR_VERSION = "almadina-nc-sim-1"
SAFE_Z_DEFAULT_MM = 20.0


class PostProcessorError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class NcDocument:
    dialect: str
    post_processor_version: str
    production: bool
    text: str
    line_count: int
    path_count: int
    cut_count: int
    pass_count: int
    tool_number: str
    spindle_speed_rpm: int
    warnings: tuple[str, ...]


def _number(value: Any, places: int = 3) -> str:
    number = float(value)
    if places <= 0:
        return str(int(round(number)))
    text = f"{number:.{places}f}".rstrip("0").rstrip(".")
    return text or "0"


def _safe_z(machine: Mapping[str, Any] | None) -> float:
    if not isinstance(machine, Mapping):
        return SAFE_Z_DEFAULT_MM
    raw = machine.get("retract_z_mm", machine.get("cnc_machine_retract_z_mm", SAFE_Z_DEFAULT_MM))
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise PostProcessorError("machine_profile_value_invalid") from exc
    if value < 0:
        raise PostProcessorError("machine_profile_value_invalid")
    return value


def _work_offset(machine: Mapping[str, Any] | None) -> str:
    if not isinstance(machine, Mapping):
        return "G54"
    token = str(machine.get("work_offset") or machine.get("cnc_machine_work_offset") or "G54").strip().upper()
    return token or "G54"


def _distance_mode(machine: Mapping[str, Any] | None) -> str:
    if not isinstance(machine, Mapping):
        return "G90"
    token = str(machine.get("distance_mode") or machine.get("cnc_machine_distance_mode") or "G90").strip().upper()
    return token or "G90"


def emit_nc(
    program: Mapping[str, Any],
    *,
    machine_profile: Mapping[str, Any] | None = None,
    sheet_label: str = "",
) -> NcDocument:
    """Emit one NC document from a geometry-ready intermediate program."""

    if not isinstance(program, Mapping):
        raise PostProcessorError("program_invalid")
    if not program.get("geometry_ready", program.get("ready")):
        raise PostProcessorError("geometry_not_ready")
    if str(program.get("coordinate_space") or "") != "sheet_bottom_left_y_up_mm":
        raise PostProcessorError("coordinate_space_unsupported")
    production_approved = bool(
        isinstance(machine_profile, Mapping)
        and machine_profile.get("production_approved")
    )
    if production_approved:
        raise PostProcessorError("production_controller_not_confirmed")
    safe_z = _safe_z(machine_profile)
    work_offset = _work_offset(machine_profile)
    distance_mode = _distance_mode(machine_profile)
    if distance_mode != "G90":
        raise PostProcessorError("distance_mode_unsupported")
    operations = program.get("operations") or []
    if not isinstance(operations, Sequence) or not operations:
        raise PostProcessorError("geometry_not_ready")

    lines: list[str] = []
    warnings: list[str] = []
    path_count = 0
    cut_count = 0
    pass_count = 0
    tool_number = ""
    spindle = 0
    feed = 0.0
    plunge = 0.0
    active_feed: float | None = None
    active_spindle: int | None = None
    current_z: float | None = None

    lines.append(f"(Almadina CNC simulation {POST_PROCESSOR_VERSION})")
    lines.append(f"(Dialect {SIMULATION_DIALECT} — not approved for a workshop controller)")
    if sheet_label:
        lines.append(f"(Sheet {sheet_label})")
    lines.append("G21")
    lines.append(distance_mode)
    lines.append("G94")
    lines.append("G17")
    lines.append("G40")
    lines.append("G49")
    lines.append("G80")
    lines.append(work_offset)
    lines.append(f"G0 Z{_number(safe_z)}")
    current_z = safe_z

    for operation in operations:
        for path in operation.get("toolpaths") or []:
            if not path.get("ready"):
                raise PostProcessorError("geometry_not_ready")
            preset = path.get("preset") or {}
            points = path.get("points") or []
            motions = path.get("motions") or []
            if len(points) < 2 or not motions:
                raise PostProcessorError("geometry_not_ready")
            path_count += 1
            path_tool = str(preset.get("tool_number") or "").strip().upper()
            path_spindle = int(preset.get("spindle_speed_rpm") or 0)
            path_feed = float(preset.get("feed_rate_mm_min") or 0)
            path_plunge = float(preset.get("plunge_rate_mm_min") or 0)
            if not path_tool or path_spindle <= 0 or path_feed <= 0 or path_plunge <= 0:
                raise PostProcessorError("preset_incomplete")
            if tool_number and tool_number != path_tool:
                raise PostProcessorError("tool_identity_conflict")
            tool_number = path_tool
            spindle = path_spindle
            feed = path_feed
            plunge = path_plunge
            lines.append(f"(Path {path.get('path_key')})")
            if active_spindle != path_spindle:
                lines.append(f"S{_number(path_spindle, 0)} M3")
                active_spindle = path_spindle
            for motion in motions:
                kind = str(motion.get("kind") or "")
                x = motion.get("x_mm")
                y = motion.get("y_mm")
                depth = motion.get("depth_mm")
                if kind == "travel":
                    if current_z is None or abs(current_z - safe_z) > 0.0005:
                        lines.append(f"G0 Z{_number(safe_z)}")
                        current_z = safe_z
                    lines.append(f"G0 X{_number(x)} Y{_number(y)}")
                elif kind == "plunge":
                    if active_feed != path_plunge:
                        lines.append(f"G1 Z-{_number(depth)} F{_number(path_plunge, 1)}")
                        active_feed = path_plunge
                    else:
                        lines.append(f"G1 Z-{_number(depth)}")
                    current_z = -float(depth)
                    pass_count += 1
                elif kind == "cut":
                    if active_feed != path_feed:
                        lines.append(f"G1 X{_number(x)} Y{_number(y)} F{_number(path_feed, 1)}")
                        active_feed = path_feed
                    else:
                        lines.append(f"G1 X{_number(x)} Y{_number(y)}")
                    cut_count += 1
                elif kind == "retract":
                    lines.append(f"G0 Z{_number(safe_z)}")
                    current_z = safe_z
                    active_feed = None
                else:
                    raise PostProcessorError("motion_unsupported")

    if current_z is None or abs(current_z - safe_z) > 0.0005:
        lines.append(f"G0 Z{_number(safe_z)}")
    lines.append("M5")
    lines.append("M30")
    warnings.append("simulation_dialect_only")
    if machine_profile and not production_approved:
        warnings.append("machine_origin_not_established")
    text = "\n".join(lines) + "\n"
    return NcDocument(
        dialect=SIMULATION_DIALECT,
        post_processor_version=POST_PROCESSOR_VERSION,
        production=False,
        text=text,
        line_count=len(lines),
        path_count=path_count,
        cut_count=cut_count,
        pass_count=pass_count,
        tool_number=tool_number,
        spindle_speed_rpm=spindle,
        warnings=tuple(warnings),
    )


def nc_payload(document: NcDocument) -> dict[str, Any]:
    return {
        "dialect": document.dialect,
        "post_processor_version": document.post_processor_version,
        "production": document.production,
        "text": document.text,
        "line_count": document.line_count,
        "path_count": document.path_count,
        "cut_count": document.cut_count,
        "pass_count": document.pass_count,
        "tool_number": document.tool_number,
        "spindle_speed_rpm": document.spindle_speed_rpm,
        "warnings": list(document.warnings),
        "filename_suffix": ".sim.nc",
    }


__all__ = [
    "POST_PROCESSOR_VERSION",
    "SIMULATION_DIALECT",
    "NcDocument",
    "PostProcessorError",
    "emit_nc",
    "nc_payload",
]
