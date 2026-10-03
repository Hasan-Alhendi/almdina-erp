"""Arabic presenter for structured DXF validation issues.

Converts ``code + target + params`` into actionable factory messages.
Does not re-run validation or invent manufacturing decisions.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

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


@dataclass(frozen=True, slots=True)
class PresentedDxfError:
    problem: str
    target: str
    action: str
    code: str
    category: str


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
    text = f"{number:.1f}".rstrip("0").rstrip(".")
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
        return f"{format_cm(width_cm)} × {format_cm(height_cm)} سم"
    return f"{format_cm(width)} × {format_cm(height)} سم"


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
    if kind == codes.TARGET_LAYER and target.layer:
        return f"الطبقة {target.layer}."
    if kind == codes.TARGET_FILE:
        return "ملف DXF."
    if kind == codes.TARGET_OVERLAY:
        if target.source_piece_no is not None:
            return f"الدرفة {target.source_piece_no}."
        if target.label:
            return f"درفة Extra رقم {target.label}."
        if target.layer:
            return f"الطبقة {target.layer}."
        return "علامة Extra."
    if kind in {codes.TARGET_PIECE, codes.TARGET_PIECE_COPY}:
        piece_no = target.source_piece_no
        if piece_no is None and target.piece_index is not None:
            # piece_index without proven identity is not a door number.
            return f"مسار القص رقم {target.piece_index}." if params.get("identity_unproven") else f"القطعة رقم {target.piece_index}."
        if piece_no is None and target.label:
            return f"الدرفة {target.label}."
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


def _special_range_action(params: dict[str, Any]) -> str:
    expected_w = params.get("expected_width_cm")
    expected_h = params.get("expected_height_cm")
    if expected_w is None and params.get("expected_width_mm") is not None:
        expected_w = _mm_to_cm(params.get("expected_width_mm"))
        expected_h = _mm_to_cm(params.get("expected_height_mm"))
    if expected_w is None or expected_h is None:
        return "اجعل Bounding Box ضمن المجال المسموح لقطعة Special (نقص حتى 2 مم لكل محور، بلا زيادة)."
    min_w = float(expected_w) - 0.2
    min_h = float(expected_h) - 0.2
    return (
        f"اجعل Bounding Box ضمن {format_cm(min_w)}–{format_cm(expected_w)} × "
        f"{format_cm(min_h)}–{format_cm(expected_h)} سم."
    )


def present_issue(issue: DxfValidationIssue) -> PresentedDxfError:
    params = dict(issue.params or {})
    target_text = present_target(issue.target, params=params)
    code = issue.code

    if code == codes.LEGACY_MESSAGE:
        message = str(params.get("message") or "تعذر التحقق من ملف DXF.")
        return PresentedDxfError(
            problem=message,
            target=target_text,
            action="صحح الرسم ثم أعد رفع الملف.",
            code=code,
            category=issue.category,
        )

    if code == codes.FILE_REQUIRED:
        return PresentedDxfError("لم يتم اختيار ملف DXF.", "ملف DXF.", "اختر ملف DXF ثم أعد المحاولة.", code, issue.category)
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
        reason = str(params.get("reason") or "")
        problem = "تعذر قراءة ملف DXF."
        if reason:
            problem = f"{problem} {reason}".strip()
        return PresentedDxfError(problem, "ملف DXF.", "صحح الملف أو أعد تصديره من AutoCAD ثم أعد الرفع.", code, issue.category)
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

    if code == codes.SHEET_LAYER_MISSING:
        return PresentedDxfError(
            "لم يتم العثور على حدود ألواح صالحة في طبقة SHEET_OUTLINE.",
            "طبقة SHEET_OUTLINE.",
            "ارسم مستطيلاً مغلقًا على SHEET_OUTLINE ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.CUT_LAYER_MISSING:
        return PresentedDxfError(
            "لم يتم العثور على مسارات قص صالحة في طبقة CUT_PATH.",
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

    if code == codes.FORBIDDEN_ROTATION:
        expected = _size_cm(
            params.get("expected_width_cm", _mm_to_cm(params.get("expected_width_mm"))),
            params.get("expected_height_cm", _mm_to_cm(params.get("expected_height_mm"))),
        )
        return PresentedDxfError(
            "الدرفة مدوّرة والتدوير غير مسموح.",
            target_text,
            f"أعد اتجاه الدرفة إلى {expected}.",
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
        return PresentedDxfError(
            "مقاس الدرفة الخاصة خارج المجال المسموح.",
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
                if len(missing_sizes) == 1
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
        extra_count = int(params.get("extra_count") or len(extra_sizes) or 1)
        if extra_count == 1:
            problem = "يوجد مسار قص زائد في ملف DXF."
        else:
            problem = f"يوجد {extra_count} مسارات قص زائدة في ملف DXF."
        if extra_sizes:
            action = (
                f"احذف من CUT_PATH المسار الزائد بمقاس {extra_sizes[0]}."
                if len(extra_sizes) == 1
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
        dxf_sizes = str(params.get("dxf_sizes_label") or "").strip()
        expected_sizes = str(params.get("expected_sizes_label") or "").strip()
        problem = "مقاسات الدرف في DXF لا تطابق مقاسات القص في الطلب."
        if dxf_sizes and expected_sizes:
            problem = (
                f"مقاسات الدرف في DXF لا تطابق مقاسات القص في الطلب. "
                f"في الملف: {dxf_sizes}. المطلوب: {expected_sizes}."
            )
        pairs = params.get("mismatch_pairs") or []
        if pairs:
            target_text = " ".join(
                f"الدرفة {pair['label']}: المطلوب {pair['expected']}، الموجود في الملف {pair['actual']}."
                for pair in pairs
            )
        else:
            target_text = present_target(issue.target, params=params)
        return PresentedDxfError(
            problem,
            target_text,
            "طابق كل مسار على CUT_PATH مع مقاس القص المحفوظ (وليس المقاس النهائي).",
            code,
            issue.category,
        )

    if code == codes.PIECE_IDENTITY_MISSING:
        return PresentedDxfError(
            "تعذر ربط مسار القص بهوية درفة واحدة في الطلب.",
            target_text,
            "طابق المقاس والهوية مع صف الطلب ثم أعد الرفع.",
            code,
            issue.category,
        )

    if code == codes.PIECE_IDENTITY_AMBIGUOUS:
        return PresentedDxfError(
            "هوية مسار القص ملتبسة بين أكثر من درفة.",
            target_text,
            "افصل القطع المتشابهة أو اجعل الهوية قابلة للإثبات ثم أعد الرفع.",
            code,
            issue.category,
        )

    if code == codes.AMBIGUOUS_CONTOUR_OWNERSHIP:
        return PresentedDxfError(
            "يوجد مسار داخلي غير واضح: هل هو فتحة أم درفة مستقلة؟",
            target_text,
            "اجعل الفتحة داخل درفة واحدة بوضوح، أو افصل الدرفة المستقلة.",
            code,
            issue.category,
        )
    if code == codes.UNRESOLVED_CONTOUR_OWNERSHIP:
        return PresentedDxfError(
            "تعذر تمييز الدرف عن الفتحات الداخلية.",
            target_text,
            "أغلق كل فتحة بالكامل داخل درفتها دون تلامس ملتبس.",
            code,
            issue.category,
        )
    if code == codes.INVALID_PART_TOPOLOGY:
        return PresentedDxfError(
            "شكل إحدى الدرف أو فتحاتها غير صالح.",
            target_text,
            "أغلق المحيط وأزل التقاطعات ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.MATERIAL_OVERLAP:
        return PresentedDxfError(
            "الدرفتان متداخلتان على اللوح.",
            target_text,
            "افصل الدرفتين عن بعضهما.",
            code,
            issue.category,
        )
    if code == codes.KERF_VIOLATION:
        kerf = format_mm(params.get("kerf_mm") or 0)
        return PresentedDxfError(
            "المسافة بين الدرفتين أقل من Kerf.",
            target_text,
            f"اجعل المسافة {kerf} مم أو أكثر.",
            code,
            issue.category,
        )
    if code == codes.HOLE_CLEARANCE_VIOLATION:
        kerf = format_mm(params.get("kerf_mm") or 0)
        return PresentedDxfError(
            "الدرفة داخل الفتحة قريبة جدًا من حافة الفتحة.",
            target_text,
            f"اترك مسافة Kerf لا تقل عن {kerf} مم من حدود الفتحة.",
            code,
            issue.category,
        )
    if code == codes.PIECE_OUTSIDE_SHEET:
        return PresentedDxfError(
            "الدرفة خارج حدود اللوح.",
            target_text,
            "حرّك الدرفة داخل اللوح ثم أعد الرفع.",
            code,
            issue.category,
        )
    if code == codes.PIECE_INVALID_DIMENSIONS:
        return PresentedDxfError(
            "أبعاد الدرفة غير صالحة.",
            target_text,
            "صحح عرض وطول الدرفة ثم أعد الرفع.",
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
            "الدرف تتجاوز حدود اللوح حتى بعد التشذيب.",
            "اللوح.",
            "حرّك الدرف داخل اللوح ثم أعد الرفع.",
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
        return PresentedDxfError(
            f"علامة الطبقة {layer} على درفة ليست Extra.",
            target_text,
            "ضع العلامة داخل درفة Extra فقط.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_FLOATING:
        layer = params.get("layer") or issue.target.layer or "؟"
        return PresentedDxfError(
            f"علامة الطبقة {layer} ليست بالكامل داخل درفة Extra.",
            target_text,
            "ضع العلامة بالكامل داخل درفة Extra واحدة.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_SPANS_HOSTS:
        layer = params.get("layer") or issue.target.layer or "؟"
        return PresentedDxfError(
            f"علامة الطبقة {layer} تمتد فوق أكثر من درفة.",
            target_text,
            "ضع كل علامة داخل درفة Extra واحدة.",
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
        return PresentedDxfError(
            f"خانة {kind_name} مفعّلة لكن العلامة ناقصة في DXF.",
            target_text,
            f"أضف علامة {kind_name} على الطبقة {layer} داخل الدرفة.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_ADDON_DUPLICATE:
        layer = params.get("layer") or "؟"
        kind_name = _OVERLAY_KIND_AR.get(str(params.get("overlay_kind") or ""), layer)
        return PresentedDxfError(
            f"يوجد أكثر من علامة {kind_name} لنفس الدرفة.",
            target_text,
            "اترك علامة واحدة فقط ثم أعد الرفع.",
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
            "مسار OFFCUT لا يطابق درفة واحدة بوضوح.",
            target_text,
            "اجعل محيط OFFCUT مطابقًا لمحيط درفة واحدة تمامًا.",
            code,
            issue.category,
        )
    if code == codes.MIXED_RESOURCE_SOURCE:
        return PresentedDxfError(
            "لا تخلط درفات OFFCUT مع درفات اللوح الكامل على نفس المصدر.",
            target_text,
            "افصل قطع OFFCUT في مصدر مستقل.",
            code,
            issue.category,
        )

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
    if code == codes.PLAN_UNPLACED_PIECES:
        return PresentedDxfError("خطة القص تحتوي قطعًا غير موزعة.", "الخطة.", "أكمل التوزيع أو أعد الاستيراد.", code, issue.category)
    if code == codes.MANUFACTURING_REQUIREMENTS_MISSING:
        return PresentedDxfError(
            "خطة القص المحفوظة بلا متطلبات تصنيع صالحة.",
            "الخطة.",
            "أعد حساب الخطة أو أعد استيراد DXF قبل التصنيع/التصدير.",
            code,
            issue.category,
        )

    message = str(params.get("message") or f"تعذر قبول DXF ({code}).")
    return PresentedDxfError(message, target_text, "صحح الرسم ثم أعد رفع الملف.", code, issue.category)


def group_issues(issues: Sequence[DxfValidationIssue]) -> list[list[DxfValidationIssue]]:
    """Group only when code, action template, and compatible targets align."""
    grouped: list[list[DxfValidationIssue]] = []
    index_by_key: dict[tuple[str, str], int] = {}
    for item in sort_issues(list(issues)):
        presented = present_issue(item)
        # Group open/branched contours and identical dimension-less codes.
        if item.code in {codes.CUT_OPEN, codes.CUT_BRANCHED, codes.CUT_SELF_INTERSECTION} and item.target.contour_no is not None:
            key = (item.code, presented.action)
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
    return first


def present_issues(issues: Iterable[DxfValidationIssue]) -> list[PresentedDxfError]:
    return [present_group(group) for group in group_issues(list(issues))]


def present_issues_as_strings(issues: Iterable[DxfValidationIssue]) -> list[str]:
    """Flat Arabic strings for legacy ``DxfImportError.errors`` / tests."""
    lines: list[str] = []
    for item in present_issues(issues):
        lines.append(
            f"ما المشكلة؟ {item.problem} أي درفة/لوح؟ {item.target} ماذا أفعل؟ {item.action}"
        )
    return lines


def render_error_cards_html(issues: Sequence[DxfValidationIssue], *, max_cards: int = 10) -> str:
    """RTL HTML cards for shop-floor dialog. Escapes all dynamic values."""
    presented = present_issues(issues)
    if not presented:
        presented = [
            PresentedDxfError(
                "تعذر التحقق من ملف DXF بسبب خطأ غير معروف.",
                "غير محدد.",
                "صحح الرسم ثم أعد رفع الملف.",
                "UNKNOWN",
                codes.CATEGORY_WORKFLOW,
            )
        ]
    visible = presented[:max_cards]
    remaining = len(presented) - len(visible)
    cards: list[str] = []
    for item in visible:
        cards.append(
            "<div class='alm-dxf-error-card' style='border:1px solid #ccd;border-radius:6px;"
            "padding:10px 12px;margin:0 0 10px;text-align:right;direction:rtl;'>"
            f"<div><strong>ما المشكلة؟</strong> {html.escape(item.problem)}</div>"
            f"<div style='margin-top:6px;'><strong>أي درفة/لوح؟</strong> {html.escape(item.target)}</div>"
            f"<div style='margin-top:6px;'><strong>ماذا أفعل؟</strong> {html.escape(item.action)}</div>"
            "</div>"
        )
    extra = (
        f"<p style='direction:rtl;text-align:right;'>وهناك {remaining} أخطاء إضافية. "
        "صحح الأخطاء الظاهرة أولًا ثم أعد الرفع.</p>"
        if remaining > 0
        else ""
    )
    return (
        "<div class='alm-dxf-error-dialog' style='direction:rtl;text-align:right;'>"
        "<p><strong>تعذر قبول ملف DXF</strong></p>"
        f"{''.join(cards)}{extra}"
        "<p>صحح الرسم ثم أعد رفع الملف. لم يتم استبدال خطة DXF الحالية في الطلب.</p>"
        "</div>"
    )
