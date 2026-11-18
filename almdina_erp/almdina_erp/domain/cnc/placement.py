"""Sheet placement on a CNC machine bed.

Internal geometry stays bottom-left, X to the right, Y up, in millimetres.
The width stop and the length stop are independent of the work zero. Each
stop occupies the whole gap between the full board and the machine bed on
the chosen side, and the board sits flush against the two opposite edges.
Work zero then chooses the G54 origin. The shift is applied once. It does
not reverse axes, rotate the sheet, or change path shape.

Stored manual stop distances are historical. They are not copied onto a
side and they do not move the board. A machine with no chosen sides stays
unset until someone selects them.

Profile home is already a G54 position and is not shifted again. G53
machine coordinates are not produced here.

Machine width and length bound the sheet rectangle. They are not mechanical
limits for the cutter centre. Approved path geometry may leave the sheet
and the bed, including negative coordinates. This module does not clip
those coordinates and does not invent axis-travel limits.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


PLACEMENT_TRANSFORM_VERSION = "placement-xy-v2"
CM_TO_MM = 10.0
WORK_ZERO_BOTTOM_LEFT = "Bottom Left"
WORK_ZERO_POSITIONS = (
    "Bottom Left",
    "Bottom Right",
    "Top Left",
    "Top Right",
)
WIDTH_STOP_LEFT = "Left Side"
WIDTH_STOP_RIGHT = "Right Side"
WIDTH_STOP_SIDES = (WIDTH_STOP_LEFT, WIDTH_STOP_RIGHT)
LENGTH_STOP_BOTTOM = "Bottom Side"
LENGTH_STOP_TOP = "Top Side"
LENGTH_STOP_SIDES = (LENGTH_STOP_BOTTOM, LENGTH_STOP_TOP)
SHEET_COORDINATE_SPACE = "sheet_bottom_left_y_up_mm"
G54_COORDINATE_SPACE = "g54_work_zero_y_up_mm"
POSTABLE_COORDINATE_SPACES = frozenset(
    {
        SHEET_COORDINATE_SPACE,
        "machine_bottom_left_y_up_mm",
        G54_COORDINATE_SPACE,
    }
)


class PlacementError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CncMachineSpec:
    name: str
    width_cm: float
    length_cm: float
    work_zero_position: str
    left_stop_cm: float | None
    bottom_stop_cm: float | None
    right_stop_cm: float | None = None
    top_stop_cm: float | None = None
    width_stop_side: str | None = None
    length_stop_side: str | None = None


@dataclass(frozen=True, slots=True)
class SheetPlacement:
    machine_name: str
    machine_width_cm: float
    machine_length_cm: float
    offset_left_cm: float
    offset_bottom_cm: float
    sheet_width_cm: float
    sheet_length_cm: float
    work_zero_position: str = WORK_ZERO_BOTTOM_LEFT
    transform_version: str = PLACEMENT_TRANSFORM_VERSION
    horizontal_stop_cm: float = 0.0
    vertical_stop_cm: float = 0.0
    horizontal_stop_side: str = "left"
    vertical_stop_side: str = "bottom"

    @property
    def offset_left_mm(self) -> float:
        return float(self.offset_left_cm) * CM_TO_MM

    @property
    def offset_bottom_mm(self) -> float:
        return float(self.offset_bottom_cm) * CM_TO_MM

    @property
    def machine_width_mm(self) -> float:
        return float(self.machine_width_cm) * CM_TO_MM

    @property
    def machine_length_mm(self) -> float:
        return float(self.machine_length_cm) * CM_TO_MM

    @property
    def sheet_width_mm(self) -> float:
        return float(self.sheet_width_cm) * CM_TO_MM

    @property
    def sheet_length_mm(self) -> float:
        return float(self.sheet_length_cm) * CM_TO_MM


def _finite_non_negative(value: Any, *, code: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PlacementError(code) from exc
    if number != number or number < 0:  # NaN or negative
        raise PlacementError(code)
    return number


def _finite_positive(value: Any, *, code: str) -> float:
    number = _finite_non_negative(value, code=code)
    if number <= 0:
        raise PlacementError(code)
    return number


def _blank_stop(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not str(value).strip())


def _stored_stop(value: Any, *, invalid_code: str) -> float | None:
    """Keep a historical measurement. Blank stays blank and is not a side."""

    if _blank_stop(value):
        return None
    return _finite_non_negative(value, code=invalid_code)


def _stop_side(value: Any, *, allowed: tuple[str, ...]) -> str | None:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return None
    token = str(value).strip()
    if token not in allowed:
        raise PlacementError("cnc_machine_stop_sides_required")
    return token


def _work_zero_position(value: Any) -> str:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return WORK_ZERO_BOTTOM_LEFT
    token = str(value).strip()
    if token == "Center":
        raise PlacementError("work_zero_center_retired")
    if token not in WORK_ZERO_POSITIONS:
        raise PlacementError("work_zero_invalid")
    return token


def _public_work_zero(value: Any) -> str:
    token = str(value or "").strip()
    return token or WORK_ZERO_BOTTOM_LEFT


def normalize_cnc_machine(
    *,
    machine_name: Any,
    width_cm: Any,
    length_cm: Any,
    work_zero_position: Any = WORK_ZERO_BOTTOM_LEFT,
    left_stop_cm: Any = None,
    bottom_stop_cm: Any = None,
    right_stop_cm: Any = None,
    top_stop_cm: Any = None,
    width_stop_side: Any = None,
    length_stop_side: Any = None,
    require_stop_sides: bool = True,
) -> CncMachineSpec:
    name = str(machine_name or "").strip()
    if not name:
        raise PlacementError("cnc_machine_name_required")
    width = _finite_positive(width_cm, code="cnc_machine_width_invalid")
    length = _finite_positive(length_cm, code="cnc_machine_length_invalid")
    position = _work_zero_position(work_zero_position)
    horizontal = _stop_side(width_stop_side, allowed=WIDTH_STOP_SIDES)
    vertical = _stop_side(length_stop_side, allowed=LENGTH_STOP_SIDES)
    if require_stop_sides and (horizontal is None or vertical is None):
        raise PlacementError("cnc_machine_stop_sides_required")
    return CncMachineSpec(
        name=name,
        width_cm=width,
        length_cm=length,
        work_zero_position=position,
        left_stop_cm=_stored_stop(left_stop_cm, invalid_code="offset_left_invalid"),
        right_stop_cm=_stored_stop(right_stop_cm, invalid_code="offset_right_invalid"),
        bottom_stop_cm=_stored_stop(bottom_stop_cm, invalid_code="offset_bottom_invalid"),
        top_stop_cm=_stored_stop(top_stop_cm, invalid_code="offset_top_invalid"),
        width_stop_side=horizontal,
        length_stop_side=vertical,
    )


def _mapping_stop(machine: Mapping[str, Any], key: str, *, missing: Any) -> Any:
    if key not in machine:
        return missing
    return machine.get(key)


def _spec_from_machine(machine: CncMachineSpec | Mapping[str, Any]) -> CncMachineSpec:
    if isinstance(machine, CncMachineSpec):
        return machine
    return normalize_cnc_machine(
        machine_name=machine.get("name") or machine.get("machine_name"),
        width_cm=machine.get("width_cm"),
        length_cm=machine.get("length_cm"),
        work_zero_position=machine.get("work_zero_position", WORK_ZERO_BOTTOM_LEFT),
        left_stop_cm=_mapping_stop(machine, "left_stop_cm", missing=None),
        right_stop_cm=_mapping_stop(machine, "right_stop_cm", missing=None),
        bottom_stop_cm=_mapping_stop(machine, "bottom_stop_cm", missing=None),
        top_stop_cm=_mapping_stop(machine, "top_stop_cm", missing=None),
        width_stop_side=_mapping_stop(machine, "width_stop_side", missing=None),
        length_stop_side=_mapping_stop(machine, "length_stop_side", missing=None),
    )


def public_cnc_machine(row: Mapping[str, Any]) -> dict[str, Any]:
    """Catalog row. Missing stop sides stay empty. They are not inferred.

    A stored Center value is returned as stored. Generation rejects it until
    the machine is given one of the four corners. Historical stop distances
    stay on the row and are not turned into a side.
    """

    def stop(key: str, *, missing: float | None) -> float | None:
        if key not in row:
            return missing
        value = row.get(key)
        if value is None or value == "":
            return None
        return float(value)

    return {
        "name": str(row.get("name") or ""),
        "machine_name": str(row.get("machine_name") or row.get("name") or ""),
        "width_cm": float(row.get("width_cm") or 0),
        "length_cm": float(row.get("length_cm") or 0),
        "enabled": bool(row.get("enabled", True)),
        "work_zero_position": _public_work_zero(row.get("work_zero_position")),
        "width_stop_side": str(row.get("width_stop_side") or "").strip(),
        "length_stop_side": str(row.get("length_stop_side") or "").strip(),
        "left_stop_cm": stop("left_stop_cm", missing=None),
        "right_stop_cm": stop("right_stop_cm", missing=None),
        "bottom_stop_cm": stop("bottom_stop_cm", missing=None),
        "top_stop_cm": stop("top_stop_cm", missing=None),
        "post_processor": str(row.get("post_processor") or ""),
    }


def legacy_machine_stops_remain_unset(saved_offsets: Sequence[tuple[Any, Any]]) -> bool:
    """True when saved sheet offsets must not be copied and must not become zero.

    An empty history, or a history that is entirely zero, can stay at zero.
    Any non-zero saved offset, including conflicting values, leaves the
    machine unset so it is configured once.
    """

    for left, bottom in saved_offsets:
        try:
            left_value = 0.0 if left in (None, "") else float(left)
            bottom_value = 0.0 if bottom in (None, "") else float(bottom)
        except (TypeError, ValueError):
            return True
        if left_value != left_value or bottom_value != bottom_value:
            return True
        if left_value != 0 or bottom_value != 0:
            return True
    return False


def sheet_to_machine_xy(
    sheet_x_mm: float,
    sheet_y_mm: float,
    *,
    offset_left_cm: float,
    offset_bottom_cm: float,
) -> tuple[float, float]:
    """Add the sheet's physical origin once. The offsets are already in centimetres."""

    return (
        float(sheet_x_mm) + float(offset_left_cm) * CM_TO_MM,
        float(sheet_y_mm) + float(offset_bottom_cm) * CM_TO_MM,
    )


