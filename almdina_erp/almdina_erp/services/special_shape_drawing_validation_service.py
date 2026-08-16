from __future__ import annotations

import json
import math
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.services.special_shape_service import (
    MAX_DRAWING_BYTES,
    MAX_DRAWING_ELEMENTS,
    validate_special_shape_drawing as validate_legacy_special_shape_drawing,
)

V4_SCHEMA = "almdina.door-drawing"
V4_VERSION = 4
V4_UNITS = "mm"
MAX_ENTITY_ID_LENGTH = 80
MAX_DRAWING_COORDINATE_MM = 20_000
DRAWING_EPSILON_MM = 0.001


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} must be a valid number.").format(label))
    if not math.isfinite(number):
        frappe.throw(_("{0} must be finite.").format(label))
    return number


def _entity_id(value: Any, label: str) -> str:
    entity_id = str(value or "")
    if not entity_id or len(entity_id) > MAX_ENTITY_ID_LENGTH:
        frappe.throw(_("{0} has an invalid identifier.").format(label))
    return entity_id


def _parse(raw_drawing: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_drawing, str):
        if len(raw_drawing.encode("utf-8")) > MAX_DRAWING_BYTES:
            frappe.throw(
                _("Special shape documentation is too large. Keep the sketch simple and try again.")
            )
        try:
            drawing = json.loads(raw_drawing)
        except (TypeError, ValueError):
            frappe.throw(_("Special shape documentation contains invalid JSON."))
    elif isinstance(raw_drawing, dict):
        drawing = raw_drawing
    else:
        frappe.throw(_("Special shape documentation must be a JSON object."))

    if not isinstance(drawing, dict):
        frappe.throw(_("Special shape documentation must be a JSON object."))
    return drawing


def _validate_blank(blank: Any) -> None:
    if not isinstance(blank, dict):
        frappe.throw(_("Drawing V4 blank dimensions are invalid."))
    for fieldname in ("widthMm", "heightMm"):
        value = _finite(blank.get(fieldname), _("Drawing V4 {0}").format(fieldname))
        if value <= 0 or value > MAX_DRAWING_COORDINATE_MM:
            frappe.throw(_("Drawing V4 blank dimensions are invalid."))


def _validate_v4(drawing: dict[str, Any]) -> dict[str, Any]:
    if drawing.get("schema") != V4_SCHEMA:
        frappe.throw(_("Unsupported special shape documentation schema."))
    if drawing.get("units") != V4_UNITS:
        frappe.throw(_("Drawing V4 must use millimetres."))

    _validate_blank(drawing.get("blank"))
    nodes = drawing.get("nodes")
    segments = drawing.get("segments")
    paths = drawing.get("paths")
    if not isinstance(nodes, list) or not isinstance(segments, list) or not isinstance(paths, list):
        frappe.throw(_("Drawing V4 must contain nodes, segments and paths lists."))
    if len(nodes) + len(segments) + len(paths) > MAX_DRAWING_ELEMENTS:
        frappe.throw(
            _("Special shape documentation has too many entities. The maximum is {0}.").format(
                MAX_DRAWING_ELEMENTS
            )
        )

    entity_ids: set[str] = set()
    node_points: dict[str, tuple[float, float]] = {}
    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, dict):
            frappe.throw(_("Drawing V4 node {0} must be an object.").format(index))
        node_id = _entity_id(node.get("id"), _("Drawing V4 node {0}").format(index))
        if node_id in entity_ids:
            frappe.throw(_("Drawing V4 entity identifiers must be unique."))
        entity_ids.add(node_id)
        x = _finite(node.get("xMm"), _("Drawing V4 node X"))
        y = _finite(node.get("yMm"), _("Drawing V4 node Y"))
        if abs(x) > MAX_DRAWING_COORDINATE_MM or abs(y) > MAX_DRAWING_COORDINATE_MM:
            frappe.throw(_("Drawing V4 node is outside the allowed drawing area."))
        node_points[node_id] = (x, y)

    segment_refs: dict[str, tuple[str, str]] = {}
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            frappe.throw(_("Drawing V4 segment {0} must be an object.").format(index))
        segment_id = _entity_id(
            segment.get("id"), _("Drawing V4 segment {0}").format(index)
        )
        if segment_id in entity_ids:
            frappe.throw(_("Drawing V4 entity identifiers must be unique."))
        entity_ids.add(segment_id)
        if segment.get("type") != "line":
            frappe.throw(_("Drawing V4 currently supports line segments only."))
        start_id = str(segment.get("startNodeId") or "")
        end_id = str(segment.get("endNodeId") or "")
        if start_id not in node_points or end_id not in node_points:
            frappe.throw(_("Drawing V4 segment references a missing node."))
        start = node_points[start_id]
        end = node_points[end_id]
        if math.hypot(end[0] - start[0], end[1] - start[1]) <= DRAWING_EPSILON_MM:
            frappe.throw(_("Drawing V4 cannot contain zero-length segments."))
        segment_refs[segment_id] = (start_id, end_id)

    for index, path in enumerate(paths, start=1):
        if not isinstance(path, dict):
            frappe.throw(_("Drawing V4 path {0} must be an object.").format(index))
        path_id = _entity_id(path.get("id"), _("Drawing V4 path {0}").format(index))
        if path_id in entity_ids:
            frappe.throw(_("Drawing V4 entity identifiers must be unique."))
        entity_ids.add(path_id)
        start_node_id = str(path.get("startNodeId") or "")
        if start_node_id not in node_points:
            frappe.throw(_("Drawing V4 path references a missing start node."))
        segment_ids = path.get("segmentIds")
        if not isinstance(segment_ids, list):
            frappe.throw(_("Drawing V4 path must contain a segmentIds list."))
        if len(segment_ids) != len(set(map(str, segment_ids))):
            frappe.throw(_("Drawing V4 path cannot contain duplicate segments."))

        current_node_id = start_node_id
        for segment_id_value in segment_ids:
            segment_id = str(segment_id_value)
            reference = segment_refs.get(segment_id)
            if reference is None:
                frappe.throw(_("Drawing V4 path references a missing segment."))
            segment_start, segment_end = reference
            if segment_start != current_node_id:
                frappe.throw(_("Drawing V4 path segments are not continuous."))
            current_node_id = segment_end

        if bool(path.get("closed")) and segment_ids and current_node_id != start_node_id:
            frappe.throw(_("Drawing V4 closed path does not return to its start node."))

    return drawing


def validate_special_shape_drawing(
    raw_drawing: str | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate the active V4 drawing document while retaining safe V1 delegation."""

    if raw_drawing in (None, ""):
        return None

    drawing = _parse(raw_drawing)
    try:
        version = int(drawing.get("version") or 0)
    except (TypeError, ValueError):
        version = 0

    if version == V4_VERSION:
        return _validate_v4(drawing)
    return validate_legacy_special_shape_drawing(drawing)


__all__ = ["validate_special_shape_drawing"]
