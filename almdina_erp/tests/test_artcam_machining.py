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
    active_toolpath_snapshots,
    calculate_toolpath_snapshot,
    machining_tool_uses,
    nc_toolpath_fingerprint_rows,
    normalize_artcam_tool,
    normalize_associations,
    normalize_profile,
    order_program_by_associations,
    overlay_frozen_toolpaths,
    apply_reversed_directions,
    effective_operational_program,
    path_geometry_id,
    reversed_direction_block,
    release_stale_toolpath_links,
    tool_copy_from_stored,
    vectors_from_paths,
)
from almdina_erp.almdina_erp.application.cnc.machining_setup import freeze_calculated_toolpath
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    GENERATED,
    NEEDS_REGENERATION,
    effective_status,
    settings_fingerprint,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
    ToolPresetError,
    mm_per_min_from_sec,
    mm_per_sec_from_min,
    normalize_tool_preset,
    tool_delete_blockers,
    unused_tool_preset_can_be_deleted,
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
    assert stored["tool_number"] == "9"
    assert mm_per_min_from_sec(stored["feed_rate_mm_sec"]) == 10200.0
    assert mm_per_min_from_sec(stored["plunge_rate_mm_sec"]) == 1800.0
    assert "feed_rate_mm_min" not in stored
    assert "pass_depth_mm" not in stored
    assert mm_per_sec_from_min(10200) == 170.0
    assert normalize_tool_preset(
        {
            "tool_name": "Finish",
            "tool_number": "T9",
            "tool_diameter_mm": 6,
            "spindle_speed_rpm": 15000,
            "feed_rate_mm_min": 10200,
            "plunge_rate_mm_min": 1800,
            "pass_depth_mm": 7,
        }
    ).feed_rate_mm_min == 10200.0
    with pytest.raises(MachiningSetupError) as caught:
        normalize_artcam_tool(_artcam(tool_type="End Mill"))
    assert caught.value.code == "tool_type_unsupported"


def test_plain_tool_number_is_stored_as_an_integer_and_notes_may_be_empty():
    blank = normalize_artcam_tool(_artcam(notes=""))
    assert blank.tool_number == "T9"
    assert blank.tool_number_display == 9
    assert blank.notes == ""
    assert artcam_tool_storage(blank)["tool_number"] == "9"
    assert artcam_tool_storage(blank)["notes"] == ""

    kept = normalize_artcam_tool(_artcam(notes="Pocket note"))
    assert kept.notes == "Pocket note"
    edited = normalize_artcam_tool(_artcam(notes="Updated note"))
    assert edited.notes == "Updated note"
    with pytest.raises(MachiningSetupError) as too_long:
        normalize_artcam_tool(_artcam(notes="x" * 4001))
    assert too_long.value.code == "notes_invalid"


def test_profile_identity_and_snapshot_are_generated_without_user_input():
    known = {"T9_CUT": _stored_tool()}
    created = normalize_profile(
        {
            "name": "Liner profile",
            "tool_preset": "T9_CUT",
            "final_depth_mm": 20,
            "safe_z_mm": 20,
            "home_x_mm": 0,
            "home_y_mm": 0,
            "home_z_mm": 20,
        },
        known_tools=known,
    )
    other = normalize_profile(
        {
            "name": "Second profile",
            "tool_preset": "T9_CUT",
            "final_depth_mm": 20,
            "safe_z_mm": 20,
            "home_x_mm": 0,
            "home_y_mm": 0,
            "home_z_mm": 20,
        },
        known_tools=known,
    )
    assert created["profile_id"].startswith("profile:")
    assert other["profile_id"].startswith("profile:")
    assert created["profile_id"] != other["profile_id"]
    assert created["tool_values"]["diameter_mm"] == 5.0
    assert created["tool_values"]["tool_number"] == "T9"

    known["T9_CUT"]["diameter_mm"] = 12
    known["T9_CUT"]["tool_diameter_mm"] = 12
    kept = normalize_profile(
        {
            "profile_id": created["profile_id"],
            "name": created["name"],
            "tool_preset": created["tool_preset"],
            "tool_values": dict(created["tool_values"]),
            "final_depth_mm": created["final_depth_mm"],
            "safe_z_mm": created["safe_z_mm"],
            "home_x_mm": created["home_x_mm"],
            "home_y_mm": created["home_y_mm"],
            "home_z_mm": created["home_z_mm"],
        },
        known_tools=known,
    )
    assert kept["profile_id"] == created["profile_id"]
    assert kept["tool_values"]["diameter_mm"] == 5.0

    replacement = _stored_tool()
    replacement["description"] = "Other"
    replacement["tool_name"] = "Other"
    replacement["diameter_mm"] = 8
    replacement["tool_diameter_mm"] = 8
    known["Other"] = replacement
    switched = normalize_profile(
        {
            "profile_id": created["profile_id"],
            "name": created["name"],
            "tool_preset": "Other",
            "tool_values": {},
            "final_depth_mm": created["final_depth_mm"],
            "safe_z_mm": created["safe_z_mm"],
            "home_x_mm": created["home_x_mm"],
            "home_y_mm": created["home_y_mm"],
            "home_z_mm": created["home_z_mm"],
        },
        known_tools=known,
    )
    assert switched["tool_values"]["diameter_mm"] == 8.0
    assert created["tool_values"]["diameter_mm"] == 5.0

    with pytest.raises(MachiningSetupError) as missing_name:
        normalize_profile(
            {"tool_preset": "T9_CUT", "final_depth_mm": 20, "safe_z_mm": 20, "home_x_mm": 0, "home_y_mm": 0, "home_z_mm": 20},
            known_tools=known,
        )
    assert missing_name.value.code == "profile_name_required"
    with pytest.raises(MachiningSetupError) as bad_id:
        normalize_profile(
            {**created, "profile_id": "bad id"},
            known_tools=known,
        )
    assert bad_id.value.code == "profile_id_invalid"


