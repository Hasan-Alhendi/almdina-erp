"""System-plan nesting of proven cut outlines inside Glass openings."""

from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.glass_opening_dxf import placed_glass_hole_mm
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    GLASS_HOST_PIECE_ID,
    guest_is_eligible,
    material_outline_cm,
    nest_glass_openings,
    nested_plan_is_better,
    nesting_time_budget_sec,
    opening_board_rect,
)
from almdina_erp.almdina_erp.domain.cutting.optimizer import optimize_plan
from almdina_erp.almdina_erp.domain.cutting.primitives import (
    expand_piece_groups,
    make_placed_piece,
)
from almdina_erp.almdina_erp.domain.cutting.registry import run_single_method


METHOD = "MaxRects Best Short Side"


def _glass(width, length, margin_mm, **extra):
    row = {
        "piece_type": "Glass",
        "width_cm": width,
        "length_cm": length,
        "qty": 1,
        "allow_rotation": 0,
        "glass_margin_mm": margin_mm,
    }
    row.update(extra)
    return row


def _regular(width, length, **extra):
    row = {
        "piece_type": "Regular",
        "width_cm": width,
        "length_cm": length,
        "qty": 1,
        "allow_rotation": 0,
    }
    row.update(extra)
    return row


def _plan(rows, board_w, board_h, kerf=0.3, **kwargs):
    pieces = expand_piece_groups(rows)
    plan = optimize_plan(
        pieces,
        board_w,
        board_h,
        kerf,
        selected_mode=kwargs.pop("selected_mode", METHOD),
        time_limit_sec=kwargs.pop("time_limit_sec", 2),
        **kwargs,
    )
    return pieces, plan


def _hosts(plan):
    return [
        piece.get(GLASS_HOST_PIECE_ID)
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
        if piece.get(GLASS_HOST_PIECE_ID) not in (None, "")
    ]


def _ids(plan):
    return sorted(
        int(piece["id"])
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
    )


def test_one_regular_door_nests_inside_a_glass_opening():
    pieces, plan = _plan([_glass(40, 40, 50), _regular(20, 20)], 50, 50)

    assert len(plan["sheets"]) == 1
    assert _hosts(plan) == [1]
    assert _ids(plan) == [1, 2]
    assert validate_plan(plan, pieces, 50, 50, kerf_cm=0.3) == []


def test_two_regular_doors_nest_inside_one_opening():
    pieces, plan = _plan(
        [_glass(40, 40, 50), _regular(12, 12, qty=2)],
        50,
        50,
    )

    assert len(plan["sheets"]) == 1
    assert sorted(_hosts(plan)) == [1, 1]
    assert _ids(plan) == [1, 2, 3]
    assert len(set(_ids(plan))) == 3
    assert validate_plan(plan, pieces, 50, 50, kerf_cm=0.3) == []


def test_two_glass_hosts_each_receive_one_regular_door():
    pieces, plan = _plan(
        [_glass(40, 40, 50), _glass(40, 40, 50), _regular(20, 20), _regular(20, 20)],
        50,
        50,
    )

    assert len(plan["sheets"]) == 2
    assert sorted(_hosts(plan)) == [1, 2]
    assert _ids(plan) == [1, 2, 3, 4]
    assert validate_plan(plan, pieces, 50, 50, kerf_cm=0.3) == []


def test_opening_without_a_fitting_door_stays_empty():
    pieces, plan = _plan([_glass(40, 40, 50), _regular(35, 35)], 50, 50)

    assert _hosts(plan) == []
    assert len(plan["sheets"]) == 2
    assert validate_plan(plan, pieces, 50, 50, kerf_cm=0.3) == []


def test_kerf_keeps_a_door_out_of_an_opening_it_almost_fits():
    pieces, plan = _plan(
        [_glass(40, 40, 50), _regular(12, 12)],
        50,
        50,
        kerf=10,
    )

    assert _hosts(plan) == []
    assert validate_plan(plan, pieces, 50, 50, kerf_cm=10) == []


def test_rotation_allows_a_door_the_opening_would_otherwise_reject():
    pieces, plan = _plan(
        [_glass(30, 50, 50), _regular(30, 15, allow_rotation=1)],
        40,
        60,
    )

    assert len(plan["sheets"]) == 1
    guest = next(piece for sheet in plan["sheets"] for piece in sheet["pieces"] if piece["id"] == 2)
    assert guest["rotated"] is True
    assert guest[GLASS_HOST_PIECE_ID] == 1
    assert validate_plan(plan, pieces, 40, 60, kerf_cm=0.3) == []


