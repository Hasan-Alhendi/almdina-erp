"""Uploaded DXF sheet extraction must not leak other boards into one preview."""

from __future__ import annotations

import pytest

import ezdxf

from almdina_erp.almdina_erp.application.cnc.nc_export import build_simulation_nc
from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.domain.cnc.post_processor import POST_PROCESSOR_VERSION
from almdina_erp.almdina_erp.infrastructure.cutting.cnc_dxf_source import read_operational_dxf
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import DxfReadError


SHEET_W = 1220.0
SHEET_H = 2440.0
KERF_MM = 5.0
ALLOWANCE = KERF_MM / 2.0


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


def _snapshot(sheet_count=1):
    return {
        "kerf_mm": KERF_MM,
        "full_board_width_cm": SHEET_W / 10.0,
        "full_board_length_cm": SHEET_H / 10.0,
        "sheets": [
            {
                "sheet_no": index,
                "full_width_cm": SHEET_W / 10.0,
                "full_length_cm": SHEET_H / 10.0,
                "applied_trim_width_cm": 0,
                "applied_trim_length_cm": 0,
            }
            for index in range(1, sheet_count + 1)
        ],
    }


def _compile(pieces, *, sheet_no, uploaded, mode="uploaded_present"):
    return compile_sheet_program(
        sheet_no=sheet_no,
        pieces=pieces,
        snapshot=_snapshot(max(sheet_no, max(int(piece["sheet_no"]) for piece in pieces))),
        operation_presets={
            "cut_path": "Finish",
            "liner": "Finish",
            "back_groove": "Finish",
            "recessed_handle_cutout": "Finish",
        },
        path_overrides={},
        operation_order=["liner", "recessed_handle_cutout", "back_groove", "cut_path"],
        known_presets=PRESETS,
        manufacturing_mode=mode,
        uploaded=uploaded,
    )


