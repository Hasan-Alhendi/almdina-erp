"""Canonical multi-liner payload: JSON list plus legacy scalar dual-write."""

import json

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


def _liner_set(face=None):
    return DoorLinerSet(
        enabled=True,
        width_cm=1.5,
        liners=(DoorLinerSpec(LEGACY_LINER_ID, "edge_width_top", 2, 0, 40),),
        face=face,
    )


def test_new_and_legacy_liners_have_no_default_face():
    legacy = door_liners_from_source(
        {
            "extra_liner": 1,
            "liner_reference_side": "edge_width_top",
            "liner_offset_cm": 2,
            "liner_width_cm": 1.5,
            "liner_start_cm": 0,
            "liner_length_cm": 40,
        }
    )
    assert legacy.face is None
    stored = json.loads(serialize_door_liners(legacy))
    assert "face" not in stored

    historical = door_liners_from_source(
        {
            "extra_liner": 1,
            "liner_width_cm": 1.5,
            "liner_specs_json": json.dumps(
                {
                    "width_cm": 1.5,
                    "liners": [
                        {
                            "id": "liner_1",
                            "side": "edge_width_top",
                            "offset_cm": 2,
                            "start_cm": 0,
                            "length_cm": 40,
                        }
                    ],
                }
            ),
        }
    )
    assert historical.face is None
    assert door_liners_from_source(
        {
            "extra_liner": 1,
            "liner_specs_json": json.dumps(
                {
                    "width_cm": 1.5,
                    "face": "side",
                    "liners": [
                        {
                            "id": "liner_1",
                            "side": "edge_width_top",
                            "offset_cm": 2,
                            "start_cm": 0,
                            "length_cm": 40,
                        }
                    ],
                }
            ),
        }
    ).face is None


def test_face_roundtrip_stays_on_the_addon_and_does_not_change_paths():
    faces = {}
    for face in ("front", "back", None):
        fields = door_liner_fields(_liner_set(face))
        payload = door_liners_from_source(fields)
        faces[face] = payload
        assert payload.face == face
        body = json.loads(fields["liner_specs_json"])
        if face is None:
            assert "face" not in body
        else:
            assert body["face"] == face
        assert "face" not in body["liners"][0]
        assert fields["liner_reference_side"] == "edge_width_top"
        assert fields["liner_offset_cm"] == 2
        assert fields["liner_width_cm"] == 1.5
        assert fields["liner_length_cm"] == 40

    def paths(payload):
        return [(spec.side, spec.offset_cm, spec.start_cm, spec.length_cm) for spec in payload.liners]

    assert paths(faces["front"]) == paths(faces["back"]) == paths(faces[None])
    assert faces["front"].width_cm == faces["back"].width_cm == 1.5


def test_cutting_plan_piece_keeps_face_through_expansion_and_metadata_refresh():
    from almdina_erp.almdina_erp.application.cutting.refresh_plan_metadata import (
        refresh_plan_metadata,
    )
    from almdina_erp.almdina_erp.domain.cutting.primitives import (
        expand_piece_groups,
        make_placed_piece,
    )

    row = {
        "width_cm": 40,
        "length_cm": 60,
        "qty": 2,
        "piece_type": "Regular",
        **door_liner_fields(_liner_set("back")),
    }
    expanded = expand_piece_groups([row])
    assert len(expanded) == 2
    placed = make_placed_piece(expanded[0], 0, 0, 40, 60, True)
    assert json.loads(placed["liner_specs_json"])["face"] == "back"
    assert placed["liner_reference_side"] == "edge_width_top"
    assert placed["liner_width_cm"] == 1.5
    assert placed["w"] == 40
    assert placed["h"] == 60
    assert placed["rotated"] is True

    snapshot = {
        "sheets": [
            {
                "pieces": [
                    {"id": placed["id"], "x": 0, "y": 0, "w": 40, "h": 60, "liner_specs_json": ""}
                ]
            }
        ]
    }
    refreshed = refresh_plan_metadata(
        snapshot,
        expanded_pieces=[placed],
        input_fingerprint="face",
        metadata_fingerprint="face",
    )
    assert json.loads(refreshed["sheets"][0]["pieces"][0]["liner_specs_json"])["face"] == "back"
    assert refreshed["sheets"][0]["pieces"][0]["x"] == 0
    assert refreshed["sheets"][0]["pieces"][0]["w"] == 40


def test_invalid_json_is_rejected():
    try:
        door_liners_from_source({"extra_liner": 1, "liner_specs_json": "{"})
    except DoorLinerError as error:
        assert error.code == "liner_specs_invalid"
    else:
        raise AssertionError("expected DoorLinerError")
