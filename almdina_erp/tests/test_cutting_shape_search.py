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
from almdina_erp.almdina_erp.domain.cutting.plan_search import _spot_on_sheet, improve_plan_search
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import (
    _inward_score,
    _orientations,
    _pair_inward_score,
    _placed_corner,
    _pull_loose_pieces,
    _recorded_facing,
    _sources_by_id,
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
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=90)
    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        90,
        90,
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
    assert _symmetric_slot_pair(
        *[piece for sheet in improved["sheets"] for piece in sheet["pieces"]],
        board=(90, 90),
    )
    assert not validate_plan(improved, pieces, 90, 90, kerf_cm=0.3)


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
    tight = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=90)
    blocked = apply_shape_aware_nesting(
        tight,
        pieces,
        90,
        90,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )
    allowed = apply_shape_aware_nesting(
        tight,
        pieces,
        90,
        90,
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
    allowed_pieces = [piece for sheet in allowed["sheets"] for piece in sheet["pieces"]]
    assert _symmetric_slot_pair(allowed_pieces[0], allowed_pieces[1], board=(90, 90))
    assert any(
        piece.get("mirrored") or piece.get("corner_mirrored")
        for piece in allowed_pieces
    )
    assert not any(int(piece.get("corner_rotation_quarter_turns") or 0) for piece in allowed_pieces)
    assert not placement_permission_errors(allowed, pieces, mirroring_allowed=True)
    assert not validate_plan(allowed, pieces, 90, 90, kerf_cm=0.3)


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
        90,
        90,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=piece_mirroring_allowed(1),
    )
    second = optimize_plan(
        pieces,
        90,
        90,
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


def test_two_clipped_corners_use_the_symmetric_slot_pair():
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
    placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"]]
    ids = [piece["id"] for piece in placed]
    assert len(improved["sheets"]) == 1
    assert sorted(ids) == sorted(piece["id"] for piece in pieces)
    assert _symmetric_slot_pair(placed[0], placed[1], board=(80.3, 40.3))
    assert not any(piece.get("placement_rotation_deg") for piece in placed)
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


def test_shape_nesting_keeps_a_valid_quad_on_an_extra_board():
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
    corners = [
        piece
        for sheet in improved["sheets"]
        for piece in sheet["pieces"]
        if piece["piece_type"] == "L-Shaped Corner"
    ]
    ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]

    assert len(plan["sheets"]) == 1
    assert len(improved["sheets"]) == 2
    assert sorted(ids) == sorted(piece["id"] for piece in pieces)
    assert len(ids) == len(set(ids))
    assert {int(piece.get("corner_rotation_quarter_turns") or 0) for piece in corners} == {0, 1, 2, 3}
    assert not validate_plan(improved, pieces, 100, 100, kerf_cm=0.3)


def test_optimize_plan_rejects_the_valid_quad_on_an_extra_board(monkeypatch):
    pieces = expand_piece_groups([
        _corner_row("L-Shaped Corner"),
        {"width_cm": 70, "length_cm": 70, "qty": 1, "allow_rotation": 0},
    ])
    baseline = _sheet_plan(
        pieces, [[(70.4, 0), (70.4, 20.4), (70.4, 40.8), (70.4, 61.2), (0, 0)]],
    )
    candidates = []

    def shape(*args, **kwargs):
        candidate = apply_shape_aware_nesting(*args, **kwargs)
        candidates.append(candidate)
        return candidate

    prefix = "almdina_erp.almdina_erp.domain.cutting."
    monkeypatch.setattr(prefix + "optimizer.run_single_method", lambda *a, **k: baseline)
    monkeypatch.setattr(prefix + "shape_aware_nesting.apply_shape_aware_nesting", shape)
    result = optimize_plan(
        pieces, 100, 100, 0.3, selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router", time_limit_sec=2,
    )
    assert len(candidates[0]["sheets"]) == 2
    assert not validate_plan(candidates[0], pieces, 100, 100, kerf_cm=0.3)
    assert len(result["sheets"]) == 1
    assert not validate_plan(result, pieces, 100, 100, kerf_cm=0.3)
    assert result.get("shape_nesting_diagnostics", {}).get("outcome") != "accepted"


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


def test_one_rotatable_l_turns_its_notch_inward():
    from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _inward_score

    pieces = expand_piece_groups([_corner_row("L-Shaped Corner", qty=1)])
    plan = _sheet_plan(pieces, [[(0, 0)]], board=80)
    improved = _apply(plan, pieces, board=80)
    placed = improved["sheets"][0]["pieces"][0]

    assert improved is not plan
    assert _inward_score(placed, 80, 80) > 0
    assert int(placed.get("corner_rotation_quarter_turns") or 0) in {0, 1, 2, 3}
    assert not placed.get("mirrored")
    assert not validate_plan(improved, pieces, 80, 80, kerf_cm=0.3)


def test_locked_single_l_stays_on_the_ordinary_plan():
    pieces = expand_piece_groups([_corner_row("L-Shaped Corner", qty=1, allow_rotation=0)])
    plan = _sheet_plan(pieces, [[(0, 0)]], board=80)
    improved = _apply(plan, pieces, board=80, mirroring_allowed=False)

    assert improved is plan
    assert "corner_rotation_quarter_turns" not in improved["sheets"][0]["pieces"][0]


