"""Policy cut sizes used by the optimizer are the manufacturing requirements."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    require_cut_dimension_cm,
)
from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    dimensions_match_exact,
)
from almdina_erp.almdina_erp.domain.orders.cut_dimensions import (
    CutDimensionInput,
    calculate_cut_dimensions,
)
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_workspace as workspace
from almdina_erp.almdina_erp.infrastructure.frappe.orders import cut_dimension_adapter


def _piece(**overrides):
    values = {
        "piece_instance_id": "piece-1",
        "width_cm": 60.0,
        "length_cm": 40.0,
        "cut_width_cm": 59.8,
        "cut_length_cm": 39.8,
        "qty": 1,
        "allow_rotation": 1,
        "edge_long_right": 1,
        "edge_long_left": 1,
        "edge_width_top": 1,
        "edge_width_bottom": 1,
        "edge_long_right_thickness_mm": 1,
        "edge_long_left_thickness_mm": 1,
        "edge_width_top_thickness_mm": 1,
        "edge_width_bottom_thickness_mm": 1,
        "edge_type": "PVC",
        "edge_rate_usd": 0,
        "edge_cost_usd": 0,
        "piece_type": "Regular",
        "clipped_corner_position": "",
        "clipped_corner_width_cm": 0,
        "clipped_corner_length_cm": 0,
        "special_shape_geometry_json": "",
        "notes": "",
        "edge_long_right_type_override": "PVC",
        "edge_long_left_type_override": "PVC",
        "edge_width_top_type_override": "PVC",
        "edge_width_bottom_type_override": "PVC",
        "edge_long_type": "PVC",
        "edge_width_type": "PVC",
        "edge_long_thickness_mm": 1,
        "edge_width_thickness_mm": 1,
        "edge_long_rate_usd": 0,
        "edge_width_rate_usd": 0,
        "edge_long_cost_usd": 0,
        "edge_width_cost_usd": 0,
        "cut_size_label": "59.8 × 39.8",
        "area_m2": 0.24,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _order(piece):
    return SimpleNamespace(name="DCO-EDGE", pieces=[piece], default_edge_type="PVC")


def _plan(deduct):
    return SimpleNamespace(deduct_edge_thickness=deduct)


def _calculated(row, *, deduct, thickness_mm):
    result = calculate_cut_dimensions(
        CutDimensionInput(
            final_width_cm=row.width_cm,
            final_length_cm=row.length_cm,
            edge_long_right=row.edge_long_right,
            edge_long_left=row.edge_long_left,
            edge_width_top=row.edge_width_top,
            edge_width_bottom=row.edge_width_bottom,
            edge_long_right_thickness_mm=thickness_mm,
            edge_long_left_thickness_mm=thickness_mm,
            edge_width_top_thickness_mm=thickness_mm,
            edge_width_bottom_thickness_mm=thickness_mm,
            deduct_edge_thickness=deduct,
        )
    )
    return (
        require_cut_dimension_cm(result.cut_width_cm, fieldname="cut_width_cm"),
        require_cut_dimension_cm(result.cut_length_cm, fieldname="cut_length_cm"),
    )


@pytest.fixture
def policy_calculator(monkeypatch):
    def expected(order, row, *, deduct_edge_thickness):
        del order
        return _calculated(
            row,
            deduct=bool(deduct_edge_thickness),
            thickness_mm=row.edge_long_right_thickness_mm,
        )

    monkeypatch.setattr(cut_dimension_adapter, "expected_policy_cut_cm", expected)
    return expected


def _sizes(requirements):
    piece = requirements["pieces"][0]
    return piece["cut_width_cm"], piece["cut_length_cm"]


def test_four_sided_policy_sizes_are_the_real_thicknesses():
    row = _piece()
    assert _calculated(row, deduct=True, thickness_mm=1) == (59.8, 39.8)
    assert _calculated(row, deduct=False, thickness_mm=1) == (60.0, 40.0)
    assert _calculated(row, deduct=True, thickness_mm=2) == (59.6, 39.6)


def test_disabled_deduction_uses_one_cut_size_for_optimizer_and_validation(policy_calculator):
    piece = _piece()
    order = _order(piece)
    plan = _plan(0)
    before = (piece.cut_width_cm, piece.cut_length_cm)

    rows = workspace._piece_rows(order, plan)
    requirements = workspace._manufacturing_requirements(order, plan)
    historical = workspace._manufacturing_requirements(order)

    assert _sizes(requirements) == ("60.000", "40.000")
    assert (rows[0]["width_cm"], rows[0]["length_cm"]) == (60.0, 40.0)
    assert dimensions_match_exact(60.0, 40.0, 60.0, 40.0)
    assert not dimensions_match_exact(
        rows[0]["width_cm"],
        rows[0]["length_cm"],
        float(historical["pieces"][0]["cut_width_cm"]),
        float(historical["pieces"][0]["cut_length_cm"]),
    )
    assert historical["pieces"][0]["cut_width_cm"] == "59.800"
    assert (piece.cut_width_cm, piece.cut_length_cm) == before
    assert requirements["pieces"][0]["piece_instance_id"] == "piece-1:1"
    assert requirements["pieces"][0]["piece_type"] == "Regular"
    assert requirements["pieces"][0]["allow_rotation"] is True


def test_enabled_deduction_keeps_the_calculated_one_millimetre_size(policy_calculator):
    piece = _piece()
    order = _order(piece)
    requirements = workspace._manufacturing_requirements(order, _plan(1))
    rows = workspace._piece_rows(order, _plan(1))

    assert _sizes(requirements) == ("59.800", "39.800")
    assert dimensions_match_exact(
        rows[0]["width_cm"],
        rows[0]["length_cm"],
        59.8,
        39.8,
    )
    assert piece.cut_width_cm == 59.8


def test_switching_policies_recalculates_from_selected_thickness(policy_calculator):
    piece = _piece()
    order = _order(piece)
    enabled = workspace._manufacturing_requirements(order, _plan(1))
    disabled = workspace._manufacturing_requirements(order, _plan(0))
    piece.edge_long_right_thickness_mm = 2
    piece.edge_long_left_thickness_mm = 2
    piece.edge_width_top_thickness_mm = 2
    piece.edge_width_bottom_thickness_mm = 2
    thicker = workspace._manufacturing_requirements(order, _plan(1))

    assert _sizes(enabled) == ("59.800", "39.800")
    assert _sizes(disabled) == ("60.000", "40.000")
    assert _sizes(thicker) == ("59.600", "39.600")
    assert piece.cut_width_cm == 59.8
    assert piece.cut_length_cm == 39.8


def test_historical_requirements_stay_on_the_persisted_order_size(policy_calculator):
    piece = _piece()
    order = _order(piece)
    approved = workspace._manufacturing_requirements(order)
    workspace._manufacturing_requirements(order, _plan(0))

    assert approved == workspace._manufacturing_requirements(order)
    assert approved["pieces"][0]["cut_width_cm"] == "59.800"


def test_committed_sizes_reopen_against_the_same_requirements(policy_calculator):
    piece = _piece(cut_width_cm=60, cut_length_cm=40, cut_size_label="60 × 40")
    order = _order(piece)
    preview = workspace._manufacturing_requirements(order, _plan(0))
    reopened = workspace._manufacturing_requirements(order)

    assert _sizes(preview) == _sizes(reopened) == ("60.000", "40.000")


def test_recorded_thickness_rejects_an_old_size_that_only_differs_from_finished():
    piece = _piece(
        edge_long_right_thickness_mm=2,
        edge_long_left_thickness_mm=2,
        edge_width_top_thickness_mm=2,
        edge_width_bottom_thickness_mm=2,
        edge_long_thickness_mm=2,
        edge_width_thickness_mm=2,
    )
    order = SimpleNamespace(name="DCO-RECORDED", pieces=[piece])
    enabled = workspace._manufacturing_requirements(order, _plan(1))
    disabled = workspace._manufacturing_requirements(order, _plan(0))

    assert _sizes(enabled) == ("59.600", "39.600")
    assert _sizes(disabled) == ("60.000", "40.000")
    assert piece.cut_width_cm == 59.8


def test_preview_does_not_sync_cut_sizes_before_commit():
    source = Path(workspace.__file__).resolve().parents[2].joinpath(
        "services/cutting_plan_preview_service.py"
    ).read_text(encoding="utf-8")
    builder = source.split("def _build_session", 1)[1].split("\ndef ", 1)[0]
    commit = source.split("def commit_cutting_plan_preview", 1)[1]
    assert "sync_order_cut_dimensions" not in builder
    assert "sync_order_cut_dimensions" in commit
