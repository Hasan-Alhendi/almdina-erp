from __future__ import annotations

import os
from collections import Counter
from typing import Any, Sequence

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.dxf_default_layer import (
    DESIGNER_DEFAULT_LAYER,
    classify_default_layer_polygons,
    polygon_to_segments,
)
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
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    serialize_geometry_from_cm,
    serialize_overlay_geometry_from_cm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    ContourCandidate,
    DxfTopologyError,
    ExpectedPieceEvidence,
    PartGeometry,
    PlacedPartGeometry,
    ResolvedTopology,
    resolve_contour_ownership,
    validate_material_layout,
)
from almdina_erp.almdina_erp.domain.cutting.extra_overlays import (
    ExtraOverlayCandidate,
    ExtraOverlayError,
    ExtraOverlayHost,
    assign_extra_overlays,
    dedupe_overlay_points,
    OVERLAY_HOST_MARGIN_MM,
)
from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    ManufacturingRequirementsError,
    require_cut_dimension_cm,
)
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    canonicalize_snapshot_sources,
    validate_source_resource_homogeneity,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    EXTRA_ADDON_FIELD_BY_CODE,
    EXTRA_OVERLAY_LAYER_BY_KIND,
    EXTRA_OVERLAY_LAYER_NAMES,
    extra_overlay_layer_for_kind,
    physical_cut_quantity,
)
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import (
    DxfReadError,
    SUPPORTED_DXF_ENTITY_TYPES,
    read_dxf_geometry,
)

SHEET_OUTLINE_LAYER = "SHEET_OUTLINE"
CUT_PATH_LAYER = "CUT_PATH"
OFFCUT_LAYER = "OFFCUT"
SHEETS_PER_ROW = 2
SHEET_GAP_MM = 200
CONNECTIVITY_TOLERANCE_MM = 1.5
DIMENSION_TOLERANCE_MM = 2.0
KERF_NUMERIC_TOLERANCE_MM = 0.1
GEOMETRY_TOLERANCE_MM = 0.25
MAX_DIAGNOSTIC_LAYERS = 8
MAX_DIAGNOSTIC_LAYER_NAME_LENGTH = 64
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


def _format_size_counts(counts: Counter[str], *, limit: int = 10) -> str:
    if not counts:
        return "لا توجد"
    visible = [
        f"{size} (×{qty})" if qty > 1 else size
        for size, qty in counts.most_common(limit)
    ]
    suffix = " ..." if len(counts) > limit else ""
    return "، ".join(visible) + suffix