def test_forbidden_rotation_keeps_the_door_outside_the_opening():
    _pieces, plan = _plan(
        [_glass(30, 50, 50), _regular(30, 15, allow_rotation=0)],
        40,
        60,
    )

    assert _hosts(plan) == []
    assert len(plan["sheets"]) == 2


def _exact_special(width, length, points):
    import json

    return json.dumps(
        {
            "version": 1,
            "kind": "polygon",
            "units": "cm",
            "blank_width_cm": width,
            "blank_length_cm": length,
            "points": points,
            "exact": True,
        }
    )


def test_regular_addons_corners_and_exact_specials_nest_together():
    special = _exact_special(12, 12, [[2, 0], [12, 0], [12, 12], [0, 12], [0, 2]])
    rows = [
        _glass(70, 70, 50),
        _regular(
            12,
            12,
            extra_liner=1,
            liner_reference_side="edge_long_right",
            liner_width_cm=1.8,
            edge_long_right=1,
            edge_long_thickness_mm=2,
        ),
        {
            "piece_type": "Clipped Corner",
            "width_cm": 12,
            "length_cm": 12,
            "qty": 1,
            "clipped_corner_position": "Top Left",
            "clipped_corner_width_cm": 3,
            "clipped_corner_length_cm": 4,
        },
        {
            "piece_type": "L-Shaped Corner",
            "width_cm": 12,
            "length_cm": 12,
            "qty": 1,
            "clipped_corner_position": "Top Right",
            "clipped_corner_width_cm": 3,
            "clipped_corner_length_cm": 4,
        },
        {
            "piece_type": "Special",
            "width_cm": 12,
            "length_cm": 12,
            "qty": 1,
            "special_shape_geometry_json": special,
        },
    ]
    pieces, plan = _plan(rows, 80, 80)

    nested = [
        piece
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
        if piece.get(GLASS_HOST_PIECE_ID) not in (None, "")
    ]
    by_type = {piece["piece_type"]: piece for piece in nested}

    assert set(by_type) == {
        "Regular",
        "Clipped Corner",
        "L-Shaped Corner",
        "Special",
    }
    assert len(plan["sheets"]) == 1
    assert by_type["Regular"]["extra_liner"] == 1
    assert by_type["Regular"]["liner_reference_side"] == "edge_long_right"
    assert by_type["Regular"]["liner_width_cm"] == 1.8
    assert by_type["Regular"]["edge_long_right"] == 1
    assert by_type["Clipped Corner"]["clipped_corner_position"] == "Top Left"
    assert by_type["L-Shaped Corner"]["clipped_corner_width_cm"] == 3
    assert by_type["Special"]["special_shape_geometry_json"] == special
    assert [len(material_outline_cm(piece)) for piece in nested] == [4, 5, 6, 5]
    assert _ids(plan) == [1, 2, 3, 4, 5]
    assert validate_plan(plan, pieces, 80, 80, kerf_cm=0.3) == []


def test_unproven_special_and_corner_shapes_stay_outside():
    rows = [
        _glass(40, 40, 50),
        {
            "piece_type": "Clipped Corner",
            "width_cm": 12,
            "length_cm": 12,
            "qty": 1,
            "clipped_corner_position": "top_left",
            "clipped_corner_width_cm": 2,
            "clipped_corner_length_cm": 3,
        },
        {
            "piece_type": "Special",
            "width_cm": 12,
            "length_cm": 12,
            "qty": 1,
            "special_shape_geometry_json": "{\"kind\":\"rectangle\"}",
        },
    ]
    pieces = expand_piece_groups(rows)

    assert [guest_is_eligible(piece) for piece in pieces] == [True, False, False]
    plan = optimize_plan(pieces, 50, 50, 0.3, selected_mode=METHOD, time_limit_sec=2)

    assert _hosts(plan) == []


def test_glass_inside_glass_stops_at_two_host_steps():
    rows = [
        _glass(70, 70, 50),
        _glass(40, 40, 50),
        _glass(24, 24, 40),
        _regular(10, 10),
    ]
    pieces, plan = _plan(rows, 80, 80)
    placed = {
        piece["id"]: piece
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
    }

    assert len(plan["sheets"]) == 1
    assert placed[2][GLASS_HOST_PIECE_ID] == 1
    assert placed[3][GLASS_HOST_PIECE_ID] == 2
    assert placed[4][GLASS_HOST_PIECE_ID] == 1
    assert placed[2]["glass_hole_local_mm"]
    assert placed[3]["glass_hole_local_mm"]
    assert placed[4]["piece_type"] == "Regular"
    assert validate_plan(plan, pieces, 80, 80, kerf_cm=0.3) == []


