"""Rigid nest translation and board consolidation after shape nesting."""

from __future__ import annotations

import time

from almdina_erp.almdina_erp.domain.cutting import expand_piece_groups, validate_plan
from almdina_erp.almdina_erp.domain.cutting.evaluation import placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    GLASS_HOST_PIECE_ID,
    material_outline_cm,
)
from almdina_erp.almdina_erp.domain.cutting.nesting_consolidation import (
    CLIPPED_PAIR,
    CLIPPED_QUAD,
    GLASS_HOST,
    L_PAIR,
    L_QUAD,
    SINGLE_CORNER,
    consolidate_nested_boards,
    extract_placement_groups,
)
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.plan_search import improve_plan_search
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import (
    _placed_corner,
    _recorded_facing,
    apply_shape_aware_nesting,
)


_REMNANT = {
    "min_remnant_width_cm": 30,
    "min_remnant_length_cm": 30,
    "min_remnant_area_m2": 0.09,
}


def _corner_row(piece_type, **extra):
    row = {
        "piece_type": piece_type,
        "width_cm": 40,
        "length_cm": 40,
        "qty": 2,
        "clipped_corner_position": "Top Right",
        "clipped_corner_width_cm": 16,
        "clipped_corner_length_cm": 16,
        "allow_rotation": 1,
        "edge_long_left": 1,
        "extra_liner": 1,
        "liner_reference_side": "edge_long_left",
        "liner_offset_cm": 1,
        "liner_width_cm": 2,
        "liner_start_cm": 0,
        "liner_length_cm": 10,
    }
    row.update(extra)
    return row


def _regular(width, height, **extra):
    row = {
        "piece_type": "Regular",
        "width_cm": width,
        "length_cm": height,
        "qty": 1,
        "allow_rotation": 0,
    }
    row.update(extra)
    return row


def _apply(plan, pieces, board_w, board_h, mirroring_allowed=False):
    return apply_shape_aware_nesting(
        plan,
        pieces,
        board_w,
        board_h,
        0.3,
        mirroring_allowed=mirroring_allowed,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )


def _metrics(sheets, board_w, board_h):
    return enrich_plan_metrics(
        {
            "sheets": sheets,
            "unplaced": [],
            "method_key": "MaxRects Best Short Side",
        },
        "MaxRects Best Short Side",
        "CNC Router",
        **_REMNANT,
    )


def _separate_plan(pieces, board_w, board_h):
    sheets = []
    for index, piece in enumerate(pieces, start=1):
        sheets.append(
            {
                "sheet_no": index,
                "w": board_w,
                "h": board_h,
                "pieces": [
                    make_placed_piece(
                        piece,
                        0,
                        0,
                        piece["width_cm"],
                        piece["length_cm"],
                        False,
                    )
                ],
            }
        )
    return _metrics(sheets, board_w, board_h)


def _consolidate(plan, pieces, board_w, board_h, mirroring_allowed=False, budget=2.0):
    return consolidate_nested_boards(
        plan,
        pieces,
        board_w,
        board_h,
        0.3,
        machine_type="CNC Router",
        mirroring_allowed=mirroring_allowed,
        deadline=time.monotonic() + budget,
    )


def _offsets(pieces):
    origin_x = min(piece["x"] for piece in pieces)
    origin_y = min(piece["y"] for piece in pieces)
    rows = []
    for piece in pieces:
        outline = material_outline_cm(piece) or ()
        relative = tuple(
            (round(point[0] - origin_x, 2), round(point[1] - origin_y, 2)) for point in outline
        )
        rows.append(
            (
                int(piece["id"]),
                round(piece["x"] - origin_x, 2),
                round(piece["y"] - origin_y, 2),
                int(piece.get("corner_rotation_quarter_turns") or 0),
                bool(piece.get("mirrored") or piece.get("corner_mirrored")),
                round(float(piece.get("placement_rotation_deg") or 0), 2),
                piece.get(GLASS_HOST_PIECE_ID),
                tuple(tuple(point) for point in piece.get("glass_hole_local_mm") or ()),
                relative,
            )
        )
    return tuple(sorted(rows))


def _ids_on(plan, wanted):
    found = []
    for sheet in plan["sheets"]:
        for piece in sheet["pieces"]:
            if int(piece["id"]) in wanted:
                found.append(piece)
    return found


