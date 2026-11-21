"""Structural contract for a Board Editor vector drawing.

This document is not a Cutting Plan, not a DXF snapshot, and not special-shape
documentation. It records door-local drawing data that later phases may store
beside a board-editor draft. It does not authorize manufacturing geometry.

Coordinate contract:
- Origin is the top-left of the piece blank.
- +X points right and +Y points down, in millimetres.
- Board pose (translation, rotation, flip) is not baked into these coordinates.

Ownership of ``piece_instance_id`` and agreement between ``blank`` and the
trusted plan are server integration checks. This module only checks structure.

A document can be structurally valid and still be unfit to cut. Open paths,
curves, holes, annotations, and reference images are accepted here and are not
promoted to a manufacturing contour.

Segment length and angle are not stored. Line metrics are derived from node
coordinates so a stored length cannot disagree with the geometry.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

SCHEMA = "almdina.board-editor-drawing"
VERSION = 1
UNITS = "mm"
COORDINATE_SPACE = "door_local"
QUANTUM_MM = Decimal("0.001")

MAX_ABS_MM = 100_000.0
MAX_BLANK_MM = 20_000.0
MAX_ABS_DEG = 3600.0
MAX_DOCUMENT_UTF8_BYTES = 1_000_000
MAX_PATHS = 256
MAX_SHAPES = 128
MAX_REFERENCES = 32
MAX_TEXTS = 32
MAX_NODES = 12_000
MAX_SEGMENTS = 12_000
MAX_NODES_PER_PATH = 4_000
MAX_TEMPLATE_PARAMS = 32
MAX_ID_LENGTH = 80
MAX_FILE_ID_LENGTH = 180
MAX_TEMPLATE_ID_LENGTH = 80
MIN_POLYGON_SIDES = 3
MAX_POLYGON_SIDES = 360

ROLE_MANUFACTURING_OUTER = "manufacturing_outer"
ROLE_MANUFACTURING_HOLE = "manufacturing_hole"
ROLE_CONSTRUCTION = "construction"
ROLE_ANNOTATION = "annotation"
ROLES = frozenset(
    {
        ROLE_MANUFACTURING_OUTER,
        ROLE_MANUFACTURING_HOLE,
        ROLE_CONSTRUCTION,
        ROLE_ANNOTATION,
    }
)
# Roles that may later be offered to a manufacturing compiler.
# Presence in a saved document does not make the path manufacturable.
MANUFACTURING_ROLES = frozenset(
    {ROLE_MANUFACTURING_OUTER, ROLE_MANUFACTURING_HOLE}
)

SEGMENT_LINE = "line"
SEGMENT_ARC = "arc"
SEGMENT_BEZIER = "bezier"
SEGMENT_KINDS = frozenset({SEGMENT_LINE, SEGMENT_ARC, SEGMENT_BEZIER})

SHAPE_RECTANGLE = "rectangle"
SHAPE_CIRCLE = "circle"
SHAPE_ELLIPSE = "ellipse"
SHAPE_ARC = "arc"
SHAPE_POLYGON = "polygon"
SHAPE_TRAPEZOID = "trapezoid"
SHAPE_L = "l_shape"
SHAPE_CLIPPED_CORNER = "clipped_corner"
SHAPE_CUSTOM = "custom_template"
SHAPE_KINDS = frozenset(
    {
        SHAPE_RECTANGLE,
        SHAPE_CIRCLE,
        SHAPE_ELLIPSE,
        SHAPE_ARC,
        SHAPE_POLYGON,
        SHAPE_TRAPEZOID,
        SHAPE_L,
        SHAPE_CLIPPED_CORNER,
        SHAPE_CUSTOM,
    }
)
CLIPPED_CORNERS = frozenset(
    {"top_left", "top_right", "bottom_left", "bottom_right"}
)
_OPTIONAL_SHAPE_ROTATION = frozenset(
    {SHAPE_ARC, SHAPE_TRAPEZOID, SHAPE_L, SHAPE_CLIPPED_CORNER}
)

TOP_FIELDS = frozenset(
    {
        "schema",
        "version",
        "units",
        "coordinate_space",
        "piece_instance_id",
        "blank",
        "paths",
        "shapes",
        "references",
        "texts",
    }
)
BLANK_FIELDS = frozenset({"width_mm", "length_mm"})
PATH_FIELDS = frozenset(
    {"id", "role", "closed", "nodes", "segments", "source_shape_id", "rotation_deg"}
)
NODE_FIELDS = frozenset({"id", "x_mm", "y_mm"})
LINE_FIELDS = frozenset({"id", "kind", "from_node", "to_node"})
ARC_FIELDS = LINE_FIELDS | frozenset(
    {"radius_mm", "large_arc", "sweep_clockwise"}
)
BEZIER_FIELDS = LINE_FIELDS | frozenset({"controls"})
CONTROL_FIELDS = frozenset({"x_mm", "y_mm"})
SHAPE_FIELDS = frozenset({"id", "kind", "exploded", "path_id", "params"})
REFERENCE_FIELDS = frozenset(
    {
        "id",
        "file_id",
        "x_mm",
        "y_mm",
        "width_mm",
        "height_mm",
        "rotation_deg",
        "opacity",
        "locked",
        "hidden",
        "calibration",
    }
)
CALIBRATION_FIELDS = frozenset({"start_mm", "end_mm", "known_distance_mm"})
EMBEDDED_IMAGE_FIELDS = frozenset(
    {
        "content",
        "content_base64",
        "data_base64",
        "base64",
        "bytes",
        "blob",
        "data_url",
        "image_data",
        "svg",
    }
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_TEMPLATE_PARAM_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_GEOMETRY_KEYS = frozenset(
    {"schema", "version", "units", "coordinate_space", "piece_instance_id", "blank", "paths", "shapes"}
)


class DrawingDocumentError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def empty_document(
    piece_instance_id: str,
    blank_width_mm: float,
    blank_length_mm: float,
) -> dict[str, Any]:
    """Return one normalized empty drawing for a known piece blank."""

    return normalize_document(
        {
            "schema": SCHEMA,
            "version": VERSION,
            "units": UNITS,
            "coordinate_space": COORDINATE_SPACE,
            "piece_instance_id": piece_instance_id,
            "blank": {"width_mm": blank_width_mm, "length_mm": blank_length_mm},
            "paths": [],
            "shapes": [],
            "references": [],
        }
    )


def parse_document(raw: str | Mapping[str, Any]) -> dict[str, Any]:
    """Parse JSON text or a mapping and return the normalized document."""

    if isinstance(raw, str):
        encoded = raw.encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_UTF8_BYTES:
            raise DrawingDocumentError("document_too_large")
        try:
            loaded = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise DrawingDocumentError("invalid_document") from exc
    elif isinstance(raw, Mapping):
        loaded = raw
    else:
        raise DrawingDocumentError("invalid_document")
    if not isinstance(loaded, Mapping):
        raise DrawingDocumentError("invalid_document")
    return normalize_document(loaded)


def normalize_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only the versioned drawing contract and quantize millimetres once."""

    if not isinstance(document, Mapping):
        raise DrawingDocumentError("invalid_document")
    _reject_unknown(document, TOP_FIELDS)
    _reject_embedded_image(document)
    if document.get("schema") != SCHEMA:
        raise DrawingDocumentError("unsupported_schema")
    if type(document.get("version")) is not int or document.get("version") != VERSION:
        raise DrawingDocumentError("unsupported_version")
    if document.get("units") != UNITS:
        raise DrawingDocumentError("invalid_units")
    if document.get("coordinate_space") != COORDINATE_SPACE:
        raise DrawingDocumentError("invalid_coordinate_space")

    piece_instance_id = _identifier(document.get("piece_instance_id"), code="invalid_id")
    blank = _blank(document.get("blank"))
    paths = _paths(document.get("paths"))
    shapes = _shapes(document.get("shapes"))
    references = _references(document.get("references"))
    texts = _texts(document["texts"]) if "texts" in document else None
    _assert_counts(paths, shapes, references, texts or [])
    _assert_unique_ids(paths, shapes, references, texts or [])
    _assert_shape_links(paths, shapes)

    normalized = {
        "schema": SCHEMA,
        "version": VERSION,
        "units": UNITS,
        "coordinate_space": COORDINATE_SPACE,
        "piece_instance_id": piece_instance_id,
        "blank": blank,
        "paths": paths,
        "shapes": shapes,
        "references": references,
    }
    if texts is not None:
        normalized["texts"] = texts
    if len(_dump(normalized).encode("utf-8")) > MAX_DOCUMENT_UTF8_BYTES:
        raise DrawingDocumentError("document_too_large")
    return normalized


