"""Parse simulation NC text and compare cut motions to an intermediate program."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


_WORD = re.compile(r"([A-Za-z])([+-]?(?:\d+\.?\d*|\.\d+))")
_TOLERANCE_MM = 0.05


@dataclass(frozen=True, slots=True)
class NcMotion:
    kind: str
    x_mm: float | None
    y_mm: float | None
    z_mm: float | None
    feed: float | None
    rapid: bool


@dataclass(frozen=True, slots=True)
class NcState:
    units: str
    distance_mode: str
    plane: str
    work_offset: str
    tool_number: str
    spindle_speed_rpm: int
    spindle_on: bool
    ended: bool
    motions: tuple[NcMotion, ...]
    min_x: float | None
    max_x: float | None
    min_y: float | None
    max_y: float | None
    min_z: float | None
    max_z: float | None
    unsafe_rapids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NcVerification:
    ok: bool
    issues: tuple[str, ...]
    matched_cuts: int
    matched_plunges: int
    state: NcState


def _words(line: str) -> dict[str, float | str]:
    body = line.split("(", 1)[0].strip()
    if not body or body.startswith(";"):
        return {}
    found: dict[str, float | str] = {}
    for letter, raw in _WORD.findall(body):
        key = letter.upper()
        if key == "T":
            found[key] = f"T{str(raw).lstrip('+').split('.', 1)[0]}"
            continue
        found[key] = float(raw)
    return found


def interpret_nc(
    text: str,
    *,
    safe_z_mm: float = 20.0,
    allowed_safe_z_mm: Sequence[float] | None = None,
) -> NcState:
    units = ""
    distance_mode = ""
    plane = ""
    work_offset = ""
    tool = ""
    spindle = 0
    spindle_on = False
    ended = False
    x = y = z = None
    feed = None
    motions: list[NcMotion] = []
    unsafe: list[str] = []
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    allowed_heights = [float(safe_z_mm)]
    for height in allowed_safe_z_mm or ():
        allowed_heights.append(float(height))

    def _at_allowed_height(height: float) -> bool:
        return any(abs(float(height) - allowed) <= _TOLERANCE_MM for allowed in allowed_heights)

    for raw in str(text or "").splitlines():
        words = _words(raw)
        if not words:
            if "M30" in raw.upper().split("(")[0]:
                ended = True
            continue
        g_code = int(words["G"]) if "G" in words else None
        m_code = int(words["M"]) if "M" in words else None
        if "T" in words:
            tool = str(words["T"])
        if "S" in words:
            spindle = int(float(words["S"]))
        if m_code == 3:
            spindle_on = True
        elif m_code == 5:
            spindle_on = False
        elif m_code == 30:
            ended = True
        if g_code == 21:
            units = "mm"
        elif g_code == 90:
            distance_mode = "G90"
        elif g_code == 91:
            distance_mode = "G91"
        elif g_code == 17:
            plane = "G17"
        elif g_code == 54:
            work_offset = "G54"
        elif g_code in (0, 1):
            has_x = "X" in words
            has_y = "Y" in words
            has_z = "Z" in words
            nx = float(words["X"]) if has_x else x
            ny = float(words["Y"]) if has_y else y
            nz = float(words["Z"]) if has_z else z
            if "F" in words:
                feed = float(words["F"])
            if g_code == 0:
                if (
                    has_x
                    and has_y
                    and z is not None
                    and not _at_allowed_height(float(z))
                    and (not has_z or abs(float(nz) - float(z)) <= _TOLERANCE_MM)
                ):
                    unsafe.append("rapid_inside_material")
                kind = "travel"
                if has_z and (not has_x and not has_y):
                    kind = "retract" if float(nz) >= 0 else "plunge"
                motions.append(NcMotion(kind, nx, ny, nz if has_z else z, None, True))
            else:
                if has_z and not has_x and not has_y:
                    kind = "plunge"
                else:
                    kind = "cut"
                motions.append(NcMotion(kind, nx, ny, nz if has_z else z, feed, False))
            if has_x:
                x = nx
            if has_y:
                y = ny
            if has_z:
                z = nz
            if x is not None:
                xs.append(float(x))
            if y is not None:
                ys.append(float(y))
            if z is not None:
                zs.append(float(z))

    return NcState(
        units=units or "unknown",
        distance_mode=distance_mode or "unknown",
        plane=plane or "unknown",
        work_offset=work_offset or "unknown",
        tool_number=tool,
        spindle_speed_rpm=spindle,
        spindle_on=spindle_on,
        ended=ended,
        motions=tuple(motions),
        min_x=min(xs) if xs else None,
        max_x=max(xs) if xs else None,
        min_y=min(ys) if ys else None,
        max_y=max(ys) if ys else None,
        min_z=min(zs) if zs else None,
        max_z=max(zs) if zs else None,
        unsafe_rapids=tuple(dict.fromkeys(unsafe)),
    )


def _expected_machine_motions(program: Mapping[str, Any]) -> list[tuple[str, float, float, float]]:
    rows: list[tuple[str, float, float, float]] = []
    for operation in program.get("operations") or []:
        for path in operation.get("toolpaths") or []:
            for motion in path.get("motions") or []:
                kind = str(motion.get("kind") or "")
                if kind == "plunge":
                    rows.append((kind, float(motion["x_mm"]), float(motion["y_mm"]), -float(motion["depth_mm"])))
                elif kind == "cut":
                    rows.append((kind, float(motion["x_mm"]), float(motion["y_mm"]), -float(motion["depth_mm"])))
    return rows


def verify_nc_against_program(
    text: str,
    program: Mapping[str, Any],
    *,
    safe_z_mm: float = 20.0,
) -> NcVerification:
    allowed_heights = [float(safe_z_mm)]
    for operation in program.get("operations") or []:
        for path in operation.get("toolpaths") or []:
            if not isinstance(path, Mapping):
                continue
            raw_safe = path.get("safe_z_mm")
            if raw_safe not in (None, ""):
                allowed_heights.append(float(raw_safe))
            home = path.get("home")
            if isinstance(home, Mapping) and home.get("z_mm") not in (None, ""):
                allowed_heights.append(float(home.get("z_mm")))
    state = interpret_nc(text, safe_z_mm=safe_z_mm, allowed_safe_z_mm=allowed_heights)
    issues: list[str] = []
    if state.units != "mm":
        issues.append("units_mismatch")
    if state.distance_mode != "G90":
        issues.append("distance_mode_mismatch")
    if not state.ended:
        issues.append("program_end_missing")
    if state.unsafe_rapids:
        issues.append("rapid_inside_material")
    expected = _expected_machine_motions(program)
    observed = [
        (
            motion.kind,
            float(motion.x_mm),
            float(motion.y_mm),
            float(motion.z_mm),
        )
        for motion in state.motions
        if motion.kind in {"cut", "plunge"}
        and motion.x_mm is not None
        and motion.y_mm is not None
        and motion.z_mm is not None
    ]
    # Plunge lines in NC omit X/Y; recover them from the previous travel.
    recovered: list[tuple[str, float, float, float]] = []
    last_xy: tuple[float, float] | None = None
    for motion in state.motions:
        if motion.x_mm is not None and motion.y_mm is not None:
            last_xy = (float(motion.x_mm), float(motion.y_mm))
        if motion.kind not in {"cut", "plunge"} or motion.z_mm is None:
            continue
        if motion.kind == "plunge":
            if last_xy is None:
                issues.append("plunge_without_xy")
                continue
            recovered.append(("plunge", last_xy[0], last_xy[1], float(motion.z_mm)))
        else:
            if motion.x_mm is None or motion.y_mm is None:
                issues.append("cut_without_xy")
                continue
            recovered.append(("cut", float(motion.x_mm), float(motion.y_mm), float(motion.z_mm)))
    if len(expected) != len(recovered):
        issues.append("motion_count_mismatch")
    matched_cuts = 0
    matched_plunges = 0
    for left, right in zip(expected, recovered):
        if left[0] != right[0]:
            issues.append("motion_kind_mismatch")
            break
        if math.dist(left[1:3], right[1:3]) > _TOLERANCE_MM or abs(left[3] - right[3]) > _TOLERANCE_MM:
            issues.append("motion_coordinate_mismatch")
            break
        if left[0] == "cut":
            matched_cuts += 1
        else:
            matched_plunges += 1
    else:
        if len(expected) == len(recovered) and "motion_kind_mismatch" not in issues and "motion_coordinate_mismatch" not in issues:
            matched_cuts = sum(1 for row in expected if row[0] == "cut")
            matched_plunges = sum(1 for row in expected if row[0] == "plunge")
    unique = []
    for code in issues:
        if code not in unique:
            unique.append(code)
    return NcVerification(
        ok=not unique,
        issues=tuple(unique),
        matched_cuts=matched_cuts,
        matched_plunges=matched_plunges,
        state=state,
    )


def verification_payload(result: NcVerification) -> dict[str, Any]:
    state = result.state
    return {
        "ok": result.ok,
        "issues": list(result.issues),
        "matched_cuts": result.matched_cuts,
        "matched_plunges": result.matched_plunges,
        "units": state.units,
        "distance_mode": state.distance_mode,
        "work_offset": state.work_offset,
        "tool_number": state.tool_number,
        "spindle_speed_rpm": state.spindle_speed_rpm,
        "ended": state.ended,
        "bounds": {
            "min_x": state.min_x,
            "max_x": state.max_x,
            "min_y": state.min_y,
            "max_y": state.max_y,
            "min_z": state.min_z,
            "max_z": state.max_z,
        },
        "unsafe_rapids": list(state.unsafe_rapids),
    }


__all__ = [
    "NcMotion",
    "NcState",
    "NcVerification",
    "interpret_nc",
    "verification_payload",
    "verify_nc_against_program",
]
