from types import SimpleNamespace

from almdina_erp.almdina_erp.services.replacement_service import (
    _build_replacement_snapshot,
    _remnant_fits,
)


def _order(**overrides):
    data = {
        "trim_margin_mm": 5,
        "kerf_mm": 3,
        "full_board_width_mm": 2070,
        "full_board_length_mm": 2800,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _replacement(**overrides):
    data = {
        "original_piece_label": "2.3",
        "board_item": "MDF-WHITE-18",
        "width_cm": 50,
        "length_cm": 90,
        "allow_rotation": 0,
        "edge_long_right": 1,
        "edge_long_left": 0,
        "edge_width_top": 1,
        "edge_width_bottom": 0,
        "edge_type": "قشاط 2سم عادي",
        "notes": "",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_remnant_fit_respects_trim_margin():
    remnant = SimpleNamespace(width_mm=510, length_mm=910)
    assert _remnant_fits(remnant, 50, 90, False, trim_mm=5) is True
    assert _remnant_fits(remnant, 50, 90, False, trim_mm=10) is False


def test_replacement_rotation_only_when_explicitly_allowed():
    remnant = SimpleNamespace(
        name="REM-1",
        width_mm=910,
        length_mm=510,
    )
    order = _order(trim_margin_mm=5)

    allowed = _replacement(width_cm=50, length_cm=90, allow_rotation=1)
    plan = _build_replacement_snapshot(order, allowed, remnant)
    piece = plan["sheets"][0]["pieces"][0]
    assert piece["rotated"] is True
    assert piece["w"] == 90
    assert piece["h"] == 50


def test_replacement_remnant_plan_opens_zero_full_boards():
    remnant = SimpleNamespace(name="REM-2", width_mm=1000, length_mm=1200)
    plan = _build_replacement_snapshot(_order(), _replacement(), remnant)
    assert plan["required_full_boards"] == 0
    assert plan["used_remnants"] == ["REM-2"]
    assert plan["sheets"][0]["source_type"] == "Remnant"
    assert plan["validation"]["is_valid"] is True


def test_replacement_full_board_plan_opens_exactly_one_board():
    plan = _build_replacement_snapshot(_order(), _replacement(), None)
    assert plan["required_full_boards"] == 1
    assert plan["used_remnants"] == []
    assert plan["sheets"][0]["source_type"] == "Full Board"
    assert len(plan["sheets"]) == 1
    assert len(plan["sheets"][0]["pieces"]) == 1


def test_replacement_snapshot_preserves_edge_flags():
    plan = _build_replacement_snapshot(_order(), _replacement(), None)
    piece = plan["sheets"][0]["pieces"][0]
    assert piece["edge_long_right"] == 1
    assert piece["edge_long_left"] == 0
    assert piece["edge_width_top"] == 1
    assert piece["edge_width_bottom"] == 0
    assert piece["edge_type"] == "قشاط 2سم عادي"