def _outline(modelspace, origin):
    x, y = origin
    modelspace.add_lwpolyline(
        [(x, y), (x + SHEET_W, y), (x + SHEET_W, y + SHEET_H), (x, y + SHEET_H)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )


def _line(modelspace, start, end, layer):
    modelspace.add_line(start, end, dxfattribs={"layer": layer})


def _four_sheet_document():
    """Draw sheets out of spatial order. Numbering follows min-y then min-x."""

    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    for name in ("SHEET_OUTLINE", "CUT_PATH", "Liner", "Handle Recess", "Rear Groove"):
        document.layers.add(name)
    modelspace = document.modelspace()
    origins = {
        4: (2000.0, 3000.0),
        3: (0.0, 3000.0),
        2: (2000.0, 0.0),
        1: (0.0, 0.0),
    }
    for sheet_no in (4, 3, 2, 1):
        origin = origins[sheet_no]
        _outline(modelspace, origin)
        x, y = origin
        _line(modelspace, (x + 40, y + 50), (x + 180, y + 50), "CUT_PATH")
        modelspace.add_lwpolyline(
            [(x + 60, y + 80), (x + 140, y + 80), (x + 140, y + 160), (x + 60, y + 160)],
            close=True,
            dxfattribs={"layer": "CUT_PATH"},
        )
        _line(modelspace, (x + 30, y + 200), (x + 30, y + 280), "Liner")
        _line(modelspace, (x + 70, y + 200), (x + 120, y + 200), "Handle Recess")
        _line(modelspace, (x + 90, y + 220), (x + 90, y + 300), "Rear Groove")
    return document, origins


def _read(path, sheet_no, allowance=ALLOWANCE):
    try:
        return read_operational_dxf(
            str(path),
            sheet_no=sheet_no,
            boundary_allowance_mm=allowance,
        )
    except TypeError:
        return read_operational_dxf(str(path), sheet_no=sheet_no)


def test_each_uploaded_sheet_keeps_only_its_own_paths(tmp_path):
    document, origins = _four_sheet_document()
    target = tmp_path / "four-sheets.dxf"
    document.saveas(target)

    per_sheet = []
    for sheet_no in (1, 2, 3, 4):
        loaded = _read(target, sheet_no)
        per_sheet.append(loaded)
        assert loaded["origin"] == origins[sheet_no]
        assert loaded["sheet_count"] == 4
        assert loaded.get("read_error") in (None, "")
        assert len(loaded["cut_segments"]) == 5, (
            "one open line plus one closed rectangle; other sheets must not leak"
        )
        assert all(0 <= start[0] <= SHEET_W and 0 <= end[0] <= SHEET_W for start, end in loaded["cut_segments"])
        assert all(0 <= start[1] <= SHEET_H and 0 <= end[1] <= SHEET_H for start, end in loaded["cut_segments"])
        layers = {item["layer"] for item in loaded["overlays"]}
        assert layers == {"Liner", "Handle Recess", "Rear Groove"}
        assert len(loaded["overlays"]) == 3
        assert {(round(item["points"][0][0], 3), item["layer"]) for item in loaded["overlays"]} == {
            (30.0, "Liner"),
            (70.0, "Handle Recess"),
            (90.0, "Rear Groove"),
        }

    identities = [loaded["cut_segments"] for loaded in per_sheet]
    assert identities[0] == identities[1] == identities[2] == identities[3]
    assert identities[0][0] == ((40.0, 50.0), (180.0, 50.0))


def test_cutter_center_may_sit_outside_the_sheet_by_the_approved_allowance(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("SHEET_OUTLINE")
    document.layers.add("CUT_PATH")
    modelspace = document.modelspace()
    _outline(modelspace, (0, 0))
    modelspace.add_line((-ALLOWANCE, 100), (40, 100), dxfattribs={"layer": "CUT_PATH"})
    modelspace.add_line((-ALLOWANCE - 2, 120), (40, 120), dxfattribs={"layer": "CUT_PATH"})
    target = tmp_path / "overhang.dxf"
    document.saveas(target)
    loaded = _read(target, 1)
    assert loaded.get("read_error") == "path_outside_sheet"
    assert loaded["cut_segments"] == []


def test_a_path_in_two_expanded_sheets_is_not_guessed(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("SHEET_OUTLINE")
    document.layers.add("CUT_PATH")
    modelspace = document.modelspace()
    _outline(modelspace, (0, 0))
    _outline(modelspace, (SHEET_W + 1, 0))
    modelspace.add_line((SHEET_W - 0.2, 80), (SHEET_W + 0.8, 80), dxfattribs={"layer": "CUT_PATH"})
    target = tmp_path / "ambiguous.dxf"
    document.saveas(target)
    loaded = _read(target, 1)
    assert loaded.get("read_error") == "path_sheet_affiliation_ambiguous"
    assert loaded["cut_segments"] == []


def test_missing_outline_unspecified_units_and_unreadable_file_stay_explicit(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 0
    document.layers.add("CUT_PATH")
    document.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "CUT_PATH"})
    missing = tmp_path / "no-outline.dxf"
    document.saveas(missing)
    loaded = _read(missing, 1, allowance=0)
    assert loaded["units"] == "unspecified"
    assert loaded.get("read_error") == "sheet_frame_unknown"
    assert loaded["origin"] is None

    broken = tmp_path / "broken.dxf"
    broken.write_text("not a dxf", encoding="ascii")
    with pytest.raises(DxfReadError):
        read_operational_dxf(str(broken), sheet_no=1)


def test_uploaded_sheet_program_uses_only_that_board_and_can_post_simulation_nc(tmp_path):
    piece = _piece("piece-a", _rect(100, 100, 400, 600), label="1.1")
    generated = _compile([piece], sheet_no=1, uploaded=None, mode="generated")
    assert generated["geometry_ready"] is True
    cut = next(path for operation in generated["operations"] if operation["operation_key"] == "cut_path" for path in operation["toolpaths"])
    points = [(float(point[0]), float(point[1])) for point in cut["points"]]
    local_segments = list(zip(points, points[1:]))
    if points[0] != points[-1]:
        local_segments.append((points[-1], points[0]))

    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("SHEET_OUTLINE")
    document.layers.add("CUT_PATH")
    modelspace = document.modelspace()
    _outline(modelspace, (5000, 800))
    _outline(modelspace, (0, 0))
    for start, end in local_segments:
        modelspace.add_line(start, end, dxfattribs={"layer": "CUT_PATH"})
    modelspace.add_line((5100, 900), (5300, 900), dxfattribs={"layer": "CUT_PATH"})
    target = tmp_path / "approved-upload.dxf"
    document.saveas(target)

    first = _read(target, 1)
    second = _read(target, 2)
    assert len(first["cut_segments"]) == len(local_segments)
    assert len(second["cut_segments"]) == 1
    assert first["origin"] == (0.0, 0.0)
    assert second["origin"] == (5000.0, 800.0)

    program = _compile([piece], sheet_no=1, uploaded=first)
    kinds = [motion["kind"] for operation in program["operations"] for path in operation["toolpaths"] for motion in path["motions"]]
    assert "travel" in kinds and "plunge" in kinds and "cut" in kinds and "retract" in kinds
    assert program["geometry_ready"] is True
    package = build_simulation_nc(
        program,
        machine_profile={
            "retract_z_mm": 20,
            "production_approved": False,
            "distance_mode": "G90",
            "work_offset": "G54",
        },
        sheet_no=1,
        settings_fingerprint="uploaded-sheet",
    )
    assert package["verification"]["ok"] is True
    assert package["post_processor_version"] == POST_PROCESSOR_VERSION
    assert "G01" in package["text"] or "G1" in package["text"]

    other = _piece("piece-b", _rect(80, 80, 200, 200), sheet_no=2, label="2.1")
    leaked = _compile([piece, other], sheet_no=2, uploaded=second)
    assert leaked["geometry_ready"] is False


def test_a_sheet_without_cut_path_follows_the_present_mismatch_policy(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("SHEET_OUTLINE")
    modelspace = document.modelspace()
    _outline(modelspace, (0, 0))
    target = tmp_path / "no-cuts.dxf"
    document.saveas(target)
    loaded = _read(target, 1)
    assert loaded["cut_segments"] == []
    assert loaded.get("read_error") in (None, "")
    piece = _piece("piece-a", _rect(100, 100, 400, 600))
    program = _compile([piece], sheet_no=1, uploaded=loaded)
    codes = [issue["code"] for issue in program["issues"]]
    assert "cut_path_does_not_match_approved_centers" in codes


def test_mismatched_cut_geometry_is_rejected_after_sheet_filtering(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("SHEET_OUTLINE")
    document.layers.add("CUT_PATH")
    modelspace = document.modelspace()
    _outline(modelspace, (0, 0))
    modelspace.add_line((20, 20), (80, 20), dxfattribs={"layer": "CUT_PATH"})
    target = tmp_path / "wrong-cut.dxf"
    document.saveas(target)
    loaded = _read(target, 1)
    piece = _piece("piece-a", _rect(100, 100, 400, 600))
    program = _compile([piece], sheet_no=1, uploaded=loaded)
    codes = [issue["code"] for issue in program["issues"]]
    codes.extend(
        code
        for operation in program["operations"]
        for path in operation["toolpaths"]
        for code in path["issues"]
    )
    assert "cut_path_does_not_match_approved_centers" in codes
    assert program["geometry_ready"] is False
