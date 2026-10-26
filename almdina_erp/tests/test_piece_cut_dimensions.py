from decimal import Decimal
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    CutDimensionError,
    SIDE_LONG_LEFT,
    SIDE_LONG_RIGHT,
    SIDE_WIDTH_BOTTOM,
    SIDE_WIDTH_TOP,
    calculate_cut_dimensions,
    dimensions_match_exact,
    l_shaped_raw_cut,
)
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
    build_order_piece_cut_specs,
)


def _row(**overrides):
    values = {
        "width_cm": 60,
        "length_cm": 100,
        "qty": 1,
        "allow_rotation": 0,
        "piece_type": "Regular",
        "edge_long_right": 0,
        "edge_long_left": 0,
        "edge_width_top": 0,
        "edge_width_bottom": 0,
        "edge_long_right_type_override": "",
        "edge_long_left_type_override": "",
        "edge_width_top_type_override": "",
        "edge_width_bottom_type_override": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _order(row, default_edge_type="Default 1mm"):
    return SimpleNamespace(pieces=[row], default_edge_type=default_edge_type)


def _profiles(names):
    catalog = {
        "Default 1mm": {"name": "Default 1mm", "thickness_mm": 1, "disabled": 0},
        "Override 2mm": {"name": "Override 2mm", "thickness_mm": 2, "disabled": 0},
    }
    return {name: catalog[name] for name in names if name in catalog}


def test_finished_size_is_unchanged_without_edge_banding():
    result = calculate_cut_dimensions(
        finished_width_cm=60,
        finished_length_cm=100,
        side_thickness_mm={},
    )
    assert str(result.finished_width_cm) == "60.000"
    assert str(result.finished_length_cm) == "100.000"
    assert str(result.cut_width_cm) == "60.000"
    assert str(result.cut_length_cm) == "100.000"


def test_long_edge_thickness_is_deducted_from_width_only():
    result = calculate_cut_dimensions(
        finished_width_cm=60,
        finished_length_cm=100,
        side_thickness_mm={SIDE_LONG_RIGHT: 1, SIDE_LONG_LEFT: 2},
    )
    assert str(result.cut_width_cm) == "59.700"
    assert str(result.cut_length_cm) == "100.000"


def test_width_edge_thickness_is_deducted_from_length_only():
    result = calculate_cut_dimensions(
        finished_width_cm=60,
        finished_length_cm=100,
        side_thickness_mm={SIDE_WIDTH_TOP: 1, SIDE_WIDTH_BOTTOM: 2},
    )
    assert str(result.cut_width_cm) == "60.000"
    assert str(result.cut_length_cm) == "99.700"


def test_piece_dimensions_have_no_two_millimeter_acceptance_tolerance():
    assert dimensions_match_exact(59.9, 100, 59.900, 100.000)
    assert not dimensions_match_exact(59.901, 100, 59.900, 100.000)


def test_side_override_and_default_profile_are_applied_independently():
    row = _row(
        edge_long_right=1,
        edge_long_left=1,
        edge_long_left_type_override="Override 2mm",
        edge_width_top=1,
    )
    spec = build_order_piece_cut_specs(_order(row), profile_loader=_profiles)[0]
    assert str(spec.finished_width_cm) == "60.000"
    assert str(spec.finished_length_cm) == "100.000"
    assert str(spec.cut_width_cm) == "59.700"
    assert str(spec.cut_length_cm) == "99.900"
    assert str(spec.width_deduction_mm) == "3"
    assert str(spec.length_deduction_mm) == "1"


def test_selected_edge_without_profile_is_rejected_clearly():
    row = _row(edge_long_right=1)
    with pytest.raises(CutDimensionError, match="نوع القشاط"):
        build_order_piece_cut_specs(_order(row, default_edge_type=""), profile_loader=_profiles)


def _l_cut(**overrides):
    values = dict(
        finished_width_cm=40,
        finished_length_cm=80,
        notch_width_cm=8,
        notch_length_cm=16,
        position="Bottom Right",
        side_thickness_mm={},
        edge_break=False,
        edge_break_thickness_mm=None,
    )
    values.update(overrides)
    return l_shaped_raw_cut(**values)


def test_l_notch_without_inner_band_keeps_the_finished_bite():
    raw = _l_cut()
    assert raw.proven is True
    assert raw.raw_notch_width_cm == Decimal("8.000")
    assert raw.raw_notch_length_cm == Decimal("16.000")
    assert raw.width.expected_raw_cm == Decimal("32.000")
    assert raw.length.expected_raw_cm == Decimal("64.000")
    assert raw.width.band_mm == Decimal("0")


def test_inner_band_and_outer_terminator_deduct_on_their_own_axes():
    raw = _l_cut(
        edge_break=True,
        edge_break_thickness_mm=1,
        side_thickness_mm={SIDE_LONG_LEFT: 1, SIDE_WIDTH_TOP: 2},
    )
    assert raw.width.band_mm == Decimal("2")
    assert raw.width.expected_raw_cm == Decimal("31.800")
    assert raw.raw_notch_width_cm == Decimal("8.100")
    assert raw.length.band_mm == Decimal("3")
    assert raw.length.expected_raw_cm == Decimal("63.700")
    assert raw.raw_notch_length_cm == Decimal("16.100")


def test_notch_side_outer_band_does_not_shorten_the_remnant_again():
    raw = _l_cut(
        edge_break=True,
        edge_break_thickness_mm=1,
        side_thickness_mm={SIDE_LONG_RIGHT: 1},
    )
    assert raw.width.band_mm == Decimal("1")
    assert raw.width.expected_raw_cm == Decimal("31.900")
    assert raw.raw_notch_width_cm == Decimal("8.000")


def test_top_right_length_uses_the_bottom_terminator_and_the_top_notch_side():
    raw = _l_cut(
        position="Top Right",
        edge_break=True,
        edge_break_thickness_mm=1,
        side_thickness_mm={SIDE_WIDTH_TOP: 2, SIDE_WIDTH_BOTTOM: 1, SIDE_LONG_RIGHT: 3},
    )
    assert raw.width.expected_raw_cm == Decimal("31.900")
    assert raw.raw_notch_width_cm == Decimal("7.800")
    assert raw.length.band_mm == Decimal("2")
    assert raw.length.expected_raw_cm == Decimal("63.800")
    assert raw.raw_notch_length_cm == Decimal("15.900")


def test_unknown_inner_thickness_does_not_invent_a_deduction():
    raw = _l_cut(edge_break=True, edge_break_thickness_mm=None, side_thickness_mm={SIDE_LONG_LEFT: 1})
    assert raw.proven is False
    assert raw.raw_notch_width_cm is None
    assert raw.width.band_mm is None
    assert raw.width.expected_raw_cm is None


def test_l_break_thickness_is_loaded_without_changing_outer_cut_size():
    row = _row(piece_type="L-Shaped Corner", edge_break=1, edge_type="Override 2mm")
    spec = build_order_piece_cut_specs(_order(row, default_edge_type=""), profile_loader=_profiles)[0]
    assert spec.edge_break_thickness_mm == Decimal("2")
    assert spec.cut_width_cm == Decimal("60.000")
    assert spec.cut_length_cm == Decimal("100.000")


def test_missing_l_break_type_does_not_block_the_order():
    row = _row(piece_type="L-Shaped Corner", edge_break=1)
    spec = build_order_piece_cut_specs(_order(row, default_edge_type=""), profile_loader=_profiles)[0]
    assert spec.edge_break_thickness_mm is None


def test_clipped_break_does_not_receive_an_l_thickness():
    row = _row(piece_type="Clipped Corner", edge_break=1)
    spec = build_order_piece_cut_specs(_order(row), profile_loader=_profiles)[0]
    assert spec.edge_break_thickness_mm is None


def test_calculation_never_mutates_finished_dimensions():
    row = _row(edge_long_right=1, edge_width_top=1)
    original = (row.width_cm, row.length_cm)
    spec = build_order_piece_cut_specs(_order(row), profile_loader=_profiles)[0]
    assert (row.width_cm, row.length_cm) == original
    assert str(spec.cut_width_cm) == "59.900"
    assert str(spec.cut_length_cm) == "99.900"
