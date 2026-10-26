"""Arabic presenter for structured DXF validation issues.

Converts ``code + target + params`` into actionable factory messages.
Does not re-run validation or invent manufacturing decisions.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from frappe import _

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
_CORNER_DIMENSION_CODES = {
    codes.L_CORNER_NOTCH_MISMATCH,
    codes.CLIPPED_CORNER_DIMENSIONS_MISMATCH,
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


def _corner_remaining_size(params: Mapping[str, Any], key: str) -> str:
    values = params.get(key)
    if not isinstance(values, Mapping):
        return ""
    if values.get("width") is None or values.get("length") is None:
        return ""
    return _size_cm(values.get("width"), values.get("length"))


def _corner_dimension_highlight(params: Mapping[str, Any]) -> str:
    finished = _corner_remaining_size(params, "expected_finished_remaining_cm")
    raw = _corner_remaining_size(params, "expected_raw_remaining_cm")
    actual = _corner_remaining_size(params, "actual_raw_remaining_cm")
    if not finished or not actual:
        return ""
    if raw and raw != finished:
        return _(
            "Order finished dimensions: {0}. Required raw dimensions after edge banding: {1}. DXF dimensions: {2}."
        ).format(finished, raw, actual)
    return _("Order dimensions: {0}. DXF dimensions: {1}.").format(
        finished,
        actual,
    )


def _corner_copy_target(issue: DxfValidationIssue, fallback: str) -> str:
    if issue.target.source_piece_no is None or issue.target.copy_no is None:
        return fallback
    return _("Door {0} — copy {1}.").format(
        issue.target.source_piece_no,
        issue.target.copy_no,
    )


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


def _glass_margin_problem(params: Mapping[str, Any]) -> str:
    tolerance = params.get("tolerance_mm")
    rows = [
        row for row in (params.get("sides") or ())
        if isinstance(row, Mapping) and row.get("violates")
    ]
    if not rows and params.get("side"):
        rows = [{
            "side": params.get("side"),
            "actual_inset_mm": params.get("actual_inset_mm"),
            "expected_inset_mm": params.get("expected_inset_mm"),
        }]
    bits = [
        (
            f"طرف {_glass_side_name(row.get('side'))}: "
            f"الموجود {_glass_mm(row.get('actual_inset_mm'), tolerance=tolerance)}، "
            f"والمطلوب {_glass_mm(row.get('expected_inset_mm'), tolerance=tolerance)}"
        )
        for row in rows
    ]
    if not bits:
        return "هامش فتحة البلور لا يطابق الهامش المحدد في الطلب."
    return "هامش فتحة البلور لا يطابق الطلب. " + "، و".join(bits) + "."


def _present_glass_opening(
    issue: DxfValidationIssue,
    target_text: str,
) -> PresentedDxfError | None:
    code = issue.code
    if code not in _GLASS_CODES:
        return None
    params = issue.params or {}
    if code == codes.GLASS_OPENING_MISSING:
        problem = "درفة البلور بلا فتحة داخلية."
        action = "أضف فتحة مستطيلة واحدة داخل محيط الدرفة."
    elif code == codes.GLASS_OPENING_UNEXPECTED:
        piece_type = _GLASS_TYPE_AR.get(str(params.get("piece_type") or ""))
        kind = f"من نوع {piece_type}" if piece_type else "ليست من نوع بلور"
        problem = f"وُجدت فتحة داخلية في قطعة {kind}."
        action = "أزل الفتحة، أو غيّر نوع الدرفة إلى بلور إذا كانت الفتحة مقصودة."
    elif code == codes.GLASS_MULTIPLE_OPENINGS:
        count_text = _glass_number(params.get("opening_count"))
        problem = (
            f"درفة البلور تحتوي {count_text} فتحات داخلية."
            if count_text
            else "درفة البلور تحتوي أكثر من فتحة داخلية."
        )
        action = "اترك فتحة مستطيلة واحدة واحذف الفتحات الزائدة."
    elif code == codes.GLASS_OPENING_INVALID:
        reasons = [
            _GLASS_GEOMETRY_AR[str(error)]
            for error in (params.get("geometry_errors") or ())
            if str(error) in _GLASS_GEOMETRY_AR
        ]
        problem = "فتحة البلور غير صالحة" + (": " + "، ".join(reasons) + "." if reasons else ".")
        action = "اجعل الفتحة مستطيلاً مغلقًا بلا تقاطع."
    elif code == codes.GLASS_OPENING_OUTSIDE:
        sides = [
            _glass_side_name(row.get("side"))
            for row in (params.get("outside_sides") or ())
            if isinstance(row, Mapping)
        ]
        problem = (
            "فتحة البلور تخرج عن محيط الدرفة من جهة " + " و".join(sides) + "."
            if sides
            else "فتحة البلور ليست داخل الدرفة بالكامل."
        )
        action = "أبعد الفتحة عن المحيط حتى تبقى داخله من الجهات الأربع."
    elif code == codes.GLASS_GEOMETRY_AMBIGUOUS:
        problem = "تعذّر تمييز درفة البلور عن قطعة أخرى بالمقاس نفسه."
        action = "اجعل فتحة البلور داخل درفة البلور فقط، ثم أعد الرفع."
    elif params.get("reason") == "margin_missing" or params.get("margin_known") is False:
        door_no = issue.target.source_piece_no if issue.target is not None else None
        if params.get("margin_state") == "absent":
            problem = (
                f"تعذرت قراءة هامش البلور المحفوظ للدرفة {door_no}."
                if door_no is not None and not params.get("identity_unproven")
                else "تعذرت قراءة هامش البلور المحفوظ."
            )
            action = "أعد رفع الملف. إذا تكرر الرفض، أبلغ الدعم الفني."
        else:
            problem = (
                f"لم يتم العثور على هامش بلور محفوظ للدرفة {door_no}."
                if door_no is not None and not params.get("identity_unproven")
                else "لم يتم العثور على هامش بلور محفوظ على صف الدرفة."
            )
            action = "افتح شكل الدرفة، أدخل الهامش، اضغط اعتماد الشكل، ثم احفظ طلب القص وأعد رفع الملف."
    elif params.get("reason") == "band_consumes_margin":
        problem = (
            f"هامش البلور على طرف {_glass_side_name(params.get('side'))} لا يترك مسافة داخل القص: "
            f"الهامش {_glass_mm(params.get('order_margin_mm'))}، "
            f"والناتج {_glass_mm(params.get('expected_inset_mm'))}."
        )
        action = _band_consumes_action(params)
    else:
        problem = _glass_margin_problem(params)
        action = _inset_action(params)
    return PresentedDxfError(problem, target_text, action, code, issue.category)


def _overlay_kind_label(kind: Any) -> str:
    labels = {
        "liner": _("liner"),
        "back_groove": _("back groove"),
        "recessed_handle_cutout": _("recessed handle"),
    }
    return labels.get(str(kind or ""), _("add-on"))


def _group_size_cm(params: Mapping[str, Any]) -> tuple[str, str] | None:
    width = params.get("width_cm")
    height = params.get("height_cm")
    if width is None or height is None:
        return None
    return format_cm(width), format_cm(height)


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
    if code == codes.SAW_CENTER_INVALID:
        return PresentedDxfError(
            "مسارات مركز الريشة على طبقة CUT_PATH غير صحيحة أو غير مكتملة ولا يمكن اعتمادها بأمان.",
            "طبقة CUT_PATH.",
            "احذف مسارات CUT_PATH غير الصحيحة واترك توليدها بعد الاعتماد، أو صحّحها بالكامل وفق Kerf ثم أعد الرفع. لا يُقبل إصلاح جزئي.",
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
    if code == codes.REGULAR_EDGE_ORIENTATION_UNRESOLVED:
        if str(params.get("reason") or "") == "machining_invalid":
            problem = _("The machining paths do not prove a safe orientation for this door.")
            action = _("Check the machining paths and their saved reference sides then re-upload the DXF.")
        else:
            problem = _("The machining paths permit multiple orientations that move edge bands to different physical sides.")
            action = _("Add a distinct machining reference that establishes the door orientation then re-upload the DXF.")
        return PresentedDxfError(problem, target_text, action, code, issue.category)
    if code == codes.CORNER_EDGE_UNRESOLVED:
        candidate_rows = tuple(
            sorted({
                int(row)
                for row in (params.get("candidate_source_piece_nos") or ())
                if str(row).isdigit()
            })
        )
        if candidate_rows and issue.target.kind == codes.TARGET_CONTOUR:
            candidates = "، ".join(str(row) for row in candidate_rows)
            target_text = _("Possible doors: {0}. Additional contour information: {1}").format(
                candidates,
                target_text,
            )
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
        corner_target = _corner_copy_target(issue, target_text)
        target_base = corner_target[:-1] if corner_target.endswith(".") else corner_target
        l_target = _("{0} — L corner.").format(target_base)
        return PresentedDxfError(
            _("The L-corner dimensions in the DXF do not match the order."),
            l_target,
            _("Correct the L-corner dimensions in the DXF file, then upload it again."),
            code,
            issue.category,
            _l_notch_difference_lines(params.get("axes")),
            _corner_dimension_highlight(params),
        )
    if code == codes.CLIPPED_CORNER_DIMENSIONS_MISMATCH:
        corner_target = _corner_copy_target(issue, target_text)
        target_base = corner_target[:-1] if corner_target.endswith(".") else corner_target
        clipped_target = _("{0} — clipped corner.").format(target_base)
        return PresentedDxfError(
            _("The clipped-corner dimensions in the DXF do not match the order."),
            clipped_target,
            _("Correct the clipped-corner dimensions in the DXF file, then upload it again."),
            code,
            issue.category,
            _l_notch_difference_lines(params.get("axes")),
            _corner_dimension_highlight(params),
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
        outline_layer = "GEOMETRY" if params.get("outline_layer") == "GEOMETRY" else "CUT_PATH"
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
            action = _("Set {0} to the required cut size {1}.").format(outline_layer, expected)
        else:
            problem = f"مقاس القص غير مطابق. الموجود {actual}."
            action = _("Match the saved order cut size on {0}.").format(outline_layer)
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

    if code == codes.REGULAR_OUTLINE_NOT_RECTANGLE:
        return PresentedDxfError(
            _("A regular door could not be matched because the DXF contour is not a rectangle."),
            target_text,
            _("Replace the contour with an axis-aligned rectangle that matches the ordered cut size."),
            code,
            issue.category,
        )
    if code == codes.SPECIAL_OUTLINE_IS_RECTANGLE:
        return PresentedDxfError(
            _("A special door could not be matched because the DXF contour is a rectangle."),
            target_text,
            _("Use a non-rectangular contour whose outer dimensions match the ordered special door."),
            code,
            issue.category,
        )
    if code in {
        codes.SPECIAL_ADDON_GROUP_EXTRA,
        codes.SPECIAL_ADDON_GROUP_MISSING,
        codes.SPECIAL_ADDON_GROUP_SPLIT,
    }:
        size = _group_size_cm(params)
        kind = _overlay_kind_label(params.get("overlay_kind"))
        kinds = [
            _overlay_kind_label(item)
            for item in (params.get("overlay_kinds") or ())
        ]
        if code == codes.SPECIAL_ADDON_GROUP_EXTRA:
            problem = (
                _("The special-door group {0} × {1} cm has an extra {2} that the order does not require.").format(size[0], size[1], kind)
                if size
                else _("A special-door group has an extra add-on that the order does not require.")
            )
            action = _("Remove the extra add-on path, or add that add-on to the order.")
        elif code == codes.SPECIAL_ADDON_GROUP_MISSING:
            problem = (
                _("The special-door group {0} × {1} cm is missing a required {2}.").format(size[0], size[1], kind)
                if size
                else _("A special-door group is missing a required add-on.")
            )
            if params.get("found_on_piece_type") == "Regular":
                problem = f"{problem} {_('That path is on a regular door and is not counted for the special door.')}"
            action = _("Draw the missing add-on on a special door in this size group.")
        elif size and len(kinds) >= 2:
            problem = _(
                "{0} and {1} are on different special doors, but the order requires them on the same door ({2} × {3} cm)."
            ).format(kinds[0], kinds[1], size[0], size[1])
            action = _("Put the required add-ons on the same special-door contour.")
        else:
            problem = _("Add-ons that belong on the same special door are split across different doors.")
            action = _("Put the required add-ons on the same special-door contour.")
        return PresentedDxfError(problem, target_text, action, code, issue.category)
    if code == codes.SPECIAL_OVERLAY_AMBIGUOUS:
        return PresentedDxfError(
            _("The {0} path could not be tied to exactly one special door.").format(
                _overlay_kind_label(params.get("overlay_kind"))
            ),
            target_text,
            _("Move the add-on path so it belongs to exactly one special door."),
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
        candidate_rows = tuple(
            sorted({
                int(row)
                for row in (params.get("candidate_source_piece_nos") or ())
                if str(row).isdigit()
            })
        )
        if candidate_rows:
            candidates = "، ".join(str(row) for row in candidate_rows)
            target_text = _("Possible doors: {0}. Additional contour information: {1}").format(
                candidates,
                target_text,
            )
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
        guest_label = str(params.get("glass_frame_guest_label") or "").strip()
        host_label = str(params.get("glass_frame_host_label") or "").strip()
        if guest_label and host_label:
            guest_no = guest_label.split(".", 1)[0]
            host_no = host_label.split(".", 1)[0]
            return PresentedDxfError(
                f"الدرفة {guest_no} تتداخل مع إطار البلور في الدرفة {host_no}.",
                target_text,
                f"حرّك الدرفة داخل الفتحة مع ترك مسافة Kerf لا تقل عن {kerf} مم عن الإطار.",
                code,
                issue.category,
            )
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

    if code == codes.FORBIDDEN_MIRRORING:
        return PresentedDxfError(
            _("This board type does not allow piece mirroring."),
            target_text,
            _("Turn mirroring off in the DXF or allow it on the order and upload the file again."),
            code,
            issue.category,
        )

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


def _corner_group_signature(item: DxfValidationIssue) -> tuple[str, ...]:
    params = item.params or {}
    return (
        item.code,
        item.category,
        str(item.target.source_piece_no or ""),
        repr(params.get("expected_finished_remaining_cm") or {}),
        repr(params.get("expected_raw_remaining_cm") or {}),
        repr(params.get("actual_raw_remaining_cm") or {}),
        repr(params.get("axes") or ()),
    )


def _corner_group_target(group: Sequence[DxfValidationIssue]) -> str:
    first = group[0]
    piece_no = first.target.source_piece_no
    copies = sorted({
        int(item.target.copy_no)
        for item in group
        if item.target.copy_no is not None
    })
    if piece_no is None or not copies:
        return present_issue(first).target
    if len(copies) == 1:
        return present_issue(first).target
    if copies == list(range(copies[0], copies[-1] + 1)):
        return _("Door {0} — copies {1} through {2}.").format(
            piece_no,
            copies[0],
            copies[-1],
        )
    listed = "، ".join(str(copy_no) for copy_no in copies)
    return _("Door {0} — copies {1}.").format(piece_no, listed)


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
                codes.FORBIDDEN_MIRRORING,
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
        if item.code in _CORNER_DIMENSION_CODES and item.target.source_piece_no is not None:
            key = _corner_group_signature(item)
            if key in index_by_key:
                grouped[index_by_key[key]].append(item)
                continue
            index_by_key[key] = len(grouped)
            grouped.append([item])
            continue
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
        )
    if group[0].code in _CORNER_DIMENSION_CODES:
        presented = present_issue(group[0])
        return PresentedDxfError(
            presented.problem,
            _corner_group_target(group),
            presented.action,
            presented.code,
            presented.category,
            presented.details,
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
        if item.code not in _GLASS_CODES and (item.details or item.detail_table):
            summary = (
                "تفاصيل الاختلاف"
                if item.code in _CORNER_DIMENSION_CODES
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
        if item.code not in _GLASS_CODES and item.highlight:
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
