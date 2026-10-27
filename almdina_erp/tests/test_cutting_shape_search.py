"""Shape nesting, glass acceptance, small-piece safety, and board cancellation."""

from __future__ import annotations

from almdina_erp.almdina_erp.domain.cutting import (
    expand_piece_groups,
    optimize_plan,
    validate_plan,
)
from almdina_erp.almdina_erp.domain.cutting.evaluation import placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    GLASS_HOST_PIECE_ID,
    material_outline_cm,
)
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.placement_orientation import (
    PlacementOrientation,
    physical_edge_bands,
    transform_ring,
)
from almdina_erp.almdina_erp.domain.cutting.plan_search import improve_plan_search
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import (
    _orientations,
    _placed_corner,
    apply_shape_aware_nesting,
    non_quarter_rotation_is_admitted,
    void_edge_angle_deg,
)
from almdina_erp.almdina_erp.domain.cutting.small_piece_safety import (
    SmallPieceSafetyPolicy,
    blocking_active,
    safety_issues,
)


def _l_rows():
    return [
        {
            "piece_type": "L-Shaped Corner",
            "width_cm": 20,
            "length_cm": 20,
            "qty": 4,
            "clipped_corner_position": "Top Right",
            "clipped_corner_width_cm": 8,
            "clipped_corner_length_cm": 8,
            "allow_rotation": 1,
        },
        {"piece_type": "Regular", "width_cm": 10, "length_cm": 10, "qty": 1, "allow_rotation": 1},
    ]


def test_four_l_pieces_share_a_void_without_mirroring():
    pieces = expand_piece_groups(_l_rows())
    blocked = optimize_plan(
        pieces,
        40.3,
        40.3,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
    )
    allowed = optimize_plan(
        pieces,
        40.3,
        40.3,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=True,
    )

    assert len(blocked["sheets"]) == 1
    assert len(allowed["sheets"]) == 1
    assert not validate_plan(blocked, pieces, 40.3, 40.3, kerf_cm=0.3)
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in blocked["sheets"]
        for piece in sheet["pieces"]
    )
    assert sum(len(sheet["pieces"]) for sheet in blocked["sheets"]) == 5
    assert not placement_permission_errors(blocked, pieces, mirroring_allowed=False)
    turns = {
        int(piece.get("corner_rotation_quarter_turns") or 0)
        for sheet in blocked["sheets"]
        for piece in sheet["pieces"]
        if piece.get("piece_type") == "L-Shaped Corner"
    }
    assert turns <= {0, 1, 2, 3}
    assert 2 in turns or 3 in turns or 1 in turns


def test_half_turn_without_a_mirror_flag_is_allowed():
    piece = expand_piece_groups([_corner_row("L-Shaped Corner", qty=1)])[0]
    placed = _placed_corner(piece, x_cm=0, y_cm=0, mirrored=False, turns=2)
    plan = {"sheets": [{"sheet_no": 1, "pieces": [placed]}]}

    assert placed["mirrored"] is False
    assert placed["corner_rotation_quarter_turns"] == 2
    assert not placement_permission_errors(plan, [piece], mirroring_allowed=False)


def test_injected_mirror_is_rejected_even_from_another_search_path():
    pieces = expand_piece_groups([_corner_row("L-Shaped Corner", qty=1)])
    piece = pieces[0]
    smuggled = _placed_corner(piece, x_cm=0, y_cm=0, mirrored=True, turns=0)
    forbidden = {"sheets": [{"sheet_no": 1, "w": 40, "h": 40, "pieces": [smuggled]}]}

    assert placement_permission_errors(forbidden, pieces, mirroring_allowed=False)
    assert not placement_permission_errors(forbidden, pieces, mirroring_allowed=True)

    plan = optimize_plan(
        pieces,
        40,
        40,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=1,
        mirroring_allowed=False,
    )
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored") or piece.get("placement_mirrored")
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
    )
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)


