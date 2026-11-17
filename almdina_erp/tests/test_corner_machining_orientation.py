"""Symmetric corner doors keep a manufacturing plan when machining is added.

The contour of a square notch is shared by more than one dihedral transform.
An internally generated door is accepted from its recorded orientation.
An imported DXF is accepted only when the toolpath selects that orientation.
"""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting.corner_contour_rotation import (
    orientations_explaining_corner_contour,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    canonical_path,
    liner_toolpath_mm,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import (
    geometry_signature,
    manufacturing_export_rejection,
    manufacturing_failure_sentences,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.domain.cutting.regular_machining_orientation import (
    match_corner_machining_orientation,
)
from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _placed_corner
from almdina_erp.almdina_erp.domain.orders.cut_dimensions import (
    CutDimensionInput,
    calculate_cut_dimensions,
)
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import domain_cutting_engine
from almdina_erp.almdina_erp.services import dxf_import_service as legacy
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError
from almdina_erp.almdina_erp.services.strict_dxf_import_service import parse_production_dxf
from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups

POSITIONS = ("Top Right", "Top Left", "Bottom Right", "Bottom Left")
TYPES = ("L-Shaped Corner", "Clipped Corner")
BIT_MM = 5.0


def _addon(kind):
    if kind == "liner":
        return dict(
            extra_liner=1,
            liner_reference_side="edge_long_left",
            liner_offset_cm=2,
            liner_width_cm=1.5,
            liner_start_cm=0,
            liner_length_cm=0,
        )
    if kind == "groove":
        return dict(
            extra_back_groove=1,
            back_groove_reference_side="edge_width_top",
            back_groove_offset_cm=1,
            back_groove_width_cm=0.8,
            back_groove_start_cm=0,
            back_groove_length_cm=0,
        )
    if kind == "handle":
        return dict(
            extra_recessed_handle_cutout=1,
            recessed_handle_reference_side="edge_long_right",
            recessed_handle_offset_cm=3,
            recessed_handle_width_cm=2,
            recessed_handle_start_cm=2,
            recessed_handle_length_cm=10,
        )
    raise AssertionError(kind)


def _row(piece_type, width, length, cut_x, cut_y, position, **extra):
    return dict(
        piece_type=piece_type,
        width_cm=width,
        length_cm=length,
        qty=1,
        clipped_corner_position=position,
        clipped_corner_width_cm=cut_x,
        clipped_corner_length_cm=cut_y,
        allow_rotation=1,
        piece_instance_id="corner-orientation",
        **extra,
    )


def _search(row, *, mirror=False):
    pieces = expand_piece_groups([row])
    return opt.smart_search(
        pieces,
        100,
        100,
        0.3,
        time_limit_sec=0.4,
        machine_type="CNC Router",
        mirroring_allowed=mirror,
    )


def _placed(plan):
    return [piece for sheet in plan.get("sheets") or [] for piece in sheet.get("pieces") or []]


@pytest.mark.parametrize("piece_type", TYPES)
@pytest.mark.parametrize(
    "width,length,cut_x,cut_y",
    [(40, 40, 10, 10), (40, 60, 10, 18), (40, 40, 10, 15)],
)
@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("addon", ("liner", "groove", "handle"))
def test_corner_with_one_addon_keeps_a_manufacturing_plan(
    piece_type, width, length, cut_x, cut_y, position, addon
):
    plan = _search(_row(piece_type, width, length, cut_x, cut_y, position, **_addon(addon)))
    placed = _placed(plan)
    assert len(placed) == 1
    assert plan["unplaced"] == []
    assert (plan.get("smart_search") or {}).get("portfolio", {}).get("rejections") == {}
    assert manufacturing_export_rejection(plan) == ""
    assert placed[0]["w"] == pytest.approx(width)
    assert placed[0]["h"] == pytest.approx(length)


def test_several_addons_and_connected_liners_stay_on_one_plan():
    specs = {
        "extra_liner": 1,
        "liner_reference_side": "edge_width_top",
        "liner_offset_cm": 2,
        "liner_width_cm": 1.5,
        "liner_start_cm": 2,
        "liner_length_cm": 0,
        "liner_specs_json": json.dumps({
            "width_cm": 1.5,
            "liners": [
                {"id": "liner_1", "side": "edge_width_top", "offset_cm": 2, "start_cm": 2, "length_cm": 0},
                {"id": "liner_2", "side": "edge_long_left", "offset_cm": 2, "start_cm": 2, "length_cm": 0},
            ],
        }),
    }
    row = _row(
        "L-Shaped Corner", 40, 40, 10, 10, "Top Right",
        extra_back_groove=1,
        back_groove_reference_side="edge_long_right",
        back_groove_offset_cm=1.2,
        back_groove_width_cm=0.6,
        back_groove_start_cm=1,
        back_groove_length_cm=20,
        **specs,
    )
    plan = _search(row)
    assert len(_placed(plan)) == 1
    assert manufacturing_export_rejection(plan) == ""
    # The notch shortens the top edge, so these two liners are not one L.
    # The connected-L join on a full rectangular corner stays one path.
    paths = __import__(
        "almdina_erp.almdina_erp.domain.cutting.liner_geometry",
        fromlist=["merged_liner_toolpaths_mm"],
    ).merged_liner_toolpaths_mm(
        LinerPiece("Regular", 40, 60),
        json.loads(row["liner_specs_json"])["liners"],
        1.5,
        BIT_MM,
    )
    assert len(paths) == 1
    assert len(paths[0]) >= 3


@pytest.mark.parametrize("mirrored", (False, True))
@pytest.mark.parametrize("turns", (0, 1, 2, 3))
@pytest.mark.parametrize("piece_type", TYPES)
def test_recorded_orientation_is_accepted_for_every_turn_and_mirror(piece_type, mirrored, turns):
    source = expand_piece_groups([
        _row(piece_type, 40, 40, 10, 10, "Top Right", **_addon("liner"))
    ])[0]
    placed = _placed_corner(source, x_cm=1, y_cm=2, mirrored=mirrored, turns=turns)
    plan = {"sheets": [{"pieces": [placed]}], "unplaced": []}
    assert manufacturing_export_rejection(plan) == ""
    local = liner_toolpath_mm(
        LinerPiece(piece_type, 40, 40, "Top Right", 10, 10),
        "edge_long_left",
        2,
        1.5,
        BIT_MM,
    )
    width_mm = 400.0
    height_mm = 400.0
    moved = [
        transform_point(point, mirrored=mirrored, quarter_turns=turns, width=width_mm, height=height_mm)
        for point in local
    ]
    recovered = canonical_path(
        moved,
        mirrored=mirrored,
        quarter_turns=turns,
        width_mm=width_mm,
        height_mm=height_mm,
    )
    assert recovered == pytest.approx(local)


def test_a_recorded_orientation_that_does_not_draw_the_outline_stays_rejected():
    plan = _search(_row("L-Shaped Corner", 40, 40, 10, 10, "Top Right", **_addon("liner")))
    piece = _placed(plan)[0]
    piece["placement_outline_cm"] = material_outline_cm(piece)
    piece["corner_rotation_quarter_turns"] = 1
    piece["corner_mirrored"] = 0
    assert manufacturing_export_rejection(plan) == "corner_machining_orientation_ambiguous"


def test_toolpaths_select_one_symmetric_orientation_and_reject_two():
    outer = [(0, 0), (300, 0), (300, 100), (400, 100), (400, 400), (0, 400)]
    piece = LinerPiece("L-Shaped Corner", 40, 40, "Top Right", 10, 10)
    path = liner_toolpath_mm(piece, "edge_long_left", 2, 1.5, BIT_MM)
    candidates = orientations_explaining_corner_contour(
        outer,
        piece_type="L-Shaped Corner",
        position="Top Right",
        width_cm=40,
        length_cm=40,
        cut_width_cm=10,
        cut_length_cm=10,
    )
    assert len({item[2] for item in candidates}) > 1
    host = {"x": 0, "y": 0, "w": 40, "h": 40, "id": 1}
    proven = match_corner_machining_orientation(
        piece=piece,
        host=host,
        outer=outer,
        sheet_pieces=[host],
        overlay_paths={"liner": path},
        settings={"liner": {
            "enabled": True, "side": "edge_long_left", "offset_cm": 2,
            "width_cm": 1.5, "start_cm": 0, "length_cm": 0,
        }},
        candidates=candidates,
        cutter_diameter_mm=BIT_MM,
    )
    assert proven.reason == "unique"
    assert (proven.mirrored, proven.quarter_turns) == (False, 0)
    opposite = match_corner_machining_orientation(
        piece=piece,
        host=host,
        outer=outer,
        sheet_pieces=[host],
        overlay_paths={"liner": path},
        settings={"liner": {
            "enabled": True, "side": "edge_long_right", "offset_cm": 2,
            "width_cm": 1.5, "start_cm": 0, "length_cm": 0,
        }},
        candidates=candidates,
        cutter_diameter_mm=BIT_MM,
    )
    assert opposite.reason != "unique"


@pytest.mark.parametrize("deduct", (False, True))
def test_cut_size_follows_edge_deduction_and_the_plan_survives(deduct):
    finished = calculate_cut_dimensions(CutDimensionInput(
        final_width_cm=40,
        final_length_cm=40,
        edge_long_right=1,
        edge_long_left=1,
        edge_width_top=1,
        edge_width_bottom=1,
        long_edge_thickness_mm=1,
        width_edge_thickness_mm=1,
        deduct_edge_thickness=deduct,
    ))
    assert finished.cut_width_cm == pytest.approx(39.8 if deduct else 40)
    assert finished.cut_length_cm == pytest.approx(39.8 if deduct else 40)
    row = _row(
        "Clipped Corner",
        float(finished.cut_width_cm),
        float(finished.cut_length_cm),
        10,
        10,
        "Top Left",
        edge_long_right=1,
        edge_long_left=1,
        edge_width_top=1,
        edge_width_bottom=1,
        edge_long_thickness_mm=1,
        edge_width_thickness_mm=1,
        edge_type="PVC",
        **_addon("groove"),
    )
    plan = _search(row)
    placed = _placed(plan)
    assert len(placed) == 1
    assert placed[0]["w"] == pytest.approx(float(finished.cut_width_cm))
    assert placed[0]["h"] == pytest.approx(float(finished.cut_length_cm))
    outline = material_outline_cm(placed[0])
    xs = [point[0] for point in outline]
    ys = [point[1] for point in outline]
    assert max(xs) - min(xs) == pytest.approx(float(finished.cut_width_cm))
    assert max(ys) - min(ys) == pytest.approx(float(finished.cut_length_cm))
    saved = json.loads(json.dumps(plan))
    assert geometry_signature(saved) == geometry_signature(plan)
    assert manufacturing_export_rejection(saved) == ""


def test_failure_sentences_list_each_recorded_reason_once():
    assert manufacturing_failure_sentences({}) == (
        "No manufacturing-valid cutting plan was found.",
    )
    assert manufacturing_failure_sentences({
        "corner_machining_orientation_ambiguous": 4,
    }) == (
        "The corner door orientation could not be proven, so no manufacturing-valid cutting plan was found.",
    )


def _order(piece_type, side):
    row = SimpleNamespace(
        name="row-1",
        piece_instance_id="corner-orientation:1",
        piece_type=piece_type,
        width_cm=40,
        length_cm=40,
        cut_width_cm=40,
        cut_length_cm=40,
        qty=1,
        allow_rotation=1,
        clipped_corner_position="Top Right",
        clipped_corner_width_cm=10,
        clipped_corner_length_cm=10,
        default_edge_type="",
        extra_liner=1,
        extra_back_groove=0,
        extra_recessed_handle_cutout=0,
        extra_double=0,
        extra_full_door_double=0,
        liner_reference_side=side,
        liner_offset_cm=2,
        liner_width_cm=1.5,
        liner_start_cm=0,
        liner_length_cm=0,
        liner_specs_json="",
        deduct_edge_thickness=0,
    )
    return SimpleNamespace(
        name="CORNER-ORIENTATION",
        trim_margin_mm=0,
        board_width_cm=100,
        board_length_cm=100,
        full_board_width_mm=1000,
        full_board_length_mm=1000,
        kerf_mm=3,
        default_edge_type="",
        deduct_edge_thickness=False,
        allow_piece_mirroring=False,
        pieces=[row],
    )


@pytest.mark.parametrize("piece_type", TYPES)
def test_exported_corner_dxf_reimports_on_the_ordered_side(piece_type, tmp_path):
    rows = [_row(piece_type, 40, 40, 10, 10, "Top Right", **_addon("liner"))]
    rows[0]["piece_instance_id"] = "corner-orientation"
    outcome = optimize_order_plan(OptimizeOrderPlanCommand(
        engine_version="corner-orientation",
        input_fingerprint="corner-orientation",
        board=BoardGeometry(100, 100, 0, 0.3),
        optimizer=OptimizerOptions("smart", "CNC Router", 0.4, 20, 30, 30, 0.09),
        piece_rows=tuple(rows),
    ), engine=domain_cutting_engine)
    snapshot = deepcopy(outcome.snapshot)
    assert snapshot["validation"]["is_valid"]
    assert manufacturing_export_rejection(snapshot) == ""
    placed = _placed(snapshot)[0]
    snapshot["liner_tool_diameter_mm"] = BIT_MM
    snapshot["full_board_width_cm"] = 100
    snapshot["full_board_length_cm"] = 100
    saved = tmp_path / "plan.json"
    saved.write_text(json.dumps(snapshot))
    reloaded = json.loads(saved.read_text())
    assert geometry_signature(reloaded) == geometry_signature(snapshot)
    dxf = export_real_js(reloaded, tmp_path)
    order = _order(piece_type, "edge_long_left")
    with patch.object(legacy.frappe, "get_site_path", return_value=str(dxf)):
        imported = parse_production_dxf(
            "/private/files/corner.dxf",
            order,
            settings=PlanSettings("smart", "CNC Router", 0.4, 3, 0, deduct_edge_thickness=False),
            tool_diameters={"liner_tool_diameter_mm": BIT_MM},
        )
    imported_piece = _placed(imported)[0]
    assert imported_piece["corner_rotation_quarter_turns"] == int(
        placed.get("corner_rotation_quarter_turns") or 0
    )
    assert int(imported_piece.get("corner_mirrored") or 0) == int(bool(placed.get("corner_mirrored")))
    liners = [item for item in imported_piece.get("overlays") or [] if item.get("kind") == "liner"]
    assert len(liners) == 1
    wrong = _order(piece_type, "edge_long_right")
    with patch.object(legacy.frappe, "get_site_path", return_value=str(dxf)):
        with pytest.raises(DxfImportError) as caught:
            parse_production_dxf(
                "/private/files/corner.dxf",
                wrong,
                settings=PlanSettings("smart", "CNC Router", 0.4, 3, 0, deduct_edge_thickness=False),
                tool_diameters={"liner_tool_diameter_mm": BIT_MM},
            )
    assert caught.value.issues