def test_two_identical_l_pieces_use_a_half_turn_without_a_mirror():
    pieces = expand_piece_groups(
        [_corner_row("L-Shaped Corner", width_cm=40, length_cm=40, qty=2, clipped_corner_width_cm=20, clipped_corner_length_cm=20)]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=80.3)
    improved = apply_shape_aware_nesting(
        plan, pieces, 80.3, 40.3, 0.3, mirroring_allowed=False, machine_type="CNC Router", time_limit_sec=2, **_REMNANT
    )
    placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"]]

    assert len(improved["sheets"]) == 1
    assert _symmetric_slot_pair(placed[0], placed[1])
    assert not any(piece.get("mirrored") for piece in placed)
    assert not validate_plan(improved, pieces, 80.3, 40.3, kerf_cm=0.3)


def test_two_l_pieces_without_rotation_or_mirroring_are_not_paired():
    pieces = expand_piece_groups(
        [_corner_row("L-Shaped Corner", qty=2, allow_rotation=0, width_cm=40, length_cm=40, clipped_corner_width_cm=20, clipped_corner_length_cm=20)]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=80)
    improved = _apply(plan, pieces, board=80, mirroring_allowed=False)

    assert improved is plan
    assert len(improved["sheets"]) == 2
    assert not _same_sheet_interlock(improved)


def test_different_l_sizes_are_not_a_matching_pair():
    pieces = expand_piece_groups(
        [
            _corner_row("L-Shaped Corner", qty=1, width_cm=40, length_cm=40, clipped_corner_width_cm=16, clipped_corner_length_cm=16),
            _corner_row("L-Shaped Corner", qty=1, width_cm=24, length_cm=24, clipped_corner_width_cm=8, clipped_corner_length_cm=8),
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=100)
    improved = _apply(plan, pieces, board=100)
    placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"]]

    assert sorted(piece["id"] for piece in placed) == [1, 2]
    assert not _same_sheet_interlock(improved)


def test_l_and_clipped_corners_are_not_a_matching_pair():
    pieces = expand_piece_groups(
        [
            _corner_row("L-Shaped Corner", qty=1),
            _corner_row("Clipped Corner", qty=1),
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)]], board=80)
    improved = _apply(plan, pieces, board=80)
    placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"]]

    assert {piece["piece_type"] for piece in placed} == {"L-Shaped Corner", "Clipped Corner"}
    assert not _same_sheet_interlock(improved)


def test_three_identical_l_pieces_become_a_pair_and_a_single():
    pieces = expand_piece_groups(
        [_corner_row("L-Shaped Corner", qty=3, width_cm=30, length_cm=30, clipped_corner_width_cm=12, clipped_corner_length_cm=12)]
    )
    plan = _sheet_plan(pieces, [[(0, 0)], [(0, 0)], [(0, 0)]], board=80)
    improved = _apply(plan, pieces, board=80)
    placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"]]
    pairs = [
        (left, right)
        for index, left in enumerate(placed)
        for right in placed[index + 1 :]
        if _symmetric_slot_pair(left, right, board=(80, 80))
    ]
    assert sorted(piece["id"] for piece in placed) == [1, 2, 3]
    assert len(pairs) == 1
    paired_ids = {pairs[0][0]["id"], pairs[0][1]["id"]}
    single = [piece for piece in placed if piece["id"] not in paired_ids]
    assert len(single) == 1
    assert len({_recorded_facing(piece) for piece in placed}) >= 2
    assert _inward_score(single[0], 80, 80) > 0.05
    assert not any(piece.get("mirrored") for piece in placed)
    assert not validate_plan(improved, pieces, 80, 80, kerf_cm=0.3)


def test_identical_l_counts_split_into_quads_pairs_and_singles():
    for qty, quad_groups in ((6, 1), (7, 1), (8, 2)):
        pieces = expand_piece_groups([_corner_row("L-Shaped Corner", qty=qty)])
        plan = _sheet_plan(pieces, [[(0, 0)] for _piece in pieces], board=120)
        improved = _apply(plan, pieces, board=120)
        placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"]]
        turns = sorted(int(piece.get("corner_rotation_quarter_turns") or 0) for piece in placed if "corner_rotation_quarter_turns" in piece)

        assert sorted(piece["id"] for piece in placed) == list(range(1, qty + 1))
        assert len(placed) == len({piece["id"] for piece in placed})
        assert turns.count(0) >= quad_groups
        assert turns.count(1) >= quad_groups
        assert turns.count(2) >= quad_groups
        assert turns.count(3) >= quad_groups
        assert not validate_plan(improved, pieces, 120, 120, kerf_cm=0.3)


def test_a_different_piece_can_sit_in_an_l_void():
    pieces = expand_piece_groups(
        [
            _corner_row("L-Shaped Corner"),
            {"piece_type": "Regular", "width_cm": 8, "length_cm": 6, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0), (0, 20.4), (0, 40.8), (0, 61.2), (70, 70)]], board=100)
    improved = _apply(plan, pieces, board=100)
    guest = next(piece for sheet in improved["sheets"] for piece in sheet["pieces"] if piece["id"] == 5)

    assert 12 < guest["x"] < 28
    assert 12 < guest["y"] < 28
    assert not validate_plan(improved, pieces, 100, 100, kerf_cm=0.3)


