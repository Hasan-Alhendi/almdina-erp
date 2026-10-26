"""Shape nesting, glass acceptance, small-piece safety, and board cancellation."""

from __future__ import annotations

from almdina_erp.almdina_erp.domain.cutting import (
    expand_piece_groups,
    optimize_plan,
    validate_plan,
)
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.plan_search import improve_plan_search
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import (
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
