from __future__ import annotations

import os
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

SHEET_OUTLINE_LAYER = "SHEET_OUTLINE"
CUT_PATH_LAYER = "CUT_PATH"
SHEETS_PER_ROW = 2
SHEET_GAP_MM = 200
TOLERANCE_MM = 1.5


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_r12_lines(content: str) -> list[dict[str, Any]]:
    """Parse minimal R12 DXF LINE entities from our export format."""
    if not content:
        return []
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    entities: list[dict[str, Any]] = []
    idx = 0
    current: dict[str, Any] = {}
    entity_type = ""

    while idx + 1 < len(lines):
        code = lines[idx].strip()
        value = lines[idx + 1]
        idx += 2

        if code == "0":
            if entity_type == "LINE" and current:
                entities.append(current)
            if value == "LINE":
                entity_type = "LINE"
                current = {"type": "LINE"}
            elif value in {"EOF", "ENDSEC"}:
                if entity_type == "LINE" and current:
                    entities.append(current)
                entity_type = ""
                current = {}
            else:
                if entity_type == "LINE" and current:
                    entities.append(current)
                entity_type = value
                current = {}
            continue

        if entity_type != "LINE":
            continue

        if code == "8":
            current["layer"] = value.strip()
        elif code == "10":
            current["x1"] = _num(value)
        elif code == "20":
            current["y1"] = _num(value)
        elif code == "11":
            current["x2"] = _num(value)
        elif code == "21":
            current["y2"] = _num(value)

    if entity_type == "LINE" and current:
        entities.append(current)

    return [row for row in entities if row.get("layer")]


def _parse_with_ezdxf(file_path: str) -> list[dict[str, Any]]:
    try:
        import ezdxf
    except ImportError:
        return []

    try:
        doc = ezdxf.readfile(file_path)
    except Exception:
        return []

    entities: list[dict[str, Any]] = []
    msp = doc.modelspace()
    for entity in msp:
        if entity.dxftype() != "LINE":
            continue
        start = entity.dxf.start
        end = entity.dxf.end
        entities.append(
            {
                "type": "LINE",
                "layer": entity.dxf.layer,
                "x1": float(start.x),
                "y1": float(start.y),
                "x2": float(end.x),
                "y2": float(end.y),
            }
        )
    return entities