def work_zero_origin_mm(
    position: str,
    *,
    machine_width_mm: float,
    machine_length_mm: float,
) -> tuple[float, float]:
    """G54 origin on the machine bed. Axes stay X right and Y up."""

    token = _work_zero_position(position)
    width = float(machine_width_mm)
    length = float(machine_length_mm)
    if token == "Bottom Left":
        return 0.0, 0.0
    if token == "Bottom Right":
        return width, 0.0
    if token == "Top Left":
        return 0.0, length
    return width, length


def automatic_clearance_cm(
    machine_cm: float,
    sheet_cm: float,
    *,
    axis: str,
) -> float:
    """Full-board gap on one axis. A larger board cannot be placed."""

    gap = float(machine_cm) - float(sheet_cm)
    if gap < -1e-6:
        raise PlacementError(
            "sheet_exceeds_machine_width" if axis == "width" else "sheet_exceeds_machine_length"
        )
    return 0.0 if gap < 0 else gap


def sheet_origin_mm(
    *,
    machine_width_mm: float,
    machine_length_mm: float,
    sheet_width_mm: float,
    sheet_length_mm: float,
    width_stop_side: str,
    length_stop_side: str,
) -> tuple[float, float]:
    """Bottom-left corner of the full board on the machine bed.

    The stop gap is the machine size minus the full board size. It sits on
    the selected side. The board is flush with the opposite edges. Work zero
    is not an argument: it does not choose the side.
    """

    width_side = _stop_side(width_stop_side, allowed=WIDTH_STOP_SIDES)
    length_side = _stop_side(length_stop_side, allowed=LENGTH_STOP_SIDES)
    if width_side is None or length_side is None:
        raise PlacementError("cnc_machine_stop_sides_required")
    width_gap = automatic_clearance_cm(
        float(machine_width_mm) / CM_TO_MM,
        float(sheet_width_mm) / CM_TO_MM,
        axis="width",
    )
    length_gap = automatic_clearance_cm(
        float(machine_length_mm) / CM_TO_MM,
        float(sheet_length_mm) / CM_TO_MM,
        axis="length",
    )
    origin_x = width_gap if width_side == WIDTH_STOP_LEFT else 0.0
    origin_y = length_gap if length_side == LENGTH_STOP_BOTTOM else 0.0
    return origin_x * CM_TO_MM, origin_y * CM_TO_MM