def test_two_guests_are_tried_in_the_same_l_void():
    pieces = expand_piece_groups(
        [
            _corner_row("L-Shaped Corner"),
            {"piece_type": "Regular", "width_cm": 6, "length_cm": 6, "qty": 2, "allow_rotation": 0},
        ]
    )
    plan = _sheet_plan(
        pieces,
        [[(0, 0), (0, 20.4), (0, 40.8), (0, 61.2), (70, 70), (80, 80)]],
        board=100,
    )
    improved = _apply(plan, pieces, board=100)
    guests = [piece for sheet in improved["sheets"] for piece in sheet["pieces"] if piece["id"] in {5, 6}]

    assert len(guests) == 2
    assert all(12 < piece["x"] < 28 and 12 < piece["y"] < 28 for piece in guests)
    assert not validate_plan(improved, pieces, 100, 100, kerf_cm=0.3)


def test_a_guest_larger_than_the_kerf_inset_void_stays_outside():
    pieces = expand_piece_groups(
        [
            _corner_row("L-Shaped Corner"),
            {"piece_type": "Regular", "width_cm": 16, "length_cm": 6, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = _sheet_plan(pieces, [[(0, 0), (0, 20.4), (0, 40.8), (0, 61.2), (70, 70)]], board=100)
    improved = _apply(plan, pieces, board=100)
    guest = next(piece for sheet in improved["sheets"] for piece in sheet["pieces"] if piece["id"] == 5)

    assert not (12 < guest["x"] < 28 and 12 < guest["y"] < 28)
    assert not validate_plan(improved, pieces, 100, 100, kerf_cm=0.3)


def test_valid_nest_is_kept_when_the_rank_gets_worse(monkeypatch):
    pieces = expand_piece_groups([_corner_row("L-Shaped Corner")])
    plan = _sheet_plan(pieces, [[(40, 0), (40, 20.4), (40, 40.8), (40, 61.2)]])

    def _worse(candidate, *_args, **_kwargs):
        candidate["industrial_rank"] = (9, 9, 9)
        return candidate

    monkeypatch.setattr(
        "almdina_erp.almdina_erp.domain.cutting.optimizer.enrich_plan_metrics",
        _worse,
    )
    improved = _apply(plan, pieces)

    assert improved is not plan
    assert improved["industrial_rank"] == (9, 9, 9)
    assert {int(piece.get("corner_rotation_quarter_turns") or 0) for piece in improved["sheets"][0]["pieces"]} == {0, 1, 2, 3}


def test_adding_a_different_l_keeps_the_original_quad():
    four = expand_piece_groups([_corner_row("L-Shaped Corner")])
    first = optimize_plan(
        four,
        80,
        80,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
    )
    five = expand_piece_groups(
        [
            _corner_row("L-Shaped Corner"),
            _corner_row(
                "L-Shaped Corner",
                qty=1,
                width_cm=28,
                length_cm=16,
                clipped_corner_width_cm=6,
                clipped_corner_length_cm=5,
            ),
        ]
    )
    second = optimize_plan(
        five,
        80,
        80,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
    )

    # Formation stability belongs to candidate generation. Final selection may
    # prefer a different layout with a larger separable offcut.
    first = _apply(first, four, board=80)
    second = _apply(second, five, board=80)
    assert _shifted_rings(first, {1, 2, 3, 4}) == _shifted_rings(second, {1, 2, 3, 4})
    assert _turn_multiset(first, {1, 2, 3, 4}) == _turn_multiset(second, {1, 2, 3, 4})
    assert _turn_multiset(first, {1, 2, 3, 4}) == (0, 1, 2, 3)
    ids = [piece["id"] for sheet in second["sheets"] for piece in sheet["pieces"]]
    assert sorted(ids) == [1, 2, 3, 4, 5]
    assert len(ids) == len(set(ids))
    assert not validate_plan(second, five, 80, 80, kerf_cm=0.3)


def test_l_quad_dxf_roundtrip_keeps_outlines_and_turns(tmp_path):
    import ezdxf

    from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry

    pieces = expand_piece_groups([_corner_row("L-Shaped Corner")])
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
    placed = [piece for sheet in plan["sheets"] for piece in sheet["pieces"]]
    outlines = [material_outline_cm(piece) for piece in placed]
    assert _turn_multiset(plan, {1, 2, 3, 4}) == (0, 1, 2, 3)
    assert all(outline and len(outline) >= 6 for outline in outlines)

    document = ezdxf.new("R2010")
    for name in ("GEOMETRY", "CUT_PATH", "TEXT"):
        document.layers.add(name)
    modelspace = document.modelspace()
    for outline in outlines:
        ring = [(point[0] * 10, point[1] * 10) for point in outline]
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "GEOMETRY"}, close=True)
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "CUT_PATH"}, close=True)
    path = tmp_path / "l-quad.dxf"
    document.saveas(path)
    loaded = read_dxf_geometry(str(path), relevant_layers={"GEOMETRY", "CUT_PATH"})
    assert {"GEOMETRY", "CUT_PATH"} <= {segment["layer"] for segment in loaded["segments"]}
    rings = []
    geometry = [segment for segment in loaded["segments"] if segment["layer"] == "GEOMETRY"]
    for entity_id in sorted({segment["entity_id"] for segment in geometry}):
        segments = [segment for segment in geometry if segment["entity_id"] == entity_id]
        points = [segments[0]["start"]]
        points.extend(segment["end"] for segment in segments)
        if points[0] == points[-1]:
            points = points[:-1]
        rings.append(points)
    assert len(rings) == 4
    for outline, ring in zip(outlines, rings, strict=True):
        _same_points([(point[0] * 10, point[1] * 10) for point in outline], ring, tolerance=0.05)


