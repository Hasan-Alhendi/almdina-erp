"""Arabic presenter for structured DXF validation issues.

Converts ``code + target + params`` into actionable factory messages.
Does not re-run validation or invent manufacturing decisions.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting import dxf_issue as codes
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    DxfIssueTarget,
    DxfValidationIssue,
    sort_issues,
)

_OVERLAY_KIND_AR = {
    "liner": "اللاينر",
    "back_groove": "فرزة الظهر",
    "recessed_handle_cutout": "مسكة الغطس",
}
_GEOMETRY_ERROR_AR = {
    "too_few_vertices": "عدد الرؤوس أقل من اللازم",
    "zero_area": "مساحة المسار تساوي صفرًا",
    "self_intersection": "المسار يتقاطع مع نفسه",
}


@dataclass(frozen=True, slots=True)
class PresentedDxfError:
    problem: str
    target: str
    action: str
    code: str
    category: str
    details: tuple[str, ...] = ()
    highlight: str = ""
    detail_table: tuple[tuple[str, ...], ...] = ()


def format_cm(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "؟"
    text = f"{number:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def format_mm(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "؟"
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _mm_to_cm(value: Any) -> float | None:
    try:
        return float(value) / 10.0
    except (TypeError, ValueError):
        return None


def _size_cm(width: Any, height: Any, *, from_mm: bool = False) -> str:
    if from_mm:
        width_cm = _mm_to_cm(width)
        height_cm = _mm_to_cm(height)
        if width_cm is None or height_cm is None:
            return "؟"
        pair = f"{format_cm(width_cm)} × {format_cm(height_cm)}"
        return f"\u2066{pair}\u2069 سم"
    pair = f"{format_cm(width)} × {format_cm(height)}"
    return f"\u2066{pair}\u2069 سم"


def present_target(target: DxfIssueTarget, *, params: dict[str, Any] | None = None) -> str:
    """Render target label. Contour numbers never become door numbers."""
    params = params or {}
    kind = target.kind
    if kind == codes.TARGET_CONTOUR and target.contour_no is not None:
        return f"مسار القص رقم {target.contour_no}."
    if kind == codes.TARGET_SHEET and target.sheet_no is not None:
        return f"اللوح {target.sheet_no}."
    if kind == codes.TARGET_PIECE_PAIR and target.pair_piece_nos:
        first, second = target.pair_piece_nos
        return f"الدرفتان {first} و{second}."
    if kind == codes.TARGET_CONTOUR_PAIR and target.pair_contour_nos:
        first, second = target.pair_contour_nos
        return f"مسارا القص {first} و{second}."
    if kind == codes.TARGET_LAYER and target.layer:
        return f"الطبقة {target.layer}."
    if kind == codes.TARGET_FILE:
        return "ملف DXF."
    if kind == codes.TARGET_OVERLAY:
        if target.source_piece_no is not None:
            return f"الدرفة {target.source_piece_no}."
        if target.label:
            return f"علامة الإضافة المرتبطة بالمعرّف {target.label}."
        if target.layer:
            return f"الطبقة {target.layer}."
        return "علامة إضافة."
    if kind in {codes.TARGET_PIECE, codes.TARGET_PIECE_COPY}:
        piece_no = target.source_piece_no
        if params.get("identity_unproven"):
            if target.piece_index is not None:
                return f"مسار القص رقم {target.piece_index}."
            if target.label:
                return f"القطعة ذات المعرّف {target.label}."
            return "مسار قص غير محدد."
        if piece_no is None and target.piece_index is not None:
            # piece_index without proven identity is not a door number.
            return f"مسار القص رقم {target.piece_index}." if params.get("identity_unproven") else f"القطعة رقم {target.piece_index}."
        if piece_no is None and target.label:
            return f"القطعة ذات المعرّف {target.label}."
        if piece_no is None:
            return "قطعة غير محددة."
        if target.copy_no is not None and int(target.copy_no) > 1:
            return f"الدرفة {piece_no} — النسخة {target.copy_no}."
        if params.get("ambiguous_copy"):
            return f"إحدى نسخ الدرفة {piece_no}."
        return f"الدرفة {piece_no}."
    if kind == codes.TARGET_ORDER:
        actual = params.get("actual_count")
        expected = params.get("expected_count")
        if actual is not None and expected is not None:
            return (
                f"الطلب يحتاج {expected} "
                f"{'درفة' if int(expected) == 1 else 'درفات'}، "
                f"والملف فيه {actual} "
                f"{'درفة' if int(actual) == 1 else 'درفات'}."
            )
        return "الطلب."
    if target.label:
        return f"{target.label}."
    return "غير محدد."


def _piece_noun(issue: DxfValidationIssue) -> str:
    """Choose a door noun only when the target carries proven order identity."""
    target = issue.target
    if target.kind in {codes.TARGET_CONTOUR, codes.TARGET_CONTOUR_PAIR} or issue.param("identity_unproven"):
        return "مسار القص"
    if target.source_piece_no is not None and target.kind in {
        codes.TARGET_PIECE,
        codes.TARGET_PIECE_COPY,
        codes.TARGET_OVERLAY,
    }:
        return "الدرفة"
    return "القطعة"


def _pair_nouns(issue: DxfValidationIssue) -> tuple[str, str]:
    if issue.target.kind == codes.TARGET_PIECE_PAIR and issue.target.pair_piece_nos:
        return "الدرفتان", "الدرفتين"
    if issue.target.kind in {codes.TARGET_CONTOUR_PAIR, codes.TARGET_CONTOUR} or issue.param("identity_unproven"):
        return "مسارا القص", "مساري القص"
    return "القطعتان", "القطعتين"


def _ltr_measure(value: Any, unit: str, *, millimeters: bool = False) -> str:
    text = format_mm(value) if millimeters else format_cm(value)
    return f"\u2066{text} {unit}\u2069"


def _l_notch_difference_lines(axes: Any) -> tuple[str, ...]:
    if not isinstance(axes, (list, tuple)):
        return ()
    lines: list[str] = []
    axis_names = {"width": "العرض", "length": "الطول"}
    for axis in axes:
        if not isinstance(axis, dict):
            continue
        if any(
            axis.get(key) in (None, "")
            for key in (
                "finished_remaining_cm",
                "band_mm",
                "expected_raw_cm",
                "actual_raw_cm",
                "delta_mm",
            )
        ):
            continue
        try:
            delta = float(axis.get("delta_mm"))
        except (TypeError, ValueError):
            continue
        if delta == 0:
            continue
        direction = "زيادة" if delta > 0 else "نقصان"
        name = axis_names.get(str(axis.get("axis") or ""))
        if name:
            lines.append(f"على {name}:")
        lines.extend(
            (
                f"البعد المتبقي المطلوب بعد القشاط: {_ltr_measure(axis.get('finished_remaining_cm'), 'سم')}.",
                f"سماكة القشاطات المؤثرة على هذا البعد: {_ltr_measure(axis.get('band_mm'), 'مم', millimeters=True)}.",
                f"مقاس القص الخام المطلوب: {_ltr_measure(axis.get('expected_raw_cm'), 'سم')}.",
                f"المقاس الموجود في DXF: {_ltr_measure(axis.get('actual_raw_cm'), 'سم')}.",
                f"الفرق: {_ltr_measure(abs(delta), 'مم', millimeters=True)} {direction}.",
            )
        )
    return tuple(lines)


def _action_for_context(action: str, context: str) -> str:
    if context == "upload":
        return action
    return (
        action.replace("أعد رفع الملف", "أعد تصدير DXF")
        .replace("أعد رفع DXF", "أعد تصدير DXF")
        .replace("أعد الرفع", "أعد التصدير")
    )


def _special_range_action(params: dict[str, Any]) -> str:
    min_w = params.get("allowed_min_width_cm")
    max_w = params.get("allowed_max_width_cm")
    min_h = params.get("allowed_min_height_cm")
    max_h = params.get("allowed_max_height_cm")
    if None in (min_w, max_w, min_h, max_h):
        return "اجعل Bounding Box ضمن المجال المحسوب المسموح لقطعة Special."
    return (
        f"اجعل Bounding Box ضمن {format_cm(min_w)}–{format_cm(max_w)} × "
        f"{format_cm(min_h)}–{format_cm(max_h)} سم."
    )


_LINER_SIDE_AR = {
    "edge_width_top": "أعلى",
    "edge_width_bottom": "أسفل",
    "edge_long_left": "يسار",
    "edge_long_right": "يمين",
    "edge_break": "الكسر الكامل",
    "edge_break_only": "الكسر فقط",
}


def _liner_side_label(value: object, piece_type: object) -> str:
    side = str(value or "")
    if side == "edge_break" and str(piece_type or "") == "L-Shaped Corner":
        return "زاوية L"
    return _LINER_SIDE_AR.get(side, side or "؟")


def _present_liner_mismatch(issue: DxfValidationIssue, target_text: str) -> PresentedDxfError:
    params = issue.params or {}
    piece_type = params.get("piece_type")
    code = issue.code
    name = _OVERLAY_KIND_AR.get(str(params.get("overlay_kind") or "liner"), "اللاينر")
    action = f"صحّح {name} في ملف DXF ثم أعد الرفع. لا يُعدَّل الملف تلقائيًا."
    if code == codes.LINER_WIDTH_NOT_MEASURABLE:
        problem = (
            f"عرض {name} غير قابل للقياس من مسار الطبقة. "
            "المسار خط بلا سماكة هندسية، والمطلوب "
            f"{params.get('expected') or '؟'} سم."
        )
    elif code == codes.LINER_OFFSET_MISMATCH:
        problem = (
            f"مسافة {name} عن الجهة المرجعية غير مطابقة. "
            f"المطلوب {params.get('expected') or '؟'} سم، "
            f"والمقاس من DXF {params.get('measured') or '؟'} سم."
        )
    elif code == codes.LINER_WIDTH_MISMATCH:
        problem = (
            f"عرض {name} غير مطابق. "
            f"المطلوب {params.get('expected') or '؟'} سم، "
            f"والمقاس من DXF {params.get('measured') or '؟'} سم."
        )
    elif code == codes.LINER_SIDE_MISMATCH:
        problem = (
            f"جهة {name} غير مطابقة. "
            f"المطلوب {_liner_side_label(params.get('expected'), piece_type)}، "
            f"والمقاس من DXF {_liner_side_label(params.get('measured'), piece_type)}."
        )
    else:
        problem = (
            f"مسار {name} لا يطابق الجهة المحددة "
            f"({_liner_side_label(params.get('expected'), piece_type)})."
        )
    return PresentedDxfError(problem, target_text, action, code, issue.category)


_GLASS_SIDE_AR = {
    "long_left": "اليسار",
    "long_right": "اليمين",
    "width_top": "الأعلى",
    "width_bottom": "الأسفل",
    "left": "يسار الملف",
    "right": "يمين الملف",
    "top": "أعلى الملف",
    "bottom": "أسفل الملف",
}
_GLASS_TYPE_AR = {
    "Regular": "عادية",
    "Clipped Corner": "الزاوية الكسر",
    "L-Shaped Corner": "زاوية L",
    "Special": "خاصة",
    "Glass": "بلور",
}
_GLASS_GEOMETRY_AR = {
    "too_few_vertices": "المحيط لا يكفي لتكوين مستطيل مغلق",
    "zero_area": "مساحة الفتحة صفر",
    "self_intersection": "الفتحة تتقاطع مع نفسها",
    "not_rectangle": "الفتحة ليست مستطيلاً",
}
_GLASS_ORIENTATION_AR = {
    "orientation_0": "اتجاه المطابقة: الوضع المستقيم.",
    "orientation_180": "اتجاه المطابقة: تدوير 180 درجة.",
    "orientation_cw": "اتجاه المطابقة: تدوير 90 درجة مع عقارب الساعة.",
    "orientation_ccw": "اتجاه المطابقة: تدوير 90 درجة عكس عقارب الساعة.",
}
_GLASS_CODES = {
    codes.GLASS_OPENING_MISSING,
    codes.GLASS_OPENING_UNEXPECTED,
    codes.GLASS_MULTIPLE_OPENINGS,
    codes.GLASS_OPENING_INVALID,
    codes.GLASS_MARGIN_MISMATCH,
    codes.GLASS_OPENING_OUTSIDE,
    codes.GLASS_GEOMETRY_AMBIGUOUS,
}


def _glass_number(value: Any, *, tolerance: Any = None) -> str | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    places = 3
    if tolerance not in (None, ""):
        try:
            limit = abs(float(tolerance))
        except (TypeError, ValueError):
            limit = None
        if limit is not None and abs(number) > limit and abs(float(f"{number:.3f}")) <= limit:
            places = 4
    text = f"{number:.{places}f}".rstrip("0").rstrip(".")
    return text or "0"


def _glass_mm(value: Any, *, tolerance: Any = None) -> str:
    text = _glass_number(value, tolerance=tolerance)
    if text is None:
        return "غير متاح"
    return f"\u2066{text} مم\u2069"


def _glass_signed_mm(value: Any, *, tolerance: Any = None) -> str:
    text = _glass_number(value, tolerance=tolerance)
    if text is None:
        return "غير متاح"
    number = float(value)
    if number > 0 and not text.startswith("-"):
        text = f"+{text}"
    return f"\u2066{text} مم\u2069"


def _glass_margin_text(params: Mapping[str, Any]) -> str:
    if params.get("margin_known") is False or params.get("order_margin_mm") in (None, ""):
        return "غير محفوظ"
    millimetres = _glass_mm(params.get("order_margin_mm"))
    centimetres = _glass_number(float(params.get("order_margin_mm")) / 10.0)
    if centimetres is None:
        return millimetres
    return f"{millimetres} (\u2066{centimetres} سم\u2069)"


def _glass_pair_mm(width: Any, height: Any) -> str | None:
    width_text = _glass_number(width)
    height_text = _glass_number(height)
    if width_text is None or height_text is None:
        return None
    return f"\u2066{width_text} × {height_text} مم\u2069"


def _glass_size_gap_lines(params: Mapping[str, Any]) -> tuple[str, ...]:
    values = []
    for key in ("finished_width_mm", "finished_length_mm", "cut_width_mm", "cut_height_mm"):
        raw = params.get(key)
        if raw in (None, ""):
            return ()
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            return ()
    finished_width, finished_length, cut_width, cut_height = values
    width_gap = finished_width - cut_width
    length_gap = finished_length - cut_height
    if abs(width_gap) <= 0.001 and abs(length_gap) <= 0.001:
        return ()
    return (
        "فرق المقاس النهائي عن محيط القص: "
        f"العرض {_glass_signed_mm(width_gap)}، الطول {_glass_signed_mm(length_gap)}.",
    )


def _glass_context_lines(params: Mapping[str, Any]) -> tuple[str, ...]:
    lines: list[str] = []
    piece_type = _GLASS_TYPE_AR.get(str(params.get("piece_type") or "Glass"), "بلور")
    if params.get("piece_type") or params.get("margin_known") is not None or params.get("sides"):
        lines.append(f"نوع الدرفة: {piece_type}.")
    finished = _glass_pair_mm(params.get("finished_width_mm"), params.get("finished_length_mm"))
    if finished:
        lines.append(f"الأبعاد الخارجية في الطلب: {finished}.")
    cut = _glass_pair_mm(params.get("cut_width_mm"), params.get("cut_height_mm"))
    if cut:
        lines.append(f"محيط القص في الملف: {cut}.")
    lines.extend(_glass_size_gap_lines(params))
    opening = _glass_pair_mm(params.get("opening_width_mm"), params.get("opening_height_mm"))
    if opening:
        lines.append(f"فتحة البلور في الملف: {opening}.")
    expected = _glass_pair_mm(
        params.get("expected_opening_width_mm"),
        params.get("expected_opening_length_mm"),
    )
    if expected:
        lines.append(f"أبعاد الفتحة المتوقعة من الطلب: {expected}.")
    if params.get("margin_known") is not None or params.get("order_margin_mm") not in (None, ""):
        lines.append(f"هامش البلور في الطلب: {_glass_margin_text(params)}.")
    if params.get("tolerance_mm") not in (None, ""):
        lines.append(f"السماحية الهندسية: {_glass_mm(params.get('tolerance_mm'))}.")
    file_insets = params.get("file_insets_mm")
    if isinstance(file_insets, Mapping) and file_insets:
        listed = "، ".join(
            f"{_glass_side_name(name)} {_glass_mm(file_insets.get(name))}"
            for name in ("left", "right", "top", "bottom")
            if name in file_insets
        )
        lines.append(f"مسافات فتحة الملف عن محيط القص: {listed}.")
    door_bands = params.get("door_bands_mm")
    if isinstance(door_bands, Mapping) and door_bands:
        listed = "، ".join(
            f"{_GLASS_SIDE_AR.get(name, name)} {_glass_mm(door_bands.get(name))}"
            for name in ("long_left", "long_right", "width_top", "width_bottom")
        )
        lines.append(f"قشاط الدرفة: {listed}.")
        lines.append("لم تُربط جهات الملف بجهات الدرفة لأن هامش الطلب غير محفوظ.")
    orientation = _GLASS_ORIENTATION_AR.get(str(params.get("orientation") or ""))
    if orientation:
        lines.append(orientation)
        lines.append("أسماء الجهات في الجدول هي جهات الدرفة بعد هذه المطابقة.")
    return tuple(lines)


def _glass_table(params: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    rows = params.get("sides")
    if not isinstance(rows, (list, tuple)) or not rows:
        return ()
    table = [("الجهة", "هامش الطلب", "القشاط", "المتوقع", "الموجود في DXF", "الفرق")]
    tolerance = params.get("tolerance_mm")
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        side = _GLASS_SIDE_AR.get(str(row.get("side") or ""), "طرف")
        if row.get("violates"):
            side = f"● {side}"
        margin = "غير محفوظ" if row.get("order_margin_mm") in (None, "") and params.get("margin_known") is False else _glass_mm(row.get("order_margin_mm"), tolerance=tolerance)
        table.append((
            side,
            margin,
            _glass_mm(row.get("band_mm"), tolerance=tolerance),
            _glass_mm(row.get("expected_inset_mm"), tolerance=tolerance),
            _glass_mm(row.get("actual_inset_mm"), tolerance=tolerance),
            _glass_signed_mm(row.get("delta_mm"), tolerance=tolerance),
        ))
    return tuple(table) if len(table) > 1 else ()


def _glass_side_name(side: Any) -> str:
    return _GLASS_SIDE_AR.get(str(side or ""), "أحد الأطراف")


def _band_consumes_action(params: Mapping[str, Any]) -> str:
    if params.get("margin_known") is False:
        return "احفظ هامش البلور على صف الدرفة في الطلب، ثم أعد رفع الملف."
    margin = params.get("order_margin_mm")
    try:
        margin_value = float(margin)
    except (TypeError, ValueError):
        return "احفظ هامش البلور على صف الدرفة في الطلب، ثم أعد رفع الملف."
    rows = [row for row in (params.get("sides") or ()) if isinstance(row, Mapping)]
    blocking = [row for row in rows if float(row.get("expected_inset_mm") or 0) <= 0]
    if not blocking and params.get("side"):
        blocking = [{"side": params.get("side"), "band_mm": params.get("band_mm")}]
    if margin_value <= 0:
        largest = max((float(row.get("band_mm") or 0) for row in rows), default=0.0)
        return (
            f"هامش البلور المحفوظ {_glass_mm(margin_value)} لا يترك مسافة داخل القص. "
            f"اجعله أكبر من {_glass_mm(largest)}."
        )
    parts = []
    for row in blocking:
        side = _glass_side_name(row.get("side"))
        band = row.get("band_mm")
        parts.append(
            f"اخفض قشاط طرف {side} إلى أقل من {_glass_mm(margin_value)}، "
            f"أو ارفع هامش البلور إلى أكبر من {_glass_mm(band)}"
        )
    if not parts:
        return "اجعل مسافة الفتحة عن محيط القص أكبر من صفر على الأطراف الأربعة."
    return " ".join(f"{part}." for part in parts)


def _inset_action(params: Mapping[str, Any]) -> str:
    rows = [
        row for row in (params.get("sides") or ())
        if isinstance(row, Mapping) and row.get("violates")
    ]
    if not rows and params.get("side"):
        rows = [{
            "side": params.get("side"),
            "actual_inset_mm": params.get("actual_inset_mm"),
            "expected_inset_mm": params.get("expected_inset_mm"),
            "delta_mm": params.get("delta_mm"),
        }]
    parts = []
    for row in rows:
        side = _glass_side_name(row.get("side"))
        parts.append(
            f"اجعل هامش طرف {side} {_glass_mm(row.get('expected_inset_mm'))} "
            f"بدل {_glass_mm(row.get('actual_inset_mm'))}"
        )
    if not parts:
        return "عدّل أبعاد التفريغ في DXF أو راجع هامش البلور في الطلب."
    return "، و".join(parts) + "."


def _present_glass_opening(
    issue: DxfValidationIssue,
    target_text: str,
) -> PresentedDxfError | None:
    code = issue.code
    if code not in _GLASS_CODES:
        return None
    params = issue.params or {}
    details = _glass_context_lines(params)
    table = _glass_table(params)
    tolerance = params.get("tolerance_mm")
    if code == codes.GLASS_OPENING_MISSING:
        expected = _glass_pair_mm(
            params.get("expected_opening_width_mm"),
            params.get("expected_opening_length_mm"),
        )
        problem = "درفة البلور بلا فتحة داخلية."
        highlight = f"المتوقع فتحة مستطيلة واحدة{f' بمقاس {expected}' if expected else ''}."
        action = "أضف محيطًا داخليًا مغلقًا واحدًا لفتحة البلور داخل محيط الدرفة."
    elif code == codes.GLASS_OPENING_UNEXPECTED:
        piece_type = _GLASS_TYPE_AR.get(str(params.get("piece_type") or ""))
        kind = f"من نوع {piece_type}" if piece_type else "ليست من نوع بلور"
        problem = f"وُجدت فتحة داخلية في قطعة {kind}."
        highlight = "فتحة البلور تُقبل فقط عندما تكون القطعة من نوع بلور."
        action = "أزل الفتحة من هذه القطعة، أو اجعل نوع الدرفة بلور إذا كانت الفتحة مقصودة."
    elif code == codes.GLASS_MULTIPLE_OPENINGS:
        count = params.get("opening_count")
        count_text = _glass_number(count) or "أكثر من واحدة"
        problem = "درفة البلور تحتوي أكثر من فتحة داخلية."
        highlight = f"عدد الفتحات المكتشفة {count_text}، والمدعوم حاليًا فتحة واحدة."
        action = "اترك فتحة مستطيلة واحدة واحذف الفتحات الزائدة."
    elif code == codes.GLASS_OPENING_INVALID:
        reasons = [
            _GLASS_GEOMETRY_AR.get(str(error), str(error))
            for error in (params.get("geometry_errors") or ())
            if str(error) in _GLASS_GEOMETRY_AR or str(error)
        ]
        proven = [text for text in reasons if text]
        problem = "فتحة البلور غير صالحة."
        highlight = "السبب: " + "، ".join(proven) + "." if proven else "سبب بطلان الفتحة غير محدد في نتيجة التحقق."
        action = "اجعل الفتحة محيطًا مستطيلًا مغلقًا بلا تقاطع."
    elif code == codes.GLASS_OPENING_OUTSIDE:
        outside = [row for row in (params.get("outside_sides") or ()) if isinstance(row, Mapping)]
        bits = []
        for row in outside:
            relation = "تتجاوز المحيط" if row.get("relation") == "crosses" else "تلامس المحيط أو تقترب منه"
            bits.append(f"{_glass_side_name(row.get('side'))} {relation} ({_glass_mm(row.get('inset_mm'), tolerance=tolerance)})")
        problem = "فتحة البلور ليست داخل الدرفة بالكامل."
        highlight = "؛ ".join(bits) + "." if bits else "الفتحة تخرج عن المحيط أو تلامسه، من دون جهة واحدة يمكن تحديدها."
        action = "أبعد الفتحة عن المحيط الخارجي حتى تبقى داخله من الجهات الأربع."
    elif code == codes.GLASS_GEOMETRY_AMBIGUOUS:
        problem = "تعذّر تمييز درفة البلور عن قطعة أخرى بالمقاس نفسه."
        highlight = "فتحات الملف لا تحدد درفة البلور بصورة واحدة، لذلك لم يُعرض رقم درفة."
        action = "اجعل فتحة البلور داخل درفة البلور فقط، ثم أعد الرفع."
    else:
        side = _glass_side_name(params.get("side"))
        if params.get("reason") == "margin_missing" or params.get("margin_known") is False:
            door_no = issue.target.source_piece_no if issue.target is not None else None
            if params.get("margin_state") == "absent":
                if door_no is not None and not params.get("identity_unproven"):
                    problem = f"تعذرت قراءة هامش البلور المحفوظ للدرفة {door_no} أثناء الاستيراد."
                else:
                    problem = "تعذرت قراءة هامش البلور المحفوظ أثناء الاستيراد."
                highlight = "مرجع التشخيص: glass_margin_absent_on_import_row."
                action = "أعد رفع الملف. إذا تكرر الرفض، أبلغ الدعم الفني بهذا المرجع."
            else:
                if door_no is not None and not params.get("identity_unproven"):
                    problem = f"لم يتم العثور على هامش بلور محفوظ للدرفة {door_no}."
                else:
                    problem = "لم يتم العثور على هامش بلور محفوظ على صف الدرفة."
                highlight = "القيمة غير موجودة في صف الدرفة الذي قرأه الاستيراد."
                action = "افتح شكل الدرفة، أدخل الهامش، اضغط اعتماد الشكل، ثم احفظ طلب القص وأعد رفع الملف."
        elif params.get("reason") == "band_consumes_margin":
            problem = "هامش البلور لا يترك مسافة صالحة داخل محيط القص بعد خصم القشاط."
            highlight = (
                f"طرف {side}: هامش الطلب {_glass_margin_text(params)}، "
                f"القشاط {_glass_mm(params.get('band_mm'))}، "
                f"الناتج {_glass_mm(params.get('expected_inset_mm'))}."
            )
            action = _band_consumes_action(params)
        else:
            problem = "هامش فتحة البلور لا يطابق الهامش المحدد في الطلب."
            highlight = (
                f"طرف {side}: الموجود {_glass_mm(params.get('actual_inset_mm'), tolerance=tolerance)}، "
                f"المتوقع {_glass_mm(params.get('expected_inset_mm'), tolerance=tolerance)}، "
                f"الفرق {_glass_signed_mm(params.get('delta_mm'), tolerance=tolerance)}."
            )
            action = _inset_action(params)
    return PresentedDxfError(
        problem,
        target_text,
        action,
        code,
        issue.category,
        details,
        highlight,
        table,
    )


def present_issue(issue: DxfValidationIssue) -> PresentedDxfError:
    params = dict(issue.params or {})
    target_text = present_target(issue.target, params=params)
    code = issue.code

    if code == codes.LEGACY_MESSAGE:
        return PresentedDxfError(
            problem="تعذر التحقق من الملف بسبب رسالة قديمة غير مفصلة.",
            target="تفاصيل الخطأ غير متاحة بأمان.",
            action="راجع مسؤول النظام لتشخيص الخطأ ثم أعد المحاولة.",
            code=code,
            category=issue.category,
        )

    if code == codes.FILE_REQUIRED:
        return PresentedDxfError("لم يتم اختيار ملف DXF.", "ملف DXF.", "اختر ملف DXF ثم أعد المحاولة.", code, issue.category)
    if code == codes.FILE_INVALID_EXTENSION:
        return PresentedDxfError("امتداد الملف غير مدعوم.", "ملف DXF.", "ارفع ملفًا بامتداد .dxf فقط.", code, issue.category)
    if code == codes.FILE_TOO_LARGE:
        maximum_mb = params.get("maximum_mb", 10)
        return PresentedDxfError("حجم ملف DXF يتجاوز الحد المسموح.", "ملف DXF.", f"قلّل حجم الملف إلى {maximum_mb} MB أو أقل ثم أعد الرفع.", code, issue.category)
    if code == codes.FILE_ATTACHED_ELSEWHERE:
        return PresentedDxfError("الملف مرتبط مسبقًا بمستند.", "ملف DXF.", "ارفع نسخة خاصة غير مرتبطة ثم أعد المحاولة.", code, issue.category)
    if code == codes.FILE_NOT_PRIVATE:
        return PresentedDxfError("الملف المرفوع ليس خاصًا.", "ملف DXF.", "ارفع DXF كملف Private ثم أعد المحاولة.", code, issue.category)
    if code == codes.FILE_MISSING:
        return PresentedDxfError(
            "تعذر العثور على ملف DXF المرفوع على الخادم.",
            "ملف DXF.",
            "أعد رفع الملف ثم حاول مرة أخرى.",
            code,
            issue.category,
        )
    if code == codes.FILE_UNREADABLE:
        return PresentedDxfError(
            "تعذر قراءة ملف DXF من الخادم.",
            "ملف DXF.",
            "أعد رفع الملف ثم حاول مرة أخرى.",
            code,
            issue.category,
        )
    if code == codes.DXF_LIBRARY_MISSING:
        return PresentedDxfError(
            "مكتبة قراءة DXF غير متوفرة على الخادم.",
            "ملف DXF.",
            "راجع إعدادات الخادم ثم أعد المحاولة.",
            code,
            issue.category,
        )
    if code == codes.DXF_UNREADABLE:
        return PresentedDxfError("تعذر قراءة ملف DXF.", "ملف DXF.", "صحح الملف أو أعد تصديره من AutoCAD ثم أعد الرفع.", code, issue.category)
    if code == codes.UNSUPPORTED_ENTITY:
        return PresentedDxfError(
            f"يوجد كيان غير مدعوم في DXF ({params.get('entity') or '؟'}).",
            present_target(issue.target, params=params),
            "استبدل الكيان بمسارات LWPOLYLINE/LINE المدعومة ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.MINSERT_UNSUPPORTED:
        return PresentedDxfError(
            "كتل MINSERT غير مدعومة في استيراد DXF.",
            present_target(issue.target, params=params),
            "فجّر الكتل (Explode) ثم أعد التصدير والرفع.",
            code,
            issue.category,
        )
    if code == codes.ENTITY_LIMIT_EXCEEDED:
        return PresentedDxfError(
            "ملف DXF يتجاوز الحد المسموح لعدد الكيانات.",
            "ملف DXF.",
            "بسّط الرسم ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.BLOCK_NESTING_TOO_DEEP:
        return PresentedDxfError("تداخل BLOCK/INSERT يتجاوز حد القراءة الآمن.", "ملف DXF.", "بسّط تداخل البلوكات ثم أعد الرفع.", code, issue.category)
    if code == codes.ENTITY_PARSE_FAILED:
        return PresentedDxfError("تعذر تحليل أحد عناصر الرسم المدعومة.", target_text, "أعد حفظ العنصر كـDXF قياسي ثم حاول مجددًا.", code, issue.category)
    if code == codes.BLOCK_TRANSFORM_FAILED:
        return PresentedDxfError("تعذر تطبيق تحويلات أحد البلوكات.", target_text, "راجع البلوك ومقياسه ودورانه ثم أعد حفظ DXF.", code, issue.category)

    if code == codes.SHEET_LAYER_MISSING:
        detected = params.get("detected_layers") or []
        detected_text = "الطبقات المكتشفة: " + ("، ".join(map(str, detected)) if detected else "لا توجد") + "."
        return PresentedDxfError(
            "لم يتم العثور على حدود ألواح صالحة في طبقة SHEET_OUTLINE. " + detected_text,
            "طبقة SHEET_OUTLINE.",
            "ارسم مستطيلاً مغلقًا على SHEET_OUTLINE ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.CUT_LAYER_MISSING:
        detected = params.get("detected_layers") or []
        detected_text = "الطبقات المكتشفة: " + ("، ".join(map(str, detected)) if detected else "لا توجد") + "."
        return PresentedDxfError(
            "لم يتم العثور على مسارات قص صالحة في طبقة CUT_PATH. " + detected_text,
            "طبقة CUT_PATH.",
            "ارسم محيطات القطع على CUT_PATH ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.SHEET_OPEN:
        return PresentedDxfError(
            "حدود اللوح غير مغلقة.",
            target_text,
            "أغلق المسار على طبقة SHEET_OUTLINE ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.SHEET_BRANCHED:
        return PresentedDxfError(
            "حدود اللوح تحتوي على تفرع أو خطوط زائدة.",
            target_text,
            "اجعل SHEET_OUTLINE مستطيلاً واحدًا مغلقًا.",
            code,
            issue.category,
        )
    if code == codes.SHEET_NOT_RECTANGLE:
        return PresentedDxfError(
            "حدود اللوح ليست مستطيلاً صحيحًا بمحاور مستقيمة.",
            target_text,
            "ارسم مستطيلاً بمحاور مستقيمة على SHEET_OUTLINE.",
            code,
            issue.category,
        )
    if code == codes.SHEET_SIZE_MISMATCH:
        actual_w = format_mm(params.get("actual_width_mm"))
        actual_h = format_mm(params.get("actual_height_mm"))
        expected_w = format_mm(params.get("expected_width_mm"))
        expected_h = format_mm(params.get("expected_height_mm"))
        return PresentedDxfError(
            f"أبعاد اللوح لا تطابق الطلب. الموجود {actual_w} × {actual_h} مم والمطلوب {expected_w} × {expected_h} مم.",
            target_text,
            f"اجعل SHEET_OUTLINE بمقاس {expected_w} × {expected_h} مم.",
            code,
            issue.category,
        )

    if code == codes.CUT_OPEN:
        return PresentedDxfError(
            "مسار القص غير مغلق.",
            target_text,
            "أغلق المحيط بالكامل على CUT_PATH.",
            code,
            issue.category,
        )
    if code == codes.CUT_BRANCHED:
        return PresentedDxfError(
            "مسار القص يحتوي على تفرع أو خطوط زائدة.",
            target_text,
            "اجعل CUT_PATH محيطًا واحدًا مغلقًا بلا تفرعات.",
            code,
            issue.category,
        )
    if code == codes.CUT_SELF_INTERSECTION:
        return PresentedDxfError(
            "مسار القص يتقاطع مع نفسه.",
            target_text,
            "أزل التقاطع الذاتي من CUT_PATH ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.CUT_INVALID_GEOMETRY:
        return PresentedDxfError(
            "هندسة مسار القص غير صالحة.",
            target_text,
            "صحح المحيط على CUT_PATH ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.CORNER_EDGE_UNRESOLVED:
        reason = str(params.get("reason") or "")
        if reason == "break_thickness_unknown":
            problem = "تعذر التحقق من أبعاد زاوية L لأن سماكة قشاط الزاوية الداخلي غير معروفة."
            action = "حدّد نوع قشاط الزاوية وسماكته في الطلب، ثم أعد رفع الملف. لا يمكن احتساب خصم غير مثبت."
        elif reason == "ambiguous":
            problem = "تعذر ربط قشاط الزاوية بأضلاع المحيط لأن أكثر من دوران أو انعكاس يضع القشاط على أضلاع مختلفة."
            action = "اجعل محيط الدرفة مطابقًا لزاوية L أو الزاوية الكسر في الطلب بعد دوران 0 أو 90 أو 180 أو 270 درجة، أو بعد انعكاس واحد مع إحدى هذه الدورانات، بشرط أن يبقى القشاط على نفس الضلع. المقاس الخارجي وحده لا يكفي."
        elif reason == "invalid":
            problem = "تعذر ربط قشاط الزاوية بأضلاع المحيط لأن بيانات زاوية الطلب لا تكفي لبناء شكل الدرفة."
            action = "راجع موضع الزاوية ومسافات القص في الطلب، ثم أعد رفع الملف."
        else:
            problem = "تعذر ربط قشاط الزاوية بأضلاع المحيط لأن شكل الدرفة لا يطابق زاوية الطلب بعد دوران أو انعكاس واضح."
            action = "اجعل محيط الدرفة مطابقًا لزاوية L أو الزاوية الكسر في الطلب بعد دوران 0 أو 90 أو 180 أو 270 درجة، أو بعد انعكاس واحد مع إحدى هذه الدورانات. المقاس الخارجي وحده لا يكفي."
        return PresentedDxfError(problem, target_text, action, code, issue.category)
    if code == codes.L_CORNER_NOTCH_MISMATCH:
        l_target = target_text[:-1] + " — زاوية L." if target_text.endswith(".") else f"{target_text} — زاوية L."
        return PresentedDxfError(
            "أبعاد زاوية L في ملف DXF لا تطابق أبعاد القص المطلوبة بعد احتساب سماكات القشاطات.",
            l_target,
            "راجع أبعاد التجويف الداخلي في AutoCAD، وعدّل البعد الموضح ليطابق مقاس القص الخام المطلوب، ثم أعد رفع الملف.",
            code,
            issue.category,
            _l_notch_difference_lines(params.get("axes")),
        )

    if code == codes.FORBIDDEN_ROTATION:
        rotation_count = max(1, int(params.get("rotation_count", 1) or 1))
        candidate_rows = tuple(
            sorted({
                int(row)
                for row in (params.get("candidate_source_piece_nos") or ())
                if str(row).isdigit()
            })
        )
        if candidate_rows and issue.target.kind == "order":
            target_text = "الدرف المحتملة: " + "، ".join(
                str(row) for row in candidate_rows
            ) + "."

        if rotation_count == 1 and not params.get("identity_ambiguous"):
            expected = _size_cm(
                params.get("expected_width_cm", _mm_to_cm(params.get("expected_width_mm"))),
                params.get("expected_height_cm", _mm_to_cm(params.get("expected_height_mm"))),
            )
            noun = _piece_noun(issue)
            adjective = "مدوّر" if noun == "مسار القص" else "مدوّرة"
            return PresentedDxfError(
                f"{noun} {adjective} والتدوير غير مسموح.",
                target_text,
                f"أعد اتجاه {noun} إلى {expected}.",
                code,
                issue.category,
            )

        measurements = params.get("possible_measurements_cm") or []
        pairs = []
        for measurement in measurements:
            actual = _size_cm(
                measurement.get("actual_width_cm"),
                measurement.get("actual_height_cm"),
            )
            expected = _size_cm(
                measurement.get("expected_width_cm"),
                measurement.get("expected_height_cm"),
            )
            pair = f"الموجود {actual} والمطلوب {expected}"
            if pair not in pairs:
                pairs.append(pair)
        if not pairs and params.get("actual_width_cm") is not None:
            pairs.append(
                "الموجود "
                + _size_cm(params.get("actual_width_cm"), params.get("actual_height_cm"))
                + " والمطلوب "
                + _size_cm(params.get("expected_width_cm"), params.get("expected_height_cm"))
            )
        count_text = "قطعة واحدة" if rotation_count == 1 else f"{rotation_count} قطع"
        problem = f"ثبت وجود تدوير ممنوع في {count_text}."
        action = "أعد اتجاه القطع."
        if pairs:
            action += " المقاسات: " + "؛ ".join(pairs) + "."
        return PresentedDxfError(
            problem,
            target_text,
            action,
            code,
            issue.category,
        )

    if code == codes.CUT_SIZE_MISMATCH:
        actual = _size_cm(
            params.get("actual_width_cm", params.get("actual_w")),
            params.get("actual_height_cm", params.get("actual_h")),
        )
        expected = _size_cm(
            params.get("expected_width_cm", params.get("expected_w")),
            params.get("expected_height_cm", params.get("expected_h")),
        )
        if params.get("expected_width_cm") is not None or params.get("expected_w") is not None:
            problem = f"مقاس القص غير مطابق. الموجود {actual} والمطلوب {expected}."
            action = f"اجعل CUT_PATH بمقاس {expected}."
        else:
            problem = f"مقاس القص غير مطابق. الموجود {actual}."
            action = "طابق مقاس القص المحفوظ في الطلب على CUT_PATH."
        return PresentedDxfError(problem, target_text, action, code, issue.category)

    if code == codes.SPECIAL_SIZE_MISMATCH:
        noun = _piece_noun(issue)
        prefix = (
            "مقاس مسار القص الخاص خارج المجال المسموح."
            if noun == "مسار القص"
            else f"مقاس {noun} الخاصة خارج المجال المسموح."
        )
        actual = _size_cm(
            params.get("actual_width_cm"),
            params.get("actual_height_cm"),
        )
        expected = _size_cm(
            params.get("expected_width_cm"),
            params.get("expected_height_cm"),
        )
        problem = (
            f"{prefix} الموجود {actual} ومقاس القص المحفوظ {expected}."
            if params.get("actual_width_cm") is not None
            and params.get("actual_height_cm") is not None
            and params.get("expected_width_cm") is not None
            and params.get("expected_height_cm") is not None
            else prefix
        )
        return PresentedDxfError(
            problem,
            target_text,
            _special_range_action(params),
            code,
            issue.category,
        )

    if code == codes.PIECE_MISSING:
        missing_sizes = [str(item) for item in (params.get("missing_sizes") or []) if item]
        missing_count = int(params.get("missing_count") or len(missing_sizes) or 1)
        preview = str(params.get("preview") or "").strip()
        if missing_count == 1:
            problem = "يوجد درفة ناقصة في ملف DXF."
        else:
            problem = f"يوجد {missing_count} درفات ناقصة في ملف DXF."
        if missing_sizes:
            action = (
                f"أضف على CUT_PATH الدرفة الناقصة بمقاس {missing_sizes[0]}."
                if missing_count == 1
                else f"أضف على CUT_PATH الدرفات الناقصة بهذه المقاسات: {'، '.join(missing_sizes)}."
            )
        elif preview:
            action = f"أضف الدرفات الناقصة على CUT_PATH: {preview}."
        else:
            action = "أضف الدرفة الناقصة على CUT_PATH ثم أعد الرفع."
        count_target = present_target(issue.target, params=params)
        return PresentedDxfError(problem, count_target, action, code, issue.category)

    if code == codes.EXTRA_CUT_PATH:
        extra_sizes = [str(item) for item in (params.get("extra_sizes") or []) if item]
        extra_labels = [str(item) for item in (params.get("labels") or []) if item]
        extra_count = int(params.get("extra_count") or len(extra_sizes) or 1)
        if extra_count == 1:
            problem = "يوجد مسار قص زائد في ملف DXF."
        else:
            problem = f"يوجد {extra_count} مسارات قص زائدة في ملف DXF."
        if extra_labels:
            action = f"أزل القطع غير المطلوبة من الخطة: {', '.join(extra_labels)}."
        elif extra_sizes:
            action = (
                f"احذف من CUT_PATH المسار الزائد بمقاس {extra_sizes[0]}."
                if extra_count == 1
                else f"احذف من CUT_PATH المسارات الزائدة بهذه المقاسات: {'، '.join(extra_sizes)}."
            )
        else:
            action = "احذف المسارات الزائدة من CUT_PATH ثم أعد الرفع."
        return PresentedDxfError(
            problem,
            present_target(issue.target, params=params),
            action,
            code,
            issue.category,
        )

    if code == codes.EXPECTED_PIECE_MISMATCH:
        actual_sizes = [str(value) for value in (params.get("extra_sizes") or []) if value]
        required_sizes = [str(value) for value in (params.get("missing_sizes") or []) if value]
        target_parts = []
        if actual_sizes:
            target_parts.append(f"في الملف: {'، '.join(actual_sizes)}.")
        if required_sizes:
            target_parts.append(f"المطلوب: {'، '.join(required_sizes)}.")
        target_text = " ".join(target_parts) or "مسارات القص في ملف DXF."
        return PresentedDxfError(
            "يوجد اختلاف في مقاسات القص بين DXF والطلب.",
            target_text,
            "صحح مسار القص غير المطابق ثم أعد رفع الملف.",
            code,
            issue.category,
        )

    if code == codes.PIECE_IDENTITY_MISSING:
        return PresentedDxfError(
            "تعذر ربط مسار القص بهوية قطعة واحدة في الطلب.",
            target_text,
            "طابق المقاس والهوية مع صف الطلب ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.PIECE_IDENTITY_MISMATCH:
        return PresentedDxfError("هوية القطعة لا تطابق هوية الطلب المحفوظة.", target_text, "أعد حساب الخطة أو استورد DXF من الطلب الحالي.", code, issue.category)

    if code == codes.PIECE_IDENTITY_AMBIGUOUS:
        return PresentedDxfError(
            "هوية مسار القص ملتبسة بين أكثر من قطعة.",
            target_text,
            "افصل القطع المتشابهة أو اجعل الهوية قابلة للإثبات ثم أعد الرفع.",
            code,
            issue.category,
        )

    if code == codes.AMBIGUOUS_CONTOUR_OWNERSHIP:
        return PresentedDxfError(
            "يوجد مسار داخلي غير واضح: هل هو فتحة أم قطعة مستقلة؟",
            target_text,
            "اجعل الفتحة داخل محيط واحد بوضوح، أو افصل القطعة المستقلة.",
            code,
            issue.category,
        )
    if code == codes.UNRESOLVED_CONTOUR_OWNERSHIP:
        return PresentedDxfError(
            "تعذر تمييز المحيطات عن الفتحات الداخلية.",
            target_text,
            "أغلق كل فتحة بالكامل داخل محيطها دون تلامس ملتبس.",
            code,
            issue.category,
        )
    if code == codes.INVALID_PART_TOPOLOGY:
        return PresentedDxfError(
            "شكل أحد محيطات القص أو فتحاته غير صالح.",
            target_text,
            "أغلق المحيط وأزل التقاطعات ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.MATERIAL_OVERLAP:
        pair_subject, pair_object = _pair_nouns(issue)
        if pair_subject == "مسارا القص":
            return PresentedDxfError("يتداخل مسارا قص.", target_text, "افصل مسارات القص بحيث لا تتداخل مادتهما.", code, issue.category)
        return PresentedDxfError(
            f"{pair_subject} متداخلتان على اللوح.",
            target_text,
            f"افصل {pair_object} عن بعضهما.",
            code,
            issue.category,
        )
    if code == codes.KERF_VIOLATION:
        kerf = format_mm(params.get("kerf_mm") or 0)
        pair_subject, pair_object = _pair_nouns(issue)
        if pair_subject == "مسارا القص":
            return PresentedDxfError("المسافة بين مساري القص أقل من Kerf.", target_text, f"اجعل المسافة {kerf} مم أو أكثر.", code, issue.category)
        return PresentedDxfError(
            f"المسافة بين {pair_object} أقل من Kerf.",
            target_text,
            f"اجعل المسافة {kerf} مم أو أكثر.",
            code,
            issue.category,
        )
    if code == codes.HOLE_CLEARANCE_VIOLATION:
        kerf = format_mm(params.get("kerf_mm") or 0)
        noun = _piece_noun(issue)
        if noun == "مسار القص":
            return PresentedDxfError("مسار قص داخل فتحة قريب من حافتها.", target_text, f"اترك مسافة Kerf لا تقل عن {kerf} مم من حدود الفتحة.", code, issue.category)
        return PresentedDxfError(
            f"{noun} داخل الفتحة قريبة جدًا من حافة الفتحة.",
            target_text,
            f"اترك مسافة Kerf لا تقل عن {kerf} مم من حدود الفتحة.",
            code,
            issue.category,
        )
    if code == codes.PIECE_OUTSIDE_SHEET:
        noun = _piece_noun(issue)
        return PresentedDxfError(
            f"{noun} خارج حدود اللوح.",
            target_text,
            f"حرّك {noun} داخل اللوح ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.PIECE_INVALID_DIMENSIONS:
        noun = _piece_noun(issue)
        return PresentedDxfError(
            f"أبعاد {noun} غير صالحة.",
            target_text,
            f"صحح عرض وطول {noun} ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.BOARD_INVALID:
        return PresentedDxfError(
            "أبعاد اللوح في الطلب غير صالحة.",
            "اللوح.",
            "حدّد عرض وطول اللوح قبل رفع DXF.",
            code,
            issue.category,
        )
    if code == codes.TRIM_EXCEEDS_BOARD:
        return PresentedDxfError(
            "هامش التشذيب أكبر من أبعاد اللوح ولا توجد مساحة صالحة للقص.",
            "اللوح.",
            "قلّل التشذيب أو زد أبعاد اللوح ثم أعد المحاولة.",
            code,
            issue.category,
        )
    if code == codes.APPLIED_TRIM_OVERFLOW:
        return PresentedDxfError(
            "القطع تتجاوز حدود اللوح حتى بعد التشذيب.",
            "اللوح.",
            "حرّك القطع داخل اللوح ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.CUT_DIMENSIONS_MISSING:
        return PresentedDxfError(
            "مقاسات القص غير محفوظة في الطلب.",
            target_text,
            "احفظ الطلب ثم أعد رفع DXF.",
            code,
            issue.category,
        )
    if code == codes.CUT_DIMENSIONS_BIND_FAILED:
        return PresentedDxfError(
            "تعذر ربط مقاسات القص بصفوف الطلب.",
            "الطلب.",
            "احفظ الطلب ثم أعد رفع DXF.",
            code,
            issue.category,
        )
    if code == codes.PERSISTED_CUT_SPECS:
        preview = str(params.get("preview") or "")
        problem = "راجع مقاسات القص المحفوظة في الطلب."
        if preview:
            problem = f"مقاسات القص المحفوظة: {preview}."
        return PresentedDxfError(
            problem,
            "الطلب.",
            "طابق مقاس القص (وليس المقاس النهائي).",
            code,
            issue.category,
        )

    if code == codes.OVERLAY_ON_NON_EXTRA:
        layer = params.get("layer") or issue.target.layer or "؟"
        noun = _piece_noun(issue)
        return PresentedDxfError(
            f"علامة الطبقة {layer} لا تطابق إضافة مفعّلة على {noun}.",
            target_text,
            f"فعّل الإضافة المطابقة على {noun} أو احذف العلامة.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_FLOATING:
        layer = params.get("layer") or issue.target.layer or "؟"
        noun = _piece_noun(issue)
        return PresentedDxfError(
            f"علامة الطبقة {layer} ليست بالكامل داخل {noun} واحدة.",
            target_text,
            f"ضع العلامة بالكامل داخل {noun} واحدة مفعّلة عليها الإضافة.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_SPANS_HOSTS:
        layer = params.get("layer") or issue.target.layer or "؟"
        noun = _piece_noun(issue)
        multiple = "أكثر من درفة" if noun == "الدرفة" else "أكثر من قطعة"
        return PresentedDxfError(
            f"علامة الطبقة {layer} تمتد فوق {multiple}.",
            target_text,
            f"ضع كل علامة داخل {noun} واحدة مفعّلة عليها الإضافة.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_ADDON_NOT_SELECTED:
        layer = params.get("layer") or "؟"
        kind_name = _OVERLAY_KIND_AR.get(str(params.get("overlay_kind") or ""), layer)
        return PresentedDxfError(
            f"رسمت علامة {kind_name} دون تفعيل خانة الطلب.",
            target_text,
            "فعّل الخانة في جدول القياسات أو احذف العلامة من الرسم.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_ADDON_MISSING:
        layer = params.get("layer") or "؟"
        kind_name = _OVERLAY_KIND_AR.get(str(params.get("overlay_kind") or ""), layer)
        noun = _piece_noun(issue)
        return PresentedDxfError(
            f"خانة {kind_name} مفعّلة لكن العلامة ناقصة في DXF.",
            target_text,
            f"أضف علامة {kind_name} على الطبقة {layer} داخل {noun}.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_ADDON_DUPLICATE:
        layer = params.get("layer") or "؟"
        kind_name = _OVERLAY_KIND_AR.get(str(params.get("overlay_kind") or ""), layer)
        noun = _piece_noun(issue)
        return PresentedDxfError(
            f"يوجد أكثر من علامة {kind_name} لنفس {noun}.",
            target_text,
            "اترك علامة واحدة فقط ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code in {
        codes.LINER_OFFSET_MISMATCH,
        codes.LINER_WIDTH_MISMATCH,
        codes.LINER_SIDE_MISMATCH,
        codes.LINER_SHAPE_MISMATCH,
        codes.LINER_WIDTH_NOT_MEASURABLE,
    }:
        return _present_liner_mismatch(issue, target_text)
    if code == codes.OVERLAY_UNKNOWN:
        return PresentedDxfError(
            "علامة تصنيع في DXF غير معروفة أو غير صالحة.",
            target_text,
            "راجع طبقات علامات الإضافات المدعومة ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_INVALID_PATH:
        layer = params.get("layer") or "؟"
        return PresentedDxfError(
            f"علامة الطبقة {layer} قصيرة جدًا ولا تُقرأ.",
            target_text,
            "ارسم خطًا أو مسارًا أوضح.",
            code,
            issue.category,
        )
    if code == codes.OFFCUT_IDENTITY_MISMATCH:
        return PresentedDxfError(
            "مسار OFFCUT لا يطابق قطعة واحدة بوضوح.",
            target_text,
            "اجعل محيط OFFCUT مطابقًا لمحيط قطعة واحدة تمامًا.",
            code,
            issue.category,
        )
    if code == codes.MIXED_RESOURCE_SOURCE:
        return PresentedDxfError(
            "لا تخلط قطع OFFCUT مع قطع اللوح الكامل على نفس المصدر.",
            target_text,
            "افصل قطع OFFCUT في مصدر مستقل.",
            code,
            issue.category,
        )
    glass_error = _present_glass_opening(issue, target_text)
    if glass_error is not None:
        return glass_error

    # Export / plan parity codes
    if code == codes.TOPOLOGY_VALIDATION_FAILED:
        topo = params.get("topology_code") or "unknown"
        return PresentedDxfError(
            f"فشل التحقق من طوبولوجيا DXF المحفوظة ({topo}).",
            target_text,
            "أعد رفع DXF صالح أو أعد حساب الخطة.",
            code,
            issue.category,
        )
    if code == codes.PLAN_SOURCE_MISSING:
        return PresentedDxfError("خطة القص بلا مصادر فيزيائية.", "الخطة.", "أعد استيراد DXF أو إعادة الحساب.", code, issue.category)
    if code == codes.PIECE_COUNT_MISMATCH:
        return PresentedDxfError(
            f"عدد القطع في خطة DXF هو {params.get('actual_count')} بينما الطلب يتطلب {params.get('expected_count')} قطعة.",
            "الخطة والطلب.",
            "طابق عدد مسارات القص مع العدد المطلوب ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.PLAN_UNPLACED_PIECES:
        return PresentedDxfError("خطة القص تحتوي قطعًا غير موزعة.", "الخطة.", "أكمل التوزيع أو أعد الاستيراد.", code, issue.category)
    if code == codes.PLAN_VALIDATION_FAILED:
        return PresentedDxfError(
            "خطة القص الحالية غير صالحة للتصدير.",
            "خطة القص.",
            "أعد حساب الخطة ثم حاول التصدير مرة أخرى.",
            code,
            issue.category,
        )
    if code == codes.MANUFACTURING_REQUIREMENTS_MISSING:
        return PresentedDxfError(
            "خطة القص المحفوظة بلا متطلبات تصنيع صالحة.",
            "الخطة.",
            "أعد حساب الخطة أو أعد استيراد DXF قبل التصنيع/التصدير.",
            code,
            issue.category,
        )
    if code == codes.PLAN_SOURCE_IDENTITY_MISMATCH:
        return PresentedDxfError("بيانات مصدر اللوح لا تطابق بيانات الطلب أو الخطة المحفوظة.", target_text, "راجع بيانات اللوح والمصدر ثم أعد حساب الخطة.", code, issue.category)
    if code == codes.REMNANT_REFERENCE_MISSING:
        return PresentedDxfError("مصدر اللوح المتبقي بلا مرجع محفوظ.", target_text, "اختر مصدر لوح صالحًا ثم أعد حساب الخطة.", code, issue.category)
    if code == codes.REMNANT_NOT_FOUND:
        return PresentedDxfError("تعذر العثور على مرجع اللوح المتبقي المحفوظ.", target_text, "راجع مصدر اللوح المتبقي ثم أعد حساب الخطة.", code, issue.category)
    if code == codes.REMNANT_IDENTITY_MISMATCH:
        return PresentedDxfError("بيانات اللوح المتبقي لا تطابق لقطة المصدر المحفوظة.", target_text, "راجع هوية ومقاسات اللوح المتبقي ثم أعد حساب الخطة.", code, issue.category)
    if code == codes.PLAN_LABEL_DUPLICATE:
        return PresentedDxfError("يوجد معرّف قطعة مكرر في خطة القص.", target_text, "أعد حساب الخطة أو استورد DXF بهويات قطع فريدة.", code, issue.category)
    if code == codes.PLAN_UNKNOWN_PIECES:
        labels = ", ".join(str(value) for value in (params.get("labels") or []))
        return PresentedDxfError("خطة القص تحتوي قطعًا غير موجودة في الطلب.", labels or target_text, "أزل القطع غير المطلوبة وأعد حساب الخطة.", code, issue.category)

    # Unknown and obsolete codes must fail safely: do not expose arbitrary
    # legacy text, internal code names, or untrusted target details.
    return PresentedDxfError(
        "تعذر التحقق من ملف DXF.",
        "تعذر تحديد موضع المشكلة بأمان.",
        "راجع مسؤول النظام قبل إعادة المحاولة.",
        code,
        issue.category,
    )


def _glass_value_token(value: Any) -> str:
    if value in (None, ""):
        return "none"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _glass_group_signature(item: DxfValidationIssue) -> tuple[str, ...]:
    params = item.params or {}
    side_tokens: list[str] = []
    for row in params.get("sides") or ():
        if not isinstance(row, Mapping):
            continue
        side_tokens.append("|".join((
            str(row.get("side") or ""),
            _glass_value_token(row.get("order_margin_mm")),
            _glass_value_token(row.get("band_mm")),
            _glass_value_token(row.get("expected_inset_mm")),
            _glass_value_token(row.get("actual_inset_mm")),
            _glass_value_token(row.get("delta_mm")),
        )))
    outside = []
    for row in params.get("outside_sides") or ():
        if isinstance(row, Mapping):
            outside.append(f"{row.get('side')}:{_glass_value_token(row.get('inset_mm'))}")
    return (
        item.code,
        str(params.get("reason") or ""),
        str(params.get("margin_known")),
        _glass_value_token(params.get("order_margin_mm")),
        str(item.target.source_piece_no),
        tuple(side_tokens),
        tuple(str(error) for error in (params.get("geometry_errors") or ())),
        str(params.get("opening_count")),
        tuple(outside),
        tuple(
            _glass_value_token((params.get("file_insets_mm") or {}).get(name))
            for name in ("left", "right", "top", "bottom")
        ),
        tuple(
            _glass_value_token((params.get("door_bands_mm") or {}).get(name))
            for name in ("long_left", "long_right", "width_top", "width_bottom")
        ),
    )


def _glass_group_target(group: Sequence[DxfValidationIssue]) -> str:
    first = group[0]
    if first.param("identity_unproven") or first.target.source_piece_no is None:
        return present_issue(first).target
    piece_no = int(first.target.source_piece_no)
    copies = sorted({
        int(item.target.copy_no)
        for item in group
        if item.target.copy_no is not None
    })
    if copies == [1, 2]:
        return f"الدرفة {piece_no} — النسختان 1 و2."
    if len(copies) > 1:
        listed = " و".join(str(number) for number in copies)
        return f"الدرفة {piece_no} — النسخ {listed}."
    return present_issue(first).target


def group_issues(issues: Sequence[DxfValidationIssue]) -> list[list[DxfValidationIssue]]:
    """Group by cause and corrective action, retaining per-issue evidence."""
    grouped: list[list[DxfValidationIssue]] = []
    index_by_key: dict[tuple[str, ...], int] = {}
    for item in sort_issues(list(issues)):
        presented = present_issue(item)
        # Group open/branched contours and identical dimension-less codes.
        contour_group = (
            item.code in {
                codes.CUT_OPEN,
                codes.CUT_BRANCHED,
                codes.CUT_SELF_INTERSECTION,
                codes.CUT_INVALID_GEOMETRY,
            }
            and item.target.contour_no is not None
        )
        piece_group = (
            item.code in {
                codes.FORBIDDEN_ROTATION,
                codes.CUT_SIZE_MISMATCH,
                codes.SPECIAL_SIZE_MISMATCH,
                codes.PIECE_MISSING,
                codes.EXTRA_CUT_PATH,
            }
            and item.target.kind in {
                codes.TARGET_PIECE,
                codes.TARGET_PIECE_COPY,
                codes.TARGET_PIECE_PAIR,
                codes.TARGET_CONTOUR,
                codes.TARGET_CONTOUR_PAIR,
            }
        )
        if item.code in _GLASS_CODES and item.target.source_piece_no is not None:
            key = _glass_group_signature(item)
            if key in index_by_key:
                grouped[index_by_key[key]].append(item)
                continue
            index_by_key[key] = len(grouped)
            grouped.append([item])
            continue
        if contour_group or piece_group:
            # Problem details and params remain on each issue for the expanded
            # evidence list; they do not change root cause or corrective action.
            geometry_errors = item.params.get("geometry_errors") or ()
            geometry_signature = (
                tuple(sorted(str(error) for error in geometry_errors))
                if item.code == codes.CUT_INVALID_GEOMETRY
                else ()
            )
            key = (
                item.code,
                item.category,
                item.target.kind,
                presented.action,
                geometry_signature,
            )
            if key in index_by_key:
                grouped[index_by_key[key]].append(item)
                continue
            index_by_key[key] = len(grouped)
            grouped.append([item])
            continue
        grouped.append([item])
    return grouped


def present_group(group: Sequence[DxfValidationIssue]) -> PresentedDxfError:
    if not group:
        return PresentedDxfError("تعذر التحقق من ملف DXF.", "غير محدد.", "صحح الرسم ثم أعد الرفع.", "UNKNOWN", codes.CATEGORY_WORKFLOW)
    if len(group) == 1:
        return present_issue(group[0])
    if group[0].code in _GLASS_CODES:
        presented = present_issue(group[0])
        return PresentedDxfError(
            presented.problem,
            _glass_group_target(group),
            presented.action,
            presented.code,
            presented.category,
            presented.details + ("القيم الهندسية متطابقة في النسخ المذكورة.",),
            presented.highlight,
            presented.detail_table,
        )
    first = present_issue(group[0])
    contour_nos = [item.target.contour_no for item in group if item.target.contour_no is not None]
    if contour_nos and group[0].code == codes.CUT_OPEN:
        listed = "، ".join(str(no) for no in contour_nos)
        return PresentedDxfError(
            "بعض مسارات القص غير مغلقة.",
            f"مسارات القص {listed}.",
            "أغلق هذه المحيطات بالكامل على CUT_PATH.",
            group[0].code,
            group[0].category,
        )
    if contour_nos and group[0].code == codes.CUT_BRANCHED:
        listed = "، ".join(str(no) for no in contour_nos)
        return PresentedDxfError(
            "بعض مسارات القص تحتوي على تفرع أو خطوط زائدة.",
            f"مسارات القص {listed}.",
            "اجعل كل CUT_PATH محيطًا واحدًا مغلقًا بلا تفرعات.",
            group[0].code,
            group[0].category,
        )
    if contour_nos and group[0].code == codes.CUT_SELF_INTERSECTION:
        listed = "، ".join(str(no) for no in contour_nos)
        return PresentedDxfError(
            "بعض مسارات القص تتقاطع مع نفسها.",
            f"مسارات القص {listed}.",
            "أزل التقاطع الذاتي من هذه المسارات على CUT_PATH.",
            group[0].code,
            group[0].category,
        )
    detail_lines = []
    for item in group:
        presented = present_issue(item)
        detail = f"{presented.target} — {presented.problem}"
        if item.code == codes.CUT_INVALID_GEOMETRY:
            causes = [
                _GEOMETRY_ERROR_AR.get(str(error), "سبب هندسي إضافي")
                for error in (item.params.get("geometry_errors") or ())
            ]
            if causes:
                detail += " التفاصيل: " + "، ".join(causes) + "."
        detail_lines.append(detail)
    details = tuple(detail_lines)
    if group[0].code == codes.CUT_SIZE_MISMATCH:
        summary = "توجد مقاسات قص غير مطابقة."
        group_target = f"{len(group)} مواضع تحتاج الإجراء نفسه."
    elif group[0].code == codes.SPECIAL_SIZE_MISMATCH:
        summary = "توجد مقاسات قطع خاصة خارج المجال المسموح."
        group_target = f"{len(group)} مواضع تحتاج الإجراء نفسه."
    else:
        summary = first.problem
        group_target = f"{len(group)} مواضع متطابقة السبب."
    return PresentedDxfError(
        f"{summary} (عدد المواضع المتأثرة: {len(group)}).",
        group_target,
        first.action,
        first.code,
        first.category,
        details,
    )


def present_issues(issues: Iterable[DxfValidationIssue]) -> list[PresentedDxfError]:
    return [present_group(group) for group in group_issues(list(issues))]


def present_issues_as_strings(issues: Iterable[DxfValidationIssue]) -> list[str]:
    """Flat Arabic strings for legacy ``DxfImportError.errors`` / tests."""
    lines: list[str] = []
    for item in present_issues(issues):
        lines.append(
            f"ما المشكلة؟ {item.problem} أين المشكلة؟ {item.target} ماذا أفعل؟ {item.action}"
        )
    return lines


def render_error_cards_html(
    issues: Sequence[DxfValidationIssue],
    *,
    context: str = "upload",
    max_cards: int = 10,
) -> str:
    """Render RTL issue cards with a footer for upload or export context."""
    if context not in {"upload", "export"}:
        raise ValueError("DXF error-card context must be 'upload' or 'export'.")
    presented = present_issues(issues)
    if not presented:
        fallback_action = (
            "أصلح المشكلة أو أعد حساب الخطة ثم أعد تصدير DXF."
            if context == "export"
            else "صحح الرسم ثم أعد رفع الملف."
        )
        presented = [
            PresentedDxfError(
                "تعذر التحقق من ملف DXF بسبب خطأ غير معروف.",
                "غير محدد.",
                fallback_action,
                "UNKNOWN",
                codes.CATEGORY_WORKFLOW,
            )
        ]
    visible = presented[:max_cards]
    remaining_items = presented[max_cards:]

    def render_table(rows: tuple[tuple[str, ...], ...]) -> str:
        if not rows:
            return ""
        header, *body = rows
        head = "".join(
            f"<th style='padding:4px 8px;text-align:center;border-bottom:1px solid var(--border-color);'>{html.escape(cell)}</th>"
            for cell in header
        )
        body_html = []
        for row in body:
            cells = "".join(
                f"<td style='padding:4px 8px;text-align:center;'>{html.escape(cell)}</td>"
                for cell in row
            )
            body_html.append(f"<tr>{cells}</tr>")
        return (
            "<table style='border-collapse:collapse;width:100%;margin-top:6px;direction:rtl;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_html)}</tbody></table>"
        )

    def render_card(item: PresentedDxfError) -> str:
        details = ""
        if item.details or item.detail_table:
            summary = (
                "التفاصيل الهندسية"
                if item.detail_table or item.code in _GLASS_CODES
                else "تفاصيل الاختلاف"
                if item.code == codes.L_CORNER_NOTCH_MISMATCH
                else "عرض كل المواضع المتأثرة"
            )
            lines = "".join(f"<li>{html.escape(detail)}</li>" for detail in item.details)
            details = (
                "<details class='alm-dxf-error-details' style='margin-top:6px;'>"
                f"<summary>{html.escape(summary)}</summary>"
                f"{'<ul>' + lines + '</ul>' if lines else ''}"
                f"{render_table(item.detail_table)}"
                "</details>"
            )
        highlight = ""
        if item.highlight:
            highlight = (
                "<div style='margin-top:6px;'><strong>الفرق الأبرز:</strong> "
                f"{html.escape(item.highlight)}</div>"
            )
        return (
            "<div class='alm-dxf-error-card' style='border:1px solid var(--border-color);border-radius:6px;"
            "padding:10px 12px;margin:0 0 10px;text-align:right;direction:rtl;'>"
            f"<div><strong>ما المشكلة؟</strong> {html.escape(item.problem)}</div>"
            f"{highlight}"
            f"<div style='margin-top:6px;'><strong>أين المشكلة؟</strong> {html.escape(item.target)}</div>"
            f"<div style='margin-top:6px;'><strong>ماذا أفعل؟</strong> {html.escape(_action_for_context(item.action, context))}</div>"
            f"{details}"
            "</div>"
        )

    cards = [render_card(item) for item in visible]
    extra = ""
    if remaining_items:
        cards.extend(
            [
                "<details class='alm-dxf-error-overflow' style='margin:0 0 10px;'>"
                f"<summary>عرض بقية الأخطاء ({len(remaining_items)})</summary>"
                + "".join(render_card(item) for item in remaining_items)
                + "</details>"
            ]
        )
    footer = (
        "صحح الرسم ثم أعد رفع الملف. لم يتم استبدال خطة DXF الحالية في الطلب."
        if context == "upload"
        else "أصلح المشكلة أعلاه أو أعد حساب الخطة، ثم أعد تصدير DXF."
    )
    return (
        "<div class='alm-dxf-error-dialog' style='direction:rtl;text-align:right;'>"
        f"{''.join(cards)}"
        f"<p>{footer}</p>"
        "</div>"
    )
