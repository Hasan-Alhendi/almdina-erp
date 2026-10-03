"""Domain + presenter contract for structured DXF validation issues."""

from __future__ import annotations

import ast
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CUT_OPEN,
    FORBIDDEN_ROTATION,
    TARGET_CONTOUR,
    TARGET_PIECE,
    contour_target,
    issue,
    piece_target,
    topology_error_to_issue,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import DxfTopologyError
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
    present_issue,
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
    assert "تعذر قبول ملف DXF" in html
    assert "ما المشكلة؟" in html


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
