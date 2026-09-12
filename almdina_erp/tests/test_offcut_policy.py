from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    Party,
    ResourceKind,
    decision_from_values,
    source_summary,
    canonicalize_snapshot_sources,
)


def test_offcut_has_exactly_three_resolved_states() -> None:
    for source, execution in (
        ("CUSTOMER", "FACTORY"),
        ("CUSTOMER", "CUSTOMER"),
        ("FACTORY", "FACTORY"),
    ):
        decision = decision_from_values("OFFCUT", source, execution)
        assert decision.is_resolved


def test_factory_source_customer_execution_is_rejected() -> None:
    with pytest.raises(OffcutPolicyError, match="forbidden"):
        decision_from_values("OFFCUT", "FACTORY", "CUSTOMER")


def test_offcut_does_not_consume_full_board_and_customer_execution_skips_queue() -> None:
    customer_only = decision_from_values("OFFCUT", Party.CUSTOMER, Party.CUSTOMER)
    assert not customer_only.consumes_full_board
    assert not customer_only.enters_worker_queues


def test_piece_count_is_preserved_by_source_summary() -> None:
    summary = source_summary(
        [
            {"piece_instance_id": "a:1", "resource_kind": "FULL_BOARD"},
            {
                "piece_instance_id": "b:1",
                "resource_kind": ResourceKind.OFFCUT,
                "offcut_source_party": "CUSTOMER",
                "offcut_execution_party": "FACTORY",
            },
        ]
    )
    assert summary == {
        "piece_count": 2,
        "full_board_piece_count": 1,
        "offcut_piece_count": 1,
        "factory_execution_piece_count": 1,
    }


def test_snapshot_source_projection_backfills_legacy_offcut_sheet() -> None:
    snapshot = {
        "sheets": [
            {
                "sheet_no": 3,
                "pieces": [
                    {
                        "piece_instance_id": "b:1",
                        "resource_kind": "OFFCUT",
                        "offcut_source_party": "UNASSIGNED",
                        "offcut_execution_party": "UNASSIGNED",
                    }
                ],
            }
        ]
    }

    canonicalize_snapshot_sources(snapshot)

    assert snapshot["sheets"][0]["resource_kind"] == "OFFCUT"
    assert snapshot["sheets"][0]["offcut_source_party"] == "UNASSIGNED"