def sheet_to_nc_xy(
    sheet_x_mm: float,
    sheet_y_mm: float,
    placement: SheetPlacement,
) -> tuple[float, float]:
    """Add the physical sheet origin once, then subtract the work-zero origin once."""

    physical_x, physical_y = sheet_to_machine_xy(
        sheet_x_mm,
        sheet_y_mm,
        offset_left_cm=placement.offset_left_cm,
        offset_bottom_cm=placement.offset_bottom_cm,
    )
    zero_x, zero_y = work_zero_origin_mm(
        placement.work_zero_position,
        machine_width_mm=placement.machine_width_mm,
        machine_length_mm=placement.machine_length_mm,
    )
    return physical_x - zero_x, physical_y - zero_y


def _origin_inside_bed(
    *,
    machine_width_cm: float,
    machine_length_cm: float,
    sheet_width_cm: float,
    sheet_length_cm: float,
    origin_x_mm: float,
    origin_y_mm: float,
) -> None:
    if origin_x_mm < -1e-6 or origin_x_mm + sheet_width_cm * CM_TO_MM > machine_width_cm * CM_TO_MM + 1e-6:
        raise PlacementError("sheet_exceeds_machine_width")
    if origin_y_mm < -1e-6 or origin_y_mm + sheet_length_cm * CM_TO_MM > machine_length_cm * CM_TO_MM + 1e-6:
        raise PlacementError("sheet_exceeds_machine_length")


