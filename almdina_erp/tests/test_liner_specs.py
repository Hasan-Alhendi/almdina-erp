"""Canonical multi-liner payload: JSON list plus legacy scalar dual-write."""

from almdina_erp.almdina_erp.domain.orders.liner_specs import (
    LEGACY_LINER_ID,
    DoorLinerError,
    DoorLinerSet,
    DoorLinerSpec,
    allocate_liner_id,
    door_liner_fields,
    door_liners_from_source,
    serialize_door_liners,
)


def test_legacy_scalar_row_becomes_liner_1():
    payload = door_liners_from_source(
        {
            "extra_liner": 1,
            "liner_reference_side": "edge_width_top",
            "liner_offset_cm": 2,
            "liner_width_cm": 1.5,
            "liner_start_cm": 0,
            "liner_length_cm": 40,
        }
    )
    assert payload.enabled is True
    assert payload.width_cm == 1.5
    assert len(payload.liners) == 1
    assert payload.liners[0].liner_id == LEGACY_LINER_ID
    assert payload.liners[0].side == "edge_width_top"
    assert payload.liners[0].offset_cm == 2


def test_json_is_canonical_and_dual_writes_first_liner():
    stored = DoorLinerSet(
        enabled=True,
        width_cm=1.8,
        liners=(
            DoorLinerSpec(LEGACY_LINER_ID, "edge_width_top", 2, 0, 40),
            DoorLinerSpec("liner_2", "edge_long_left", 3, 5, 20),
        ),
    )
    fields = door_liner_fields(stored)
    assert fields["extra_liner"] == 1
    assert fields["liner_reference_side"] == "edge_width_top"
    assert fields["liner_offset_cm"] == 2
    assert fields["liner_width_cm"] == 1.8
    assert fields["liner_start_cm"] == 0
    assert fields["liner_length_cm"] == 40
    roundtrip = door_liners_from_source(fields)
    assert [spec.liner_id for spec in roundtrip.liners] == [LEGACY_LINER_ID, "liner_2"]
    assert roundtrip.width_cm == 1.8
    assert roundtrip.liners[1].offset_cm == 3
    assert roundtrip.liners[1].length_cm == 20


def test_allocate_liner_id_skips_existing_numbers():
    assert allocate_liner_id([]) == "liner_1"
    assert allocate_liner_id(["liner_1", "liner_3"]) == "liner_4"


def test_invalid_json_is_rejected():
    try:
        door_liners_from_source({"extra_liner": 1, "liner_specs_json": "{"})
    except DoorLinerError as error:
        assert error.code == "liner_specs_invalid"
    else:
        raise AssertionError("expected DoorLinerError")
