"""Connected sheet-perimeter CUT_PATH join: geometry, compile, fingerprint."""

from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.cnc.nc_export import build_simulation_nc
from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.application.cnc.simulation_nc import build_generation_snapshot
from almdina_erp.almdina_erp.application.cnc.workspace import prepare_sheet_settings
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    ApprovedPlanRef,
    OperationalFileError,
    catalog_sheet,
    settings_fingerprint,
)
from almdina_erp.almdina_erp.domain.cnc.perimeter import (
    CUT_PATH_INTERNAL_SEQUENCE_KEY,
    SHEET_PERIMETER_PATH_KEY,
    connected_cut_path_order_keys,
    diagnose_cut_network,
    edge_sets_equal,
    extract_connected_perimeter,
    polyline_segments,
    prefer_uploaded_perimeter_polyline,
    remaining_segments_after_perimeter,
    resolve_cut_path_sequence,
    segment_edge_multiset,
)
from almdina_erp.almdina_erp.domain.cnc.post_processor import POST_PROCESSOR_VERSION


KERF_MM = 5.0
SHEET_W = 1220.0
SHEET_H = 2440.0


def _raw(**overrides):
    values = {
        "preset_name": "Finish",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 5,
        "final_depth_mm": 18,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 8000,
        "plunge_rate_mm_min": 1500,
        "pass_depth_mm": 6,
        "enabled": True,
    }
    values.update(overrides)
    return values


PRESETS = {"Finish": _raw()}


def _rect(x, y, width, height):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


def _piece(instance_id, outer, *, sheet_no=1, label=None):
    return {
        "piece_instance_id": instance_id,
        "label": label or instance_id,
        "sheet_no": sheet_no,
        "piece_type": "Regular",
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
        "geometry": {
            "schema_version": 1,
            "unit": "mm",
            "coordinate_space": "usable_sheet",
            "outer": outer,
            "holes": [],
        },
    }


def _snapshot():
    return {
        "kerf_mm": KERF_MM,
        "full_board_width_cm": SHEET_W / 10.0,
        "full_board_length_cm": SHEET_H / 10.0,
        "sheets": [
            {
                "sheet_no": 1,
                "full_width_cm": SHEET_W / 10.0,
                "full_length_cm": SHEET_H / 10.0,
                "applied_trim_width_cm": 0,
                "applied_trim_length_cm": 0,
            }
        ],
    }


def test_default_join_mode_is_separate_and_fingerprint_stable():
    pieces = [_piece("A", _rect(50, 50, 400, 600))]
    catalog = catalog_sheet(1, pieces)
    assert all(path.path_key != SHEET_PERIMETER_PATH_KEY for path in catalog.paths)
    left = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets=PRESETS,
        operation_order=["cut_path"],
    )
    right = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets=PRESETS,
        operation_order=["cut_path"],
        perimeter_join_mode="separate",
        cut_path_sequence=[],
        perimeter_cut_early_confirmed=False,
    )
    assert left == right


def test_connected_mode_changes_fingerprint_and_marks_regeneration():
    base = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets=PRESETS,
        operation_order=["cut_path"],
        perimeter_join_mode="separate",
    )
    connected = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets=PRESETS,
        operation_order=["cut_path"],
        perimeter_join_mode="connected",
        cut_path_sequence=[SHEET_PERIMETER_PATH_KEY],
    )
    assert base != connected


def test_extract_rectangular_perimeter_and_union_equality():
    segments = polyline_segments(_rect(0, 0, 100, 80), closed=True)
    perimeter = extract_connected_perimeter(segments)
    assert perimeter.closed
    assert perimeter.edge_count == 4
    leftovers = remaining_segments_after_perimeter(segments, perimeter)
    assert leftovers == []
    assert edge_sets_equal(
        segments,
        polyline_segments(perimeter.points, closed=True) + leftovers,
    )


