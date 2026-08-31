from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import frappe
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
from almdina_erp.almdina_erp.services import dxf_export_service
from almdina_erp.almdina_erp.services.dxf_import_service import (
    DxfImportError,
    _expected_order_pieces,
)
from almdina_erp.almdina_erp.services.export_validation_service import (
    _expected_snapshot_pieces,
)
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
    OrderPieceCutSpec,
)
from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
    _proxy_order,
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
        optimization_mode="",
        machine_type="",
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


def test_full_door_double_expands_manufacturing_copies_without_changing_stored_qty():
    row = _piece(qty=3, extra_full_door_double=1)
    data = FrappeCutDimensionPlanAdapter.piece_row_as_dict(row)

    assert row.qty == 3
    assert data["qty"] == 6
    contract = _manufacturing_requirements(_order(row))
    assert [piece["label"] for piece in contract["pieces"]] == [
        "1.1",
        "1.2",
        "1.3",
        "1.4",
        "1.5",
        "1.6",
    ]


def test_plan_fingerprint_changes_when_persisted_cut_dimension_changes():
    order = _order(_piece(cut_width_cm=59.9))
    first = plan_input_fingerprint(order, _plan())
    order.pieces[0].cut_width_cm = 59.8
    second = plan_input_fingerprint(order, _plan())

    assert first != second


def test_dxf_import_matches_persisted_cut_dimensions_not_finished_dimensions():
    order = _order(
        _piece(width_cm=60, length_cm=200, cut_width_cm=59.9, cut_length_cm=199.8)
    )
    expected = _expected_order_pieces(order)

    assert expected == [
        {
            "label": "1.1",
            "width_cm": 59.9,
            "length_cm": 199.8,
            "allow_rotation": 1,
            "piece_type": "Regular",
            "source_piece_no": 1,
            "copy_no": 1,
        }
    ]


def test_dxf_import_fails_closed_when_persisted_cut_dimensions_are_missing():
    order = _order(_piece(cut_width_cm=0, width_cm=60))
    with pytest.raises(DxfImportError):
        _expected_order_pieces(order)


def test_strict_dxf_import_proxy_preserves_normalized_cut_dimensions():
    spec = OrderPieceCutSpec(
        row_index=1,
        finished_width_cm=Decimal("60.000"),
        finished_length_cm=Decimal("200.000"),
        cut_width_cm=Decimal("59.900"),
        cut_length_cm=Decimal("199.800"),
        width_deduction_mm=Decimal("1.000"),
        length_deduction_mm=Decimal("2.000"),
        allow_rotation=1,
        piece_type="Regular",
        qty=1,
        side_profiles=(),
    )
    proxy = _proxy_order(_order(_piece()), [spec], _plan())

    assert proxy.pieces[0].width_cm == 59.9
    assert proxy.pieces[0].length_cm == 199.8
    assert proxy.pieces[0].cut_width_cm == 59.9
    assert proxy.pieces[0].cut_length_cm == 199.8
    assert _expected_order_pieces(proxy)[0]["width_cm"] == 59.9
    assert _expected_order_pieces(proxy)[0]["length_cm"] == 199.8


def test_saved_plan_validation_reads_captured_requirement_not_live_order_dimensions():
    order = _order(_piece(cut_width_cm=59.9, cut_length_cm=199.8))
    captured = _manufacturing_requirements(order)
    order.pieces[0].width_cm = 61
    order.pieces[0].length_cm = 201
    order.pieces[0].cut_width_cm = 58
    order.pieces[0].cut_length_cm = 198

    expected = _expected_snapshot_pieces(
        {"manufacturing_requirements": captured}
    )
    assert expected["1.1"]["width_cm"] == 59.9
    assert expected["1.1"]["length_cm"] == 199.8


def test_legacy_saved_plan_without_captured_requirements_fails_closed():
    with pytest.raises(ManufacturingRequirementsError):
        _expected_snapshot_pieces({})


def test_saved_export_rejects_fingerprint_drift_before_geometry(monkeypatch):
    order = _order(_piece())
    plan = _plan()
    plan.plan_needs_recalculation = 0
    plan.input_fingerprint = "captured-revision"
    monkeypatch.setattr(
        dxf_export_service,
        "plan_input_fingerprint",
        lambda _order, _plan: "current-revision",
    )

    with pytest.raises(frappe.ValidationError):
        dxf_export_service._assert_saved_plan_fresh(order, plan)
