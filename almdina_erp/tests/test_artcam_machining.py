"""ArtCAM tool, profile, vector association, and frozen toolpath rules."""

from __future__ import annotations

import copy

import pytest

from almdina_erp.almdina_erp.domain.cnc.artcam_machining import (
    BALL_NOSE,
    RATE_UNITS_MM_SEC,
    SELECTION_LAYER,
    SELECTION_SHEET_PERIMETER,
    SELECTION_VECTORS,
    TOOL_UNITS_MM,
    MachiningSetupError,
    append_snapshot,
    artcam_tool_storage,
    association_availability,
    calculate_toolpath_snapshot,
    normalize_artcam_tool,
    normalize_associations,
    normalize_profile,
    overlay_frozen_toolpaths,
    tool_copy_from_stored,
    vectors_from_paths,
)
from almdina_erp.almdina_erp.domain.cnc.perimeter import SHEET_PERIMETER_PATH_KEY


def _artcam(**overrides):
    raw = {
        "description": "T9_CUT",
        "tool_type": BALL_NOSE,
        "tool_number": 9,
        "tool_units": TOOL_UNITS_MM,
        "rate_units": RATE_UNITS_MM_SEC,
        "notes": "",
        "diameter_mm": 5.0,
        "stepdown_mm": 19.0,
        "final_tool_offset_mm": 2.5,
        "stepover_size_mm": 0.2,
        "stepover_percent": 4,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_sec": 170.0,
        "plunge_rate_mm_sec": 30.0,
    }
    raw.update(overrides)
    return raw


def _stored_tool():
    tool = normalize_artcam_tool(_artcam())
    stored = artcam_tool_storage(tool)
    stored["preset_name"] = "T9_CUT"
    stored["enabled"] = True
    return stored


def _profile(tool_name="T9_CUT", **overrides):
    raw = {
        "profile_id": "profile:liner",
        "name": "Liner profile",
        "tool_preset": tool_name,
        "final_depth_mm": 20,
        "safe_z_mm": 20,
        "home_x_mm": 0,
        "home_y_mm": 0,
        "home_z_mm": 20,
    }
    raw.update(overrides)
    return raw


def _vector(vector_id, operation="cut_path", layer="CUT_PATH", piece="piece-a"):
    return {
        "path_key": vector_id,
        "operation_key": operation,
        "dxf_layer": layer,
        "piece_instance_id": piece,
        "piece_label": piece,
    }


def _catalog(*rows):
    return vectors_from_paths(rows)


def _program(*path_keys, operation="cut_path", layer="CUT_PATH"):
    return {
        "operations": [
            {
                "operation_key": operation,
                "dxf_layer": layer,
                "toolpaths": [
                    {
                        "path_key": path_key,
                        "operation_key": operation,
                        "dxf_layer": layer,
                        "ready": True,
                        "closed": True,
                        "points": [[0, 0], [10, 0], [10, 10]],
                        "issues": [],
                    }
                    for path_key in path_keys
                ],
            }
        ]
    }


def test_ball_nose_tool_uses_the_artcam_dialog_fields_and_keeps_the_physical_tool_number():
    tool = normalize_artcam_tool(_artcam())
    assert tool.tool_type == BALL_NOSE
    assert tool.description == "T9_CUT"
    assert tool.tool_number == "T9"
    assert tool.tool_number_display == 9
    assert tool.tool_units == "mm"
    assert tool.rate_units == "mm/sec"
    assert tool.diameter_mm == 5.0
    assert tool.stepdown_mm == 19.0
    assert tool.final_tool_offset_mm == 2.5
    assert tool.stepover_size_mm == 0.2
    assert tool.stepover_percent == 4
    assert tool.spindle_speed_rpm == 15000
    assert tool.feed_rate_mm_sec == 170.0
    assert tool.plunge_rate_mm_sec == 30.0
    stored = artcam_tool_storage(tool)
    assert stored["feed_rate_mm_min"] == 10200.0
    assert stored["plunge_rate_mm_min"] == 1800.0
    assert "final_depth_mm" not in stored
    with pytest.raises(MachiningSetupError) as caught:
        normalize_artcam_tool(_artcam(tool_type="End Mill"))
    assert caught.value.code == "tool_type_unsupported"


def test_profile_copy_is_independent_of_the_base_tool_and_of_other_profiles():
    stored = _stored_tool()
    known = {"T9_CUT": stored}
    first = normalize_profile(_profile(), known_tools=known)
    second = normalize_profile(
        _profile(profile_id="profile:groove", name="Groove profile", final_depth_mm=22),
        known_tools=known,
    )
    first["tool_values"]["diameter_mm"] = 8
    first["final_depth_mm"] = 30
    stored["tool_diameter_mm"] = 5
    assert known["T9_CUT"]["tool_diameter_mm"] == 5
    assert second["tool_values"]["diameter_mm"] == 5
    assert second["final_depth_mm"] == 22
    assert first["tool_preset"] == "T9_CUT"
    assert first["safe_z_mm"] == 20
    assert (first["home_x_mm"], first["home_y_mm"], first["home_z_mm"]) == (0, 0, 20)