def test_association_overrides_stay_local_and_unresolved_sources_do_not_calculate():
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    original_depth = profile["final_depth_mm"]
    original_feed = profile["tool_values"]["feed_rate_mm_sec"]
    catalog = _catalog(
        _vector("cut_path:piece-a:outer", "cut_path", "CUT_PATH"),
        _vector("liner:piece-a", "liner", "Liner"),
        _vector("note:a", "text", "TEXT"),
    )
    availability = association_availability(catalog, [])
    assert [row["dxf_layer"] for row in availability["layers"]] == ["CUT_PATH", "Liner"]
    assert "vectors" in availability
    stored = normalize_associations(
        [
            {
                "association_id": "association:one",
                "name": "Pocket",
                "profile_id": profile["profile_id"],
                "selection": {"kind": "layer", "operation_key": "cut_path"},
                "local_values": {
                    "final_depth_mm": 15,
                    "tool_values": {**profile["tool_values"], "feed_rate_mm_sec": 80, "stepdown_mm": 5},
                },
            },
            {
                "association_id": "association:two",
                "name": "Edge",
                "profile_id": profile["profile_id"],
                "selection": {"kind": "layer", "operation_key": "liner"},
            },
            {
                "association_id": "association:later",
                "name": "Later",
                "profile_id": profile["profile_id"],
                "selection": {"kind": "selected_vectors"},
            },
        ],
        profiles=[profile],
        catalog=catalog,
        keep_unresolved=True,
    )
    assert stored[0]["local_values"]["final_depth_mm"] == 15.0
    assert stored[0]["local_values"]["tool_values"]["feed_rate_mm_sec"] == 80.0
    assert stored[1]["local_values"]["final_depth_mm"] == original_depth
    assert stored[1]["local_values"]["tool_values"]["feed_rate_mm_sec"] == original_feed
    assert profile["final_depth_mm"] == original_depth
    assert stored[0]["association_id"] != stored[1]["association_id"]
    assert stored[2]["conflict"] == "selected_vectors_pending"
    assert stored[2]["geometry_ready"] is False
    with pytest.raises(MachiningSetupError) as pending:
        calculate_toolpath_snapshot(
            association=stored[2],
            toolpath_name="Later",
            program=_program("cut_path:piece-a:outer"),
        )
    assert pending.value.code == "selected_vectors_pending"
    blocked = normalize_associations(
        [{
            "association_id": "association:edge",
            "name": "Perimeter",
            "profile_id": profile["profile_id"],
            "selection": {"kind": "sheet_perimeter"},
        }],
        profiles=[profile],
        catalog=catalog,
        keep_unresolved=True,
    )
    assert blocked[0]["conflict"] == "sheet_perimeter_unavailable"
    assert blocked[0]["vector_ids"] == []
    ordered = order_program_by_associations(
        {
            "operations": [
                {"operation_key": "liner", "toolpaths": [{"path_key": "liner:piece-a"}]},
                {"operation_key": "cut_path", "toolpaths": [{"path_key": "cut_path:piece-a:outer"}]},
            ]
        },
        stored[:2],
    )
    assert [row["operation_key"] for row in ordered["operations"]] == ["cut_path", "liner"]


    selected = normalize_associations(
        [{
            "association_id": "association:picked",
            "name": "Picked",
            "profile_id": profile["profile_id"],
            "selection": {"kind": "selected_vectors", "vector_ids": ["cut_path:piece-a:outer"]},
        }],
        profiles=[profile],
        catalog=catalog,
    )
    assert selected[0]["geometry_ready"] is True
    assert selected[0]["vector_ids"] == ["cut_path:piece-a:outer"]
    assert selected[0]["selection"]["kind"] == "selected_vectors"
    with pytest.raises(MachiningSetupError) as duplicate:
        normalize_associations(
            [
                selected[0],
                {
                    "association_id": "association:again",
                    "name": "Again",
                    "profile_id": profile["profile_id"],
                    "selection": {"kind": "selected_vectors", "vector_ids": ["cut_path:piece-a:outer"]},
                },
            ],
            profiles=[profile],
            catalog=catalog,
        )
    assert duplicate.value.code == "vector_already_assigned"


