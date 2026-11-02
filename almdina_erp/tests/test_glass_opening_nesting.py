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
from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()


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
    more_guests = {
        "industrial_rank": (0, 9, 0),
        "sheets": [{"pieces": [{"id": 2, GLASS_HOST_PIECE_ID: 1, "w": 10, "h": 10}]}],
    }
    better_rank = {"industrial_rank": (0, 1, 0), "sheets": [{"pieces": [{"id": 2}]}]}
    assert nested_plan_is_better(more_guests, better_rank)


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
    assert _hosts(rejected) == [1]


def test_panel_saw_does_not_nest_inside_glass():
    _pieces, plan = _plan(
        [_glass(40, 40, 50), _regular(20, 20)],
        50,
        50,
        machine_type="Panel Saw",
    )

    assert _hosts(plan) == []
    assert len(plan["sheets"]) >= 2


def test_validation_deadline_returns_sentinel_without_partial_pair_errors():
    from almdina_erp.almdina_erp.domain.cutting.evaluation import (
        VALIDATION_DEADLINE_EXCEEDED,
        validate_plan,
    )

    pieces, plan = _plan([_glass(40, 40, 50), _regular(20, 20)], 50, 50)
    # Already expired deadline must abort before emitting pair faults.
    errors = validate_plan(
        plan,
        pieces,
        50,
        50,
        kerf_cm=0.3,
        deadline_monotonic=0.0,
    )
    assert errors == [VALIDATION_DEADLINE_EXCEEDED]


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


def test_glass_85_opening_75_nests_regular_20_on_a_shared_board():
    """Regression: 850×850 Glass / 750×750 opening / 200×200 Regular / kerf 3 mm."""

    pieces, plan = _plan(
        [_glass(85, 85, 50), _regular(20, 20)],
        122,
        244,
        kerf=0.3,
    )
    hosts = _hosts(plan)
    diagnostics = plan.get("glass_nesting_diagnostics") or {}

    assert len(plan["sheets"]) == 1
    assert hosts == [1]
    assert diagnostics.get("outcome") == "accepted"
    assert diagnostics.get("openings_found") == 1
    assert diagnostics.get("guests_selected") == [2]
    assert _ids(plan) == [1, 2]
    assert validate_plan(plan, pieces, 122, 244, kerf_cm=0.3) == []


def test_nesting_diagnostics_name_rejected_rank_when_candidate_is_worse(monkeypatch):
    pieces = expand_piece_groups([_glass(40, 40, 50), _regular(20, 20)])
    baseline = run_single_method(pieces, 50, 50, 0.3, METHOD)
    baseline["industrial_rank"] = (0, 1)

    def worse_rank(plan, *_args, **_kwargs):
        plan["industrial_rank"] = (0, 2)
        return plan

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

    assert rejected is not baseline
    assert rejected["glass_nesting_diagnostics"]["outcome"] == "accepted"
    assert rejected["glass_nesting_diagnostics"]["guests_selected"] == [2]


def test_corner_and_second_regular_nest_inside_one_opening():
    rows = [
        _glass(70, 70, 50),
        {
            "piece_type": "Clipped Corner",
            "width_cm": 18,
            "length_cm": 16,
            "qty": 1,
            "clipped_corner_position": "Top Right",
            "clipped_corner_width_cm": 5,
            "clipped_corner_length_cm": 6,
        },
        _regular(12, 12),
    ]
    pieces, plan = _plan(rows, 80, 80)

    nested = [
        piece
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
        if piece.get(GLASS_HOST_PIECE_ID) not in (None, "")
    ]
    assert {piece["piece_type"] for piece in nested} == {"Clipped Corner", "Regular"}
    assert all(piece[GLASS_HOST_PIECE_ID] == 1 for piece in nested)
    assert validate_plan(plan, pieces, 80, 80, kerf_cm=0.3) == []


def test_l_shaped_beside_glass_uses_material_not_bbox():
    pieces = expand_piece_groups(
        [
            _glass(40, 40, 50),
            {
                "piece_type": "L-Shaped Corner",
                "width_cm": 20,
                "length_cm": 20,
                "qty": 1,
                "clipped_corner_position": "Top Left",
                "clipped_corner_width_cm": 5,
                "clipped_corner_length_cm": 6,
            },
        ]
    )
    glass = make_placed_piece(pieces[0], 0, 0, 40, 40, False)
    beside = make_placed_piece(pieces[1], 40.1, 35, 20, 20, False)

    assert validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, beside]}], "unplaced": []},
        pieces,
        80,
        80,
        kerf_cm=0.3,
    ) == []