def test_shape_candidate_pairs_two_rotatable_l_pieces_without_a_mirror():
    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=50, length_cm=50, qty=2, cut=20, allow_rotation=1),
            {"piece_type": "Regular", "width_cm": 12, "length_cm": 12, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = optimize_plan(
        pieces,
        122,
        244,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
    )
    plan = apply_shape_aware_nesting(
        plan, pieces, 122, 244, 0.3, mirroring_allowed=False,
        machine_type="CNC Router", time_limit_sec=2, **_REMNANT,
    )
    corners = _corners(plan)

    assert sorted(piece["id"] for sheet in plan["sheets"] for piece in sheet["pieces"]) == [1, 2, 3]
    assert len({piece["id"] for sheet in plan["sheets"] for piece in sheet["pieces"]}) == 3
    assert _symmetric_slot_pair(corners[0], corners[1], board=(122, 244))
    assert _recorded_facing(corners[0]) != _recorded_facing(corners[1])
    assert not any(piece.get("mirrored") or piece.get("corner_mirrored") for piece in corners)
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)
    assert not validate_plan(plan, pieces, 122, 244, kerf_cm=0.3)


def test_shape_candidate_pairs_two_l_pieces_by_reflection_without_rotation():
    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=50, length_cm=50, qty=2, cut=20, allow_rotation=0),
            {"piece_type": "Regular", "width_cm": 12, "length_cm": 12, "qty": 1, "allow_rotation": 0},
        ]
    )
    plan = optimize_plan(
        pieces,
        122,
        244,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=True,
    )
    plan = apply_shape_aware_nesting(
        plan, pieces, 122, 244, 0.3, mirroring_allowed=True,
        machine_type="CNC Router", time_limit_sec=2, **_REMNANT,
    )
    corners = _corners(plan)

    assert _symmetric_slot_pair(corners[0], corners[1], board=(122, 244))
    assert any(piece.get("mirrored") or piece.get("corner_mirrored") for piece in corners)
    assert not any(int(piece.get("corner_rotation_quarter_turns") or 0) for piece in corners)
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=True)
    assert not validate_plan(plan, pieces, 122, 244, kerf_cm=0.3)


def test_optimize_plan_splits_three_l_pieces_into_a_symmetric_pair_and_a_single():
    pieces = expand_piece_groups(
        [_plain_corner(width_cm=45, length_cm=45, qty=3, cut=15, allow_rotation=1)]
    )
    plan = optimize_plan(
        pieces,
        122,
        244,
        0.3,
        selected_mode="MaxRects Best Short Side",
        machine_type="CNC Router",
        time_limit_sec=2,
        mirroring_allowed=False,
    )
    corners = _corners(plan)
    pairs = [
        (left, right)
        for index, left in enumerate(corners)
        for right in corners[index + 1 :]
        if _symmetric_slot_pair(left, right, board=(122, 244))
    ]

    assert sorted(piece["id"] for piece in corners) == [1, 2, 3]
    assert len(corners) == len({piece["id"] for piece in corners})
    assert len(pairs) == 1
    paired = {pairs[0][0]["id"], pairs[0][1]["id"]}
    single = next(piece for piece in corners if piece["id"] not in paired)
    assert _inward_score(single, 122, 244) > 0.05
    assert len({_recorded_facing(piece) for piece in corners}) >= 2
    assert not any(piece.get("mirrored") for piece in corners)
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)
    assert not validate_plan(plan, pieces, 122, 244, kerf_cm=0.3)


def _plain_corner(*, width_cm, length_cm, qty, cut, allow_rotation):
    return {
        "piece_type": "L-Shaped Corner",
        "width_cm": width_cm,
        "length_cm": length_cm,
        "qty": qty,
        "clipped_corner_position": "Top Right",
        "clipped_corner_width_cm": cut,
        "clipped_corner_length_cm": cut,
        "allow_rotation": allow_rotation,
    }


def _corners(plan):
    return [
        piece
        for sheet in plan["sheets"]
        for piece in sheet["pieces"]
        if piece.get("piece_type") == "L-Shaped Corner"
    ]


def _symmetric_slot_pair(first, second, kerf=0.3, board=None):
    facings = frozenset((_recorded_facing(first), _recorded_facing(second)))
    edges = {
        frozenset({"Top Right", "Top Left"}),
        frozenset({"Bottom Right", "Bottom Left"}),
        frozenset({"Top Right", "Bottom Right"}),
        frozenset({"Top Left", "Bottom Left"}),
    }
    if facings not in edges:
        return False
    gap_x = max(first["x"], second["x"]) - min(first["x"] + first["w"], second["x"] + second["w"])
    gap_y = max(first["y"], second["y"]) - min(first["y"] + first["h"], second["y"] + second["h"])
    horizontal = abs(gap_x - kerf) <= 0.05 and -gap_y > min(first["h"], second["h"]) * 0.5
    vertical = abs(gap_y - kerf) <= 0.05 and -gap_x > min(first["w"], second["w"]) * 0.5
    if not horizontal and not vertical:
        return False
    if board is None:
        return True
    score = _pair_inward_score((first, second), board[0], board[1])
    return score is not None and score > 0


def _same_sheet_interlock(plan):
    for sheet in plan["sheets"]:
        pieces = list(sheet["pieces"])
        for index, left in enumerate(pieces):
            for right in pieces[index + 1 :]:
                if _boxes_interlock(left, right):
                    return True
    return False