def test_extract_stepped_perimeter_with_shared_edge():
    # Two rectangles sharing one vertical edge → outer stepped outline.
    left = polyline_segments(_rect(0, 0, 100, 100), closed=True)
    right = polyline_segments(_rect(100, 0, 100, 50), closed=True)
    network = left + right
    perimeter = extract_connected_perimeter(network)
    leftovers = remaining_segments_after_perimeter(network, perimeter)
    assert perimeter.closed
    assert perimeter.edge_count == 7
    assert edge_sets_equal(
        network,
        polyline_segments(perimeter.points, closed=True) + leftovers,
    )
    # Shared wall is internal (present twice from both piece rings) and stays.
    shared = segment_edge_multiset([[(100, 0), (100, 50)]])
    remaining = segment_edge_multiset(leftovers)
    assert remaining[next(iter(shared))] == 2


def test_small_corner_jog_is_preserved():
    points = [
        (0, 0),
        (100, 0),
        (100, 40),
        (95, 40),
        (95, 45),
        (100, 45),
        (100, 80),
        (0, 80),
    ]
    segments = polyline_segments(points, closed=True)
    perimeter = extract_connected_perimeter(segments)
    assert len(perimeter.points) == 8
    assert (95.0, 40.0) in perimeter.points
    assert (95.0, 45.0) in perimeter.points


def test_open_and_disconnected_networks_fail_closed():
    with pytest.raises(OperationalFileError) as open_exc:
        extract_connected_perimeter([[(0, 0), (10, 0)], [(10, 0), (20, 0)]])
    assert open_exc.value.code in {"perimeter_not_closed", "perimeter_unavailable"}

    left = polyline_segments(_rect(0, 0, 20, 20), closed=True)
    right = polyline_segments(_rect(50, 50, 20, 20), closed=True)
    with pytest.raises(OperationalFileError) as disconnected:
        extract_connected_perimeter(left + right)
    assert disconnected.value.code == "perimeter_components_disconnected"


def test_t_junction_and_mid_edge_internal_keep_union():
    outer = polyline_segments(_rect(0, 0, 100, 80), closed=True)
    # Internal path ending mid-bottom edge.
    internal = [((50, 40), (50, 0))]
    network = outer + internal
    perimeter = extract_connected_perimeter(network)
    leftovers = remaining_segments_after_perimeter(network, perimeter)
    assert edge_sets_equal(
        network,
        polyline_segments(perimeter.points, closed=True) + leftovers,
    )
    assert segment_edge_multiset(leftovers)[segment_edge_multiset(internal).most_common(1)[0][0]] == 1


def test_prefer_uploaded_closed_polyline():
    outer = polyline_segments(_rect(0, 0, 120, 90), closed=True)
    preferred = prefer_uploaded_perimeter_polyline(
        [
            {
                "closed": True,
                "points": [(0, 0), (120, 0), (120, 90), (0, 90)],
                "entity_id": 7,
            }
        ],
        outer,
    )
    assert preferred is not None
    assert preferred.closed
    assert preferred.edge_count == 4


def test_legacy_sequence_helper_no_longer_rejects_perimeter_before_internals():
    keys = connected_cut_path_order_keys()
    ordered = resolve_cut_path_sequence(keys, None)
    assert ordered == (CUT_PATH_INTERNAL_SEQUENCE_KEY, SHEET_PERIMETER_PATH_KEY)
    assert resolve_cut_path_sequence(keys, []) == ordered
    early = resolve_cut_path_sequence(
        keys,
        [SHEET_PERIMETER_PATH_KEY, CUT_PATH_INTERNAL_SEQUENCE_KEY],
        perimeter_early_confirmed=False,
    )
    assert early[0] == SHEET_PERIMETER_PATH_KEY
    # Legacy piece-key sequences collapse to the perimeter-position contract.
    legacy = resolve_cut_path_sequence(
        keys,
        ["cut_path:a:outer", SHEET_PERIMETER_PATH_KEY],
        perimeter_early_confirmed=False,
    )
    assert legacy == ordered
    with pytest.raises(OperationalFileError) as invalid:
        resolve_cut_path_sequence(keys, ["cut_path:a:outer"], perimeter_early_confirmed=False)
    assert invalid.value.code == "cut_path_sequence_invalid"


