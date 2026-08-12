from __future__ import annotations

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.infrastructure.cutting.legacy_engine import (
    legacy_cutting_engine,
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
        engine=legacy_cutting_engine,
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
        engine=legacy_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert not snapshot["unplaced"]
    assert outcome.required_boards == 1
    assert snapshot["applied_trim_length_cm"] == 0.5
    assert snapshot["applied_trim_width_cm"] <= 0.4
    assert snapshot["applied_trim_width_cm"] > 0
    assert snapshot["margin_policy"]["top_mm"] == 5
    assert snapshot["margin_policy"]["bottom_mm"] == 5
    assert snapshot["margin_policy"]["left_mm"] <= 4
    assert snapshot["margin_policy"]["right_mm"] <= 4
    assert any("الأيمن والأيسر" in note for note in snapshot["margin_notes"])


def test_normal_plan_keeps_preferred_trim_unchanged():
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
        engine=legacy_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert not snapshot["unplaced"]
    assert snapshot["applied_trim_width_cm"] == 0.5
    assert snapshot["applied_trim_length_cm"] == 0.5
    assert snapshot["margin_policy"]["mode"] == "preferred"
    assert snapshot["margin_notes"] == []


def test_impossible_piece_does_not_hide_error_by_relaxing_trim():
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
        engine=legacy_cutting_engine,
    )

    snapshot = outcome.snapshot
    assert snapshot["unplaced"]
    assert snapshot["applied_trim_width_cm"] == 0.5
    assert snapshot["applied_trim_length_cm"] == 0.5
    assert snapshot["margin_notes"] == []