def _boxes_interlock(first, second):
    overlap_x = min(first["x"] + first["w"], second["x"] + second["w"]) - max(first["x"], second["x"])
    overlap_y = min(first["y"] + first["h"], second["y"] + second["h"]) - max(first["y"], second["y"])
    notch = min(
        first.get("clipped_corner_width_cm") or 0,
        first.get("clipped_corner_length_cm") or 0,
        second.get("clipped_corner_width_cm") or 0,
        second.get("clipped_corner_length_cm") or 0,
    )
    return min(overlap_x, overlap_y) + 1e-6 >= notch * 0.5 > 0


def _shifted_rings(plan, ids):
    rings = []
    for sheet in plan["sheets"]:
        for piece in sheet["pieces"]:
            if piece["id"] not in ids:
                continue
            rings.append(material_outline_cm(piece))
    min_x = min(point[0] for ring in rings for point in ring)
    min_y = min(point[1] for ring in rings for point in ring)
    shifted = []
    for ring in rings:
        shifted.append(tuple(sorted((round(point[0] - min_x, 1), round(point[1] - min_y, 1)) for point in ring)))
    return tuple(sorted(shifted))


def _turn_multiset(plan, ids):
    turns = []
    for sheet in plan["sheets"]:
        for piece in sheet["pieces"]:
            if piece["id"] in ids:
                turns.append(int(piece.get("corner_rotation_quarter_turns") or 0))
    return tuple(sorted(turns))


def _quad_sheet(corners, board_w, board_h, kerf=0.3):
    step = corners[0]["width_cm"] + kerf
    seats = ((0, 0, 1), (step, 0, 2), (0, step, 0), (step, step, 3))
    placed = [
        _placed_corner(corner, x_cm=x_pos, y_cm=y_pos, mirrored=False, turns=turns)
        for corner, (x_pos, y_pos, turns) in zip(corners, seats, strict=True)
    ]
    return {"sheet_no": 1, "w": board_w, "h": board_h, "pieces": placed}


def _pull(sheets, pieces, board_w, board_h, kerf=0.3):
    _pull_loose_pieces(
        sheets,
        kerf,
        board_w,
        board_h,
        _spot_on_sheet,
        _sources_by_id(pieces),
    )


def _ids(sheets):
    return [int(piece["id"]) for sheet in sheets for piece in sheet["pieces"]]


def test_pull_loose_pieces_relocates_placed_glass_from_the_source_piece():
    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=20, length_cm=20, qty=4, cut=8, allow_rotation=1),
            {
                "piece_type": "Glass",
                "width_cm": 40,
                "length_cm": 30,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 50,
            },
        ]
    )
    corners = [piece for piece in pieces if piece["piece_type"] == "L-Shaped Corner"]
    glass = next(piece for piece in pieces if piece["piece_type"] == "Glass")
    placed_glass = make_placed_piece(glass, 0, 0, 40, 30, False)
    assert "width_cm" not in placed_glass
    assert "length_cm" not in placed_glass
    sheets = [
        _quad_sheet(corners, 120, 80),
        {"sheet_no": 2, "w": 120, "h": 80, "pieces": [placed_glass]},
    ]

    _pull(sheets, pieces, 120, 80)

    moved = [
        piece
        for piece in sheets[0]["pieces"]
        if piece["piece_type"] == "Glass"
    ]
    assert len(moved) == 1
    assert sheets[1]["pieces"] == []
    assert _ids(sheets).count(int(glass["id"])) == 1
    assert sorted(_ids(sheets)) == sorted(piece["id"] for piece in pieces)
    glass_piece = moved[0]
    assert glass_piece["original_w"] == 40
    assert glass_piece["original_h"] == 30
    assert glass_piece["w"] == 40
    assert glass_piece["h"] == 30
    assert glass_piece["glass_margin_mm"] == 50
    assert glass_piece["glass_hole_local_mm"] == [
        [50.0, 50.0],
        [350.0, 50.0],
        [350.0, 250.0],
        [50.0, 250.0],
    ]
    assert not validate_plan(
        {"sheets": sheets, "unplaced": []},
        pieces,
        120,
        80,
        kerf_cm=0.3,
    )


def test_pull_loose_pieces_keeps_allow_rotation_from_the_source_piece():
    def scenario(allow_rotation):
        pieces = expand_piece_groups(
            [
                _plain_corner(width_cm=20, length_cm=20, qty=1, cut=8, allow_rotation=1),
                {
                    "piece_type": "Regular",
                    "width_cm": 20,
                    "length_cm": 50,
                    "qty": 1,
                    "allow_rotation": 0,
                },
                {
                    "piece_type": "Regular",
                    "width_cm": 36,
                    "length_cm": 16,
                    "qty": 1,
                    "allow_rotation": allow_rotation,
                },
            ]
        )
        corner, filler, regular = pieces
        placed = make_placed_piece(regular, 0, 0, 36, 16, False)
        assert "allow_rotation" not in placed
        sheets = [
            {
                "sheet_no": 1,
                "w": 60,
                "h": 50,
                "pieces": [
                    _placed_corner(corner, x_cm=0, y_cm=0, mirrored=False, turns=1),
                    make_placed_piece(filler, 20.3, 0, 19.7, 50, False),
                ],
            },
            {"sheet_no": 2, "w": 60, "h": 50, "pieces": [placed]},
        ]
        _pull(sheets, pieces, 60, 50)
        found = [
            (sheet["sheet_no"], piece)
            for sheet in sheets
            for piece in sheet["pieces"]
            if int(piece["id"]) == int(regular["id"])
        ]
        assert len(found) == 1
        assert regular["allow_rotation"] == allow_rotation
        return found[0]

    sheet_no, rotated = scenario(1)
    assert sheet_no == 1
    assert rotated["rotated"] is True
    assert rotated["w"] == 16
    assert rotated["h"] == 36

    sheet_no, stayed = scenario(0)
    assert sheet_no == 2
    assert stayed["rotated"] is False
    assert stayed["w"] == 36
    assert stayed["h"] == 16


