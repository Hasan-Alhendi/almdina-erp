from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
)
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    physical_execution_projection,
)
from almdina_erp.almdina_erp.domain.orders.costing import (
    SpecialPricingPieceInput,
    SpecialPricingSettings,
    calculate_order_costs,
    calculate_special_pricing,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    pending_custom_edge_price_labels,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


def _piece(
    identity: str,
    *,
    copy_no: int,
    kind: str = "FULL_BOARD",
    source: str = "UNASSIGNED",
    execution: str = "UNASSIGNED",
) -> dict[str, object]:
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


def test_cutting_fee_is_charged_per_full_board_only() -> None:
    all_offcut = calculate_order_costs(
        required_boards=0,
        board_rate_usd=50,
        cutting_cost_per_board_usd=10,
        edge_cost_usd=0,
    )
    mixed = calculate_order_costs(
        required_boards=3,
        board_rate_usd=50,
        cutting_cost_per_board_usd=10,
        edge_cost_usd=0,
    )

    assert all_offcut.mdf_cost_usd == 0
    assert all_offcut.cutting_cost_usd == 0
    assert mixed.cutting_cost_usd == 30


def test_customer_executed_special_copy_with_zero_factory_qty_is_not_factory_pricing_work() -> None:
    summary = calculate_special_pricing(
        [
            SpecialPricingPieceInput(
                piece_type="Special",
                qty=0,
                area_m2=1.5,
                edge_cost_usd=12,
                price_status="Estimated",
                custom_unit_price_usd=0,
            )
        ],
        settings=SpecialPricingSettings(
            design_fee_usd=5,
            cnc_fee_usd=7,
            manual_edge_fee_usd=3,
            margin_percent=20,
        ),
        total_area_m2=0,
        board_and_cutting_cost_usd=0,
        total_cost_usd=25,
        extra_addons_total_usd=0,
    )

    result = summary.pieces[0]
    assert result.applicable is False
    assert result.estimated_unit_price_usd == 0
    assert result.final_unit_price_usd == 0
    assert summary.customer_quote_total_usd == 25
    assert summary.customer_quote_status == "Automatic"


def test_custom_price_readiness_ignores_customer_executed_rows_but_keeps_factory_rows() -> None:
    pending = pending_custom_edge_price_labels([
        {
            "piece_type": "Special",
            "special_shape_price_status": "Estimated",
            "factory_execution_qty": 0,
        },
        {
            "piece_type": "Special",
            "special_shape_price_status": "Estimated",
            "factory_execution_qty": 1,
        },
        {
            "piece_type": "Clipped Corner",
            "clipped_corner_edge_price_status": "Unpriced",
            "factory_execution_qty": 0,
        },
    ])

    assert pending == ("درفة خاصة رقم 2",)


def test_legacy_custom_price_readiness_without_execution_projection_is_unchanged() -> None:
    pending = pending_custom_edge_price_labels([
        {
            "piece_type": "Special",
            "special_shape_price_status": "Estimated",
        }
    ])
    assert pending == ("درفة خاصة رقم 1",)


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
                "extra_liner_total_usd": 12,
            },
            {
                "piece_type": "Regular",
                "qty": 1,
                "factory_execution_qty": 0,
                "edge_meters": 0,
                "edge_rate_usd": 1,
                "edge_cost_usd": 0,
            },
            {
                "piece_type": "Special",
                "qty": 1,
                "factory_execution_qty": 0,
                "special_shape_price_status": "Estimated",
                "special_shape_custom_unit_price_usd": 40,
            },
            {
                "piece_type": "Clipped Corner",
                "qty": 1,
                "factory_execution_qty": 0,
                "clipped_corner_edge_price_status": "Unpriced",
                "clipped_corner_edge_price_usd": 18,
            },
        ],
    )

    offcut_lines = [line for line in document["lines"] if line["type"] == "offcut"]
    liner_lines = [line for line in document["lines"] if line["type"] == "extra_addon"]
    edge_lines = [line for line in document["lines"] if line["type"] == "edge"]
    special_lines = [line for line in document["lines"] if line["type"] == "special"]
    corner_lines = [line for line in document["lines"] if line["type"] == "cut_corner"]
    assert offcut_lines == [{
        "type": "offcut", "description": "سعر الفضلة", "quantity": 1,
        "unit": "مجموعة", "rate_usd": 25.0, "amount_usd": 25.0,
        "note": "سعر إجمالي للمجموعة",
    }]
    assert liner_lines[0]["quantity"] == 4
    assert liner_lines[0]["amount_usd"] == 12.0
    assert edge_lines == []
    assert special_lines == []
    assert corner_lines == []