def _motion_program(points, depths=(5.0, 10.0), closed=False, path_key="cut_path:piece-a:outer"):
    from almdina_erp.almdina_erp.domain.cnc.program import _motions

    motions = _motions(points, closed=closed, depths=depths)
    return {
        "geometry_ready": True,
        "coordinate_space": "sheet_bottom_left_y_up_mm",
        "operations": [{
            "operation_key": "cut_path",
            "toolpaths": [{
                "path_key": path_key,
                "closed": closed,
                "ready": True,
                "points": [[point[0], point[1]] for point in points],
                "motions": [
                    {
                        "kind": motion.kind,
                        "x_mm": motion.x_mm,
                        "y_mm": motion.y_mm,
                        "depth_mm": motion.depth_mm,
                    }
                    for motion in motions
                ],
                "preset": {
                    "tool_number": "T9",
                    "spindle_speed_rpm": 18000,
                    "feed_rate_mm_min": 2400,
                    "plunge_rate_mm_min": 600,
                    "safe_z_mm": 5,
                },
                "safe_z_mm": 5,
            }],
        }],
    }


def test_reverse_changes_nc_direction_without_changing_depth_or_tool():
    from almdina_erp.almdina_erp.domain.cnc.post_processor import emit_nc

    points = ((0.0, 0.0), (10.0, 0.0), (10.0, 5.0))
    program = _motion_program(points)
    identity = path_geometry_id(program["operations"][0]["toolpaths"][0])
    reversed_program = apply_reversed_directions(
        program,
        [{"path_key": "cut_path:piece-a:outer", "geometry_id": identity}],
    )
    path = reversed_program["operations"][0]["toolpaths"][0]
    assert path["points"][0] == [10.0, 5.0]
    assert path["points"][-1] == [0.0, 0.0]
    plunges = [motion for motion in path["motions"] if motion["kind"] == "plunge"]
    assert [motion["depth_mm"] for motion in plunges] == [5.0, 10.0]
    assert path["preset"]["feed_rate_mm_min"] == 2400
    original_nc = emit_nc(program).text
    reversed_nc = emit_nc(reversed_program).text
    assert "G0 X0 Y0" in original_nc
    assert "G0 X10 Y5" in reversed_nc
    assert "G1 Z-5" in reversed_nc
    stale = apply_reversed_directions(
        program,
        [{"path_key": "cut_path:piece-a:outer", "geometry_id": "not-this-path"}],
    )
    assert stale["operations"][0]["toolpaths"][0]["points"][0] == [0.0, 0.0]
    assert stale["issues"][0]["code"] == "path_reverse_stale"
    assert stale["nc_export_ready"] is False
    assert reversed_direction_block(stale) == "path_reverse_stale"
    unsupported = apply_reversed_directions(
        {
            "operations": [{
                "toolpaths": [{
                    "path_key": "cut_path:arc",
                    "closed": False,
                    "points": [[0, 0, 1], [2, 0, 1]],
                    "motions": [],
                }],
            }],
        },
        [{"path_key": "cut_path:arc", "geometry_id": ""}],
    )
    assert unsupported["issues"][0]["code"] == "path_reverse_unsupported"
    assert unsupported["operations"][0]["toolpaths"][0]["points"][0] == [0, 0, 1]
    assert unsupported["nc_export_ready"] is False
    assert reversed_direction_block(unsupported) == "path_reverse_unsupported"
    closed = _motion_program(((0, 0), (4, 0), (4, 4), (0, 0)), depths=(3.0,), closed=True, path_key="cut_path:closed")
    closed_id = path_geometry_id(closed["operations"][0]["toolpaths"][0])
    closed_reversed = apply_reversed_directions(
        closed,
        [{"path_key": "cut_path:closed", "geometry_id": closed_id}],
    )
    closed_path = closed_reversed["operations"][0]["toolpaths"][0]
    assert closed_path["points"][0] == [4.0, 4.0]
    assert [motion["depth_mm"] for motion in closed_path["motions"] if motion["kind"] == "plunge"] == [3.0]
    original_edges = _undirected_edges(closed["operations"][0]["toolpaths"][0]["points"], closed=True)
    reversed_edges = _undirected_edges(closed_path["points"], closed=True)
    assert original_edges == reversed_edges
    second = apply_reversed_directions(
        closed_reversed,
        [{"path_key": "cut_path:closed", "geometry_id": closed_id}],
    )
    assert second["direction_blocked"] is True
    assert second["operations"][0]["toolpaths"][0]["points"] == closed_path["points"]
    missing = apply_reversed_directions(
        closed,
        [{"path_key": "cut_path:gone", "geometry_id": closed_id}],
    )
    assert missing["issues"][0]["code"] == "path_reverse_missing"
    assert missing["nc_export_ready"] is False
    restored = apply_reversed_directions(closed, [])
    assert restored["operations"][0]["toolpaths"][0]["points"][0] == [0.0, 0.0]