def test_two_l_pieces_nest_on_one_board_without_mirroring():
    pieces = expand_piece_groups(
        [
            _corner_row(
                "L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                qty=2,
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=20,
            )
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=80.3)
    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        80.3,
        40.3,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )

    ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert len(improved["sheets"]) == 1
    assert sorted(ids) == sorted(piece["id"] for piece in pieces)
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in improved["sheets"]
        for piece in sheet["pieces"]
    )
    assert not validate_plan(improved, pieces, 80.3, 40.3, kerf_cm=0.3)
    assert not placement_permission_errors(improved, pieces, mirroring_allowed=False)
    outlines = [material_outline_cm(piece) for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert all(outline and len(outline) >= 6 for outline in outlines)


def test_opposite_hand_l_pieces_interlock_without_mirroring():
    pieces = expand_piece_groups(
        [
            _corner_row(
                "L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                qty=1,
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=20,
            ),
            _corner_row(
                "L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                qty=1,
                clipped_corner_position="Top Left",
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=20,
            ),
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=61)
    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        61,
        61,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert len(improved["sheets"]) == 1
    assert sorted(ids) == sorted(piece["id"] for piece in pieces)
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in improved["sheets"]
        for piece in sheet["pieces"]
    )
    assert not validate_plan(improved, pieces, 61, 61, kerf_cm=0.3)


def test_same_hand_l_interlock_uses_mirroring_only_when_allowed():
    pieces = expand_piece_groups(
        [
            _corner_row(
                "L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                qty=2,
                allow_rotation=0,
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=20,
            )
        ]
    )
    tight = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=61)
    blocked = apply_shape_aware_nesting(
        tight,
        pieces,
        61,
        61,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    allowed = apply_shape_aware_nesting(
        tight,
        pieces,
        61,
        61,
        0.3,
        mirroring_allowed=True,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    assert len(blocked["sheets"]) == 2
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in blocked["sheets"]
        for piece in sheet["pieces"]
    )
    assert len(allowed["sheets"]) == 1
    assert any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in allowed["sheets"]
        for piece in sheet["pieces"]
    )
    assert not placement_permission_errors(allowed, pieces, mirroring_allowed=True)
    assert not validate_plan(allowed, pieces, 61, 61, kerf_cm=0.3)


def test_three_l_pieces_keep_every_copy_without_mirroring():
    pieces = expand_piece_groups(
        [
            _corner_row(
                "L-Shaped Corner",
                width_cm=30,
                length_cm=30,
                qty=3,
                clipped_corner_width_cm=12,
                clipped_corner_length_cm=12,
            )
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)], [(0, 0)]], board=80)
    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        62,
        62,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert sorted(ids) == sorted(piece["id"] for piece in pieces)
    assert len(set(ids)) == 3
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in improved["sheets"]
        for piece in sheet["pieces"]
    )
    assert not placement_permission_errors(improved, pieces, mirroring_allowed=False)


def test_three_clipped_corners_keep_every_copy_without_a_void_angle():
    pieces = expand_piece_groups(
        [
            _corner_row(
                "Clipped Corner",
                width_cm=30,
                length_cm=30,
                qty=3,
                clipped_corner_width_cm=12,
                clipped_corner_length_cm=12,
            )
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)], [(0, 0)]], board=80)
    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        62,
        62,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert sorted(ids) == sorted(piece["id"] for piece in pieces)
    assert len(set(ids)) == 3
    assert not any(piece.get("placement_rotation_deg") for sheet in improved["sheets"] for piece in sheet["pieces"])
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in improved["sheets"]
        for piece in sheet["pieces"]
    )
    assert not placement_permission_errors(improved, pieces, mirroring_allowed=False)
    assert not validate_plan(improved, pieces, 62, 62, kerf_cm=0.3)


def test_disabling_mirroring_recalculates_without_a_mirror_flag():
    from almdina_erp.almdina_erp.domain.orders.piece_mirroring import piece_mirroring_allowed

    assert piece_mirroring_allowed(0) is False
    assert piece_mirroring_allowed(False) is False
    assert piece_mirroring_allowed(None) is False
    assert piece_mirroring_allowed("") is False
    assert piece_mirroring_allowed(1) is True

    pieces = expand_piece_groups(
        [
            _corner_row(
                "L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                qty=2,
                allow_rotation=0,
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=20,
            )
        ]
    )
    first = optimize_plan(
        pieces,
        61,
        61,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=piece_mirroring_allowed(1),
    )
    second = optimize_plan(
        pieces,
        61,
        61,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=piece_mirroring_allowed(0),
    )
    assert any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in first["sheets"]
        for piece in sheet["pieces"]
    )
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored") or piece.get("placement_mirrored")
        for sheet in second["sheets"]
        for piece in sheet["pieces"]
    )
    assert not placement_permission_errors(second, pieces, mirroring_allowed=False)
    assert placement_permission_errors(first, pieces, mirroring_allowed=False)