def test_real_overlap_between_glass_frame_and_external_door_is_rejected():
    pieces = expand_piece_groups([_glass(40, 40, 50), _regular(20, 20)])
    glass = make_placed_piece(pieces[0], 0, 0, 40, 40, False)
    crossing = make_placed_piece(pieces[1], 30, 10, 20, 20, False)

    errors = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [glass, crossing]}], "unplaced": []},
        pieces,
        80,
        80,
        kerf_cm=0.3,
    )
    assert any("overlap" in error for error in errors)


def test_export_rectangle_fallback_accepts_nested_guests_and_rejects_true_conflicts():
    from almdina_erp.almdina_erp.services import dxf_export_service

    pieces = expand_piece_groups(
        [
            _glass(40, 40, 50),
            _regular(12, 12),
            _regular(12, 12),
            {
                "piece_type": "L-Shaped Corner",
                "width_cm": 20,
                "length_cm": 20,
                "qty": 1,
                "clipped_corner_position": "Top Left",
                "clipped_corner_width_cm": 5,
                "clipped_corner_length_cm": 6,
            },
        ]
    )
    glass = make_placed_piece(pieces[0], 0, 0, 40, 40, False)
    hole = opening_board_rect(glass)
    first = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 12, 12, False)
    second = make_placed_piece(pieces[2], hole["x"] + 14, hole["y"] + 1, 12, 12, False)
    beside = make_placed_piece(pieces[3], 40.1, 35, 20, 20, False)
    for guest in (first, second):
        guest[GLASS_HOST_PIECE_ID] = glass["id"]

    accepted = {
        "kerf_cm": 0.3,
        "sheets": [{"sheet_no": 1, "pieces": [glass, first, second, beside]}],
    }
    assert dxf_export_service._kerf_errors(accepted) == []

    overlap = make_placed_piece(pieces[2], hole["x"] + 5, hole["y"] + 1, 12, 12, False)
    overlap[GLASS_HOST_PIECE_ID] = glass["id"]
    rejected = {
        "kerf_cm": 0.3,
        "sheets": [{"sheet_no": 1, "pieces": [glass, first, overlap]}],
    }
    issues = dxf_export_service._kerf_errors(rejected)
    assert issues
    assert {issue.target.pair_contour_nos for issue in issues} == {("2.1", "3.1")}

    frame_conflict = make_placed_piece(pieces[1], glass["x"], glass["y"], 12, 12, False)
    frame_conflict.update(
        {
            GLASS_HOST_PIECE_ID: glass["id"],
            "source_piece_no": 2,
            "label": "2.1",
            "id": 2,
        }
    )
    glass_labeled = dict(glass)
    glass_labeled.update(source_piece_no=1, label="1.1", id=1)
    frame_rejected = {
        "kerf_cm": 0.3,
        "sheets": [{"sheet_no": 1, "pieces": [glass_labeled, frame_conflict]}],
    }
    frame_issues = dxf_export_service._kerf_errors(frame_rejected)
    assert frame_issues
    assert frame_issues[0].params.get("glass_frame_guest_label") == "2.1"
    assert frame_issues[0].params.get("glass_frame_host_label") == "1.1"
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
        present_issue,
    )

    presented = present_issue(frame_issues[0])
    assert "تتداخل مع إطار البلور" in presented.problem
    assert "2" in presented.problem
    assert "1" in presented.problem