def _undirected_edges(points, *, closed):
    sequence = [tuple(point) for point in points]
    if closed and len(sequence) > 2 and sequence[0] == sequence[-1]:
        sequence = sequence[:-1]
    edges = []
    for start, end in zip(sequence, sequence[1:]):
        edges.append(tuple(sorted((start, end))))
    if closed and len(sequence) > 2:
        edges.append(tuple(sorted((sequence[-1], sequence[0]))))
    return sorted(edges)


def test_effective_program_uses_the_frozen_path_before_reverse():
    program = _motion_program(((0, 0), (10, 0)), depths=(4.0,), path_key="cut_path:local")
    program["geometry_ready"] = True
    program["nc_export_ready"] = True
    frozen_points = [[0, 0], [10, 0], [10, 6]]
    snapshot = {
        "toolpath_id": "tp-local",
        "preset": {"tool_diameter_mm": 8, "final_depth_mm": 4, "feed_rate_mm_min": 1000},
        "safe_z_mm": 20,
        "paths": [{
            "path_key": "cut_path:local",
            "operation_key": "cut_path",
            "closed": False,
            "points": frozen_points,
            "motions": program["operations"][0]["toolpaths"][0]["motions"],
        }],
    }
    associations = [
        {"association_id": "b", "toolpath_id": "tp-local", "vector_ids": ["cut_path:local"]},
        {"association_id": "a", "vector_ids": ["cut_path:other"]},
    ]
    identity = path_geometry_id({"points": frozen_points, "closed": False})
    effective = effective_operational_program(
        program,
        snapshots=[snapshot],
        associations=associations,
        reversed_path_keys=[{"path_key": "cut_path:local", "geometry_id": identity}],
    )
    path = effective["operations"][0]["toolpaths"][0]
    assert path["points"][0] == [10.0, 6.0]
    assert path["points"][-1] == [0.0, 0.0]
    assert path["preset"]["tool_diameter_mm"] == 8
    assert reversed_direction_block(effective) == ""
    stale = effective_operational_program(
        program,
        snapshots=[snapshot],
        associations=associations,
        reversed_path_keys=[{"path_key": "cut_path:local", "geometry_id": "old-plan"}],
    )
    assert reversed_direction_block(stale) == "path_reverse_stale"
    assert stale["nc_export_ready"] is False


