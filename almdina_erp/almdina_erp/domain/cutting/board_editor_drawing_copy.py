"""Copy an editable drawing onto a new cutting plan, and rebuild a line outline.

The copied document is a new drawing. It does not reuse the source key, version,
or source fingerprint. Reference images stay on the source draft. Guide lines
and notes stay in the drawing and are not manufacturing geometry.

A stored polygon can be rebuilt as a closed line path. Curves and guide lines
that were never stored are not invented.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    COORDINATE_SPACE,
    ROLE_MANUFACTURING_OUTER,
    SCHEMA,
    SEGMENT_LINE,
    UNITS,
    VERSION,
    DrawingDocumentError,
    document_fingerprint,
    normalize_document,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_persistence import (
    drawing_key,
)


class DrawingCopyError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def clone_drawing_document(document: Mapping[str, Any], piece_instance_id: str) -> dict[str, Any]:
    """Independent drawing for one copied piece, without reference images."""

    cloned = deepcopy(dict(document))
    cloned["piece_instance_id"] = str(piece_instance_id)
    cloned["references"] = []
    return normalize_document(cloned)


def editable_outline_points_mm(raw: Any) -> list[list[float]] | None:
    """Door-local millimetre ring from a stored centimetre polygon, or None."""

    payload = raw
    if isinstance(raw, str):
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if not isinstance(payload, Mapping):
        return None
    if (
        payload.get("version") != 1
        or payload.get("kind") != "polygon"
        or payload.get("units") != "cm"
        or payload.get("exact") is False
    ):
        return None
    points = payload.get("points")
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)):
        return None
    converted: list[list[float]] = []
    for point in points:
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) < 2:
            return None
        try:
            x_mm = float(point[0]) * 10.0
            y_mm = float(point[1]) * 10.0
        except (TypeError, ValueError):
            return None
        if x_mm != x_mm or y_mm != y_mm:
            return None
        if converted and abs(converted[-1][0] - x_mm) <= 1e-6 and abs(converted[-1][1] - y_mm) <= 1e-6:
            continue
        converted.append([x_mm, y_mm])
    if (
        len(converted) >= 2
        and abs(converted[0][0] - converted[-1][0]) <= 1e-6
        and abs(converted[0][1] - converted[-1][1]) <= 1e-6
    ):
        converted.pop()
    if len(converted) < 3:
        return None
    return converted


def document_from_editable_outline(
    points_mm: Sequence[Sequence[float]],
    piece_instance_id: str,
    blank_width_mm: float,
    blank_length_mm: float,
) -> dict[str, Any] | None:
    """Closed line path. This is the stored polygon, not a recovered curve."""

    points = [list(point) for point in points_mm]
    if len(points) < 3:
        return None
    nodes = [
        {"id": f"restored-n{index}", "x_mm": point[0], "y_mm": point[1]}
        for index, point in enumerate(points)
    ]
    segments = []
    for index in range(len(points)):
        nxt = (index + 1) % len(points)
        segments.append(
            {
                "id": f"restored-s{index}",
                "kind": SEGMENT_LINE,
                "from_node": f"restored-n{index}",
                "to_node": f"restored-n{nxt}",
            }
        )
    try:
        return normalize_document(
            {
                "schema": SCHEMA,
                "version": VERSION,
                "units": UNITS,
                "coordinate_space": COORDINATE_SPACE,
                "piece_instance_id": piece_instance_id,
                "blank": {"width_mm": blank_width_mm, "length_mm": blank_length_mm},
                "paths": [
                    {
                        "id": "restored-outline",
                        "role": ROLE_MANUFACTURING_OUTER,
                        "closed": True,
                        "source_shape_id": None,
                        "nodes": nodes,
                        "segments": segments,
                    }
                ],
                "shapes": [],
                "references": [],
            }
        )
    except DrawingDocumentError:
        return None


def restore_document_from_catalog(piece: Mapping[str, Any], piece_instance_id: str) -> dict[str, Any] | None:
    points = piece.get("editable_outline_mm")
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)):
        return None
    try:
        width = float(piece.get("blank_width_mm") or 0)
        length = float(piece.get("blank_length_mm") or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or length <= 0:
        return None
    return document_from_editable_outline(points, piece_instance_id, width, length)


def ordered_piece_ids(snapshot: Mapping[str, Any]) -> list[str]:
    sheets = [
        sheet
        for sheet in (snapshot.get("sheets") or [])
        if isinstance(sheet, Mapping)
    ]
    sheets.sort(key=lambda sheet: int(sheet.get("sheet_no") or 0))
    found: list[str] = []
    for sheet in sheets:
        for piece in sheet.get("pieces") or []:
            if not isinstance(piece, Mapping):
                continue
            instance = str(piece.get("piece_instance_id") or "").strip()
            if instance:
                found.append(instance)
    return found


def map_piece_instances(
    source_snapshot: Mapping[str, Any],
    copied_snapshot: Mapping[str, Any],
) -> dict[str, str]:
    """Map source piece ids to copied piece ids.

    Matching uses the piece id itself. Name and size are not identities.
    A complete id change is accepted only when both snapshots list the same
    number of distinct pieces in the same sheet order.
    """

    source_ids = ordered_piece_ids(source_snapshot)
    copied_ids = ordered_piece_ids(copied_snapshot)
    if not copied_ids:
        return {}
    if set(copied_ids) <= set(source_ids):
        return {item: item for item in copied_ids}
    if (
        len(source_ids) == len(copied_ids)
        and len(source_ids) == len(set(source_ids))
        and len(copied_ids) == len(set(copied_ids))
        and set(source_ids).isdisjoint(set(copied_ids))
    ):
        return dict(zip(source_ids, copied_ids, strict=True))
    raise DrawingCopyError("unmapped_pieces")


def build_copied_drawing_rows(
    *,
    records: Sequence[Mapping[str, Any]],
    source_snapshot: Mapping[str, Any],
    copied_snapshot: Mapping[str, Any],
    order_name: str,
    plan_name: str,
    source_content_revision: str,
    source_input_fingerprint: str,
) -> list[dict[str, Any]]:
    """Rows for the new plan. The source records are not modified."""

    mapping = map_piece_instances(source_snapshot, copied_snapshot)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        source_id = str(record.get("piece_instance_id") or "").strip()
        target_id = mapping.get(source_id)
        if not target_id or target_id in seen:
            continue
        document = record.get("drawing_json")
        if not isinstance(document, Mapping):
            document = record.get("document")
        if not isinstance(document, Mapping):
            raise DrawingCopyError("invalid_document")
        try:
            cloned = clone_drawing_document(document, target_id)
        except DrawingDocumentError as exc:
            raise DrawingCopyError(exc.code) from exc
        seen.add(target_id)
        rows.append(
            {
                "drawing_key": drawing_key(order_name, plan_name, target_id),
                "door_cutting_order": order_name,
                "source_plan": plan_name,
                "piece_instance_id": target_id,
                "source_input_fingerprint": source_input_fingerprint,
                "source_content_revision": source_content_revision,
                "drawing_version": 1,
                "document_fingerprint": document_fingerprint(cloned),
                "drawing_json": cloned,
                "prior_drawing_archive_json": [],
            }
        )
    return rows


__all__ = [
    "DrawingCopyError",
    "build_copied_drawing_rows",
    "clone_drawing_document",
    "document_from_editable_outline",
    "editable_outline_points_mm",
    "map_piece_instances",
    "ordered_piece_ids",
    "restore_document_from_catalog",
]