def test_export_rebuild_keeps_glass_host_piece_id():
    import json
    from types import SimpleNamespace

    from almdina_erp.almdina_erp.services.export_validation_service import (
        _plan_to_export_snapshot,
    )

    hole = [[50.0, 50.0], [350.0, 50.0], [350.0, 350.0], [50.0, 350.0]]
    persisted = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 1,
                        "piece_type": "Glass",
                        "glass_margin_mm": 50,
                        "glass_hole_local_mm": hole,
                    },
                    {
                        "id": 2,
                        "piece_type": "Regular",
                        GLASS_HOST_PIECE_ID: 1,
                    },
                ],
            }
        ]
    }
    plan = SimpleNamespace(
        snapshot_json=json.dumps(persisted),
        placed_pieces=[
            SimpleNamespace(
                sheet_no=1,
                piece_id=1,
                piece_label="1.1",
                piece_instance_id="door-1:1",
                source_piece_no=1,
                copy_no=1,
                x_mm=0,
                y_mm=0,
                width_mm=400,
                height_mm=400,
                original_width_cm=40,
                original_length_cm=40,
                piece_type="Glass",
                clipped_corner_position="",
                clipped_corner_width_cm=0,
                clipped_corner_length_cm=0,
                special_shape_geometry_json="",
                rotated=0,
                edge_long_right=0,
                edge_long_left=0,
                edge_width_top=0,
                edge_width_bottom=0,
                edge_type="",
                notes="",
            ),
            SimpleNamespace(
                sheet_no=1,
                piece_id=2,
                piece_label="2.1",
                piece_instance_id="door-2:1",
                source_piece_no=2,
                copy_no=1,
                x_mm=60,
                y_mm=60,
                width_mm=120,
                height_mm=120,
                original_width_cm=12,
                original_length_cm=12,
                piece_type="Regular",
                clipped_corner_position="",
                clipped_corner_width_cm=0,
                clipped_corner_length_cm=0,
                special_shape_geometry_json="",
                rotated=0,
                edge_long_right=0,
                edge_long_left=0,
                edge_width_top=0,
                edge_width_bottom=0,
                edge_type="",
                notes="",
            ),
        ],
        sources=[
            SimpleNamespace(
                sheet_no=1,
                source_type="Full Board",
                remnant=None,
                board_item=None,
                material="",
                color="",
                thickness_mm=18,
                full_width_mm=1220,
                full_length_mm=2440,
                usable_width_mm=1220,
                usable_length_mm=2440,
                source_area_m2=2.9768,
            )
        ],
        engine_version="system",
        method_key=METHOD,
        method_label=METHOD,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        usable_board_width_mm=1220,
        usable_board_length_mm=2440,
        kerf_mm=3,
        trim_margin_mm=0,
        used_area_m2=0.1744,
        total_source_area_m2=2.9768,
        waste_area_m2=2.8,
        required_boards=1,
    )

    rebuilt = _plan_to_export_snapshot(plan)
    by_id = {int(piece["id"]): piece for piece in rebuilt["sheets"][0]["pieces"]}

    assert by_id[1]["glass_hole_local_mm"] == hole
    assert by_id[2][GLASS_HOST_PIECE_ID] == 1


def _cutting_plan_for_layout(pieces_cm, *, kerf_mm=3, plan_kind="Remnant"):
    import json
    from types import SimpleNamespace
    from unittest.mock import patch

    from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
        sanitize_plan_snapshot,
    )
    from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
        validate_snapshot_material_layout,
    )
    from almdina_erp.almdina_erp.services.export_validation_service import (
        validate_cutting_plan_issues,
    )

    snapshot = sanitize_plan_snapshot(
        {
            "kerf_cm": kerf_mm / 10.0,
            "sheets": [{"sheet_no": 1, "pieces": pieces_cm}],
            "unplaced": [],
        }
    )
    topology_aware = validate_snapshot_material_layout(
        snapshot,
        required_clearance_mm=float(kerf_mm),
    )

    def _placed(piece):
        return SimpleNamespace(
            sheet_no=1,
            piece_id=piece["id"],
            piece_label=piece.get("label") or f"{piece['id']}.1",
            source_piece_no=piece.get("source_piece_no", piece["id"]),
            copy_no=1,
            x_mm=piece["x"] * 10,
            y_mm=piece["y"] * 10,
            width_mm=piece["w"] * 10,
            height_mm=piece["h"] * 10,
            original_width_cm=piece["w"],
            original_length_cm=piece["h"],
            piece_type=piece.get("piece_type") or "Regular",
            rotated=0,
            clipped_corner_position=piece.get("clipped_corner_position") or "",
            clipped_corner_width_cm=piece.get("clipped_corner_width_cm") or 0,
            clipped_corner_length_cm=piece.get("clipped_corner_length_cm") or 0,
            special_shape_geometry_json=piece.get("special_shape_geometry_json") or "",
        )

    plan = SimpleNamespace(
        plan_kind=plan_kind,
        door_cutting_order="DCO-NEST",
        board_item="",
        snapshot_json=json.dumps(snapshot),
        kerf_mm=kerf_mm,
        sources=[
            SimpleNamespace(
                sheet_no=1,
                source_type="Full Board",
                remnant=None,
                board_item="",
                material="",
                color="",
                thickness_mm=18,
                board_description="",
                full_width_mm=2000,
                full_length_mm=2000,
                usable_width_mm=2000,
                usable_length_mm=2000,
            )
        ],
        placed_pieces=[_placed(piece) for piece in pieces_cm],
    )
    order = SimpleNamespace(
        board_description="",
        board_material="",
        board_color="",
        board_thickness_mm=18,
    )
    with patch(
        "almdina_erp.almdina_erp.services.export_validation_service.frappe.get_doc",
        return_value=order,
        create=True,
    ):
        issues = validate_cutting_plan_issues(plan)
    return issues, snapshot, topology_aware