def test_two_clipped_corners_complement_without_a_void_angle():
    pieces = expand_piece_groups(
        [
            _corner_row(
                "Clipped Corner",
                width_cm=40,
                length_cm=40,
                qty=2,
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=20,
            )
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=80.3)
    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        80.3,
        40.3,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert len(improved["sheets"]) == 1
    assert sorted(ids) == sorted(piece["id"] for piece in pieces)
    assert not any(piece.get("placement_rotation_deg") for sheet in improved["sheets"] for piece in sheet["pieces"])
    assert not validate_plan(improved, pieces, 80.3, 40.3, kerf_cm=0.3)


def test_mixed_sizes_can_nest_when_outlines_clear():
    pieces = expand_piece_groups(
        [
            _corner_row(
                "L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                qty=1,
                clipped_corner_width_cm=18,
                clipped_corner_length_cm=18,
            ),
            _corner_row(
                "Clipped Corner",
                width_cm=20,
                length_cm=16,
                qty=1,
                clipped_corner_width_cm=6,
                clipped_corner_length_cm=5,
            ),
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=80)
    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        61,
        40,
        0.3,
        mirroring_allowed=True,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert sorted(ids) == sorted(piece["id"] for piece in pieces)
    assert not validate_plan(improved, pieces, 61, 40, kerf_cm=0.3)


def test_disabled_rotation_does_not_invent_a_turn():
    pieces = expand_piece_groups(
        [_corner_row("L-Shaped Corner", qty=2, allow_rotation=0, width_cm=20, length_cm=20)]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=50)
    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        50,
        20.3,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    for sheet in improved["sheets"]:
        for piece in sheet["pieces"]:
            assert int(piece.get("corner_rotation_quarter_turns") or 0) == 0
            assert not piece.get("mirrored")
    assert not placement_permission_errors(improved, pieces, mirroring_allowed=False)


def test_optimize_plan_rejects_a_smuggled_mirror_when_the_order_forbids_it(monkeypatch):
    pieces = expand_piece_groups([_corner_row("L-Shaped Corner", qty=2)])

    def _smuggle(plan, requested, *args, **kwargs):
        first = requested[0]
        plan = {
            "sheets": [{
                "sheet_no": 1,
                "w": 80,
                "h": 80,
                "pieces": [_placed_corner(first, x_cm=0, y_cm=0, mirrored=True, turns=0)],
            }],
            "unplaced": requested[1:],
            "method_key": plan.get("method_key") or "",
            "method_label": plan.get("method_label") or "",
        }
        return plan

    monkeypatch.setattr(
        "almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting.apply_shape_aware_nesting",
        _smuggle,
    )
    plan = optimize_plan(
        pieces,
        80,
        80,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=1,
        mirroring_allowed=False,
    )
    assert not any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
    )
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)


def test_four_clipped_corners_store_the_void_edge_angle():
    pieces = expand_piece_groups(
        [
            {
                "piece_type": "Clipped Corner",
                "width_cm": 20,
                "length_cm": 20,
                "qty": 4,
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 8,
                "clipped_corner_length_cm": 8,
                "allow_rotation": 1,
            },
            {
                "piece_type": "Regular",
                "width_cm": 8,
                "length_cm": 3,
                "qty": 1,
                "allow_rotation": 0,
            },
        ]
    )
    plan = optimize_plan(
        pieces,
        40.3,
        40.3,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=True,
    )
    angled = [
        piece
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
        if piece.get("placement_rotation_deg")
    ]

    assert len(plan["sheets"]) == 1
    assert len(angled) == 1
    assert angled[0]["placement_rotation_deg"] == void_edge_angle_deg(8, 8)
    assert angled[0]["placement_void_angle_deg"] == angled[0]["placement_rotation_deg"]
    assert not validate_plan(plan, pieces, 40.3, 40.3, kerf_cm=0.3)


def test_dxf_accepts_the_void_angle_and_rejects_another_angle():
    import math

    from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
        ContourCandidate,
        DxfTopologyError,
        ExpectedPieceEvidence,
        resolve_contour_ownership,
    )
    from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
        material_outline_cm,
    )

    pieces = expand_piece_groups(
        [
            {
                "piece_type": "Clipped Corner",
                "width_cm": 30,
                "length_cm": 24,
                "qty": 4,
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 12,
                "clipped_corner_length_cm": 6,
                "allow_rotation": 1,
            },
            {
                "piece_type": "Regular",
                "width_cm": 10,
                "length_cm": 3,
                "qty": 1,
                "allow_rotation": 0,
            },
        ]
    )
    plan = optimize_plan(
        pieces,
        60.3,
        48.3,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=True,
    )
    placed = [piece for sheet in plan["sheets"] for piece in sheet["pieces"]]
    expected = tuple(
        ExpectedPieceEvidence(
            width=piece["width_cm"] * 10,
            height=piece["length_cm"] * 10,
            allow_rotation=bool(piece["allow_rotation"]),
            piece_type=piece["piece_type"],
            clipped_cut_width_mm=piece["clipped_corner_width_cm"] * 10,
            clipped_cut_length_mm=piece["clipped_corner_length_cm"] * 10,
            clipped_corner_position=piece["clipped_corner_position"],
        )
        for piece in pieces
    )
    contours = tuple(
        ContourCandidate(
            piece["id"],
            tuple((point[0] * 10, point[1] * 10) for point in material_outline_cm(piece)),
        )
        for piece in placed
    )
    admitted = resolve_contour_ownership(contours, expected, dimension_tolerance=0.2)
    assert len(admitted.parts) == 5

    radians = math.radians(33)
    cosine, sine = math.cos(radians), math.sin(radians)
    center = (30.15 * 10, 24.15 * 10)
    tilted = tuple(
        (
            center[0] + px * cosine - py * sine,
            center[1] + px * sine + py * cosine,
        )
        for px, py in ((-50, -15), (50, -15), (50, 15), (-50, 15))
    )
    replaced = tuple(
        ContourCandidate(contour.key, tilted if contour.key == 5 else contour.polygon)
        for contour in contours
    )
    try:
        resolve_contour_ownership(replaced, expected, dimension_tolerance=0.2)
    except DxfTopologyError:
        return
    raise AssertionError("an angle other than the void edge was accepted")