def test_association_keeps_a_different_local_tool_without_changing_the_profile():
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    catalog = _catalog(_vector("cut_path:piece-a:outer", "cut_path", "CUT_PATH"))
    stored = normalize_associations(
        [{
            "association_id": "association:tool",
            "name": "Local tool",
            "profile_id": profile["profile_id"],
            "selection": {"kind": "vectors", "vector_ids": ["cut_path:piece-a:outer"]},
            "local_values": {
                "tool_preset": "T12_LOCAL",
                "tool_values": {
                    **profile["tool_values"],
                    "tool_preset": "T12_LOCAL",
                    "description": "T12_LOCAL",
                    "tool_number": 9,
                    "feed_rate_mm_sec": 40,
                },
            },
        }],
        profiles=[profile],
        catalog=catalog,
    )
    assert stored[0]["local_values"]["tool_preset"] == "T12_LOCAL"
    assert stored[0]["local_values"]["tool_values"]["feed_rate_mm_sec"] == 40.0
    assert profile["tool_preset"] != "T12_LOCAL"
    with pytest.raises(MachiningSetupError) as conflict:
        normalize_associations(
            [
                stored[0],
                {
                    "association_id": "association:other",
                    "name": "Other tool",
                    "profile_id": profile["profile_id"],
                    "selection": {"kind": "vectors", "vector_ids": ["liner:piece-a"]},
                    "local_values": {
                        "tool_preset": "T8_OTHER",
                        "tool_values": {**profile["tool_values"], "tool_number": 8},
                    },
                },
            ],
            profiles=[profile],
            catalog=_catalog(
                _vector("cut_path:piece-a:outer", "cut_path", "CUT_PATH"),
                _vector("liner:piece-a", "liner", "Liner"),
            ),
        )
    assert conflict.value.code == "tool_identity_conflict"


def test_repeated_layer_order_follows_association_identity():
    ordered = order_program_by_associations(
        {
            "operations": [
                {
                    "operation_key": "cut_path",
                    "toolpaths": [{"path_key": "layer-1:a"}, {"path_key": "layer-1:c"}],
                },
                {"operation_key": "liner", "toolpaths": [{"path_key": "layer-2:b"}]},
            ]
        },
        [
            {"association_id": "a", "vector_ids": ["layer-1:a"]},
            {"association_id": "b", "vector_ids": ["layer-2:b"]},
            {"association_id": "c", "vector_ids": ["layer-1:c"]},
        ],
    )
    assert [
        path["path_key"]
        for operation in ordered["operations"]
        for path in operation["toolpaths"]
    ] == ["layer-1:a", "layer-2:b", "layer-1:c"]


def test_reopened_profile_keeps_its_tool_copy_after_the_base_tool_changes():
    stored = _stored_tool()
    known = {"T9_CUT": stored}
    saved = normalize_profile(_profile(), known_tools=known)
    stored["tool_diameter_mm"] = 12
    stored["diameter_mm"] = 12
    reopened = normalize_profile(
        {
            "profile_id": saved["profile_id"],
            "name": saved["name"],
            "tool_preset": saved["tool_preset"],
            "tool_values": dict(saved["tool_values"]),
            "final_depth_mm": saved["final_depth_mm"],
            "safe_z_mm": saved["safe_z_mm"],
            "home_x_mm": saved["home_x_mm"],
            "home_y_mm": saved["home_y_mm"],
            "home_z_mm": saved["home_z_mm"],
        },
        known_tools=known,
    )
    assert reopened["tool_values"]["diameter_mm"] == 5.0
    assert known["T9_CUT"]["tool_diameter_mm"] == 12


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


def _linked(profile, association_id, vector_ids, **local_overrides):
    local = {**copy.deepcopy(profile), **local_overrides}
    return {
        "association_id": association_id,
        "profile_id": profile["profile_id"],
        "selection": {"kind": SELECTION_VECTORS, "vector_ids": list(vector_ids)},
        "local_values": local,
    }


def test_profile_edits_keep_an_independent_validated_tool_copy():
    stored = _stored_tool()
    known = {"T9_CUT": stored}
    created = normalize_profile(_profile(), known_tools=known)
    edited_tool = copy.deepcopy(created["tool_values"])
    edited_tool["diameter_mm"] = 8
    edited_tool["feed_rate_mm_sec"] = 20
    edited_tool["stepover_percent"] = 10
    edited = normalize_profile(
        {
            **created,
            "final_depth_mm": 22,
            "safe_z_mm": 30,
            "home_x_mm": 4,
            "tool_values": edited_tool,
        },
        known_tools={"T9_CUT": stored},
    )
    assert stored["tool_diameter_mm"] == 5
    assert stored["feed_rate_mm_sec"] == 170
    assert edited["tool_values"]["diameter_mm"] == 8
    assert edited["tool_values"]["feed_rate_mm_sec"] == 20
    assert edited["final_depth_mm"] == 22
    assert edited["safe_z_mm"] == 30
    assert edited["home_x_mm"] == 4
    reopened = normalize_profile(edited, known_tools={})
    assert reopened["tool_values"]["diameter_mm"] == 8
    stored["tool_diameter_mm"] = 11
    stored["feed_rate_mm_sec"] = 1
    again = normalize_profile(edited, known_tools={"T9_CUT": stored})
    assert again["tool_values"]["diameter_mm"] == 8
    assert again["tool_values"]["feed_rate_mm_sec"] == 20
    with pytest.raises(MachiningSetupError) as invalid:
        normalize_profile(
            {**created, "tool_values": {**created["tool_values"], "stepover_percent": 0}},
            known_tools=known,
        )
    assert invalid.value.code == "stepover_invalid"