def test_three_nested_guests_pass_plan_and_cutting_plan_validation():
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import MATERIAL_OVERLAP
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors

    pieces = expand_piece_groups(
        [
            _glass(70, 70, 50),
            _regular(15, 15),
            _regular(12, 12),
            _regular(10, 10),
        ]
    )
    glass = make_placed_piece(pieces[0], 0, 0, 70, 70, False)
    glass.update(source_piece_no=1, label="1.1")
    hole = opening_board_rect(glass)
    guests = []
    placements = (
        (pieces[1], hole["x"] + 1, hole["y"] + 1, 15, 15, 2),
        (pieces[2], hole["x"] + 1 + 15 + 0.3, hole["y"] + 1, 12, 12, 3),
        (pieces[3], hole["x"] + 1, hole["y"] + 1 + 15 + 0.3, 10, 10, 4),
    )
    for source, x_pos, y_pos, width, height, source_no in placements:
        guest = make_placed_piece(source, x_pos, y_pos, width, height, False)
        guest.update(
            {
                GLASS_HOST_PIECE_ID: glass["id"],
                "source_piece_no": source_no,
                "label": f"{source_no}.1",
            }
        )
        guests.append(guest)

    plan = {
        "kerf_cm": 0.3,
        "sheets": [{"sheet_no": 1, "pieces": [glass, *guests]}],
        "unplaced": [],
    }
    assert validate_plan(plan, pieces, 100, 100, kerf_cm=0.3) == []
    assert _kerf_errors(plan) == []

    issues, snapshot, topology_aware = _cutting_plan_for_layout(
        [glass, *guests],
        kerf_mm=3,
    )
    assert topology_aware is False
    assert issues == []
    assert snapshot["sheets"][0]["pieces"][0]["glass_hole_local_mm"]
    assert [piece.get(GLASS_HOST_PIECE_ID) for piece in snapshot["sheets"][0]["pieces"][1:]] == [
        1,
        1,
        1,
    ]
    assert not any(issue.code == MATERIAL_OVERLAP for issue in issues)


