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


def test_calculation_never_mutates_finished_dimensions():
    row = _row(edge_long_right=1, edge_width_top=1)
    original = (row.width_cm, row.length_cm)
    spec = build_order_piece_cut_specs(_order(row), profile_loader=_profiles)[0]
    assert (row.width_cm, row.length_cm) == original
    assert str(spec.cut_width_cm) == "59.900"
    assert str(spec.cut_length_cm) == "99.900"