def test_profile_rejects_mixed_units_and_a_stepdown_deeper_than_final_depth():
    known = {"T9_CUT": _stored_tool()}
    with pytest.raises(MachiningSetupError) as caught:
        normalize_profile(_profile(final_depth_mm=10), known_tools=known)
    assert caught.value.code == "pass_depth_exceeds_final_depth"
    with pytest.raises(MachiningSetupError) as caught:
        normalize_profile(_profile(safe_z_mm=-1), known_tools=known)
    assert caught.value.code == "safe_z_invalid"


def test_layer_assignment_disables_that_layer_and_its_vectors_everywhere_else():
    catalog = _catalog(
        _vector("cut_path:piece-a:outer", piece="piece-a"),
        _vector("cut_path:piece-b:outer", piece="piece-b"),
        _vector("liner:piece-a:primary", operation="liner", layer="LINER", piece="piece-a"),
    )
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    associations = normalize_associations(
        [
            {
                "association_id": "association:cut",
                "profile_id": profile["profile_id"],
                "selection": {"kind": SELECTION_LAYER, "operation_key": "cut_path"},
            }
        ],
        profiles=[profile],
        catalog=catalog,
    )
    availability = association_availability(catalog, associations)
    cut_layer = next(row for row in availability["layers"] if row["operation_key"] == "cut_path")
    liner_layer = next(row for row in availability["layers"] if row["operation_key"] == "liner")
    assert cut_layer["disabled"] is True
    assert liner_layer["disabled"] is False
    assert all(row["disabled"] for row in availability["vectors"] if row["operation_key"] == "cut_path")
    assert availability["sheet_perimeter"] is None
    with pytest.raises(MachiningSetupError) as caught:
        normalize_associations(
            associations
            + [
                {
                    "association_id": "association:again",
                    "profile_id": profile["profile_id"],
                    "selection": {"kind": SELECTION_VECTORS, "vector_ids": ["cut_path:piece-a:outer"]},
                }
            ],
            profiles=[profile],
            catalog=catalog,
        )
    assert caught.value.code == "vector_already_assigned"


def test_different_vectors_from_one_layer_can_belong_to_different_profiles():
    catalog = _catalog(
        _vector("cut_path:piece-a:outer", piece="piece-a"),
        _vector("cut_path:piece-b:outer", piece="piece-b"),
    )
    known = {"T9_CUT": _stored_tool()}
    first = normalize_profile(_profile(), known_tools=known)
    second = normalize_profile(
        _profile(profile_id="profile:second", name="Second profile"),
        known_tools=known,
    )
    associations = normalize_associations(
        [
            {
                "association_id": "association:a",
                "profile_id": first["profile_id"],
                "selection": {"kind": SELECTION_VECTORS, "vector_ids": ["cut_path:piece-a:outer"]},
                "local_values": {**first, "final_depth_mm": 21},
            },
            {
                "association_id": "association:b",
                "profile_id": second["profile_id"],
                "selection": {"kind": SELECTION_VECTORS, "vector_ids": ["cut_path:piece-b:outer"]},
            },
        ],
        profiles=[first, second],
        catalog=catalog,
    )
    assert associations[0]["local_values"]["final_depth_mm"] == 21
    assert associations[1]["local_values"]["final_depth_mm"] == 20
    assert first["final_depth_mm"] == 20
    remaining = [row for row in associations if row["association_id"] != "association:a"]
    availability = association_availability(catalog, remaining)
    released = next(row for row in availability["vectors"] if row["vector_id"] == "cut_path:piece-a:outer")
    assert released["disabled"] is False
    held = next(row for row in availability["vectors"] if row["vector_id"] == "cut_path:piece-b:outer")
    assert held["disabled"] is True


def test_sheet_perimeter_is_absent_until_connected_and_then_uses_the_existing_path_key():
    separate = _catalog(_vector("cut_path:piece-a:outer"))
    assert association_availability(separate, [])["sheet_perimeter"] is None
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    with pytest.raises(MachiningSetupError) as caught:
        normalize_associations(
            [
                {
                    "association_id": "association:edge",
                    "profile_id": profile["profile_id"],
                    "selection": {"kind": SELECTION_SHEET_PERIMETER},
                }
            ],
            profiles=[profile],
            catalog=separate,
        )
    assert caught.value.code == "sheet_perimeter_unavailable"
    connected = _catalog(
        _vector("cut_path:piece-a:outer"),
        _vector(SHEET_PERIMETER_PATH_KEY, operation="sheet_perimeter", layer="CUT_PATH", piece=""),
    )
    associations = normalize_associations(
        [
            {
                "association_id": "association:edge",
                "profile_id": profile["profile_id"],
                "selection": {"kind": SELECTION_SHEET_PERIMETER},
            }
        ],
        profiles=[profile],
        catalog=connected,
    )
    assert associations[0]["vector_ids"] == [SHEET_PERIMETER_PATH_KEY]
    assert association_availability(connected, associations)["sheet_perimeter"]["disabled"] is True


