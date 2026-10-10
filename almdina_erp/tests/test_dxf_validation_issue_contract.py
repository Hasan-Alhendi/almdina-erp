"""Domain + presenter contract for structured DXF validation issues."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CUT_INVALID_GEOMETRY,
    CUT_OPEN,
    FORBIDDEN_ROTATION,
    PIECE_INVALID_DIMENSIONS,
    PIECE_OUTSIDE_SHEET,
    TARGET_CONTOUR,
    TARGET_PIECE,
    TARGET_CONTOUR_PAIR,
    TARGET_PIECE_PAIR,
    contour_target,
    contour_pair_target,
    issue,
    piece_target,
    topology_error_to_issue,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import DxfTopologyError
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
    present_issue,
    present_issues,
    present_target,
    render_error_cards_html,
)


def test_issue_shape_is_language_free() -> None:
    item = issue(
        FORBIDDEN_ROTATION,
        "DIMENSIONS",
        target=piece_target(source_piece_no=9),
        params={
            "actual_width_cm": 28.5,
            "actual_height_cm": 59.2,
            "expected_width_cm": 59.2,
            "expected_height_cm": 28.5,
        },
    )
    assert item.code == FORBIDDEN_ROTATION
    assert item.target.source_piece_no == 9
    assert "مدوّرة" not in str(item.params)


def test_contour_target_is_not_door_label() -> None:
    target = contour_target(9)
    assert target.kind == TARGET_CONTOUR
    assert present_target(target) == "مسار القص رقم 9."
    assert "الدرفة 9" not in present_target(target)


def test_proven_piece_target_uses_door_label() -> None:
    target = piece_target(source_piece_no=9, copy_no=2)
    assert target.kind == "piece_copy"
    assert present_target(target) == "الدرفة 9 — النسخة 2."


def test_topology_forbidden_rotation_maps_to_stable_code() -> None:
    mapped = topology_error_to_issue(
        DxfTopologyError(
            "FORBIDDEN_ROTATION",
            expected_piece_index=0,
            actual_width=285,
            actual_height=592,
            expected_width=592,
            expected_height=285,
        ),
        source_piece_no=1,
    )
    assert mapped.code == FORBIDDEN_ROTATION
    assert mapped.target.kind == TARGET_PIECE
    assert mapped.target.source_piece_no == 1


def test_expected_piece_index_is_never_source_piece_number():
    mapped = topology_error_to_issue(
        DxfTopologyError("FORBIDDEN_ROTATION", expected_piece_index=1),
    )
    assert mapped.target.source_piece_no is None
    assert present_target(mapped.target) == "غير محدد."


def test_quantity_copy_two_is_still_source_door_one():
    from almdina_erp.almdina_erp.services.dxf_import_service import _topology_error_issue

    order = SimpleNamespace(pieces=[SimpleNamespace(
        cut_width_cm=30, cut_length_cm=40, finished_width_cm=30,
        finished_length_cm=40, allow_rotation=0, qty=2,
        extra_full_door_double=0, piece_type="Regular",
    )])
    mapped = _topology_error_issue(
        DxfTopologyError("FORBIDDEN_ROTATION", expected_piece_index=1),
        order=order,
    )
    assert mapped.target.source_piece_no == 1
    assert mapped.target.copy_no == 2
    assert present_target(mapped.target) == "الدرفة 1 — النسخة 2."
    assert "الدرفة 2" not in present_target(mapped.target)


def test_pair_target_semantics_are_explicit_before_and_after_identity():
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import MATERIAL_OVERLAP

    error = DxfTopologyError("MATERIAL_FOOTPRINT_OVERLAP", first_key=1, second_key=2)
    contours = topology_error_to_issue(error, pair_identity_proven=False)
    assert contours.target.kind == TARGET_CONTOUR_PAIR
    assert present_target(contours.target) == "مسارا القص 1 و2."

    proven = topology_error_to_issue(
        error,
        pair_identity_proven=True,
        pair_source_piece_nos=(3, 7),
    )
    assert proven.code == MATERIAL_OVERLAP
    assert proven.target.kind == TARGET_PIECE_PAIR
    assert present_target(proven.target) == "الدرفتان 3 و7."


def test_piece_label_alone_never_proves_door_identity():
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import DxfIssueTarget

    text = present_target(DxfIssueTarget(kind=TARGET_PIECE, label="7"))
    assert "الدرفة" not in text
    assert "المعرّف 7" in text


def test_mm_formatter_preserves_one_hundredth_mm():
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import format_mm

    assert format_mm(1220.01) == "1220.01"
    assert format_mm(1220.00) == "1220"
    assert format_mm(5.10) == "5.1"


def test_presenter_rotation_is_actionable_arabic() -> None:
    card = present_issue(
        issue(
            FORBIDDEN_ROTATION,
            "DIMENSIONS",
            target=piece_target(source_piece_no=9),
            params={
                "actual_width_cm": 28.5,
                "actual_height_cm": 59.2,
                "expected_width_cm": 59.2,
                "expected_height_cm": 28.5,
            },
        )
    )
    assert "مدوّرة" in card.problem
    assert "التدوير غير مسموح" in card.problem
    assert card.target == "الدرفة 9."
    assert "59.2" in card.action
    assert "28.5" in card.action


def test_presenter_missing_piece_is_plain_arabic() -> None:
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
        CATEGORY_IDENTITY,
        PIECE_MISSING,
        DxfIssueTarget,
    )

    card = present_issue(
        issue(
            PIECE_MISSING,
            CATEGORY_IDENTITY,
            target=DxfIssueTarget(kind="order"),
            params={
                "actual_count": 1,
                "expected_count": 2,
                "missing_count": 1,
                "missing_sizes": ["40 × 39.9 سم"],
            },
        )
    )
    assert card.problem == "يوجد درفة ناقصة في ملف DXF."
    assert "يحتاج 2" in card.target
    assert "فيه 1" in card.target
    assert "40 × 39.9 سم" in card.action
    assert "CUT_PATH" in card.action
    assert "لا يمكن مطابقة" not in card.problem


def test_presenter_groups_open_contours() -> None:
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
        present_issues,
    )

    cards = present_issues(
        [
            issue(CUT_OPEN, "CONTOUR", target=contour_target(2)),
            issue(CUT_OPEN, "CONTOUR", target=contour_target(4)),
            issue(CUT_OPEN, "CONTOUR", target=contour_target(7)),
        ]
    )
    assert len(cards) == 1
    assert "2" in cards[0].target and "4" in cards[0].target and "7" in cards[0].target
    assert "غير مغلقة" in cards[0].problem


def test_html_cards_escape_xss_payload() -> None:
    payload = '<img src=x onerror=alert(1)>'
    html = render_error_cards_html(
        [
            issue(
                "LEGACY_MESSAGE",
                "WORKFLOW",
                params={"message": payload},
            )
        ]
    )
    assert "<img" not in html
    assert "&lt;img" in html
    assert "onerror=alert(1)" in html  # escaped text content, not an executable attribute
    assert 'onerror=alert(1)>"' not in html
    assert "تعذر قبول ملف DXF" not in html
    assert "ما المشكلة؟" in html


def test_error_card_footer_changes_with_explicit_context():
    item = issue(CUT_INVALID_GEOMETRY, "CONTOUR", target=contour_target(4))
    upload = render_error_cards_html([item], context="upload")
    export = render_error_cards_html([item], context="export")
    assert "صحح الرسم ثم أعد رفع الملف. لم يتم استبدال خطة DXF الحالية في الطلب." in upload
    assert "أصلح المشكلة أعلاه أو أعد حساب الخطة، ثم أعد تصدير DXF." in export
    assert "لم يتم استبدال خطة DXF" not in export
    assert "صحح المحيط على CUT_PATH ثم أعد التصدير." in export
    assert "أعد الرفع" not in export


def test_error_cards_keep_three_arabic_questions_once_and_in_order():
    item = issue(CUT_INVALID_GEOMETRY, "CONTOUR", target=contour_target(4))
    for context in ("upload", "export"):
        html = render_error_cards_html([item], context=context)
        headings = ("ما المشكلة؟", "أين المشكلة؟", "ماذا أفعل؟")
        assert all(html.count(heading) == 1 for heading in headings)
        positions = [html.index(heading) for heading in headings]
        assert positions == sorted(positions)
        assert "direction:rtl" in html


def test_matching_piece_errors_group_without_losing_target_evidence():
    params = {
        "actual_width_cm": 28.5,
        "actual_height_cm": 59.2,
        "expected_width_cm": 59.2,
        "expected_height_cm": 28.5,
    }
    grouped = present_issues(
        [
            issue(FORBIDDEN_ROTATION, "DIMENSIONS", target=piece_target(source_piece_no=n), params=params)
            for n in (1, 2, 3)
        ]
    )

    assert len(grouped) == 1
    assert "3" in grouped[0].problem
    assert len(grouped[0].details) == 3
    assert all(f"الدرفة {n}" in detail for n, detail in enumerate(grouped[0].details, start=1))

    html = render_error_cards_html(
        [
            issue(FORBIDDEN_ROTATION, "DIMENSIONS", target=piece_target(source_piece_no=n), params=params)
            for n in (1, 2, 3)
        ]
    )
    assert "عرض كل المواضع المتأثرة" in html
    assert all(f"الدرفة {n}" in html for n in (1, 2, 3))


def test_error_dialog_expands_all_issues_beyond_initial_ten():
    issues = [
        issue("LEGACY_MESSAGE", "WORKFLOW", params={"message": f"حالة {index}"})
        for index in range(12)
    ]

    html = render_error_cards_html(issues)

    assert "عرض بقية الأخطاء (2)" in html
    assert all(f"حالة {index}" in html for index in range(12))


def test_contour_dimensions_and_bounds_are_never_presented_as_a_door():
    for code in (PIECE_OUTSIDE_SHEET, PIECE_INVALID_DIMENSIONS):
        item = issue(code, "LAYOUT", target=contour_target(9))
        card = present_issue(item)
        rendered = " ".join((card.problem, card.target, card.action))
        assert "مسار القص" in rendered
        assert "الدرفة" not in rendered

        proven = issue(code, "LAYOUT", target=piece_target(source_piece_no=9))
        assert "الدرفة" in present_issue(proven).problem

    unproven = issue(
        PIECE_OUTSIDE_SHEET,
        "LAYOUT",
        target=piece_target(source_piece_no=9),
        params={"identity_unproven": True},
    )
    card = present_issue(unproven)
    assert "الدرفة" not in " ".join((card.problem, card.target, card.action))


def test_special_presenter_formats_precomputed_domain_range_only():
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import SPECIAL_SIZE_MISMATCH
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import _special_range_action

    action = _special_range_action({
        "allowed_min_width_cm": 29.8,
        "allowed_max_width_cm": 30.0,
        "allowed_min_height_cm": 39.8,
        "allowed_max_height_cm": 40.0,
    })
    assert "29.8–30" in action and "39.8–40" in action
    presenter_path = Path(__file__).resolve().parents[1] / "almdina_erp" / "presentation" / "cutting" / "dxf_error_presenter.py"
    source = presenter_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_special_range_action")
    assert "0.2" not in ast.get_source_segment(source, function)
    assert SPECIAL_SIZE_MISMATCH == "SPECIAL_SIZE_MISMATCH"


def test_grouped_self_intersections_preserve_every_contour():
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import CUT_SELF_INTERSECTION
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issues

    cards = present_issues([
        issue(CUT_SELF_INTERSECTION, "CONTOUR", target=contour_target(2)),
        issue(CUT_SELF_INTERSECTION, "CONTOUR", target=contour_target(4)),
        issue(CUT_SELF_INTERSECTION, "CONTOUR", target=contour_target(7)),
    ])
    assert len(cards) == 1
    assert cards[0].target == "مسارات القص 2، 4، 7."


def test_every_runtime_issue_call_has_explicit_presenter_branch():
    root = Path(__file__).resolve().parents[1] / "almdina_erp"
    codes_tree = ast.parse((root / "domain" / "cutting" / "dxf_issue.py").read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: node.value.value
        for node in codes_tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    emitted = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "issue" or not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Name) and arg.id in constants:
                emitted.add(arg.id)
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                emitted.add(arg.value)
    emitted.update({
        "BLOCK_NESTING_TOO_DEEP", "ENTITY_LIMIT_EXCEEDED", "ENTITY_PARSE_FAILED",
        "BLOCK_TRANSFORM_FAILED", "MINSERT_UNSUPPORTED", "DXF_LIBRARY_MISSING",
        "DXF_UNREADABLE", "OVERLAY_UNKNOWN",
    })

    presenter_path = root / "presentation" / "cutting" / "dxf_error_presenter.py"
    presenter_tree = ast.parse(presenter_path.read_text(encoding="utf-8"))
    handled = set()
    for node in ast.walk(presenter_tree):
        if isinstance(node, ast.Compare):
            for value in [node.left, *node.comparators]:
                if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.value.id == "codes":
                    handled.add(value.attr)
                if isinstance(value, (ast.Set, ast.Tuple, ast.List)):
                    handled.update(
                        item.attr for item in value.elts
                        if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == "codes"
                    )
    assert emitted <= handled, f"issue codes missing explicit presenter mappings: {sorted(emitted - handled)}"


def test_unknown_issue_code_uses_safe_non_echoing_fallback():
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
        DxfIssueTarget,
        DxfValidationIssue,
    )

    card = present_issue(
        DxfValidationIssue(
            code="UNRECOGNIZED_INTERNAL_CODE",
            category="WORKFLOW",
            target=DxfIssueTarget(kind="file", label="private-tenant-name.dxf"),
            params={"message": "internal stack details", "path": "/srv/private/file.dxf"},
        )
    )

    assert card.problem == "تعذر التحقق من ملف DXF."
    assert card.target == "تعذر تحديد موضع المشكلة بأمان."
    assert card.action == "راجع مسؤول النظام قبل إعادة المحاولة."
    assert "UNRECOGNIZED_INTERNAL_CODE" not in card.problem
    assert "internal stack details" not in str(card)
    assert "private-tenant-name.dxf" not in str(card)
    assert "/srv/private/file.dxf" not in str(card)


def test_architecture_forbids_arabic_substring_branching_in_strict_service() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "almdina_erp" / "services" / "strict_dxf_import_service.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    value = comparator.value
                    if any("\u0600" <= ch <= "\u06FF" for ch in value):
                        # Arabic string literals may exist in helpers, but must not
                        # be used with `in` against str(error).
                        if isinstance(node.left, ast.Call) and getattr(node.left.func, "id", "") == "str":
                            raise AssertionError(
                                f"Text-coupled Arabic branching found at line {node.lineno}"
                            )
            if isinstance(node.ops[0], ast.In):
                left = node.left
                if isinstance(left, ast.Constant) and isinstance(left.value, str):
                    if any("\u0600" <= ch <= "\u06FF" for ch in left.value):
                        raise AssertionError(
                            f"Arabic substring membership check at line {node.lineno}: {left.value!r}"
                        )


def test_shop_floor_uses_rtl_cards_not_bare_ul_list() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "almdina_erp" / "services" / "shop_floor_dxf_service.py"
    ).read_text(encoding="utf-8")
    assert "render_error_cards_html" in source
    assert "alm-dxf-error-card" in (
        root / "almdina_erp" / "presentation" / "cutting" / "dxf_error_presenter.py"
    ).read_text(encoding="utf-8")
