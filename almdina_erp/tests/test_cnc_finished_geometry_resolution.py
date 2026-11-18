"""Finished geometry resolution for CNC without inventing unsupported shapes."""

from __future__ import annotations

import json
import math
from pathlib import Path

from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.domain.cutting.finished_piece_geometry import (
    resolve_finished_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import serialize_geometry_mm
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry


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