def _sheet_count_for(plan, wanted):
    numbers = {
        int(sheet["sheet_no"])
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
        if int(piece["id"]) in wanted
    }
    return numbers


def _nested_pair(piece_type, board_w, board_h, **extra):
    pieces = expand_piece_groups([_corner_row(piece_type, **extra)])
    nested = _apply(_separate_plan(pieces, board_w, board_h), pieces, board_w, board_h)
    assert len(nested["sheets"]) == 1
    assert not validate_plan(nested, pieces, board_w, board_h, kerf_cm=0.3)
    return pieces, nested["sheets"][0]["pieces"]


def test_same_facing_corners_are_not_a_pair():
    pieces = expand_piece_groups([_corner_row("L-Shaped Corner", qty=2)])
    placed = [
        _placed_corner(piece, x_cm=index * 40.3, y_cm=0, mirrored=False, turns=0)
        for index, piece in enumerate(pieces)
    ]
    plan = _metrics([{"sheet_no": 1, "w": 160, "h": 80, "pieces": placed}], 160, 80)
    kinds = [group.kind for group in extract_placement_groups(plan)]

    assert L_PAIR not in kinds
    assert L_QUAD not in kinds
    assert kinds.count(SINGLE_CORNER) == 2
    assert _recorded_facing(placed[0]) == _recorded_facing(placed[1])


def test_l_pair_translates_onto_the_occupied_board_and_drops_the_empty_one():
    corners = expand_piece_groups([_corner_row("L-Shaped Corner", qty=2)])
    blocker = expand_piece_groups([_regular(30, 30)])[0]
    blocker["id"] = 3
    blocker["label"] = "3.1"
    blocker["source_piece_no"] = 3
    nested = _apply(_separate_plan(corners, 180, 120), corners, 180, 120)
    pair = [dict(piece) for piece in nested["sheets"][0]["pieces"]]
    before = _offsets(pair)
    assert _recorded_facing(pair[0]) != _recorded_facing(pair[1])
    origin_x = min(piece["x"] for piece in pair)
    origin_y = min(piece["y"] for piece in pair)
    occupied = _metrics(
        [
            {
                "sheet_no": 1,
                "w": 180,
                "h": 120,
                "pieces": [make_placed_piece(blocker, origin_x, origin_y, 30, 30, False)],
            },
            {"sheet_no": 2, "w": 180, "h": 120, "pieces": pair},
        ],
        180,
        120,
    )
    improved = _consolidate(occupied, [*corners, blocker], 180, 120)

    moved = _ids_on(improved, {1, 2})
    assert len(improved["sheets"]) == 1
    assert _sheet_count_for(improved, {1, 2}) == {1}
    assert _offsets(moved) == before
    assert moved[0]["edge_long_left"] == 1
    assert moved[0]["liner_reference_side"] == "edge_long_left"
    assert not validate_plan(improved, [*corners, blocker], 180, 120, kerf_cm=0.3)
    assert not placement_permission_errors(improved, [*corners, blocker], mirroring_allowed=False)
    assert any(group.kind == L_PAIR for group in extract_placement_groups(improved))
    searched = improve_plan_search(
        occupied,
        [*corners, blocker],
        180,
        120,
        0.3,
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
        **_REMNANT,
    )
    assert len(searched["sheets"]) == 1
    assert _offsets(_ids_on(searched, {1, 2})) == before


def test_l_quad_translates_without_changing_corner_directions():
    corners = expand_piece_groups([_corner_row("L-Shaped Corner", qty=4, width_cm=20, length_cm=20, clipped_corner_width_cm=8, clipped_corner_length_cm=8)])
    blocker = expand_piece_groups([_regular(20, 20)])[0]
    blocker["id"] = 5
    blocker["label"] = "5.1"
    blocker["source_piece_no"] = 5
    nested = _apply(_separate_plan(corners, 120, 120), corners, 120, 120)
    quad = [dict(piece) for piece in nested["sheets"][0]["pieces"] if piece["piece_type"] == "L-Shaped Corner"]
    assert len(quad) == 4
    before = _offsets(quad)
    turns = {int(piece.get("corner_rotation_quarter_turns") or 0) for piece in quad}
    origin_x = min(piece["x"] for piece in quad)
    origin_y = min(piece["y"] for piece in quad)
    occupied = _metrics(
        [
            {
                "sheet_no": 1,
                "w": 120,
                "h": 120,
                "pieces": [make_placed_piece(blocker, origin_x, origin_y, 20, 20, False)],
            },
            {"sheet_no": 2, "w": 120, "h": 120, "pieces": quad},
        ],
        120,
        120,
    )
    improved = _consolidate(occupied, [*corners, blocker], 120, 120)

    moved = _ids_on(improved, {1, 2, 3, 4})
    assert len(improved["sheets"]) == 1
    assert _offsets(moved) == before
    assert {int(piece.get("corner_rotation_quarter_turns") or 0) for piece in moved} == turns
    assert turns == {0, 1, 2, 3}
    assert any(group.kind == L_QUAD for group in extract_placement_groups(improved))
    assert not validate_plan(improved, [*corners, blocker], 120, 120, kerf_cm=0.3)


