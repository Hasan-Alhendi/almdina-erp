"""IMA-WH post processor: format, placement, home, and verification."""

from __future__ import annotations

from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cnc.nc_export import build_post_processed_nc
from almdina_erp.almdina_erp.domain.cnc.nc_interpreter import interpret_nc, verify_nc_against_program
from almdina_erp.almdina_erp.domain.cnc.operational_file import settings_fingerprint
from almdina_erp.almdina_erp.domain.cnc.placement import apply_placement_to_program, build_sheet_placement
from almdina_erp.almdina_erp.domain.cnc.post_processor import PostProcessorError
from almdina_erp.almdina_erp.domain.cnc.post_processors import (
    IMA_WH_ID,
    emit_ima_wh,
    list_post_processors,
    resolve_post_processor,
)


FIXTURE = Path(__file__).resolve().parents[0] / "fixtures" / "cnc" / "ima_wh_reference.nc"
ROOT = Path(__file__).resolve().parents[1]


def _machine(**overrides):
    values = {"name": "IMA Router", "width_cm": 160.0, "length_cm": 360.0, "enabled": True}
    values.update(overrides)
    return values


def _placement(**overrides):
    values = {
        "machine": _machine(),
        "sheet_width_cm": 122,
        "sheet_length_cm": 244,
        "offset_left_cm": 10,
        "offset_bottom_cm": 5,
    }
    values.update(overrides)
    return build_sheet_placement(**values)


def _path(points, motions, *, tool="T9", safe_z=20, home=(0, 2440, 120), feed_sec=170, plunge_sec=30):
    return {
        "ready": True,
        "path_key": "path-1",
        "safe_z_mm": safe_z,
        "home": {"x_mm": home[0], "y_mm": home[1], "z_mm": home[2]},
        "points": [[point[0], point[1]] for point in points],
        "preset": {
            "tool_number": tool,
            "spindle_speed_rpm": 15000,
            "feed_rate_mm_sec": feed_sec,
            "plunge_rate_mm_sec": plunge_sec,
            "feed_rate_mm_min": feed_sec * 60,
            "plunge_rate_mm_min": plunge_sec * 60,
        },
        "motions": motions,
    }


def _program(*paths):
    return {
        "geometry_ready": True,
        "nc_export_ready": True,
        "ready": True,
        "coordinate_space": "sheet_bottom_left_y_up_mm",
        "operations": [{"operation_key": "profile", "toolpaths": list(paths)}],
    }


def _reference_program():
    return _program(
        _path(
            [(300, 500), (320, 800)],
            [
                {"kind": "travel", "x_mm": 300, "y_mm": 500},
                {"kind": "plunge", "x_mm": 300, "y_mm": 500, "depth_mm": 10},
                {"kind": "cut", "x_mm": 300, "y_mm": 800, "depth_mm": 10},
                {"kind": "cut", "x_mm": 320, "y_mm": 800, "depth_mm": 10},
                {"kind": "retract", "x_mm": 320, "y_mm": 800},
            ],
        )
    )


def _export(program, placement=None, processor=IMA_WH_ID):
    return build_post_processed_nc(
        program,
        post_processor_id=processor,
        sheet_placement=placement or _placement(),
        sheet_no=1,
        settings_fingerprint="sheet",
    )


def test_registry_has_one_explicit_processor_and_no_default():
    listed = list_post_processors()
    assert listed == ({"id": "ima_wh_ncstudio", "label": "IMA-WH (*.nc)", "extension": "nc"},)
    assert resolve_post_processor("", required=False) == ""
    with pytest.raises(PostProcessorError) as missing:
        resolve_post_processor("", required=True)
    assert missing.value.code == "post_processor_required"
    with pytest.raises(PostProcessorError) as unknown:
        resolve_post_processor("simulation", required=True)
    assert unknown.value.code == "post_processor_unsupported"


def test_missing_or_unknown_processor_is_refused_before_emission():
    program = _reference_program()
    with pytest.raises(PostProcessorError) as missing:
        _export(program, processor="")
    assert missing.value.code == "post_processor_required"
    with pytest.raises(PostProcessorError) as unknown:
        _export(program, processor="artcam_legacy")
    assert unknown.value.code == "post_processor_unsupported"


