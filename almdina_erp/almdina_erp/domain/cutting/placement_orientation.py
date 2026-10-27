"""In-plane orientation of a placed piece.

Historical plans store only ``rotated``. That flag remains the odd-quarter
bounding-box swap and means the piece is not mirrored. A horizontal mirror is
recorded explicitly. It swaps the left and right edges in the piece plane and
is not a flip of the board's front and back faces.

The transform matches the corner-contour and liner geometry: reflect across
the vertical axis first, then apply clockwise quarter-turns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    inverse_transform_point,
    piece_quarter_turns,
    transform_point,
)

Point = tuple[float, float]


class PlacementOrientationError(ValueError):
    """A placement used a rotation or mirror the order does not allow."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PlacementOrientation:
    mirrored: bool
    quarter_turns: int

    @property
    def rotated(self) -> bool:
        """Historical bbox flag. True only for a 90° or 270° clockwise turn."""

        return bool(self.quarter_turns % 2)

    @property
    def rotation_deg(self) -> int:
        return (self.quarter_turns % 4) * 90


def resolve_placement_orientation(piece: Mapping[str, object] | None) -> PlacementOrientation:
    """Read an orientation without inventing fields the historical record lacks."""

    if not piece:
        return PlacementOrientation(False, 0)
    return PlacementOrientation(recorded_mirror(piece), piece_quarter_turns(piece))


def recorded_mirror(piece: Mapping[str, object] | None) -> bool:
    """True when any stored mirror flag is on. Missing flags stay false.

    The three names are one physical reflection. A lone historical ``rotated``
    flag is not a mirror.
    """

    if not piece:
        return False
    return any(
        key in piece and _flag(piece.get(key))
        for key in ("mirrored", "corner_mirrored", "placement_mirrored")
    )


def assert_orientation_allowed(
    orientation: PlacementOrientation,
    *,
    mirroring_allowed: bool,
    allow_rotation: object,
) -> None:
    """Reject a turn the piece may not rotate, then a mirror the order forbids.

    Rotation is checked first so an illegal quarter-turn keeps its existing
    diagnosis. A mirror with no turn is still rejected when mirroring is not
    allowed. The permission itself is decided outside the cutting algorithms.
    """

    if orientation.quarter_turns % 4 and not _flag(allow_rotation):
        raise PlacementOrientationError("FORBIDDEN_ROTATION")
    if orientation.mirrored and not mirroring_allowed:
        raise PlacementOrientationError("FORBIDDEN_MIRRORING")


def physical_edge_bands(
    bands: Mapping[str, str],
    orientation: PlacementOrientation,
) -> tuple[str, str, str, str]:
    """Physical (left, top, right, bottom) bands after the in-plane transform.

    Horizontal mirroring exchanges left and right only. Top and bottom stay
    put until a quarter-turn moves them.
    """

    left = str(bands.get("left", ""))
    top = str(bands.get("top", ""))
    right = str(bands.get("right", ""))
    bottom = str(bands.get("bottom", ""))
    if orientation.mirrored:
        left, right = right, left
    for _ in range(orientation.quarter_turns % 4):
        left, top, right, bottom = bottom, left, top, right
    return left, top, right, bottom


def transform_ring(
    points: Sequence[Point],
    orientation: PlacementOrientation,
    *,
    width: float,
    height: float,
) -> list[Point]:
    """Move a piece-local ring. The ring's edge lengths are unchanged."""

    return [
        transform_point(
            (float(point[0]), float(point[1])),
            mirrored=orientation.mirrored,
            quarter_turns=orientation.quarter_turns,
            width=width,
            height=height,
        )
        for point in points
    ]


def inverse_ring(
    points: Sequence[Point],
    orientation: PlacementOrientation,
    *,
    width: float,
    height: float,
) -> list[Point]:
    return [
        inverse_transform_point(
            (float(point[0]), float(point[1])),
            mirrored=orientation.mirrored,
            quarter_turns=orientation.quarter_turns,
            width=width,
            height=height,
        )
        for point in points
    ]


def _flag(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true"}
    return bool(int(value or 0)) if isinstance(value, int) else bool(value)
