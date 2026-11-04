"""CNC machine bed placement: validation, fingerprint, and NC XY transform."""

from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.cnc.nc_export import build_simulation_nc
from almdina_erp.almdina_erp.domain.cnc.operational_file import settings_fingerprint
from almdina_erp.almdina_erp.domain.cnc.placement import (
    PLACEMENT_TRANSFORM_VERSION,
    PlacementError,
    apply_placement_to_program,
    build_sheet_placement,
    normalize_cnc_machine,
    placement_fingerprint_payload,
    sheet_to_machine_xy,
    validate_program_within_machine,
    validate_sheet_fits_machine,
)


def _machine(**overrides):
    values = {
        "name": "Router A",
        "width_cm": 130.0,
        "length_cm": 250.0,
        "enabled": True,
    }
    values.update(overrides)
    return values


def _program_with_point(x: float, y: float) -> dict:
    return {
        "geometry_ready": True,
        "nc_export_ready": True,
        "ready": True,
        "coordinate_space": "sheet_bottom_left_y_up_mm",
        "operations": [
            {
                "operation_key": "cut_path",
                "toolpaths": [
                    {
                        "path_key": "cut_path:demo",
                        "ready": True,
                        "closed": False,
                        "points": [[x, y], [x + 10, y]],
                        "preset": {
                            "tool_number": "T9",
                            "spindle_speed_rpm": 15000,
                            "feed_rate_mm_min": 8000,
                            "plunge_rate_mm_min": 1500,
                        },
                        "motions": [
                            {"kind": "travel", "x_mm": x, "y_mm": y, "depth_mm": None},
                            {"kind": "plunge", "x_mm": x, "y_mm": y, "depth_mm": 6},
                            {"kind": "cut", "x_mm": x + 10, "y_mm": y, "depth_mm": 6},
                            {"kind": "retract", "x_mm": x + 10, "y_mm": y, "depth_mm": None},
                        ],
                    }
                ],
            }
        ],
    }


def test_normalize_machine_rejects_non_positive_dimensions():
    with pytest.raises(PlacementError) as width:
        normalize_cnc_machine(machine_name="A", width_cm=0, length_cm=250)
    assert width.value.code == "cnc_machine_width_invalid"
    with pytest.raises(PlacementError) as length:
        normalize_cnc_machine(machine_name="A", width_cm=130, length_cm=-1)
    assert length.value.code == "cnc_machine_length_invalid"


def test_sheet_fit_accepts_zero_and_decimal_offsets():
    validate_sheet_fits_machine(
        machine_width_cm=130,
        machine_length_cm=250,
        sheet_width_cm=122,
        sheet_length_cm=244,
        offset_left_cm=0,
        offset_bottom_cm=0,
    )
    validate_sheet_fits_machine(
        machine_width_cm=130,
        machine_length_cm=250,
        sheet_width_cm=122,
        sheet_length_cm=244,
        offset_left_cm=3.5,
        offset_bottom_cm=4.25,
    )


def test_sheet_fit_rejects_negative_and_overflow():
    with pytest.raises(PlacementError) as negative:
        validate_sheet_fits_machine(
            machine_width_cm=130,
            machine_length_cm=250,
            sheet_width_cm=122,
            sheet_length_cm=244,
            offset_left_cm=-0.1,
            offset_bottom_cm=0,
        )
    assert negative.value.code == "offset_left_invalid"
    with pytest.raises(PlacementError) as overflow:
        validate_sheet_fits_machine(
            machine_width_cm=130,
            machine_length_cm=250,
            sheet_width_cm=122,
            sheet_length_cm=244,
            offset_left_cm=10,
            offset_bottom_cm=4,
        )
    assert overflow.value.code == "sheet_exceeds_machine_width"


def test_reference_coordinate_transform_x100_y200():
    machine_x, machine_y = sheet_to_machine_xy(
        100,
        200,
        offset_left_cm=3,
        offset_bottom_cm=4,
    )
    assert machine_x == 130
    assert machine_y == 240


