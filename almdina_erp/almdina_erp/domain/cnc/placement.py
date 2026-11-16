"""Sheet placement on a CNC machine bed (origin bottom-left, X right, Y up).

Sheet-local cutter geometry is never recomputed here. Offsets translate
approved sheet XY into G54 work XY once. Profile home stays in G54 work
coordinates and is not shifted again.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


PLACEMENT_TRANSFORM_VERSION = "placement-xy-v1"
CM_TO_MM = 10.0
MAX_CUTTER_TRAVEL_EXTENSION_MM = 10_000.0
_BOUNDS_TOLERANCE_MM = 1e-9


class PlacementError(ValueError):
    def __init__(self, code: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class CncMachineSpec:
    name: str
    width_cm: float
    length_cm: float
    cutter_travel_left_extension_mm: float = 0.0
    cutter_travel_right_extension_mm: float = 0.0
    cutter_travel_bottom_extension_mm: float = 0.0
    cutter_travel_top_extension_mm: float = 0.0


@dataclass(frozen=True, slots=True)
class SheetPlacement:
    machine_name: str
    machine_width_cm: float
    machine_length_cm: float
    offset_left_cm: float
    offset_bottom_cm: float
    sheet_width_cm: float
    sheet_length_cm: float
    cutter_travel_left_extension_mm: float = 0.0
    cutter_travel_right_extension_mm: float = 0.0
    cutter_travel_bottom_extension_mm: float = 0.0
    cutter_travel_top_extension_mm: float = 0.0
    transform_version: str = PLACEMENT_TRANSFORM_VERSION

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
    def cutter_travel_x_min_mm(self) -> float:
        return -float(self.cutter_travel_left_extension_mm)

    @property
    def cutter_travel_x_max_mm(self) -> float:
        return self.machine_width_mm + float(self.cutter_travel_right_extension_mm)

    @property
    def cutter_travel_y_min_mm(self) -> float:
        return -float(self.cutter_travel_bottom_extension_mm)

    @property
    def cutter_travel_y_max_mm(self) -> float:
        return self.machine_length_mm + float(self.cutter_travel_top_extension_mm)

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
    if not math.isfinite(number) or number < 0:
        raise PlacementError(code)
    return number


def _finite_positive(value: Any, *, code: str) -> float:
    number = _finite_non_negative(value, code=code)
    if number <= 0:
        raise PlacementError(code)
    return number


def normalize_cnc_machine(
    *,
    machine_name: Any,
    width_cm: Any,
    length_cm: Any,
    cutter_travel_left_extension_mm: Any = 0,
    cutter_travel_right_extension_mm: Any = 0,
    cutter_travel_bottom_extension_mm: Any = 0,
    cutter_travel_top_extension_mm: Any = 0,
) -> CncMachineSpec:
    name = str(machine_name or "").strip()
    if not name:
        raise PlacementError("cnc_machine_name_required")
    width = _finite_positive(width_cm, code="cnc_machine_width_invalid")
    length = _finite_positive(length_cm, code="cnc_machine_length_invalid")
    extension_values = (
        (
            "cutter_travel_left_extension_mm",
            cutter_travel_left_extension_mm,
            "cutter_travel_left_extension_invalid",
        ),
        (
            "cutter_travel_right_extension_mm",
            cutter_travel_right_extension_mm,
            "cutter_travel_right_extension_invalid",
        ),
        (
            "cutter_travel_bottom_extension_mm",
            cutter_travel_bottom_extension_mm,
            "cutter_travel_bottom_extension_invalid",
        ),
        (
            "cutter_travel_top_extension_mm",
            cutter_travel_top_extension_mm,
            "cutter_travel_top_extension_invalid",
        ),
    )
    extensions: dict[str, float] = {}
    for fieldname, raw_value, code in extension_values:
        value = _finite_non_negative(raw_value, code=code)
        if value > MAX_CUTTER_TRAVEL_EXTENSION_MM:
            raise PlacementError(code)
        extensions[fieldname] = value
    return CncMachineSpec(name=name, width_cm=width, length_cm=length, **extensions)


def sheet_to_machine_xy(
    sheet_x_mm: float,
    sheet_y_mm: float,
    *,
    offset_left_cm: float,
    offset_bottom_cm: float,
) -> tuple[float, float]:
    """Translate one sheet-local point into machine coordinates."""

    return (
        float(sheet_x_mm) + float(offset_left_cm) * CM_TO_MM,
        float(sheet_y_mm) + float(offset_bottom_cm) * CM_TO_MM,
    )


def validate_sheet_fits_machine(
    *,
    machine_width_cm: float,
    machine_length_cm: float,
    sheet_width_cm: float,
    sheet_length_cm: float,
    offset_left_cm: float,
    offset_bottom_cm: float,
) -> None:
    """Reject negative offsets or a sheet rectangle that leaves the machine bed."""

    machine_w = _finite_positive(machine_width_cm, code="cnc_machine_width_invalid")
    machine_l = _finite_positive(machine_length_cm, code="cnc_machine_length_invalid")
    sheet_w = _finite_positive(sheet_width_cm, code="sheet_width_invalid")
    sheet_l = _finite_positive(sheet_length_cm, code="sheet_length_invalid")
    left = _finite_non_negative(offset_left_cm, code="offset_left_invalid")
    bottom = _finite_non_negative(offset_bottom_cm, code="offset_bottom_invalid")
    if left + sheet_w > machine_w:
        raise PlacementError("sheet_exceeds_machine_width")
    if bottom + sheet_l > machine_l:
        raise PlacementError("sheet_exceeds_machine_length")


def build_sheet_placement(
    *,
    machine: CncMachineSpec | Mapping[str, Any],
    sheet_width_cm: Any,
    sheet_length_cm: Any,
    offset_left_cm: Any,
    offset_bottom_cm: Any,
) -> SheetPlacement:
    if isinstance(machine, CncMachineSpec):
        spec = machine
    else:
        spec = normalize_cnc_machine(
            machine_name=machine.get("name") or machine.get("machine_name"),
            width_cm=machine.get("width_cm"),
            length_cm=machine.get("length_cm"),
            cutter_travel_left_extension_mm=machine.get(
                "cutter_travel_left_extension_mm", 0
            ),
            cutter_travel_right_extension_mm=machine.get(
                "cutter_travel_right_extension_mm", 0
            ),
            cutter_travel_bottom_extension_mm=machine.get(
                "cutter_travel_bottom_extension_mm", 0
            ),
            cutter_travel_top_extension_mm=machine.get(
                "cutter_travel_top_extension_mm", 0
            ),
        )
    sheet_w = _finite_positive(sheet_width_cm, code="sheet_width_invalid")
    sheet_l = _finite_positive(sheet_length_cm, code="sheet_length_invalid")
    left = _finite_non_negative(offset_left_cm, code="offset_left_invalid")
    bottom = _finite_non_negative(offset_bottom_cm, code="offset_bottom_invalid")
    validate_sheet_fits_machine(
        machine_width_cm=spec.width_cm,
        machine_length_cm=spec.length_cm,
        sheet_width_cm=sheet_w,
        sheet_length_cm=sheet_l,
        offset_left_cm=left,
        offset_bottom_cm=bottom,
    )
    return SheetPlacement(
        machine_name=spec.name,
        machine_width_cm=spec.width_cm,
        machine_length_cm=spec.length_cm,
        offset_left_cm=left,
        offset_bottom_cm=bottom,
        sheet_width_cm=sheet_w,
        sheet_length_cm=sheet_l,
        cutter_travel_left_extension_mm=spec.cutter_travel_left_extension_mm,
        cutter_travel_right_extension_mm=spec.cutter_travel_right_extension_mm,
        cutter_travel_bottom_extension_mm=spec.cutter_travel_bottom_extension_mm,
        cutter_travel_top_extension_mm=spec.cutter_travel_top_extension_mm,
    )


def placement_fingerprint_payload(placement: SheetPlacement | None) -> dict[str, Any]:
    if placement is None:
        return {}
    return {
        "cnc_machine": placement.machine_name,
        "machine_width_cm": placement.machine_width_cm,
        "machine_length_cm": placement.machine_length_cm,
        "cutter_travel_left_extension_mm": placement.cutter_travel_left_extension_mm,
        "cutter_travel_right_extension_mm": placement.cutter_travel_right_extension_mm,
        "cutter_travel_bottom_extension_mm": placement.cutter_travel_bottom_extension_mm,
        "cutter_travel_top_extension_mm": placement.cutter_travel_top_extension_mm,
        "offset_left_cm": placement.offset_left_cm,
        "offset_bottom_cm": placement.offset_bottom_cm,
        "placement_transform_version": placement.transform_version,
    }


def placement_snapshot_payload(placement: SheetPlacement) -> dict[str, Any]:
    payload = placement_fingerprint_payload(placement)
    payload.update(
        {
            "offset_left_mm": placement.offset_left_mm,
            "offset_bottom_mm": placement.offset_bottom_mm,
            "machine_width_mm": placement.machine_width_mm,
            "machine_length_mm": placement.machine_length_mm,
            "cutter_travel_x_min_mm": placement.cutter_travel_x_min_mm,
            "cutter_travel_x_max_mm": placement.cutter_travel_x_max_mm,
            "cutter_travel_y_min_mm": placement.cutter_travel_y_min_mm,
            "cutter_travel_y_max_mm": placement.cutter_travel_y_max_mm,
            "sheet_width_cm": placement.sheet_width_cm,
            "sheet_length_cm": placement.sheet_length_cm,
        }
    )
    return payload


def _iter_program_xy_details(
    program: Mapping[str, Any],
) -> list[tuple[str, float, float]]:
    points: list[tuple[str, float, float]] = []
    for operation_index, operation in enumerate(program.get("operations") or (), start=1):
        operation_key = str(operation.get("operation_key") or f"operation:{operation_index}")
        for path_index, path in enumerate(operation.get("toolpaths") or (), start=1):
            path_key = str(path.get("path_key") or f"{operation_key}:path:{path_index}")
            for motion in path.get("motions") or ():
                kind = str(motion.get("kind") or "")
                if kind not in {"travel", "cut"}:
                    continue
                x = motion.get("x_mm")
                y = motion.get("y_mm")
                if x is None or y is None:
                    continue
                points.append((path_key, float(x), float(y)))
            for point in path.get("points") or ():
                if not isinstance(point, Sequence) or len(point) < 2:
                    continue
                points.append((path_key, float(point[0]), float(point[1])))
    return points


def iter_program_xy_mm(program: Mapping[str, Any]) -> list[tuple[float, float]]:
    return [(x_mm, y_mm) for _path_key, x_mm, y_mm in _iter_program_xy_details(program)]


def validate_program_within_machine(
    program: Mapping[str, Any],
    placement: SheetPlacement,
) -> None:
    """Ensure every placed cutter centre stays inside the configured G54 travel."""

    bounds = {
        "X": (placement.cutter_travel_x_min_mm, placement.cutter_travel_x_max_mm),
        "Y": (placement.cutter_travel_y_min_mm, placement.cutter_travel_y_max_mm),
    }
    for path_key, sheet_x, sheet_y in _iter_program_xy_details(program):
        machine_x, machine_y = sheet_to_machine_xy(
            sheet_x,
            sheet_y,
            offset_left_cm=placement.offset_left_cm,
            offset_bottom_cm=placement.offset_bottom_cm,
        )
        for axis, coordinate in (("X", machine_x), ("Y", machine_y)):
            minimum, maximum = bounds[axis]
            if coordinate < minimum - _BOUNDS_TOLERANCE_MM:
                overrun = minimum - coordinate
            elif coordinate > maximum + _BOUNDS_TOLERANCE_MM:
                overrun = coordinate - maximum
            else:
                continue
            raise PlacementError(
                "toolpath_exceeds_machine",
                details={
                    "machine_name": placement.machine_name,
                    "path_key": path_key,
                    "axis": axis,
                    "coordinate_mm": coordinate,
                    "minimum_mm": minimum,
                    "maximum_mm": maximum,
                    "overrun_mm": overrun,
                },
            )


def apply_placement_to_program(
    program: Mapping[str, Any],
    placement: SheetPlacement,
) -> dict[str, Any]:
    """Return a deep-copied program whose cutter XY is in G54 work coordinates.

    Z depths, profile home, and other non-path fields stay unchanged. Home is
    already a G54 position and must not receive the sheet offset. The original
    sheet program is not mutated.
    """

    validate_program_within_machine(program, placement)
    left = placement.offset_left_cm
    bottom = placement.offset_bottom_cm
    operations: list[dict[str, Any]] = []
    for operation in program.get("operations") or ():
        toolpaths: list[dict[str, Any]] = []
        for path in operation.get("toolpaths") or ():
            points = []
            for point in path.get("points") or ():
                if not isinstance(point, Sequence) or len(point) < 2:
                    points.append(point)
                    continue
                mx, my = sheet_to_machine_xy(float(point[0]), float(point[1]), offset_left_cm=left, offset_bottom_cm=bottom)
                points.append([mx, my])
            motions = []
            for motion in path.get("motions") or ():
                item = dict(motion)
                if item.get("x_mm") is not None and item.get("y_mm") is not None:
                    mx, my = sheet_to_machine_xy(
                        float(item["x_mm"]),
                        float(item["y_mm"]),
                        offset_left_cm=left,
                        offset_bottom_cm=bottom,
                    )
                    item["x_mm"] = mx
                    item["y_mm"] = my
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
    payload["coordinate_space"] = "machine_bottom_left_y_up_mm"
    payload["sheet_coordinate_space"] = "sheet_bottom_left_y_up_mm"
    payload["placement"] = placement_snapshot_payload(placement)
    return payload


__all__ = [
    "CM_TO_MM",
    "CncMachineSpec",
    "MAX_CUTTER_TRAVEL_EXTENSION_MM",
    "PLACEMENT_TRANSFORM_VERSION",
    "PlacementError",
    "SheetPlacement",
    "apply_placement_to_program",
    "build_sheet_placement",
    "iter_program_xy_mm",
    "normalize_cnc_machine",
    "placement_fingerprint_payload",
    "placement_snapshot_payload",
    "sheet_to_machine_xy",
    "validate_program_within_machine",
    "validate_sheet_fits_machine",
]