def test_cutting_plan_validation_rejects_nested_and_historical_collisions():
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import MATERIAL_OVERLAP

    pieces = expand_piece_groups(
        [
            _glass(70, 70, 50),
            _regular(15, 15),
            _regular(12, 12),
            _regular(20, 20, qty=2),
        ]
    )
    glass = make_placed_piece(pieces[0], 0, 0, 70, 70, False)
    glass.update(source_piece_no=1, label="1.1")
    hole = opening_board_rect(glass)

    touching = make_placed_piece(pieces[1], hole["x"], hole["y"] + 1, 15, 15, False)
    touching.update({GLASS_HOST_PIECE_ID: 1, "source_piece_no": 2, "label": "2.1"})
    issues, _, topology_aware = _cutting_plan_for_layout([glass, touching])
    assert topology_aware is False
    assert any(
        issue.code == MATERIAL_OVERLAP and issue.target.pair_piece_nos == (1, 2)
        for issue in issues
    )

    crossing = make_placed_piece(
        pieces[1], hole["x"] + hole["w"] - 5, hole["y"] + 1, 15, 15, False
    )
    crossing.update({GLASS_HOST_PIECE_ID: 1, "source_piece_no": 2, "label": "2.1"})
    issues, _, _ = _cutting_plan_for_layout([glass, crossing])
    assert any(issue.code == MATERIAL_OVERLAP for issue in issues)

    first = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 15, 15, False)
    first.update({GLASS_HOST_PIECE_ID: 1, "source_piece_no": 2, "label": "2.1"})
    overlap = make_placed_piece(pieces[2], hole["x"] + 5, hole["y"] + 1, 12, 12, False)
    overlap.update({GLASS_HOST_PIECE_ID: 1, "source_piece_no": 3, "label": "3.1"})
    issues, _, _ = _cutting_plan_for_layout([glass, first, overlap])
    assert any(
        issue.code == MATERIAL_OVERLAP and issue.target.pair_piece_nos == (2, 3)
        for issue in issues
    )

    short = make_placed_piece(pieces[1], hole["x"] + 0.1, hole["y"] + 1, 15, 15, False)
    short.update({GLASS_HOST_PIECE_ID: 1, "source_piece_no": 2, "label": "2.1"})
    issues, _, _ = _cutting_plan_for_layout([glass, short], kerf_mm=10)
    assert any(issue.code == MATERIAL_OVERLAP for issue in issues)

    wrong = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 15, 15, False)
    wrong.update({GLASS_HOST_PIECE_ID: 99, "source_piece_no": 2, "label": "2.1"})
    issues, _, _ = _cutting_plan_for_layout([glass, wrong])
    assert any(issue.code == MATERIAL_OVERLAP for issue in issues)

    bare = dict(glass)
    bare.pop("glass_hole_local_mm", None)
    bare.pop("glass_margin_mm", None)
    guest = make_placed_piece(pieces[1], hole["x"] + 1, hole["y"] + 1, 15, 15, False)
    guest.update({GLASS_HOST_PIECE_ID: 1, "source_piece_no": 2, "label": "2.1"})
    issues, _, _ = _cutting_plan_for_layout([bare, guest])
    assert any(issue.code == MATERIAL_OVERLAP for issue in issues)

    left = make_placed_piece(pieces[3], 0, 0, 20, 20, False)
    left.update(source_piece_no=1, label="1.1")
    right = make_placed_piece(pieces[4], 10, 0, 20, 20, False)
    right.update(source_piece_no=2, label="2.1")
    issues, _, topology_aware = _cutting_plan_for_layout([left, right])
    assert topology_aware is False
    assert any(
        issue.code == MATERIAL_OVERLAP and issue.target.pair_piece_nos == (1, 2)
        for issue in issues
    )


def _lifecycle_placed_row(piece, sheet_no=1):
    from types import SimpleNamespace

    return SimpleNamespace(
        sheet_no=sheet_no,
        piece_id=piece["id"],
        piece_label=piece.get("label") or f"{piece['id']}.1",
        piece_instance_id=piece.get("piece_instance_id") or f"door-{piece['id']}:1",
        source_piece_no=piece.get("source_piece_no", piece["id"]),
        copy_no=piece.get("copy_no", 1),
        x_mm=piece["x"] * 10,
        y_mm=piece["y"] * 10,
        width_mm=piece["w"] * 10,
        height_mm=piece["h"] * 10,
        original_width_cm=piece.get("original_w", piece["w"]),
        original_length_cm=piece.get("original_h", piece["h"]),
        piece_type=piece.get("piece_type") or "Regular",
        clipped_corner_position=piece.get("clipped_corner_position") or "",
        clipped_corner_width_cm=piece.get("clipped_corner_width_cm") or 0,
        clipped_corner_length_cm=piece.get("clipped_corner_length_cm") or 0,
        special_shape_geometry_json=piece.get("special_shape_geometry_json") or "",
        rotated=1 if piece.get("rotated") else 0,
        edge_long_right=0,
        edge_long_left=0,
        edge_width_top=0,
        edge_width_bottom=0,
        edge_type="",
        notes="",
        resource_kind="FULL_BOARD",
        offcut_source_party="UNASSIGNED",
        offcut_execution_party="UNASSIGNED",
        extra_liner=0,
        liner_reference_side="",
        liner_offset_cm=0,
        liner_width_cm=0,
        liner_start_cm=0,
        liner_length_cm=0,
        extra_back_groove=0,
        back_groove_reference_side="",
        back_groove_offset_cm=0,
        back_groove_width_cm=0,
        back_groove_start_cm=0,
        back_groove_length_cm=0,
        extra_recessed_handle_cutout=0,
        recessed_handle_reference_side="",
        recessed_handle_offset_cm=0,
        recessed_handle_width_cm=0,
        recessed_handle_start_cm=0,
        recessed_handle_length_cm=0,
    )