def _line_bounds(lines: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    if not lines:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for line in lines:
        xs.extend([_num(line.get("x1")), _num(line.get("x2"))])
        ys.extend([_num(line.get("y1")), _num(line.get("y2"))])
    return min(xs), min(ys), max(xs), max(ys)


def _is_axis_aligned_rect(lines: list[dict[str, Any]], tol: float = TOLERANCE_MM) -> bool:
    if len(lines) != 4:
        return False
    bounds = _line_bounds(lines)
    if not bounds:
        return False
    min_x, min_y, max_x, max_y = bounds
    width = max_x - min_x
    height = max_y - min_y
    if width <= tol or height <= tol:
        return False
    for line in lines:
        x1, y1, x2, y2 = _num(line.get("x1")), _num(line.get("y1")), _num(line.get("x2")), _num(line.get("y2"))
        horizontal = abs(y1 - y2) <= tol
        vertical = abs(x1 - x2) <= tol
        if not (horizontal or vertical):
            return False
        if horizontal:
            if not (abs(y1 - min_y) <= tol or abs(y1 - max_y) <= tol):
                return False
        if vertical:
            if not (abs(x1 - min_x) <= tol or abs(x1 - max_x) <= tol):
                return False
    return True


def _cluster_lines(lines: list[dict[str, Any]], tol: float = TOLERANCE_MM) -> list[list[dict[str, Any]]]:
    """Group lines that belong to the same rectangle/path by endpoint connectivity."""
    remaining = list(lines)
    clusters: list[list[dict[str, Any]]] = []

    def point_key(x: float, y: float) -> tuple[int, int]:
        return (int(round(x / tol)), int(round(y / tol)))

    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        frontier = [
            point_key(_num(seed.get("x1")), _num(seed.get("y1"))),
            point_key(_num(seed.get("x2")), _num(seed.get("y2"))),
        ]
        changed = True
        while changed:
            changed = False
            for index in range(len(remaining) - 1, -1, -1):
                line = remaining[index]
                keys = [
                    point_key(_num(line.get("x1")), _num(line.get("y1"))),
                    point_key(_num(line.get("x2")), _num(line.get("y2"))),
                ]
                if any(key in frontier for key in keys):
                    cluster.append(line)
                    remaining.pop(index)
                    for key in keys:
                        if key not in frontier:
                            frontier.append(key)
                    changed = True
        clusters.append(cluster)
    return clusters


def _extract_sheet_outlines(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outline_lines = [row for row in entities if row.get("layer") == SHEET_OUTLINE_LAYER]
    sheets: list[dict[str, Any]] = []
    for cluster in _cluster_lines(outline_lines):
        bounds = _line_bounds(cluster)
        if not bounds:
            continue
        min_x, min_y, max_x, max_y = bounds
        width_mm = max_x - min_x
        height_mm = max_y - min_y
        if width_mm <= 0 or height_mm <= 0:
            continue
        sheets.append(
            {
                "offset_x_mm": min_x,
                "offset_y_mm": min_y,
                "full_width_mm": width_mm,
                "full_height_mm": height_mm,
                "lines": cluster,
            }
        )
    sheets.sort(key=lambda row: (row["offset_y_mm"], row["offset_x_mm"]))
    for index, sheet in enumerate(sheets, start=1):
        sheet["sheet_no"] = index
    return sheets


def _piece_in_sheet(
    bounds: tuple[float, float, float, float],
    sheet: dict[str, Any],
    tol: float = TOLERANCE_MM,
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    sheet_min_x = _num(sheet.get("offset_x_mm"))
    sheet_min_y = _num(sheet.get("offset_y_mm"))
    sheet_max_x = sheet_min_x + _num(sheet.get("full_width_mm"))
    sheet_max_y = sheet_min_y + _num(sheet.get("full_height_mm"))
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    return (
        sheet_min_x - tol <= center_x <= sheet_max_x + tol
        and sheet_min_y - tol <= center_y <= sheet_max_y + tol
    )


def _dxf_to_plan_coords(
    *,
    x_mm: float,
    y_mm: float,
    width_mm: float,
    height_mm: float,
    sheet: dict[str, Any],
    trim_mm: float,
    usable_width_cm: float,
    usable_length_cm: float,
) -> dict[str, float]:
    offset_x = _num(sheet.get("offset_x_mm"))
    offset_y = _num(sheet.get("offset_y_mm"))
    full_height_mm = _num(sheet.get("full_height_mm"))

    local_x_mm = x_mm - offset_x - trim_mm
    local_y_mm = full_height_mm - trim_mm - (y_mm - offset_y) - height_mm

    return {
        "x": local_x_mm / 10.0,
        "y": local_y_mm / 10.0,
        "w": width_mm / 10.0,
        "h": height_mm / 10.0,
    }


def _expected_order_pieces(order: Any) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    for group_index, row in enumerate(order.pieces or [], start=1):
        for copy_no in range(1, cint(row.qty) + 1):
            expected.append(
                {
                    "label": f"{group_index}.{copy_no}",
                    "width_cm": flt(row.width_cm),
                    "length_cm": flt(row.length_cm),
                    "allow_rotation": cint(row.allow_rotation),
                    "piece_type": row.piece_type or "Regular",
                    "source_piece_no": group_index,
                    "copy_no": copy_no,
                }
            )
    return expected


def _match_dimensions(a_w: float, a_h: float, b_w: float, b_h: float, tol: float = 0.2) -> bool:
    direct = abs(a_w - b_w) <= tol and abs(a_h - b_h) <= tol
    rotated = abs(a_w - b_h) <= tol and abs(a_h - b_w) <= tol
    return direct or rotated


def _match_pieces_to_order(pieces: list[dict[str, Any]], order: Any) -> list[dict[str, Any]]:
    expected = _expected_order_pieces(order)
    unmatched = list(expected)
    labeled: list[dict[str, Any]] = []

    for piece in pieces:
        width_cm = _num(piece.get("w"))
        height_cm = _num(piece.get("h"))
        match_index = None
        rotated = False
        for index, candidate in enumerate(unmatched):
            if _match_dimensions(width_cm, height_cm, candidate["width_cm"], candidate["length_cm"]):
                match_index = index
                rotated = not (
                    abs(width_cm - candidate["width_cm"]) <= 0.2
                    and abs(height_cm - candidate["length_cm"]) <= 0.2
                )
                if rotated and not candidate["allow_rotation"]:
                    match_index = None
                    rotated = False
                    continue
                break
        if match_index is None:
            piece["label"] = piece.get("label") or f"imported-{len(labeled) + 1}"
            piece["piece_type"] = piece.get("piece_type") or "Regular"
            labeled.append(piece)
            continue

        candidate = unmatched.pop(match_index)
        piece["label"] = candidate["label"]
        piece["source_piece_no"] = candidate["source_piece_no"]
        piece["copy_no"] = candidate["copy_no"]
        piece["original_w"] = candidate["width_cm"]
        piece["original_h"] = candidate["length_cm"]
        piece["rotated"] = rotated
        piece["piece_type"] = candidate["piece_type"]
        piece["area_m2"] = round((width_cm * height_cm) / 10000.0, 4)
        labeled.append(piece)

    return labeled


def _rects_overlap(a: dict[str, Any], b: dict[str, Any], tol: float = 1e-3) -> bool:
    return not (
        a["x"] + a["w"] <= b["x"] + tol
        or b["x"] + b["w"] <= a["x"] + tol
        or a["y"] + a["h"] <= b["y"] + tol
        or b["y"] + b["h"] <= a["y"] + tol
    )


def validate_imported_plan(plan: dict[str, Any], order: Any) -> dict[str, Any]:
    errors: list[str] = []
    expected_count = sum(cint(row.qty) for row in (order.pieces or []))
    placed_count = sum(len(sheet.get("pieces") or []) for sheet in (plan.get("sheets") or []))
    if placed_count != expected_count:
        errors.append(
            _("Imported plan has {0} pieces but the order expects {1}.").format(placed_count, expected_count)
        )

    usable_w = flt(plan.get("usable_board_width_cm"))
    usable_h = flt(plan.get("usable_board_length_cm"))

    for sheet in plan.get("sheets") or []:
        pieces = sheet.get("pieces") or []
        for piece in pieces:
            x, y = flt(piece.get("x")), flt(piece.get("y"))
            w, h = flt(piece.get("w")), flt(piece.get("h"))
            if w <= 0 or h <= 0:
                errors.append(_("Piece {0} has invalid dimensions.").format(piece.get("label") or ""))
            if x < -0.01 or y < -0.01 or x + w > usable_w + 0.01 or y + h > usable_h + 0.01:
                errors.append(_("Piece {0} exceeds board bounds.").format(piece.get("label") or ""))

        for i, first in enumerate(pieces):
            rect_a = {
                "x": flt(first.get("x")),
                "y": flt(first.get("y")),
                "w": flt(first.get("w")),
                "h": flt(first.get("h")),
            }
            for second in pieces[i + 1 :]:
                rect_b = {
                    "x": flt(second.get("x")),
                    "y": flt(second.get("y")),
                    "w": flt(second.get("w")),
                    "h": flt(second.get("h")),
                }
                if _rects_overlap(rect_a, rect_b):
                    errors.append(
                        _("Pieces {0} and {1} overlap on sheet {2}.").format(
                            first.get("label"),
                            second.get("label"),
                            sheet.get("sheet_no"),
                        )
                    )

    return {"is_valid": not errors, "errors": errors}


def parse_production_dxf(file_url: str, order: Any) -> dict[str, Any]:
    """Parse a production DXF exported from this system into cutting_plan_json."""
    if not file_url:
        frappe.throw(_("Attach a DXF file."))

    file_path = frappe.get_site_path("public", file_url.lstrip("/"))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path(file_url.lstrip("/"))

    content = ""
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
    except OSError as exc:
        frappe.throw(_("Unable to read DXF file: {0}").format(exc))

    entities = _parse_r12_lines(content)
    if not entities:
        entities = _parse_with_ezdxf(file_path)
    if not entities:
        frappe.throw(_("DXF contains no usable LINE geometry."))

    outline_entities = [row for row in entities if row.get("layer") == SHEET_OUTLINE_LAYER]
    cut_entities = [row for row in entities if row.get("layer") == CUT_PATH_LAYER]
    if not outline_entities:
        frappe.throw(_("DXF is missing the {0} layer.").format(SHEET_OUTLINE_LAYER))
    if not cut_entities:
        frappe.throw(_("DXF is missing the {0} layer.").format(CUT_PATH_LAYER))

    trim_mm = flt(order.trim_margin_mm)
    full_board_width_cm = flt(order.board_width_cm) or flt(order.full_board_width_mm) / 10
    full_board_length_cm = flt(order.board_length_cm) or flt(order.full_board_length_mm) / 10
    trim_cm = trim_mm / 10.0
    usable_board_width_cm = max(0.0, full_board_width_cm - (2 * trim_cm))
    usable_board_length_cm = max(0.0, full_board_length_cm - (2 * trim_cm))

    sheets = _extract_sheet_outlines(entities)
    cut_clusters = _cluster_lines(cut_entities)
    placed_pieces: list[dict[str, Any]] = []

    for cluster in cut_clusters:
        bounds = _line_bounds(cluster)
        if not bounds:
            continue
        min_x, min_y, max_x, max_y = bounds
        width_mm = max_x - min_x
        height_mm = max_y - min_y
        if width_mm <= TOLERANCE_MM or height_mm <= TOLERANCE_MM:
            continue

        target_sheet = None
        for sheet in sheets:
            if _piece_in_sheet(bounds, sheet):
                target_sheet = sheet
                break
        if not target_sheet:
            continue

        coords = _dxf_to_plan_coords(
            x_mm=min_x,
            y_mm=min_y,
            width_mm=width_mm,
            height_mm=height_mm,
            sheet=target_sheet,
            trim_mm=trim_mm,
            usable_width_cm=usable_board_width_cm,
            usable_length_cm=usable_board_length_cm,
        )
        piece_type = "Regular"
        if not _is_axis_aligned_rect(cluster):
            piece_type = "Special" if len(cluster) > 4 else "Clipped Corner"

        placed_pieces.append(
            {
                "id": len(placed_pieces) + 1,
                **coords,
                "piece_type": piece_type,
                "area_m2": round((coords["w"] * coords["h"]) / 10000.0, 4),
            }
        )
        target_sheet.setdefault("pieces", []).append(placed_pieces[-1])

    for sheet in sheets:
        sheet["full_width_cm"] = _num(sheet.get("full_width_mm")) / 10.0
        sheet["full_length_cm"] = _num(sheet.get("full_height_mm")) / 10.0
        sheet["usable_width_cm"] = usable_board_width_cm
        sheet["usable_length_cm"] = usable_board_length_cm
        sheet["w"] = usable_board_width_cm
        sheet["h"] = usable_board_length_cm
        sheet["source_type"] = "Full Board"
        sheet_pieces = sheet.get("pieces") or []
        sheet["pieces"] = _match_pieces_to_order(sheet_pieces, order)

    all_pieces = [piece for sheet in sheets for piece in (sheet.get("pieces") or [])]
    used_area_m2 = sum(flt(piece.get("area_m2")) for piece in all_pieces)
    total_board_area_m2 = len(sheets) * (full_board_width_cm * full_board_length_cm) / 100.0
    waste_area_m2 = max(0.0, total_board_area_m2 - used_area_m2)

    snapshot = {
        "engine_version": "dxf-import-v1",
        "optimization_mode": "Custom DXF",
        "method_key": "custom_dxf",
        "method_label": _("Uploaded DXF"),
        "full_board_width_cm": full_board_width_cm,
        "full_board_length_cm": full_board_length_cm,
        "usable_board_width_cm": usable_board_width_cm,
        "usable_board_length_cm": usable_board_length_cm,
        "kerf_cm": flt(order.kerf_mm) / 10.0,
        "trim_cm": trim_cm,
        "used_area_m2": used_area_m2,
        "total_board_area_m2": total_board_area_m2,
        "waste_area_m2": waste_area_m2,
        "required_full_boards": len(sheets),
        "sheets": [
            {
                "sheet_no": sheet.get("sheet_no"),
                "source_type": sheet.get("source_type"),
                "full_width_cm": sheet.get("full_width_cm"),
                "full_length_cm": sheet.get("full_length_cm"),
                "usable_width_cm": sheet.get("usable_width_cm"),
                "usable_length_cm": sheet.get("usable_length_cm"),
                "w": sheet.get("w"),
                "h": sheet.get("h"),
                "pieces": sheet.get("pieces") or [],
            }
            for sheet in sheets
        ],
        "unplaced": [],
        "validation": {"is_valid": True, "errors": []},
    }
    snapshot["validation"] = validate_imported_plan(snapshot, order)
    return snapshot