def test_rotated_corner_outline_follows_the_placed_notch():
    piece = {
        "piece_type": "Clipped Corner",
        "x": 4,
        "y": 5,
        "w": 12,
        "h": 8,
        "rotated": True,
        "clipped_corner_position": "Top Left",
        "clipped_corner_width_cm": 3,
        "clipped_corner_length_cm": 2,
        "width_cm": 8,
        "length_cm": 12,
    }

    assert material_outline_cm(piece)[:3] == ((4.0, 5.0), (14.0, 5.0), (16.0, 8.0))


def test_interlocking_corners_use_material_clearance_not_their_boxes():
    pieces = expand_piece_groups(
        [
            _glass(40, 40, 20),
            {
                "piece_type": "L-Shaped Corner",
                "width_cm": 12,
                "length_cm": 10,
                "qty": 1,
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 6,
                "clipped_corner_length_cm": 9,
            },
            _regular(8, 8),
        ]
    )
    glass = make_placed_piece(pieces[0], 0, 0, 40, 40, False)
    hole = opening_board_rect(glass)
    shaped = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 12, 10, False)
    beside = make_placed_piece(pieces[2], hole["x"] + 8, hole["y"] + 1, 8, 8, False)
    overlapping = make_placed_piece(pieces[2], hole["x"] + 6, hole["y"] + 1, 8, 8, False)
    for guest in (shaped, beside, overlapping):
        guest[GLASS_HOST_PIECE_ID] = glass["id"]

    assert validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, shaped, beside]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=0.3,
    ) == []
    errors = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, shaped, overlapping]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=0.3,
    )
    assert any("overlap" in error for error in errors)


def test_rank_prefers_improvement_then_unique_opening_use():
    assert nested_plan_is_better(
        {"industrial_rank": (0, 1, 0), "sheets": []},
        {"industrial_rank": (0, 2, 0), "sheets": []},
    )
    assert not nested_plan_is_better(
        {"industrial_rank": (0, 2, 0), "sheets": []},
        {"industrial_rank": (0, 1, 0), "sheets": []},
    )
    equal = (0, 1, 0)
    hosted = {
        "industrial_rank": equal,
        "sheets": [
            {
                "pieces": [
                    {"id": 2, GLASS_HOST_PIECE_ID: 1},
                    {"id": 2, GLASS_HOST_PIECE_ID: 1},
                ]
            }
        ],
    }
    plain = {"industrial_rank": equal, "sheets": [{"pieces": [{"id": 2}]}]}
    also_hosted = {
        "industrial_rank": equal,
        "sheets": [{"pieces": [{"id": 4, GLASS_HOST_PIECE_ID: 3}]}],
    }

    assert nested_plan_is_better(hosted, plain)
    assert not nested_plan_is_better(plain, plain)
    assert not nested_plan_is_better(hosted, also_hosted)


def test_equal_rank_accepts_nesting_and_a_worse_rank_keeps_baseline(monkeypatch):
    pieces = expand_piece_groups([_glass(40, 40, 50), _regular(20, 20)])
    baseline = run_single_method(pieces, 50, 50, 0.3, METHOD)
    baseline["industrial_rank"] = (0, 1)

    def same_rank(plan, *_args, **_kwargs):
        plan["industrial_rank"] = (0, 1)
        return plan

    def worse_rank(plan, *_args, **_kwargs):
        plan["industrial_rank"] = (0, 2)
        return plan

    monkeypatch.setattr(
        "almdina_erp.almdina_erp.domain.cutting.optimizer.enrich_plan_metrics",
        same_rank,
    )
    accepted = nest_glass_openings(
        baseline,
        pieces,
        50,
        50,
        0.3,
        machine_type="CNC Router",
        time_limit_sec=2,
        min_remnant_width_cm=30,
        min_remnant_length_cm=30,
        min_remnant_area_m2=0.09,
    )
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.domain.cutting.optimizer.enrich_plan_metrics",
        worse_rank,
    )
    rejected = nest_glass_openings(
        baseline,
        pieces,
        50,
        50,
        0.3,
        machine_type="CNC Router",
        time_limit_sec=2,
        min_remnant_width_cm=30,
        min_remnant_length_cm=30,
        min_remnant_area_m2=0.09,
    )

    assert _hosts(accepted) == [1]
    assert rejected is baseline


def test_panel_saw_does_not_nest_inside_glass():
    _pieces, plan = _plan(
        [_glass(40, 40, 50), _regular(20, 20)],
        50,
        50,
        machine_type="Panel Saw",
    )

    assert _hosts(plan) == []
    assert len(plan["sheets"]) >= 2