def test_feed_rate_is_converted_from_mm_per_second_once():
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    catalog = _catalog(_vector("cut_path:piece-a:outer"))
    associations = normalize_associations(
        [_linked(profile, "association:cut", ["cut_path:piece-a:outer"])],
        profiles=[profile],
        catalog=catalog,
    )
    assert associations[0]["local_values"]["tool_values"]["feed_rate_mm_sec"] == 170
    assert associations[0]["local_values"]["tool_values"]["rate_units"] == RATE_UNITS_MM_SEC
    snapshot = calculate_toolpath_snapshot(
        association=associations[0],
        toolpath_name="T9_CUT",
        program=_program("cut_path:piece-a:outer"),
    )
    assert snapshot["preset"]["feed_rate_mm_min"] == 10200
    assert snapshot["preset"]["plunge_rate_mm_min"] == 1800


def test_one_association_can_hold_several_vectors_and_can_be_edited_in_place():
    catalog = _catalog(
        _vector("cut_path:piece-a:outer", piece="piece-a"),
        _vector("cut_path:piece-b:outer", piece="piece-b"),
        _vector("cut_path:piece-c:outer", piece="piece-c"),
    )
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    other = normalize_profile(_profile(profile_id="profile:other", name="Other"), known_tools=known)
    stored = normalize_associations(
        [
            _linked(profile, "association:group", ["cut_path:piece-a:outer", "cut_path:piece-b:outer"]),
            _linked(other, "association:rest", ["cut_path:piece-c:outer"]),
        ],
        profiles=[profile, other],
        catalog=catalog,
    )
    assert stored[0]["vector_ids"] == ["cut_path:piece-a:outer", "cut_path:piece-b:outer"]
    edited = normalize_associations(
        [
            {
                **stored[0],
                "local_values": {**stored[0]["local_values"], "final_depth_mm": 24, "safe_z_mm": 28},
                "toolpath_id": "toolpath:old",
            },
            stored[1],
        ],
        profiles=[profile, other],
        catalog=catalog,
    )
    assert edited[0]["association_id"] == "association:group"
    assert edited[0]["vector_ids"] == stored[0]["vector_ids"]
    assert edited[1]["local_values"]["final_depth_mm"] == 20
    with pytest.raises(MachiningSetupError) as overlap:
        normalize_associations(
            [
                _linked(profile, "association:group", ["cut_path:piece-a:outer", "cut_path:piece-c:outer"]),
                stored[1],
            ],
            profiles=[profile, other],
            catalog=catalog,
        )
    assert overlap.value.code == "vector_already_assigned"


def test_editing_an_association_releases_its_active_snapshot_without_deleting_history():
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    catalog = _catalog(_vector("cut_path:piece-a:outer"))
    association = normalize_associations(
        [_linked(profile, "association:cut", ["cut_path:piece-a:outer"], final_depth_mm=21)],
        profiles=[profile],
        catalog=catalog,
    )[0]
    snapshot = calculate_toolpath_snapshot(
        association=association,
        toolpath_name="T9_CUT",
        program=_program("cut_path:piece-a:outer"),
        toolpath_id="toolpath:first",
    )
    association["toolpath_id"] = snapshot["toolpath_id"]
    unchanged = release_stale_toolpath_links([association], [snapshot])
    assert unchanged[0]["toolpath_id"] == "toolpath:first"
    changed = copy.deepcopy(association)
    changed["local_values"]["final_depth_mm"] = 25
    released = release_stale_toolpath_links([changed], [snapshot])
    assert released[0]["toolpath_id"] == ""
    assert snapshot["local_values"]["final_depth_mm"] == 21
    program = overlay_frozen_toolpaths(
        _program("cut_path:piece-a:outer"),
        [snapshot],
        associations=released,
    )
    assert program["operations"][0]["toolpaths"][0].get("safe_z_mm") is None