def test_repack_pulls_separated_pairs_into_one_cluster():
    first = expand_piece_groups([_corner_row("L-Shaped Corner", qty=2, width_cm=30, length_cm=30, clipped_corner_width_cm=12, clipped_corner_length_cm=12)])
    second_rows = expand_piece_groups([_corner_row("L-Shaped Corner", qty=2, width_cm=30, length_cm=30, clipped_corner_width_cm=12, clipped_corner_length_cm=12)])
    for piece, piece_id in zip(second_rows, (3, 4), strict=True):
        piece["id"] = piece_id
        piece["label"] = f"{piece_id}.1"
        piece["source_piece_no"] = piece_id
    left = _apply(_separate_plan(first, 140, 80), first, 140, 80)["sheets"][0]["pieces"]
    right = _apply(_separate_plan(second_rows, 140, 80), second_rows, 140, 80)["sheets"][0]["pieces"]
    left_before = _offsets(left)
    right_before = _offsets(right)
    spread = [dict(piece) for piece in left] + [
        {**piece, "x": piece["x"] + 150, "y": piece["y"]} for piece in right
    ]
    for piece in spread:
        outline = piece.get("placement_outline_cm")
        if outline and piece["id"] in {3, 4}:
            piece["placement_outline_cm"] = [(point[0] + 150, point[1]) for point in outline]
    plan = _metrics([{"sheet_no": 1, "w": 280, "h": 80, "pieces": spread}], 280, 80)
    before_area = _span(spread)
    pieces = [*first, *second_rows]
    improved = _consolidate(plan, pieces, 280, 80)
    moved_left = _ids_on(improved, {1, 2})
    moved_right = _ids_on(improved, {3, 4})

    assert len(improved["sheets"]) == 1
    assert _offsets(moved_left) == left_before
    assert _offsets(moved_right) == right_before
    assert _span(improved["sheets"][0]["pieces"]) < before_area - 1
    assert not validate_plan(improved, pieces, 280, 80, kerf_cm=0.3)


def test_glass_host_and_guests_translate_as_one_group():
    pieces = expand_piece_groups(
        [
            {
                "piece_type": "Glass",
                "width_cm": 80,
                "length_cm": 100,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 100,
            },
            _regular(10, 10),
            _regular(10, 10),
            _regular(70, 40),
        ]
    )
    glass, first, second, blocker = pieces
    guest_a = make_placed_piece(first, 20, 20, 10, 10, False)
    guest_b = make_placed_piece(second, 20, 32, 10, 10, False)
    guest_a[GLASS_HOST_PIECE_ID] = glass["id"]
    guest_b[GLASS_HOST_PIECE_ID] = glass["id"]
    host = make_placed_piece(glass, 0, 0, 80, 100, False)
    before = _offsets([host, guest_a, guest_b])
    plan = _metrics(
        [
            {
                "sheet_no": 1,
                "w": 220,
                "h": 140,
                "pieces": [make_placed_piece(blocker, 0, 0, 70, 40, False)],
            },
            {"sheet_no": 2, "w": 220, "h": 140, "pieces": [host, guest_a, guest_b]},
        ],
        220,
        140,
    )
    assert not validate_plan(plan, pieces, 220, 140, kerf_cm=0.3)
    improved = _consolidate(plan, pieces, 220, 140)
    grouped = [
        group
        for group in extract_placement_groups(improved)
        if group.kind == GLASS_HOST
    ]

    assert len(improved["sheets"]) == 1
    assert len(grouped) == 1
    assert grouped[0].piece_ids == (int(glass["id"]), int(first["id"]), int(second["id"]))
    assert grouped[0].glass_links == (
        (int(first["id"]), int(glass["id"])),
        (int(second["id"]), int(glass["id"])),
    )
    assert _offsets(_ids_on(improved, set(grouped[0].piece_ids))) == before
    assert not validate_plan(improved, pieces, 220, 140, kerf_cm=0.3)