def _hosted_links(plan):
    links = []
    for sheet in plan["sheets"]:
        for piece in sheet["pieces"]:
            host = piece.get(GLASS_HOST_PIECE_ID)
            if host not in (None, ""):
                links.append((int(piece["id"]), int(host)))
    return tuple(sorted(links))


def _quad_turn_ids(plan, piece_type):
    grouped: dict[tuple, list] = {}
    for sheet in plan["sheets"]:
        for piece in sheet["pieces"]:
            if piece.get("piece_type") != piece_type:
                continue
            if piece.get(GLASS_HOST_PIECE_ID) not in (None, ""):
                continue
            key = (
                round(float(piece.get("original_w") or piece.get("w") or 0), 3),
                round(float(piece.get("original_h") or piece.get("h") or 0), 3),
            )
            grouped.setdefault(key, []).append(piece)
    return {
        key: tuple(sorted(int(piece.get("corner_rotation_quarter_turns") or 0) for piece in pieces))
        for key, pieces in grouped.items()
        if len(pieces) >= 4
    }


def test_shape_nesting_keeps_glass_guests_and_nests_free_corners():
    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=30, length_cm=30, qty=6, cut=10, allow_rotation=1),
            {
                "piece_type": "Clipped Corner",
                "width_cm": 24,
                "length_cm": 24,
                "qty": 4,
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 8,
                "clipped_corner_length_cm": 8,
                "allow_rotation": 1,
            },
            {
                "piece_type": "Glass",
                "width_cm": 80,
                "length_cm": 100,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 100,
            },
            {
                "piece_type": "Glass",
                "width_cm": 70,
                "length_cm": 90,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 80,
            },
        ]
    )
    hosted = pieces[:2]
    free_l = pieces[2:6]
    clipped = pieces[6:10]
    glass_a, glass_b = pieces[10], pieces[11]
    guest_a = make_placed_piece(hosted[0], 12, 12, 30, 30, False)
    guest_b = make_placed_piece(hosted[1], 91, 12, 30, 30, False)
    guest_a[GLASS_HOST_PIECE_ID] = glass_a["id"]
    guest_b[GLASS_HOST_PIECE_ID] = glass_b["id"]
    free = [
        make_placed_piece(piece, 0, index * 32, piece["width_cm"], piece["length_cm"], False)
        for index, piece in enumerate([*free_l, *clipped])
    ]
    plan = {
        "sheets": [
            {
                "sheet_no": 1,
                "w": 180,
                "h": 300,
                "pieces": [
                    make_placed_piece(glass_a, 0, 0, 80, 100, False),
                    guest_a,
                    make_placed_piece(glass_b, 81, 0, 70, 90, False),
                    guest_b,
                ],
            },
            {"sheet_no": 2, "w": 180, "h": 300, "pieces": free},
        ],
        "unplaced": [],
        "method_key": "MaxRects Best Short Side",
    }
    before = _hosted_links(plan)

    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        180,
        300,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )

    assert _hosted_links(improved) == before == ((1, 11), (2, 12))
    assert _quad_turn_ids(improved, "L-Shaped Corner")[(30.0, 30.0)] == (0, 1, 2, 3)
    assert _quad_turn_ids(improved, "Clipped Corner")[(24.0, 24.0)] == (0, 1, 2, 3)
    placed_ids = [piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert sorted(placed_ids) == list(range(1, 13))
    assert len(placed_ids) == len(set(placed_ids))
    assert not validate_plan(improved, pieces, 180, 300, kerf_cm=0.3)
    assert not placement_permission_errors(improved, pieces, mirroring_allowed=False)


def test_one_failing_corner_group_does_not_cancel_the_other(monkeypatch):
    import almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting as shape_nesting

    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=30, length_cm=30, qty=4, cut=10, allow_rotation=1),
            _plain_corner(width_cm=20, length_cm=20, qty=4, cut=6, allow_rotation=1),
        ]
    )
    plan = _sheet_plan(
        pieces,
        [[(0, 0), (31, 0), (0, 31), (31, 31)], [(0, 0), (21, 0), (0, 21), (21, 21)]],
        board=120,
    )
    real_compose = shape_nesting._compose_plan
    real_fallback = shape_nesting._fallback_plan

    def _contains_second_group(blocks) -> bool:
        return any(int(piece["id"]) >= 5 for block in blocks for piece in block["pieces"])

    def compose(plan, pieces, blocks, *args, **kwargs):
        if _contains_second_group(blocks):
            return None
        return real_compose(plan, pieces, blocks, *args, **kwargs)

    def fallback(plan, pieces, blocks, *args, **kwargs):
        if _contains_second_group(blocks):
            return None
        return real_fallback(plan, pieces, blocks, *args, **kwargs)

    monkeypatch.setattr(shape_nesting, "_compose_plan", compose)
    monkeypatch.setattr(shape_nesting, "_fallback_plan", fallback)

    improved = _apply(plan, pieces, board=120, mirroring_allowed=True)

    assert _turn_multiset(improved, {1, 2, 3, 4}) == (0, 1, 2, 3)
    assert "corner_rotation_quarter_turns" not in {
        key
        for sheet in improved["sheets"]
        for piece in sheet["pieces"]
        if int(piece["id"]) >= 5
        for key in piece
    }
    assert sorted(piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]) == list(range(1, 9))
    assert not validate_plan(improved, pieces, 120, 120, kerf_cm=0.3)


