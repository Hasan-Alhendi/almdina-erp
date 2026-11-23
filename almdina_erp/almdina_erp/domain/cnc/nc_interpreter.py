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
    machine_moves: tuple[NcMotion, ...]
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


def _line_words(line: str) -> list[tuple[str, str]]:
    body = line.split("(", 1)[0].strip()
    if not body or body.startswith(";"):
        return []
    return [(letter.upper(), raw) for letter, raw in _WORD.findall(body)]


def interpret_nc(
    text: str,
    *,
    safe_z_mm: float = 20.0,
    allowed_safe_z_mm: Sequence[float] | None = None,
) -> NcState:
    """Read work-coordinate motion from NC text.

    G53 is a machine-coordinate move for that block only. It does not change
    the G54 position and is not treated as a cut. Omitted axes, feed, and
    G0/G1 stay in effect. A program that never states G20/G21 is millimetres.
    """

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
    motion_mode: int | None = None
    motions: list[NcMotion] = []
    machine_moves: list[NcMotion] = []
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
        words = _line_words(raw)
        if not words:
            if "M30" in raw.upper().split("(")[0]:
                ended = True
            continue
        g_codes: list[int] = []
        m_codes: list[int] = []
        has_x = has_y = has_z = False
        x_word = y_word = z_word = None
        for letter, raw_value in words:
            if letter == "N":
                continue
            if letter == "T":
                tool = f"T{int(float(raw_value))}"
                continue
            if letter == "S":
                spindle = int(round(float(raw_value)))
                continue
            if letter == "F":
                feed = float(raw_value)
                continue
            if letter == "M":
                m_codes.append(int(float(raw_value)))
                continue
            if letter == "G":
                g_codes.append(int(float(raw_value)))
                continue
            if letter == "X":
                has_x = True
                x_word = float(raw_value)
            elif letter == "Y":
                has_y = True
                y_word = float(raw_value)
            elif letter == "Z":
                has_z = True
                z_word = float(raw_value)
        for m_code in m_codes:
            if m_code == 3:
                spindle_on = True
            elif m_code == 5:
                spindle_on = False
            elif m_code == 30:
                ended = True
        for g_code in g_codes:
            if g_code == 53:
                continue
            if g_code == 21:
                units = "mm"
            elif g_code == 20:
                units = "inch"
            elif g_code == 90:
                distance_mode = "G90"
            elif g_code == 91:
                distance_mode = "G91"
            elif g_code == 17:
                plane = "G17"
            elif g_code == 54:
                work_offset = "G54"
            elif g_code in (0, 1, 2, 3):
                motion_mode = g_code
        if 53 in g_codes:
            machine_moves.append(
                NcMotion(
                    "machine",
                    x_word,
                    y_word,
                    z_word,
                    feed,
                    motion_mode == 0,
                )
            )
            continue
        if not (has_x or has_y or has_z) or motion_mode not in (0, 1, 2, 3):
            continue
        nx = x_word if has_x else x
        ny = y_word if has_y else y
        nz = z_word if has_z else z
        if motion_mode in (2, 3):
            motions.append(NcMotion("arc", nx, ny, nz if has_z else z, feed, False))
        elif motion_mode == 0:
            moves_xy = has_x or has_y
            end_z = float(nz) if nz is not None else None
            start_safe = z is not None and _at_allowed_height(float(z))
            end_safe = end_z is not None and _at_allowed_height(end_z)
            if moves_xy and not start_safe and not (z is None and has_z and end_safe):
                unsafe.append("rapid_inside_material")
            kind = "travel"
            if has_z and not has_x and not has_y:
                kind = "retract" if float(nz) >= 0 else "plunge"
            motions.append(NcMotion(kind, nx, ny, nz if has_z else z, None, True))
        else:
            kind = "plunge" if has_z and not has_x and not has_y else "cut"
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
        units=units or "mm",
        distance_mode=distance_mode or "unknown",
        plane=plane or "unknown",
        work_offset=work_offset or "unknown",
        tool_number=tool,
        spindle_speed_rpm=spindle,
        spindle_on=spindle_on,
        ended=ended,
        motions=tuple(motions),
        machine_moves=tuple(machine_moves),
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
                elif kind in {"cut", "arc"}:
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
        if motion.kind in {"cut", "plunge", "arc"}
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
        if motion.kind not in {"cut", "plunge", "arc"} or motion.z_mm is None:
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
            recovered.append((motion.kind, float(motion.x_mm), float(motion.y_mm), float(motion.z_mm)))
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