def test_zero_time_budget_keeps_the_baseline():
    assert nesting_time_budget_sec(0) == 0
    _pieces, plan = _plan(
        [_glass(40, 40, 50), _regular(20, 20)],
        50,
        50,
        time_limit_sec=0,
    )

    assert _hosts(plan) == []
    assert len(plan["sheets"]) == 2


def test_same_inputs_pack_the_same_nested_plan_twice():
    rows = [_glass(40, 40, 50), _regular(20, 20)]
    _first_pieces, first = _plan(rows, 50, 50)
    _second_pieces, second = _plan(rows, 50, 50)

    assert [
        (piece["id"], piece["x"], piece["y"], piece["w"], piece["h"], piece.get(GLASS_HOST_PIECE_ID))
        for sheet in first["sheets"]
        for piece in sheet["pieces"]
    ] == [
        (piece["id"], piece["x"], piece["y"], piece["w"], piece["h"], piece.get(GLASS_HOST_PIECE_ID))
        for sheet in second["sheets"]
        for piece in sheet["pieces"]
    ]


def test_orders_without_glass_keep_the_rectangle_pack():
    rows = [_regular(50, 90, qty=2), _regular(30, 70, allow_rotation=1)]
    pieces = expand_piece_groups(rows)
    nested = optimize_plan(pieces, 206, 279, 0.3, selected_mode=METHOD, time_limit_sec=2)
    baseline = run_single_method(pieces, 206, 279, 0.3, METHOD)

    assert _hosts(nested) == []
    assert [
        (piece["id"], round(piece["x"], 6), round(piece["y"], 6), piece["w"], piece["h"])
        for sheet in nested["sheets"]
        for piece in sheet["pieces"]
    ] == [
        (piece["id"], round(piece["x"], 6), round(piece["y"], 6), piece["w"], piece["h"])
        for sheet in baseline["sheets"]
        for piece in sheet["pieces"]
    ]


def test_failed_validation_keeps_the_unnested_plan(monkeypatch):
    def reject(*_args, **_kwargs):
        return ["forced"]

    monkeypatch.setattr(
        "almdina_erp.almdina_erp.domain.cutting.evaluation.validate_plan",
        reject,
    )
    _pieces, plan = _plan([_glass(40, 40, 50), _regular(20, 20)], 50, 50)

    assert _hosts(plan) == []
    assert len(plan["sheets"]) == 2


def test_touching_or_crossing_the_opening_is_rejected():
    pieces = expand_piece_groups([_glass(40, 40, 50), _regular(20, 20)])
    glass = make_placed_piece(pieces[0], 0, 0, 40, 40, False)
    hole = opening_board_rect(glass)
    touching = make_placed_piece(pieces[1], hole["x"], hole["y"], 20, 20, False)
    touching[GLASS_HOST_PIECE_ID] = glass["id"]
    crossing = make_placed_piece(pieces[1], hole["x"] + hole["w"] - 5, hole["y"] + 1, 20, 20, False)
    crossing[GLASS_HOST_PIECE_ID] = glass["id"]

    touching_errors = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, touching]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=0.3,
    )
    crossing_errors = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, crossing]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=0.3,
    )

    assert any("valid Glass opening nest" in error for error in touching_errors)
    assert any("valid Glass opening nest" in error for error in crossing_errors)
    unlinked = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 20, 20, False)
    unlinked_errors = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, unlinked]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=0.3,
    )
    assert any("overlap" in error for error in unlinked_errors)


def test_exact_single_kerf_gap_is_accepted_and_a_short_gap_is_rejected():
    pieces = expand_piece_groups([_glass(40, 40, 50), _regular(18, 18)])
    glass = make_placed_piece(pieces[0], 0, 0, 40, 40, False)
    hole = opening_board_rect(glass)
    exact = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 18, 18, False)
    exact[GLASS_HOST_PIECE_ID] = glass["id"]
    short = make_placed_piece(pieces[1], hole["x"] + 0.5, hole["y"] + 1, 18, 18, False)
    short[GLASS_HOST_PIECE_ID] = glass["id"]

    assert validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, exact]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=1,
    ) == []
    assert validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, short]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=1,
    )


