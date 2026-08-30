from __future__ import annotations

from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    ManufacturingRequirementsError,
    build_manufacturing_requirements,
    snapshot_manufacturing_requirement_index,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    _manufacturing_requirements,
    plan_input_fingerprint,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.cut_dimension_plan_adapter import (
    FrappeCutDimensionPlanAdapter,
)


def _piece(**overrides):
    values = {
        "width_cm": 60.0,
        "length_cm": 200.0,
        "cut_width_cm": 59.9,
        "cut_length_cm": 199.8,
        "qty": 1,
        "allow_rotation": 1,
        "edge_long_right": 0,
        "edge_long_left": 0,
        "edge_width_top": 0,
        "edge_width_bottom": 0,
        "edge_type": "",
        "edge_rate_usd": 0,
        "edge_cost_usd": 0,
        "piece_type": "Regular",
        "clipped_corner_position": "",
        "clipped_corner_width_cm": 0,
        "clipped_corner_length_cm": 0,
        "special_shape_geometry_json": "",
        "notes": "",
        "edge_long_right_type_override": "",
        "edge_long_left_type_override": "",
        "edge_width_top_type_override": "",
        "edge_width_bottom_type_override": "",
        "edge_long_type": "",
        "edge_width_type": "",
        "edge_long_thickness_mm": 0,
        "edge_width_thickness_mm": 0,
        "edge_long_rate_usd": 0,
        "edge_width_rate_usd": 0,
        "edge_long_cost_usd": 0,
        "edge_width_cost_usd": 0,
        "cut_size_label": "59.9 × 199.8",
        "area_m2": 1.2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _order(piece):
    return SimpleNamespace(
        name="DCO-TEST-143",
        revision=1,
        board_description="MDF TEST",
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        board_width_cm=122,
        board_length_cm=244,
        pieces=[piece],
    )


def _plan():
    return SimpleNamespace(
        optimization_mode="auto_pro",
        machine_type="Auto",
        optimization_time_limit_sec=10,
        kerf_mm=3.2,
        trim_margin_mm=5,
    )


def test_requirement_contract_is_versioned_deterministic_and_identity_safe():
    contract = build_manufacturing_requirements(
        [
            {
                "label": "1.1",
                "source_piece_no": 1,
                "copy_no": 1,
                "cut_width_cm": 59.9,
                "cut_length_cm": "199.8",
                "allow_rotation": True,
                "piece_type": "Regular",
            },
            {
                "label": "2.1",
                "source_piece_no": 2,
                "copy_no": 1,
                "cut_width_cm": 59.9,
                "cut_length_cm": 199.8,
                "allow_rotation": False,
                "piece_type": "Regular",
            },
        ]
    )

    assert contract["schema_version"] == 1
    assert contract["unit"] == "cm"
    assert contract["pieces"][0]["cut_width_cm"] == "59.900"
    assert contract["pieces"][0]["cut_length_cm"] == "199.800"
    index, present = snapshot_manufacturing_requirement_index(
        {"manufacturing_requirements": contract}, require=True
    )
    assert present is True
    assert set(index) == {"1.1", "2.1"}


def test_declared_malformed_requirement_fails_closed_in_snapshot_sanitizer():
    malformed = {
        "manufacturing_requirements": {
            "schema_version": 1,
            "unit": "cm",
            "pieces": [
                {
                    "label": "1.1",
                    "source_piece_no": 1,
                    "copy_no": 1,
                    "cut_width_cm": 0,
                    "cut_length_cm": 200,
                    "allow_rotation": True,
                    "piece_type": "Regular",
                }
            ],
        }
    }
    with pytest.raises(ManufacturingRequirementsError):
        sanitize_plan_snapshot(malformed)


def test_cut_adapter_uses_persisted_cut_dimensions_not_finished_dimensions():
    row = _piece(width_cm=60, length_cm=200, cut_width_cm=59.9, cut_length_cm=199.8)
    data = FrappeCutDimensionPlanAdapter.piece_row_as_dict(row)

    assert data["final_width_cm"] == 60
    assert data["final_length_cm"] == 200
    assert data["width_cm"] == 59.9
    assert data["length_cm"] == 199.8


def test_cut_adapter_fails_closed_instead_of_falling_back_to_finished_dimensions():
    row = _piece(cut_width_cm=0, width_cm=60)
    with pytest.raises(ManufacturingRequirementsError):
        FrappeCutDimensionPlanAdapter.piece_row_as_dict(row)


def test_plan_revision_captures_expanded_persisted_manufacturing_requirements():
    order = _order(_piece(qty=2))
    contract = _manufacturing_requirements(order)

    assert [piece["label"] for piece in contract["pieces"]] == ["1.1", "1.2"]
    assert all(piece["cut_width_cm"] == "59.900" for piece in contract["pieces"])
    assert all(piece["cut_length_cm"] == "199.800" for piece in contract["pieces"])


def test_plan_fingerprint_changes_when_persisted_cut_dimension_changes():
    order = _order(_piece(cut_width_cm=59.9))
    first = plan_input_fingerprint(order, _plan())
    order.pieces[0].cut_width_cm = 59.8
    second = plan_input_fingerprint(order, _plan())

    assert first != second