def test_reassigning_a_vector_keeps_history_and_executes_only_the_linked_snapshot():
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    catalog = _catalog(_vector("cut_path:piece-a:outer"))
    first_association = normalize_associations(
        [_linked(profile, "association:first", ["cut_path:piece-a:outer"], final_depth_mm=21)],
        profiles=[profile],
        catalog=catalog,
    )[0]
    program = _program("cut_path:piece-a:outer")
    first = freeze_calculated_toolpath(
        association=first_association,
        toolpath_name="First",
        program=program,
        snapshots=[],
    )
    first_association["toolpath_id"] = first[-1]["toolpath_id"]
    second_association = normalize_associations(
        [_linked(profile, "association:second", ["cut_path:piece-a:outer"], final_depth_mm=22)],
        profiles=[profile],
        catalog=catalog,
    )[0]
    both = freeze_calculated_toolpath(
        association=second_association,
        toolpath_name="Second",
        program=program,
        snapshots=first,
    )
    second_association["toolpath_id"] = both[-1]["toolpath_id"]
    assert len(both) == 2
    assert both[0]["superseded_by"] == both[1]["toolpath_id"]
    active = active_toolpath_snapshots(both, [second_association])
    assert [row["name"] for row in active] == ["Second"]
    overlaid = overlay_frozen_toolpaths(program, both, associations=[second_association])
    assert overlaid["operations"][0]["toolpaths"][0]["preset"]["final_depth_mm"] == 22
    assert len(overlaid["operations"][0]["toolpaths"]) == 1


def test_toolpath_snapshot_fingerprint_tracks_nc_changes_and_ignores_json_shape():
    base = settings_fingerprint(
        operation_presets={"cut_path": "T9_CUT"},
        path_overrides={},
        presets={"T9_CUT": _stored_tool()},
        machine_profile={"tool_number": "T9"},
    )
    assert settings_fingerprint(
        operation_presets={"cut_path": "T9_CUT"},
        path_overrides={},
        presets={"T9_CUT": _stored_tool()},
        machine_profile={"tool_number": "T9"},
        toolpath_snapshots=[],
        vector_associations=[],
    ) == base
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    catalog = _catalog(_vector("cut_path:piece-a:outer"))
    association = normalize_associations(
        [_linked(profile, "association:cut", ["cut_path:piece-a:outer"], final_depth_mm=21, safe_z_mm=25)],
        profiles=[profile],
        catalog=catalog,
    )[0]
    snapshot = calculate_toolpath_snapshot(
        association=association,
        toolpath_name="T9_CUT",
        program=_program("cut_path:piece-a:outer"),
        toolpath_id="toolpath:first",
    )
    association["toolpath_id"] = snapshot["toolpath_id"]
    arguments = {
        "operation_presets": {"cut_path": "T9_CUT"},
        "path_overrides": {},
        "presets": {"T9_CUT": _stored_tool()},
        "machine_profile": {"tool_number": "T9"},
        "toolpath_snapshots": [snapshot],
        "vector_associations": [association],
    }
    current = settings_fingerprint(**arguments)
    assert current != base
    assert effective_status(
        generation_fingerprint=current,
        current_fingerprint=current,
        stored_plan=("PLAN-1", 1),
        current_plan=("PLAN-1", 1),
        generated_file="/private/files/sheet.sim.nc",
        file_present=True,
        snapshot_complete=True,
    ) == GENERATED
    changed_snapshot = copy.deepcopy(snapshot)
    changed_snapshot["preset"]["feed_rate_mm_min"] = 9000
    changed_snapshot["paths"][0]["motions"] = [{"kind": "cut", "x_mm": 1, "y_mm": 2, "depth_mm": 3}]
    changed = settings_fingerprint(**{**arguments, "toolpath_snapshots": [changed_snapshot]})
    assert changed != current
    assert effective_status(
        generation_fingerprint=current,
        current_fingerprint=changed,
        stored_plan=("PLAN-1", 1),
        current_plan=("PLAN-1", 1),
        generated_file="/private/files/sheet.sim.nc",
        file_present=True,
        snapshot_complete=True,
    ) == NEEDS_REGENERATION
    shuffled = copy.deepcopy(snapshot)
    shuffled["preset"] = {key: shuffled["preset"][key] for key in reversed(list(shuffled["preset"]))}
    shuffled["unused_note"] = "formatting only"
    assert nc_toolpath_fingerprint_rows([shuffled], [association]) == nc_toolpath_fingerprint_rows(
        [snapshot],
        [association],
    )
    assert settings_fingerprint(**{**arguments, "toolpath_snapshots": [shuffled]}) == current


