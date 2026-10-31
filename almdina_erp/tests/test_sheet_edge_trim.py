from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import (
    physical_edge_margins_mm,
    realize_sheet_edge_trim,
    resolved_sheet_trim_cm,
)
import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import DxfGeometrySnapshotError
from almdina_erp.almdina_erp.domain.cutting.optimizer import _largest_reusable_free_area


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("scope", ["sheet", "plan"])
def test_equal_full_and_usable_proves_zero_trim_when_applied_is_missing(axis, scope):
    sheet = {"full_width_cm": 122, "usable_width_cm": 122,
             "full_length_cm": 244, "usable_length_cm": 244}
    plan = {"trim_cm": 0.5}
    if scope == "plan":
        plan.update(full_board_width_cm=122, usable_board_width_cm=122,
                    full_board_length_cm=244, usable_board_length_cm=244)
        sheet = {}
    assert resolved_sheet_trim_cm(sheet, plan, axis=axis) == 0


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("scope", ["sheet", "plan"])
def test_usable_larger_than_full_cannot_fall_back_to_preferred_trim(axis, scope):
    sheet = {"full_width_cm": 122, "usable_width_cm": 123,
             "full_length_cm": 244, "usable_length_cm": 245}
    plan = {"trim_cm": 0.5}
    if scope == "plan":
        plan.update(full_board_width_cm=122, usable_board_width_cm=123,
                    full_board_length_cm=244, usable_board_length_cm=245)
        sheet = {}
    with pytest.raises(DxfGeometrySnapshotError):
        resolved_sheet_trim_cm(sheet, plan, axis=axis)


def _sheet(pieces, *, width_trim=0.0, length_trim=0.0, board_w=122.0, board_h=244.0):
    return {
        "resource_kind": "FULL_BOARD",
        "w": board_w - (width_trim * 2),
        "h": board_h - (length_trim * 2),
        "applied_trim_width_cm": width_trim,
        "applied_trim_length_cm": length_trim,
        "pieces": pieces,
    }


def _apply(sheets, **kwargs):
    balance = kwargs.pop("balance_existing_applied", False)
    remnant_options = {
        "machine_type": kwargs.pop("machine_type", "Auto"),
        "min_remnant_width_cm": kwargs.pop("min_remnant_width_cm", 30.0),
        "min_remnant_length_cm": kwargs.pop("min_remnant_length_cm", 30.0),
        "min_remnant_area_m2": kwargs.pop("min_remnant_area_m2", 0.09),
        "max_centerable_edge_gap_cm": kwargs.pop("max_centerable_edge_gap_cm", 5.0),
    }
    realize_sheet_edge_trim(
        sheets,
        full_width_cm=kwargs.pop("full_width_cm", 122),
        full_length_cm=kwargs.pop("full_length_cm", 244),
        preferred_width_trim_cm=kwargs.pop("preferred_width_trim_cm", 0.5),
        preferred_length_trim_cm=kwargs.pop("preferred_length_trim_cm", 0.5),
        balance_existing_applied=balance,
        **remnant_options,
    )


def test_ten_millimetres_of_slack_becomes_five_on_each_side():
    pieces = [
        {"x": 0, "y": 204, "w": 40, "h": 40},
        {"x": 40.5, "y": 204, "w": 40, "h": 40},
        {"x": 81, "y": 204, "w": 40, "h": 40},
    ]
    sheet = _sheet(pieces)
    _apply([sheet])

    assert sheet["applied_trim_width_cm"] == 0.5
    assert sheet["applied_trim_length_cm"] == 0.5
    assert [piece["x"] for piece in pieces] == [0, 40.5, 81]
    assert [piece["y"] for piece in pieces] == [203, 203, 203]
    assert max(piece["x"] + piece["w"] for piece in pieces) == 121
    assert max(piece["y"] + piece["h"] for piece in pieces) == 243


def test_six_millimetres_of_slack_keeps_three_on_each_side():
    pieces = [
        {"x": 0, "y": 204, "w": 40, "h": 40},
        {"x": 40.5, "y": 204, "w": 40, "h": 40},
        {"x": 81.4, "y": 204, "w": 40, "h": 40},
    ]
    sheet = _sheet(pieces)
    _apply([sheet])

    assert sheet["applied_trim_width_cm"] == 0.3
    assert [piece["x"] for piece in pieces] == [0, 40.5, 81.4]
    assert max(piece["x"] + piece["w"] for piece in pieces) == 121.4