def _bbox_size_label_cm(points: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> str:
    min_x, min_y, max_x, max_y = bbox(points)
    return f"{_format_cm((max_x - min_x) / 10.0)} × {_format_cm((max_y - min_y) / 10.0)} سم"


def _cut_topology_mismatch_details(
    candidates: tuple[ContourCandidate, ...],
    order: Any,
) -> str:
    dxf_sizes = _format_size_counts(
        Counter(_bbox_size_label_cm(candidate.polygon) for candidate in candidates)
    )
    expected_sizes = _format_size_counts(
        Counter(
            f"{_format_cm(piece['width_cm'])} × {_format_cm(piece['length_cm'])} سم"
            for piece in _expected_order_pieces(order)
        )
    )
    parts = [
        f"مقاسات DXF: {dxf_sizes}.",
        f"مقاسات القص المطلوبة: {expected_sizes}.",
        "ارسم بمقاس القص المحفوظ وليس المقاس النهائي، ولا تترك مسارات إضافية على CUT_PATH.",
    ]
    parts.extend(_finished_size_hints(candidates, order)[:2])
    parts.extend(_near_miss_size_hints(candidates, order)[:2])
    return " ".join(parts)


def _size_matches(width: float, height: float, expected_w: float, expected_h: float, *, tol: float) -> bool:
    return abs(width - expected_w) <= tol and abs(height - expected_h) <= tol


def _finished_size_hints(
    candidates: tuple[ContourCandidate, ...],
    order: Any,
) -> list[str]:
    expected = _expected_order_pieces(order)
    tol = DIMENSION_TOLERANCE_MM / 10.0
    hints: list[str] = []
    seen: set[tuple[object, ...]] = set()
    for contour in candidates:
        min_x, min_y, max_x, max_y = bbox(contour.polygon)
        width_cm = (max_x - min_x) / 10.0
        height_cm = (max_y - min_y) / 10.0
        for piece in expected:
            finished_w = _num(piece.get("finished_width_cm"))
            finished_h = _num(piece.get("finished_length_cm"))
            if finished_w <= 0 or finished_h <= 0:
                continue
            matches_finished = _size_matches(
                width_cm, height_cm, finished_w, finished_h, tol=tol
            ) or (
                bool(piece["allow_rotation"])
                and _size_matches(width_cm, height_cm, finished_h, finished_w, tol=tol)
            )
            matches_cut = _size_matches(
                width_cm, height_cm, piece["width_cm"], piece["length_cm"], tol=tol
            ) or (
                bool(piece["allow_rotation"])
                and _size_matches(width_cm, height_cm, piece["length_cm"], piece["width_cm"], tol=tol)
            )
            key = (piece["source_piece_no"], _bbox_size_label_cm(contour.polygon))
            if matches_finished and not matches_cut and key not in seen:
                seen.add(key)
                hints.append(
                    f"محيط {_bbox_size_label_cm(contour.polygon)} يطابق المقاس النهائي للدرفة "
                    f"{piece['source_piece_no']} وليس مقاس القص "
                    f"{_format_cm(piece['width_cm'])} × {_format_cm(piece['length_cm'])} سم."
                )
    return hints


def _near_miss_size_hints(
    candidates: tuple[ContourCandidate, ...],
    order: Any,
) -> list[str]:
    expected = _expected_order_pieces(order)
    match_tol = DIMENSION_TOLERANCE_MM / 10.0
    near_tol = 1.5
    hints: list[str] = []
    seen: set[tuple[str, str]] = set()
    for contour in candidates:
        min_x, min_y, max_x, max_y = bbox(contour.polygon)
        width_cm = (max_x - min_x) / 10.0
        height_cm = (max_y - min_y) / 10.0
        if any(
            _size_matches(width_cm, height_cm, piece["width_cm"], piece["length_cm"], tol=match_tol)
            or (
                bool(piece["allow_rotation"])
                and _size_matches(width_cm, height_cm, piece["length_cm"], piece["width_cm"], tol=match_tol)
            )
            for piece in expected
        ):
            continue
        dxf_label = _bbox_size_label_cm(contour.polygon)
        for piece in expected:
            orientations = [(piece["width_cm"], piece["length_cm"])]
            if piece["allow_rotation"]:
                orientations.append((piece["length_cm"], piece["width_cm"]))
            for expected_w, expected_h in orientations:
                delta_w = abs(width_cm - expected_w)
                delta_h = abs(height_cm - expected_h)
                if max(delta_w, delta_h) > near_tol or (delta_w <= match_tol and delta_h <= match_tol):
                    continue
                key = (dxf_label, piece["label"])
                if key in seen:
                    continue
                seen.add(key)
                hints.append(
                    f"محيط {dxf_label} قريب من مقاس القص {piece['label']} "
                    f"({_format_cm(piece['width_cm'])} × {_format_cm(piece['length_cm'])} سم) "
                    f"بفرق {_format_mm(delta_w * 10.0)} × {_format_mm(delta_h * 10.0)} مم."
                )
    return hints


def _topology_error_message(
    error: DxfTopologyError,
    *,
    kerf_mm: float = 0.0,
    details: str = "",
) -> str:
    first = error.first_key if error.first_key is not None else "؟"
    second = error.second_key if error.second_key is not None else "؟"
    if error.code == "EXPECTED_PIECE_MISMATCH":
        message = (
            "لا يمكن مطابقة محيطات CUT_PATH المغلقة مع قطع الطلب المطلوبة. "
            "تأكد من مقاسات محيطات القطع ومن أن المسارات الإضافية هي فتحات داخلية فقط."
        )
        return f"{message} {details}".strip()
    if error.code == "AMBIGUOUS_CONTOUR_OWNERSHIP":
        return (
            "تركيب مسارات CUT_PATH ملتبس فعليًا: يوجد مسار داخلي يمكن اعتباره فتحة أو قطعة مستقلة من الطلب. "
            "افصل القطعة المستقلة عن الفتحة أو اجعل الفتحة مملوكة بوضوح لمحيط خارجي واحد ثم أعد الرفع."
        )
    if error.code == "UNRESOLVED_CONTOUR_OWNERSHIP":
        return (
            "تعذر تحديد القطع والفتحات الداخلية في CUT_PATH بشكل مؤكد. "
            "تأكد أن كل فتحة مغلقة بالكامل داخل قطعة واحدة، وأن أي قطعة موضوعة داخل الفتحة لا تلامس حافتها ولا تتقاطع مع مادة القطعة."
        )
    if error.code == "INVALID_PART_TOPOLOGY":
        return (
            "بنية إحدى القطع أو فتحاتها الداخلية غير صالحة. "
            "يجب أن تكون الحدود مغلقة، غير متقاطعة، وأن تبقى كل فتحة بالكامل داخل محيط القطعة."
        )
    if error.code == "MATERIAL_FOOTPRINT_OVERLAP":
        return (
            f"القطعتان {first} و{second} تتداخلان في مادة اللوح. "
            "وجود القطعة داخل المستطيل الخارجي لقطعة أخرى مسموح فقط عندما تكون بالكامل داخل فتحة داخلية صالحة."
        )
    if error.code == "HOLE_CLEARANCE_VIOLATION":
        return (
            f"القطعتان {first} و{second}: القطعة الموضوعة داخل الفتحة قريبة من حافة الفتحة أكثر من المسموح. "
            f"حافظ على مسافة Kerf لا تقل عن {_format_mm(kerf_mm)} مم من حدود الفتحة."
        )
    if error.code == "PART_CLEARANCE_VIOLATION":
        return (
            f"المسافة بين القطعتين {first} و{second} أقل من Kerf المطلوب "
            f"({_format_mm(kerf_mm)} مم). افصل القطعتين ثم أعد الرفع."
        )
    return "تعذر التحقق من بنية القطع والفتحات الداخلية في DXF. صحح الرسم ثم أعد الرفع."


def _overlay_error_message(error: ExtraOverlayError) -> str:
    layer = error.layer or "؟"
    kind_name = _OVERLAY_KIND_AR.get(error.kind, layer)
    door = _overlay_door_label(error)
    if error.code == "extra_overlay_on_non_extra":
        return (
            f"العلامة على الطبقة {layer} تقع على درفة ليست Extra. "
            "ضع علامات اللاينر وفرزة الظهر ومسكة الغطس داخل درفة Extra فقط."
        )
    if error.code == "extra_overlay_floating":
        return (
            f"العلامة على الطبقة {layer} ليست بالكامل داخل درفة Extra واحدة. "
            "ضع العلامة بالكامل داخل درفة Extra ثم أعد الرفع."
        )
    if error.code == "extra_overlay_spans_hosts":
        return (
            f"العلامة على الطبقة {layer} تمتد فوق أكثر من درفة. "
            "ضع كل علامة داخل درفة Extra واحدة ثم أعد الرفع."
        )
    if error.code == "extra_overlay_addon_not_selected":
        return (
            f"{door}العلامة على الطبقة {layer} ({kind_name}) مرسومة دون تفعيل الخانة المطابقة في جدول القياسات. "
            "أزل العلامة من الرسم أو فعّل الخانة في صف Extra ثم احفظ الطلب وأعد الرفع."
        )
    if error.code == "extra_overlay_addon_missing":
        return (
            f"{door}خانة {kind_name} مفعّلة في جدول القياسات، لكن ملف DXF لا يحتوي علامة على الطبقة {layer} داخل هذه الدرفة. "
            f"أضف علامة {kind_name} على الطبقة {layer} داخل درفة Extra ثم أعد الرفع."
        )
    if error.code == "extra_overlay_addon_duplicate":
        return (
            f"{door}خانة {kind_name} مفعّلة مرة واحدة في جدول القياسات، لكن ملف DXF يحتوي أكثر من علامة على الطبقة {layer} داخل هذه الدرفة. "
            "اترك علامة واحدة مطابقة للخانة ثم أعد الرفع."
        )
    if error.code == "extra_overlay_invalid_path":
        return (
            f"العلامة على الطبقة {layer} أقصر من أن تُقرأ. "
            "ارسم خطًا أو مسارًا واضحًا ثم أعد الرفع."
        )
    return f"تعذر التحقق من علامات Extra على الطبقة {layer}. صحح الرسم ثم أعد الرفع."


_OVERLAY_KIND_AR = {
    "liner": "اللاينر",
    "back_groove": "فرزة الظهر",
    "recessed_handle_cutout": "مسكة الغطس",
}


def _overlay_door_label(error: ExtraOverlayError) -> str:
    label = str(error.label or error.host_key or "").strip()
    if not label:
        return ""
    return f"درفة Extra رقم {label}: "


def _lwpolyline_segments(current: dict[str, Any]) -> list[dict[str, Any]]:
    layer = str(current.get("layer") or "").strip()
    points = list(current.get("points") or [])
    if not layer or len(points) < 2:
        return []
    if current.get("closed") and points[0] != points[-1]:
        points.append(points[0])
    segments: list[dict[str, Any]] = []
    for start, end in zip(points, points[1:]):
        if start == end:
            continue
        segments.append(
            {
                "type": "LWPOLYLINE",
                "layer": layer,
                "x1": start[0],
                "y1": start[1],
                "x2": end[0],
                "y2": end[1],
            }
        )
    return segments


def _flush_ascii_entity(
    entity_type: str,
    current: dict[str, Any],
    entities: list[dict[str, Any]],
    *,
    section: str,
) -> None:
    if section not in {"", "ENTITIES"}:
        return
    if current.get("paperspace"):
        return
    if entity_type == "LINE" and current:
        entities.append(current)
        return
    if entity_type == "LWPOLYLINE" and current:
        entities.extend(_lwpolyline_segments(current))


def _parse_r12_lines(content: str) -> list[dict[str, Any]]:
    """Fallback parser for R12 LINE entities and AutoCAD LWPOLYLINE."""
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
    section = ""
    while idx + 1 < len(lines):
        code = lines[idx].strip()
        value = lines[idx + 1]
        idx += 2
        if code == "0":
            _flush_ascii_entity(entity_type, current, entities, section=section)
            if value == "SECTION":
                entity_type = "_SECTION"
                current = {}
            elif value in {"EOF", "ENDSEC"}:
                entity_type = ""
                current = {}
                if value == "ENDSEC":
                    section = ""
            elif value == "LINE":
                entity_type = "LINE"
                current = {"type": "LINE"}
            elif value == "LWPOLYLINE":
                entity_type = "LWPOLYLINE"
                current = {"type": "LWPOLYLINE", "points": []}
            else:
                entity_type = value
                current = {}
            continue
        if entity_type == "_SECTION" and code == "2":
            section = value.strip()
            entity_type = ""
            current = {}
            continue
        if section not in {"", "ENTITIES"}:
            continue
        if entity_type == "LINE":
            if code == "8":
                current["layer"] = value.strip()
            elif code == "67":
                current["paperspace"] = value.strip() not in {"", "0"}
            elif code == "10":
                current["x1"] = _num(value)
            elif code == "20":
                current["y1"] = _num(value)
            elif code == "11":
                current["x2"] = _num(value)
            elif code == "21":
                current["y2"] = _num(value)
            continue
        if entity_type != "LWPOLYLINE":
            continue
        if code == "8":
            current["layer"] = value.strip()
        elif code == "67":
            current["paperspace"] = value.strip() not in {"", "0"}
        elif code == "70":
            try:
                current["closed"] = bool(int(float(value.strip())) & 1)
            except ValueError:
                pass
        elif code == "10":
            current["_x"] = _num(value)
        elif code == "20":
            current.setdefault("points", []).append((current.pop("_x", 0.0), _num(value)))
    _flush_ascii_entity(entity_type, current, entities, section=section)
    return [row for row in entities if row.get("layer")]


def _read_legacy_content(file_path: str) -> str:
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError as exc:
        raise DxfImportError("تعذر قراءة ملف DXF من الخادم. أعد رفع الملف ثم حاول مرة أخرى.") from exc


def _read_normalized_geometry(file_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    content_cache: str | None = None

    def legacy_parser() -> list[dict[str, Any]]:
        nonlocal content_cache
        if content_cache is None:
            content_cache = _read_legacy_content(file_path)
        return _parse_r12_lines(content_cache)

    try:
        result = read_dxf_geometry(
            file_path,
            relevant_layers={
                SHEET_OUTLINE_LAYER,
                CUT_PATH_LAYER,
                OFFCUT_LAYER,
                DESIGNER_DEFAULT_LAYER,
                *EXTRA_OVERLAY_LAYER_NAMES,
            },
            legacy_line_parser=legacy_parser,
        )
    except DxfReadError as exc:
        raise DxfImportError(str(exc)) from exc

    unsupported = [
        item
        for item in (result.get("unsupported") or [])
        if str(item.get("layer") or "").strip().upper() != DESIGNER_DEFAULT_LAYER
    ]
    if unsupported:
        unique = sorted({f"{item['entity_type']} على {item['layer']}" for item in unsupported})
        supported = ", ".join(sorted(SUPPORTED_DXF_ENTITY_TYPES))
        raise DxfImportError(
            "يحتوي ملف DXF على عناصر غير مدعومة داخل طبقات القص: "
            + "، ".join(unique)
            + f". العناصر المدعومة هي: {supported}."
        )
    return result.get("segments") or [], result.get("diagnostics") or {}


def _normalized_segments(file_path: str) -> list[dict[str, Any]]:
    rows, _diagnostics = _read_normalized_geometry(file_path)
    return rows


def _detected_layers_message(diagnostics: dict[str, Any]) -> str:
    detected: list[str] = []
    for layer in diagnostics.get("detected_layers") or []:
        value = str(layer or "").strip()
        if not value:
            continue
        if len(value) > MAX_DIAGNOSTIC_LAYER_NAME_LENGTH:
            value = value[: MAX_DIAGNOSTIC_LAYER_NAME_LENGTH - 3] + "..."
        detected.append(value)

    if not detected:
        return "الطبقات المكتشفة: لا توجد."

    visible = detected[:MAX_DIAGNOSTIC_LAYERS]
    hidden_count = len(detected) - len(visible)
    suffix = f" (+{hidden_count})" if hidden_count > 0 else ""
    return f"الطبقات المكتشفة: {'، '.join(visible)}{suffix}."


def _missing_role_layer_guidance(diagnostics: dict[str, Any]) -> list[str]:
    detected = {
        str(layer or "").strip().upper()
        for layer in diagnostics.get("detected_layers") or []
        if str(layer or "").strip()
    }
    hints = [
        "أي طبقة غير SHEET_OUTLINE أو CUT_PATH أو OFFCUT لا تُستخدم كحدود لوح أو مسار قص. "
        "ضع مستطيل كل لوح على SHEET_OUTLINE، ومحيط الدرفة الكاملة على CUT_PATH، "
        "ومحيط الدرفة الناقصة على OFFCUT."
    ]
    if DESIGNER_DEFAULT_LAYER in detected:
        hints.append(
            "إذا لم تُرسم SHEET_OUTLINE وCUT_PATH، تُقرأ المحيطات المغلقة على الطبقة 0: "
            "مستطيل اللوح بمقاس الطلب كحدود اللوح، وباقي الدرف كمسارات قص. "
            "إذا وُجدت SHEET_OUTLINE دون CUT_PATH، الطبقة 0 تُقرأ كـCUT_PATH. "
            "طبقات along وPIECES لا تُعد قصًا."
        )
    found_overlays = [
        extra_overlay_layer_for_kind(kind)
        for kind, layer_name in EXTRA_OVERLAY_LAYER_BY_KIND.items()
        if layer_name.strip().upper() in detected
    ]
    if found_overlays:
        hints.append(
            "طبقات علامات Extra ("
            + "، ".join(found_overlays)
            + ") تُقرأ فوق درفة Extra فقط، ولا تغني عن طبقات اللوح والقص."
        )
    return hints


def _segments_for_layer(rows: list[dict[str, Any]], layer: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    wanted = str(layer or "").strip().upper()
    return [
        (row["start"], row["end"])
        for row in rows
        if str(row.get("layer") or "").strip().upper() == wanted
    ]


def _overlay_rows_for_layer(rows: list[dict[str, Any]], layer: str) -> list[dict[str, Any]]:
    wanted = str(layer or "").strip().upper()
    return [
        row
        for row in rows
        if str(row.get("layer") or "").strip().upper() == wanted
    ]


def _polyline_from_ordered_segments(
    segments: Sequence[dict[str, Any]],
) -> tuple[tuple[float, float], ...]:
    if not segments:
        return ()
    points = [tuple(segments[0]["start"])]
    for row in segments:
        points.append(tuple(row["end"]))
    return tuple((float(point[0]), float(point[1])) for point in points)


def _overlay_source_paths(
    rows: list[dict[str, Any]],
    layer_name: str,
) -> tuple[tuple[tuple[tuple[tuple[float, float], ...], bool], ...], tuple[str, ...]]:
    """Keep polyline/curve marks as original DXF entities; assemble LINE networks only.

    Handle Recess is often one open LWPOLYLINE whose vertices sit closer than the
    cut-path connectivity tolerance. Assembling those flattened segments as a
    graph falsely reports a branch. LINE rectangles stay assembled from edges.
    """
    layer_rows = _overlay_rows_for_layer(rows, layer_name)
    grouped: dict[int, list[dict[str, Any]]] = {}
    line_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    ungrouped: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for row in layer_rows:
        entity_type = str(row.get("entity_type") or "").strip().upper()
        entity_id = row.get("entity_id")
        if entity_type == "LINE":
            line_segments.append((row["start"], row["end"]))
            continue
        if entity_id is None:
            ungrouped.append((row["start"], row["end"]))
            continue
        grouped.setdefault(int(entity_id), []).append(row)

    paths: list[tuple[tuple[tuple[float, float], ...], bool]] = []
    errors: list[str] = []
    for entity_id in sorted(grouped):
        entity_rows = grouped[entity_id]
        points = _polyline_from_ordered_segments(entity_rows)
        closed = bool(entity_rows[0].get("closed"))
        paths.append((points, closed))
    for source in (line_segments, ungrouped):
        if not source:
            continue
        tolerance = (
            CONNECTIVITY_TOLERANCE_MM if source is line_segments else GEOMETRY_TOLERANCE_MM
        )
        for contour_no, contour in enumerate(assemble_contours(source, tolerance), start=1):
            if contour.get("branched"):
                errors.append(
                    f"علامة {layer_name} رقم {contour_no} تحتوي على تفرع أو خطوط زائدة "
                    "ولا تشكل علامة واحدة."
                )
                continue
            points = tuple(tuple(point) for point in (contour.get("points") or ()))
            closed = bool(contour.get("closed"))
            paths.append((points, closed))
    return tuple(paths), tuple(errors)


def _closed_polygons_from_segments(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    polygons: list[tuple[tuple[float, float], ...]] = []
    for contour in assemble_contours(segments, CONNECTIVITY_TOLERANCE_MM):
        if contour.get("branched") or not contour.get("closed"):
            continue
        points = simplify_polygon(contour.get("points") or [], GEOMETRY_TOLERANCE_MM)
        if validate_polygon(points, GEOMETRY_TOLERANCE_MM):
            continue
        polygons.append(tuple(tuple(point) for point in points))
    return tuple(polygons)


def _same_polygon_geometry(
    first: Sequence[tuple[float, float]],
    second: Sequence[tuple[float, float]],
    *,
    tolerance: float,
) -> bool:
    """Compare closed contours independent of start vertex and winding."""
    left = tuple(simplify_polygon(first, tolerance))
    right = tuple(simplify_polygon(second, tolerance))
    if len(left) != len(right) or not left:
        return False

    def matches(candidate: Sequence[tuple[float, float]]) -> bool:
        for start in range(len(candidate)):
            if all(
                abs(left[index][0] - candidate[(start + index) % len(candidate)][0]) <= tolerance
                and abs(left[index][1] - candidate[(start + index) % len(candidate)][1]) <= tolerance
                for index in range(len(left))
            ):
                return True
        return False

    return matches(right) or matches(tuple(reversed(right)))


def _offcut_piece_indexes(
    pieces: Sequence[dict[str, Any]],
    offcut_polygons: Sequence[Sequence[tuple[float, float]]],
) -> set[int]:
    """Map OFFCUT contours to exactly one imported piece, or fail closed."""
    marked: set[int] = set()
    for polygon_no, polygon in enumerate(offcut_polygons, start=1):
        matches = [
            index
            for index, piece in enumerate(pieces)
            if _same_polygon_geometry(
                piece.get("_outline_mm") or (),
                polygon,
                tolerance=GEOMETRY_TOLERANCE_MM,
            )
        ]
        if len(matches) != 1:
            raise DxfImportError(
                f"محيط OFFCUT رقم {polygon_no} لا يرتبط بقطعة فيزيائية واحدة بشكل مؤكد. "
                "يجب أن يطابق محيط OFFCUT محيط قطعة قص واحدة تمامًا دون تداخل أو تخمين."
            )
        marked.add(matches[0])
    return marked


def _default_layer_role_segments(
    rows: list[dict[str, Any]],
    *,
    expected_width_mm: float,
    expected_height_mm: float,
    overlays: Sequence[ExtraOverlayCandidate],
    infer_sheets: bool = True,
) -> tuple[
    list[tuple[tuple[float, float], tuple[float, float]]],
    list[tuple[tuple[float, float], tuple[float, float]]],
]:
    polygons = _closed_polygons_from_segments(
        _segments_for_layer(rows, DESIGNER_DEFAULT_LAYER)
    )
    if not polygons:
        return [], []
    sheets, cuts = classify_default_layer_polygons(
        polygons,
        expected_width_mm=expected_width_mm,
        expected_height_mm=expected_height_mm,
        overlays=overlays,
        geometry_tolerance=CONNECTIVITY_TOLERANCE_MM,
        dimension_tolerance=DIMENSION_TOLERANCE_MM,
        infer_sheets=infer_sheets,
    )
    sheet_segments = [
        segment
        for polygon in sheets
        for segment in polygon_to_segments(polygon)
    ]
    cut_segments = [
        segment
        for polygon in cuts
        for segment in polygon_to_segments(polygon)
    ]
    return sheet_segments, cut_segments


def _expected_order_pieces(order: Any) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    for group_index, row in enumerate(order.pieces or [], start=1):
        try:
            cut_width_cm = require_cut_dimension_cm(
                getattr(row, "cut_width_cm", None), fieldname="cut_width_cm"
            )
            cut_length_cm = require_cut_dimension_cm(
                getattr(row, "cut_length_cm", None), fieldname="cut_length_cm"
            )
        except ManufacturingRequirementsError as exc:
            raise DxfImportError(
                f"مقاسات القص التصنيعية للقطعة رقم {group_index} غير محفوظة أو غير صالحة. "
                "احفظ الطلب لإعادة تثبيت مقاسات القص ثم أعد رفع DXF."
            ) from exc
        finished_width_cm = getattr(row, "finished_width_cm", None)
        finished_length_cm = getattr(row, "finished_length_cm", None)
        if finished_width_cm is None:
            finished_width_cm = getattr(row, "width_cm", 0)
        if finished_length_cm is None:
            finished_length_cm = getattr(row, "length_cm", 0)
        selected_codes = tuple(
            code
            for code, attr in EXTRA_ADDON_FIELD_BY_CODE.items()
            if bool(cint(getattr(row, attr, 0)))
        )
        for copy_no in range(
            1,
            physical_cut_quantity(
                cint(row.qty),
                full_door_double=bool(cint(getattr(row, "extra_full_door_double", 0))),
            )
            + 1,
        ):
            expected.append(
                {
                    "label": f"{group_index}.{copy_no}",
                    "width_cm": cut_width_cm,
                    "length_cm": cut_length_cm,
                    "finished_width_cm": _num(finished_width_cm),
                    "finished_length_cm": _num(finished_length_cm),
                    "allow_rotation": cint(row.allow_rotation),
                    "piece_type": row.piece_type or "Regular",
                    "source_piece_no": group_index,
                    "copy_no": copy_no,
                    "selected_codes": selected_codes,
                }
            )
    return expected


def _expected_topology_evidence(order: Any) -> tuple[ExpectedPieceEvidence, ...]:
    return tuple(
        ExpectedPieceEvidence(
            width=piece["width_cm"] * 10.0,
            height=piece["length_cm"] * 10.0,
            allow_rotation=bool(piece["allow_rotation"]),
            arbitrary_outline=piece["piece_type"] == "Special",
        )
        for piece in _expected_order_pieces(order)
    )


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


def _legacy_expected_piece_match(
    *,
    width_cm: float,
    height_cm: float,
    expected: list[dict[str, Any]],
    unmatched_indexes: list[int],
) -> tuple[int | None, bool, dict[str, Any] | None]:
    """Match callers that do not yet carry the topology-owned identity index."""
    direct_index = next(
        (
            index
            for index in unmatched_indexes
            if _direct_dimensions_match(
                width_cm,
                height_cm,
                expected[index]["width_cm"],
                expected[index]["length_cm"],
            )
        ),
        None,
    )
    rotated_index = next(
        (
            index
            for index in unmatched_indexes
            if expected[index]["allow_rotation"]
            and _rotated_dimensions_match(
                width_cm,
                height_cm,
                expected[index]["width_cm"],
                expected[index]["length_cm"],
            )
        ),
        None,
    )
    expected_index = direct_index if direct_index is not None else rotated_index
    if expected_index is not None:
        return expected_index, direct_index is None, None

    forbidden_rotation = next(
        (
            expected[index]
            for index in unmatched_indexes
            if not expected[index]["allow_rotation"]
            and _rotated_dimensions_match(
                width_cm,
                height_cm,
                expected[index]["width_cm"],
                expected[index]["length_cm"],
            )
        ),
        None,
    )
    return None, False, forbidden_rotation


def _topology_piece_rotation(
    width_cm: float,
    height_cm: float,
    candidate: dict[str, Any],
) -> bool:
    if _direct_dimensions_match(
        width_cm,
        height_cm,
        candidate["width_cm"],
        candidate["length_cm"],
    ):
        return False
    return bool(
        candidate["allow_rotation"]
        and _rotated_dimensions_match(
            width_cm,
            height_cm,
            candidate["width_cm"],
            candidate["length_cm"],
        )
    )


def _match_pieces_to_order(pieces: list[dict[str, Any]], order: Any) -> list[dict[str, Any]]:
    expected = _expected_order_pieces(order)
    unmatched_indexes = list(range(len(expected)))
    labeled: list[dict[str, Any]] = []
    errors: list[str] = []

    for piece_index, piece in enumerate(pieces, start=1):
        width_cm = _num(piece.get("w"))
        height_cm = _num(piece.get("h"))
        expected_index = piece.get("_expected_piece_index")
        if expected_index is not None:
            try:
                expected_index = int(expected_index)
            except (TypeError, ValueError):
                expected_index = -1
            if expected_index not in unmatched_indexes:
                errors.append(
                    f"تعذر ربط القطعة رقم {piece_index} بهوية قطعة واحدة في الطلب."
                )
                continue
            candidate = expected[expected_index]
            rotated = _topology_piece_rotation(
                width_cm,
                height_cm,
                candidate,
            )
        else:
            expected_index, rotated, forbidden_rotation = _legacy_expected_piece_match(
                width_cm=width_cm,
                height_cm=height_cm,
                expected=expected,
                unmatched_indexes=unmatched_indexes,
            )

            if expected_index is None:
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

            candidate = expected[expected_index]

        unmatched_indexes.remove(expected_index)

        piece["label"] = candidate["label"]
        piece["source_piece_no"] = candidate["source_piece_no"]
        piece["copy_no"] = candidate["copy_no"]
        piece["original_w"] = candidate["width_cm"]
        piece["original_h"] = candidate["length_cm"]
        piece["rotated"] = rotated
        piece["piece_type"] = candidate["piece_type"]
        piece["_extra_selected_codes"] = tuple(candidate.get("selected_codes") or ())
        if "_material_area_m2" in piece:
            piece["area_m2"] = round(_num(piece["_material_area_m2"]), 4)
        else:
            piece["area_m2"] = round((width_cm * height_cm) / 10000.0, 4)
        labeled.append(piece)

    if unmatched_indexes:
        preview = "، ".join(
            f"{expected[index]['label']} ({_format_cm(expected[index]['width_cm'])} × {_format_cm(expected[index]['length_cm'])} سم)"
            for index in unmatched_indexes[:6]
        )
        suffix = " ..." if len(unmatched_indexes) > 6 else ""
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


def _validated_cut_candidates(contours: list[dict[str, object]]) -> tuple[ContourCandidate, ...]:
    errors: list[str] = []
    candidates: list[ContourCandidate] = []
    for contour_no, contour in enumerate(contours, start=1):
        raw_points = contour.get("points") or []
        if contour.get("branched"):
            errors.append(f"مسار القطعة/الفتحة رقم {contour_no} يحتوي على تفرع أو خطوط زائدة ولا يشكل محيطًا واحدًا.")
            continue
        if not contour.get("closed"):
            errors.append(
                f"مسار القطعة/الفتحة رقم {contour_no} غير مغلق على طبقة {CUT_PATH_LAYER}. "
                "أغلق المحيط بالكامل ثم أعد الرفع."
            )
            continue
        points_mm = simplify_polygon(raw_points, GEOMETRY_TOLERANCE_MM)
        geometry_errors = validate_polygon(points_mm, GEOMETRY_TOLERANCE_MM)
        if "self_intersection" in geometry_errors:
            errors.append(
                f"هندسة القطعة/الفتحة رقم {contour_no} تتقاطع مع نفسها. "
                "عدّل المحيط بحيث لا تتقاطع أضلاعه/منحنياته."
            )
            continue
        if geometry_errors:
            errors.append(
                f"هندسة القطعة/الفتحة رقم {contour_no} غير صالحة: المحيط لا يكوّن مساحة قطع مغلقة صحيحة."
            )
            continue
        candidates.append(ContourCandidate(key=contour_no, polygon=tuple(points_mm)))
    if errors:
        raise DxfImportError(errors)
    return tuple(candidates)


def _resolve_cut_topology(contours: list[dict[str, object]], order: Any) -> ResolvedTopology:
    candidates = _validated_cut_candidates(contours)
    try:
        return resolve_contour_ownership(
            candidates,
            _expected_topology_evidence(order),
            dimension_tolerance=DIMENSION_TOLERANCE_MM,
            geometry_tolerance=GEOMETRY_TOLERANCE_MM,
        )
    except DxfTopologyError as exc:
        details = ""
        if exc.code == "EXPECTED_PIECE_MISMATCH":
            details = _cut_topology_mismatch_details(candidates, order)
        raise DxfImportError(
            _topology_error_message(
                exc,
                kerf_mm=max(0.0, flt(order.kerf_mm)),
                details=details,
            )
        ) from exc


def _extract_pieces(
    topology: ResolvedTopology,
    *,
    sheets: list[dict[str, Any]],
    trim_mm: float,
    usable_width_cm: float,
    usable_length_cm: float,
) -> list[dict[str, Any]]:
    errors: list[str] = []
    pieces: list[dict[str, Any]] = []
    for piece_no, part in enumerate(topology.parts, start=1):
        points_mm = list(part.geometry.outer)
        target_sheet = _sheet_for_piece(points_mm, sheets)
        if target_sheet is None:
            errors.append(
                f"القطعة رقم {piece_no} ليست موجودة بالكامل داخل حدود لوح واحد من طبقة {SHEET_OUTLINE_LAYER}."
            )
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

        holes_mm = [list(hole) for hole in part.geometry.holes]
        holes_cm = [
            _to_plan_points(hole, sheet=target_sheet, trim_mm=trim_mm)
            for hole in holes_mm
        ]
        min_x, min_y, max_x, max_y = bbox(plan_points)
        piece = {
            "id": piece_no,
            "x": min_x,
            "y": min_y,
            "w": max_x - min_x,
            "h": max_y - min_y,
            "piece_type": "Regular" if is_axis_aligned_rectangle(points_mm, CONNECTIVITY_TOLERANCE_MM) else "Special",
            "_outline_mm": points_mm,
            "_holes_mm": holes_mm,
            "_outline_cm": plan_points,
            "_holes_cm": holes_cm,
            "_sheet_no": target_sheet["sheet_no"],
            "_expected_piece_index": part.expected_piece_index,
        }
        material_area_mm2 = polygon_area(points_mm) - sum(
            polygon_area(hole) for hole in holes_mm
        )
        piece["_material_area_m2"] = max(0.0, material_area_mm2) / 1_000_000.0
        pieces.append(piece)
        target_sheet["pieces"].append(piece)
    if errors:
        raise DxfImportError(errors)
    return pieces


def _piece_material_geometry(piece: dict[str, Any], *, units: str) -> PartGeometry:
    outer_key = f"_outline_{units}"
    holes_key = f"_holes_{units}"
    return PartGeometry(
        outer=tuple(tuple(point) for point in piece.get(outer_key) or ()),
        holes=tuple(
            tuple(tuple(point) for point in hole)
            for hole in (piece.get(holes_key) or ())
        ),
    )


def _validate_piece_spacing(pieces: list[dict[str, Any]], *, kerf_mm: float) -> None:
    by_sheet: dict[int, list[dict[str, Any]]] = {}
    for piece in pieces:
        by_sheet.setdefault(int(piece["_sheet_no"]), []).append(piece)
    for sheet_pieces in by_sheet.values():
        placed = tuple(
            PlacedPartGeometry(
                key=int(piece["id"]),
                geometry=_piece_material_geometry(piece, units="mm"),
            )
            for piece in sheet_pieces
        )
        try:
            validate_material_layout(
                placed,
                required_clearance=max(0.0, kerf_mm),
                geometry_tolerance=GEOMETRY_TOLERANCE_MM,
                numeric_tolerance=KERF_NUMERIC_TOLERANCE_MM,
            )
        except DxfTopologyError as exc:
            raise DxfImportError(_topology_error_message(exc, kerf_mm=kerf_mm)) from exc


def _collect_extra_overlay_candidates(rows: list[dict[str, Any]]) -> tuple[ExtraOverlayCandidate, ...]:
    errors: list[str] = []
    candidates: list[ExtraOverlayCandidate] = []
    next_key = 1
    for kind, layer_name in EXTRA_OVERLAY_LAYER_BY_KIND.items():
        source_paths, source_errors = _overlay_source_paths(rows, layer_name)
        errors.extend(source_errors)
        for contour_no, (raw_points, closed_flag) in enumerate(
            source_paths,
            start=1,
        ):
            points_mm = dedupe_overlay_points(
                raw_points,
                tolerance=GEOMETRY_TOLERANCE_MM,
            )
            if len(points_mm) < 2:
                errors.append(
                    f"علامة {layer_name} رقم {contour_no} أقصر من أن تُقرأ. "
                    "ارسم خطًا أو مسارًا واضحًا ثم أعد الرفع."
                )
                continue
            closed = bool(closed_flag) and len(points_mm) >= 3
            points_mm = dedupe_overlay_points(
                points_mm,
                tolerance=GEOMETRY_TOLERANCE_MM,
                closed=closed,
            )
            closed = closed and len(points_mm) >= 3
            candidates.append(
                ExtraOverlayCandidate(
                    key=next_key,
                    kind=kind,
                    layer=extra_overlay_layer_for_kind(kind),
                    path=points_mm,
                    closed=closed,
                )
            )
            next_key += 1
    if errors:
        raise DxfImportError(errors)
    return tuple(candidates)


def _attach_extra_overlays(
    pieces: list[dict[str, Any]],
    *,
    overlays: Sequence[ExtraOverlayCandidate],
    sheets: list[dict[str, Any]],
    trim_mm: float,
) -> None:
    hosts = tuple(
        ExtraOverlayHost(
            key=int(piece["id"]),
            piece_type=str(piece.get("piece_type") or "Regular"),
            polygon=tuple(tuple(point) for point in piece.get("_outline_mm") or ()),
            selected_codes=tuple(piece.get("_extra_selected_codes") or ()),
            label=str(piece.get("label") or piece["id"]),
        )
        for piece in pieces
    )
    if not overlays and not any(
        code in EXTRA_OVERLAY_LAYER_BY_KIND
        for host in hosts
        for code in host.selected_codes
    ):
        return
    try:
        assigned = assign_extra_overlays(
            overlays,
            hosts,
            tolerance=GEOMETRY_TOLERANCE_MM,
            host_margin=OVERLAY_HOST_MARGIN_MM,
        )
    except ExtraOverlayError as exc:
        raise DxfImportError(_overlay_error_message(exc)) from exc

    sheets_by_no = {int(sheet["sheet_no"]): sheet for sheet in sheets}
    grouped: dict[int, list] = {}
    for item in assigned:
        grouped.setdefault(int(item.host_key), []).append(item)
    for piece in pieces:
        items = grouped.get(int(piece["id"])) or []
        if not items:
            continue
        sheet = sheets_by_no[int(piece["_sheet_no"])]
        piece["overlays"] = [
            {
                "kind": item.kind,
                "layer": item.layer,
                "geometry": serialize_overlay_geometry_from_cm(
                    tuple(
                        _to_plan_points(
                            list(item.path),
                            sheet=sheet,
                            trim_mm=trim_mm,
                        )
                    ),
                    closed=item.closed,
                ),
            }
            for item in items
        ]


def _public_piece(piece: dict[str, Any]) -> dict[str, Any]:
    public_piece = {key: value for key, value in piece.items() if not key.startswith("_")}
    public_piece["geometry"] = serialize_geometry_from_cm(
        _piece_material_geometry(piece, units="cm")
    )
    return public_piece


def validate_imported_plan(
    plan: dict[str, Any],
    order: Any,
    *,
    geometry_by_piece_id: dict[int, list[tuple[float, float]]] | None = None,
    topology_by_piece_id: dict[int, PartGeometry] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    expected_count = sum(
        physical_cut_quantity(
            cint(row.qty),
            full_door_double=bool(cint(getattr(row, "extra_full_door_double", 0))),
        )
        for row in (order.pieces or [])
    )
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

        if topology_by_piece_id is not None:
            placed: list[PlacedPartGeometry] = []
            for piece in pieces:
                piece_id = int(piece.get("id") or 0)
                geometry = topology_by_piece_id.get(piece_id)
                if geometry is None:
                    errors.append(f"تعذر التحقق من هندسة القطعة {piece.get('label') or piece_id} في خطة DXF.")
                    continue
                placed.append(PlacedPartGeometry(key=piece.get("label") or piece_id, geometry=geometry))
            if len(placed) == len(pieces):
                try:
                    validate_material_layout(
                        placed,
                        required_clearance=kerf_cm,
                        geometry_tolerance=GEOMETRY_TOLERANCE_MM / 10.0,
                        numeric_tolerance=KERF_NUMERIC_TOLERANCE_MM / 10.0,
                    )
                except DxfTopologyError as exc:
                    errors.append(_topology_error_message(exc, kerf_mm=kerf_cm * 10.0))
            continue

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

    rows, diagnostics = _read_normalized_geometry(file_path)
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

    overlays = _collect_extra_overlay_candidates(rows)
    sheet_segments = _segments_for_layer(rows, SHEET_OUTLINE_LAYER)
    cut_segments = _segments_for_layer(rows, CUT_PATH_LAYER)
    offcut_segments = _segments_for_layer(rows, OFFCUT_LAYER)
    if offcut_segments:
        # OFFCUT is an input classification, not a validation bypass. Its
        # contours enter the same topology, spacing, bounds and exact-size
        # pipeline as ordinary CUT_PATH contours.
        cut_segments = [*cut_segments, *offcut_segments]
    if not sheet_segments or not cut_segments:
        fallback_sheets, fallback_cuts = _default_layer_role_segments(
            rows,
            expected_width_mm=full_board_width_cm * 10.0,
            expected_height_mm=full_board_length_cm * 10.0,
            overlays=overlays,
            infer_sheets=not sheet_segments,
        )
        if not sheet_segments:
            sheet_segments = fallback_sheets
        if not cut_segments:
            cut_segments = fallback_cuts
    missing: list[str] = []
    if not sheet_segments:
        missing.append(f"الطبقة {SHEET_OUTLINE_LAYER} الخاصة بحدود الألواح غير موجودة أو فارغة.")
    if not cut_segments:
        missing.append(f"الطبقة {CUT_PATH_LAYER} الخاصة بمسارات القطع غير موجودة أو فارغة.")
    if missing:
        missing.append(_detected_layers_message(diagnostics))
        missing.extend(_missing_role_layer_guidance(diagnostics))
        raise DxfImportError(missing)

    sheet_contours = assemble_contours(sheet_segments, CONNECTIVITY_TOLERANCE_MM)
    sheets = _validate_sheet_contours(
        sheet_contours,
        expected_width_mm=full_board_width_cm * 10.0,
        expected_height_mm=full_board_length_cm * 10.0,
    )
    cut_contours = assemble_contours(cut_segments, CONNECTIVITY_TOLERANCE_MM)
    topology = _resolve_cut_topology(cut_contours, order)
    pieces = _extract_pieces(
        topology,
        sheets=sheets,
        trim_mm=trim_mm,
        usable_width_cm=usable_board_width_cm,
        usable_length_cm=usable_board_length_cm,
    )
    offcut_polygons = _closed_polygons_from_segments(offcut_segments)
    offcut_indexes = _offcut_piece_indexes(pieces, offcut_polygons)
    for piece_index, piece in enumerate(pieces):
        if piece_index in offcut_indexes:
            piece["resource_kind"] = "OFFCUT"
            piece["offcut_source_party"] = "UNASSIGNED"
            piece["offcut_execution_party"] = "UNASSIGNED"

    expected_count = len(_expected_order_pieces(order))
    if len(pieces) != expected_count:
        raise DxfImportError(
            f"عدد مسارات القطع الفعلية في DXF هو {len(pieces)} بينما الطلب يتطلب {expected_count} قطعة بالضبط."
        )

    _validate_piece_spacing(pieces, kerf_mm=max(0.0, flt(order.kerf_mm)))
    labeled = _match_pieces_to_order(pieces, order)
    _attach_extra_overlays(
        labeled,
        overlays=overlays,
        sheets=sheets,
        trim_mm=trim_mm,
    )
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
    try:
        validate_source_resource_homogeneity(sheets)
    except OffcutPolicyError as exc:
        raise DxfImportError(
            "لا يمكن أن يحتوي نفس مصدر القص على قطع نقص وقطع من لوح كامل. "
            "ضع قطع OFFCUT كمصدر مستقل عن ألواح MDF الكاملة."
        ) from exc

    for sheet in sheets:
        sheet["resource_kind"] = (
            "OFFCUT"
            if sheet.get("pieces") and all(
                str(piece.get("resource_kind") or "FULL_BOARD").upper() == "OFFCUT"
                for piece in sheet.get("pieces") or []
            )
            else "FULL_BOARD"
        )
        sheet["offcut_source_party"] = "UNASSIGNED"
        sheet["offcut_execution_party"] = "UNASSIGNED"

    canonicalize_snapshot_sources({"sheets": sheets})

    geometry_by_piece_id = {int(piece["id"]): piece["_outline_cm"] for piece in labeled}
    topology_by_piece_id = {
        int(piece["id"]): _piece_material_geometry(piece, units="cm")
        for piece in labeled
    }
    all_public_pieces = [_public_piece(piece) for piece in labeled]
    public_by_id = {int(piece["id"]): piece for piece in all_public_pieces}
    used_area_m2 = sum(flt(piece.get("area_m2")) for piece in all_public_pieces)
    full_board_sheets = [
        sheet
        for sheet in sheets
        if str(sheet.get("resource_kind") or "FULL_BOARD").upper() == "FULL_BOARD"
    ]
    total_board_area_m2 = len(full_board_sheets) * (full_board_width_cm * full_board_length_cm) / 10000.0
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
        "required_full_boards": len(full_board_sheets),
        "sheets": [
            {
                "sheet_no": sheet["sheet_no"],
                "source_type": sheet["source_type"],
                "full_width_cm": sheet["full_width_cm"],
                "full_length_cm": sheet["full_length_cm"],
                "usable_width_cm": sheet["usable_width_cm"],
                "usable_length_cm": sheet["usable_length_cm"],
                # The UI and print output project this authoritative source
                # classification. Without it OFFCUT silently becomes a board.
                "resource_kind": sheet.get("resource_kind") or "FULL_BOARD",
                "offcut_source_party": sheet.get("offcut_source_party") or "UNASSIGNED",
                "offcut_execution_party": sheet.get("offcut_execution_party") or "UNASSIGNED",
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
        topology_by_piece_id=topology_by_piece_id,
    )
    if not snapshot["validation"]["is_valid"]:
        raise DxfImportError(snapshot["validation"]["errors"])
    return snapshot


__all__ = [
    "CUT_PATH_LAYER",
    "OFFCUT_LAYER",
    "DIMENSION_TOLERANCE_MM",
    "DxfImportError",
    "SHEET_OUTLINE_LAYER",
    "TOLERANCE_MM",
    "parse_production_dxf",
    "validate_imported_plan",
]