def test_a_tool_can_be_saved_without_final_depth_and_calculation_still_requires_it():
    stored = _stored_tool()
    created = normalize_tool_preset(stored)
    assert created.final_depth_mm is None
    assert created.pass_depth_mm == 19.0
    ignored = normalize_tool_preset({**stored, "final_depth_mm": 20})
    assert ignored.final_depth_mm is None
    kept = normalize_tool_preset(stored, machining_depth_mm=20)
    assert kept.final_depth_mm == 20.0
    with pytest.raises(ToolPresetError) as invalid:
        normalize_tool_preset(stored, machining_depth_mm=-1)
    assert invalid.value.code == "final_depth_invalid"
    with pytest.raises(ToolPresetError) as deeper:
        normalize_tool_preset({**stored, "pass_depth_mm": 19}, machining_depth_mm=10)
    assert deeper.value.code == "pass_depth_exceeds_final_depth"

    known = {"T9_CUT": stored}
    with pytest.raises(MachiningSetupError) as profile_depth:
        normalize_profile(_profile(final_depth_mm=None), known_tools=known)
    assert profile_depth.value.code == "final_depth_invalid"
    profile = normalize_profile(_profile(), known_tools=known)
    catalog = _catalog(_vector("cut_path:piece-a:outer"))
    association = normalize_associations(
        [
            {
                "association_id": "association:cut",
                "profile_id": profile["profile_id"],
                "selection": {"kind": SELECTION_VECTORS, "vector_ids": ["cut_path:piece-a:outer"]},
            }
        ],
        profiles=[profile],
        catalog=catalog,
    )[0]
    missing_depth = copy.deepcopy(association)
    missing_depth["local_values"]["final_depth_mm"] = None
    with pytest.raises(MachiningSetupError) as calculation:
        calculate_toolpath_snapshot(
            association=missing_depth,
            toolpath_name="Cut",
            program=_program("cut_path:piece-a:outer"),
        )
    assert calculation.value.code == "final_depth_invalid"
    calculated = calculate_toolpath_snapshot(
        association=association,
        toolpath_name="Cut",
        program=_program("cut_path:piece-a:outer"),
    )
    assert calculated["preset"]["final_depth_mm"] == 20


def test_a_tool_used_by_a_profile_association_or_snapshot_cannot_be_deleted():
    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    association = {"local_values": profile}
    snapshot = {"local_values": profile, "preset": {"preset_name": "T9_CUT"}}
    assert machining_tool_uses("T9_CUT", profiles=[profile])["profiles"] == 1
    assert machining_tool_uses("T9_CUT", associations=[association])["associations"] == 1
    assert machining_tool_uses("T9_CUT", snapshots=[snapshot])["snapshots"] == 1
    assert machining_tool_uses("Unused", profiles=[profile])["profiles"] == 0
    assert unused_tool_preset_can_be_deleted(
        operation_uses=0, path_uses=0, factory_uses=0, machining_uses=0
    ) is True
    assert unused_tool_preset_can_be_deleted(
        operation_uses=0, path_uses=0, factory_uses=0, machining_uses=1
    ) is False
    historical = machining_tool_uses("T9_CUT", snapshots=[snapshot])
    assert historical["historical_snapshots"] == 1
    assert historical["active_snapshots"] == 0
    assert tool_delete_blockers() == ()
    assert tool_delete_blockers(active_snapshot_uses=historical["active_snapshots"]) == ()
    active = machining_tool_uses(
        "T9_CUT",
        associations=[{"toolpath_id": "toolpath:current", "local_values": profile}],
        snapshots=[{**snapshot, "toolpath_id": "toolpath:current"}],
    )
    assert active["active_snapshots"] == 1
    assert active["associations"] == 1
    assert tool_delete_blockers(
        profile_uses=1,
        association_uses=1,
        active_snapshot_uses=1,
        operation_uses=1,
        factory_uses=1,
    ) == (
        "operational_file",
        "factory_default",
        "profile",
        "association",
        "active_snapshot",
    )