def document_to_json(document: Mapping[str, Any]) -> str:
    """Serialize a document. Mapping key order does not matter."""

    return _dump(normalize_document(document))


def document_fingerprint(document: Mapping[str, Any]) -> str:
    """Stable hash of the whole drawing, including reference-image properties.

    Image bytes are not part of the document. Changing opacity, placement, or
    calibration still changes this fingerprint so an editor can detect unsaved
    work. This is not a manufacturing geometry identity.
    """

    normalized = normalize_document(document)
    return _sha256(document_to_json(normalized))


def geometry_fingerprint(document: Mapping[str, Any]) -> str:
    """Stable hash of piece, blank, paths, and shapes.

    Reference images are excluded. A future manufacturing compiler must use
    this identity, not the document fingerprint, when deciding whether cut
    geometry changed.
    """

    normalized = normalize_document(document)
    payload = {key: normalized[key] for key in sorted(_GEOMETRY_KEYS)}
    return _sha256(_dump(payload))


def line_length_mm(x1: float, y1: float, x2: float, y2: float) -> float:
    """Straight distance between two door-local points, after one quantization."""

    start_x = _quantize_mm(x1)
    start_y = _quantize_mm(y1)
    end_x = _quantize_mm(x2)
    end_y = _quantize_mm(y2)
    return float(math.hypot(end_x - start_x, end_y - start_y))