def test_placement_does_not_mutate_sheet_program_and_applies_once():
    program = _program_with_point(100, 200)
    placement = build_sheet_placement(
        machine=_machine(),
        sheet_width_cm=122,
        sheet_length_cm=244,
        offset_left_cm=3,
        offset_bottom_cm=4,
    )
    machine_program = apply_placement_to_program(program, placement)
    assert program["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == 100
    assert program["operations"][0]["toolpaths"][0]["motions"][0]["y_mm"] == 200
    travel = machine_program["operations"][0]["toolpaths"][0]["motions"][0]
    cut = machine_program["operations"][0]["toolpaths"][0]["motions"][2]
    plunge = machine_program["operations"][0]["toolpaths"][0]["motions"][1]
    assert travel["x_mm"] == 130
    assert travel["y_mm"] == 240
    assert cut["x_mm"] == 140
    assert cut["y_mm"] == 240
    assert plunge["depth_mm"] == 6
    assert machine_program["coordinate_space"] == "machine_bottom_left_y_up_mm"
    assert machine_program["sheet_coordinate_space"] == "sheet_bottom_left_y_up_mm"
    # Applying again to already-translated program would double-shift — callers
    # must keep sheet program separate. Guard: sheet program still original.
    again = apply_placement_to_program(program, placement)
    assert again["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == 130


def test_toolpath_near_machine_edge_with_cutter_overhang_rejected():
    placement = build_sheet_placement(
        machine=_machine(width_cm=130, length_cm=250),
        sheet_width_cm=122,
        sheet_length_cm=244,
        offset_left_cm=8,
        offset_bottom_cm=6,
    )
    # Sheet fits (8+122=130 cm, 6+244=250 cm). A cutter center past the sheet
    # right edge exceeds the machine travel after the left offset.
    program = _program_with_point(1220.1, 10)
    with pytest.raises(PlacementError) as exc:
        validate_program_within_machine(program, placement)
    assert exc.value.code == "toolpath_exceeds_machine"


def test_fingerprint_changes_with_machine_or_offsets():
    base = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets={"Finish": {"preset_name": "Finish", "tool_number": "T9"}},
        sheet_placement=placement_fingerprint_payload(
            build_sheet_placement(
                machine=_machine(),
                sheet_width_cm=122,
                sheet_length_cm=244,
                offset_left_cm=3,
                offset_bottom_cm=4,
            )
        ),
    )
    moved = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets={"Finish": {"preset_name": "Finish", "tool_number": "T9"}},
        sheet_placement=placement_fingerprint_payload(
            build_sheet_placement(
                machine=_machine(),
                sheet_width_cm=122,
                sheet_length_cm=244,
                offset_left_cm=4,
                offset_bottom_cm=4,
            )
        ),
    )
    resized = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets={"Finish": {"preset_name": "Finish", "tool_number": "T9"}},
        sheet_placement=placement_fingerprint_payload(
            build_sheet_placement(
                machine=_machine(width_cm=140),
                sheet_width_cm=122,
                sheet_length_cm=244,
                offset_left_cm=3,
                offset_bottom_cm=4,
            )
        ),
    )
    assert base != moved
    assert base != resized
    assert PLACEMENT_TRANSFORM_VERSION in str(
        placement_fingerprint_payload(
            build_sheet_placement(
                machine=_machine(),
                sheet_width_cm=122,
                sheet_length_cm=244,
                offset_left_cm=0,
                offset_bottom_cm=0,
            )
        )
    )


def test_simulation_nc_emits_machine_coordinates_for_g0_and_g1():
    program = _program_with_point(100, 200)
    placement = build_sheet_placement(
        machine=_machine(),
        sheet_width_cm=122,
        sheet_length_cm=244,
        offset_left_cm=3,
        offset_bottom_cm=4,
    )
    package = build_simulation_nc(
        program,
        machine_profile={
            "retract_z_mm": 20,
            "production_approved": False,
            "distance_mode": "G90",
            "work_offset": "G54",
        },
        sheet_no=1,
        settings_fingerprint="fp-placement",
        sheet_placement=placement,
    )
    text = str(package.get("text") or "")
    assert "G0 X130 Y240" in text
    assert "G1 X140 Y240" in text
    assert "Z-6" in text
    assert package["coordinate_space"] == "machine_bottom_left_y_up_mm"
    assert package["sheet_placement"]["offset_left_mm"] == 30
    assert package["sheet_placement"]["offset_bottom_mm"] == 40
    assert package["sheet_placement"]["placement_transform_version"] == PLACEMENT_TRANSFORM_VERSION
    # Original sheet program unchanged.
    assert program["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == 100


def test_sheet_fit_rejects_length_overflow_and_accepts_boundary():
    validate_sheet_fits_machine(
        machine_width_cm=130,
        machine_length_cm=250,
        sheet_width_cm=122,
        sheet_length_cm=244,
        offset_left_cm=8,
        offset_bottom_cm=6,
    )
    with pytest.raises(PlacementError) as overflow:
        validate_sheet_fits_machine(
            machine_width_cm=130,
            machine_length_cm=250,
            sheet_width_cm=122,
            sheet_length_cm=244,
            offset_left_cm=3,
            offset_bottom_cm=7,
        )
    assert overflow.value.code == "sheet_exceeds_machine_length"


def test_placement_applies_to_liner_handle_and_rear_groove_xy_only():
    placement = build_sheet_placement(
        machine=_machine(),
        sheet_width_cm=122,
        sheet_length_cm=244,
        offset_left_cm=3,
        offset_bottom_cm=4,
    )
    program = {
        "geometry_ready": True,
        "nc_export_ready": True,
        "ready": True,
        "coordinate_space": "sheet_bottom_left_y_up_mm",
        "operations": [
            {
                "operation_key": key,
                "toolpaths": [
                    {
                        "path_key": f"{key}:demo",
                        "ready": True,
                        "closed": False,
                        "points": [[10, 20]],
                        "preset": {
                            "tool_number": "T9",
                            "spindle_speed_rpm": 15000,
                            "feed_rate_mm_min": 8000,
                            "plunge_rate_mm_min": 1500,
                        },
                        "motions": [
                            {"kind": "travel", "x_mm": 10, "y_mm": 20, "depth_mm": None},
                            {"kind": "plunge", "x_mm": 10, "y_mm": 20, "depth_mm": 3},
                            {"kind": "cut", "x_mm": 15, "y_mm": 25, "depth_mm": 3},
                        ],
                    }
                ],
            }
            for key in ("liner", "recessed_handle", "rear_groove", "sheet_perimeter")
        ],
    }
    machine_program = apply_placement_to_program(program, placement)
    for operation in machine_program["operations"]:
        travel = operation["toolpaths"][0]["motions"][0]
        plunge = operation["toolpaths"][0]["motions"][1]
        cut = operation["toolpaths"][0]["motions"][2]
        assert travel["x_mm"] == 40
        assert travel["y_mm"] == 60
        assert cut["x_mm"] == 45
        assert cut["y_mm"] == 65
        assert plunge["depth_mm"] == 3
    assert program["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == 10
