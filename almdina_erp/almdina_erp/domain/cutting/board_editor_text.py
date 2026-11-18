"""Shape pinned Noto Naskh text into door-local outlines.

HarfBuzz on the system shapes each directional run, including Arabic joining
and mark placement. fontTools reads the same variable-font file for the glyph
curves. Preview and export both call this module, so they share one font
version. Letter counters stay separate closed rings. Nothing here writes a
door contour, a cutter path, or NC.
"""

from __future__ import annotations

import ctypes
import math
import unicodedata
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from fontTools.pens.basePen import decomposeQuadraticSegment
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    DrawingDocumentError,
    normalize_document,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_compile import (
    compile_manufacturing_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import rotate_point
from almdina_erp.almdina_erp.domain.cutting.dxf_layer_catalog import TEXT_OUTLINE_LAYER

FONT_ID = "noto-naskh-arabic"
FONT_VERSION = "1"
CHORD_ERROR_MM = 0.05
MAX_TEXT_CHARS = 80
MAX_TEXT_RINGS = 400
MAX_POINTS_PER_RING = 800
MAX_TEXT_POINTS = 20_000
_WEIGHTS = {"regular": 400.0, "bold": 700.0}
_FONT_FILE = Path(__file__).resolve().parents[3] / "public" / "fonts" / "NotoNaskhArabic-wght.ttf"
_HB = "/usr/lib/x86_64-linux-gnu/libharfbuzz.so.0"


class TextGeometryError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Info(ctypes.Structure):
    _fields_ = [
        ("codepoint", ctypes.c_uint32),
        ("mask", ctypes.c_uint32),
        ("cluster", ctypes.c_uint32),
        ("var1", ctypes.c_uint32),
        ("var2", ctypes.c_uint32),
    ]


class _Pos(ctypes.Structure):
    _fields_ = [
        ("x_advance", ctypes.c_int32),
        ("y_advance", ctypes.c_int32),
        ("x_offset", ctypes.c_int32),
        ("y_offset", ctypes.c_int32),
        ("var", ctypes.c_uint32),
    ]


class _Variation(ctypes.Structure):
    _fields_ = [("tag", ctypes.c_uint32), ("value", ctypes.c_float)]


def layout_text(
    content: str,
    *,
    font_size_mm: float,
    font_weight: str = "regular",
    direction: str = "auto",
    align: str = "left",
) -> dict[str, Any]:
    """Return top-left local outlines. Font size is the em, not the ink height."""

    text = _plain_text(content)
    size = float(font_size_mm)
    if not math.isfinite(size) or size <= 0 or size > 500:
        raise TextGeometryError("invalid_font_size")
    weight = _WEIGHTS.get(str(font_weight or ""))
    if weight is None:
        raise TextGeometryError("invalid_font_weight")
    if direction not in {"auto", "rtl", "ltr"}:
        raise TextGeometryError("invalid_text_direction")
    if align not in {"left", "center", "right"}:
        raise TextGeometryError("invalid_text_align")
    if not _FONT_FILE.is_file():
        raise TextGeometryError("font_unavailable")
    shaped = _shape_runs(text, direction, weight)
    tt, order = _font_instance(weight)
    scale = size / float(tt["head"].unitsPerEm)
    glyphset = tt.getGlyphSet()
    pen_x = 0.0
    rings: list[list[tuple[float, float]]] = []
    for glyph in shaped:
        name = order[glyph["gid"]]
        origin_x = pen_x + glyph["dx"]
        origin_y = glyph["dy"]
        for contour in _glyph_contours(glyphset, name, CHORD_ERROR_MM / scale):
            ring = [
                ((origin_x + point[0]) * scale, -((origin_y + point[1]) * scale))
                for point in contour
            ]
            if len(ring) >= 3:
                rings.append(ring)
        pen_x += glyph["advance"]
    if not rings:
        raise TextGeometryError("text_empty")
    _limit_rings(rings)
    min_x = min(point[0] for ring in rings for point in ring)
    min_y = min(point[1] for ring in rings for point in ring)
    moved = [[(point[0] - min_x, point[1] - min_y) for point in ring] for ring in rings]
    width = max(point[0] for ring in moved for point in ring)
    height = max(point[1] for ring in moved for point in ring)
    if align == "center":
        shift = -width / 2.0
    elif align == "right":
        shift = -width
    else:
        shift = 0.0
    if shift:
        moved = [[(point[0] + shift, point[1]) for point in ring] for ring in moved]
    return {
        "font_id": FONT_ID,
        "font_version": FONT_VERSION,
        "font_size_mm": size,
        "width_mm": width,
        "height_mm": height,
        "outlines": moved,
    }


def place_outlines(
    outlines: Sequence[Sequence[Sequence[float]]],
    *,
    x_mm: float,
    y_mm: float,
    rotation_deg: float,
) -> list[list[tuple[float, float]]]:
    """Keep the alignment origin at x/y, then rotate the placed ink around its center.

    Local outlines use x = 0 as the alignment point. Adding x/y before rotation
    leaves that point fixed when the angle is zero, including after a content edit.
    """

    rings = [_ring(ring) for ring in outlines]
    if not rings:
        raise TextGeometryError("text_empty")
    placed = [[(point[0] + float(x_mm), point[1] + float(y_mm)) for point in ring] for ring in rings]
    if not float(rotation_deg):
        return placed
    xs = [point[0] for ring in placed for point in ring]
    ys = [point[1] for ring in placed for point in ring]
    center = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    return [
        [tuple(rotate_point(point, center, rotation_deg)) for point in ring]
        for ring in placed
    ]


def validate_text_export(
    document: Mapping[str, Any],
    text_id: str,
    *,
    blank_width_mm: float,
    blank_length_mm: float,
) -> dict[str, Any]:
    """Approved text must be vector outlines strictly inside the door contour."""

    try:
        normalized = normalize_document(document)
    except DrawingDocumentError as exc:
        return {"ok": False, "code": exc.code}
    text = next((row for row in normalized.get("texts") or [] if row["id"] == text_id), None)
    if text is None:
        return {"ok": False, "code": "unknown_text"}
    if text["font_id"] != FONT_ID or text["font_version"] != FONT_VERSION:
        return {"ok": False, "code": "font_unavailable"}
    if text["state"] != "vector":
        return {"ok": False, "code": "text_not_vector"}
    rings = [_ring(ring["points"]) for ring in text["outlines"]]
    try:
        _limit_rings(rings)
        for ring in rings:
            if not _closed_valid(ring):
                return {"ok": False, "code": "text_geometry_invalid"}
    except TextGeometryError as exc:
        return {"ok": False, "code": exc.code}
    compiled = compile_manufacturing_geometry(
        normalized,
        blank_width_mm=blank_width_mm,
        blank_length_mm=blank_length_mm,
    )
    if compiled["status"] != "ready":
        return {"ok": False, "code": "text_outside_contour"}
    outer = [(float(point[0]) * 10.0, float(point[1]) * 10.0) for point in compiled["geometry"]["points"]]
    if any(not _strictly_inside(ring, outer) for ring in rings):
        return {"ok": False, "code": "text_outside_contour"}
    if any(_rings_touch(ring, outer) for ring in rings):
        return {"ok": False, "code": "text_crosses_contour"}
    return {"ok": True, "code": "", "role": "manufacturing_text"}


def approved_text_rings(document: Mapping[str, Any]) -> list[list[tuple[float, float]]]:
    """Door-local rings for text the user explicitly approved. Others stay out."""

    normalized = normalize_document(document)
    rings: list[list[tuple[float, float]]] = []
    for text in normalized.get("texts") or []:
        if text["state"] != "vector" or text["export_approved"] is not True:
            continue
        if text["role"] != "manufacturing_text":
            continue
        rings.extend(_ring(row["points"]) for row in text["outlines"])
    return rings


def pose_door_rings_to_sheet(
    rings: Sequence[Sequence[Sequence[float]]],
    door_reference_mm: Sequence[Sequence[float]],
    sheet_reference_mm: Sequence[Sequence[float]],
) -> list[list[tuple[float, float]]]:
    """Move door-local rings onto the sheet with the contour's one rigid pose.

    The reference rings are the same manufacturing contour before and after the
    door is placed. Text uses that pose once. Repeating the call needs the
    original door-local rings, so a second export does not accumulate it.
    """

    door = [_point(point) for point in door_reference_mm]
    sheet = [_point(point) for point in sheet_reference_mm]
    if len(door) < 2 or len(door) != len(sheet):
        raise TextGeometryError("text_geometry_invalid")
    transform = _rigid_pose(door, sheet)
    if transform is None:
        raise TextGeometryError("text_geometry_invalid")
    posed: list[list[tuple[float, float]]] = []
    for ring in rings:
        posed.append([_apply_affine(transform, point) for point in ring])
    return posed


def _apply_affine(affine: Sequence[float], point: Sequence[float]) -> tuple[float, float]:
    a, b, c, d, dx, dy = affine
    return (
        a * float(point[0]) + b * float(point[1]) + dx,
        c * float(point[0]) + d * float(point[1]) + dy,
    )


def _rigid_pose(
    door: Sequence[tuple[float, float]],
    sheet: Sequence[tuple[float, float]],
) -> tuple[float, float, float, float, float, float] | None:
    best = None
    best_error = None
    for shift in range(len(door)):
        cycled = list(door[shift:]) + list(door[:shift])
        for candidate in (cycled, list(reversed(cycled))):
            for mirrored in (False, True):
                source = [(-point[0], point[1]) for point in candidate] if mirrored else candidate
                fitted = _fit_rigid(source, sheet)
                if mirrored:
                    a, b, c, d, dx, dy = fitted
                    affine = (-a, b, -c, d, dx, dy)
                else:
                    affine = fitted
                error = sum(
                    math.dist(_apply_affine(affine, point), target)
                    for point, target in zip(candidate, sheet)
                ) / len(candidate)
                if best_error is None or error < best_error:
                    best = affine
                    best_error = error
    if best is None or best_error is None or best_error > 0.2:
        return None
    return best


def _fit_rigid(
    source: Sequence[tuple[float, float]],
    target: Sequence[tuple[float, float]],
) -> tuple[float, float, float, float, float, float]:
    source_center = _center(source)
    target_center = _center(target)
    dot = 0.0
    cross = 0.0
    for point, other in zip(source, target, strict=True):
        vx = point[0] - source_center[0]
        vy = point[1] - source_center[1]
        wx = other[0] - target_center[0]
        wy = other[1] - target_center[1]
        dot += vx * wx + vy * wy
        cross += vx * wy - vy * wx
    angle = math.atan2(cross, dot)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    dx = target_center[0] - (cosine * source_center[0] - sine * source_center[1])
    dy = target_center[1] - (sine * source_center[0] + cosine * source_center[1])
    return (cosine, -sine, sine, cosine, dx, dy)


def _center(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def attach_approved_text_outlines(
    snapshot: Mapping[str, Any],
    drawings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Copy approved door-local text onto the export snapshot in sheet space.

    The source plan and the drawing documents are not modified. Unapproved text
    and reference images are omitted. The rings are not door contours.
    """

    attached = dict(snapshot)
    by_piece = {}
    for record in drawings:
        instance = str(record.get("piece_instance_id") or "")
        document = record.get("drawing_json")
        if not instance or not isinstance(document, Mapping):
            document = record.get("document") if isinstance(record.get("document"), Mapping) else document
        if instance and isinstance(document, Mapping):
            by_piece[instance] = document
    sheets = []
    for sheet in attached.get("sheets") or []:
        if not isinstance(sheet, Mapping):
            sheets.append(sheet)
            continue
        pieces = []
        for piece in sheet.get("pieces") or []:
            if not isinstance(piece, Mapping):
                pieces.append(piece)
                continue
            row = dict(piece)
            row.pop("approved_text_outlines", None)
            document = by_piece.get(str(piece.get("piece_instance_id") or ""))
            geometry = piece.get("geometry") if isinstance(piece.get("geometry"), Mapping) else None
            outer = geometry.get("outer") if isinstance(geometry, Mapping) else None
            if document is not None and isinstance(outer, list) and len(outer) >= 3:
                compiled = compile_manufacturing_geometry(
                    document,
                    blank_width_mm=float(piece.get("original_w") or piece.get("w") or 0) * 10.0,
                    blank_length_mm=float(piece.get("original_h") or piece.get("h") or 0) * 10.0,
                )
                door_outer = (
                    [(float(point[0]) * 10.0, float(point[1]) * 10.0) for point in compiled["geometry"]["points"]]
                    if compiled.get("status") == "ready"
                    else []
                )
                rings = approved_text_rings(document)
                if rings and len(door_outer) == len(outer):
                    row["approved_text_outlines"] = pose_door_rings_to_sheet(rings, door_outer, outer)
            pieces.append(row)
        copied = dict(sheet)
        copied["pieces"] = pieces
        sheets.append(copied)
    attached["sheets"] = sheets
    return attached


def pose_rings_once(
    rings: Sequence[Sequence[Sequence[float]]],
    pivot: Mapping[str, float] | Sequence[float],
    rotation_deg: float,
    dx_mm: float = 0.0,
    dy_mm: float = 0.0,
) -> list[list[tuple[float, float]]]:
    """Apply a door pose to stored door-local rings. Repeating it needs the source rings."""

    posed: list[list[tuple[float, float]]] = []
    for ring in rings:
        turned = [rotate_point((float(point[0]), float(point[1])), pivot, rotation_deg) for point in ring]
        posed.append([(point[0] + dx_mm, point[1] + dy_mm) for point in turned])
    return posed


def write_text_outline_dxf(document: Mapping[str, Any], *, pose: Mapping[str, Any] | None = None) -> str:
    """DXF with TEXT_OUTLINE only. GEOMETRY and CUT_PATH are not written."""

    rings = approved_text_rings(document)
    if pose:
        rings = pose_rings_once(
            rings,
            pose.get("pivot") or {"x": 0, "y": 0},
            float(pose.get("rotation_deg") or 0),
            float(pose.get("dx_mm") or 0),
            float(pose.get("dy_mm") or 0),
        )
    return _dxf(rings)


def _shape_runs(text: str, direction: str, weight: float) -> list[dict[str, float]]:
    runs = _visual_runs(text, direction)
    glyphs: list[dict[str, float]] = []
    for run, rtl in runs:
        glyphs.extend(_hb_shape(run, rtl, weight))
    if not glyphs:
        raise TextGeometryError("text_empty")
    return glyphs


def _visual_runs(text: str, direction: str) -> list[tuple[str, bool]]:
    kinds = [_char_dir(char) for char in text]
    if direction == "rtl":
        base = "R"
    elif direction == "ltr":
        base = "L"
    else:
        base = next((kind for kind in kinds if kind in {"L", "R"}), "L")
    resolved: list[str] = []
    for index, kind in enumerate(kinds):
        if kind in {"L", "R"}:
            resolved.append(kind)
            continue
        previous = next((item for item in reversed(resolved) if item in {"L", "R"}), base)
        following = next((item for item in kinds[index + 1 :] if item in {"L", "R"}), base)
        resolved.append(previous if previous == following else base)
    runs: list[tuple[str, bool]] = []
    cursor = 0
    while cursor < len(text):
        kind = resolved[cursor]
        end = cursor + 1
        while end < len(text) and resolved[end] == kind:
            end += 1
        runs.append((text[cursor:end], kind == "R"))
        cursor = end
    if base == "R":
        runs.reverse()
    return [(run, rtl) for run, rtl in runs if run]


def _char_dir(char: str) -> str:
    kind = unicodedata.bidirectional(char)
    if kind in {"R", "AL"}:
        return "R"
    if kind == "L":
        return "L"
    return "N"


def _hb_shape(text: str, rtl: bool, weight: float) -> list[dict[str, float]]:
    lib, font = _hb_font(weight)
    buffer = lib.hb_buffer_create()
    try:
        encoded = text.encode("utf-8")
        lib.hb_buffer_add_utf8(buffer, encoded, len(encoded), 0, len(encoded))
        lib.hb_buffer_guess_segment_properties(buffer)
        lib.hb_buffer_set_direction(buffer, 5 if rtl else 4)
        lib.hb_shape(font, buffer, None, 0)
        count = lib.hb_buffer_get_length(buffer)
        length = ctypes.c_uint(count)
        infos = lib.hb_buffer_get_glyph_infos(buffer, ctypes.byref(length))
        positions = lib.hb_buffer_get_glyph_positions(buffer, ctypes.byref(length))
        return [
            {
                "gid": int(infos[index].codepoint),
                "advance": float(positions[index].x_advance),
                "dx": float(positions[index].x_offset),
                "dy": float(positions[index].y_offset),
            }
            for index in range(count)
            if infos[index].codepoint
        ]
    finally:
        lib.hb_buffer_destroy(buffer)


def _glyph_contours(glyphset: Any, name: str, error: float) -> list[list[tuple[float, float]]]:
    """Walk one decomposed glyph. Off-curve points stay controls, never corners."""

    if name not in glyphset:
        raise TextGeometryError("font_unavailable")
    pen = DecomposingRecordingPen(glyphset)
    glyphset[name].draw(pen)
    contours: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for operator, args in pen.value:
        if operator == "moveTo":
            _store_contour(contours, current, error)
            current = [_point(args[0])]
        elif operator == "lineTo":
            current.append(_point(args[0]))
        elif operator == "curveTo":
            if not current:
                raise TextGeometryError("text_geometry_invalid")
            current.extend(_cubic(current[-1], _point(args[0]), _point(args[1]), _point(args[2]), error))
        elif operator == "qCurveTo":
            if not current:
                raise TextGeometryError("text_geometry_invalid")
            current.extend(_quadratic_chain(current[-1], args, error))
        elif operator in {"closePath", "endPath"}:
            _store_contour(contours, current, error)
            current = []
    _store_contour(contours, current, error)
    return contours


def _store_contour(
    contours: list[list[tuple[float, float]]],
    current: list[tuple[float, float]],
    error: float,
) -> None:
    if len(current) < 3:
        return
    ring = list(current)
    if math.dist(ring[0], ring[-1]) <= max(error, 1e-6):
        ring.pop()
    if len(ring) >= 3:
        contours.append(ring)


def _point(value: Sequence[float]) -> tuple[float, float]:
    return (float(value[0]), float(value[1]))


def _quadratic_chain(
    start: tuple[float, float],
    points: Sequence[Any],
    error: float,
) -> list[tuple[float, float]]:
    """TrueType quadratic chain. The last point is on-curve, or None when implied."""

    raw = list(points)
    if raw and raw[-1] is None:
        if len(raw) < 2:
            return []
        last_x, last_y = raw[-2]
        first_x, first_y = raw[0]
        implied = ((last_x + first_x) / 2.0, (last_y + first_y) / 2.0)
        raw = raw[:-1] + [implied]
    if len(raw) == 1:
        return [_point(raw[0])]
    produced: list[tuple[float, float]] = []
    cursor = start
    for control, destination in decomposeQuadraticSegment(tuple(raw)):
        produced.extend(_quadratic(cursor, _point(control), _point(destination), error))
        cursor = _point(destination)
    return produced


def _cubic(p0, p1, p2, p3, error) -> list[tuple[float, float]]:
    return _subdivide(lambda t: _bezier(p0, p1, p2, p3, t), error)[1:]


def _quadratic(p0, p1, p2, error) -> list[tuple[float, float]]:
    def at(t: float) -> tuple[float, float]:
        u = 1.0 - t
        return (
            u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
        )
    return _subdivide(at, error)[1:]


def _bezier(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1.0 - t
    return (
        u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
        u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
    )


def _subdivide(at, error: float) -> list[tuple[float, float]]:
    points = [at(0.0)]

    def walk(a: float, b: float, depth: int) -> None:
        mid = (a + b) / 2.0
        left, right, center = at(a), at(b), at(mid)
        chord = math.dist(left, right)
        if depth >= 16 or (chord > 0 and _distance_to_chord(center, left, right) <= error):
            points.append(right)
            return
        walk(a, mid, depth + 1)
        walk(mid, b, depth + 1)

    walk(0.0, 1.0, 0)
    return points


def _distance_to_chord(point, start, end) -> float:
    length = math.dist(start, end)
    if length == 0:
        return math.dist(point, start)
    area = abs(
        (end[0] - start[0]) * (start[1] - point[1])
        - (start[0] - point[0]) * (end[1] - start[1])
    )
    return area / length


def _limit_rings(rings: Sequence[Sequence[tuple[float, float]]]) -> None:
    if len(rings) > MAX_TEXT_RINGS:
        raise TextGeometryError("text_too_complex")
    total = 0
    for ring in rings:
        if len(ring) > MAX_POINTS_PER_RING:
            raise TextGeometryError("text_too_complex")
        total += len(ring)
    if total > MAX_TEXT_POINTS:
        raise TextGeometryError("text_too_complex")


def _closed_valid(ring: Sequence[tuple[float, float]]) -> bool:
    if len(ring) < 3:
        return False
    area = 0.0
    for index, point in enumerate(ring):
        nxt = ring[(index + 1) % len(ring)]
        if not all(math.isfinite(value) for value in point + nxt):
            return False
        area += point[0] * nxt[1] - nxt[0] * point[1]
    return abs(area) > 1e-6


def _strictly_inside(ring: Sequence[tuple[float, float]], outer: Sequence[tuple[float, float]]) -> bool:
    return all(_contains(outer, point) for point in ring)


def _contains(outer: Sequence[tuple[float, float]], point: tuple[float, float]) -> bool:
    inside = False
    j = len(outer) - 1
    for i, current in enumerate(outer):
        other = outer[j]
        crosses = (current[1] > point[1]) != (other[1] > point[1])
        if crosses:
            x_at = (other[0] - current[0]) * (point[1] - current[1]) / (other[1] - current[1]) + current[0]
            if point[0] < x_at:
                inside = not inside
        j = i
    return inside


def _rings_touch(ring: Sequence[tuple[float, float]], outer: Sequence[tuple[float, float]]) -> bool:
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        for other_index, other_start in enumerate(outer):
            other_end = outer[(other_index + 1) % len(outer)]
            if _segments_cross(start, end, other_start, other_end):
                return True
    return False


def _segments_cross(a, b, c, d) -> bool:
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    ab_c, ab_d = side(a, b, c), side(a, b, d)
    cd_a, cd_b = side(c, d, a), side(c, d, b)
    return ab_c * ab_d < 0 and cd_a * cd_b < 0


def _ring(points: Sequence[Any]) -> list[tuple[float, float]]:
    ring = []
    for point in points:
        if isinstance(point, Mapping):
            ring.append((float(point["x_mm"]), float(point["y_mm"])))
        else:
            ring.append((float(point[0]), float(point[1])))
    return ring


def _plain_text(value: Any) -> str:
    if not isinstance(value, str):
        raise TextGeometryError("invalid_text")
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise TextGeometryError("text_empty")
    if len(text) > MAX_TEXT_CHARS:
        raise TextGeometryError("text_too_long")
    if any(char in text for char in "<>{}\\&") or any(unicodedata.category(char).startswith("C") and char != "\n" for char in text):
        raise TextGeometryError("invalid_text")
    return text


def _dxf(rings: Sequence[Sequence[tuple[float, float]]]) -> str:
    import io

    import ezdxf

    document = ezdxf.new("R2010")
    document.layers.add(TEXT_OUTLINE_LAYER, color=30)
    model = document.modelspace()
    for ring in rings:
        model.add_lwpolyline(ring, close=True, dxfattribs={"layer": TEXT_OUTLINE_LAYER})
    stream = io.StringIO()
    document.write(stream)
    return stream.getvalue()


def _tag(value: str) -> int:
    raw = value.encode("ascii")[:4].ljust(4, b" ")
    return (raw[0] << 24) | (raw[1] << 16) | (raw[2] << 8) | raw[3]


@lru_cache(maxsize=2)
def _font_instance(weight: float):
    source = TTFont(_FONT_FILE)
    instance = instantiateVariableFont(source, {"wght": weight}, inplace=False)
    return instance, instance.getGlyphOrder()


@lru_cache(maxsize=2)
def _hb_font(weight: float):
    lib = ctypes.CDLL(_HB)
    lib.hb_blob_create_from_file.argtypes = [ctypes.c_char_p]
    lib.hb_blob_create_from_file.restype = ctypes.c_void_p
    lib.hb_face_create.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    lib.hb_face_create.restype = ctypes.c_void_p
    lib.hb_font_create.argtypes = [ctypes.c_void_p]
    lib.hb_font_create.restype = ctypes.c_void_p
    lib.hb_ot_font_set_funcs.argtypes = [ctypes.c_void_p]
    lib.hb_font_set_scale.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.hb_font_set_variations.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Variation), ctypes.c_uint]
    lib.hb_buffer_create.restype = ctypes.c_void_p
    lib.hb_buffer_add_utf8.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_uint, ctypes.c_int]
    lib.hb_buffer_guess_segment_properties.argtypes = [ctypes.c_void_p]
    lib.hb_buffer_set_direction.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.hb_buffer_set_script.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    lib.hb_buffer_set_language.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.hb_language_from_string.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.hb_language_from_string.restype = ctypes.c_void_p
    lib.hb_shape.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    lib.hb_buffer_get_length.argtypes = [ctypes.c_void_p]
    lib.hb_buffer_get_length.restype = ctypes.c_uint
    lib.hb_buffer_get_glyph_infos.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    lib.hb_buffer_get_glyph_infos.restype = ctypes.POINTER(_Info)
    lib.hb_buffer_get_glyph_positions.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    lib.hb_buffer_get_glyph_positions.restype = ctypes.POINTER(_Pos)
    lib.hb_buffer_destroy.argtypes = [ctypes.c_void_p]
    blob = lib.hb_blob_create_from_file(str(_FONT_FILE).encode())
    face = lib.hb_face_create(blob, 0)
    font = lib.hb_font_create(face)
    lib.hb_ot_font_set_funcs(font)
    lib.hb_font_set_scale(font, 1000, 1000)
    variation = _Variation(_tag("wght"), float(weight))
    lib.hb_font_set_variations(font, ctypes.byref(variation), 1)
    return lib, font