def line_angle_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    """Angle of a straight line in door-local space.

    0 degrees points to +X (right). 90 degrees points to +Y (down).
    The value is derived and must not be persisted on the segment.
    """

    start_x = _quantize_mm(x1)
    start_y = _quantize_mm(y1)
    end_x = _quantize_mm(x2)
    end_y = _quantize_mm(y2)
    return math.degrees(math.atan2(end_y - start_y, end_x - start_x))


def segment_line_metrics(
    document: Mapping[str, Any],
    path_id: str,
    segment_id: str,
) -> dict[str, float]:
    """Derive length and angle for one straight segment.

    Arc and Bézier segments do not report the chord as if it were the curve
    length. Callers receive ``segment_not_line`` for those kinds.
    """

    normalized = normalize_document(document)
    path = _find_by_id(normalized["paths"], path_id, code="unknown_path")
    segment = _find_by_id(path["segments"], segment_id, code="unknown_segment")
    if segment["kind"] != SEGMENT_LINE:
        raise DrawingDocumentError("segment_not_line")
    nodes = {node["id"]: node for node in path["nodes"]}
    start = nodes[segment["from_node"]]
    end = nodes[segment["to_node"]]
    return {
        "length_mm": line_length_mm(start["x_mm"], start["y_mm"], end["x_mm"], end["y_mm"]),
        "angle_deg": line_angle_deg(start["x_mm"], start["y_mm"], end["x_mm"], end["y_mm"]),
    }


def path_bounds_mm(document: Mapping[str, Any], path_id: str) -> dict[str, float]:
    """Axis-aligned bounds of a path made only of straight segments.

    Curve bounds are not guessed from endpoints. A path that contains an arc
    or Bézier raises ``bounds_require_lines``.
    """

    normalized = normalize_document(document)
    path = _find_by_id(normalized["paths"], path_id, code="unknown_path")
    if any(segment["kind"] != SEGMENT_LINE for segment in path["segments"]):
        raise DrawingDocumentError("bounds_require_lines")
    xs = [node["x_mm"] for node in path["nodes"]]
    ys = [node["y_mm"] for node in path["nodes"]]
    return {
        "min_x_mm": min(xs),
        "min_y_mm": min(ys),
        "max_x_mm": max(xs),
        "max_y_mm": max(ys),
    }


def _blank(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_blank")
    _reject_unknown(value, BLANK_FIELDS)
    width = _positive_mm(value.get("width_mm"), code="invalid_blank")
    length = _positive_mm(value.get("length_mm"), code="invalid_blank")
    if width > MAX_BLANK_MM or length > MAX_BLANK_MM:
        raise DrawingDocumentError("invalid_blank")
    return {"width_mm": width, "length_mm": length}


def _paths(value: Any) -> list[dict[str, Any]]:
    rows = _sequence(value, code="invalid_document")
    if len(rows) > MAX_PATHS:
        raise DrawingDocumentError("too_many_elements")
    return [_path(row) for row in rows]


def _path(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_document")
    _reject_unknown(value, PATH_FIELDS)
    _reject_embedded_image(value)
    role = value.get("role")
    if role not in ROLES:
        raise DrawingDocumentError("unknown_role")
    closed = _required_bool(value.get("closed"))
    nodes = _nodes(value.get("nodes"))
    segments = _segments(value.get("segments"), nodes)
    ordered_nodes, ordered_segments = _order_chain(nodes, segments, closed)
    source_shape_id = value.get("source_shape_id")
    if source_shape_id not in (None,):
        source_shape_id = _identifier(source_shape_id, code="invalid_id")
    path = {
        "id": _identifier(value.get("id"), code="invalid_id"),
        "role": role,
        "closed": closed,
        "nodes": ordered_nodes,
        "segments": ordered_segments,
        "source_shape_id": source_shape_id,
    }
    if "rotation_deg" in value and value.get("rotation_deg") not in (None, ""):
        rotation = _degrees(value.get("rotation_deg"), code="invalid_document")
        if rotation:
            path["rotation_deg"] = rotation
    return path


def _nodes(value: Any) -> list[dict[str, Any]]:
    rows = _sequence(value, code="invalid_document")
    if not rows or len(rows) > MAX_NODES_PER_PATH:
        raise DrawingDocumentError("too_many_elements" if len(rows) > MAX_NODES_PER_PATH else "inconsistent_path")
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise DrawingDocumentError("invalid_document")
        _reject_unknown(row, NODE_FIELDS)
        node_id = _identifier(row.get("id"), code="invalid_id")
        if node_id in seen:
            raise DrawingDocumentError("duplicate_id")
        seen.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "x_mm": _mm(row.get("x_mm")),
                "y_mm": _mm(row.get("y_mm")),
            }
        )
    return nodes