def test_non_quarter_angle_is_admitted_only_for_the_void_edge():
    angle = void_edge_angle_deg(12, 6)
    assert angle is not None
    assert non_quarter_rotation_is_admitted(
        angle,
        cut_width_cm=12,
        cut_length_cm=6,
        outline_inside_void=True,
    )
    assert not non_quarter_rotation_is_admitted(
        33,
        cut_width_cm=12,
        cut_length_cm=6,
        outline_inside_void=True,
    )
    assert not non_quarter_rotation_is_admitted(
        angle,
        cut_width_cm=12,
        cut_length_cm=6,
        outline_inside_void=False,
    )


def test_void_rotation_keeps_piece_size_and_rejects_a_different_angle():
    import math

    pieces = expand_piece_groups(
        [{"width_cm": 12, "length_cm": 4, "qty": 1, "allow_rotation": 0}]
    )
    piece = pieces[0]
    angle = void_edge_angle_deg(12, 6)
    radians = math.radians(angle or 0)
    cosine, sine = math.cos(radians), math.sin(radians)
    center = (15.0, 15.0)
    outline = []
    for px, py in ((-6, -2), (6, -2), (6, 2), (-6, 2)):
        outline.append((center[0] + px * cosine - py * sine, center[1] + px * sine + py * cosine))
    xs = [point[0] for point in outline]
    ys = [point[1] for point in outline]
    placed = make_placed_piece(piece, min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), False)
    placed["placement_outline_cm"] = outline
    placed["placement_rotation_deg"] = angle
    placed["placement_void_angle_deg"] = angle
    fitting = {
        "sheets": [{"sheet_no": 1, "pieces": [placed]}],
        "unplaced": [],
    }
    assert validate_plan(fitting, pieces, 30, 30, kerf_cm=0) == []

    placed["placement_rotation_deg"] = 33
    rejected = validate_plan(
        {"sheets": [{"sheet_no": 1, "pieces": [placed]}], "unplaced": []},
        pieces,
        30,
        30,
        kerf_cm=0,
    )
    assert rejected


def test_edge_distance_alone_does_not_block_and_missing_criteria_stay_inactive():
    piece = {"id": 1, "label": "1.1", "x": 0, "y": 0, "w": 5, "h": 5}
    plan = {"sheets": [{"sheet_no": 1, "pieces": [piece]}]}
    inactive = SmallPieceSafetyPolicy(enabled=True, max_area_m2=0.01)
    assert blocking_active(inactive) is False
    assert safety_issues(plan, inactive) == []
    assert safety_issues(plan, SmallPieceSafetyPolicy()) == []

    active = SmallPieceSafetyPolicy(enabled=True, max_area_m2=0.01, support_gap_cm=2)
    assert blocking_active(active) is True
    assert safety_issues(plan, active)
    supported = {
        "sheets": [{
            "sheet_no": 1,
            "pieces": [piece, {"id": 2, "label": "2.1", "x": 5.5, "y": 0, "w": 20, "h": 20}],
        }]
    }
    assert safety_issues(supported, active) == []
    assert safety_issues(plan, active) == safety_issues(plan, active)


def test_cancellable_board_moves_when_the_piece_fits_and_validation_passes():
    pieces = expand_piece_groups(
        [
            {"width_cm": 10, "length_cm": 10, "qty": 1, "allow_rotation": 0},
            {"width_cm": 10, "length_cm": 10, "qty": 1, "allow_rotation": 0},
        ]
    )
    first = make_placed_piece(pieces[0], 0, 0, 10, 10, False)
    second = make_placed_piece(pieces[1], 0, 0, 10, 10, False)
    plan = enrich_plan_metrics(
        {
            "sheets": [
                {"sheet_no": 1, "w": 100, "h": 100, "pieces": [first]},
                {"sheet_no": 2, "w": 100, "h": 100, "pieces": [second]},
            ],
            "unplaced": [],
            "method_key": "MaxRects Best Short Side",
        },
        "MaxRects Best Short Side",
        "CNC Router",
        min_remnant_width_cm=0,
        min_remnant_length_cm=0,
        min_remnant_area_m2=0,
    )
    improved = improve_plan_search(
        plan,
        pieces,
        100,
        100,
        0.3,
        machine_type="CNC Router",
        time_limit_sec=2,
        min_remnant_width_cm=0,
        min_remnant_length_cm=0,
        min_remnant_area_m2=0,
    )

    assert len(improved["sheets"]) == 1
    assert not validate_plan(improved, pieces, 100, 100, kerf_cm=0.3)
    assert sorted(piece["id"] for piece in improved["sheets"][0]["pieces"]) == [1, 2]