def test_group_that_fits_nowhere_stays_put():
    corners = expand_piece_groups(
        [_corner_row("Clipped Corner", width_cm=44, length_cm=44, clipped_corner_width_cm=14, clipped_corner_length_cm=14)]
    )
    blocker = expand_piece_groups([_regular(90, 40)])[0]
    blocker["id"] = 3
    blocker["label"] = "3.1"
    blocker["source_piece_no"] = 3
    nested = _apply(_separate_plan(corners, 120, 60), corners, 120, 60)
    pair = [dict(piece) for piece in nested["sheets"][0]["pieces"]]
    before = _offsets(pair)
    before_xy = sorted((int(piece["id"]), round(piece["x"], 2), round(piece["y"], 2)) for piece in pair)
    plan = _metrics(
        [
            {
                "sheet_no": 1,
                "w": 120,
                "h": 60,
                "pieces": [make_placed_piece(blocker, 0, 0, 90, 40, False)],
            },
            {"sheet_no": 2, "w": 120, "h": 60, "pieces": pair},
        ],
        120,
        60,
    )
    improved = _consolidate(plan, [*corners, blocker], 120, 60)
    stayed = _ids_on(improved, {1, 2})

    assert len(improved["sheets"]) == 2
    assert _offsets(stayed) == before
    assert sorted((int(piece["id"]), round(piece["x"], 2), round(piece["y"], 2)) for piece in stayed) == before_xy
    assert not validate_plan(improved, [*corners, blocker], 120, 60, kerf_cm=0.3)


def test_consolidation_keeps_pair_quad_and_glass_nests():
    l_corners = expand_piece_groups(
        [_corner_row("L-Shaped Corner", qty=4, width_cm=20, length_cm=20, clipped_corner_width_cm=8, clipped_corner_length_cm=8)]
    )
    clipped = expand_piece_groups(
        [_corner_row("Clipped Corner", qty=4, width_cm=18, length_cm=18, clipped_corner_width_cm=6, clipped_corner_length_cm=6)]
    )
    for piece, piece_id in zip(clipped, range(5, 9), strict=True):
        piece["id"] = piece_id
        piece["label"] = f"{piece_id}.1"
        piece["source_piece_no"] = piece_id
    l_nested = _apply(_separate_plan(l_corners, 80, 80), l_corners, 80, 80)
    c_nested = _apply(_separate_plan(clipped, 80, 80), clipped, 80, 80)
    l_pieces = [dict(piece) for piece in l_nested["sheets"][0]["pieces"]]
    c_pieces = [dict(piece) for piece in c_nested["sheets"][0]["pieces"]]
    l_before = _offsets(l_pieces)
    c_before = _offsets(c_pieces)
    glass_rows = expand_piece_groups(
        [
            {
                "piece_type": "Glass",
                "width_cm": 50,
                "length_cm": 50,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 80,
            },
            _regular(8, 8),
        ]
    )
    glass, guest = glass_rows
    glass["id"] = 9
    glass["label"] = "9.1"
    glass["source_piece_no"] = 9
    guest["id"] = 10
    guest["label"] = "10.1"
    guest["source_piece_no"] = 10
    host = make_placed_piece(glass, 100, 0, 50, 50, False)
    placed_guest = make_placed_piece(guest, 112, 12, 8, 8, False)
    placed_guest[GLASS_HOST_PIECE_ID] = 9
    glass_before = _offsets([host, placed_guest])
    plan = _metrics(
        [
            {"sheet_no": 1, "w": 200, "h": 120, "pieces": [*l_pieces, host, placed_guest]},
            {"sheet_no": 2, "w": 200, "h": 120, "pieces": c_pieces},
        ],
        200,
        120,
    )
    pieces = [*l_corners, *clipped, glass, guest]
    assert not validate_plan(plan, pieces, 200, 120, kerf_cm=0.3)
    improved = _consolidate(plan, pieces, 200, 120)
    kinds = {group.kind for group in extract_placement_groups(improved)}

    assert _offsets(_ids_on(improved, {1, 2, 3, 4})) == l_before
    assert _offsets(_ids_on(improved, {5, 6, 7, 8})) == c_before
    assert _offsets(_ids_on(improved, {9, 10})) == glass_before
    assert {L_QUAD, CLIPPED_QUAD, GLASS_HOST} <= kinds
    assert not validate_plan(improved, pieces, 200, 120, kerf_cm=0.3)
    assert not placement_permission_errors(improved, pieces, mirroring_allowed=False)