def validate_sheet_fits_machine(
    *,
    machine_width_cm: float,
    machine_length_cm: float,
    sheet_width_cm: float,
    sheet_length_cm: float,
    offset_left_cm: float = 0,
    offset_bottom_cm: float = 0,
    work_zero_position: str = WORK_ZERO_BOTTOM_LEFT,
    right_stop_cm: Any = None,
    top_stop_cm: Any = None,
) -> None:
    """Reject a full board that is larger than the machine bed.

    Stop distances and work zero do not change this check. The automatic gap
    is zero on the edges opposite the stops, so a board that fits the bed
    also fits after it is pushed against those edges.
    """

    del offset_left_cm, offset_bottom_cm, work_zero_position, right_stop_cm, top_stop_cm
    machine_w = _finite_positive(machine_width_cm, code="cnc_machine_width_invalid")
    machine_l = _finite_positive(machine_length_cm, code="cnc_machine_length_invalid")
    sheet_w = _finite_positive(sheet_width_cm, code="sheet_width_invalid")
    sheet_l = _finite_positive(sheet_length_cm, code="sheet_length_invalid")
    automatic_clearance_cm(machine_w, sheet_w, axis="width")
    automatic_clearance_cm(machine_l, sheet_l, axis="length")


def build_sheet_placement(
    *,
    machine: CncMachineSpec | Mapping[str, Any],
    sheet_width_cm: Any,
    sheet_length_cm: Any,
) -> SheetPlacement:
    """Place a full board from the machine size and the two stop sides.

    Callers cannot pass a different offset. Historical stop distances and
    values named ``offset_left_cm`` on a mapping are ignored.
    """

    spec = _spec_from_machine(machine)
    if spec.width_stop_side is None or spec.length_stop_side is None:
        raise PlacementError("cnc_machine_stop_sides_required")
    sheet_w = _finite_positive(sheet_width_cm, code="sheet_width_invalid")
    sheet_l = _finite_positive(sheet_length_cm, code="sheet_length_invalid")
    width_gap = automatic_clearance_cm(spec.width_cm, sheet_w, axis="width")
    length_gap = automatic_clearance_cm(spec.length_cm, sheet_l, axis="length")
    origin_x, origin_y = sheet_origin_mm(
        machine_width_mm=spec.width_cm * CM_TO_MM,
        machine_length_mm=spec.length_cm * CM_TO_MM,
        sheet_width_mm=sheet_w * CM_TO_MM,
        sheet_length_mm=sheet_l * CM_TO_MM,
        width_stop_side=spec.width_stop_side,
        length_stop_side=spec.length_stop_side,
    )
    _origin_inside_bed(
        machine_width_cm=spec.width_cm,
        machine_length_cm=spec.length_cm,
        sheet_width_cm=sheet_w,
        sheet_length_cm=sheet_l,
        origin_x_mm=origin_x,
        origin_y_mm=origin_y,
    )
    horizontal_side = "left" if spec.width_stop_side == WIDTH_STOP_LEFT else "right"
    vertical_side = "bottom" if spec.length_stop_side == LENGTH_STOP_BOTTOM else "top"
    return SheetPlacement(
        machine_name=spec.name,
        machine_width_cm=spec.width_cm,
        machine_length_cm=spec.length_cm,
        offset_left_cm=origin_x / CM_TO_MM,
        offset_bottom_cm=origin_y / CM_TO_MM,
        sheet_width_cm=sheet_w,
        sheet_length_cm=sheet_l,
        work_zero_position=spec.work_zero_position,
        horizontal_stop_cm=width_gap,
        vertical_stop_cm=length_gap,
        horizontal_stop_side=horizontal_side,
        vertical_stop_side=vertical_side,
    )


