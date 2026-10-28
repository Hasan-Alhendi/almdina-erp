from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import (
    physical_edge_margins_mm,
    realize_sheet_edge_trim,
    resolved_sheet_trim_cm,
)
import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import DxfGeometrySnapshotError


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
    realize_sheet_edge_trim(
        sheets,
        full_width_cm=kwargs.pop("full_width_cm", 122),
        full_length_cm=kwargs.pop("full_length_cm", 244),
        preferred_width_trim_cm=kwargs.pop("preferred_width_trim_cm", 0.5),
        preferred_length_trim_cm=kwargs.pop("preferred_length_trim_cm", 0.5),
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