def test_dxf_roundtrip_after_a_nest_translation(tmp_path):
    import ezdxf

    from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry

    corners = expand_piece_groups(
        [_corner_row("Clipped Corner", width_cm=44, length_cm=44, clipped_corner_width_cm=14, clipped_corner_length_cm=14)]
    )
    blocker = expand_piece_groups([_regular(20, 20)])[0]
    blocker["id"] = 3
    blocker["label"] = "3.1"
    blocker["source_piece_no"] = 3
    nested = _apply(_separate_plan(corners, 180, 100), corners, 180, 100)
    pair = [dict(piece) for piece in nested["sheets"][0]["pieces"]]
    origin_x = min(piece["x"] for piece in pair)
    origin_y = min(piece["y"] for piece in pair)
    plan = _metrics(
        [
            {
                "sheet_no": 1,
                "w": 180,
                "h": 100,
                "pieces": [make_placed_piece(blocker, origin_x, origin_y, 20, 20, False)],
            },
            {"sheet_no": 2, "w": 180, "h": 100, "pieces": pair},
        ],
        180,
        100,
    )
    improved = _consolidate(plan, [*corners, blocker], 180, 100)
    placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"]]
    outlines = [material_outline_cm(piece) for piece in placed]

    assert len(improved["sheets"]) == 1
    assert all(outline for outline in outlines)
    assert all(piece["edge_long_left"] == 1 for piece in placed if piece["piece_type"] == "Clipped Corner")
    document = ezdxf.new("R2010")
    for name in ("GEOMETRY", "CUT_PATH"):
        document.layers.add(name)
    modelspace = document.modelspace()
    for outline in outlines:
        ring = [(point[0] * 10, point[1] * 10) for point in outline]
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "GEOMETRY"}, close=True)
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "CUT_PATH"}, close=True)
    path = tmp_path / "moved-pair.dxf"
    document.saveas(path)
    loaded = read_dxf_geometry(str(path), relevant_layers={"GEOMETRY", "CUT_PATH"})
    rings = []
    geometry = [segment for segment in loaded["segments"] if segment["layer"] == "GEOMETRY"]
    for entity_id in sorted({segment["entity_id"] for segment in geometry}):
        segments = [segment for segment in geometry if segment["entity_id"] == entity_id]
        points = [segments[0]["start"]]
        points.extend(segment["end"] for segment in segments)
        if points and points[0] == points[-1]:
            points = points[:-1]
        rings.append(points)
    assert len(rings) == len(outlines)
    for outline, ring in zip(outlines, rings, strict=True):
        _same_points([(point[0] * 10, point[1] * 10) for point in outline], ring)