def placement_fingerprint_payload(placement: SheetPlacement | None) -> dict[str, Any]:
    if placement is None:
        return {}
    return {
        "cnc_machine": placement.machine_name,
        "machine_width_cm": placement.machine_width_cm,
        "machine_length_cm": placement.machine_length_cm,
        "offset_left_cm": placement.offset_left_cm,
        "offset_bottom_cm": placement.offset_bottom_cm,
        "work_zero_position": placement.work_zero_position,
        "horizontal_stop_side": placement.horizontal_stop_side,
        "vertical_stop_side": placement.vertical_stop_side,
        "placement_transform_version": placement.transform_version,
    }


def placement_snapshot_payload(placement: SheetPlacement) -> dict[str, Any]:
    payload = placement_fingerprint_payload(placement)
    zero_x, zero_y = work_zero_origin_mm(
        placement.work_zero_position,
        machine_width_mm=placement.machine_width_mm,
        machine_length_mm=placement.machine_length_mm,
    )
    payload.update(
        {
            "left_stop_cm": (
                placement.horizontal_stop_cm if placement.horizontal_stop_side == "left" else None
            ),
            "right_stop_cm": (
                placement.horizontal_stop_cm if placement.horizontal_stop_side == "right" else None
            ),
            "bottom_stop_cm": (
                placement.vertical_stop_cm if placement.vertical_stop_side == "bottom" else None
            ),
            "top_stop_cm": (
                placement.vertical_stop_cm if placement.vertical_stop_side == "top" else None
            ),
            "horizontal_stop_side": placement.horizontal_stop_side,
            "vertical_stop_side": placement.vertical_stop_side,
            "offset_left_mm": placement.offset_left_mm,
            "offset_bottom_mm": placement.offset_bottom_mm,
            "work_zero_x_mm": zero_x,
            "work_zero_y_mm": zero_y,
            "machine_width_mm": placement.machine_width_mm,
            "machine_length_mm": placement.machine_length_mm,
            "sheet_width_cm": placement.sheet_width_cm,
            "sheet_length_cm": placement.sheet_length_cm,
            "coordinate_space": G54_COORDINATE_SPACE,
        }
    )
    return payload


