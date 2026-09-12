from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutBusinessState,
    OffcutPolicyError,
    Party,
    ResourceKind,
    business_state_options,
    canonicalize_snapshot_allocation,
    canonicalize_snapshot_sources,
    decision_from_business_state,
    decision_from_values,
    offcut_summary,
    preserve_offcut_classification,
    source_summary,
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
    assert all(
        option["value"] != "FACTORY_CUSTOMER"
        for option in business_state_options()
    )


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


def test_allocation_numbers_only_real_full_boards_without_rewriting_source_identity() -> None:
    snapshot = {
        "sheets": [
            {
                "sheet_no": 10,
                "resource_kind": "FULL_BOARD",
                "pieces": [{"piece_instance_id": "row-a:1", "resource_kind": "FULL_BOARD", "area_m2": 1}],
            },
            {
                "sheet_no": 20,
                "resource_kind": "OFFCUT",
                "pieces": [{"piece_instance_id": "row-b:1", "resource_kind": "OFFCUT", "area_m2": 0.5}],
            },
            {
                "sheet_no": 30,
                "resource_kind": "FULL_BOARD",
                "pieces": [{"piece_instance_id": "row-c:1", "resource_kind": "FULL_BOARD", "area_m2": 1}],
            },
        ],
        "total_board_area_m2": 6,
        "waste_area_m2": 4,
    }

    canonicalize_snapshot_allocation(snapshot)

    assert [sheet["sheet_no"] for sheet in snapshot["sheets"]] == [10, 20, 30]
    assert [sheet["full_board_no"] for sheet in snapshot["sheets"]] == [1, None, 2]
    assert snapshot["required_full_boards"] == 2


def test_allocation_excludes_offcut_area_from_new_board_waste() -> None:
    snapshot = {
        "used_area_m2": 4.0,
        "total_board_area_m2": 5.0,
        "waste_area_m2": 1.0,
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "FULL_BOARD",
                "pieces": [{"piece_instance_id": "full:1", "resource_kind": "FULL_BOARD", "area_m2": 3.0}],
            },
            {
                "sheet_no": 2,
                "resource_kind": "OFFCUT",
                "pieces": [{"piece_instance_id": "offcut:1", "resource_kind": "OFFCUT", "area_m2": 1.0}],
            },
        ],
    }

    canonicalize_snapshot_allocation(snapshot)

    assert snapshot["used_area_m2"] == 4.0
    assert snapshot["full_board_used_area_m2"] == 3.0
    assert snapshot["total_board_area_m2"] == 5.0
    assert snapshot["waste_area_m2"] == 2.0
    assert snapshot["required_full_boards"] == 1


@pytest.mark.parametrize(
    ("state", "source", "execution"),
    [
        ("UNASSIGNED", "UNASSIGNED", "UNASSIGNED"),
        ("CUSTOMER_FACTORY", "CUSTOMER", "FACTORY"),
        ("CUSTOMER_CUSTOMER", "CUSTOMER", "CUSTOMER"),
        ("FACTORY_FACTORY", "FACTORY", "FACTORY"),
    ],
)
def test_all_supported_offcut_business_states_allocate_zero_new_boards(
    state: str,
    source: str,
    execution: str,
) -> None:
    decision = decision_from_business_state("OFFCUT", state)
    assert decision.source_party.value == source
    assert decision.execution_party.value == execution

    snapshot = {
        "total_board_area_m2": 0,
        "waste_area_m2": 0,
        "sheets": [{
            "sheet_no": 7,
            "resource_kind": "OFFCUT",
            "offcut_source_party": source,
            "offcut_execution_party": execution,
            "pieces": [{
                "piece_instance_id": f"copy:{state}",
                "resource_kind": "OFFCUT",
                "offcut_source_party": source,
                "offcut_execution_party": execution,
                "area_m2": 0.8,
            }],
        }],
    }

    canonicalize_snapshot_allocation(snapshot)

    assert snapshot["required_full_boards"] == 0
    assert snapshot["sheets"][0]["full_board_no"] is None