def test_panel_saw_search_does_not_rewrite_the_plan():
    pieces = expand_piece_groups([{"width_cm": 10, "length_cm": 10, "qty": 1}])
    placed = make_placed_piece(pieces[0], 0, 0, 10, 10, False)
    plan = {
        "sheets": [
            {"sheet_no": 1, "w": 100, "h": 100, "pieces": [placed]},
            {"sheet_no": 2, "w": 100, "h": 100, "pieces": [dict(placed, id=2)]},
        ],
        "unplaced": [],
    }
    assert improve_plan_search(
        plan,
        pieces,
        100,
        100,
        0.3,
        machine_type="Panel Saw",
        time_limit_sec=2,
        min_remnant_width_cm=0,
        min_remnant_length_cm=0,
        min_remnant_area_m2=0,
    ) is plan


def test_benchmark_record_for_the_l_cluster_and_inactive_safety():
    pieces = expand_piece_groups(_l_rows())
    plan = optimize_plan(
        pieces,
        40.3,
        40.3,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=True,
    )
    record = {
        "case": "four-l-and-inner",
        "boards": len(plan["sheets"]),
        "pieces": sum(len(sheet["pieces"]) for sheet in plan["sheets"]),
        "algorithm": plan.get("method_key"),
        "machine": "CNC Router",
        "geometry_valid": validate_plan(plan, pieces, 40.3, 40.3, kerf_cm=0.3) == [],
        "safety_blocking": blocking_active(SmallPieceSafetyPolicy()),
        "largest_reusable_remnant_m2": plan["industrial_metrics"]["largest_reusable_free_area_m2"],
    }

    assert record["boards"] == 1
    assert record["pieces"] == 5
    assert record["geometry_valid"] is True
    assert record["safety_blocking"] is False
    assert record["largest_reusable_remnant_m2"] >= 0


_REMNANT = {
    "min_remnant_width_cm": 30,
    "min_remnant_length_cm": 30,
    "min_remnant_area_m2": 0.09,
}


def _corner_row(piece_type, **extra):
    row = {
        "piece_type": piece_type,
        "width_cm": 20,
        "length_cm": 20,
        "qty": 4,
        "clipped_corner_position": "Top Right",
        "clipped_corner_width_cm": 8,
        "clipped_corner_length_cm": 8,
        "allow_rotation": 1,
        "edge_long_left": 1,
        "extra_liner": 1,
        "liner_reference_side": "edge_long_left",
        "liner_offset_cm": 1,
        "liner_width_cm": 2,
        "liner_start_cm": 0,
        "liner_length_cm": 10,
        "extra_back_groove": 1,
        "back_groove_reference_side": "edge_long_left",
        "back_groove_offset_cm": 1,
        "back_groove_width_cm": 1.2,
        "back_groove_start_cm": 0,
        "back_groove_length_cm": 8,
        "extra_recessed_handle_cutout": 1,
        "recessed_handle_reference_side": "edge_width_top",
        "recessed_handle_offset_cm": 1,
        "recessed_handle_width_cm": 3,
        "recessed_handle_start_cm": 1,
        "recessed_handle_length_cm": 8,
    }
    row.update(extra)
    return row


def _sheet_plan(pieces, placed_at, board=100):
    sheets = []
    cursor = 0
    for sheet_no, spots in enumerate(placed_at, start=1):
        sheet_pieces = []
        for x_pos, y_pos in spots:
            source = pieces[cursor]
            cursor += 1
            sheet_pieces.append(
                make_placed_piece(
                    source,
                    x_pos,
                    y_pos,
                    source["width_cm"],
                    source["length_cm"],
                    False,
                )
            )
        sheets.append({"sheet_no": sheet_no, "w": board, "h": board, "pieces": sheet_pieces})
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


def _apply(plan, pieces, board=100, mirroring_allowed=False, machine_type="CNC Router"):
    return apply_shape_aware_nesting(
        plan,
        pieces,
        board,
        board,
        0.3,
        mirroring_allowed=mirroring_allowed,
        machine_type=machine_type,
        time_limit_sec=2,
        **_REMNANT,
    )


def _same_points(actual, expected, tolerance=0.02):
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