def test_illustrative_geometry_and_a_direct_reassignment_are_rejected():
    catalog = _catalog(_vector("cut_path:piece-a:outer"))
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    with pytest.raises(MachiningSetupError) as caught:
        normalize_associations(
            [
                {
                    "association_id": "association:text",
                    "profile_id": profile["profile_id"],
                    "selection": {"kind": SELECTION_VECTORS, "vector_ids": ["text:label"]},
                }
            ],
            profiles=[profile],
            catalog=catalog,
        )
    assert caught.value.code == "vector_not_machinable"


def test_calculated_toolpath_keeps_a_snapshot_after_the_profile_and_tool_change():
    catalog = _catalog(_vector("cut_path:piece-a:outer"))
    stored = _stored_tool()
    known = {"T9_CUT": stored}
    profile = normalize_profile(_profile(name="Pocket"), known_tools=known)
    associations = normalize_associations(
        [
            {
                "association_id": "association:cut",
                "profile_id": profile["profile_id"],
                "selection": {"kind": SELECTION_VECTORS, "vector_ids": ["cut_path:piece-a:outer"]},
                "local_values": {**copy.deepcopy(profile), "final_depth_mm": 21, "safe_z_mm": 25},
            }
        ],
        profiles=[profile],
        catalog=catalog,
    )
    snapshot = calculate_toolpath_snapshot(
        association=associations[0],
        toolpath_name="T9_CUT",
        program=_program("cut_path:piece-a:outer"),
    )
    stored["tool_diameter_mm"] = 12
    stored["spindle_speed_rpm"] = 1000
    profile["final_depth_mm"] = 40
    profile["tool_values"]["feed_rate_mm_sec"] = 10
    associations[0]["local_values"]["final_depth_mm"] = 30
    assert snapshot["name"] == "T9_CUT"
    assert snapshot["preset"]["tool_number"] == "T9"
    assert snapshot["preset"]["tool_diameter_mm"] == 5
    assert snapshot["preset"]["final_depth_mm"] == 21
    assert snapshot["preset"]["spindle_speed_rpm"] == 15000
    assert snapshot["safe_z_mm"] == 25
    assert snapshot["home"] == {"x_mm": 0, "y_mm": 0, "z_mm": 20}
    assert snapshot["vector_ids"] == ["cut_path:piece-a:outer"]
    assert snapshot["paths"][0]["points"][0] == [0, 0]
    assert snapshot["paths"][0]["motions"]
    assert snapshot["local_values"]["final_depth_mm"] == 21
    assert "profile_id" in snapshot
    later = append_snapshot([snapshot], {**snapshot, "toolpath_id": "toolpath:second", "name": "T9_NEXT"})
    assert [row["name"] for row in later] == ["T9_CUT", "T9_NEXT"]
    program = overlay_frozen_toolpaths(
        _program("cut_path:piece-a:outer"),
        [snapshot],
    )
    path = program["operations"][0]["toolpaths"][0]
    assert path["preset"]["final_depth_mm"] == 21
    assert path["safe_z_mm"] == 25
    assert path["home"]["z_mm"] == 20


def test_a_second_physical_tool_is_rejected_for_the_same_file():
    catalog = _catalog(
        _vector("cut_path:piece-a:outer", piece="piece-a"),
        _vector("liner:piece-a:primary", operation="liner", layer="LINER", piece="piece-a"),
    )
    other = _stored_tool()
    other["tool_number"] = "T8"
    other["preset_name"] = "T8_CUT"
    known = {"T9_CUT": _stored_tool(), "T8_CUT": other}
    first = normalize_profile(_profile(), known_tools=known)
    second = normalize_profile(
        _profile(profile_id="profile:other", name="Other", tool_preset="T8_CUT"),
        known_tools=known,
    )
    with pytest.raises(MachiningSetupError) as caught:
        normalize_associations(
            [
                {
                    "association_id": "association:a",
                    "profile_id": first["profile_id"],
                    "selection": {"kind": SELECTION_VECTORS, "vector_ids": ["cut_path:piece-a:outer"]},
                },
                {
                    "association_id": "association:b",
                    "profile_id": second["profile_id"],
                    "selection": {"kind": SELECTION_VECTORS, "vector_ids": ["liner:piece-a:primary"]},
                },
            ],
            profiles=[first, second],
            catalog=catalog,
        )
    assert caught.value.code == "tool_identity_conflict"


def test_legacy_tool_copy_does_not_invent_artcam_fields():
    legacy = {
        "preset_name": "Finish",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 6,
        "final_depth_mm": 18,
        "spindle_speed_rpm": 12000,
        "feed_rate_mm_min": 3000,
        "plunge_rate_mm_min": 600,
        "pass_depth_mm": None,
        "enabled": True,
    }
    copied = tool_copy_from_stored(legacy, tool_preset="Finish")
    assert copied["tool_type"] == ""
    assert copied["rate_units"] == "mm/min"
    assert copied["stepover_size_mm"] is None
    assert copied["final_tool_offset_mm"] is None
    legacy["tool_diameter_mm"] = 9
    assert copied["diameter_mm"] == 6