def test_all_offcut_plan_keeps_every_piece_and_allocates_zero_full_boards() -> None:
    identities = [f"row:copy:{copy_no}" for copy_no in range(1, 6)]
    snapshot = {
        "used_area_m2": 5.0,
        "total_board_area_m2": 5.0,
        "waste_area_m2": 0.0,
        "sheets": [{
            "sheet_no": 4,
            "resource_kind": "OFFCUT",
            "pieces": [
                {"piece_instance_id": identity, "resource_kind": "OFFCUT", "area_m2": 1.0}
                for identity in identities
            ],
        }],
    }

    canonicalize_snapshot_allocation(snapshot)

    assert [piece["piece_instance_id"] for piece in snapshot["sheets"][0]["pieces"]] == identities
    assert snapshot["required_full_boards"] == 0
    assert snapshot["full_board_used_area_m2"] == 0.0
    assert snapshot["total_board_area_m2"] == 0.0
    assert snapshot["waste_area_m2"] == 0.0
    assert snapshot["sheets"][0]["sheet_no"] == 4
    assert snapshot["sheets"][0]["full_board_no"] is None


def test_legacy_snapshot_without_resource_kind_keeps_normal_full_board_behavior() -> None:
    snapshot = {
        "used_area_m2": 3.0,
        "total_board_area_m2": 5.0,
        "waste_area_m2": 2.0,
        "sheets": [{
            "sheet_no": 1,
            "pieces": [{"piece_instance_id": "legacy:1", "area_m2": 3.0}],
        }],
    }

    canonicalize_snapshot_allocation(snapshot)

    assert snapshot["required_full_boards"] == 1
    assert snapshot["sheets"][0]["full_board_no"] == 1
    assert snapshot["full_board_used_area_m2"] == 3.0
    assert snapshot["waste_area_m2"] == 2.0


def test_per_copy_identity_geometry_and_extra_metadata_survive_allocation_projection() -> None:
    full_board_copies = [
        {
            "piece_instance_id": f"door-row:copy:{copy_no}",
            "resource_kind": "FULL_BOARD",
            "area_m2": 1.0,
            "special_shape_geometry_json": f"geometry-{copy_no}",
            "extra_overlays": {"Liner": [copy_no]},
        }
        for copy_no in (1, 2, 4, 5)
    ]
    offcut_copy = {
        "piece_instance_id": "door-row:copy:3",
        "resource_kind": "OFFCUT",
        "area_m2": 1.0,
        "special_shape_geometry_json": "geometry-3",
        "extra_overlays": {"Liner": [3], "Rear Groove": [3], "Handle Recess": [3]},
    }
    snapshot = {
        "used_area_m2": 5.0,
        "total_board_area_m2": 8.0,
        "waste_area_m2": 3.0,
        "sheets": [
            {"sheet_no": 1, "resource_kind": "FULL_BOARD", "pieces": full_board_copies},
            {"sheet_no": 2, "resource_kind": "OFFCUT", "pieces": [offcut_copy]},
        ],
    }

    canonicalize_snapshot_allocation(snapshot)

    all_pieces = [piece for sheet in snapshot["sheets"] for piece in sheet["pieces"]]
    assert {piece["piece_instance_id"] for piece in all_pieces} == {
        f"door-row:copy:{copy_no}" for copy_no in range(1, 6)
    }
    preserved = next(piece for piece in all_pieces if piece["piece_instance_id"] == "door-row:copy:3")
    assert preserved["special_shape_geometry_json"] == "geometry-3"
    assert preserved["extra_overlays"] == {
        "Liner": [3],
        "Rear Groove": [3],
        "Handle Recess": [3],
    }
    assert snapshot["required_full_boards"] == 1
    assert snapshot["full_board_used_area_m2"] == 4.0


def test_snapshot_security_applies_canonical_offcut_allocation_before_persistence() -> None:
    snapshot = {
        "used_area_m2": 4.0,
        "total_board_area_m2": 5.0,
        "waste_area_m2": 1.0,
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "FULL_BOARD",
                "pieces": [{"piece_instance_id": "full:1", "resource_kind": "FULL_BOARD", "area_m2": 3.0}],
            },
            {
                "sheet_no": 2,
                "resource_kind": "OFFCUT",
                "pieces": [{"piece_instance_id": "offcut:1", "resource_kind": "OFFCUT", "area_m2": 1.0}],
            },
        ],
    }

    sanitized = sanitize_plan_snapshot(snapshot)

    assert sanitized["required_full_boards"] == 1
    assert sanitized["full_board_used_area_m2"] == 3.0
    assert sanitized["waste_area_m2"] == 2.0
    assert [sheet["full_board_no"] for sheet in sanitized["sheets"]] == [1, None]