def test_active_stage_start_and_handoff_fail_closed_after_reclassification_removes_factory_work() -> None:
    facts = ProductionActionFacts(
        order_status="In Production",
        production_path="Standard",
        current_stage_name="STAGE-1",
        has_cutting_plan=True,
        plan_needs_recalculation=False,
        stage_name="STAGE-1",
        stage_type="Cutting",
        stage_status="Pending",
        assigned_to="worker@example.com",
        actor="worker@example.com",
        has_factory_work=False,
    )
    capabilities = {
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
    }

    start = decide_production_action(
        Capability.START_ASSIGNED_STAGE,
        capabilities=capabilities,
        facts=facts,
    )
    handoff = decide_production_action(
        Capability.HANDOFF_ASSIGNED_STAGE,
        capabilities=capabilities,
        facts=facts,
    )

    assert start.allowed is False
    assert start.code == "customer_only_offcut"
    assert handoff.allowed is False
    assert handoff.code == "customer_only_offcut"


def test_cost_plan_uses_zero_board_uploaded_draft_when_resolver_selects_it(monkeypatch) -> None:
    from almdina_erp.almdina_erp.infrastructure.frappe import (
        cutting_plan_costing_workspace as workspace,
    )

    uploaded = SimpleNamespace(
        name="PLAN-UPLOADED",
        status="Draft",
        source_type="Uploaded DXF",
        required_boards=0,
        snapshot_json=json.dumps({
            "sheets": [
                {
                    "pieces": [
                        _piece(
                            "door:1",
                            copy_no=1,
                            kind="OFFCUT",
                            source="FACTORY",
                            execution="FACTORY",
                        )
                    ]
                }
            ]
        }),
    )
    monkeypatch.setattr(
        workspace,
        "resolve_canonical_cost_plan",
        lambda _order: uploaded,
    )

    assert workspace.current_cost_plan(SimpleNamespace(name="DCO-1", approved_plan="")) is uploaded


def test_cost_plan_keeps_official_approved_authority_over_newer_drafts(monkeypatch) -> None:
    from almdina_erp.almdina_erp.infrastructure.frappe import (
        cutting_plan_costing_workspace as workspace,
    )

    approved = SimpleNamespace(
        name="PLAN-APPROVED",
        status="Approved",
        required_boards=2,
        snapshot_json=json.dumps({"sheets": [{"pieces": [_piece("door:1", copy_no=1)]}]}),
    )
    monkeypatch.setattr(
        workspace,
        "resolve_canonical_cost_plan",
        lambda _order: approved,
    )

    order = SimpleNamespace(name="DCO-1", approved_plan=approved.name)
    assert workspace.current_cost_plan(order) is approved


def test_invoice_service_scales_edge_and_extra_totals_to_factory_physical_quantity() -> None:
    from almdina_erp.almdina_erp.services.cost_document_service import (
        _commercial_piece_snapshots,
    )

    row = SimpleNamespace(
        name="ROW-1",
        piece_no=1,
        piece_type="Extra",
        qty=5,
        edge_type="2cm",
        edge_meters=10,
        edge_rate_usd=2,
        edge_cost_usd=20,
        notes="",
        extra_liner=1,
        extra_liner_unit_price_usd=3,
        extra_liner_total_usd=15,
        extra_addons_total_usd=15,
    )

    result = _commercial_piece_snapshots([row], {1: 4}, {1: 5})[0]

    assert result["factory_execution_qty"] == 4
    assert result["edge_meters"] == 8
    assert result["edge_cost_usd"] == 16
    assert result["extra_liner_total_usd"] == 12
    assert result["extra_addons_total_usd"] == 12


def test_cost_price_has_one_canonical_save_boundary() -> None:
    source = (
        __import__(
            "pathlib"
        ).Path(__file__).resolve().parents[1]
        / "almdina_erp/services/offcut_service.py"
    ).read_text(encoding="utf-8")
    assert "def set_offcut_group_price" not in source