def test_order_26_00130_is_not_in_the_repo_and_a_44_pair_gap_is_measured():
    """The live order is not in this workspace. This measures the same layout shape."""

    l_corners = expand_piece_groups(
        [
            _corner_row(
                "L-Shaped Corner",
                qty=8,
                width_cm=36,
                length_cm=36,
                clipped_corner_width_cm=12,
                clipped_corner_length_cm=12,
            )
        ]
    )
    clipped = expand_piece_groups(
        [
            _corner_row(
                "Clipped Corner",
                qty=2,
                width_cm=44,
                length_cm=44,
                clipped_corner_width_cm=14,
                clipped_corner_length_cm=14,
            )
        ]
    )
    for piece, piece_id in zip(clipped, (9, 10), strict=True):
        piece["id"] = piece_id
        piece["label"] = f"{piece_id}.1"
        piece["source_piece_no"] = piece_id
    fillers = expand_piece_groups([_regular(30, 20, qty=5)])
    for offset, piece in enumerate(fillers, start=11):
        piece["id"] = offset
        piece["label"] = f"{offset}.1"
        piece["source_piece_no"] = offset
    l_nested = _apply(_separate_plan(l_corners, 244, 122), l_corners, 244, 122)
    c_nested = _apply(_separate_plan(clipped, 244, 122), clipped, 244, 122)
    l_pieces = [dict(piece) for sheet in l_nested["sheets"] for piece in sheet["pieces"]]
    c_pieces = [dict(piece) for sheet in c_nested["sheets"] for piece in sheet["pieces"]]
    l_before = _offsets(l_pieces)
    c_before = _offsets(c_pieces)
    filler_placed = [
        make_placed_piece(piece, 150, index * 22, 30, 20, False)
        for index, piece in enumerate(fillers)
    ]
    plan = _metrics(
        [
            {"sheet_no": 1, "w": 244, "h": 122, "pieces": [*l_pieces, *filler_placed]},
            {"sheet_no": 2, "w": 244, "h": 122, "pieces": c_pieces},
        ],
        244,
        122,
    )
    pieces = [*l_corners, *clipped, *fillers]
    assert not validate_plan(plan, pieces, 244, 122, kerf_cm=0.3)
    improved = _consolidate(plan, pieces, 244, 122, budget=2.0)

    assert _offsets(_ids_on(improved, set(range(1, 9)))) == l_before
    assert _offsets(_ids_on(improved, {9, 10})) == c_before
    assert not validate_plan(improved, pieces, 244, 122, kerf_cm=0.3)
    assert {L_QUAD, CLIPPED_PAIR} <= {group.kind for group in extract_placement_groups(improved)} or {
        L_PAIR,
        CLIPPED_PAIR,
    } <= {group.kind for group in extract_placement_groups(improved)}
    improved.setdefault("nest_consolidation_diagnostics", {})["measured_sheets"] = (
        len(plan["sheets"]),
        len(improved["sheets"]),
    )
    assert len(plan["sheets"]) == 2
    assert len(improved["sheets"]) == 1


def test_consolidation_stays_within_a_short_budget_on_large_boards():
    durations = {}
    for count in (20, 50, 100, 160):
        pieces = expand_piece_groups([_regular(12, 10, qty=count, allow_rotation=0)])
        pair_rows = expand_piece_groups(
            [_corner_row("L-Shaped Corner", qty=2, width_cm=24, length_cm=24, clipped_corner_width_cm=8, clipped_corner_length_cm=8)]
        )
        for piece, piece_id in zip(pair_rows, (count + 1, count + 2), strict=True):
            piece["id"] = piece_id
            piece["label"] = f"{piece_id}.1"
            piece["source_piece_no"] = piece_id
        nested = _apply(_separate_plan(pair_rows, 200, 80), pair_rows, 200, 80)
        pair = [dict(piece) for piece in nested["sheets"][0]["pieces"]]
        sheets = []
        per_sheet = 8
        for start in range(0, count, per_sheet):
            chunk = pieces[start : start + per_sheet]
            placed = [
                make_placed_piece(piece, (index % 4) * 22, (index // 4) * 16, 12, 10, False)
                for index, piece in enumerate(chunk)
            ]
            sheets.append(
                {
                    "sheet_no": len(sheets) + 1,
                    "w": 200,
                    "h": 80,
                    "pieces": placed,
                }
            )
        sheets.append({"sheet_no": len(sheets) + 1, "w": 200, "h": 80, "pieces": pair})
        plan = _metrics(sheets, 200, 80)
        catalog = [*pieces, *pair_rows]
        started = time.perf_counter()
        improved = _consolidate(plan, catalog, 200, 80, budget=1.5)
        durations[count] = time.perf_counter() - started
        assert durations[count] < 5
        assert not validate_plan(improved, catalog, 200, 80, kerf_cm=0.3)
        assert len(improved["sheets"]) <= len(plan["sheets"])
    assert set(durations) == {20, 50, 100, 160}


def _span(pieces):
    min_x = min(piece["x"] for piece in pieces)
    min_y = min(piece["y"] for piece in pieces)
    max_x = max(piece["x"] + piece["w"] for piece in pieces)
    max_y = max(piece["y"] + piece["h"] for piece in pieces)
    return (max_x - min_x) * (max_y - min_y)


def _same_points(actual, expected, tolerance=0.05):
    unused = [tuple(point) for point in expected]
    assert len(actual) == len(unused)
    for point in actual:
        index = next(
            (
                item
                for item, candidate in enumerate(unused)
                if abs(candidate[0] - point[0]) <= tolerance
                and abs(candidate[1] - point[1]) <= tolerance
            ),
            None,
        )
        assert index is not None
        unused.pop(index)
