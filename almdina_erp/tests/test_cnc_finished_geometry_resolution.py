"""Finished geometry resolution for CNC without inventing unsupported shapes."""

from __future__ import annotations

import json
import math
from pathlib import Path

from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.domain.cutting.finished_piece_geometry import (
    placed_source_for_finished_geometry,
    resolve_finished_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import serialize_geometry_mm
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.domain.cutting.primitives import (
    expand_piece_groups,
    make_placed_piece,
)


APP_ROOT = Path(__file__).resolve().parents[1]
REPO = APP_ROOT / "almdina_erp" / "infrastructure" / "frappe" / "cnc_operational_file_repository.py"
UX = APP_ROOT / "public" / "js" / "door_cutting_order" / "cnc" / "door_cutting_order_operational_files_ux.js"


def _raw(**overrides):
    values = {
        "preset_name": "Finish",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 5,
        "final_depth_mm": 18.5,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 10200,
        "plunge_rate_mm_min": 1800,
        "pass_depth_mm": None,
        "enabled": True,
    }
    values.update(overrides)
    return values


PRESETS = {
    "Finish": _raw(),
    "Kerf3": _raw(preset_name="Kerf3", tool_diameter_mm=3),
}


def _snapshot(**extra):
    snapshot = {
        "kerf_mm": 5,
        "full_board_width_cm": 122,
        "full_board_length_cm": 244,
        "sheets": [
            {
                "sheet_no": 1,
                "full_width_cm": 122,
                "full_length_cm": 244,
                "usable_width_cm": 122,
                "usable_length_cm": 244,
                "applied_trim_width_cm": 0,
                "applied_trim_length_cm": 0,
                "pieces": [],
            }
        ],
    }
    snapshot.update(extra)
    return snapshot


def _compile(pieces, *, snapshot=None, presets=None, kerf_mm=5):
    snap = snapshot or _snapshot(kerf_mm=kerf_mm)
    return compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=snap,
        operation_presets={"cut_path": "Finish" if presets is None else next(iter(presets))},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=presets or PRESETS,
        cut_path_early_confirmed=False,
    )