def iter_program_xy_mm(program: Mapping[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for operation in program.get("operations") or ():
        for path in operation.get("toolpaths") or ():
            for motion in path.get("motions") or ():
                kind = str(motion.get("kind") or "")
                if kind not in {"travel", "cut"}:
                    continue
                x = motion.get("x_mm")
                y = motion.get("y_mm")
                if x is None or y is None:
                    continue
                points.append((float(x), float(y)))
            for point in path.get("points") or ():
                if not isinstance(point, Sequence) or len(point) < 2:
                    continue
                points.append((float(point[0]), float(point[1])))
    return points


def validate_program_within_machine(
    program: Mapping[str, Any],
    placement: SheetPlacement,
) -> None:
    """Accept cutter centres that leave the sheet or the machine bed.

    The sheet rectangle is validated separately by ``validate_sheet_fits_machine``.
    Cutter-centre XY, including the rapid to the path start, is the approved
    machining geometry and is not compared with the bed. No unrecorded
    mechanical travel box is applied here, and the coordinates are not moved
    or shortened. Neighbouring-door collision, recorded profile-home range,
    Z safety, and the G53 parking check stay outside this function.
    """

    del program, placement


def apply_placement_to_program(
    program: Mapping[str, Any],
    placement: SheetPlacement,
) -> dict[str, Any]:
    """Return a copied program whose cutter XY is in G54 work coordinates.

    Stops and work zero are applied together, once. Z depths, feeds, profile
    home, and other non-path fields stay unchanged. Home is already G54 and
    must not receive the stops or the work-zero shift. The original sheet
    program is not mutated.
    """

    validate_program_within_machine(program, placement)
    operations: list[dict[str, Any]] = []
    for operation in program.get("operations") or ():
        toolpaths: list[dict[str, Any]] = []
        for path in operation.get("toolpaths") or ():
            points = []
            for point in path.get("points") or ():
                if not isinstance(point, Sequence) or len(point) < 2:
                    points.append(point)
                    continue
                nc_x, nc_y = sheet_to_nc_xy(float(point[0]), float(point[1]), placement)
                points.append([nc_x, nc_y])
            motions = []
            for motion in path.get("motions") or ():
                item = dict(motion)
                if item.get("x_mm") is not None and item.get("y_mm") is not None:
                    nc_x, nc_y = sheet_to_nc_xy(float(item["x_mm"]), float(item["y_mm"]), placement)
                    item["x_mm"] = nc_x
                    item["y_mm"] = nc_y
                motions.append(item)
            cloned = dict(path)
            cloned["points"] = points
            cloned["motions"] = motions
            toolpaths.append(cloned)
        cloned_op = dict(operation)
        cloned_op["toolpaths"] = toolpaths
        operations.append(cloned_op)
    payload = dict(program)
    payload["operations"] = operations
    payload["coordinate_space"] = G54_COORDINATE_SPACE
    payload["sheet_coordinate_space"] = SHEET_COORDINATE_SPACE
    payload["work_zero_position"] = placement.work_zero_position
    payload["placement"] = placement_snapshot_payload(placement)
    return payload


__all__ = [
    "CM_TO_MM",
    "CncMachineSpec",
    "G54_COORDINATE_SPACE",
    "PLACEMENT_TRANSFORM_VERSION",
    "POSTABLE_COORDINATE_SPACES",
    "PlacementError",
    "SHEET_COORDINATE_SPACE",
    "SheetPlacement",
    "WORK_ZERO_BOTTOM_LEFT",
    "WORK_ZERO_POSITIONS",
    "apply_placement_to_program",
    "build_sheet_placement",
    "iter_program_xy_mm",
    "legacy_machine_stops_remain_unset",
    "normalize_cnc_machine",
    "placement_fingerprint_payload",
    "placement_snapshot_payload",
    "public_cnc_machine",
    "sheet_origin_mm",
    "sheet_to_machine_xy",
    "sheet_to_nc_xy",
    "validate_program_within_machine",
    "validate_sheet_fits_machine",
    "work_zero_origin_mm",
]