def test_choice_changes_the_saved_settings_fingerprint():
    base = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets={},
    )
    chosen = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets={},
        post_processor=IMA_WH_ID,
    )
    assert chosen != base


def test_ima_wh_golden_file_matches_artcam_format_rules():
    original = _reference_program()
    package = _export(original)
    text = package["text"]
    assert text.encode("ascii") == FIXTURE.read_bytes()
    assert "\n" not in text.replace("\r\n", "")
    assert text.startswith("G90\r\nG40 G80\r\nG54\r\nG53 Z0\r\nT9\r\nM3 S15000\r\n")
    assert text.endswith("G80\r\nM5\r\nG53 X1500.0 Y3500.0 Z0\r\nM30\r\n;\r\n")
    assert "N60 G0 X400.0000 Y550.0000 Z20.0000" in text
    assert "N70 G1 Z-10.0000 F1800.0" in text
    assert "N80 G1 Y850.0000 F10200.0" in text
    assert "N90 X420.0000" in text
    assert "G21" not in text
    assert "M6" not in text
    assert "(" not in text
    assert package["production"] is False
    assert package["machine_coordinate_transform_unverified"] is True
    assert package["post_processor"] == IMA_WH_ID
    assert original["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == 300


def test_tool_prefix_is_not_doubled_and_feed_is_converted_once():
    for tool in ("9", "T9", "T09"):
        program = _program(
            _path(
                [(300, 500), (320, 800)],
                [
                    {"kind": "travel", "x_mm": 300, "y_mm": 500},
                    {"kind": "plunge", "x_mm": 300, "y_mm": 500, "depth_mm": 10},
                    {"kind": "cut", "x_mm": 320, "y_mm": 800, "depth_mm": 10},
                    {"kind": "retract", "x_mm": 320, "y_mm": 800},
                ],
                tool=tool,
            )
        )
        text = _export(program)["text"]
        assert "\r\nT9\r\n" in text
        assert "TT9" not in text
        assert "T T9" not in text
    minutes_only = _reference_program()
    preset = minutes_only["operations"][0]["toolpaths"][0]["preset"]
    del preset["feed_rate_mm_sec"]
    del preset["plunge_rate_mm_sec"]
    text = _export(minutes_only)["text"]
    assert "F10200.0" in text
    assert "F1800.0" in text
    assert "F612000" not in text


def test_sheet_offset_is_applied_once_and_not_to_home_or_g53():
    program = _reference_program()
    placement = _placement()
    placed = apply_placement_to_program(program, placement)
    home = placed["operations"][0]["toolpaths"][0]["home"]
    assert home["x_mm"] == 0
    assert home["y_mm"] == 2440
    assert placed["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == 400
    assert placed["operations"][0]["toolpaths"][0]["motions"][0]["y_mm"] == 550
    text = _export(program, placement)["text"]
    assert "X400.0000 Y550.0000" in text
    assert "X500.0000" not in text
    assert "G0 X0.0000 Y2440.0000 Z120.0000" in text
    assert "G53 X1500.0 Y3500.0 Z0" in text
    assert "G53 X1600" not in text
    assert text.count("Y2440.0000") == 1


def test_negative_g54_coordinates_and_profile_home_are_allowed_inside_travel_extensions():
    path = _path(
        [(-2.5, 100), (20, 100)],
        [
            {"kind": "travel", "x_mm": -2.5, "y_mm": 100},
            {"kind": "plunge", "x_mm": -2.5, "y_mm": 100, "depth_mm": 5},
            {"kind": "cut", "x_mm": 20, "y_mm": 100, "depth_mm": 5},
            {"kind": "retract", "x_mm": 20, "y_mm": 100},
        ],
        home=(-2.5, 100, 120),
    )
    placement = _placement(
        machine=_machine(cutter_travel_left_extension_mm=5),
        offset_left_cm=0,
        offset_bottom_cm=0,
    )
    program = _program(path)
    package = _export(program, placement)
    assert "X-2.5000 Y100.0000" in package["text"]
    assert package["verification"]["ok"] is True
    assert package["sheet_placement"]["cutter_travel_x_min_mm"] == -5
    assert program["operations"][0]["toolpaths"][0]["motions"][0]["x_mm"] == -2.5


def test_g54_extensions_do_not_expand_the_g53_parking_limits():
    placement = _placement(
        machine=_machine(
            width_cm=140,
            length_cm=340,
            cutter_travel_right_extension_mm=200,
            cutter_travel_top_extension_mm=200,
        ),
        sheet_width_cm=100,
        sheet_length_cm=200,
        offset_left_cm=0,
        offset_bottom_cm=0,
    )
    with pytest.raises(PostProcessorError) as parking:
        _export(_reference_program(), placement)
    assert parking.value.code == "machine_parking_outside_limits"


def test_home_happens_once_and_not_between_stepdowns():
    program = _program(
        _path(
            [(300, 500), (320, 800)],
            [
                {"kind": "travel", "x_mm": 300, "y_mm": 500},
                {"kind": "plunge", "x_mm": 300, "y_mm": 500, "depth_mm": 5},
                {"kind": "cut", "x_mm": 320, "y_mm": 800, "depth_mm": 5},
                {"kind": "retract", "x_mm": 320, "y_mm": 800},
                {"kind": "plunge", "x_mm": 320, "y_mm": 800, "depth_mm": 10},
                {"kind": "cut", "x_mm": 300, "y_mm": 500, "depth_mm": 10},
                {"kind": "retract", "x_mm": 300, "y_mm": 500},
            ],
        )
    )
    text = _export(program)["text"]
    assert text.count("Y2440.0000") == 1
    between_passes = text.split("Z-5.0000", 1)[1].split("Z-10.0000", 1)[0]
    assert "Y2440.0000" not in between_passes


def test_each_profile_keeps_its_safe_z_and_the_last_home():
    first = _path(
        [(100, 100), (120, 100)],
        [
            {"kind": "travel", "x_mm": 100, "y_mm": 100},
            {"kind": "plunge", "x_mm": 100, "y_mm": 100, "depth_mm": 4},
            {"kind": "cut", "x_mm": 120, "y_mm": 100, "depth_mm": 4},
            {"kind": "retract", "x_mm": 120, "y_mm": 100},
        ],
        safe_z=20,
        home=(10, 10, 40),
    )
    second = _path(
        [(200, 200), (220, 200)],
        [
            {"kind": "travel", "x_mm": 200, "y_mm": 200},
            {"kind": "plunge", "x_mm": 200, "y_mm": 200, "depth_mm": 6},
            {"kind": "cut", "x_mm": 220, "y_mm": 200, "depth_mm": 6},
            {"kind": "retract", "x_mm": 220, "y_mm": 200},
        ],
        safe_z=15,
        home=(0, 2440, 120),
    )
    second["path_key"] = "path-2"
    text = _export(_program(first, second))["text"]
    assert "Z20.0000" in text
    assert "Z15.0000" in text
    assert text.count("Y2440.0000") == 1
    assert "X10.0000 Y10.0000" not in text


def test_modal_program_matches_the_intermediate_cuts_and_ignores_g53():
    program = _reference_program()
    placed = apply_placement_to_program(program, _placement())
    text = _export(program)["text"]
    state = interpret_nc(text, safe_z_mm=20, allowed_safe_z_mm=(20, 120))
    assert state.units == "mm"
    assert state.distance_mode == "G90"
    assert state.work_offset == "G54"
    assert state.tool_number == "T9"
    assert state.spindle_speed_rpm == 15000
    assert state.ended is True
    assert state.unsafe_rapids == ()
    cuts = [motion for motion in state.motions if motion.kind == "cut"]
    assert [(round(motion.x_mm, 4), round(motion.y_mm, 4)) for motion in cuts] == [
        (400.0, 850.0),
        (420.0, 850.0),
    ]
    assert all(abs(motion.z_mm + 10) < 0.001 for motion in cuts)
    assert state.machine_moves[-1].x_mm == 1500.0
    assert state.machine_moves[-1].y_mm == 3500.0
    assert state.max_x < 1500
    verification = verify_nc_against_program(text, placed, safe_z_mm=20)
    assert verification.ok is True
    assert verification.matched_cuts == 2
    assert verification.matched_plunges == 1


def test_reversed_and_separate_motion_order_is_preserved():
    forward = _reference_program()
    reversed_path = _path(
        [(320, 800), (300, 500)],
        [
            {"kind": "travel", "x_mm": 320, "y_mm": 800},
            {"kind": "plunge", "x_mm": 320, "y_mm": 800, "depth_mm": 10},
            {"kind": "cut", "x_mm": 300, "y_mm": 500, "depth_mm": 10},
            {"kind": "cut", "x_mm": 300, "y_mm": 800, "depth_mm": 10},
            {"kind": "retract", "x_mm": 300, "y_mm": 800},
        ],
    )
    reversed_text = _export(_program(reversed_path))["text"]
    forward_text = _export(forward)["text"]

    def cut_xy(text):
        state = interpret_nc(text, safe_z_mm=20, allowed_safe_z_mm=(20, 120))
        return [(round(motion.x_mm, 4), round(motion.y_mm, 4)) for motion in state.motions if motion.kind == "cut"]

    assert cut_xy(forward_text) == [(400.0, 850.0), (420.0, 850.0)]
    assert cut_xy(reversed_text) == [(400.0, 550.0), (400.0, 850.0)]
    separate = _program(
        _path(
            [(100, 100), (140, 100)],
            [
                {"kind": "travel", "x_mm": 100, "y_mm": 100},
                {"kind": "plunge", "x_mm": 100, "y_mm": 100, "depth_mm": 3},
                {"kind": "cut", "x_mm": 140, "y_mm": 100, "depth_mm": 3},
                {"kind": "retract", "x_mm": 140, "y_mm": 100},
            ],
            home=(0, 1000, 80),
        ),
        _path(
            [(200, 200), (260, 200)],
            [
                {"kind": "travel", "x_mm": 200, "y_mm": 200},
                {"kind": "plunge", "x_mm": 200, "y_mm": 200, "depth_mm": 3},
                {"kind": "cut", "x_mm": 260, "y_mm": 200, "depth_mm": 3},
                {"kind": "retract", "x_mm": 260, "y_mm": 200},
            ],
            home=(0, 2440, 120),
        ),
    )
    separate["operations"][0]["toolpaths"][1]["path_key"] = "path-2"
    package = _export(separate)
    assert package["verification"]["ok"] is True
    assert package["verification"]["matched_cuts"] == 2
    assert package["text"].count("G0 Z20.0000") >= 2


def test_parking_and_home_outside_the_machine_are_refused():
    program = _reference_program()
    with pytest.raises(PostProcessorError) as parking:
        _export(program, _placement(machine=_machine(width_cm=140, length_cm=280), sheet_width_cm=100, sheet_length_cm=200, offset_left_cm=0, offset_bottom_cm=0))
    assert parking.value.code == "machine_parking_outside_limits"
    placed = apply_placement_to_program(program, _placement())
    with pytest.raises(PostProcessorError) as missing_home:
        path = dict(placed["operations"][0]["toolpaths"][0])
        path["home"] = {}
        placed["operations"][0]["toolpaths"][0] = path
        emit_ima_wh(placed, machine_width_mm=1600, machine_length_mm=3600)
    assert missing_home.value.code == "profile_home_missing"


def test_post_does_not_touch_dxf_perimeter_or_association_engines():
    for relative in (
        "almdina_erp/infrastructure/cutting/cnc_dxf_source.py",
        "almdina_erp/services/dxf_export_service.py",
        "almdina_erp/domain/cnc/perimeter.py",
        "almdina_erp/domain/cnc/artcam_machining.py",
        "almdina_erp/domain/cutting/dxf_geometry.py",
    ):
        assert "ima_wh" not in (ROOT / relative).read_text(encoding="utf-8")
    export_source = (ROOT / "almdina_erp/application/cnc/nc_export.py").read_text(encoding="utf-8")
    builder = export_source.split("def build_post_processed_nc", 1)[1].split("def ", 1)[0]
    assert "save_file" not in builder
    assert "open(" not in builder


def test_xy_rapid_at_cutting_depth_is_rejected_by_the_interpreter():
    unsafe = "\r\n".join(
        [
            "G90",
            "G54",
            "T9",
            "M3 S15000",
            "N60 G0 X10.0000 Y10.0000 Z20.0000",
            "N70 G1 Z-10.0000 F1800.0",
            "N80 G0 X20.0000 Y10.0000",
            "M30",
        ]
    )
    state = interpret_nc(unsafe, safe_z_mm=20)
    assert "rapid_inside_material" in state.unsafe_rapids
