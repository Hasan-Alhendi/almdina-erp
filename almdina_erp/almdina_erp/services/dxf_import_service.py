from __future__ import annotations

import os
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    assemble_contours,
    bbox,
    is_axis_aligned_rectangle,
    polygon_area,
    polygon_distance,
    polygon_inside_rect,
    polygons_overlap,
    simplify_polygon,
    validate_polygon,
)
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import (
    DxfReadError,
    SUPPORTED_DXF_ENTITY_TYPES,
    read_dxf_geometry,
)

SHEET_OUTLINE_LAYER = "SHEET_OUTLINE"
CUT_PATH_LAYER = "CUT_PATH"
SHEETS_PER_ROW = 2
SHEET_GAP_MM = 200
CONNECTIVITY_TOLERANCE_MM = 1.5
DIMENSION_TOLERANCE_MM = 2.0
KERF_NUMERIC_TOLERANCE_MM = 0.1
GEOMETRY_TOLERANCE_MM = 0.25
TOLERANCE_MM = CONNECTIVITY_TOLERANCE_MM  # backward-compatible public constant


class DxfImportError(ValueError):
    """Expected, user-fixable DXF validation failure."""

    def __init__(self, errors: str | list[str]):
        self.errors = [errors] if isinstance(errors, str) else [str(error) for error in errors if error]
        super().__init__("\n".join(self.errors))


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_cm(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_mm(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _parse_r12_lines(content: str) -> list[dict[str, Any]]:
    """Fallback parser for the application's legacy R12 LINE-only exporter."""
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
                entity_type = ""
                current = {}
            else:
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


def _read_legacy_content(file_path: str) -> str:
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError as exc:
        raise DxfImportError("تعذر قراءة ملف DXF من الخادم. أعد رفع الملف ثم حاول مرة أخرى.") from exc


def _normalized_segments(file_path: str) -> list[dict[str, Any]]:
    content_cache: str | None = None

    def legacy_parser() -> list[dict[str, Any]]:
        nonlocal content_cache
        if content_cache is None:
            content_cache = _read_legacy_content(file_path)
        return _parse_r12_lines(content_cache)

    try:
        result = read_dxf_geometry(
            file_path,
            relevant_layers={SHEET_OUTLINE_LAYER, CUT_PATH_LAYER},
            legacy_line_parser=legacy_parser,
        )
    except DxfReadError as exc:
        raise DxfImportError(str(exc)) from exc

    unsupported = result.get("unsupported") or []
    if unsupported:
        unique = sorted({f"{item['entity_type']} على {item['layer']}" for item in unsupported})
        supported = ", ".join(sorted(SUPPORTED_DXF_ENTITY_TYPES))
        raise DxfImportError(
            "يحتوي ملف DXF على عناصر غير مدعومة داخل طبقات القص: "
            + "، ".join(unique)
            + f". العناصر المدعومة هي: {supported}."
        )
    return result.get("segments") or []


def _segments_for_layer(rows: list[dict[str, Any]], layer: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [(row["start"], row["end"]) for row in rows if row.get("layer") == layer]


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


def _direct_dimensions_match(piece_w: float, piece_h: float, expected_w: float, expected_h: float) -> bool:
    tolerance_cm = DIMENSION_TOLERANCE_MM / 10.0
    return abs(piece_w - expected_w) <= tolerance_cm and abs(piece_h - expected_h) <= tolerance_cm


def _rotated_dimensions_match(piece_w: float, piece_h: float, expected_w: float, expected_h: float) -> bool:
    tolerance_cm = DIMENSION_TOLERANCE_MM / 10.0
    return abs(piece_w - expected_h) <= tolerance_cm and abs(piece_h - expected_w) <= tolerance_cm


def _match_dimensions(a_w: float, a_h: float, b_w: float, b_h: float, tol: float = 0.2) -> bool:
    """Backward-compatible helper retained for contracts/tests; tolerance is in cm."""
    return (abs(a_w - b_w) <= tol and abs(a_h - b_h) <= tol) or (
        abs(a_w - b_h) <= tol and abs(a_h - b_w) <= tol
    )


def _match_pieces_to_order(pieces: list[dict[str, Any]], order: Any) -> list[dict[str, Any]]:
    expected = _expected_order_pieces(order)
    unmatched = list(expected)
    labeled: list[dict[str, Any]] = []
    errors: list[str] = []

    for piece_index, piece in enumerate(pieces, start=1):
        width_cm = _num(piece.get("w"))
        height_cm = _num(piece.get("h"))
        direct_index = next(
            (
                index
                for index, candidate in enumerate(unmatched)
                if _direct_dimensions_match(width_cm, height_cm, candidate["width_cm"], candidate["length_cm"])
            ),
            None,
        )
        rotated_index = next(
            (
                index
                for index, candidate in enumerate(unmatched)
                if candidate["allow_rotation"]
                and _rotated_dimensions_match(width_cm, height_cm, candidate["width_cm"], candidate["length_cm"])
            ),
            None,
        )
        match_index = direct_index if direct_index is not None else rotated_index
        rotated = direct_index is None and rotated_index is not None

        if match_index is None:
            forbidden_rotation = next(
                (
                    candidate
                    for candidate in unmatched
                    if not candidate["allow_rotation"]
                    and _rotated_dimensions_match(width_cm, height_cm, candidate["width_cm"], candidate["length_cm"])
                ),
                None,
            )
            if forbidden_rotation:
                errors.append(
                    f"القطعة رقم {piece_index} أبعادها {_format_cm(width_cm)} × {_format_cm(height_cm)} سم "
                    f"وتطابق القطعة {forbidden_rotation['label']} بعد تدويرها، لكن التدوير غير مسموح لهذه القطعة في الطلب."
                )
            else:
                errors.append(
                    f"القطعة رقم {piece_index} أبعادها {_format_cm(width_cm)} × {_format_cm(height_cm)} سم "
                    f"ولا تطابق أي قطعة متبقية في الطلب ضمن سماحية ±{_format_mm(DIMENSION_TOLERANCE_MM)} مم."
                )
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

    if unmatched:
        preview = "، ".join(
            f"{candidate['label']} ({_format_cm(candidate['width_cm'])} × {_format_cm(candidate['length_cm'])} سم)"
            for candidate in unmatched[:6]
        )
        suffix = " ..." if len(unmatched) > 6 else ""
        errors.append(f"ملف DXF لا يحتوي على جميع قطع الطلب. القطع غير المطابقة/المفقودة: {preview}{suffix}")
    if errors:
        raise DxfImportError(errors)
    return labeled


def _validate_sheet_contours(
    contours: list[dict[str, object]],
    *,
    expected_width_mm: float,
    expected_height_mm: float,
) -> list[dict[str, Any]]:
    if not contours:
        raise DxfImportError(f"لم يتم العثور على حدود ألواح صالحة في طبقة {SHEET_OUTLINE_LAYER}.")
    errors: list[str] = []
    sheets: list[dict[str, Any]] = []
    for index, contour in enumerate(contours, start=1):
        points = contour.get("points") or []
        if contour.get("branched"):
            errors.append(f"حدود اللوح رقم {index} تحتوي على تفرع/خطوط زائدة. يجب أن تكون مستطيلاً واحدًا مغلقًا.")
            continue
        if not contour.get("closed"):
            errors.append(f"حدود اللوح رقم {index} غير مغلقة. أغلق المسار على طبقة {SHEET_OUTLINE_LAYER} ثم أعد الرفع.")
            continue
        if not is_axis_aligned_rectangle(points, CONNECTIVITY_TOLERANCE_MM):
            errors.append(f"حدود اللوح رقم {index} ليست مستطيلاً صحيحًا بمحاور مستقيمة على طبقة {SHEET_OUTLINE_LAYER}.")
            continue
        min_x, min_y, max_x, max_y = bbox(points)
        width_mm = max_x - min_x
        height_mm = max_y - min_y
        if (
            abs(width_mm - expected_width_mm) > DIMENSION_TOLERANCE_MM
            or abs(height_mm - expected_height_mm) > DIMENSION_TOLERANCE_MM
        ):
            errors.append(
                f"أبعاد اللوح رقم {index} في DXF هي {_format_mm(width_mm)} × {_format_mm(height_mm)} مم، "
                f"بينما الطلب يتطلب {_format_mm(expected_width_mm)} × {_format_mm(expected_height_mm)} مم "
                f"(السماحية ±{_format_mm(DIMENSION_TOLERANCE_MM)} مم)."
            )
            continue
        sheets.append(
            {
                "offset_x_mm": min_x,
                "offset_y_mm": min_y,
                "full_width_mm": width_mm,
                "full_height_mm": height_mm,
                "outline_points_mm": simplify_polygon(points, CONNECTIVITY_TOLERANCE_MM),
                "pieces": [],
            }
        )
    if errors:
        raise DxfImportError(errors)
    sheets.sort(key=lambda row: (row["offset_y_mm"], row["offset_x_mm"]))
    for sheet_no, sheet in enumerate(sheets, start=1):
        sheet["sheet_no"] = sheet_no
    return sheets


def _sheet_for_piece(points: list[tuple[float, float]], sheets: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = []
    for sheet in sheets:
        min_x = _num(sheet["offset_x_mm"])
        min_y = _num(sheet["offset_y_mm"])
        max_x = min_x + _num(sheet["full_width_mm"])
        max_y = min_y + _num(sheet["full_height_mm"])
        if polygon_inside_rect(
            points,
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
            tolerance=CONNECTIVITY_TOLERANCE_MM,
        ):
            matches.append(sheet)
    return matches[0] if len(matches) == 1 else None


def _to_plan_points(
    points_mm: list[tuple[float, float]],
    *,
    sheet: dict[str, Any],
    trim_mm: float,
) -> list[tuple[float, float]]:
    offset_x = _num(sheet["offset_x_mm"])
    offset_y = _num(sheet["offset_y_mm"])
    full_height = _num(sheet["full_height_mm"])
    return [
        (
            (x - offset_x - trim_mm) / 10.0,
            (full_height - trim_mm - (y - offset_y)) / 10.0,
        )
        for x, y in points_mm
    ]


def _extract_pieces(
    contours: list[dict[str, object]],
    *,
    sheets: list[dict[str, Any]],
    trim_mm: float,
    usable_width_cm: float,
    usable_length_cm: float,
) -> list[dict[str, Any]]:
    errors: list[str] = []
    pieces: list[dict[str, Any]] = []
    for piece_no, contour in enumerate(contours, start=1):
        raw_points = contour.get("points") or []
        if contour.get("branched"):
            errors.append(f"مسار القطعة رقم {piece_no} يحتوي على تفرع أو خطوط زائدة ولا يشكل محيط قطعة واحدًا.")
            continue
        if not contour.get("closed"):
            errors.append(f"مسار القطعة رقم {piece_no} غير مغلق على طبقة {CUT_PATH_LAYER}. أغلق محيط القطعة بالكامل ثم أعد الرفع.")
            continue
        points_mm = simplify_polygon(raw_points, GEOMETRY_TOLERANCE_MM)
        geometry_errors = validate_polygon(points_mm, GEOMETRY_TOLERANCE_MM)
        if "self_intersection" in geometry_errors:
            errors.append(f"هندسة القطعة رقم {piece_no} تتقاطع مع نفسها. عدّل المحيط بحيث لا تتقاطع أضلاعه/منحنياته.")
            continue
        if "too_few_vertices" in geometry_errors or "zero_area" in geometry_errors:
            errors.append(f"هندسة القطعة رقم {piece_no} غير صالحة: المحيط لا يكوّن مساحة قطع صحيحة.")
            continue
        target_sheet = _sheet_for_piece(points_mm, sheets)
        if target_sheet is None:
            errors.append(f"القطعة رقم {piece_no} ليست موجودة بالكامل داخل حدود لوح واحد من طبقة {SHEET_OUTLINE_LAYER}.")
            continue
        plan_points = _to_plan_points(points_mm, sheet=target_sheet, trim_mm=trim_mm)
        if not polygon_inside_rect(
            plan_points,
            min_x=0.0,
            min_y=0.0,
            max_x=usable_width_cm,
            max_y=usable_length_cm,
            tolerance=0.01,
        ):
            errors.append(
                f"القطعة رقم {piece_no} تتجاوز المساحة القابلة للاستخدام من اللوح بعد احتساب هامش التشذيب {_format_mm(trim_mm)} مم."
            )
            continue
        min_x, min_y, max_x, max_y = bbox(plan_points)
        piece = {
            "id": piece_no,
            "x": min_x,
            "y": min_y,
            "w": max_x - min_x,
            "h": max_y - min_y,
            "piece_type": "Regular" if is_axis_aligned_rectangle(points_mm, CONNECTIVITY_TOLERANCE_MM) else "Special",
            "_outline_mm": points_mm,
            "_outline_cm": plan_points,
            "_sheet_no": target_sheet["sheet_no"],
        }
        pieces.append(piece)
        target_sheet["pieces"].append(piece)
    if errors:
        raise DxfImportError(errors)
    return pieces


def _validate_piece_spacing(pieces: list[dict[str, Any]], *, kerf_mm: float) -> None:
    errors: list[str] = []
    by_sheet: dict[int, list[dict[str, Any]]] = {}
    for piece in pieces:
        by_sheet.setdefault(int(piece["_sheet_no"]), []).append(piece)
    for sheet_no, sheet_pieces in by_sheet.items():
        for index, first in enumerate(sheet_pieces):
            for second in sheet_pieces[index + 1 :]:
                first_outline = first["_outline_mm"]
                second_outline = second["_outline_mm"]
                if polygons_overlap(first_outline, second_outline, tolerance=1e-6):
                    errors.append(
                        f"القطعتان {first['id']} و{second['id']} متداخلتان على اللوح رقم {sheet_no}. افصل القطعتين قبل الرفع."
                    )
                    continue
                if kerf_mm <= 0:
                    continue
                distance = polygon_distance(first_outline, second_outline, tolerance=1e-6)
                if distance + KERF_NUMERIC_TOLERANCE_MM < kerf_mm:
                    errors.append(
                        f"المسافة بين القطعتين {first['id']} و{second['id']} على اللوح رقم {sheet_no} هي "
                        f"{_format_mm(distance)} مم، بينما سماكة القص (Kerf) المطلوبة {_format_mm(kerf_mm)} مم."
                    )
    if errors:
        raise DxfImportError(errors)


def _public_piece(piece: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in piece.items() if not key.startswith("_")}


def validate_imported_plan(
    plan: dict[str, Any],
    order: Any,
    *,
    geometry_by_piece_id: dict[int, list[tuple[float, float]]] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    expected_count = sum(cint(row.qty) for row in (order.pieces or []))
    placed_count = sum(len(sheet.get("pieces") or []) for sheet in (plan.get("sheets") or []))
    if placed_count != expected_count:
        errors.append(f"عدد القطع في خطة DXF هو {placed_count} بينما الطلب يتطلب {expected_count} قطعة بالضبط.")

    usable_w = flt(plan.get("usable_board_width_cm"))
    usable_h = flt(plan.get("usable_board_length_cm"))
    kerf_cm = max(0.0, flt(plan.get("kerf_cm")))
    for sheet in plan.get("sheets") or []:
        pieces = sheet.get("pieces") or []
        for piece in pieces:
            x, y = flt(piece.get("x")), flt(piece.get("y"))
            w, h = flt(piece.get("w")), flt(piece.get("h"))
            label = piece.get("label") or piece.get("id") or "؟"
            if w <= 0 or h <= 0:
                errors.append(f"القطعة {label} لها أبعاد غير صالحة.")
            if x < -0.01 or y < -0.01 or x + w > usable_w + 0.01 or y + h > usable_h + 0.01:
                errors.append(f"القطعة {label} تتجاوز حدود المساحة القابلة للاستخدام من اللوح.")

        for index, first in enumerate(pieces):
            first_outline = (geometry_by_piece_id or {}).get(int(first.get("id") or 0))
            if first_outline is None:
                first_outline = [
                    (flt(first.get("x")), flt(first.get("y"))),
                    (flt(first.get("x")) + flt(first.get("w")), flt(first.get("y"))),
                    (flt(first.get("x")) + flt(first.get("w")), flt(first.get("y")) + flt(first.get("h"))),
                    (flt(first.get("x")), flt(first.get("y")) + flt(first.get("h"))),
                ]
            for second in pieces[index + 1 :]:
                second_outline = (geometry_by_piece_id or {}).get(int(second.get("id") or 0))
                if second_outline is None:
                    second_outline = [
                        (flt(second.get("x")), flt(second.get("y"))),
                        (flt(second.get("x")) + flt(second.get("w")), flt(second.get("y"))),
                        (flt(second.get("x")) + flt(second.get("w")), flt(second.get("y")) + flt(second.get("h"))),
                        (flt(second.get("x")), flt(second.get("y")) + flt(second.get("h"))),
                    ]
                if polygons_overlap(first_outline, second_outline, tolerance=1e-6):
                    errors.append(
                        f"القطعتان {first.get('label')} و{second.get('label')} متداخلتان على اللوح رقم {sheet.get('sheet_no')}."
                    )
                elif kerf_cm > 0 and polygon_distance(first_outline, second_outline, tolerance=1e-6) + 0.01 < kerf_cm:
                    errors.append(
                        f"المسافة بين القطعتين {first.get('label')} و{second.get('label')} على اللوح رقم {sheet.get('sheet_no')} "
                        f"أقل من Kerf المطلوب ({_format_mm(kerf_cm * 10)} مم)."
                    )
    return {"is_valid": not errors, "errors": errors}


def parse_production_dxf(file_url: str, order: Any) -> dict[str, Any]:
    """Parse and fully validate an uploaded production DXF without mutating it."""
    if not file_url:
        raise DxfImportError("اختر ملف DXF ثم أعد المحاولة.")

    file_path = frappe.get_site_path("public", file_url.lstrip("/"))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path(file_url.lstrip("/"))
    if not os.path.exists(file_path):
        raise DxfImportError("تعذر العثور على ملف DXF المرفوع على الخادم. أعد رفع الملف ثم حاول مرة أخرى.")

    rows = _normalized_segments(file_path)
    sheet_segments = _segments_for_layer(rows, SHEET_OUTLINE_LAYER)
    cut_segments = _segments_for_layer(rows, CUT_PATH_LAYER)
    missing: list[str] = []
    if not sheet_segments:
        missing.append(f"الطبقة {SHEET_OUTLINE_LAYER} الخاصة بحدود الألواح غير موجودة أو فارغة.")
    if not cut_segments:
        missing.append(f"الطبقة {CUT_PATH_LAYER} الخاصة بمسارات القطع غير موجودة أو فارغة.")
    if missing:
        raise DxfImportError(missing)

    trim_mm = max(0.0, flt(order.trim_margin_mm))
    full_board_width_cm = flt(order.board_width_cm) or flt(order.full_board_width_mm) / 10
    full_board_length_cm = flt(order.board_length_cm) or flt(order.full_board_length_mm) / 10
    if full_board_width_cm <= 0 or full_board_length_cm <= 0:
        raise DxfImportError("أبعاد اللوح في الطلب غير صالحة. حدّد عرض وطول اللوح قبل رفع DXF.")
    trim_cm = trim_mm / 10.0
    usable_board_width_cm = max(0.0, full_board_width_cm - (2 * trim_cm))
    usable_board_length_cm = max(0.0, full_board_length_cm - (2 * trim_cm))
    if usable_board_width_cm <= 0 or usable_board_length_cm <= 0:
        raise DxfImportError("هامش التشذيب أكبر من أبعاد اللوح ولا توجد مساحة صالحة للقص.")

    sheet_contours = assemble_contours(sheet_segments, CONNECTIVITY_TOLERANCE_MM)
    sheets = _validate_sheet_contours(
        sheet_contours,
        expected_width_mm=full_board_width_cm * 10.0,
        expected_height_mm=full_board_length_cm * 10.0,
    )
    cut_contours = assemble_contours(cut_segments, CONNECTIVITY_TOLERANCE_MM)
    pieces = _extract_pieces(
        cut_contours,
        sheets=sheets,
        trim_mm=trim_mm,
        usable_width_cm=usable_board_width_cm,
        usable_length_cm=usable_board_length_cm,
    )

    expected_count = len(_expected_order_pieces(order))
    if len(pieces) != expected_count:
        raise DxfImportError(
            f"عدد مسارات القطع المغلقة في DXF هو {len(pieces)} بينما الطلب يتطلب {expected_count} قطعة بالضبط."
        )

    _validate_piece_spacing(pieces, kerf_mm=max(0.0, flt(order.kerf_mm)))
    labeled = _match_pieces_to_order(pieces, order)
    by_id = {int(piece["id"]): piece for piece in labeled}
    for sheet in sheets:
        sheet["pieces"] = [by_id[int(piece["id"])] for piece in sheet["pieces"]]
        sheet["full_width_cm"] = _num(sheet["full_width_mm"]) / 10.0
        sheet["full_length_cm"] = _num(sheet["full_height_mm"]) / 10.0
        sheet["usable_width_cm"] = usable_board_width_cm
        sheet["usable_length_cm"] = usable_board_length_cm
        sheet["w"] = usable_board_width_cm
        sheet["h"] = usable_board_length_cm
        sheet["source_type"] = "Full Board"

    geometry_by_piece_id = {int(piece["id"]): piece["_outline_cm"] for piece in labeled}
    all_public_pieces = [_public_piece(piece) for piece in labeled]
    public_by_id = {int(piece["id"]): piece for piece in all_public_pieces}
    used_area_m2 = sum(flt(piece.get("area_m2")) for piece in all_public_pieces)
    total_board_area_m2 = len(sheets) * (full_board_width_cm * full_board_length_cm) / 10000.0
    waste_area_m2 = max(0.0, total_board_area_m2 - used_area_m2)

    snapshot = {
        "engine_version": "dxf-import-v2",
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
                "sheet_no": sheet["sheet_no"],
                "source_type": sheet["source_type"],
                "full_width_cm": sheet["full_width_cm"],
                "full_length_cm": sheet["full_length_cm"],
                "usable_width_cm": sheet["usable_width_cm"],
                "usable_length_cm": sheet["usable_length_cm"],
                "w": sheet["w"],
                "h": sheet["h"],
                "pieces": [public_by_id[int(piece["id"])] for piece in sheet["pieces"]],
            }
            for sheet in sheets
        ],
        "unplaced": [],
        "validation": {"is_valid": True, "errors": []},
    }
    snapshot["validation"] = validate_imported_plan(
        snapshot,
        order,
        geometry_by_piece_id=geometry_by_piece_id,
    )
    if not snapshot["validation"]["is_valid"]:
        raise DxfImportError(snapshot["validation"]["errors"])
    return snapshot


__all__ = [
    "CUT_PATH_LAYER",
    "DIMENSION_TOLERANCE_MM",
    "DxfImportError",
    "SHEET_OUTLINE_LAYER",
    "TOLERANCE_MM",
    "parse_production_dxf",
    "validate_imported_plan",
]