def test_one_board_l_cluster_improves_the_separable_remnant():
    pieces = expand_piece_groups([_corner_row("L-Shaped Corner")])
    plan = _sheet_plan(
        pieces,
        [[(40, 0), (40, 20.4), (40, 40.8), (40, 61.2)]],
    )
    improved = _apply(plan, pieces)
    again = _apply(improved, pieces)

    assert len(plan["sheets"]) == 1
    assert len(improved["sheets"]) == 1
    assert improved is not plan
    assert improved["industrial_rank"] < plan["industrial_rank"]
    assert (
        improved["industrial_metrics"]["largest_reusable_free_area_m2"]
        > plan["industrial_metrics"]["largest_reusable_free_area_m2"]
    )
    assert again is improved
    assert not validate_plan(improved, pieces, 100, 100, kerf_cm=0.3)
    assert {
        piece["clipped_corner_position"] for piece in improved["sheets"][0]["pieces"]
    } == {"Top Right"}


def test_one_board_l_cluster_can_hold_the_inner_piece():
    pieces = expand_piece_groups(
        [_corner_row("L-Shaped Corner"), {"piece_type": "Regular", "width_cm": 8, "length_cm": 8, "qty": 1}]
    )
    plan = _sheet_plan(
        pieces,
        [[(40, 0), (40, 20.4), (40, 40.8), (40, 61.2), (70, 70)]],
    )
    improved = _apply(plan, pieces)
    guest = next(piece for piece in improved["sheets"][0]["pieces"] if piece["id"] == 5)

    assert len(improved["sheets"]) == 1
    assert improved["industrial_rank"] < plan["industrial_rank"]
    assert 12 < guest["x"] < 30
    assert 12 < guest["y"] < 30
    assert not validate_plan(improved, pieces, 100, 100, kerf_cm=0.3)


