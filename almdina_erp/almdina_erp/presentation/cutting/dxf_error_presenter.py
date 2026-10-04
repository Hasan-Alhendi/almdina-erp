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
            return f"علامة Extra المرتبطة بالمعرّف {target.label}."
        if target.layer:
            return f"الطبقة {target.layer}."
        return "علامة Extra."
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

    if code == codes.FORBIDDEN_ROTATION:
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
        problem = (
            "مقاس مسار القص الخاص خارج المجال المسموح."
            if noun == "مسار القص"
            else f"مقاس {noun} الخاصة خارج المجال المسموح."
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
        problem = "مقاسات مسارات القص في DXF لا تطابق مقاسات القص في الطلب."
        if dxf_sizes and expected_sizes:
            problem = (
                f"مقاسات مسارات القص في DXF لا تطابق مقاسات القص في الطلب. "
                f"في الملف: {dxf_sizes}. المطلوب: {expected_sizes}."
            )
        actual_sizes = [str(value) for value in (params.get("extra_sizes") or []) if value]
        required_sizes = [str(value) for value in (params.get("missing_sizes") or []) if value]
        target_parts = []
        if actual_sizes:
            target_parts.append(f"في الملف: {', '.join(actual_sizes)}.")
        if required_sizes:
            target_parts.append(f"المقاسات المطلوبة غير المطابقة: {', '.join(required_sizes)}.")
        target_text = " ".join(target_parts) or present_target(issue.target, params=params)
        return PresentedDxfError(
            problem,
            target_text,
            "طابق كل مسار على CUT_PATH مع مقاس القص المحفوظ (وليس المقاس النهائي).",
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
            f"علامة الطبقة {layer} على {noun} ليست Extra.",
            target_text,
            f"ضع العلامة داخل {noun} من نوع Extra فقط.",
            code,
            issue.category,
        )
    if code == codes.OVERLAY_FLOATING:
        layer = params.get("layer") or issue.target.layer or "؟"
        noun = _piece_noun(issue)
        return PresentedDxfError(
            f"علامة الطبقة {layer} ليست بالكامل داخل {noun} من نوع Extra.",
            target_text,
            f"ضع العلامة بالكامل داخل {noun} واحد من نوع Extra.",
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
            f"ضع كل علامة داخل {noun} واحد من نوع Extra.",
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
    if code == codes.OVERLAY_UNKNOWN:
        return PresentedDxfError(
            "علامة تصنيع في DXF غير معروفة أو غير صالحة.",
            target_text,
            "راجع طبقات علامات Extra المدعومة ثم أعد الرفع.",
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
    if contour_nos and group[0].code == codes.CUT_SELF_INTERSECTION:
        listed = "، ".join(str(no) for no in contour_nos)
        return PresentedDxfError(
            "بعض مسارات القص تتقاطع مع نفسها.",
            f"مسارات القص {listed}.",
            "أزل التقاطع الذاتي من هذه المسارات على CUT_PATH.",
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
    remaining = len(presented) - len(visible)
    cards: list[str] = []
    for item in visible:
        cards.append(
            "<div class='alm-dxf-error-card' style='border:1px solid var(--border-color);border-radius:6px;"
            "padding:10px 12px;margin:0 0 10px;text-align:right;direction:rtl;'>"
            f"<div><strong>ما المشكلة؟</strong> {html.escape(item.problem)}</div>"
            f"<div style='margin-top:6px;'><strong>أين المشكلة؟</strong> {html.escape(item.target)}</div>"
            f"<div style='margin-top:6px;'><strong>ماذا أفعل؟</strong> {html.escape(_action_for_context(item.action, context))}</div>"
            "</div>"
        )
    extra = (
        f"<p style='direction:rtl;text-align:right;'>وهناك {remaining} أخطاء إضافية. "
        + ("صحح الأخطاء الظاهرة أولًا ثم أعد الرفع." if context == "upload" else "راجع الأخطاء الظاهرة أولًا ثم أعد التصدير.")
        + "</p>"
        if remaining > 0
        else ""
    )
    footer = (
        "صحح الرسم ثم أعد رفع الملف. لم يتم استبدال خطة DXF الحالية في الطلب."
        if context == "upload"
        else "أصلح المشكلة أعلاه أو أعد حساب الخطة، ثم أعد تصدير DXF."
    )
    return (
        "<div class='alm-dxf-error-dialog' style='direction:rtl;text-align:right;'>"
        f"{''.join(cards)}{extra}"
        f"<p>{footer}</p>"
        "</div>"
    )
