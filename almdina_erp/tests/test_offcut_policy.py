from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutBusinessState,
    OffcutPolicyError,
    Party,
    ResourceKind,
    business_state_options,
    decision_from_business_state,
    decision_from_values,
    offcut_summary,
    preserve_offcut_classification,
    source_summary,
    canonicalize_snapshot_sources,
    validate_source_resource_homogeneity,
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


def test_unassigned_is_one_explicit_neutral_state() -> None:
    partial = decision_from_values("OFFCUT", "CUSTOMER", "UNASSIGNED")
    assert partial.source_party is Party.UNASSIGNED
    assert partial.execution_party is Party.UNASSIGNED
    assert decision_from_business_state("OFFCUT", "UNASSIGNED") == partial


def test_full_board_cannot_receive_offcut_business_state() -> None:
    legacy = decision_from_values("FULL_BOARD", "CUSTOMER", "FACTORY")
    assert legacy.source_party is Party.UNASSIGNED
    assert legacy.execution_party is Party.UNASSIGNED
    with pytest.raises(OffcutPolicyError, match="full_board"):
        decision_from_business_state("FULL_BOARD", "CUSTOMER_FACTORY")


def test_business_state_options_expose_only_supported_cases() -> None:
    assert business_state_options() == [
        {"value": "UNASSIGNED", "label": "غير محدد"},
        {"value": "CUSTOMER_FACTORY", "label": "فضلة من الزبون — تنفيذ في المعمل"},
        {"value": "CUSTOMER_CUSTOMER", "label": "فضلة من الزبون — تنفيذ عند الزبون"},
        {"value": "FACTORY_FACTORY", "label": "فضلة من المعمل — تنفيذ في المعمل"},
    ]
    assert all(option["value"] != "FACTORY_CUSTOMER" for option in business_state_options())


def test_physical_source_cannot_mix_full_board_and_offcut() -> None:
    with pytest.raises(OffcutPolicyError, match="mixed_full_board_offcut_source"):
        validate_source_resource_homogeneity(
            [
                {
                    "pieces": [
                        {"piece_instance_id": "a:1", "resource_kind": "FULL_BOARD"},
                        {"piece_instance_id": "b:1", "resource_kind": "OFFCUT"},
                    ]
                }
            ]
        )


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
    assert snapshot["sheets"][0]["offcut_execution_party"] == "UNASSIGNED"


def test_mixed_piece_decisions_project_neutral_source_instead_of_first_piece() -> None:
    snapshot = {
        "sheets": [{
            "sheet_no": 2,
            "pieces": [
                {
                    "piece_instance_id": "copy:3",
                    "resource_kind": "OFFCUT",
                    "offcut_source_party": "CUSTOMER",
                    "offcut_execution_party": "FACTORY",
                },
                {
                    "piece_instance_id": "copy:5",
                    "resource_kind": "OFFCUT",
                    "offcut_source_party": "CUSTOMER",
                    "offcut_execution_party": "CUSTOMER",
                },
            ],
        }]
    }

    canonicalize_snapshot_sources(snapshot)

    assert snapshot["sheets"][0]["offcut_source_party"] == "UNASSIGNED"
    assert snapshot["sheets"][0]["offcut_execution_party"] == "UNASSIGNED"


def test_offcut_summary_distinguishes_all_business_states() -> None:
    pieces = []
    states = [
        OffcutBusinessState.CUSTOMER_FACTORY,
        OffcutBusinessState.CUSTOMER_FACTORY,
        OffcutBusinessState.CUSTOMER_CUSTOMER,
        OffcutBusinessState.FACTORY_FACTORY,
        OffcutBusinessState.FACTORY_FACTORY,
        OffcutBusinessState.UNASSIGNED,
    ]
    for index, state in enumerate(states, start=1):
        decision = decision_from_business_state("OFFCUT", state)
        pieces.append({
            "piece_instance_id": f"piece:{index}",
            "resource_kind": "OFFCUT",
            "offcut_source_party": decision.source_party.value,
            "offcut_execution_party": decision.execution_party.value,
        })

    assert offcut_summary(pieces) == [
        {"business_state": "CUSTOMER_FACTORY", "label": "من الزبون / في المعمل", "count": 2},
        {"business_state": "CUSTOMER_CUSTOMER", "label": "من الزبون / عند الزبون", "count": 1},
        {"business_state": "FACTORY_FACTORY", "label": "من المعمل / في المعمل", "count": 2},
        {"business_state": "UNASSIGNED", "label": "غير محدد", "count": 1},
    ]


def test_reimport_preserves_only_same_offcut_physical_identity() -> None:
    previous = [
        {
            "piece_instance_id": "row:copy:3",
            "resource_kind": "OFFCUT",
            "offcut_source_party": "CUSTOMER",
            "offcut_execution_party": "FACTORY",
        },
        {
            "piece_instance_id": "removed:copy:5",
            "resource_kind": "OFFCUT",
            "offcut_source_party": "FACTORY",
            "offcut_execution_party": "FACTORY",
        },
    ]
    snapshot = {
        "sheets": [{
            "sheet_no": 3,
            "resource_kind": "OFFCUT",
            "pieces": [
                {"piece_instance_id": "row:copy:3", "resource_kind": "OFFCUT"},
                {"piece_instance_id": "new:copy:5", "resource_kind": "OFFCUT"},
            ],
        }]
    }

    preserve_offcut_classification(snapshot, previous)

    matched, new = snapshot["sheets"][0]["pieces"]
    assert (matched["offcut_source_party"], matched["offcut_execution_party"]) == (
        "CUSTOMER",
        "FACTORY",
    )
    assert (new["offcut_source_party"], new["offcut_execution_party"]) == (
        "UNASSIGNED",
        "UNASSIGNED",
    )
