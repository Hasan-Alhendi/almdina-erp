"""Facing-gap compensation when a machining tool extends past a door.

The recorded door size and the machining centerline stay as they are. Only the
gap that the tool actually enters grows, and the saw centers have to sweep it.
"""

from __future__ import annotations

from copy import deepcopy

from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
    SAW_CENTER_INVALID,
    SAW_CENTER_MATCH,
    classify_saw_center_segments,
    clearing_centers_mm,
    cutter_center_segments,
    swept_covers_gap,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    point_in_polygon,
    point_to_polygon_distance,
)
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    liner_toolpath_mm,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_clearance import (
    apply_machining_clearance,
    mark_unresolved_clearance,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import generate_toolpath as overlay_toolpath
from almdina_erp.almdina_erp.domain.cutting.optimizer import optimize_plan
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.registry import STRATEGIES

KERF_CM = 0.5
CUTTER_MM = 5.0


def _diameters(**overrides: float) -> dict[str, float]:
    values = {
        "kerf_mm": CUTTER_MM,
        "liner": CUTTER_MM,
        "liner_tool_diameter_mm": CUTTER_MM,
        "back_groove": CUTTER_MM,
        "rear_groove_tool_diameter_mm": CUTTER_MM,
        "recessed_handle_cutout": CUTTER_MM,
        "handle_recess_tool_diameter_mm": CUTTER_MM,
    }
    values.update(overrides)
    for kind, field in (
        ("liner", "liner_tool_diameter_mm"),
        ("back_groove", "rear_groove_tool_diameter_mm"),
        ("recessed_handle_cutout", "handle_recess_tool_diameter_mm"),
    ):
        if kind in overrides and field not in overrides:
            values[field] = overrides[kind]
        if field in overrides and kind not in overrides:
            values[kind] = overrides[field]
    return values


def _door(
    piece_id: int,
    x: float,
    y: float,
    width: float = 40.0,
    length: float = 30.0,
    **machining: object,
) -> dict:
    door = {
        "id": piece_id,
        "label": f"D{piece_id}",
        "x": x,
        "y": y,
        "w": width,
        "h": length,
        "original_w": width,
        "original_h": length,
        "piece_type": "Regular",
        "rotated": False,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    door.update(machining)
    return door


def _liner(side: str, width: float, length: float, start: float = 0.0, strip: float = 1.2) -> dict:
    return {
        "extra_liner": 1,
        "liner_reference_side": side,
        "liner_offset_cm": 0,
        "liner_width_cm": strip,
        "liner_start_cm": start,
        "liner_length_cm": length,
    }


def _groove(side: str, width: float, length: float, start: float = 0.0, strip: float = 1.2) -> dict:
    return {
        "extra_back_groove": 1,
        "back_groove_reference_side": side,
        "back_groove_offset_cm": 0,
        "back_groove_width_cm": strip,
        "back_groove_start_cm": start,
        "back_groove_length_cm": length,
    }


def _handle(side: str, width: float, length: float, start: float = 0.0, strip: float = 1.2) -> dict:
    return {
        "extra_recessed_handle_cutout": 1,
        "recessed_handle_reference_side": side,
        "recessed_handle_offset_cm": 0,
        "recessed_handle_width_cm": strip,
        "recessed_handle_start_cm": start,
        "recessed_handle_length_cm": length,
    }


def _plan(doors: list[dict], board_w: float, board_h: float) -> dict:
    return {
        "sheets": [{
            "sheet_no": 1,
            "w": board_w,
            "h": board_h,
            "pieces": doors,
        }],
        "unplaced": [],
    }


def _requested(doors: list[dict]) -> list[dict]:
    return [
        {
            "id": door["id"],
            "label": door["label"],
            "width_cm": door["original_w"],
            "length_cm": door["original_h"],
            "allow_rotation": 0,
        }
        for door in doors
    ]


def _gap(first: dict, second: dict, axis: str) -> float:
    if axis == "x":
        left, right = (first, second) if first["x"] <= second["x"] else (second, first)
        return right["x"] - (left["x"] + left["w"])
    top, bottom = (first, second) if first["y"] <= second["y"] else (second, first)
    return bottom["y"] - (top["y"] + top["h"])


def _apply(doors: list[dict], diameters: dict | None, board_w: float, board_h: float):
    plan = _plan(doors, board_w, board_h)
    return apply_machining_clearance(
        plan,
        kerf_cm=KERF_CM,
        board_w_cm=board_w,
        board_h_cm=board_h,
        diameters=diameters,
    )


def _local_path(door: dict, kind: str, diameter: float) -> list[tuple[float, float]]:
    piece = LinerPiece("Regular", door["original_w"], door["original_h"])
    if kind == "liner":
        side = door["liner_reference_side"]
        offset = door["liner_offset_cm"]
        width = door["liner_width_cm"]
        start = door["liner_start_cm"]
        length = door["liner_length_cm"]
    elif kind == "back_groove":
        side = door["back_groove_reference_side"]
        offset = door["back_groove_offset_cm"]
        width = door["back_groove_width_cm"]
        start = door["back_groove_start_cm"]
        length = door["back_groove_length_cm"]
    else:
        side = door["recessed_handle_reference_side"]
        offset = door["recessed_handle_offset_cm"]
        width = door["recessed_handle_width_cm"]
        start = door["recessed_handle_start_cm"]
        length = door["recessed_handle_length_cm"]
    return overlay_toolpath(
        kind=kind,
        piece=piece,
        reference_side=side,
        offset_cm=offset,
        width_cm=width,
        start_cm=start,
        length_cm=length,
        cutter_diameter_mm=diameter,
    )


def _assert_sizes_and_path(before: dict, after: dict, kind: str, diameter: float) -> None:
    assert (after["w"], after["h"], after["original_w"], after["original_h"]) == (
        before["w"], before["h"], before["original_w"], before["original_h"],
    )
    assert _local_path(after, kind, diameter) == _local_path(before, kind, diameter)


def _slot_centers(segments, origin: float, gap: float, along: str) -> list[float]:
    centers = []
    for start, end in segments:
        if along == "x":
            if abs(start[0] - end[0]) > 0.05 or abs(end[1] - start[1]) < gap:
                continue
            center = (start[0] + end[0]) / 2.0
        else:
            if abs(start[1] - end[1]) > 0.05 or abs(end[0] - start[0]) < gap:
                continue
            center = (start[1] + end[1]) / 2.0
        if origin - 0.05 <= center <= origin + gap + 0.05:
            centers.append(center - origin)
    unique = sorted({round(center, 4) for center in centers})
    return unique


def _assert_gap_swept(segments, origin: float, gap: float, diameter: float, along: str) -> None:
    centers = _slot_centers(segments, origin, gap, along)
    assert swept_covers_gap(centers, gap, diameter)
    radius = diameter / 2.0
    station = 0.0
    while station <= gap + 1e-9:
        assert any(abs(station - center) <= radius + 1e-6 for center in centers)
        station += 0.1
    ordered = sorted(centers)
    for previous, current in zip(ordered, ordered[1:]):
        overlap = (previous + radius) - (current - radius)
        assert overlap + 1e-6 >= 0.5
    assert all(radius - 1e-6 <= center <= gap - radius + 1e-6 for center in centers)


def _shapes(doors: list[dict]) -> list[tuple]:
    shapes = []
    for door in doors:
        x = door["x"] * 10.0
        y = door["y"] * 10.0
        w = door["w"] * 10.0
        h = door["h"] * 10.0
        shapes.append(([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], []))
    return shapes


def _assert_paths_stay_out_of_doors(segments, shapes) -> None:
    for start, end in segments:
        for step in range(5):
            weight = step / 4.0
            point = (
                start[0] + (end[0] - start[0]) * weight,
                start[1] + (end[1] - start[1]) * weight,
            )
            for outer, _holes in shapes:
                if point_in_polygon(point, outer) and point_to_polygon_distance(point, outer) > 0.05:
                    raise AssertionError(f"saw center {point} enters a door")


def test_clearing_centers_cover_the_slot_and_reject_a_mere_division():
    assert clearing_centers_mm(8, 5) == [2.5, 5.5]
    assert clearing_centers_mm(10, 5) == [2.5, 5.0, 7.5]
    assert clearing_centers_mm(5, 5) == [2.5]
    assert clearing_centers_mm(4, 5) == []
    assert not swept_covers_gap([2.5, 7.5], 10, 5)
    assert swept_covers_gap(clearing_centers_mm(9.6, 5), 9.6, 5)
    tight = clearing_centers_mm(9.5, 5)
    assert len(tight) == 2
    assert swept_covers_gap(tight, 9.5, 5)


def test_no_extension_leaves_the_kerf_gap_untouched():
    doors = [
        _door(1, 0, 0),
        _door(2, 40 + KERF_CM, 0),
    ]
    original = deepcopy(doors)
    applied = _apply(doors, _diameters(liner=8), 120, 80)
    assert applied is not None
    placed = applied["sheets"][0]["pieces"]
    assert _gap(placed[0], placed[1], "x") == KERF_CM
    assert [(door["x"], door["y"]) for door in placed] == [(door["x"], door["y"]) for door in original]
    segments = cutter_center_segments(_shapes(placed), CUTTER_MM / 2)
    limited = cutter_center_segments(_shapes(placed), CUTTER_MM / 2, clearance_limit_mm=8)
    assert limited == segments


def test_internal_liner_does_not_widen_a_neighbor():
    doors = [
        _door(1, 0, 0, **_liner("edge_width_top", 40, 20, start=10)),
        _door(2, 40 + KERF_CM, 0),
    ]
    before = _local_path(doors[0], "liner", 8)
    applied = _apply(doors, _diameters(liner=8), 120, 80)
    placed = applied["sheets"][0]["pieces"]
    assert _gap(placed[0], placed[1], "x") == KERF_CM
    assert _local_path(placed[0], "liner", 8) == before


def test_liner_wider_than_the_saw_opens_only_that_gap_and_the_saw_clears_it():
    doors = [
        _door(1, 0, 0, **_liner("edge_width_top", 40, 40)),
        _door(2, 40 + KERF_CM, 0),
    ]
    before = deepcopy(doors)
    applied = _apply(doors, _diameters(liner=8), 120, 80)
    placed = applied["sheets"][0]["pieces"]
    assert abs(_gap(placed[0], placed[1], "x") - 0.8) < 1e-6
    _assert_sizes_and_path(before[0], placed[0], "liner", 8)
    _assert_sizes_and_path(before[1], placed[1], "liner", 8) if placed[1].get("extra_liner") else None
    assert (placed[1]["w"], placed[1]["h"]) == (40, 30)
    segments = cutter_center_segments(_shapes(placed), CUTTER_MM / 2, clearance_limit_mm=8)
    left = min(placed, key=lambda door: door["x"])
    _assert_gap_swept(segments, (left["x"] + left["w"]) * 10, 8, CUTTER_MM, "x")
    _assert_paths_stay_out_of_doors(segments, _shapes(placed))
    assert validate_plan(applied, _requested(placed), 120, 80, kerf_cm=KERF_CM) == []


def test_back_groove_uses_the_same_clearance_and_coverage():
    doors = [
        _door(1, 0, 0, **_groove("edge_width_top", 40, 40)),
        _door(2, 40 + KERF_CM, 0),
    ]
    before = deepcopy(doors[0])
    applied = _apply(doors, _diameters(back_groove=8), 120, 80)
    placed = applied["sheets"][0]["pieces"]
    assert abs(_gap(placed[0], placed[1], "x") - 0.8) < 1e-6
    _assert_sizes_and_path(before, placed[0], "back_groove", 8)
    segments = cutter_center_segments(_shapes(placed), CUTTER_MM / 2, clearance_limit_mm=8)
    left = min(placed, key=lambda door: door["x"])
    _assert_gap_swept(segments, (left["x"] + left["w"]) * 10, 8, CUTTER_MM, "x")


def test_dip_handle_ten_millimetres_needs_three_saw_passes():
    doors = [
        _door(1, 0, 0, **_handle("edge_width_top", 40, 40, strip=1.2)),
        _door(2, 40 + KERF_CM, 0),
    ]
    before = deepcopy(doors[0])
    applied = _apply(doors, _diameters(recessed_handle_cutout=10), 120, 80)
    placed = applied["sheets"][0]["pieces"]
    assert abs(_gap(placed[0], placed[1], "x") - 1.0) < 1e-6
    _assert_sizes_and_path(before, placed[0], "recessed_handle_cutout", 10)
    segments = cutter_center_segments(_shapes(placed), CUTTER_MM / 2, clearance_limit_mm=10)
    left = min(placed, key=lambda door: door["x"])
    centers = _slot_centers(segments, (left["x"] + left["w"]) * 10, 10, "x")
    assert centers == [2.5, 5.0, 7.5]
    _assert_gap_swept(segments, (left["x"] + left["w"]) * 10, 10, CUTTER_MM, "x")
    plain = cutter_center_segments(_shapes(placed), CUTTER_MM / 2)
    assert classify_saw_center_segments(segments, segments) == SAW_CENTER_MATCH
    assert classify_saw_center_segments(segments, plain) == SAW_CENTER_INVALID


def test_equal_or_smaller_tool_does_not_increase_the_gap():
    for diameter in (5, 4):
        doors = [
            _door(1, 0, 0, **_liner("edge_width_top", 40, 40)),
            _door(2, 40 + KERF_CM, 0),
        ]
        snapshot = [(door["x"], door["y"]) for door in doors]
        applied = _apply(doors, _diameters(liner=diameter), 120, 80)
        placed = applied["sheets"][0]["pieces"]
        assert [(door["x"], door["y"]) for door in placed] == snapshot
        assert _gap(placed[0], placed[1], "x") == KERF_CM


def test_two_tools_on_one_gap_use_the_larger_diameter_only():
    doors = [
        _door(
            1, 0, 0,
            **_liner("edge_width_top", 40, 40),
            **_groove("edge_width_top", 40, 40),
        ),
        _door(2, 40 + KERF_CM, 0),
    ]
    applied = _apply(doors, _diameters(liner=8, back_groove=10), 120, 80)
    placed = applied["sheets"][0]["pieces"]
    assert abs(_gap(placed[0], placed[1], "x") - 1.0) < 1e-6
    assert abs(_gap(placed[0], placed[1], "x") - (0.8 + 0.5)) > 0.1


def test_extension_on_one_end_widens_only_that_neighbor():
    doors = [
        _door(1, 0, 0),
        _door(2, 40 + KERF_CM, 0, **_liner("edge_width_top", 40, 20, start=0)),
        _door(3, 80 + 2 * KERF_CM, 0),
    ]
    applied = _apply(doors, _diameters(liner=8), 160, 80)
    placed = {door["id"]: door for door in applied["sheets"][0]["pieces"]}
    assert abs(_gap(placed[1], placed[2], "x") - KERF_CM) < 1e-6 or abs(
        _gap(placed[2], placed[3], "x") - KERF_CM
    ) < 1e-6
    gaps = sorted([
        round(_gap(placed[1], placed[2], "x"), 4),
        round(_gap(placed[2], placed[3], "x"), 4),
    ])
    assert gaps == [0.5, 0.8]


def test_extensions_on_two_sides_widen_each_facing_gap_independently():
    center = _door(
        1, 0, 0,
        **_liner("edge_width_top", 40, 40),
        **_groove("edge_long_left", 30, 30),
    )
    right = _door(2, 40 + KERF_CM, 0)
    below = _door(3, 0, 30 + KERF_CM)
    before = deepcopy(center)
    applied = _apply([center, right, below], _diameters(liner=8, back_groove=10), 120, 90)
    placed = {door["id"]: door for door in applied["sheets"][0]["pieces"]}
    assert abs(_gap(placed[1], placed[2], "x") - 0.8) < 1e-6
    assert abs(_gap(placed[1], placed[3], "y") - 1.0) < 1e-6
    _assert_sizes_and_path(before, placed[1], "liner", 8)
    assert _local_path(placed[1], "back_groove", 10) == _local_path(before, "back_groove", 10)


def test_only_the_affected_gap_in_a_row_grows():
    doors = [
        _door(1, 0, 0, **_liner("edge_width_top", 40, 40)),
        _door(2, 40 + KERF_CM, 0, **_liner("edge_width_top", 40, 20, start=0)),
        _door(3, 80 + 2 * KERF_CM, 0),
    ]
    applied = _apply(doors, _diameters(liner=8), 200, 80)
    placed = {door["id"]: door for door in applied["sheets"][0]["pieces"]}
    widened = round(_gap(placed[1], placed[2], "x"), 4)
    untouched = round(_gap(placed[2], placed[3], "x"), 4)
    assert widened == 0.8
    assert untouched == 0.5
    assert abs((placed[1]["w"] + placed[2]["w"] + placed[3]["w"]) - 120) < 1e-6


def test_different_diameters_in_one_order_stay_on_their_own_gaps():
    center = _door(1, 0, 0, **_liner("edge_width_top", 40, 40))
    right = _door(2, 40 + KERF_CM, 0)
    below = _door(3, 0, 30 + KERF_CM, **_handle("edge_long_left", 30, 30))
    applied = _apply(
        [center, right, below],
        _diameters(liner=8, recessed_handle_cutout=10),
        120, 90,
    )
    placed = {door["id"]: door for door in applied["sheets"][0]["pieces"]}
    assert abs(_gap(placed[1], placed[2], "x") - 0.8) < 1e-6
    assert abs(_gap(placed[1], placed[3], "y") - 1.0) < 1e-6


def test_a_flush_board_is_rejected_without_moving_the_doors():
    doors = [
        _door(1, 0, 0, **_liner("edge_width_top", 40, 40)),
        _door(2, 40 + KERF_CM, 0),
    ]
    snapshot = [(door["x"], door["y"]) for door in doors]
    board_w = 40 + KERF_CM + 40
    applied = _apply(doors, _diameters(liner=8), board_w, 30)
    assert applied is None
    assert [(door["x"], door["y"]) for door in doors] == snapshot
    marked = mark_unresolved_clearance(
        _plan(doors, board_w, 30),
        kerf_cm=KERF_CM,
        diameters=_diameters(liner=8),
    )
    errors = validate_plan(marked, _requested(doors), board_w, 30, kerf_cm=KERF_CM)
    assert any("machining clearance" in error for error in errors)
    assert marked["machining_clearance_unresolved"] is True
    historical = _plan(doors, board_w, 30)
    assert validate_plan(historical, _requested(doors), board_w, 30, kerf_cm=KERF_CM) == []


def test_missing_diameters_leave_an_old_plan_unchanged():
    doors = [
        _door(1, 0, 0, **_liner("edge_width_top", 40, 40)),
        _door(2, 40 + KERF_CM, 0),
    ]
    plan = _plan(doors, 120, 80)
    assert apply_machining_clearance(
        plan, kerf_cm=KERF_CM, board_w_cm=120, board_h_cm=80, diameters=None,
    ) is plan
    assert _gap(plan["sheets"][0]["pieces"][0], plan["sheets"][0]["pieces"][1], "x") == KERF_CM


def test_nested_layout_opens_the_gap_after_shop_floor_placement():
    pieces = expand_piece_groups([{
        "width_cm": 30,
        "length_cm": 40,
        "qty": 2,
        "allow_rotation": 0,
        **_liner("edge_width_top", 30, 30),
    }])
    strategy = next(item for item in STRATEGIES if item.key == "MaxRects Best Short Side")
    packed = strategy.execute(pieces, 100, 40, KERF_CM)
    before = _local_path(packed["sheets"][0]["pieces"][0], "liner", 8)
    applied = apply_machining_clearance(
        packed,
        kerf_cm=KERF_CM,
        board_w_cm=100,
        board_h_cm=40,
        diameters=_diameters(liner=8),
    )
    assert applied is not None
    placed = applied["sheets"][0]["pieces"]
    assert len(placed) == 2
    assert abs(_gap(placed[0], placed[1], "x") - 0.8) < 1e-6
    assert _local_path(placed[0], "liner", 8) == before
    assert validate_plan(applied, pieces, 100, 40, kerf_cm=KERF_CM) == []
    segments = cutter_center_segments(_shapes(placed), CUTTER_MM / 2, clearance_limit_mm=8)
    left = min(placed, key=lambda door: door["x"])
    _assert_gap_swept(segments, (left["x"] + left["w"]) * 10, 8, CUTTER_MM, "x")
    _assert_paths_stay_out_of_doors(segments, _shapes(placed))


def test_optimizer_reports_a_board_that_cannot_hold_the_gap():
    pieces = expand_piece_groups([{
        "width_cm": 40,
        "length_cm": 30,
        "qty": 2,
        "allow_rotation": 0,
        **_liner("edge_width_top", 40, 40),
    }])
    board_w = 40 + KERF_CM + 40
    plan = optimize_plan(
        pieces,
        board_w,
        30,
        KERF_CM,
        selected_mode="MaxRects Best Short Side",
        time_limit_sec=0.2,
        machining_diameters_mm=_diameters(liner=8),
    )
    assert plan.get("machining_clearance_unresolved") is True
    errors = validate_plan(plan, pieces, board_w, 30, kerf_cm=KERF_CM)
    assert any("machining clearance" in error for error in errors)
    placed = [door for sheet in plan["sheets"] for door in sheet["pieces"]]
    if len(placed) == 2 and abs(placed[0]["y"] - placed[1]["y"]) < 1:
        assert _gap(placed[0], placed[1], "x") < 0.8


def test_tool_disk_reaches_the_neighbor_at_the_new_gap_and_not_beyond_it():
    door = _door(1, 0, 0, **_liner("edge_width_top", 40, 40))
    path = _local_path(door, "liner", 8)
    width_mm = 400.0
    furthest = max(point[0] for point in path)
    assert furthest > width_mm
    assert abs((furthest + 4.0) - (width_mm + 8.0)) < 0.2
    neighbor_at_kerf = width_mm + 5.0
    assert furthest + 4.0 > neighbor_at_kerf + 0.2
    neighbor_at_clearance = width_mm + 8.0
    assert furthest + 4.0 <= neighbor_at_clearance + 0.05


def test_guest_inside_a_moved_host_keeps_the_same_offset():
    host = _door(2, 40 + KERF_CM, 0)
    guest = {
        "id": 9,
        "label": "G9",
        "x": host["x"] + 2,
        "y": host["y"] + 2,
        "w": 5,
        "h": 5,
        "original_w": 5,
        "original_h": 5,
        "piece_type": "Glass",
        "rotated": False,
        "glass_host_piece_id": host["id"],
    }
    doors = [_door(1, 0, 0, **_liner("edge_width_top", 40, 40)), host, guest]
    offset = guest["x"] - host["x"]
    applied = _apply(doors, _diameters(liner=8), 160, 80)
    placed = {door["id"]: door for door in applied["sheets"][0]["pieces"]}
    assert abs((placed[9]["x"] - placed[2]["x"]) - offset) < 1e-6
    assert abs(_gap(placed[1], placed[2], "x") - 0.8) < 1e-6


def test_generate_toolpath_import_matches_the_overlay_used_above():
    piece = LinerPiece("Regular", 40, 30)
    direct = liner_toolpath_mm(piece, "edge_width_top", 0, 1.2, 8, 0, 40)
    wrapped = overlay_toolpath(
        kind="liner",
        piece=piece,
        reference_side="edge_width_top",
        offset_cm=0,
        width_cm=1.2,
        start_cm=0,
        length_cm=40,
        cutter_diameter_mm=8,
    )
    assert direct == wrapped
    moved = transform_point((direct[0][0], direct[0][1]), mirrored=False, quarter_turns=0, width=400, height=300)
    assert moved == direct[0]
