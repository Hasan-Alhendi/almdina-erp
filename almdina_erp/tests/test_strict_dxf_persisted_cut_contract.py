from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
    OrderPieceCutSpec,
)
from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
    _apply_strict_dimension_contract,
    _bind_persisted_cut_dimensions,
)


def _spec(
    *,
    cut_width_cm: str = "59.800",
    cut_length_cm: str = "199.700",
    piece_type: str = "Regular",
    allow_rotation: int = 1,
):
    return OrderPieceCutSpec(
        row_index=1,
        finished_width_cm=Decimal("60.000"),
        finished_length_cm=Decimal("200.000"),
        cut_width_cm=Decimal(cut_width_cm),
        cut_length_cm=Decimal(cut_length_cm),
        width_deduction_mm=Decimal("2.000"),
        length_deduction_mm=Decimal("3.000"),
        allow_rotation=allow_rotation,
        piece_type=piece_type,
        qty=1,
        side_profiles=(),
    )


def _special_snapshot(*, width: float, height: float) -> dict:
    return {
        "sheets": [
            {
                "pieces": [
                    {
                        "label": "1.1",
                        "source_piece_no": 1,
                        "copy_no": 1,
                        "piece_type": "Special",
                        "w": width,
                        "h": height,
                        "rotated": False,
                    }
                ]
            }
        ]
    }


def test_strict_import_uses_persisted_cut_dimensions_over_recomputed_spec():
    order = SimpleNamespace(
        pieces=[
            SimpleNamespace(
                cut_width_cm=59.9,
                cut_length_cm=199.8,
            )
        ]
    )

    bound = _bind_persisted_cut_dimensions(order, [_spec()])

    assert bound[0].cut_width_cm == Decimal("59.900")
    assert bound[0].cut_length_cm == Decimal("199.800")
    assert bound[0].width_deduction_mm == Decimal("1.000")
    assert bound[0].length_deduction_mm == Decimal("2.000")


def test_strict_import_fails_closed_when_persisted_cut_dimension_is_missing():
    order = SimpleNamespace(
        pieces=[
            SimpleNamespace(
                cut_width_cm=0,
                cut_length_cm=199.8,
            )
        ]
    )

    with pytest.raises(DxfImportError):
        _bind_persisted_cut_dimensions(order, [_spec()])


def test_strict_contract_preserves_topology_special_with_exact_cut_envelope():
    snapshot = _special_snapshot(width=120, height=200)

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(cut_width_cm="120", cut_length_cm="200", piece_type="Special")],
    )

    assert errors == []
    piece = snapshot["sheets"][0]["pieces"][0]
    assert piece["piece_type"] == "Special"
    assert piece["cut_width_cm"] == 120
    assert piece["cut_length_cm"] == 200
    assert piece["rotated"] is False


def test_strict_contract_rejects_topology_special_with_wrong_cut_envelope():
    snapshot = _special_snapshot(width=60, height=60)

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(cut_width_cm="120", cut_length_cm="200", piece_type="Special")],
    )

    assert errors
    assert "الإطار الخارجي للتصنيع" in errors[0]


def test_strict_contract_allows_special_rotation_only_when_order_allows_it():
    allowed_snapshot = _special_snapshot(width=200, height=120)
    allowed_errors = _apply_strict_dimension_contract(
        allowed_snapshot,
        [
            _spec(
                cut_width_cm="120",
                cut_length_cm="200",
                piece_type="Special",
                allow_rotation=1,
            )
        ],
    )

    assert allowed_errors == []
    assert allowed_snapshot["sheets"][0]["pieces"][0]["rotated"] is True

    forbidden_snapshot = _special_snapshot(width=200, height=120)
    forbidden_errors = _apply_strict_dimension_contract(
        forbidden_snapshot,
        [
            _spec(
                cut_width_cm="120",
                cut_length_cm="200",
                piece_type="Special",
                allow_rotation=0,
            )
        ],
    )

    assert forbidden_errors
    assert "التدوير غير مسموح" in forbidden_errors[0]


def test_strict_contract_keeps_regular_pieces_dimension_bound():
    snapshot = {
        "sheets": [
            {
                "pieces": [
                    {
                        "label": "1.1",
                        "source_piece_no": 1,
                        "copy_no": 1,
                        "piece_type": "Regular",
                        "w": 60,
                        "h": 60,
                    }
                ]
            }
        ]
    }

    errors = _apply_strict_dimension_contract(snapshot, [_spec()])

    assert errors
    assert "لا تطابق" in "\n".join(errors)


def test_strict_contract_rejects_unproven_special_identity():
    snapshot = {
        "sheets": [
            {
                "pieces": [
                    {
                        "label": "9.1",
                        "source_piece_no": 9,
                        "copy_no": 1,
                        "piece_type": "Special",
                        "w": 59.8,
                        "h": 199.7,
                    }
                ]
            }
        ]
    }

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(piece_type="Special")],
    )

    assert errors
    assert "تعذر ربط الدرفة الخاصة" in errors[0]