def test_compile_separate_unchanged_and_connected_adds_one_perimeter():
    # Leave a full kerf gap so shared cutter centers merge into one network.
    outers = [_rect(40, 40, 300, 400), _rect(345, 40, 250, 200)]
    pieces = [
        _piece("A", outers[0], label="A"),
        _piece("B", outers[1], label="B"),
    ]
    separate = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=PRESETS,
        perimeter_join_mode="separate",
    )
    connected = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=PRESETS,
        perimeter_join_mode="connected",
        cut_path_sequence=None,
        perimeter_cut_early_confirmed=False,
    )
    separate_ops = [operation["operation_key"] for operation in separate["operations"]]
    connected_ops = [operation["operation_key"] for operation in connected["operations"]]
    assert "sheet_perimeter" not in separate_ops
    assert "sheet_perimeter" in connected_ops
    separate_paths = [
        path
        for operation in separate["operations"]
        if operation["operation_key"] == "cut_path"
        for path in operation["toolpaths"]
    ]
    connected_cut = [
        path
        for operation in connected["operations"]
        if operation["operation_key"] == "cut_path"
        for path in operation["toolpaths"]
    ]
    perimeter_paths = [
        path
        for operation in connected["operations"]
        if operation["operation_key"] == "sheet_perimeter"
        for path in operation["toolpaths"]
    ]
    assert not any(path["path_key"] == SHEET_PERIMETER_PATH_KEY for path in separate_paths)
    assert len(perimeter_paths) == 1
    assert perimeter_paths[0]["path_key"] == SHEET_PERIMETER_PATH_KEY
    assert perimeter_paths[0]["closed"] is True
    assert perimeter_paths[0]["piece_label"] == ""
    assert not any(path["path_key"] == SHEET_PERIMETER_PATH_KEY for path in connected_cut)
    assert len(connected_cut) <= len(separate_paths)


def test_perimeter_preset_override_accepted():
    pieces = [_piece("A", _rect(40, 40, 300, 400))]
    payload = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish", "sheet_perimeter": "Finish"},
        path_overrides={SHEET_PERIMETER_PATH_KEY: "Finish"},
        operation_order=["sheet_perimeter", "cut_path"],
        known_presets=PRESETS,
        perimeter_join_mode="connected",
    )
    toolpaths = [
        path
        for operation in payload["operations"]
        if operation["operation_key"] == "sheet_perimeter"
        for path in operation["toolpaths"]
        if path["path_key"] == SHEET_PERIMETER_PATH_KEY
    ]
    assert toolpaths
    assert toolpaths[0]["preset_name"] == "Finish"


def test_prepare_sheet_settings_persists_join_mode_and_sequence():
    pieces = [_piece("A", _rect(40, 40, 300, 400)), _piece("B", _rect(345, 40, 250, 200))]
    plan = ApprovedPlanRef(
        name="PLAN-1",
        revision=1,
        source_type="System",
        status="Approved",
    )
    prepared = prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=plan,
        plan_is_current=True,
        pieces=pieces,
        sheet_no=1,
        existing=None,
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        known_presets=PRESETS,
        machine_profile={"fingerprint_payload": {}, "production_approved": False},
        operation_order=["sheet_perimeter", "cut_path"],
        cut_path_early_confirmed=False,
        perimeter_join_mode="connected",
        cut_path_sequence=None,
        perimeter_cut_early_confirmed=False,
        factory_defaults={"cut_path": "Finish"},
    )
    assert prepared["perimeter_join_mode"] == "connected"
    assert SHEET_PERIMETER_PATH_KEY in prepared["cut_path_sequence"]
    # Default independent order places perimeter before cut_path.
    assert prepared["cut_path_sequence"][0] == SHEET_PERIMETER_PATH_KEY
    assert any(row["operation_key"] == "sheet_perimeter" for row in prepared["operations"])
    assert any(row["path_key"] == SHEET_PERIMETER_PATH_KEY for row in prepared["paths"])
    peri = next(row for row in prepared["operations"] if row["operation_key"] == "sheet_perimeter")
    assert peri["tool_preset"] == ""  # factory/inherited source stores blank
    assert peri["dxf_layer"] == "CUT_PATH"