def test_one_board_clipped_cluster_keeps_the_void_angle():
    pieces = expand_piece_groups(
        [
            _corner_row("Clipped Corner"),
            {"piece_type": "Regular", "width_cm": 8, "length_cm": 3, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = _sheet_plan(
        pieces,
        [[(40, 0), (40, 20.4), (40, 40.8), (40, 61.2), (75, 70)]],
    )
    improved = _apply(plan, pieces, mirroring_allowed=True)
    angled = [
        piece
        for piece in improved["sheets"][0]["pieces"]
        if piece.get("placement_rotation_deg")
    ]

    assert len(improved["sheets"]) == 1
    assert len(angled) == 1
    assert angled[0]["placement_rotation_deg"] == void_edge_angle_deg(8, 8)
    assert not validate_plan(improved, pieces, 100, 100, kerf_cm=0.3)


def test_same_board_count_without_a_better_remnant_keeps_the_plan():
    pieces = expand_piece_groups(
        [
            {"width_cm": 60, "length_cm": 60, "qty": 1, "allow_rotation": 0},
            {"width_cm": 60, "length_cm": 60, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]])
    improved = improve_plan_search(
        plan,
        pieces,
        100,
        100,
        0.3,
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
        **_REMNANT,
    )

    assert improved is plan
    assert len(improved["sheets"]) == 2


def test_same_board_count_accepts_a_larger_separable_remnant():
    pieces = expand_piece_groups(
        [
            {"width_cm": 70, "length_cm": 70, "qty": 2, "allow_rotation": 0},
            {"width_cm": 20, "length_cm": 20, "qty": 2, "allow_rotation": 0},
        ]
    )
    blocks = [piece for piece in pieces if piece["width_cm"] == 70]
    splitters = [piece for piece in pieces if piece["width_cm"] == 20]
    ordered = [blocks[0], splitters[0], blocks[1], splitters[1]]
    plan = _sheet_plan(ordered, [[(0, 0), (70.3, 70.3)], [(0, 0), (70.3, 70.3)]])
    improved = improve_plan_search(
        plan,
        ordered,
        100,
        100,
        0.3,
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
        **_REMNANT,
    )

    assert len(improved["sheets"]) == 2
    assert improved["industrial_rank"] < plan["industrial_rank"]
    assert (
        improved["industrial_metrics"]["largest_reusable_free_area_m2"]
        > plan["industrial_metrics"]["largest_reusable_free_area_m2"]
    )
    assert not validate_plan(improved, ordered, 100, 100, kerf_cm=0.3)
    ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert sorted(ids) == sorted(piece["id"] for piece in ordered)


def test_shape_nesting_refuses_an_extra_board():
    pieces = expand_piece_groups(
        [
            _corner_row("L-Shaped Corner"),
            {"width_cm": 70, "length_cm": 70, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = _sheet_plan(
        pieces,
        [[(70.4, 0), (70.4, 20.4), (70.4, 40.8), (70.4, 61.2), (0, 0)]],
    )
    improved = _apply(plan, pieces)

    assert len(plan["sheets"]) == 1
    assert improved is plan


def test_invalid_geometry_keeps_the_original_plan(monkeypatch):
    pieces = expand_piece_groups([_corner_row("L-Shaped Corner")])
    plan = _sheet_plan(pieces, [[(40, 0), (40, 20.4), (40, 40.8), (40, 61.2)]])
    monkeypatch.setattr(
        "almdina_erp.almdina_erp.domain.cutting.evaluation.validate_plan",
        lambda *args, **kwargs: ["overlap"],
    )

    assert _apply(plan, pieces) is plan


def test_orientations_follow_rotation_and_mirroring_permission():
    locked = expand_piece_groups([_corner_row("L-Shaped Corner", allow_rotation=0, qty=1)])[0]
    free = expand_piece_groups([_corner_row("L-Shaped Corner", allow_rotation=1, qty=1)])[0]

    assert {(item[0], item[1]) for item in _orientations(locked, False)} == {(False, 0)}
    assert {(item[0], item[1]) for item in _orientations(free, False)} == {
        (False, 0),
        (False, 1),
        (False, 2),
        (False, 3),
    }
    assert any(item[0] for item in _orientations(free, True))
    assert not any(item[0] for item in _orientations(free, False))


def test_recorded_turns_keep_edge_identity_and_addons():
    piece = expand_piece_groups(
        [_corner_row("L-Shaped Corner", width_cm=30, length_cm=16, qty=1)]
    )[0]
    bare = make_placed_piece(piece, 0, 0, 30, 16, False)
    local = material_outline_cm(bare)
    for turns in (2, 3):
        placed = _placed_corner(piece, x_cm=1, y_cm=2, mirrored=False, turns=turns)
        expected = [
            (1 + point[0], 2 + point[1])
            for point in transform_ring(
                local,
                PlacementOrientation(False, turns),
                width=30,
                height=16,
            )
        ]
        assert placed["clipped_corner_position"] == "Top Right"
        assert placed["edge_long_left"] == 1
        assert placed["liner_reference_side"] == "edge_long_left"
        assert placed["back_groove_reference_side"] == "edge_long_left"
        assert placed["recessed_handle_reference_side"] == "edge_width_top"
        assert placed["corner_rotation_quarter_turns"] == turns
        _same_points(material_outline_cm(placed), expected)
    mirrored = _placed_corner(piece, x_cm=0, y_cm=0, mirrored=True, turns=0)
    bands = physical_edge_bands(
        {"left": "band", "top": "", "right": "", "bottom": ""},
        PlacementOrientation(True, 1),
    )
    assert mirrored["edge_long_left"] == 1
    assert mirrored["mirrored"] is True
    assert bands[3] == "band"
    forbidden = {
        "sheets": [{
            "sheet_no": 1,
            "pieces": [_placed_corner(piece, x_cm=0, y_cm=0, mirrored=False, turns=2)],
        }]
    }
    piece["allow_rotation"] = 0
    assert placement_permission_errors(forbidden, [piece], mirroring_allowed=False)


def test_plan_dxf_roundtrip_matches_the_placed_polygons(tmp_path):
    import ezdxf

    from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
        ContourCandidate,
        ExpectedPieceEvidence,
        resolve_contour_ownership,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry

    pieces = expand_piece_groups(
        [
            _corner_row(
                "Clipped Corner",
                width_cm=30,
                length_cm=24,
                clipped_corner_width_cm=12,
                clipped_corner_length_cm=6,
            ),
            {"piece_type": "Regular", "width_cm": 10, "length_cm": 3, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = optimize_plan(
        pieces,
        60.3,
        48.3,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=True,
    )
    placed = [piece for sheet in plan["sheets"] for piece in sheet["pieces"]]
    outlines = [material_outline_cm(piece) for piece in placed]
    assert all(outline is not None for outline in outlines)
    angled = [piece for piece in placed if piece.get("placement_rotation_deg")]
    assert len(angled) == 1
    assert angled[0]["placement_rotation_deg"] == void_edge_angle_deg(12, 6)

    document = ezdxf.new("R2010")
    for name in ("GEOMETRY", "CUT_PATH", "TEXT"):
        document.layers.add(name)
    modelspace = document.modelspace()
    for outline in outlines:
        ring = [(point[0] * 10, point[1] * 10) for point in outline]
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "GEOMETRY"}, close=True)
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "CUT_PATH"}, close=True)
    path = tmp_path / "cluster.dxf"
    document.saveas(path)
    loaded = read_dxf_geometry(
        str(path),
        relevant_layers={"GEOMETRY", "CUT_PATH"},
    )
    layers = {segment["layer"] for segment in loaded["segments"]}
    assert {"GEOMETRY", "CUT_PATH"} <= layers
    rings = []
    for entity_id in sorted({segment["entity_id"] for segment in loaded["segments"] if segment["layer"] == "GEOMETRY"}):
        segments = [
            segment
            for segment in loaded["segments"]
            if segment["entity_id"] == entity_id and segment["layer"] == "GEOMETRY"
        ]
        points = [segments[0]["start"]]
        points.extend(segment["end"] for segment in segments)
        if points[0] == points[-1]:
            points = points[:-1]
        rings.append(points)
    assert len(rings) == len(outlines)
    for outline, ring in zip(outlines, rings, strict=True):
        _same_points([(point[0] * 10, point[1] * 10) for point in outline], ring, tolerance=0.05)

    expected = tuple(
        ExpectedPieceEvidence(
            width=piece["width_cm"] * 10,
            height=piece["length_cm"] * 10,
            allow_rotation=bool(piece["allow_rotation"]),
            piece_type=piece["piece_type"],
            clipped_cut_width_mm=piece["clipped_corner_width_cm"] * 10,
            clipped_cut_length_mm=piece["clipped_corner_length_cm"] * 10,
            clipped_corner_position=piece["clipped_corner_position"],
        )
        for piece in pieces
    )
    admitted = resolve_contour_ownership(
        tuple(ContourCandidate(index, tuple(ring)) for index, ring in enumerate(rings, start=1)),
        expected,
        dimension_tolerance=0.2,
    )
    assert len(admitted.parts) == 5


def test_glass_nesting_still_accepts_a_fitting_guest():
    pieces = expand_piece_groups(
        [
            {
                "piece_type": "Glass",
                "width_cm": 40,
                "length_cm": 40,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 50,
            },
            {"piece_type": "Regular", "width_cm": 20, "length_cm": 20, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = optimize_plan(
        pieces,
        50,
        50,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
    )
    hosts = [
        piece.get(GLASS_HOST_PIECE_ID)
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
    ]

    assert hosts.count(1) == 1
    assert len(plan["sheets"]) == 1
    assert not validate_plan(plan, pieces, 50, 50, kerf_cm=0.3)


def test_shape_nesting_does_not_drop_an_existing_glass_nest():
    pieces = expand_piece_groups(
        [
            _corner_row("L-Shaped Corner"),
            {
                "piece_type": "Glass",
                "width_cm": 40,
                "length_cm": 40,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 50,
            },
            {"piece_type": "Regular", "width_cm": 18, "length_cm": 18, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = optimize_plan(
        pieces,
        100,
        100,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=True,
    )
    hosts = [
        piece.get(GLASS_HOST_PIECE_ID)
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
    ]

    assert hosts.count(5) == 1
    assert not validate_plan(plan, pieces, 100, 100, kerf_cm=0.3)


def test_panel_saw_shape_nesting_does_not_rewrite_a_single_board():
    pieces = expand_piece_groups([_corner_row("L-Shaped Corner")])
    plan = _sheet_plan(pieces, [[(40, 0), (40, 20.4), (40, 40.8), (40, 61.2)]])

    assert _apply(plan, pieces, machine_type="Panel Saw") is plan


def test_search_passes_stay_within_a_measured_time_budget():
    import time

    cases = {
        "small": ([{"width_cm": 20, "length_cm": 30, "qty": 4, "allow_rotation": 1}], 80, 80, 1),
        "medium": (
            [{"width_cm": 25, "length_cm": 18, "qty": 12, "allow_rotation": 1}],
            120,
            80,
            2,
        ),
        "large": (
            [{"width_cm": 22, "length_cm": 14, "qty": 28, "allow_rotation": 1}],
            244,
            122,
            3,
        ),
        "corners": ([_corner_row("L-Shaped Corner"), _corner_row("Clipped Corner")], 80, 80, 2),
        "glass": (
            [
                {
                    "piece_type": "Glass",
                    "width_cm": 40,
                    "length_cm": 40,
                    "qty": 3,
                    "allow_rotation": 0,
                    "glass_margin_mm": 50,
                },
                {"width_cm": 18, "length_cm": 18, "qty": 3, "allow_rotation": 0},
            ],
            90,
            50,
            2,
        ),
    }
    measured = {}
    for name, (rows, width, height, limit) in cases.items():
        pieces = expand_piece_groups(rows)
        started = time.perf_counter()
        optimize_plan(
            pieces,
            width,
            height,
            0.3,
            selected_mode="Auto",
            machine_type="CNC Router",
            time_limit_sec=limit,
            mirroring_allowed=False,
        )
        measured[name] = time.perf_counter() - started
    print("CUTTING_SEARCH_SECONDS " + " ".join(f"{name}={value:.3f}" for name, value in measured.items()))
    assert measured["small"] < 8, measured
    assert measured["medium"] < 12
    assert measured["large"] < 20
    assert measured["corners"] < 12
    assert measured["glass"] < 15
