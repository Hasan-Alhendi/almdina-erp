"""Registered NC post processors.

Path geometry is already calculated. A processor only turns those motions
into one controller dialect. There is no implicit processor.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.post_processor import (
    NcDocument,
    PostProcessorError,
)


IMA_WH_ID = "ima_wh_ncstudio"
IMA_WH_LABEL = "IMA-WH (*.nc)"
IMA_WH_VERSION = "ima-wh-ncstudio-1"
IMA_WH_EXTENSION = "nc"

# Machine coordinates from the IMA-WH end block. They are not a profile home.
IMA_WH_PARKING_X_MM = 1500.0
IMA_WH_PARKING_Y_MM = 3500.0
IMA_WH_PARKING_Z_MM = 0.0
_LINE_INCREMENT = 10
_LINE_MAXIMUM = 9999999
_AXIS_TOLERANCE_MM = 0.0005


def list_post_processors() -> tuple[dict[str, str], ...]:
    return (
        {
            "id": IMA_WH_ID,
            "label": IMA_WH_LABEL,
            "extension": IMA_WH_EXTENSION,
        },
    )


def resolve_post_processor(processor_id: Any, *, required: bool) -> str:
    token = str(processor_id or "").strip()
    if not token:
        if required:
            raise PostProcessorError("post_processor_required")
        return ""
    if token != IMA_WH_ID:
        raise PostProcessorError("post_processor_unsupported")
    return token


def _path_safe_z(path: Mapping[str, Any]) -> float:
    raw = path.get("safe_z_mm")
    if raw in (None, ""):
        preset = path.get("preset") if isinstance(path.get("preset"), Mapping) else {}
        raw = preset.get("safe_z_mm") if isinstance(preset, Mapping) else None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise PostProcessorError("machine_profile_value_invalid") from exc
    if value < 0:
        raise PostProcessorError("machine_profile_value_invalid")
    return value


def _posted_rate(preset: Mapping[str, Any], sec_key: str, min_key: str) -> float:
    sec_raw = preset.get(sec_key)
    min_raw = preset.get(min_key)
    sec_value = None if sec_raw in (None, "") else float(sec_raw)
    min_value = None if min_raw in (None, "") else float(min_raw)
    if sec_value is None and min_value is None:
        raise PostProcessorError("preset_incomplete")
    if sec_value is not None and min_value is not None:
        converted = sec_value * 60.0
        if abs(converted - min_value) > 0.05:
            raise PostProcessorError("feed_rate_inconsistent")
        return converted
    if sec_value is not None:
        return sec_value * 60.0
    return float(min_value)


def _tool_number(raw: Any) -> str:
    token = str(raw or "").strip().upper().replace(" ", "")
    if token.startswith("T"):
        token = token[1:]
    if not token.isdigit():
        raise PostProcessorError("tool_number_invalid")
    return str(int(token))


def _spindle(raw: Any) -> int:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise PostProcessorError("preset_incomplete") from exc
    if value <= 0 or abs(value - round(value)) > 1e-6:
        raise PostProcessorError("preset_incomplete")
    return int(round(value))


def _home(path: Mapping[str, Any]) -> tuple[float, float, float]:
    home = path.get("home")
    if not isinstance(home, Mapping):
        raise PostProcessorError("profile_home_missing")
    try:
        x_mm = float(home.get("x_mm"))
        y_mm = float(home.get("y_mm"))
        z_mm = float(home.get("z_mm"))
    except (TypeError, ValueError) as exc:
        raise PostProcessorError("profile_home_missing") from exc
    if z_mm < 0:
        raise PostProcessorError("profile_home_unsafe")
    return x_mm, y_mm, z_mm


class _LineNumbers:
    def __init__(self) -> None:
        self._value = 0

    def take(self, *, numbered: bool) -> int | None:
        current = self._value
        if current > _LINE_MAXIMUM:
            raise PostProcessorError("line_number_overflow")
        self._value += _LINE_INCREMENT
        return current if numbered else None


class _ImaEmitter:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.numbers = _LineNumbers()
        self.x: float | None = None
        self.y: float | None = None
        self.z: float | None = None
        self.feed: float | None = None
        self.mode: str | None = None

    def _consume(self, text: str, *, numbered: bool) -> None:
        number = self.numbers.take(numbered=numbered)
        if numbered:
            self.lines.append(f"N{number} {text}")
        else:
            self.lines.append(text)

    def literal(self, text: str) -> None:
        self._consume(text, numbered=False)

    def _changed(self, current: float | None, value: float) -> bool:
        return current is None or abs(current - value) > _AXIS_TOLERANCE_MM

    def rapid(self, *, x: float | None = None, y: float | None = None, z: float | None = None) -> None:
        words: list[str] = []
        if x is not None and self._changed(self.x, x):
            words.append(f"X{x:.4f}")
            self.x = x
        if y is not None and self._changed(self.y, y):
            words.append(f"Y{y:.4f}")
            self.y = y
        if z is not None and self._changed(self.z, z):
            words.append(f"Z{z:.4f}")
            self.z = z
        if not words:
            return
        self._consume("G0 " + " ".join(words), numbered=True)
        self.mode = "G0"

    def feed_to(
        self,
        *,
        x: float | None,
        y: float | None,
        z: float | None,
        feed: float,
    ) -> None:
        words: list[str] = []
        if x is not None and self._changed(self.x, x):
            words.append(f"X{x:.4f}")
            self.x = x
        if y is not None and self._changed(self.y, y):
            words.append(f"Y{y:.4f}")
            self.y = y
        if z is not None and self._changed(self.z, z):
            words.append(f"Z{z:.4f}")
            self.z = z
        if not words:
            return
        feed_changed = self.feed is None or abs(self.feed - feed) > 0.05
        first = self.mode != "G1" or feed_changed
        body = " ".join(words)
        if first:
            body = f"G1 {body} F{feed:.1f}"
        self._consume(body, numbered=True)
        self.mode = "G1"
        self.feed = feed

    def rapid_xy_at(self, x: float, y: float, safe_z: float) -> None:
        if self.z is not None and self.z < safe_z - _AXIS_TOLERANCE_MM:
            self.rapid(z=safe_z)
        self.rapid(x=x, y=y, z=safe_z if self.z is None or self._changed(self.z, safe_z) else None)


def _within_machine(x_mm: float, y_mm: float, width_mm: float, length_mm: float) -> bool:
    return (
        x_mm >= -_AXIS_TOLERANCE_MM
        and y_mm >= -_AXIS_TOLERANCE_MM
        and x_mm <= width_mm + _AXIS_TOLERANCE_MM
        and y_mm <= length_mm + _AXIS_TOLERANCE_MM
    )


def emit_ima_wh(
    program: Mapping[str, Any],
    *,
    machine_width_mm: float,
    machine_length_mm: float,
) -> NcDocument:
    """Post one sheet program with the IMA-WH / NCStudio dialect.

    ``program`` cutter XY must already be G54 work coordinates. Stops and
    work zero are not applied again here. The machine bed limits the sheet,
    not the cutter centre, so path coordinates and the rapid to the path
    start are posted as stored, including positions outside the bed. Profile
    home XY is posted as stored because it is already G54. The IMA-WH parking
    move stays the fixed G53 point and is refused when it does not fit the
    selected machine. Choosing a work zero does not change that G53 move.
    Z safety is unchanged.
    """

    if not isinstance(program, Mapping):
        raise PostProcessorError("program_invalid")
    if not program.get("geometry_ready", program.get("ready")):
        raise PostProcessorError("geometry_not_ready")
    from almdina_erp.almdina_erp.domain.cnc.placement import POSTABLE_COORDINATE_SPACES

    coordinate_space = str(program.get("coordinate_space") or "")
    if coordinate_space not in POSTABLE_COORDINATE_SPACES:
        raise PostProcessorError("coordinate_space_unsupported")
    try:
        width_mm = float(machine_width_mm)
        length_mm = float(machine_length_mm)
    except (TypeError, ValueError) as exc:
        raise PostProcessorError("machine_parking_unverified") from exc
    if width_mm <= 0 or length_mm <= 0:
        raise PostProcessorError("machine_parking_unverified")
    if not _within_machine(IMA_WH_PARKING_X_MM, IMA_WH_PARKING_Y_MM, width_mm, length_mm):
        raise PostProcessorError("machine_parking_outside_limits")

    operations = program.get("operations") or []
    if not isinstance(operations, list) or not operations:
        raise PostProcessorError("program_invalid")

    prepared: list[dict[str, Any]] = []
    tool_number = ""
    spindle = 0
    path_count = 0
    cut_count = 0
    pass_count = 0
    for operation in operations:
        for path in operation.get("toolpaths") or []:
            if not path.get("ready"):
                raise PostProcessorError("geometry_not_ready")
            preset = path.get("preset") or {}
            if not isinstance(preset, Mapping):
                raise PostProcessorError("preset_incomplete")
            points = path.get("points") or []
            motions = path.get("motions") or []
            if len(points) < 2 or not motions:
                raise PostProcessorError("geometry_not_ready")
            path_tool = _tool_number(preset.get("tool_number"))
            path_spindle = _spindle(preset.get("spindle_speed_rpm"))
            path_feed = _posted_rate(preset, "feed_rate_mm_sec", "feed_rate_mm_min")
            path_plunge = _posted_rate(preset, "plunge_rate_mm_sec", "plunge_rate_mm_min")
            if path_feed <= 0 or path_plunge <= 0:
                raise PostProcessorError("preset_incomplete")
            if tool_number and tool_number != path_tool:
                raise PostProcessorError("tool_identity_conflict")
            tool_number = path_tool
            spindle = path_spindle
            safe_z = _path_safe_z(path)
            path_count += 1
            prepared.append(
                {
                    "motions": motions,
                    "safe_z": safe_z,
                    "feed": path_feed,
                    "plunge": path_plunge,
                    "home": path.get("home"),
                    "path": path,
                }
            )
            for motion in motions:
                if str(motion.get("kind") or "") == "cut":
                    cut_count += 1
                elif str(motion.get("kind") or "") == "plunge":
                    pass_count += 1
    if not prepared or not tool_number:
        raise PostProcessorError("geometry_not_ready")

    last = prepared[-1]
    home_x, home_y, home_z = _home(last["path"])

    writer = _ImaEmitter()
    for line in ("G90", "G40 G80", "G54", "G53 Z0", f"T{tool_number}", f"M3 S{spindle}"):
        writer.literal(line)

    for item in prepared:
        safe_z = float(item["safe_z"])
        for motion in item["motions"]:
            kind = str(motion.get("kind") or "")
            if kind == "travel":
                writer.rapid_xy_at(float(motion["x_mm"]), float(motion["y_mm"]), safe_z)
            elif kind == "plunge":
                writer.feed_to(x=None, y=None, z=-float(motion["depth_mm"]), feed=float(item["plunge"]))
            elif kind == "cut":
                writer.feed_to(
                    x=float(motion["x_mm"]),
                    y=float(motion["y_mm"]),
                    z=-float(motion["depth_mm"]),
                    feed=float(item["feed"]),
                )
            elif kind == "retract":
                writer.rapid(z=safe_z)
            else:
                raise PostProcessorError("motion_unsupported")

    safe_z = float(last["safe_z"])
    if writer.z is None or writer.z < safe_z - _AXIS_TOLERANCE_MM:
        writer.rapid(z=safe_z)
    if home_z + _AXIS_TOLERANCE_MM < safe_z:
        writer.rapid(x=home_x, y=home_y)
        writer.rapid(z=home_z)
    else:
        writer.rapid(x=home_x, y=home_y, z=home_z)
    if writer.z is None or writer.z < safe_z - _AXIS_TOLERANCE_MM:
        raise PostProcessorError("home_move_unsafe")

    for line in ("G80", "M5", "G53 X1500.0 Y3500.0 Z0", "M30", ";"):
        writer.literal(line)

    text = "\r\n".join(writer.lines) + "\r\n"
    try:
        text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise PostProcessorError("nc_not_ascii") from exc
    return NcDocument(
        dialect=IMA_WH_ID,
        post_processor_version=IMA_WH_VERSION,
        production=False,
        text=text,
        line_count=len(writer.lines),
        path_count=path_count,
        cut_count=cut_count,
        pass_count=pass_count,
        tool_number=f"T{tool_number}",
        spindle_speed_rpm=spindle,
        warnings=("g54_g53_transform_unverified",),
    )


__all__ = [
    "IMA_WH_EXTENSION",
    "IMA_WH_ID",
    "IMA_WH_LABEL",
    "IMA_WH_PARKING_X_MM",
    "IMA_WH_PARKING_Y_MM",
    "IMA_WH_PARKING_Z_MM",
    "IMA_WH_VERSION",
    "emit_ima_wh",
    "list_post_processors",
    "resolve_post_processor",
]
