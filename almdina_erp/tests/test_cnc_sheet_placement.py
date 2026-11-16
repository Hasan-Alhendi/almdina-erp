"""CNC machine bed placement: validation, fingerprint, and NC XY transform."""

from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.cnc.nc_export import (
    build_post_processed_nc,
    build_simulation_nc,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import settings_fingerprint
from almdina_erp.almdina_erp.domain.cnc.placement import (
    PLACEMENT_TRANSFORM_VERSION,
    PlacementError,
    apply_placement_to_program,
    build_sheet_placement,
    legacy_machine_stops_remain_unset,
    normalize_cnc_machine,
    placement_fingerprint_payload,
    sheet_to_machine_xy,
    sheet_to_nc_xy,
    validate_program_within_machine,
    validate_sheet_fits_machine,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import extension_conflict


def _machine(**overrides):
    values = {
        "name": "Router A",
        "width_cm": 130.0,
        "length_cm": 250.0,
        "enabled": True,
        "work_zero_position": "Bottom Left",
        "left_stop_cm": 0,
        "bottom_stop_cm": 0,
    }
    values.update(overrides)
    return values


def _placed(**overrides):
    machine = dict(overrides.pop("machine", _machine()))
    if "offset_left_cm" in overrides:
        machine["left_stop_cm"] = overrides.pop("offset_left_cm")
    if "offset_bottom_cm" in overrides:
        machine["bottom_stop_cm"] = overrides.pop("offset_bottom_cm")
    if "work_zero_position" in overrides:
        machine["work_zero_position"] = overrides.pop("work_zero_position")
    return build_sheet_placement(machine=machine, **overrides)


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
    placement = _placed(
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
    assert machine_program["coordinate_space"] == "g54_work_zero_y_up_mm"
    assert machine_program["sheet_coordinate_space"] == "sheet_bottom_left_y_up_mm"
    # Applying again to already-translated program would double-shift — callers
    # must keep sheet program separate. Guard: sheet program still original.
    again = apply_placement_to_program(program, placement)
    assert again["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == 130


@pytest.mark.parametrize("diameter_mm", (5.0, 8.0, 12.0))
@pytest.mark.parametrize(
    ("axis", "sign"),
    (
        ("x", -1),
        ("x", 1),
        ("y", -1),
        ("y", 1),
    ),
)
def test_edge_cutter_centres_may_leave_the_bed_on_every_side(diameter_mm, axis, sign):
    """A 4000 mm bed does not reject radius compensation past the sheet edge."""

    machine_width_mm = 1600.0
    machine_length_mm = 4000.0
    radius = diameter_mm / 2.0
    if axis == "x":
        x_mm = -radius if sign < 0 else machine_width_mm + radius
        y_mm = 100.0
    else:
        x_mm = 100.0
        y_mm = -radius if sign < 0 else machine_length_mm + radius
    placement = _placed(
        machine=_machine(width_cm=machine_width_mm / 10.0, length_cm=machine_length_mm / 10.0),
        sheet_width_cm=machine_width_mm / 10.0,
        sheet_length_cm=machine_length_mm / 10.0,
        offset_left_cm=0,
        offset_bottom_cm=0,
    )
    program = _program_with_point(x_mm, y_mm)
    original = program["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"]
    original_y = program["operations"][0]["toolpaths"][0]["motions"][0]["y_mm"]
    validate_program_within_machine(program, placement)
    placed = apply_placement_to_program(program, placement)
    travel = placed["operations"][0]["toolpaths"][0]["motions"][0]
    cut = placed["operations"][0]["toolpaths"][0]["motions"][2]
    assert travel["kind"] == "travel"
    assert travel["x_mm"] == x_mm
    assert travel["y_mm"] == y_mm
    assert cut["x_mm"] == x_mm + 10
    assert cut["y_mm"] == y_mm
    assert program["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == original
    assert program["operations"][0]["toolpaths"][0]["motions"][0]["y_mm"] == original_y
    if diameter_mm == 5.0 and axis == "y" and sign < 0:
        assert y_mm == -2.5
    if diameter_mm == 5.0 and axis == "y" and sign > 0:
        assert y_mm == 4002.5


def test_sheet_that_leaves_the_4000_mm_bed_is_rejected():
    validate_sheet_fits_machine(
        machine_width_cm=160,
        machine_length_cm=400,
        sheet_width_cm=160,
        sheet_length_cm=400,
        offset_left_cm=0,
        offset_bottom_cm=0,
    )
    with pytest.raises(PlacementError) as length_overflow:
        _placed(
            machine=_machine(width_cm=160, length_cm=400),
            sheet_width_cm=160,
            sheet_length_cm=400.1,
            offset_left_cm=0,
            offset_bottom_cm=0,
        )
    assert length_overflow.value.code == "sheet_exceeds_machine_length"
    with pytest.raises(PlacementError) as width_overflow:
        _placed(
            machine=_machine(width_cm=160, length_cm=400),
            sheet_width_cm=160.1,
            sheet_length_cm=400,
            offset_left_cm=0,
            offset_bottom_cm=0,
        )
    assert width_overflow.value.code == "sheet_exceeds_machine_width"


def test_cutter_body_that_enters_an_adjacent_door_stays_rejected():
    neighbor = {"polygon": [(20.0, 0.0), (220.0, 0.0), (220.0, 200.0), (20.0, 200.0)]}
    for diameter_mm in (5.0, 8.0, 12.0):
        radius = diameter_mm / 2.0
        invading = [(0.0, 100.0), (20.0 + radius - 0.2, 100.0)]
        clear = [(0.0, 100.0), (20.0 - radius, 100.0)]
        assert extension_conflict(invading, diameter_mm, None, [neighbor]) == "liner_extension_hits_piece"
        assert extension_conflict(clear, diameter_mm, None, [neighbor]) == ""
        program = _program_with_point(invading[1][0], invading[1][1])
        placement = _placed(
            machine=_machine(width_cm=160, length_cm=400),
            sheet_width_cm=160,
            sheet_length_cm=400,
            offset_left_cm=0,
            offset_bottom_cm=0,
        )
        placed = apply_placement_to_program(program, placement)
        cut = placed["operations"][0]["toolpaths"][0]["motions"][2]
        assert cut["x_mm"] == invading[1][0] + 10
        assert cut["y_mm"] == invading[1][1]


def test_fingerprint_changes_with_machine_or_offsets():
    base = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets={"Finish": {"preset_name": "Finish", "tool_number": "T9"}},
        sheet_placement=placement_fingerprint_payload(
            _placed(
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
            _placed(
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
            _placed(
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
    assert "cutter_travel" not in str(
        placement_fingerprint_payload(
            _placed(
                machine=_machine(),
                sheet_width_cm=122,
                sheet_length_cm=244,
                offset_left_cm=3,
                offset_bottom_cm=4,
            )
        )
    )
    assert PLACEMENT_TRANSFORM_VERSION in str(
        placement_fingerprint_payload(
            _placed(
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
    placement = _placed(
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
    assert package["coordinate_space"] == "g54_work_zero_y_up_mm"
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
    placement = _placed(
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


REFERENCE_NC = {
    "Bottom Left": (250.0, 400.0),
    "Bottom Right": (-1750.0, 400.0),
    "Top Left": (250.0, -3600.0),
    "Top Right": (-1750.0, -3600.0),
    "Center": (-750.0, -1600.0),
}


def _reference_machine(position="Bottom Left"):
    return {
        "name": "Reference",
        "width_cm": 200,
        "length_cm": 400,
        "left_stop_cm": 5,
        "bottom_stop_cm": 10,
        "work_zero_position": position,
        "enabled": True,
    }


def _nc_program(points, *, tool="T9", feed_sec=170, home=(0, 100, 120)):
    motions = [{"kind": "travel", "x_mm": points[0][0], "y_mm": points[0][1]}]
    motions.append({"kind": "plunge", "x_mm": points[0][0], "y_mm": points[0][1], "depth_mm": 6})
    for point in points[1:]:
        motions.append({"kind": "cut", "x_mm": point[0], "y_mm": point[1], "depth_mm": 6})
    motions.append({"kind": "retract", "x_mm": points[-1][0], "y_mm": points[-1][1]})
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
                        "ready": True,
                        "path_key": "cut_path:reference",
                        "safe_z_mm": 20,
                        "home": {"x_mm": home[0], "y_mm": home[1], "z_mm": home[2]},
                        "points": [[point[0], point[1]] for point in points],
                        "preset": {
                            "tool_number": tool,
                            "spindle_speed_rpm": 15000,
                            "feed_rate_mm_sec": feed_sec,
                            "plunge_rate_mm_sec": 30,
                            "feed_rate_mm_min": feed_sec * 60,
                            "plunge_rate_mm_min": 1800,
                        },
                        "motions": motions,
                    }
                ],
            }
        ],
    }


def test_machine_settings_round_trip_and_reject_bad_stops():
    created = normalize_cnc_machine(
        machine_name="Router A",
        width_cm=200,
        length_cm=400,
        work_zero_position="Center",
        left_stop_cm=5,
        bottom_stop_cm=10,
    )
    reloaded = normalize_cnc_machine(
        machine_name=created.name,
        width_cm=created.width_cm,
        length_cm=created.length_cm,
        work_zero_position=created.work_zero_position,
        left_stop_cm=created.left_stop_cm,
        bottom_stop_cm=created.bottom_stop_cm,
    )
    assert reloaded.work_zero_position == "Center"
    assert reloaded.left_stop_cm == 5
    assert reloaded.bottom_stop_cm == 10
    zero = normalize_cnc_machine(
        machine_name="Router A",
        width_cm=200,
        length_cm=400,
        left_stop_cm=0,
        bottom_stop_cm=0,
    )
    assert zero.left_stop_cm == 0
    assert zero.bottom_stop_cm == 0
    assert zero.work_zero_position == "Bottom Left"
    with pytest.raises(PlacementError) as negative:
        normalize_cnc_machine(
            machine_name="Router A",
            width_cm=200,
            length_cm=400,
            left_stop_cm=-1,
            bottom_stop_cm=0,
        )
    assert negative.value.code == "offset_left_invalid"
    with pytest.raises(PlacementError) as missing:
        normalize_cnc_machine(
            machine_name="Router A",
            width_cm=200,
            length_cm=400,
            left_stop_cm=None,
            bottom_stop_cm=0,
        )
    assert missing.value.code == "cnc_machine_stops_unconfigured"


@pytest.mark.parametrize("position,expected", tuple(REFERENCE_NC.items()))
def test_reference_work_zero_and_stops(position, expected):
    placement = build_sheet_placement(
        machine=_reference_machine(position),
        sheet_width_cm=100,
        sheet_length_cm=200,
    )
    physical = sheet_to_machine_xy(200, 300, offset_left_cm=5, offset_bottom_cm=10)
    assert physical == (250, 400)
    assert sheet_to_nc_xy(200, 300, placement) == expected
    placed = apply_placement_to_program(_nc_program([(200, 300), (300, 300)]), placement)
    travel = placed["operations"][0]["toolpaths"][0]["motions"][0]
    assert (travel["x_mm"], travel["y_mm"]) == expected
    assert placed["coordinate_space"] == "g54_work_zero_y_up_mm"
    assert placed["work_zero_position"] == position
    package = build_post_processed_nc(
        _nc_program([(200, 300), (300, 300)]),
        post_processor_id="ima_wh_ncstudio",
        sheet_placement=placement,
        sheet_no=1,
    )
    assert f"X{expected[0]:.4f} Y{expected[1]:.4f}" in package["text"]
    assert "G53 X1500.0 Y3500.0 Z0" in package["text"]
    assert "G53 Z0" in package["text"]
    assert "X0.0000 Y100.0000" in package["text"]


def test_stops_and_work_zero_are_applied_once_and_do_not_reverse_axes():
    placement = build_sheet_placement(
        machine=_reference_machine("Top Right"),
        sheet_width_cm=100,
        sheet_length_cm=200,
    )
    program = _nc_program([(200, 300), (300, 450)])
    placed = apply_placement_to_program(program, placement)
    first = placed["operations"][0]["toolpaths"][0]["motions"][0]
    second = placed["operations"][0]["toolpaths"][0]["motions"][2]
    assert second["x_mm"] - first["x_mm"] == 100
    assert second["y_mm"] - first["y_mm"] == 150
    assert first["x_mm"] == -1750
    again = apply_placement_to_program(program, placement)
    assert again["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == first["x_mm"]
    assert program["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == 200
    ignored = build_sheet_placement(
        machine={**_reference_machine("Bottom Left"), "offset_left_cm": 99, "offset_bottom_cm": 80},
        sheet_width_cm=100,
        sheet_length_cm=200,
    )
    assert ignored.offset_left_cm == 5
    assert ignored.offset_bottom_cm == 10


def test_same_machine_stops_apply_to_different_tools():
    placement = build_sheet_placement(
        machine=_reference_machine("Center"),
        sheet_width_cm=100,
        sheet_length_cm=200,
    )
    texts = []
    for tool, feed in (("T9", 170), ("T4", 90)):
        package = build_post_processed_nc(
            _nc_program([(200, 300), (300, 300)], tool=tool, feed_sec=feed),
            post_processor_id="ima_wh_ncstudio",
            sheet_placement=placement,
            sheet_no=1,
        )
        texts.append(package["text"])
    assert "X-750.0000 Y-1600.0000" in texts[0]
    assert "X-750.0000 Y-1600.0000" in texts[1]
    assert "T9" in texts[0]
    assert "T4" in texts[1]
    assert "F10200.0" in texts[0]
    assert "F5400.0" in texts[1]


def test_fingerprint_changes_when_work_zero_changes():
    base = placement_fingerprint_payload(
        build_sheet_placement(
            machine=_reference_machine("Bottom Left"),
            sheet_width_cm=100,
            sheet_length_cm=200,
        )
    )
    moved = placement_fingerprint_payload(
        build_sheet_placement(
            machine=_reference_machine("Center"),
            sheet_width_cm=100,
            sheet_length_cm=200,
        )
    )
    assert base["work_zero_position"] == "Bottom Left"
    assert moved["work_zero_position"] == "Center"
    assert settings_fingerprint(
        operation_presets={},
        path_overrides={},
        presets={},
        sheet_placement=base,
    ) != settings_fingerprint(
        operation_presets={},
        path_overrides={},
        presets={},
        sheet_placement=moved,
    )


def test_legacy_offsets_are_not_copied_onto_the_machine():
    assert legacy_machine_stops_remain_unset(()) is False
    assert legacy_machine_stops_remain_unset([(0, 0), (0, 0)]) is False
    assert legacy_machine_stops_remain_unset([(5, 10)]) is True
    assert legacy_machine_stops_remain_unset([(5, 0), (0, 10)]) is True
    assert legacy_machine_stops_remain_unset([(0, 0), (4, 0)]) is True
