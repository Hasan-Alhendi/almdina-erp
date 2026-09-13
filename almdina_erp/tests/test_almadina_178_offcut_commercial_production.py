from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
)
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    physical_execution_projection,
)


def _piece(identity: str, *, copy_no: int, kind: str = "FULL_BOARD", source="UNASSIGNED", execution="UNASSIGNED"):
    return {
        "piece_instance_id": identity,
        "source_piece_no": 1,
        "copy_no": copy_no,
        "resource_kind": kind,
        "offcut_source_party": source,
        "offcut_execution_party": execution,
    }


def test_physical_execution_projection_keeps_customer_qty_and_counts_only_factory_copies() -> None:
    projection = physical_execution_projection([
        _piece("door:1", copy_no=1),
        _piece("door:2", copy_no=2),
        _piece("door:3", copy_no=3, kind="OFFCUT", source="CUSTOMER", execution="FACTORY"),
        _piece("door:4", copy_no=4, kind="OFFCUT", source="CUSTOMER", execution="CUSTOMER"),
        _piece("door:5", copy_no=5, kind="OFFCUT", source="FACTORY", execution="FACTORY"),
    ])

    assert projection.piece_instance_ids == ("door:1", "door:2", "door:3", "door:4", "door:5")
    assert projection.factory_executable_quantity == 4
    assert projection.factory_processing_qty_by_source_piece_no == {1: 4}
    assert projection.factory_source_offcut_piece_ids == ("door:5",)


def test_projection_excludes_customer_executed_copy_without_mutating_requirement_quantity() -> None:
    projection = physical_execution_projection([
        _piece("door:1", copy_no=1),
        _piece("door:2", copy_no=2),
        _piece("door:3", copy_no=3, kind="OFFCUT", source="CUSTOMER", execution="CUSTOMER"),
        _piece("door:4", copy_no=4),
        _piece("door:5", copy_no=5, kind="OFFCUT", source="FACTORY", execution="FACTORY"),
    ])

    assert projection.factory_executable_quantity == 4
    assert projection.customer_execution_piece_ids == ("door:3",)
    assert projection.factory_processing_qty_by_source_piece_no == {1: 4}
    assert projection.physical_qty_by_source_piece_no == {1: 5}


def test_invalid_factory_source_customer_execution_fails_closed() -> None:
    with pytest.raises(OffcutPolicyError, match="factory_source_customer_execution_forbidden"):
        physical_execution_projection([
            _piece("door:1", copy_no=1, kind="OFFCUT", source="FACTORY", execution="CUSTOMER"),
        ])


def test_invoice_uses_one_aggregate_offcut_line_and_excludes_customer_execution_services() -> None:
    document = build_customer_invoice_document(
        {
            "offcut_price_usd": 25,
            "offcut_factory_factory": True,
            "required_boards": 0,
        },
        [
            {
                "piece_type": "Extra",
                "qty": 5,
                "factory_execution_qty": 4,
                "extra_liner": 1,
                "extra_liner_unit_price_usd": 3,
                "extra_liner_total_usd": 15,
            },
            {
                "piece_type": "Regular",
                "qty": 1,
                "factory_execution_qty": 0,
                "edge_meters": 8,
                "edge_rate_usd": 1,
                "edge_cost_usd": 8,
            },
        ],
    )

    offcut_lines = [line for line in document["lines"] if line["type"] == "offcut"]
    liner_lines = [line for line in document["lines"] if line["type"] == "extra_addon"]
    edge_lines = [line for line in document["lines"] if line["type"] == "edge"]
    assert offcut_lines == [{
        "type": "offcut", "description": "سعر الفضلة", "quantity": 1,
        "unit": "مجموعة", "rate_usd": 25.0, "amount_usd": 25.0,
        "note": "سعر إجمالي للمجموعة",
    }]
    assert liner_lines[0]["quantity"] == 4
    assert liner_lines[0]["amount_usd"] == 12.0
    assert edge_lines == []


def test_cost_price_has_one_canonical_save_boundary() -> None:
    source = (
        __import__(
            "pathlib"
        ).Path(__file__).resolve().parents[1]
        / "almdina_erp/services/offcut_service.py"
    ).read_text(encoding="utf-8")
    assert "def set_offcut_group_price" not in source