def test_a_full_door_keeps_zero_trim_and_its_place():
    pieces = [{"x": 0, "y": 0, "w": 122, "h": 244}]
    sheet = _sheet(pieces)
    _apply([sheet])

    assert sheet["applied_trim_width_cm"] == 0
    assert sheet["applied_trim_length_cm"] == 0
    assert pieces[0] == {"x": 0, "y": 0, "w": 122, "h": 244}


def test_existing_preferred_trim_is_not_repacked():
    pieces = [{"x": 0, "y": 193, "w": 40, "h": 40}]
    sheet = _sheet(pieces, width_trim=0.5, length_trim=0.5)
    _apply([sheet])

    assert sheet["applied_trim_width_cm"] == 0.5
    assert sheet["applied_trim_length_cm"] == 0.5
    assert pieces[0]["x"] == 0
    assert pieces[0]["y"] == 193


def test_target_equal_to_current_keeps_saved_usable_coordinates():
    pieces = [
        {"x": 0, "y": 203, "w": 40, "h": 40},
        {"x": 40.3, "y": 203, "w": 40, "h": 40},
        {"x": 80.6, "y": 203, "w": 40, "h": 40},
    ]
    sheet = _sheet(pieces, width_trim=0.5, length_trim=0.5)
    sheet["full_width_cm"] = 122
    sheet["full_length_cm"] = 244
    before = [dict(piece) for piece in pieces]
    _apply([sheet])

    assert pieces == before
    assert sheet["applied_trim_width_cm"] == 0.5
    margins = physical_edge_margins_mm(sheet, {"applied_trim_width_cm": 0, "applied_trim_length_cm": 0})
    assert margins["left"] == 5
    assert margins["right"] == 9
    assert margins["bottom"] == 5
    assert margins["top"] == 2035


def test_target_equal_to_current_does_not_pull_an_already_inset_group():
    pieces = [{"x": 0.2, "y": 203, "w": 40, "h": 40}]
    sheet = _sheet(pieces, width_trim=0.5, length_trim=0.5)
    _apply([sheet])

    assert pieces[0]["x"] == 0.2
    assert pieces[0]["y"] == 203


def test_missing_sheet_trim_is_recovered_from_usable_width_not_plan_zero():
    sheet = {
        "full_width_cm": 122,
        "full_length_cm": 244,
        "usable_width_cm": 121,
        "usable_length_cm": 243,
        "pieces": [
            {"x": 0, "y": 203, "w": 40, "h": 40},
            {"x": 40.3, "y": 203, "w": 40, "h": 40},
            {"x": 80.6, "y": 203, "w": 40, "h": 40},
        ],
    }
    plan = {
        "applied_trim_width_cm": 0,
        "applied_trim_length_cm": 0,
        "trim_cm": 0.5,
        "full_board_width_cm": 122,
        "full_board_length_cm": 244,
        "usable_board_width_cm": 122,
        "usable_board_length_cm": 244,
    }

    assert resolved_sheet_trim_cm(sheet, plan, axis="x") == 0.5
    assert resolved_sheet_trim_cm(sheet, plan, axis="y") == 0.5
    margins = physical_edge_margins_mm(sheet, plan)
    assert (margins["left"], margins["right"], margins["bottom"]) == (5, 9, 5)


def test_old_flush_snapshot_is_not_given_trim_without_recalculation():
    sheet = {
        "applied_trim_width_cm": 0,
        "applied_trim_length_cm": 0,
        "full_width_cm": 122,
        "full_length_cm": 244,
        "usable_width_cm": 122,
        "usable_length_cm": 244,
        "pieces": [
            {"x": 0, "y": 204, "w": 40, "h": 40},
            {"x": 40.3, "y": 204, "w": 40, "h": 40},
            {"x": 80.6, "y": 204, "w": 40, "h": 40},
        ],
    }
    plan = {"applied_trim_width_cm": 0, "applied_trim_length_cm": 0, "trim_cm": 0.5}

    assert resolved_sheet_trim_cm(sheet, plan, axis="x") == 0
    assert physical_edge_margins_mm(sheet, plan)["left"] == 0
    assert physical_edge_margins_mm(sheet, plan)["right"] == 14


@pytest.mark.parametrize(
    ("piece_width", "expected_margin"),
    [(98.0, 10.0), (97.0, 15.0)],
)
def test_mandatory_five_mm_minimum_balances_additional_width_slack(piece_width, expected_margin):
    pieces = [{"x": 0.5, "y": 10, "w": piece_width, "h": 20}]
    sheet = _sheet(pieces, width_trim=0.5, length_trim=0.5, board_w=100, board_h=40)
    sheet["full_width_cm"] = 100
    sheet["full_length_cm"] = 40
    _apply([sheet], full_width_cm=100, full_length_cm=40, balance_existing_applied=True)

    margins = physical_edge_margins_mm(sheet)
    assert margins["left"] == pytest.approx(expected_margin)
    assert margins["right"] == pytest.approx(expected_margin)
    assert sheet["applied_trim_width_cm"] >= 0.5