def test_forbidden_pair_does_not_cancel_the_other_quads():
    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=30, length_cm=30, qty=4, cut=10, allow_rotation=1),
            {
                "piece_type": "Clipped Corner",
                "width_cm": 24,
                "length_cm": 24,
                "qty": 4,
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 8,
                "clipped_corner_length_cm": 8,
                "allow_rotation": 1,
            },
            _plain_corner(width_cm=18, length_cm=18, qty=2, cut=6, allow_rotation=0),
        ]
    )
    plan = _sheet_plan(
        pieces,
        [
            [(0, 0), (31, 0), (0, 31), (31, 31)],
            [(0, 0), (25, 0), (0, 25), (25, 25)],
            [(0, 0), (19, 0)],
        ],
        board=140,
    )

    improved = _apply(plan, pieces, board=140, mirroring_allowed=False)

    assert _turn_multiset(improved, {1, 2, 3, 4}) == (0, 1, 2, 3)
    assert _turn_multiset(improved, {5, 6, 7, 8}) == (0, 1, 2, 3)
    assert _turn_multiset(improved, {9, 10}) == (0, 0)
    placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"] if int(piece["id"]) in {9, 10}]
    assert not _symmetric_slot_pair(placed[0], placed[1], board=(140, 140))
    assert sorted(piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]) == list(range(1, 11))
    assert not validate_plan(improved, pieces, 140, 140, kerf_cm=0.3)


def test_shape_nesting_preserves_single_many_and_nested_glass_links():
    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=20, length_cm=20, qty=4, cut=6, allow_rotation=1),
            {
                "piece_type": "Glass",
                "width_cm": 80,
                "length_cm": 80,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 60,
            },
            {
                "piece_type": "Glass",
                "width_cm": 40,
                "length_cm": 40,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 40,
            },
            {"piece_type": "Regular", "width_cm": 10, "length_cm": 10, "qty": 2, "allow_rotation": 0},
        ]
    )
    corners = pieces[:4]
    outer, inner = pieces[4], pieces[5]
    guests = pieces[6:]
    placed_inner = make_placed_piece(inner, 12, 12, 40, 40, False)
    placed_inner[GLASS_HOST_PIECE_ID] = outer["id"]
    first = make_placed_piece(guests[0], 17, 17, 10, 10, False)
    second = make_placed_piece(guests[1], 17, 29, 10, 10, False)
    first[GLASS_HOST_PIECE_ID] = inner["id"]
    second[GLASS_HOST_PIECE_ID] = inner["id"]
    plan = {
        "sheets": [
            {
                "sheet_no": 1,
                "w": 140,
                "h": 140,
                "pieces": [
                    make_placed_piece(outer, 0, 0, 80, 80, False),
                    placed_inner,
                    first,
                    second,
                ],
            },
            {
                "sheet_no": 2,
                "w": 140,
                "h": 140,
                "pieces": [
                    make_placed_piece(piece, 0, index * 22, 20, 20, False)
                    for index, piece in enumerate(corners)
                ],
            },
        ],
        "unplaced": [],
        "method_key": "MaxRects Best Short Side",
    }
    before = _hosted_links(plan)

    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        140,
        140,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )

    assert _hosted_links(improved) == before == ((6, 5), (7, 6), (8, 6))
    assert _turn_multiset(improved, {1, 2, 3, 4}) == (0, 1, 2, 3)
    holes = {
        int(piece["id"]): piece.get("glass_hole_local_mm")
        for sheet in improved["sheets"]
        for piece in sheet["pieces"]
        if piece.get("piece_type") == "Glass"
    }
    assert holes[5] and holes[6]
    assert sorted(piece["id"] for sheet in improved["sheets"] for piece in sheet["pieces"]) == list(range(1, 9))
    assert not validate_plan(improved, pieces, 140, 140, kerf_cm=0.3)