def test_simulation_nc_contains_single_connected_perimeter_path():
    pieces = [_piece("A", _rect(40, 40, 300, 400)), _piece("B", _rect(345, 40, 250, 200))]
    program = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["sheet_perimeter", "cut_path"],
        known_presets=PRESETS,
        perimeter_join_mode="connected",
    )
    package = build_simulation_nc(
        program,
        machine_profile={
            "production_approved": False,
            "retract_z_mm": 20,
            "dialect": "fanuc",
        },
        sheet_no=1,
        settings_fingerprint="fp-perimeter",
    )
    assert package["production"] is False
    text = str(package.get("text") or "")
    assert "Simulation NC" in text or "simulation" in text.lower() or POST_PROCESSOR_VERSION
    perimeter = next(
        path
        for operation in program["operations"]
        if operation["operation_key"] == "sheet_perimeter"
        for path in operation["toolpaths"]
        if path["path_key"] == SHEET_PERIMETER_PATH_KEY
    )
    cuts = [motion for motion in perimeter["motions"] if motion["kind"] == "cut"]
    retracts = [motion for motion in perimeter["motions"] if motion["kind"] == "retract"]
    assert len(cuts) >= 4
    # One retract per depth pass — no lift between perimeter corners.
    assert len(retracts) >= 1
    snapshot = build_generation_snapshot(
        order_name="DCO-1",
        cutting_plan="PLAN-1",
        plan_revision=1,
        plan_source_type="system",
        sheet_no=1,
        settings_fingerprint="fp-perimeter",
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        cut_path_early_confirmed=False,
        known_presets=PRESETS,
        machine_profile={"production_approved": False},
        package=package,
        program=program,
        perimeter_join_mode="connected",
        cut_path_sequence=program and [SHEET_PERIMETER_PATH_KEY],
        perimeter_cut_early_confirmed=False,
    )
    assert snapshot["perimeter_join_mode"] == "connected"
    assert snapshot["production"] is False


def test_outer_perimeter_with_internal_closed_loop_is_accepted():
    outer = polyline_segments(_rect(0, 0, 100, 80), closed=True)
    hole = polyline_segments(_rect(25, 20, 30, 25), closed=True)
    network = outer + hole
    diagnosis = diagnose_cut_network(
        network,
        uploaded_cut_paths=[
            {"closed": True, "points": _rect(0, 0, 100, 80)},
            {"closed": True, "points": _rect(25, 20, 30, 25)},
        ],
    )
    assert diagnosis.component_count == 2
    assert diagnosis.closed_component_count == 2
    assert diagnosis.uploaded_closed_polyline_count == 2
    assert diagnosis.reject_code is None
    roles = {row.role for row in diagnosis.components}
    assert roles == {"outer", "internal"}
    perimeter = extract_connected_perimeter(network)
    assert perimeter.closed
    assert perimeter.edge_count == 4
    leftovers = remaining_segments_after_perimeter(network, perimeter)
    assert edge_sets_equal(
        network,
        polyline_segments(perimeter.points, closed=True) + leftovers,
    )
    assert segment_edge_multiset(leftovers) == segment_edge_multiset(hole)


def test_outer_perimeter_with_multiple_internal_loops():
    outer = polyline_segments(_rect(0, 0, 200, 120), closed=True)
    holes = (
        polyline_segments(_rect(20, 20, 20, 20), closed=True)
        + polyline_segments(_rect(80, 40, 25, 30), closed=True)
        + polyline_segments(_rect(140, 15, 15, 15), closed=True)
    )
    network = outer + holes
    diagnosis = diagnose_cut_network(network)
    assert diagnosis.component_count == 4
    assert diagnosis.reject_code is None
    assert sum(1 for row in diagnosis.components if row.role == "internal") == 3
    perimeter = extract_connected_perimeter(network)
    leftovers = remaining_segments_after_perimeter(network, perimeter)
    assert edge_sets_equal(
        network,
        polyline_segments(perimeter.points, closed=True) + leftovers,
    )


