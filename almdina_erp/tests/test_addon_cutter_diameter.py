"""A cutter wider than its add-on blocks the plan, except an edge rear groove.

The edge case keeps the requested groove width and shifts the cutter center
outward. Preview, DXF comparison, and NC use that same center.
"""

from __future__ import annotations

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.addon_cutter_rules import (
    as_dxf_issues,
    assess_piece_addons,
    layout_conflicts,
    resolve_exceptional_groove_layout,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import ADDON_CUTTER_REJECTED
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    compare_overlay_path,
    generate_toolpath,
)
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
    present_issue,
    render_error_cards_html,
)
from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.tests.test_cnc_toolpath_coverage import (
    PRESETS,
    _compile,
    _expected_mill,
    _mill_piece,
    _paths,
    _raw,
    _same_sequence,
    _snapshot,
)


DIAMETERS = {
    "liner_tool_diameter_mm": 8,
    "handle_recess_tool_diameter_mm": 8,
    "rear_groove_tool_diameter_mm": 8,
}


def _door(**extra):
    piece = {
        "piece_type": "Regular",
        "label": "7.1",
        "source_piece_no": 7,
        "copy_no": 1,
        "width_cm": 40,
        "length_cm": 80,
        "w": 40,
        "h": 80,
        "x": 0,
        "y": 0,
        "id": "door-7",
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    piece.update(extra)
    return piece


def _ys(path):
    return {round(point[1], 3) for point in path}


def test_equal_or_narrower_cutter_keeps_the_center_inside_the_strip():
    piece = LinerPiece("Regular", 40, 80)
    equal = generate_toolpath(
        kind="liner",
        piece=piece,
        reference_side="edge_width_top",
        offset_cm=0,
        width_cm=0.5,
        start_cm=0,
        length_cm=0,
        cutter_diameter_mm=5,
    )
    narrower = generate_toolpath(
        kind="back_groove",
        piece=piece,
        reference_side="edge_width_top",
        offset_cm=0,
        width_cm=1.8,
        start_cm=0,
        length_cm=0,
        cutter_diameter_mm=5,
    )
    assert _ys(equal) == {2.5}
    assert min(_ys(narrower)) >= 2.5 - 0.001


def test_liner_and_handle_and_inset_groove_reject_a_wider_cutter():
    liner = assess_piece_addons(_door(
        extra_liner=1,
        liner_reference_side="edge_width_top",
        liner_offset_cm=0,
        liner_width_cm=0.5,
    ), DIAMETERS)
    handle = assess_piece_addons(_door(
        extra_recessed_handle_cutout=1,
        recessed_handle_reference_side="edge_width_bottom",
        recessed_handle_offset_cm=1,
        recessed_handle_width_cm=0.5,
    ), DIAMETERS)
    inset = assess_piece_addons(_door(
        extra_back_groove=1,
        back_groove_reference_side="edge_width_top",
        back_groove_offset_cm=1,
        back_groove_width_cm=0.5,
    ), DIAMETERS)
    assert [item["code"] for item in liner] == ["liner_narrower_than_cutter"]
    assert [item["code"] for item in handle] == ["liner_narrower_than_cutter"]
    assert [item["code"] for item in inset] == ["liner_narrower_than_cutter"]
    assert liner[0]["width_mm"] == 5
    assert liner[0]["diameter_mm"] == 8
    assert liner[0]["source_piece_no"] == 7


def test_absent_addons_and_special_pieces_are_not_checked():
    absent = assess_piece_addons(_door(
        extra_back_groove=0,
        back_groove_reference_side="edge_width_top",
        back_groove_width_cm=0.5,
    ), DIAMETERS)
    special = assess_piece_addons(_door(piece_type="Special", extra_liner=1, liner_width_cm=0.1), DIAMETERS)
    assert absent == []
    assert special == []


def test_edge_rear_groove_shifts_outward_and_keeps_the_requested_width():
    piece = LinerPiece("Regular", 40, 80)
    path = generate_toolpath(
        kind="back_groove",
        piece=piece,
        reference_side="edge_width_top",
        offset_cm=0,
        width_cm=0.5,
        start_cm=0,
        length_cm=0,
        cutter_diameter_mm=8,
    )
    assert _ys(path) == {1.0}
    assert min(point[0] for point in path) < 0
    assert max(point[0] for point in path) > 400
    measurement = compare_overlay_path(
        path,
        piece,
        "back_groove",
        "edge_width_top",
        0,
        0.5,
        8,
    )
    assert measurement.ok, measurement
    unshifted = [(point[0], 2.5) for point in path]
    rejected = compare_overlay_path(
        unshifted,
        piece,
        "back_groove",
        "edge_width_top",
        0,
        0.5,
        8,
    )
    assert rejected.ok is False


def test_partial_edge_groove_with_a_wider_cutter_is_unsafe():
    piece = LinerPiece("Regular", 40, 80)
    try:
        generate_toolpath(
            kind="back_groove",
            piece=piece,
            reference_side="edge_width_top",
            offset_cm=0,
            width_cm=0.5,
            start_cm=5,
            length_cm=10,
            cutter_diameter_mm=8,
        )
    except LinerGeometryError as exc:
        assert exc.code == "rear_groove_oversize_unsafe"
    else:
        raise AssertionError("partial oversize groove was accepted")


def test_rotation_and_mirror_keep_the_center_one_millimetre_inside():
    piece = LinerPiece("Regular", 40, 80)
    local = generate_toolpath(
        kind="back_groove",
        piece=piece,
        reference_side="edge_width_top",
        offset_cm=0,
        width_cm=0.5,
        start_cm=0,
        length_cm=0,
        cutter_diameter_mm=8,
    )
    turned = [
        transform_point(point, mirrored=False, quarter_turns=1, width=400, height=800)
        for point in local
    ]
    mirrored = [
        transform_point(point, mirrored=True, quarter_turns=0, width=400, height=800)
        for point in local
    ]
    assert {round(point[0], 3) for point in turned} == {799.0}
    assert {round(point[1], 3) for point in mirrored} == {1.0}


def test_neighbor_conflict_is_repaired_only_along_the_groove():
    host = _door(
        id="host",
        label="4.1",
        source_piece_no=4,
        extra_back_groove=1,
        back_groove_reference_side="edge_long_right",
        back_groove_offset_cm=0,
        back_groove_width_cm=0.5,
        x=0,
        y=0,
        w=40,
        h=50,
        width_cm=40,
        length_cm=50,
    )
    neighbor = _door(
        id="neighbor",
        label="5.1",
        source_piece_no=5,
        x=40.2,
        y=0,
        w=20,
        h=50,
        width_cm=20,
        length_cm=50,
    )
    bystander = _door(
        id="bystander",
        label="6.1",
        source_piece_no=6,
        x=0,
        y=50.2,
        w=40,
        h=10,
        width_cm=40,
        length_cm=10,
    )
    clear = _door(
        id="clear",
        label="9.1",
        source_piece_no=9,
        x=80,
        y=0,
        w=20,
        h=20,
        width_cm=20,
        length_cm=20,
    )
    plan = {
        "sheets": [{
            "sheet_no": 1,
            "w": 120,
            "h": 80,
            "pieces": [host, neighbor, bystander, clear],
        }],
    }
    conflicts = layout_conflicts(plan, DIAMETERS)
    assert conflicts
    assert conflicts[0]["code"] == "rear_groove_neighbor_conflict"
    assert conflicts[0]["neighbor_piece_no"] == 5
    repaired, remaining = resolve_exceptional_groove_layout(plan, DIAMETERS, kerf_cm=0.2)
    assert remaining == []
    placed = {piece["id"]: piece for piece in repaired["sheets"][0]["pieces"]}
    assert placed["neighbor"]["x"] > neighbor["x"]
    assert placed["host"]["x"] == host["x"]
    assert placed["host"]["y"] == host["y"]
    assert placed["bystander"]["y"] > bystander["y"]
    assert placed["clear"]["x"] == clear["x"]
    assert placed["clear"]["y"] == clear["y"]
    assert layout_conflicts(repaired, DIAMETERS) == []


def test_cards_name_the_door_addon_width_and_correction():
    findings = assess_piece_addons(_door(
        extra_liner=1,
        liner_reference_side="edge_width_top",
        liner_width_cm=0.5,
    ), DIAMETERS)
    findings.extend(assess_piece_addons(_door(
        label="8.1",
        source_piece_no=8,
        extra_recessed_handle_cutout=1,
        recessed_handle_reference_side="edge_width_bottom",
        recessed_handle_width_cm=0.4,
    ), DIAMETERS))
    issues = as_dxf_issues(findings)
    assert all(item.code == ADDON_CUTTER_REJECTED for item in issues)
    html = render_error_cards_html(issues, context="save")
    assert "ما المشكلة؟" in html
    assert "أين المشكلة؟" in html
    assert "ماذا أفعل؟" in html
    assert "7" in html and "8" in html
    assert "5" in html and "8" in html
    presented = present_issue(issues[0])
    assert "5" in presented.problem
    assert presented.action


def test_nc_and_preview_use_the_same_shifted_rear_groove():
    spec = {
        "side": "edge_width_top",
        "offset_cm": 0,
        "width_cm": 0.5,
        "start_cm": 0,
        "length_cm": 0,
    }
    piece = _mill_piece(
        extra_back_groove=1,
        back_groove_reference_side=spec["side"],
        back_groove_offset_cm=spec["offset_cm"],
        back_groove_width_cm=spec["width_cm"],
    )
    program = _compile(
        [piece],
        snapshot=_snapshot(rear_groove_tool_diameter_mm=8, kerf_mm=5),
        operation_presets={"back_groove": "Wide"},
    )
    paths = _paths(program, "back_groove")
    assert program["ready"] is True, program["issues"]
    assert len(paths) == 1
    assert _same_sequence(paths[0]["points"], _expected_mill(piece, "back_groove", spec, diameter=8))


def test_nc_rejects_a_selected_profile_wider_than_the_liner():
    known = dict(PRESETS)
    known["TooWide"] = _raw(preset_name="TooWide", tool_diameter_mm=12)
    piece = _mill_piece(
        extra_liner=1,
        liner_reference_side="edge_width_top",
        liner_offset_cm=0,
        liner_width_cm=0.5,
    )
    program = compile_sheet_program(
        sheet_no=1,
        pieces=[piece],
        snapshot=_snapshot(liner_tool_diameter_mm=12, kerf_mm=5),
        operation_presets={
            "cut_path": "Finish",
            "liner": "TooWide",
            "back_groove": "Finish",
            "recessed_handle_cutout": "Finish",
        },
        path_overrides={},
        operation_order=["liner", "recessed_handle_cutout", "back_groove", "cut_path"],
        known_presets=known,
        manufacturing_mode="generated",
    )
    paths = _paths(program, "liner")
    assert paths
    assert "liner_narrower_than_cutter" in paths[0]["issues"]
    assert paths[0]["motions"] == []