def test_system_plan_without_stored_geometry_rebuilds_regular_and_corners():
    regular = {
        "piece_instance_id": "r1",
        "label": "1.1",
        "sheet_no": 1,
        "piece_type": "Regular",
        "width_mm": 400,
        "height_mm": 600,
        "x_mm": 10,
        "y_mm": 20,
        "original_width_cm": 40,
        "original_length_cm": 60,
        "rotated": 0,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    corner = {
        "piece_instance_id": "l1",
        "label": "2.1",
        "sheet_no": 1,
        "piece_type": "L-Shaped Corner",
        "width_mm": 500,
        "height_mm": 700,
        "x_mm": 50,
        "y_mm": 80,
        "original_width_cm": 50,
        "original_length_cm": 70,
        "rotated": 1,
        "clipped_corner_position": "Top Right",
        "clipped_corner_width_cm": 12,
        "clipped_corner_length_cm": 18,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    clipped = dict(corner, piece_instance_id="c1", label="3.1", piece_type="Clipped Corner", rotated=0)
    for piece in (regular, corner, clipped):
        geometry = resolve_finished_geometry_mm(piece=piece, stored_piece={})
        assert geometry is not None
        assert geometry["unit"] == "mm"
        assert geometry["coordinate_space"] == "usable_sheet"
        assert len(geometry["outer"]) >= 4
        piece["geometry"] = None  # force rebuild path inside compile
    payload = _compile([regular, corner, clipped], presets={"Finish": _raw(tool_diameter_mm=5)})
    assert not any(issue["code"] == "finished_geometry_missing" for issue in payload["issues"])
    assert any(path.get("points") for path in payload["operations"][0]["toolpaths"])


def test_explicit_geometry_is_preferred_and_keeps_dimensions():
    outer = [[10.0, 20.0], [110.0, 20.0], [110.0, 70.0], [10.0, 70.0]]
    stored = serialize_geometry_mm(PartGeometry(outer=tuple(tuple(p) for p in outer), holes=()))
    piece = {
        "piece_instance_id": "r1",
        "label": "1.1",
        "sheet_no": 1,
        "piece_type": "Regular",
        "width_mm": 100,
        "height_mm": 50,
        "x_mm": 10,
        "y_mm": 20,
        "original_width_cm": 10,
        "original_length_cm": 5,
        "geometry": stored,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    resolved = resolve_finished_geometry_mm(stored_geometry=stored, piece=piece)
    assert resolved["outer"] == outer
    width = max(p[0] for p in resolved["outer"]) - min(p[0] for p in resolved["outer"])
    height = max(p[1] for p in resolved["outer"]) - min(p[1] for p in resolved["outer"])
    assert math.isclose(width, 100.0)
    assert math.isclose(height, 50.0)


def test_special_without_exact_polygon_stays_rejected():
    piece = {
        "piece_instance_id": "s1",
        "label": "9.1",
        "sheet_no": 1,
        "piece_type": "Special",
        "width_mm": 300,
        "height_mm": 400,
        "x_mm": 0,
        "y_mm": 0,
        "original_width_cm": 30,
        "original_length_cm": 40,
        "special_shape_geometry_json": "",
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    assert resolve_finished_geometry_mm(piece=piece) is None
    payload = _compile([piece])
    assert any(issue["code"] == "finished_geometry_missing" for issue in payload["issues"])
    assert payload["geometry_ready"] is False


def test_special_with_exact_polygon_and_glass_hole_rebuild():
    special_json = json.dumps(
        {
            "version": 1,
            "kind": "polygon",
            "units": "cm",
            "exact": True,
            "blank_width_cm": 40,
            "blank_length_cm": 60,
            "points": [[0, 0], [40, 0], [40, 60], [10, 60], [0, 40]],
        }
    )
    special = {
        "piece_instance_id": "s1",
        "label": "4.1",
        "sheet_no": 1,
        "piece_type": "Special",
        "width_mm": 400,
        "height_mm": 600,
        "x_mm": 5,
        "y_mm": 15,
        "original_width_cm": 40,
        "original_length_cm": 60,
        "special_shape_geometry_json": special_json,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    glass = {
        "piece_instance_id": "g1",
        "label": "5.1",
        "sheet_no": 1,
        "piece_type": "Glass",
        "width_mm": 800,
        "height_mm": 1000,
        "x_mm": 0,
        "y_mm": 0,
        "original_width_cm": 80,
        "original_length_cm": 100,
        "glass_margin_mm": 100,
        "glass_hole_local_mm": [[100, 100], [700, 100], [700, 900], [100, 900]],
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    nested = {
        "piece_instance_id": "n1",
        "label": "5.2",
        "sheet_no": 1,
        "piece_type": "Regular",
        "width_mm": 200,
        "height_mm": 300,
        "x_mm": 150,
        "y_mm": 200,
        "original_width_cm": 20,
        "original_length_cm": 30,
        "glass_host_piece_id": 5,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    for piece in (special, glass, nested):
        assert resolve_finished_geometry_mm(piece=piece, stored_piece=piece) is not None
        piece["geometry"] = None
    glass_geometry = resolve_finished_geometry_mm(piece=glass, stored_piece=glass)
    assert glass_geometry["holes"]
    payload = _compile([special, glass, nested], presets={"Finish": _raw(tool_diameter_mm=5)})
    assert not any(issue["code"] == "finished_geometry_missing" for issue in payload["issues"])


def test_piece_id_mismatch_falls_back_to_instance_fields_in_repository_contract():
    source = REPO.read_text(encoding="utf-8")
    assert "stored_by_instance" in source
    assert "resolve_finished_geometry_mm" in source
    assert "special_shape_geometry_json" in source


def test_ui_dedupes_finished_geometry_missing_and_hides_path_keys_by_default():
    panel = UX.read_text(encoding="utf-8")
    assert "uniqueIssues" in panel
    assert "Cut paths for {0} pieces could not be prepared because finished geometry is missing from the approved plan." in panel
    assert "dco-cnc-program__issue-group" in panel
    assert 'item.code !== "finished_geometry_missing"' in panel


def test_many_missing_pieces_do_not_duplicate_board_and_path_counts_in_compile_payload():
    pieces = []
    for index in range(8):
        pieces.append(
            {
                "piece_instance_id": f"p{index}",
                "label": f"{index + 1}.1",
                "sheet_no": 1,
                "piece_type": "Special",
                "width_mm": 300,
                "height_mm": 400,
                "x_mm": index * 10,
                "y_mm": 0,
                "original_width_cm": 30,
                "original_length_cm": 40,
                "special_shape_geometry_json": "",
                "extra_liner": 0,
                "extra_back_groove": 0,
                "extra_recessed_handle_cutout": 0,
            }
        )
    payload = _compile(pieces)
    missing = [issue for issue in payload["issues"] if issue["code"] == "finished_geometry_missing"]
    # One board-level blocked path per piece outer; no invented geometry.
    assert len(missing) == 8
    assert payload["geometry_ready"] is False


def _special_json(*, blank_w=40.0, blank_h=60.0, points=None, exact=True):
    return json.dumps(
        {
            "version": 1,
            "kind": "polygon",
            "units": "cm",
            "exact": exact,
            "blank_width_cm": blank_w,
            "blank_length_cm": blank_h,
            "points": points
            or [[0, 0], [blank_w, 0], [blank_w, blank_h], [10, blank_h], [0, 40]],
        }
    )


def _arc_approximated_points(blank_w=40.0, blank_h=60.0, samples=12):
    """Simple closed polyline with a semicircle top that spans the blank."""

    radius = blank_w / 2.0
    cy = blank_h - radius
    points = [[0.0, 0.0], [blank_w, 0.0], [blank_w, cy]]
    for index in range(samples + 1):
        # Walk the top semicircle from right (0) to left (pi).
        angle = math.pi * index / samples
        points.append(
            [
                round(radius + radius * math.cos(angle), 3),
                round(cy + radius * math.sin(angle), 3),
            ]
        )
    points.append([0.0, cy])
    return points


def _historical_cut_vs_finished_special(**overrides):
    """Approved System shape where original_* wrongly stored cut nesting size."""

    special_json = _special_json()
    piece = {
        "piece_instance_id": "s-hist",
        "label": "4.1",
        "sheet_no": 1,
        "piece_type": "Special",
        "width_mm": 395.0,
        "height_mm": 595.0,
        "x_mm": 50.0,
        "y_mm": 100.0,
        "original_width_cm": 39.5,
        "original_length_cm": 59.5,
        "special_shape_geometry_json": special_json,
        "rotated": 0,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    stored = {
        "x": 5.0,
        "y": 10.0,
        "w": 39.5,
        "h": 59.5,
        "original_w": 39.5,
        "original_h": 59.5,
        "piece_type": "Special",
        "special_shape_geometry_json": special_json,
        "rotated": 0,
        "label": "4.1",
    }
    piece.update(overrides)
    return piece, stored


def test_historical_system_special_recovers_blank_when_original_was_cut_size():
    piece, stored = _historical_cut_vs_finished_special()
    geometry = resolve_finished_geometry_mm(piece=piece, stored_piece=stored)
    assert geometry is not None
    assert geometry["unit"] == "mm"
    outer = geometry["outer"]
    assert len(outer) == 5
    xs = [point[0] for point in outer]
    ys = [point[1] for point in outer]
    assert math.isclose(min(xs), 50.0)
    assert math.isclose(min(ys), 100.0)
    assert math.isclose(max(xs) - min(xs), 395.0)
    assert math.isclose(max(ys) - min(ys), 595.0)
    # Not a substituted axis-aligned rectangle of the cut AABB.
    assert len({(round(x, 3), round(y, 3)) for x, y in outer}) == 5
    piece["geometry"] = None
    payload = _compile([piece], snapshot=_snapshot(sheets=[{
        "sheet_no": 1,
        "full_width_cm": 122,
        "full_length_cm": 244,
        "usable_width_cm": 122,
        "usable_length_cm": 244,
        "applied_trim_width_cm": 0,
        "applied_trim_length_cm": 0,
        "pieces": [stored],
    }]))
    assert not any(issue["code"] == "finished_geometry_missing" for issue in payload["issues"])
    assert payload["geometry_ready"] is True
    cut_ops = [op for op in payload["operations"] if op.get("operation_key") == "cut_path"]
    assert cut_ops
    toolpaths = cut_ops[0]["toolpaths"]
    assert any(path.get("points") for path in toolpaths)


def test_special_with_arcs_holes_addons_rotation_and_mixed_board():
    arc_json = _special_json(points=_arc_approximated_points())
    special = {
        "piece_instance_id": "s-arc",
        "label": "4.1",
        "sheet_no": 1,
        "piece_type": "Special",
        "width_mm": 395.0,
        "height_mm": 595.0,
        "x_mm": 20.0,
        "y_mm": 30.0,
        "original_width_cm": 39.5,
        "original_length_cm": 59.5,
        "special_shape_geometry_json": arc_json,
        "rotated": 1,
        "extra_liner": 1,
        "liner_reference_side": "long_right",
        "liner_offset_cm": 2,
        "liner_width_cm": 1.5,
        "liner_start_cm": 5,
        "liner_length_cm": 20,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    # Rotated placement swaps the cut viewport; blank identity stays finished.
    stored_special = {
        "x": 2.0,
        "y": 3.0,
        "w": 59.5,
        "h": 39.5,
        "original_w": 39.5,
        "original_h": 59.5,
        "piece_type": "Special",
        "special_shape_geometry_json": arc_json,
        "rotated": 1,
        "extra_liner": 1,
        "liner_reference_side": "long_right",
        "liner_offset_cm": 2,
        "liner_width_cm": 1.5,
        "liner_start_cm": 5,
        "liner_length_cm": 20,
    }
    special["width_mm"] = 595.0
    special["height_mm"] = 395.0
    glass = {
        "piece_instance_id": "g1",
        "label": "5.1",
        "sheet_no": 1,
        "piece_type": "Glass",
        "width_mm": 200.0,
        "height_mm": 250.0,
        "x_mm": 80.0,
        "y_mm": 90.0,
        "original_width_cm": 20.0,
        "original_length_cm": 25.0,
        "glass_margin_mm": 20,
        "glass_hole_local_mm": [[20, 20], [180, 20], [180, 230], [20, 230]],
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    regular = {
        "piece_instance_id": "r1",
        "label": "1.1",
        "sheet_no": 1,
        "piece_type": "Regular",
        "width_mm": 300.0,
        "height_mm": 400.0,
        "x_mm": 650.0,
        "y_mm": 40.0,
        "original_width_cm": 30.0,
        "original_length_cm": 40.0,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    special_geometry = resolve_finished_geometry_mm(
        piece=special, stored_piece=stored_special
    )
    assert special_geometry is not None
    assert len(special_geometry["outer"]) >= 8
    assert special.get("extra_liner") == 1
    glass_geometry = resolve_finished_geometry_mm(piece=glass, stored_piece=glass)
    assert glass_geometry is not None
    assert glass_geometry["holes"]
    # Compile cut paths without liner generation so the NC check isolates
    # finished-geometry recovery for Special / Glass / Regular on one board.
    special_for_cut = dict(special, extra_liner=0, geometry=None)
    glass["geometry"] = None
    regular["geometry"] = None
    payload = _compile(
        [special_for_cut, glass, regular],
        presets={"Finish": _raw(tool_diameter_mm=5)},
    )
    assert not any(issue["code"] == "finished_geometry_missing" for issue in payload["issues"])
    assert payload["geometry_ready"] is True
    cut_ops = [op for op in payload["operations"] if op.get("operation_key") == "cut_path"]
    assert cut_ops and any(path.get("points") for path in cut_ops[0]["toolpaths"])
    # Every piece must contribute at least one outer cut path.
    path_piece_ids = {
        str(path.get("piece_instance_id") or "")
        for path in cut_ops[0]["toolpaths"]
        if path.get("points")
    }
    assert {"s-arc", "g1", "r1"} <= path_piece_ids


def test_approved_plan_placement_outline_passes_through_without_bbox_invention():
    outline = [[5.0, 10.0], [44.5, 10.0], [44.5, 69.5], [15.0, 69.5], [5.0, 50.0]]
    piece = {
        "piece_instance_id": "s-outline",
        "label": "9.1",
        "sheet_no": 1,
        "piece_type": "Special",
        "width_mm": 395.0,
        "height_mm": 595.0,
        "x_mm": 50.0,
        "y_mm": 100.0,
        "original_width_cm": 39.5,
        "original_length_cm": 59.5,
        "special_shape_geometry_json": "",
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    stored = {
        "x": 5.0,
        "y": 10.0,
        "w": 39.5,
        "h": 59.5,
        "original_w": 39.5,
        "original_h": 59.5,
        "piece_type": "Special",
        "placement_outline_cm": outline,
        "special_shape_geometry_json": "",
    }
    source = placed_source_for_finished_geometry(piece, stored)
    assert source.get("placement_outline_cm") == outline
    geometry = resolve_finished_geometry_mm(piece=piece, stored_piece=stored)
    assert geometry is not None
    assert len(geometry["outer"]) == 5
    # Without outline or JSON, still fail closed — no rectangle substitute.
    assert resolve_finished_geometry_mm(piece=piece, stored_piece={
        "x": 5, "y": 10, "w": 39.5, "h": 59.5, "piece_type": "Special"
    }) is None


def test_new_system_expand_preserves_finished_original_for_special_only():
    special_json = _special_json()
    expanded = expand_piece_groups(
        [
            {
                "width_cm": 39.5,
                "length_cm": 59.5,
                "final_width_cm": 40.0,
                "final_length_cm": 60.0,
                "qty": 1,
                "piece_type": "Special",
                "special_shape_geometry_json": special_json,
                "allow_rotation": 0,
            },
            {
                "width_cm": 39.5,
                "length_cm": 59.5,
                "final_width_cm": 40.0,
                "final_length_cm": 60.0,
                "qty": 1,
                "piece_type": "Regular",
                "allow_rotation": 0,
            },
            {
                "width_cm": 50.0,
                "length_cm": 70.0,
                "final_width_cm": 50.5,
                "final_length_cm": 70.5,
                "qty": 1,
                "piece_type": "L-Shaped Corner",
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 12,
                "clipped_corner_length_cm": 18,
                "allow_rotation": 0,
            },
        ]
    )
    special_placed = make_placed_piece(expanded[0], 1, 2, 39.5, 59.5, False)
    regular_placed = make_placed_piece(expanded[1], 3, 4, 39.5, 59.5, False)
    corner_placed = make_placed_piece(expanded[2], 5, 6, 50.0, 70.0, False)
    assert special_placed["original_w"] == 40.0
    assert special_placed["original_h"] == 60.0
    assert regular_placed["original_w"] == 39.5
    assert regular_placed["original_h"] == 59.5
    assert corner_placed["original_w"] == 50.0
    assert corner_placed["original_h"] == 70.0
    outline = material_outline_cm(special_placed)
    assert outline is not None
    assert len(outline) == 5
    piece = {
        "piece_instance_id": "s-new",
        "label": special_placed["label"],
        "sheet_no": 1,
        "piece_type": "Special",
        "width_mm": special_placed["w"] * 10,
        "height_mm": special_placed["h"] * 10,
        "x_mm": special_placed["x"] * 10,
        "y_mm": special_placed["y"] * 10,
        "original_width_cm": special_placed["original_w"],
        "original_length_cm": special_placed["original_h"],
        "special_shape_geometry_json": special_json,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    assert resolve_finished_geometry_mm(piece=piece, stored_piece=special_placed) is not None


def test_repository_contract_forwards_placement_outline_for_cnc_views():
    source = REPO.read_text(encoding="utf-8")
    assert '"placement_outline_cm"' in source
    assert "resolve_finished_geometry_mm" in source