def _segments(value: Any, nodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = _sequence(value, code="invalid_document")
    if not rows:
        raise DrawingDocumentError("inconsistent_path")
    known = {str(node["id"]) for node in nodes}
    segments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        segment = _segment(row, known)
        if segment["id"] in seen:
            raise DrawingDocumentError("duplicate_id")
        seen.add(segment["id"])
        segments.append(segment)
    return segments


def _segment(value: Any, known_nodes: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_document")
    _reject_embedded_image(value)
    kind = value.get("kind")
    if kind not in SEGMENT_KINDS:
        raise DrawingDocumentError("unknown_segment_kind")
    allowed = {
        SEGMENT_LINE: LINE_FIELDS,
        SEGMENT_ARC: ARC_FIELDS,
        SEGMENT_BEZIER: BEZIER_FIELDS,
    }[kind]
    _reject_unknown(value, allowed)
    start = _identifier(value.get("from_node"), code="invalid_id")
    end = _identifier(value.get("to_node"), code="invalid_id")
    if start not in known_nodes or end not in known_nodes:
        raise DrawingDocumentError("unknown_node")
    if start == end:
        raise DrawingDocumentError("inconsistent_path")
    segment: dict[str, Any] = {
        "id": _identifier(value.get("id"), code="invalid_id"),
        "kind": kind,
        "from_node": start,
        "to_node": end,
    }
    if kind == SEGMENT_ARC:
        segment["radius_mm"] = _positive_mm(value.get("radius_mm"), code="curve_incomplete")
        segment["large_arc"] = _required_bool(value.get("large_arc"), code="curve_incomplete")
        segment["sweep_clockwise"] = _required_bool(
            value.get("sweep_clockwise"),
            code="curve_incomplete",
        )
    elif kind == SEGMENT_BEZIER:
        segment["controls"] = _bezier_controls(value.get("controls"))
    return segment


def _order_chain(
    nodes: Sequence[Mapping[str, Any]],
    segments: Sequence[Mapping[str, Any]],
    closed: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {str(node["id"]): dict(node) for node in nodes}
    outgoing: dict[str, dict[str, Any]] = {}
    incoming = {node_id: 0 for node_id in by_id}
    node_lookup = {str(node["id"]): node for node in nodes}
    normalized_segments: list[dict[str, Any]] = []
    for raw in segments:
        segment = dict(raw)
        if segment["kind"] == SEGMENT_ARC:
            _assert_arc_radius(node_lookup, segment)
        if segment["from_node"] in outgoing:
            raise DrawingDocumentError("inconsistent_path")
        outgoing[segment["from_node"]] = segment
        incoming[segment["to_node"]] += 1
        if incoming[segment["to_node"]] > 1:
            raise DrawingDocumentError("inconsistent_path")
        normalized_segments.append(segment)

    forms_cycle = (
        len(normalized_segments) == len(nodes)
        and all(count == 1 for count in incoming.values())
        and all(node_id in outgoing for node_id in by_id)
    )
    if closed:
        if not forms_cycle:
            raise DrawingDocumentError("inconsistent_closure")
        start_id = str(nodes[0]["id"])
    else:
        if forms_cycle:
            raise DrawingDocumentError("inconsistent_closure")
        if len(normalized_segments) != len(nodes) - 1:
            raise DrawingDocumentError("inconsistent_path")
        starts = [node_id for node_id, count in incoming.items() if count == 0]
        ends = [node_id for node_id in by_id if node_id not in outgoing]
        if len(starts) != 1 or len(ends) != 1:
            raise DrawingDocumentError("inconsistent_path")
        start_id = starts[0]

    ordered_nodes: list[dict[str, Any]] = []
    ordered_segments: list[dict[str, Any]] = []
    cursor = start_id
    seen: set[str] = set()
    for _ in range(len(normalized_segments)):
        if cursor in seen or cursor not in outgoing:
            raise DrawingDocumentError("inconsistent_closure" if closed else "inconsistent_path")
        seen.add(cursor)
        ordered_nodes.append(by_id[cursor])
        segment = outgoing[cursor]
        ordered_segments.append(segment)
        cursor = str(segment["to_node"])
    if closed:
        if cursor != start_id or len(seen) != len(nodes):
            raise DrawingDocumentError("inconsistent_closure")
    else:
        if cursor in seen or cursor not in by_id:
            raise DrawingDocumentError("inconsistent_closure" if cursor in seen else "inconsistent_path")
        ordered_nodes.append(by_id[cursor])
        if len(ordered_nodes) != len(nodes):
            raise DrawingDocumentError("inconsistent_path")
    return ordered_nodes, ordered_segments


def _assert_arc_radius(nodes: Mapping[str, Mapping[str, Any]], segment: Mapping[str, Any]) -> None:
    start = nodes[str(segment["from_node"])]
    end = nodes[str(segment["to_node"])]
    chord = math.hypot(
        float(end["x_mm"]) - float(start["x_mm"]),
        float(end["y_mm"]) - float(start["y_mm"]),
    )
    radius = float(segment["radius_mm"])
    if radius + 1e-9 < (chord / 2.0):
        raise DrawingDocumentError("curve_inconsistent")


def _bezier_controls(value: Any) -> list[dict[str, float]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DrawingDocumentError("curve_incomplete")
    if len(value) != 2:
        raise DrawingDocumentError("curve_incomplete")
    controls: list[dict[str, float]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise DrawingDocumentError("curve_incomplete")
        _reject_unknown(row, CONTROL_FIELDS)
        controls.append({"x_mm": _mm(row.get("x_mm")), "y_mm": _mm(row.get("y_mm"))})
    return controls


def _shapes(value: Any) -> list[dict[str, Any]]:
    rows = _sequence(value, code="invalid_document")
    if len(rows) > MAX_SHAPES:
        raise DrawingDocumentError("too_many_elements")
    return [_shape(row) for row in rows]


def _shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_shape")
    _reject_unknown(value, SHAPE_FIELDS)
    kind = value.get("kind")
    if kind not in SHAPE_KINDS:
        raise DrawingDocumentError("unknown_shape_kind")
    exploded = _required_bool(value.get("exploded"), code="invalid_shape")
    path_id = value.get("path_id")
    if exploded:
        path_id = _identifier(path_id, code="invalid_shape")
    elif path_id not in (None,):
        raise DrawingDocumentError("invalid_shape")
    else:
        path_id = None
    return {
        "id": _identifier(value.get("id"), code="invalid_id"),
        "kind": kind,
        "exploded": exploded,
        "path_id": path_id,
        "params": _shape_params(kind, value.get("params")),
    }


def _shape_params(kind: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_shape")
    specs: dict[str, tuple[str, ...]] = {
        SHAPE_RECTANGLE: ("x_mm", "y_mm", "width_mm", "height_mm", "rotation_deg"),
        SHAPE_CIRCLE: ("cx_mm", "cy_mm", "radius_mm"),
        SHAPE_ELLIPSE: ("cx_mm", "cy_mm", "rx_mm", "ry_mm", "rotation_deg"),
        SHAPE_ARC: ("cx_mm", "cy_mm", "radius_mm", "start_angle_deg", "sweep_angle_deg", "rotation_deg"),
        SHAPE_POLYGON: ("cx_mm", "cy_mm", "radius_mm", "sides", "rotation_deg"),
        SHAPE_TRAPEZOID: ("x_mm", "y_mm", "bottom_width_mm", "top_width_mm", "height_mm", "rotation_deg"),
        SHAPE_L: (
            "x_mm",
            "y_mm",
            "width_mm",
            "height_mm",
            "notch_width_mm",
            "notch_height_mm",
            "rotation_deg",
        ),
        SHAPE_CLIPPED_CORNER: (
            "x_mm",
            "y_mm",
            "width_mm",
            "height_mm",
            "cut_width_mm",
            "cut_height_mm",
            "corner",
            "rotation_deg",
        ),
    }
    if kind == SHAPE_CUSTOM:
        return _custom_template_params(value)
    allowed = specs[kind]
    present = dict(value)
    if kind in _OPTIONAL_SHAPE_ROTATION and "rotation_deg" not in present:
        present["rotation_deg"] = 0
    _reject_unknown(present, set(allowed))
    if set(present) != set(allowed):
        raise DrawingDocumentError("invalid_shape")
    params = {key: _param_value(kind, key, present.get(key)) for key in allowed}
    _assert_shape_relationships(kind, params)
    normalized = {key: params[key] for key in allowed}
    if kind in _OPTIONAL_SHAPE_ROTATION and not normalized["rotation_deg"]:
        normalized.pop("rotation_deg")
    return normalized


def _param_value(kind: str, key: str, value: Any) -> Any:
    if key == "sides":
        if type(value) is not int or isinstance(value, bool):
            raise DrawingDocumentError("invalid_shape")
        if value < MIN_POLYGON_SIDES or value > MAX_POLYGON_SIDES:
            raise DrawingDocumentError("invalid_shape")
        return value
    if key == "corner":
        if value not in CLIPPED_CORNERS:
            raise DrawingDocumentError("invalid_shape")
        return value
    if key.endswith("_deg"):
        return _degrees(value, code="invalid_shape")
    if key in {"width_mm", "height_mm", "radius_mm", "rx_mm", "ry_mm", "bottom_width_mm", "top_width_mm"}:
        return _positive_mm(value, code="invalid_shape")
    if key in {"notch_width_mm", "notch_height_mm", "cut_width_mm", "cut_height_mm"}:
        return _positive_mm(value, code="invalid_shape")
    return _mm(value, code="invalid_shape")


def _assert_shape_relationships(kind: str, params: Mapping[str, Any]) -> None:
    if kind == SHAPE_ARC and abs(float(params["sweep_angle_deg"])) <= 1e-9:
        raise DrawingDocumentError("invalid_shape")
    if kind == SHAPE_L:
        if params["notch_width_mm"] >= params["width_mm"] or params["notch_height_mm"] >= params["height_mm"]:
            raise DrawingDocumentError("invalid_shape")
    if kind == SHAPE_CLIPPED_CORNER:
        if params["cut_width_mm"] >= params["width_mm"] or params["cut_height_mm"] >= params["height_mm"]:
            raise DrawingDocumentError("invalid_shape")


def _custom_template_params(value: Mapping[str, Any]) -> dict[str, Any]:
    _reject_unknown(value, {"template_id", "x_mm", "y_mm", "params"})
    if set(value) != {"template_id", "x_mm", "y_mm", "params"}:
        raise DrawingDocumentError("invalid_shape")
    template_id = value.get("template_id")
    if not isinstance(template_id, str) or not _ID_RE.fullmatch(template_id):
        raise DrawingDocumentError("invalid_shape")
    if len(template_id) > MAX_TEMPLATE_ID_LENGTH:
        raise DrawingDocumentError("invalid_shape")
    raw_params = value.get("params")
    if not isinstance(raw_params, Mapping) or len(raw_params) > MAX_TEMPLATE_PARAMS:
        raise DrawingDocumentError("invalid_shape")
    params: dict[str, float] = {}
    for key in sorted(raw_params):
        if not isinstance(key, str) or not _TEMPLATE_PARAM_RE.fullmatch(key):
            raise DrawingDocumentError("invalid_shape")
        params[key] = _mm(raw_params[key], code="invalid_shape")
    return {
        "template_id": template_id,
        "x_mm": _mm(value.get("x_mm"), code="invalid_shape"),
        "y_mm": _mm(value.get("y_mm"), code="invalid_shape"),
        "params": params,
    }


TEXT_ROLE = "manufacturing_text"
TEXT_STATES = frozenset({"editable", "vector"})
TEXT_WEIGHTS = frozenset({"regular", "bold"})
TEXT_DIRECTIONS = frozenset({"auto", "rtl", "ltr"})
TEXT_ALIGNS = frozenset({"left", "center", "right"})
TEXT_FIELDS = frozenset(
    {
        "id",
        "role",
        "text",
        "font_id",
        "font_version",
        "font_size_mm",
        "font_weight",
        "direction",
        "align",
        "x_mm",
        "y_mm",
        "rotation_deg",
        "aspect_locked",
        "state",
        "export_approved",
        "outlines",
    }
)
OUTLINE_FIELDS = frozenset({"id", "points"})
_TEXT_CONTENT_RE = re.compile(r"^[^<>{}\\&\x00-\x08\x0b\x0c\x0e-\x1f]{1,80}$")


def _texts(value: Any) -> list[dict[str, Any]]:
    rows = _sequence(value, code="invalid_document")
    if len(rows) > MAX_TEXTS:
        raise DrawingDocumentError("too_many_elements")
    return [_text(row) for row in rows]


def _text(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_text")
    _reject_unknown(value, TEXT_FIELDS)
    _reject_embedded_image(value)
    if set(value) != TEXT_FIELDS:
        raise DrawingDocumentError("invalid_text")
    content = value.get("text")
    if not isinstance(content, str) or not _TEXT_CONTENT_RE.fullmatch(content) or not content.strip():
        raise DrawingDocumentError("invalid_text")
    if value.get("role") != TEXT_ROLE:
        raise DrawingDocumentError("invalid_text")
    state = value.get("state")
    if state not in TEXT_STATES:
        raise DrawingDocumentError("invalid_text")
    approved = _required_bool(value.get("export_approved"), code="invalid_text")
    if approved and state != "vector":
        raise DrawingDocumentError("invalid_text")
    weight = value.get("font_weight")
    direction = value.get("direction")
    align = value.get("align")
    if weight not in TEXT_WEIGHTS or direction not in TEXT_DIRECTIONS or align not in TEXT_ALIGNS:
        raise DrawingDocumentError("invalid_text")
    font_id = value.get("font_id")
    font_version = value.get("font_version")
    if font_id != "noto-naskh-arabic" or font_version != "1":
        raise DrawingDocumentError("font_unavailable")
    return {
        "id": _identifier(value.get("id"), code="invalid_id"),
        "role": TEXT_ROLE,
        "text": content,
        "font_id": font_id,
        "font_version": font_version,
        "font_size_mm": _positive_mm(value.get("font_size_mm"), code="invalid_text"),
        "font_weight": weight,
        "direction": direction,
        "align": align,
        "x_mm": _mm(value.get("x_mm"), code="invalid_text"),
        "y_mm": _mm(value.get("y_mm"), code="invalid_text"),
        "rotation_deg": _degrees(value.get("rotation_deg"), code="invalid_text"),
        "aspect_locked": _required_bool(value.get("aspect_locked"), code="invalid_text"),
        "state": state,
        "export_approved": approved,
        "outlines": _outlines(value.get("outlines")),
    }


def _outlines(value: Any) -> list[dict[str, Any]]:
    rows = _sequence(value, code="invalid_text")
    outlines = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != OUTLINE_FIELDS:
            raise DrawingDocumentError("invalid_text")
        points = []
        raw_points = row.get("points")
        if isinstance(raw_points, (str, bytes)) or not isinstance(raw_points, Sequence) or len(raw_points) < 3:
            raise DrawingDocumentError("invalid_text")
        for point in raw_points:
            if not isinstance(point, Mapping) or set(point) != CONTROL_FIELDS:
                raise DrawingDocumentError("invalid_text")
            points.append({
                "x_mm": _mm(point.get("x_mm"), code="invalid_text"),
                "y_mm": _mm(point.get("y_mm"), code="invalid_text"),
            })
        outlines.append({"id": _identifier(row.get("id"), code="invalid_id"), "points": points})
    return outlines


def _references(value: Any) -> list[dict[str, Any]]:
    rows = _sequence(value, code="invalid_document")
    if len(rows) > MAX_REFERENCES:
        raise DrawingDocumentError("too_many_elements")
    return [_reference(row) for row in rows]


def _reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_reference")
    _reject_embedded_image(value)
    _reject_unknown(value, REFERENCE_FIELDS)
    required = REFERENCE_FIELDS - {"calibration"}
    if not required <= set(value):
        raise DrawingDocumentError("invalid_reference")
    file_id = _file_id(value.get("file_id"))
    calibration = value.get("calibration")
    return {
        "id": _identifier(value.get("id"), code="invalid_id"),
        "file_id": file_id,
        "x_mm": _mm(value.get("x_mm"), code="invalid_reference"),
        "y_mm": _mm(value.get("y_mm"), code="invalid_reference"),
        "width_mm": _positive_mm(value.get("width_mm"), code="invalid_reference"),
        "height_mm": _positive_mm(value.get("height_mm"), code="invalid_reference"),
        "rotation_deg": _degrees(value.get("rotation_deg"), code="invalid_reference"),
        "opacity": _opacity(value.get("opacity")),
        "locked": _required_bool(value.get("locked"), code="invalid_reference"),
        "hidden": _required_bool(value.get("hidden"), code="invalid_reference"),
        "calibration": None if calibration is None else _calibration(calibration),
    }


def _calibration(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_reference")
    _reject_unknown(value, CALIBRATION_FIELDS)
    if set(value) != CALIBRATION_FIELDS:
        raise DrawingDocumentError("invalid_reference")
    start = _point(value.get("start_mm"))
    end = _point(value.get("end_mm"))
    known = _positive_mm(value.get("known_distance_mm"), code="invalid_reference")
    if start == end:
        raise DrawingDocumentError("invalid_reference")
    return {"start_mm": start, "end_mm": end, "known_distance_mm": known}


def _point(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise DrawingDocumentError("invalid_reference")
    _reject_unknown(value, CONTROL_FIELDS)
    if set(value) != CONTROL_FIELDS:
        raise DrawingDocumentError("invalid_reference")
    return {"x_mm": _mm(value.get("x_mm"), code="invalid_reference"), "y_mm": _mm(value.get("y_mm"), code="invalid_reference")}


def _assert_counts(
    paths: Sequence[Mapping[str, Any]],
    shapes: Sequence[Any],
    references: Sequence[Any],
    texts: Sequence[Any] = (),
) -> None:
    node_count = sum(len(path["nodes"]) for path in paths)
    segment_count = sum(len(path["segments"]) for path in paths)
    if node_count > MAX_NODES or segment_count > MAX_SEGMENTS:
        raise DrawingDocumentError("too_many_elements")
    if (
        len(shapes) > MAX_SHAPES
        or len(references) > MAX_REFERENCES
        or len(paths) > MAX_PATHS
        or len(texts) > MAX_TEXTS
    ):
        raise DrawingDocumentError("too_many_elements")
    if sum(len(text.get("outlines") or []) for text in texts) > 400:
        raise DrawingDocumentError("too_many_elements")


def _assert_unique_ids(
    paths: Sequence[Mapping[str, Any]],
    shapes: Sequence[Mapping[str, Any]],
    references: Sequence[Mapping[str, Any]],
    texts: Sequence[Mapping[str, Any]] = (),
) -> None:
    seen: set[str] = set()

    def take(identifier: str) -> None:
        if identifier in seen:
            raise DrawingDocumentError("duplicate_id")
        seen.add(identifier)

    for path in paths:
        take(path["id"])
        for node in path["nodes"]:
            take(node["id"])
        for segment in path["segments"]:
            take(segment["id"])
    for shape in shapes:
        take(shape["id"])
    for reference in references:
        take(reference["id"])
    for text in texts:
        take(text["id"])
        for outline in text["outlines"]:
            take(outline["id"])


def _assert_shape_links(paths: Sequence[Mapping[str, Any]], shapes: Sequence[Mapping[str, Any]]) -> None:
    paths_by_id = {path["id"]: path for path in paths}
    shapes_by_id = {shape["id"]: shape for shape in shapes}
    linked_paths: set[str] = set()
    for shape in shapes:
        if not shape["exploded"]:
            continue
        path = paths_by_id.get(shape["path_id"])
        if path is None or path["source_shape_id"] != shape["id"]:
            raise DrawingDocumentError("invalid_shape")
        if shape["path_id"] in linked_paths:
            raise DrawingDocumentError("invalid_shape")
        linked_paths.add(shape["path_id"])
    for path in paths:
        source = path["source_shape_id"]
        if source is None:
            continue
        shape = shapes_by_id.get(source)
        if shape is None or not shape["exploded"] or shape["path_id"] != path["id"]:
            raise DrawingDocumentError("invalid_shape")


def _find_by_id(rows: Sequence[Mapping[str, Any]], identifier: str, *, code: str) -> Mapping[str, Any]:
    identity = _identifier(identifier, code=code)
    for row in rows:
        if row.get("id") == identity:
            return row
    raise DrawingDocumentError(code)


def _sequence(value: Any, *, code: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DrawingDocumentError(code)
    return list(value)


def _reject_unknown(value: Mapping[str, Any], allowed: set[str] | frozenset[str]) -> None:
    if set(value) - set(allowed):
        raise DrawingDocumentError("unknown_field")


def _reject_embedded_image(value: Mapping[str, Any]) -> None:
    if EMBEDDED_IMAGE_FIELDS.intersection(value):
        raise DrawingDocumentError("embedded_image")
    for nested in value.values():
        if isinstance(nested, str) and nested.lower().startswith("data:"):
            raise DrawingDocumentError("embedded_image")


def _identifier(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise DrawingDocumentError(code)
    if len(value) > MAX_ID_LENGTH:
        raise DrawingDocumentError(code)
    return value


def _file_id(value: Any) -> str:
    if not isinstance(value, str):
        raise DrawingDocumentError("invalid_reference")
    if value.lower().startswith("data:"):
        raise DrawingDocumentError("embedded_image")
    if (
        not value
        or len(value) > MAX_FILE_ID_LENGTH
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise DrawingDocumentError("invalid_reference")
    return value


def _required_bool(value: Any, *, code: str = "invalid_document") -> bool:
    if not isinstance(value, bool):
        raise DrawingDocumentError(code)
    return value


def _finite(value: Any, *, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DrawingDocumentError(code)
    number = float(value)
    if not math.isfinite(number):
        raise DrawingDocumentError("invalid_number")
    return number


def _quantize_mm(value: Any, *, code: str = "invalid_number") -> float:
    number = _finite(value, code=code)
    if abs(number) > MAX_ABS_MM:
        raise DrawingDocumentError("unbounded")
    quantized = Decimal(str(number)).quantize(QUANTUM_MM, rounding=ROUND_HALF_UP)
    result = float(quantized)
    if result == 0:
        return 0.0
    return result


def _mm(value: Any, *, code: str = "invalid_number") -> float:
    return _quantize_mm(value, code=code)


def _positive_mm(value: Any, *, code: str) -> float:
    number = _mm(value, code=code)
    if number <= 0:
        raise DrawingDocumentError(code)
    return number


def _degrees(value: Any, *, code: str) -> float:
    number = _finite(value, code=code)
    if abs(number) > MAX_ABS_DEG:
        raise DrawingDocumentError("unbounded")
    quantized = Decimal(str(number)).quantize(QUANTUM_MM, rounding=ROUND_HALF_UP)
    result = float(quantized)
    if result == 0:
        return 0.0
    return result


def _opacity(value: Any) -> float:
    number = _finite(value, code="invalid_reference")
    if number < 0 or number > 1:
        raise DrawingDocumentError("invalid_reference")
    quantized = Decimal(str(number)).quantize(QUANTUM_MM, rounding=ROUND_HALF_UP)
    result = float(quantized)
    if result < 0 or result > 1:
        raise DrawingDocumentError("invalid_reference")
    return result


def _dump(document: Mapping[str, Any]) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "COORDINATE_SPACE",
    "DrawingDocumentError",
    "MANUFACTURING_ROLES",
    "MAX_NODES",
    "MAX_NODES_PER_PATH",
    "QUANTUM_MM",
    "ROLES",
    "SCHEMA",
    "SEGMENT_KINDS",
    "SHAPE_KINDS",
    "UNITS",
    "VERSION",
    "document_fingerprint",
    "document_to_json",
    "empty_document",
    "geometry_fingerprint",
    "line_angle_deg",
    "line_length_mm",
    "normalize_document",
    "parse_document",
    "path_bounds_mm",
    "segment_line_metrics",
]