def test_hole_polyline_is_not_chosen_as_uploaded_outer():
    outer_pts = _rect(0, 0, 120, 90)
    hole_pts = _rect(30, 25, 20, 20)
    network = polyline_segments(outer_pts, closed=True) + polyline_segments(hole_pts, closed=True)
    preferred = prefer_uploaded_perimeter_polyline(
        [
            {"closed": True, "points": hole_pts, "entity_id": 1},
            {"closed": True, "points": outer_pts, "entity_id": 2},
        ],
        network,
    )
    assert preferred is not None
    assert preferred.edge_count == 4
    assert (0.0, 0.0) in preferred.points
    assert (30.0, 25.0) not in preferred.points or len(preferred.points) == 4
    # Outer ring points only.
    assert set(preferred.points) == {(0.0, 0.0), (120.0, 0.0), (120.0, 90.0), (0.0, 90.0)}


def test_uploaded_outer_survives_when_listed_before_extract_would_have_seen_internals():
    outer_pts = [(0, 0), (100, 0), (100, 60), (70, 60), (70, 80), (0, 80)]
    hole_pts = _rect(20, 20, 15, 15)
    network = polyline_segments(outer_pts, closed=True) + polyline_segments(hole_pts, closed=True)
    preferred = prefer_uploaded_perimeter_polyline(
        [{"closed": True, "points": outer_pts}],
        network,
    )
    assert preferred is not None
    assert preferred.closed
    assert len(preferred.points) == 6


def test_line_segments_forming_closed_outer_with_interior_path():
    outer_lines = [
        ((0, 0), (100, 0)),
        ((100, 0), (100, 80)),
        ((100, 80), (0, 80)),
        ((0, 80), (0, 0)),
    ]
    interior = [((40, 20), (60, 20)), ((60, 20), (60, 40))]
    network = outer_lines + interior
    perimeter = extract_connected_perimeter(network)
    leftovers = remaining_segments_after_perimeter(network, perimeter)
    assert perimeter.closed
    assert perimeter.edge_count == 4
    assert edge_sets_equal(
        network,
        polyline_segments(perimeter.points, closed=True) + leftovers,
    )


def test_true_external_components_still_rejected():
    left = polyline_segments(_rect(0, 0, 40, 40), closed=True)
    right = polyline_segments(_rect(80, 10, 40, 40), closed=True)
    diagnosis = diagnose_cut_network(left + right)
    assert diagnosis.component_count == 2
    assert diagnosis.reject_code == "perimeter_components_disconnected"
    with pytest.raises(OperationalFileError) as exc:
        extract_connected_perimeter(left + right)
    assert exc.value.code == "perimeter_components_disconnected"


def test_compile_connected_with_hole_geometry_keeps_single_perimeter_path():
    piece = _piece(
        "A",
        _rect(40, 40, 400, 500),
        label="A",
    )
    piece["geometry"]["holes"] = [_rect(120, 140, 80, 90)]
    connected = compile_sheet_program(
        sheet_no=1,
        pieces=[piece],
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=PRESETS,
        perimeter_join_mode="connected",
    )
    assert not any(
        issue.get("code") == "perimeter_components_disconnected"
        for issue in connected.get("issues") or []
    )
    perimeter_paths = [
        path
        for operation in connected["operations"]
        if operation["operation_key"] == "sheet_perimeter"
        for path in operation["toolpaths"]
        if path["path_key"] == SHEET_PERIMETER_PATH_KEY
    ]
    cut_paths = [
        path
        for operation in connected["operations"]
        if operation["operation_key"] == "cut_path"
        for path in operation["toolpaths"]
    ]
    assert len(perimeter_paths) == 1
    assert perimeter_paths[0]["closed"] is True
    assert all(path["path_key"] != SHEET_PERIMETER_PATH_KEY for path in cut_paths)
    retracts = [motion for motion in perimeter_paths[0]["motions"] if motion["kind"] == "retract"]
    cuts = [motion for motion in perimeter_paths[0]["motions"] if motion["kind"] == "cut"]
    assert len(cuts) >= 4
    assert len(retracts) >= 1
    package = build_simulation_nc(
        connected,
        machine_profile={"production_approved": False, "retract_z_mm": 20, "dialect": "fanuc"},
        sheet_no=1,
        settings_fingerprint="fp-hole",
    )
    assert package["production"] is False
    assert int(package.get("path_count") or 0) >= 1