def test_wrong_host_id_and_circular_host_links_are_rejected():
    pieces = expand_piece_groups([_glass(40, 40, 50), _regular(18, 18), _regular(10, 10)])
    glass = make_placed_piece(pieces[0], 0, 0, 40, 40, False)
    hole = opening_board_rect(glass)
    guest = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 18, 18, False)
    guest[GLASS_HOST_PIECE_ID] = 99
    other = make_placed_piece(pieces[2], 0, 42, 10, 10, False)
    wrong = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, guest, other]}], "unplaced": []},
        pieces,
        80,
        80,
        kerf_cm=1,
    )
    guest[GLASS_HOST_PIECE_ID] = other["id"]
    other[GLASS_HOST_PIECE_ID] = guest["id"]
    circular = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, guest, other]}], "unplaced": []},
        pieces,
        80,
        80,
        kerf_cm=1,
    )

    assert any("not in the plan" in error for error in wrong)
    assert any("circular" in error for error in circular)

    deep_pieces = expand_piece_groups(
        [_glass(70, 70, 50), _glass(40, 40, 50), _glass(20, 20, 30), _regular(6, 6)]
    )
    outer = make_placed_piece(deep_pieces[0], 0, 0, 70, 70, False)
    middle = make_placed_piece(deep_pieces[1], 6, 6, 40, 40, False)
    inner = make_placed_piece(deep_pieces[2], 12, 12, 20, 20, False)
    deep_guest = make_placed_piece(deep_pieces[3], 16, 16, 6, 6, False)
    middle[GLASS_HOST_PIECE_ID] = outer["id"]
    inner[GLASS_HOST_PIECE_ID] = middle["id"]
    deep_guest[GLASS_HOST_PIECE_ID] = inner["id"]
    too_deep = validate_plan(
        {
            "sheets": [
                {"sheet_no": 1, "pieces": [outer, middle, inner, deep_guest]}
            ],
            "unplaced": [],
        },
        deep_pieces,
        80,
        80,
        kerf_cm=0.3,
    )

    assert any("nesting depth" in error for error in too_deep)


def test_a_nested_door_outside_the_board_is_rejected():
    pieces = expand_piece_groups([_regular(10, 10)])
    placed = make_placed_piece(pieces[0], -1, 0, 10, 10, False)
    errors = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [placed]}], "unplaced": []},
        pieces,
        50,
        50,
    )

    assert any("exceeds usable board bounds" in error for error in errors)


def test_two_guests_inside_one_opening_need_one_kerf_between_them():
    pieces = expand_piece_groups([_glass(40, 40, 50), _regular(10, 10), _regular(10, 10)])
    glass = make_placed_piece(pieces[0], 0, 0, 40, 40, False)
    hole = opening_board_rect(glass)
    first = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 10, 10, False)
    second = make_placed_piece(pieces[2], hole["x"] + 12, hole["y"] + 1, 10, 10, False)
    overlap = make_placed_piece(pieces[2], hole["x"] + 5, hole["y"] + 1, 10, 10, False)
    for guest in (first, second, overlap):
        guest[GLASS_HOST_PIECE_ID] = glass["id"]

    assert validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, first, second]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=1,
    ) == []
    errors = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, first, overlap]}], "unplaced": []},
        pieces,
        50,
        50,
        kerf_cm=1,
    )
    assert any("overlap" in error for error in errors)


def test_asymmetric_banding_and_host_rotation_use_the_stored_opening_once():
    source = {
        "piece_type": "Glass",
        "width_cm": 40,
        "length_cm": 60,
        "glass_margin_mm": 100,
        "edge_long_left": 1,
        "edge_long_thickness_mm": 20,
        "edge_long_right": 0,
        "edge_width_top": 0,
        "edge_width_bottom": 0,
    }
    placed = {"id": 7, "piece_type": "Glass", "x": 5, "y": 7, "w": 40, "h": 60, "rotated": False}
    from almdina_erp.almdina_erp.domain.cutting.glass_opening_dxf import record_glass_opening

    record_glass_opening(placed, source, rotated=False)
    opening = opening_board_rect(placed)
    ring = placed_glass_hole_mm(source, rotated=False)
    min_x = min(point[0] for point in ring)
    min_y = min(point[1] for point in ring)

    assert opening["x"] == placed["x"] + (min_x / 10)
    assert opening["y"] == placed["y"] + (min_y / 10)
    assert abs(opening["x"] - 13) < 1e-6
    assert abs(opening["w"] - 22) < 1e-6

    rotated = {"id": 8, "piece_type": "Glass", "x": 1, "y": 2, "w": 60, "h": 40, "rotated": True}
    record_glass_opening(rotated, source, rotated=True)
    rotated_opening = opening_board_rect(rotated)
    rotated_ring = placed["glass_hole_local_mm"] and rotated["glass_hole_local_mm"]
    assert rotated_opening["x"] == 1 + (min(point[0] for point in rotated_ring) / 10)
    assert rotated_opening["y"] == 2 + (min(point[1] for point in rotated_ring) / 10)
    assert rotated_ring != placed["glass_hole_local_mm"]