def test_balances_vertical_rows_independently_when_their_geometry_is_disjoint():
    pieces = [
        {"x": 0, "y": 0, "w": 20, "h": 10},
        {"x": 20.5, "y": 0, "w": 20, "h": 10},
        {"x": 0, "y": 20, "w": 10, "h": 10},
    ]
    sheet = _sheet(pieces, width_trim=0.5, length_trim=0.5, board_w=100, board_h=40)
    sheet["full_width_cm"] = 100
    sheet["full_length_cm"] = 40
    _apply(
        [sheet], full_width_cm=100, full_length_cm=40,
        balance_existing_applied=True,
        max_centerable_edge_gap_cm=100,
        min_remnant_width_cm=101,
        min_remnant_length_cm=41,
    )

    assert [piece["x"] for piece in pieces] == pytest.approx([29.25, 49.75, 44.5])
    assert physical_edge_margins_mm(sheet)["left"] >= 5
    assert physical_edge_margins_mm(sheet)["right"] >= 5


def test_shape_aware_row_is_left_untouched_for_safety():
    piece = {"x": 0, "y": 0, "w": 20, "h": 10, "piece_type": "Glass"}
    sheet = _sheet([piece], width_trim=0.5, length_trim=0.5, board_w=100, board_h=40)
    _apply([sheet], full_width_cm=100, full_length_cm=40, balance_existing_applied=True)

    assert (piece["x"], piece["y"]) == (0, 0)


def test_large_vertical_remnant_blocks_vertical_but_not_safe_horizontal_centering():
    piece = {"x": 0, "y": 0, "w": 40, "h": 13.9}
    sheet = _sheet([piece], width_trim=0.5, length_trim=0.5)
    sheet.update(full_width_cm=122, full_length_cm=244)
    original_piece = dict(piece)
    original_kerf = 0.3
    sheet["kerf_cm"] = original_kerf

    _apply([sheet], balance_existing_applied=True, max_centerable_edge_gap_cm=50)

    assert piece["x"] == original_piece["x"]
    assert piece["y"] == original_piece["y"]
    assert sheet["applied_trim_width_cm"] == 0.5
    assert sheet["applied_trim_length_cm"] == 0.5
    assert sheet["kerf_cm"] == original_kerf
    actual_remnant = _largest_reusable_free_area(
        {"sheets": [sheet]}, 30, 30, .09, machine_type="CNC Router"
    )
    centered_sheet = _sheet(
        [{"x": 40.5, "y": (243 - 13.9) / 2, "w": 40, "h": 13.9}],
        width_trim=0.5,
        length_trim=0.5,
    )
    after_remnant = _largest_reusable_free_area(
        {"sheets": [centered_sheet]}, 30, 30, .09, machine_type="CNC Router"
    )
    assert actual_remnant == pytest.approx(2.77211)
    assert after_remnant == pytest.approx(1.386055)
    assert after_remnant < actual_remnant


def test_useful_remnant_blocks_only_axis_moves_that_reduce_its_area():
    pieces = [
        {"x": 0, "y": 0, "w": 40, "h": 40},
        {"x": 40.3, "y": 0, "w": 40, "h": 40},
        {"x": 0, "y": 40.3, "w": 40, "h": 40},
    ]
    sheet = _sheet(pieces, width_trim=0.5, length_trim=0.5)
    sheet.update(full_width_cm=122, full_length_cm=244)
    original = [dict(piece) for piece in pieces]

    _apply([sheet], balance_existing_applied=True, max_centerable_edge_gap_cm=100)

    assert [piece["x"] for piece in pieces] == pytest.approx([20.35, 60.65, 40.5])
    assert [piece["y"] for piece in pieces] == [piece["y"] for piece in original]
    after_remnant = _largest_reusable_free_area(
        {"sheets": [sheet]}, 30, 30, 0.09, machine_type="CNC Router"
    )
    assert after_remnant == pytest.approx(1.96867)


def test_small_slack_centers_when_no_remnant_meets_factory_thresholds():
    piece = {"x": 0.5, "y": 10, "w": 98, "h": 20}
    sheet = _sheet([piece], width_trim=0.5, length_trim=0.5, board_w=100, board_h=40)
    sheet.update(full_width_cm=100, full_length_cm=40)

    _apply([sheet], full_width_cm=100, full_length_cm=40, balance_existing_applied=True)

    assert physical_edge_margins_mm(sheet)["left"] == pytest.approx(10)
    assert physical_edge_margins_mm(sheet)["right"] == pytest.approx(10)


