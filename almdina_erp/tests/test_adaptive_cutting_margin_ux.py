from __future__ import annotations

from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
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

    assert "function ensureMarginPolicyAlert" in source
    assert "normalizedMarginNotes" in source
    assert 'className = "dco-margin-policy-alert"' in source
    assert "تنبيه هامش التشذيب" in source
    assert "marginSignature" in source
    assert 'existing.dataset.marginSignature === signature' in source
    assert 'role", "status"' in source
    assert 'aria-live", "polite"' in source
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in source
    assert '["يمين", policy.right_mm]' in source
    assert '["يسار", policy.left_mm]' in source
    assert '["أعلى", policy.top_mm]' in source
    assert '["أسفل", policy.bottom_mm]' in source


def test_zero_margin_edges_are_visually_marked_without_touching_cut_geometry():
    source = PLAN_CONTENT_UX.read_text(encoding="utf-8")

    assert "function zeroMarginEdges" in source
    assert "function ensureOriginalBoardEdges" in source
    assert "function buildOriginalEdgeMarker" in source
    assert "dco-board-original-edge--top" in source
    assert "dco-board-original-edge--bottom" in source
    assert "dco-board-original-edge--left" in source
    assert "dco-board-original-edge--right" in source
    assert "حافة أصلية · أعلى" in source
    assert "حافة أصلية · أسفل" in source
    assert "originalEdgeSignature" in source
    assert "ZERO_MARGIN_EPSILON_MM" in source
    assert "ensureOriginalBoardEdges(planRoot, plan)" in source


def test_margin_warning_is_compact_except_when_original_edge_is_used():
    source = PLAN_CONTENT_UX.read_text(encoding="utf-8")

    assert "const hasOriginalEdge = zeroEdges.length > 0" in source
    assert "const detailNotes = hasOriginalEdge ? notes : []" in source
    assert "تم تخفيض الهامش تلقائيًا بالقدر اللازم للحفاظ على قياسات القطع." in source
    assert "تم استخدام حافة أصلية من اللوح؛ افحص استقامتها قبل التنفيذ." in source
    assert "dco-margin-policy-alert__summary" in source
    assert "dco-margin-policy-alert__details" in source
    assert "dco-margin-policy-alert__edge${zeroClass}" in source
    assert ".dco-margin-policy-alert__edge.is-zero" in source


def test_cutting_plan_sections_are_always_arabic_for_factory_operator_ui():
    source = PLAN_CONTENT_UX.read_text(encoding="utf-8")

    assert "function applyArabicPlanLabels" in source
    assert "function isArabic" not in source
    assert 'cut_geometry_section: "إعدادات تنفيذ القص"' in source
    assert 'optimizer_section: "محرك خطة القص"' in source
    assert 'plan_section: "توزيع القطع على الألواح"' in source
    assert "applyArabicPlanLabels(frm);" in source
