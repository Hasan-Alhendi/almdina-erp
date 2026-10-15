from __future__ import annotations

from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import (
    physical_edge_margins_mm,
)
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import (
    domain_cutting_engine,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_CONTENT_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_content_ux.js"
)
PLAN_CONTENT_STYLES = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_content_styles.js"
)


def _command(
    rows: list[dict],
    *,
    board_width_cm: float = 122,
    board_length_cm: float = 244,
    trim_cm: float = 0.5,
    kerf_cm: float = 0.3,
) -> OptimizeOrderPlanCommand:
    return OptimizeOrderPlanCommand(
        engine_version="test",
        input_fingerprint="adaptive-margin-test",
        board=BoardGeometry(
            full_width_cm=board_width_cm,
            full_length_cm=board_length_cm,
            trim_cm=trim_cm,
            kerf_cm=kerf_cm,
        ),
        optimizer=OptimizerOptions(
            selected_mode="Auto",
            machine_type="Auto",
            time_limit_sec=1,
            exact_piece_limit=20,
            min_remnant_width_cm=30,
            min_remnant_length_cm=30,
            min_remnant_area_m2=0.09,
        ),
        piece_rows=tuple(rows),
    )


def test_full_board_length_removes_only_top_and_bottom_trim():
    outcome = optimize_order_plan(
        _command(
            [
                {
                    "width_cm": 30,
                    "length_cm": 244,
                    "qty": 1,
                    "allow_rotation": 0,
                }
            ]
        ),
        engine=domain_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert not snapshot["unplaced"]
    assert snapshot["applied_trim_width_cm"] == 0.5
    assert snapshot["applied_trim_length_cm"] == 0
    assert snapshot["usable_board_width_cm"] == 121
    assert snapshot["usable_board_length_cm"] == 244
    assert snapshot["margin_policy"]["left_mm"] == 5
    assert snapshot["margin_policy"]["right_mm"] == 5
    assert snapshot["margin_policy"]["top_mm"] == 0
    assert snapshot["margin_policy"]["bottom_mm"] == 0
    assert any("طول اللوح الكامل" in note for note in snapshot["margin_notes"])
    assert "طول اللوح الكامل" in outcome.packing_score


def test_four_long_doors_reduce_only_side_trim_to_keep_one_board():
    outcome = optimize_order_plan(
        _command(
            [
                {
                    "width_cm": 30,
                    "length_cm": 243,
                    "qty": 4,
                    "allow_rotation": 0,
                }
            ],
            kerf_cm=0.4,
        ),
        engine=domain_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert not snapshot["unplaced"]
    assert outcome.required_boards == 1
    assert snapshot["applied_trim_length_cm"] == 0.5
    assert 0 < snapshot["applied_trim_width_cm"] <= 0.4
    assert snapshot["margin_policy"]["top_mm"] == 5
    assert snapshot["margin_policy"]["bottom_mm"] == 5
    assert snapshot["margin_policy"]["left_mm"] <= 4
    assert snapshot["margin_policy"]["right_mm"] <= 4
    assert any("الأيمن والأيسر" in note for note in snapshot["margin_notes"])


def test_normal_plan_keeps_preferred_trim_and_has_no_warning():
    outcome = optimize_order_plan(
        _command(
            [
                {
                    "width_cm": 40,
                    "length_cm": 80,
                    "qty": 2,
                    "allow_rotation": 1,
                }
            ]
        ),
        engine=domain_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert not snapshot["unplaced"]
    assert snapshot["applied_trim_width_cm"] == 0.5
    assert snapshot["applied_trim_length_cm"] == 0.5
    assert snapshot["margin_policy"]["mode"] == "preferred"
    assert snapshot["margin_notes"] == []
    assert "⚠" not in outcome.packing_score


def test_slack_on_a_later_sheet_is_split_across_both_edges():
    outcome = optimize_order_plan(
        _command(
            [
                {
                    "width_cm": 122,
                    "length_cm": 244,
                    "qty": 1,
                    "allow_rotation": 0,
                },
                {
                    "width_cm": 40,
                    "length_cm": 40,
                    "qty": 3,
                    "allow_rotation": 0,
                },
            ],
            kerf_cm=0.5,
        ),
        engine=domain_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert not snapshot["unplaced"]
    assert outcome.required_boards == 2
    assert snapshot["applied_trim_width_cm"] == 0
    assert snapshot["applied_trim_length_cm"] == 0
    sheets = snapshot["sheets"]
    full = next(
        sheet for sheet in sheets
        if any(piece["w"] >= 122 and piece["h"] >= 244 for piece in sheet["pieces"])
    )
    row = next(sheet for sheet in sheets if sheet is not full)
    assert full["applied_trim_width_cm"] == 0
    assert full["applied_trim_length_cm"] == 0
    door = full["pieces"][0]
    assert (door["x"], door["y"], door["w"], door["h"]) == (0, 0, 122, 244)
    assert row["applied_trim_width_cm"] == 0.5
    assert row["applied_trim_length_cm"] == 0.5
    pieces = row["pieces"]
    assert len(pieces) == 3
    assert min(piece["x"] for piece in pieces) == 0
    assert max(piece["x"] + piece["w"] for piece in pieces) == 121
    assert max(piece["y"] + piece["h"] for piece in pieces) == 243
    xs = sorted(piece["x"] for piece in pieces)
    assert xs[1] - (xs[0] + 40) == 0.5
    assert xs[2] - (xs[1] + 40) == 0.5


def test_fourteen_millimetres_with_three_millimetre_kerf_keeps_five_on_both_sides():
    outcome = optimize_order_plan(
        _command(
            [
                {
                    "width_cm": 122,
                    "length_cm": 244,
                    "qty": 1,
                    "allow_rotation": 0,
                },
                {
                    "width_cm": 40,
                    "length_cm": 40,
                    "qty": 3,
                    "allow_rotation": 0,
                },
            ],
            kerf_cm=0.3,
        ),
        engine=domain_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert not snapshot["unplaced"]
    assert outcome.required_boards == 2
    assert snapshot["applied_trim_width_cm"] == 0
    assert snapshot["kerf_cm"] == 0.3
    full = next(
        sheet for sheet in snapshot["sheets"]
        if any(piece["w"] >= 122 and piece["h"] >= 244 for piece in sheet["pieces"])
    )
    row = next(sheet for sheet in snapshot["sheets"] if sheet is not full)
    assert physical_edge_margins_mm(full, snapshot) == {
        "left": 0.0,
        "right": 0.0,
        "top": 0.0,
        "bottom": 0.0,
    }
    pieces = sorted(row["pieces"], key=lambda piece: piece["x"])
    assert [piece["w"] for piece in pieces] == [40, 40, 40]
    assert pieces[1]["x"] - (pieces[0]["x"] + pieces[0]["w"]) == pytest.approx(0.3)
    assert pieces[2]["x"] - (pieces[1]["x"] + pieces[1]["w"]) == pytest.approx(0.3)
    margins = physical_edge_margins_mm(row, snapshot)
    assert margins["left"] >= 5
    assert margins["right"] >= 5
    assert margins["bottom"] >= 5
    assert margins["left"] + margins["right"] == pytest.approx(14)
    assert pieces[0]["x"] == 0
    assert pieces[-1]["x"] == pytest.approx(80.6)


def test_impossible_piece_is_not_hidden_by_margin_relaxation():
    outcome = optimize_order_plan(
        _command(
            [
                {
                    "width_cm": 123,
                    "length_cm": 245,
                    "qty": 1,
                    "allow_rotation": 0,
                }
            ]
        ),
        engine=domain_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert snapshot["unplaced"]
    assert snapshot["applied_trim_width_cm"] == 0.5
    assert snapshot["applied_trim_length_cm"] == 0.5
    assert snapshot["margin_notes"] == []


def test_operator_warning_is_visible_idempotent_and_mobile_friendly():
    source = PLAN_CONTENT_UX.read_text(encoding="utf-8")
    styles = PLAN_CONTENT_STYLES.read_text(encoding="utf-8")

    assert "function ensureMarginPolicyAlert" in source
    assert "normalizedMarginNotes" in source
    assert 'className = "dco-margin-policy-alert"' in source
    assert "تنبيه هامش التشذيب" in source
    assert "marginSignature" in source
    assert 'existing.dataset.marginSignature === signature' in source
    assert 'role", "status"' in source
    assert 'aria-live", "polite"' in source
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in styles
    assert '["يمين", margins.right]' in source
    assert '["يسار", margins.left]' in source
    assert '["أعلى", margins.top]' in source
    assert '["أسفل", margins.bottom]' in source
    assert "physicalMarginsMm" in source


def test_zero_margin_edges_are_visually_marked_without_touching_cut_geometry():
    source = PLAN_CONTENT_UX.read_text(encoding="utf-8")
    styles = PLAN_CONTENT_STYLES.read_text(encoding="utf-8")

    assert "function zeroMarginEdges" in source
    assert "function ensureOriginalBoardEdges" in source
    assert "function buildOriginalEdgeCaption" in source
    assert "dco-board-original-edges" in source
    assert "card.insertBefore(buildOriginalEdgeCaption(edges), board)" in source
    assert "board.appendChild(buildOriginalEdgeMarker" not in source
    assert "dco-board-original-edge--top" in styles
    assert "dco-board-original-edge--bottom" in styles
    assert "dco-board-original-edge--left" in styles
    assert "dco-board-original-edge--right" in styles
    assert "dco-board-original-edges" in styles
    assert "position:static" in styles
    assert "حافة أصلية · أعلى" in source
    assert "حافة أصلية · أسفل" in source
    assert "originalEdgeSignature" in source
    assert "ZERO_MARGIN_EPSILON_MM" in source
    assert "ensureOriginalBoardEdges(planRoot, plan)" in source


def test_margin_warning_is_compact_except_when_original_edge_is_used():
    source = PLAN_CONTENT_UX.read_text(encoding="utf-8")
    styles = PLAN_CONTENT_STYLES.read_text(encoding="utf-8")

    assert "const hasOriginalEdge = Boolean(margins.anyOriginal)" in source
    assert "const detailNotes = margins.everySheetOriginal ? notes : []" in source
    assert "بعض الألواح تلامس حافة اللوح الأصلية؛ افحص استقامتها قبل التنفيذ." in source
    assert "تم تخفيض الهامش تلقائيًا بالقدر اللازم للحفاظ على قياسات القطع." in source
    assert "تم استخدام حافة أصلية من اللوح؛ افحص استقامتها قبل التنفيذ." in source
    assert "dco-margin-policy-alert__summary" in source
    assert "dco-margin-policy-alert__details" in source
    assert "dco-margin-policy-alert__row" in source
    assert "dco-margin-policy-alert__copy" in source
    assert "dco-margin-policy-alert__edge${zeroClass}" in source
    assert ".dco-margin-policy-alert__edge.is-zero" in styles
    assert "justify-content:space-between" in styles


def test_cutting_plan_sections_are_always_arabic_for_factory_operator_ui():
    source = PLAN_CONTENT_UX.read_text(encoding="utf-8")

    assert "function applyArabicPlanLabels" in source
    assert "function isArabic" not in source
    assert 'cut_geometry_section: "إعدادات تنفيذ القص"' in source
    assert 'optimizer_section: "محرك خطة القص"' in source
    assert 'plan_section: "توزيع القطع على الألواح"' in source
    assert "applyArabicPlanLabels(frm);" in source