def test_centers_horizontal_row_without_splitting_large_vertical_remnant():
    pieces = [
        {"x": 0, "y": 0, "w": 40, "h": 13.9},
        {"x": 40.5, "y": 0, "w": 40, "h": 13.9},
        {"x": 81, "y": 0, "w": 40, "h": 13.9},
    ]
    sheet = _sheet(pieces, width_trim=0, length_trim=0)
    sheet.update(full_width_cm=122, full_length_cm=244, kerf_cm=0.5)
    before = _largest_reusable_free_area(
        {"sheets": [sheet]}, 30, 30, 0.09, machine_type="CNC Router"
    )

    _apply(
        [sheet], full_width_cm=122, full_length_cm=244,
        preferred_width_trim_cm=0, preferred_length_trim_cm=0,
        balance_existing_applied=True, machine_type="CNC Router",
    )

    after = _largest_reusable_free_area(
        {"sheets": [sheet]}, 30, 30, 0.09, machine_type="CNC Router"
    )
    assert [piece["x"] for piece in pieces] == pytest.approx([0.5, 41, 81.5])
    assert [piece["y"] for piece in pieces] == [0, 0, 0]
    assert (sheet["applied_trim_width_cm"], sheet["applied_trim_length_cm"]) == (0, 0)
    assert sheet["kerf_cm"] == 0.5
    assert before == pytest.approx(2.80722)
    assert after == pytest.approx(before)


@pytest.mark.parametrize(
    ("left", "right", "limit", "expected_center"),
    [(1, 3, 5, True), (0, 5, 5, True), (0, 6, 5, False),
     (41, 41, 5, False), (1, 3, 10, True), (0, 1, 0, False),
     (0.4, 0.5, 0.5, True), (0.4, 0.5001, 0.5, False)],
)
def test_axis_centering_respects_factory_edge_gap_limit(left, right, limit, expected_center):
    board_w, piece_w = 100.0, 100.0 - left - right
    x = left
    piece = {"x": x, "y": 0, "w": piece_w, "h": 20}
    sheet = _sheet([piece], width_trim=0, length_trim=0, board_w=board_w, board_h=40)
    sheet.update(full_width_cm=board_w, full_length_cm=40)

    _apply(
        [sheet], full_width_cm=board_w, full_length_cm=40,
        preferred_width_trim_cm=0, preferred_length_trim_cm=0,
        balance_existing_applied=True, max_centerable_edge_gap_cm=limit,
        min_remnant_width_cm=101, min_remnant_length_cm=41,
    )

    if expected_center:
        assert piece["x"] == pytest.approx((board_w - piece_w) / 2)
    else:
        assert piece["x"] == pytest.approx(x)


def test_three_door_row_centers_x_within_gap_limit_and_preserves_long_offcut():
    pieces = [
        {"x": 0, "y": 0, "w": 40, "h": 13.9},
        {"x": 40.5, "y": 0, "w": 40, "h": 13.9},
        {"x": 81, "y": 0, "w": 40, "h": 13.9},
    ]
    sheet = _sheet(pieces, width_trim=0, length_trim=0)
    sheet.update(full_width_cm=122, full_length_cm=244, kerf_cm=0.5)
    before = _largest_reusable_free_area(
        {"sheets": [sheet]}, 30, 30, .09, machine_type="CNC Router"
    )

    _apply(
        [sheet], full_width_cm=122, full_length_cm=244,
        preferred_width_trim_cm=0, preferred_length_trim_cm=0,
        balance_existing_applied=True, machine_type="CNC Router",
    )

    after = _largest_reusable_free_area(
        {"sheets": [sheet]}, 30, 30, .09, machine_type="CNC Router"
    )
    assert [piece["x"] for piece in pieces] == pytest.approx([0.5, 41, 81.5])
    assert [piece["y"] for piece in pieces] == [0, 0, 0]
    assert after == pytest.approx(before)


def test_single_door_far_from_both_edges_is_not_centered_by_default_limit():
    piece = {"x": 0, "y": 0, "w": 40, "h": 13.9}
    sheet = _sheet([piece], width_trim=0, length_trim=0)
    sheet.update(full_width_cm=122, full_length_cm=244)

    _apply(
        [sheet], full_width_cm=122, full_length_cm=244,
        preferred_width_trim_cm=0, preferred_length_trim_cm=0,
        balance_existing_applied=True,
    )

    assert (piece["x"], piece["y"]) == (0, 0)