def _reload_export_snapshot(plan, *, board_w_cm, board_h_cm):
    """Simulate save → placed_pieces without host fields → reload → export rebuild."""

    import json
    from types import SimpleNamespace

    from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
        sanitize_plan_snapshot,
    )
    from almdina_erp.almdina_erp.services.export_validation_service import (
        _plan_to_export_snapshot,
    )

    snapshot = sanitize_plan_snapshot(plan)
    # JSON round-trip is the browser/workspace reload boundary.
    snapshot = sanitize_plan_snapshot(json.loads(json.dumps(snapshot)))
    sheet = snapshot["sheets"][0]
    cutting_plan = SimpleNamespace(
        snapshot_json=json.dumps(snapshot),
        placed_pieces=[_lifecycle_placed_row(piece) for piece in sheet["pieces"]],
        sources=[
            SimpleNamespace(
                sheet_no=1,
                source_type="Full Board",
                remnant=None,
                board_item=None,
                material="",
                color="",
                thickness_mm=18,
                full_width_mm=board_w_cm * 10,
                full_length_mm=board_h_cm * 10,
                usable_width_mm=board_w_cm * 10,
                usable_length_mm=board_h_cm * 10,
                source_area_m2=board_w_cm * board_h_cm / 10000,
                board_description="",
                resource_kind="FULL_BOARD",
                offcut_source_party="UNASSIGNED",
                offcut_execution_party="UNASSIGNED",
            )
        ],
        engine_version="system",
        method_key=METHOD,
        method_label=METHOD,
        full_board_width_mm=board_w_cm * 10,
        full_board_length_mm=board_h_cm * 10,
        usable_board_width_mm=board_w_cm * 10,
        usable_board_length_mm=board_h_cm * 10,
        kerf_mm=3,
        trim_margin_mm=0,
        used_area_m2=0.5,
        total_source_area_m2=board_w_cm * board_h_cm / 10000,
        waste_area_m2=0.4,
        required_boards=1,
    )
    rebuilt = _plan_to_export_snapshot(cutting_plan)
    return snapshot, rebuilt, cutting_plan


def test_nested_plan_survives_snapshot_reload_and_export_rebuild():
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors

    _, plan = _plan(
        [_glass(40, 40, 50), _regular(12, 12, qty=3)],
        50,
        50,
    )
    snapshot, rebuilt, _ = _reload_export_snapshot(plan, board_w_cm=50, board_h_cm=50)

    before = {
        int(piece["id"]): (
            round(piece["x"], 4),
            round(piece["y"], 4),
            round(piece["w"], 4),
            round(piece["h"], 4),
            bool(piece.get("rotated")),
            piece.get(GLASS_HOST_PIECE_ID),
            piece.get("glass_hole_local_mm"),
            piece.get("piece_type"),
        )
        for piece in snapshot["sheets"][0]["pieces"]
    }
    after = {
        int(piece["id"]): (
            round(piece["x"], 4),
            round(piece["y"], 4),
            round(piece["w"], 4),
            round(piece["h"], 4),
            bool(piece.get("rotated")),
            piece.get(GLASS_HOST_PIECE_ID),
            piece.get("glass_hole_local_mm"),
            piece.get("piece_type"),
        )
        for piece in rebuilt["sheets"][0]["pieces"]
    }
    assert before == after
    assert sorted(_hosts({"sheets": snapshot["sheets"]})) == [1, 1, 1]
    assert sorted(_hosts({"sheets": rebuilt["sheets"]})) == [1, 1, 1]
    assert len(rebuilt["sheets"][0]["pieces"]) == 4
    assert len({piece["id"] for piece in rebuilt["sheets"][0]["pieces"]}) == 4
    assert _kerf_errors(rebuilt) == []


def test_glass_in_glass_host_chain_survives_reload():
    _, plan = _plan(
        [_glass(70, 70, 50), _glass(40, 40, 50), _regular(20, 20)],
        80,
        80,
    )
    snapshot, rebuilt, _ = _reload_export_snapshot(plan, board_w_cm=80, board_h_cm=80)
    before = {
        int(piece["id"]): piece.get(GLASS_HOST_PIECE_ID)
        for piece in snapshot["sheets"][0]["pieces"]
    }
    after = {
        int(piece["id"]): piece.get(GLASS_HOST_PIECE_ID)
        for piece in rebuilt["sheets"][0]["pieces"]
    }
    assert before == after
    assert before[2] == 1
    assert before[3] == 2
    assert all(
        piece.get("glass_hole_local_mm")
        for piece in rebuilt["sheets"][0]["pieces"]
        if piece.get("piece_type") == "Glass"
    )