def test_combined_glass_corner_and_special_dxf_roundtrip(tmp_path):
    import json

    import ezdxf

    from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry

    special = {
        "version": 1,
        "kind": "polygon",
        "units": "cm",
        "exact": True,
        "blank_width_cm": 20,
        "blank_length_cm": 16,
        "points": [[0, 5], [14, 0], [20, 11], [6, 16]],
    }
    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=20, length_cm=20, qty=4, cut=6, allow_rotation=1),
            {
                "piece_type": "Clipped Corner",
                "width_cm": 18,
                "length_cm": 18,
                "qty": 4,
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 6,
                "clipped_corner_length_cm": 6,
                "allow_rotation": 1,
            },
            {
                "piece_type": "Glass",
                "width_cm": 50,
                "length_cm": 40,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 40,
            },
            {"piece_type": "Regular", "width_cm": 12, "length_cm": 10, "qty": 1, "allow_rotation": 0},
            {
                "piece_type": "Special",
                "width_cm": 20,
                "length_cm": 16,
                "qty": 1,
                "allow_rotation": 0,
                "special_shape_geometry_json": json.dumps(special),
            },
        ]
    )
    corners = pieces[:4]
    clipped = pieces[4:8]
    glass, regular, shaped = pieces[8], pieces[9], pieces[10]
    guest = make_placed_piece(regular, 6, 6, 12, 10, False)
    guest[GLASS_HOST_PIECE_ID] = glass["id"]
    plan = {
        "sheets": [
            {
                "sheet_no": 1,
                "w": 160,
                "h": 160,
                "pieces": [make_placed_piece(glass, 0, 0, 50, 40, False), guest],
            },
            {
                "sheet_no": 2,
                "w": 160,
                "h": 160,
                "pieces": [
                    make_placed_piece(piece, 0, index * 22, 20, 20, False)
                    for index, piece in enumerate(corners)
                ],
            },
            {
                "sheet_no": 3,
                "w": 160,
                "h": 160,
                "pieces": [
                    make_placed_piece(piece, 0, index * 20, 18, 18, False)
                    for index, piece in enumerate(clipped)
                ]
                + [make_placed_piece(shaped, 40, 0, 20, 16, False)],
            },
        ],
        "unplaced": [],
        "method_key": "MaxRects Best Short Side",
    }

    improved = apply_shape_aware_nesting(
        plan,
        pieces,
        160,
        160,
        0.3,
        mirroring_allowed=False,
        machine_type="CNC Router",
        time_limit_sec=2,
        **_REMNANT,
    )

    assert _hosted_links(improved) == ((10, 9),)
    assert _turn_multiset(improved, {1, 2, 3, 4}) == (0, 1, 2, 3)
    assert _turn_multiset(improved, {5, 6, 7, 8}) == (0, 1, 2, 3)
    placed = [piece for sheet in improved["sheets"] for piece in sheet["pieces"]]
    assert sorted(piece["id"] for piece in placed) == list(range(1, 12))
    outlines = [material_outline_cm(piece) for piece in placed]
    assert all(outline and len(outline) >= 4 for outline in outlines)
    special_outline = material_outline_cm(next(piece for piece in placed if piece["piece_type"] == "Special"))
    assert special_outline is not None and len(special_outline) == 4
    glass_piece = next(piece for piece in placed if piece["piece_type"] == "Glass")
    hole = glass_piece.get("glass_hole_local_mm")
    assert hole
    hole_ring = [
        (glass_piece["x"] + point[0] / 10, glass_piece["y"] + point[1] / 10) for point in hole
    ]

    document = ezdxf.new("R2010")
    for name in ("GEOMETRY", "CUT_PATH", "TEXT"):
        document.layers.add(name)
    modelspace = document.modelspace()
    exported = [*outlines, hole_ring]
    for outline in exported:
        ring = [(point[0] * 10, point[1] * 10) for point in outline]
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "GEOMETRY"}, close=True)
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "CUT_PATH"}, close=True)
    path = tmp_path / "combined-nest.dxf"
    document.saveas(path)
    loaded = read_dxf_geometry(str(path), relevant_layers={"GEOMETRY", "CUT_PATH"})
    geometry = [segment for segment in loaded["segments"] if segment["layer"] == "GEOMETRY"]
    cut_path = [segment for segment in loaded["segments"] if segment["layer"] == "CUT_PATH"]
    assert len({segment["entity_id"] for segment in geometry}) == len(exported)
    assert len({segment["entity_id"] for segment in cut_path}) == len(exported)
    rings = []
    for entity_id in sorted({segment["entity_id"] for segment in geometry}):
        segments = [segment for segment in geometry if segment["entity_id"] == entity_id]
        points = [segments[0]["start"]]
        points.extend(segment["end"] for segment in segments)
        if points[0] == points[-1]:
            points = points[:-1]
        rings.append(points)
    for outline, ring in zip(exported, rings, strict=True):
        _same_points([(point[0] * 10, point[1] * 10) for point in outline], ring, tolerance=0.05)
    assert not validate_plan(improved, pieces, 160, 160, kerf_cm=0.3)


def test_pull_loose_pieces_does_not_separate_a_glass_host_from_its_guests():
    pieces = expand_piece_groups(
        [
            _plain_corner(width_cm=20, length_cm=20, qty=4, cut=8, allow_rotation=1),
            {
                "piece_type": "Glass",
                "width_cm": 50,
                "length_cm": 40,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": 40,
            },
            {
                "piece_type": "Regular",
                "width_cm": 10,
                "length_cm": 10,
                "qty": 1,
                "allow_rotation": 0,
            },
        ]
    )
    corners = [piece for piece in pieces if piece["piece_type"] == "L-Shaped Corner"]
    glass = next(piece for piece in pieces if piece["piece_type"] == "Glass")
    guest = next(piece for piece in pieces if piece["piece_type"] == "Regular")
    placed_glass = make_placed_piece(glass, 0, 0, 50, 40, False)
    placed_guest = make_placed_piece(guest, 5, 5, 10, 10, False)
    placed_guest[GLASS_HOST_PIECE_ID] = glass["id"]
    sheets = [
        _quad_sheet(corners, 120, 90),
        {"sheet_no": 2, "w": 120, "h": 90, "pieces": [placed_glass, placed_guest]},
    ]

    _pull(sheets, pieces, 120, 90)

    second = sheets[1]["pieces"]
    assert {int(piece["id"]) for piece in second} == {int(glass["id"]), int(guest["id"])}
    hosted = next(piece for piece in second if int(piece["id"]) == int(guest["id"]))
    assert int(hosted[GLASS_HOST_PIECE_ID]) == int(glass["id"])
    assert all(piece["piece_type"] != "Glass" for piece in sheets[0]["pieces"])
    assert sorted(_ids(sheets)) == sorted(piece["id"] for piece in pieces)
