from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import (
    realize_sheet_edge_trim,
)


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