def test_corner_guests_keep_geometry_through_reload():
    rows = [
        _glass(50, 50, 50),
        {
            "piece_type": "Clipped Corner",
            "width_cm": 15,
            "length_cm": 15,
            "qty": 1,
            "allow_rotation": 0,
            "clipped_corner_position": "Top Right",
            "clipped_corner_width_cm": 5,
            "clipped_corner_length_cm": 5,
        },
        {
            "piece_type": "L-Shaped Corner",
            "width_cm": 18,
            "length_cm": 18,
            "qty": 1,
            "allow_rotation": 0,
            "clipped_corner_position": "Top Right",
            "clipped_corner_width_cm": 8,
            "clipped_corner_length_cm": 8,
        },
    ]
    _, plan = _plan(rows, 60, 60)
    assert sorted(_hosts(plan)) == [1, 1]
    snapshot, rebuilt, _ = _reload_export_snapshot(plan, board_w_cm=60, board_h_cm=60)
    for source, target in (
        (snapshot["sheets"][0]["pieces"], rebuilt["sheets"][0]["pieces"]),
    ):
        by_id = {int(piece["id"]): piece for piece in target}
        for piece in source:
            restored = by_id[int(piece["id"])]
            assert restored.get("piece_type") == piece.get("piece_type")
            assert restored.get("clipped_corner_position") == piece.get(
                "clipped_corner_position"
            )
            assert restored.get("clipped_corner_width_cm") == piece.get(
                "clipped_corner_width_cm"
            )
            assert restored.get("clipped_corner_length_cm") == piece.get(
                "clipped_corner_length_cm"
            )
            assert restored.get(GLASS_HOST_PIECE_ID) == piece.get(GLASS_HOST_PIECE_ID)


def test_legacy_plan_without_host_id_is_not_rejected_for_absence():
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors

    pieces = expand_piece_groups([_regular(20, 20), _regular(15, 15)])
    left = make_placed_piece(pieces[0], 0, 0, 20, 20, False)
    right = make_placed_piece(pieces[1], 25, 0, 15, 15, False)
    plan = {
        "kerf_cm": 0.3,
        "sheets": [{"sheet_no": 1, "pieces": [left, right]}],
        "unplaced": [],
    }
    assert GLASS_HOST_PIECE_ID not in left
    assert GLASS_HOST_PIECE_ID not in right
    assert _kerf_errors(plan) == []
    issues, _, topology_aware = _cutting_plan_for_layout([left, right])
    assert topology_aware is False
    assert issues == []


def test_approved_snapshot_nesting_fields_are_not_rewritten_by_sanitize():
    import json

    from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
        sanitize_plan_snapshot,
    )

    _, plan = _plan([_glass(40, 40, 50), _regular(20, 20)], 50, 50)
    approved = sanitize_plan_snapshot(plan)
    original = json.dumps(approved, sort_keys=True)
    # Re-opening an approved plan only re-sanitizes; it must not drop nesting.
    reopened = sanitize_plan_snapshot(json.loads(original))
    assert json.dumps(reopened, sort_keys=True) == original
    assert sorted(_hosts({"sheets": reopened["sheets"]})) == [1]


def test_true_overlap_still_fails_export_after_reload():
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors

    _, plan = _plan([_glass(40, 40, 50), _regular(20, 20)], 50, 50)
    snapshot, _, _ = _reload_export_snapshot(plan, board_w_cm=50, board_h_cm=50)
    glass = next(
        piece
        for piece in snapshot["sheets"][0]["pieces"]
        if piece.get("piece_type") == "Glass"
    )
    guest = next(
        piece
        for piece in snapshot["sheets"][0]["pieces"]
        if piece.get(GLASS_HOST_PIECE_ID) == glass["id"]
    )
    conflict = dict(guest)
    conflict["x"] = glass["x"]
    conflict["y"] = glass["y"]
    rejected = {
        "kerf_cm": 0.3,
        "sheets": [{"sheet_no": 1, "pieces": [glass, conflict]}],
    }
    assert _kerf_errors(rejected)
