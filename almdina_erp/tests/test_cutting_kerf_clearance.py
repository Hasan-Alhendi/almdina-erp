from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.primitives import (
    expand_piece_groups,
    rects_have_clearance,
)
from almdina_erp.almdina_erp.domain.cutting.registry import run_single_method
from almdina_erp.almdina_erp.domain.cutting.strategies.maxrects import pack_maxrects


def _pieces():
    return [
        {
            "id": 1,
            "label": "1.1",
            "width_cm": 40,
            "length_cm": 40,
            "allow_rotation": 0,
        },
        {
            "id": 2,
            "label": "1.2",
            "width_cm": 40,
            "length_cm": 40,
            "allow_rotation": 0,
        },
    ]


def _plan(second_x: float):
    pieces = _pieces()
    return {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {**pieces[0], "x": 0, "y": 0, "w": 40, "h": 40, "rotated": False},
                    {**pieces[1], "x": second_x, "y": 0, "w": 40, "h": 40, "rotated": False},
                ],
            }
        ],
        "unplaced": [],
    }


def _packing_pieces(dimensions):
    return [
        {
            "id": index,
            "label": f"{index}.1",
            "source_piece_no": index,
            "copy_no": 1,
            "group_qty": 1,
            "width_cm": width,
            "length_cm": length,
            "allow_rotation": 0,
        }
        for index, (width, length) in enumerate(dimensions, start=1)
    ]


def test_clearance_rule_requires_one_kerf_gap_not_double_kerf():
    first = {"x": 0.0, "y": 0.0, "w": 40.0, "h": 40.0}
    exact_kerf = {"x": 40.3, "y": 0.0, "w": 40.0, "h": 40.0}
    short_gap = {"x": 40.2, "y": 0.0, "w": 40.0, "h": 40.0}

    assert rects_have_clearance(first, exact_kerf, 0.3)
    assert not rects_have_clearance(first, short_gap, 0.3)


def test_validator_rejects_non_overlapping_paths_that_lose_saw_kerf():
    errors = validate_plan(_plan(40.2), _pieces(), 100, 100, kerf_cm=0.3)

    assert not any("overlap" in error.lower() for error in errors)
    assert any("kerf clearance" in error.lower() for error in errors)


def test_validator_accepts_exact_required_saw_kerf():
    errors = validate_plan(_plan(40.3), _pieces(), 100, 100, kerf_cm=0.3)

    assert errors == []


def test_maxrects_never_accepts_sub_kerf_candidate_from_overlapping_free_rects():
    # This exact sequence reproduced the old MaxRects bug: overlapping free
    # rectangles allowed the last piece to be placed against/inside an existing
    # piece even though the requested Kerf was 5 mm.
    pieces = _packing_pieces(
        [(40, 13), (44, 34), (28, 22), (39, 29), (55, 69), (17, 11), (11, 18)]
    )
    plan = pack_maxrects(pieces, 100, 100, 0.5, "best_short_side")

    for sheet in plan["sheets"]:
        placed = sheet["pieces"]
        for index, first in enumerate(placed):
            for second in placed[index + 1 :]:
                assert rects_have_clearance(first, second, 0.5), (
                    first["label"],
                    second["label"],
                )

    assert validate_plan(plan, pieces, 100, 100, kerf_cm=0.5) == []


def _door_rows():
    return [
        {"width_cm": 40, "length_cm": 70, "qty": 3, "allow_rotation": 1, "piece_no": 1},
        {"width_cm": 55, "length_cm": 90, "qty": 2, "allow_rotation": 1, "piece_no": 2},
        {"width_cm": 28, "length_cm": 40, "qty": 4, "allow_rotation": 1, "piece_no": 3},
    ]


def _arrangement(plan):
    return [
        tuple(sorted((piece["label"], bool(piece["rotated"])) for piece in sheet["pieces"]))
        for sheet in plan["sheets"]
    ]


def _minimum_axis_gap(plan):
    best = None
    for sheet in plan["sheets"]:
        placed = sheet["pieces"]
        for index, first in enumerate(placed):
            for second in placed[index + 1 :]:
                horizontal = max(
                    0.0,
                    max(first["x"], second["x"])
                    - min(first["x"] + first["w"], second["x"] + second["w"]),
                )
                vertical = max(
                    0.0,
                    max(first["y"], second["y"])
                    - min(first["y"] + first["h"], second["y"] + second["h"]),
                )
                overlaps_y = vertical <= 1e-6 and horizontal > 1e-6
                overlaps_x = horizontal <= 1e-6 and vertical > 1e-6
                gap = horizontal if overlaps_y else vertical if overlaps_x else None
                if gap is None:
                    continue
                best = gap if best is None else min(best, gap)
    return best


def test_larger_kerf_keeps_door_arrangement_and_widens_the_saw_gap():
    pieces = expand_piece_groups(_door_rows())
    narrow = run_single_method(pieces, 122, 244, 0.3, "MaxRects Best Short Side")
    wide = run_single_method(pieces, 122, 244, 0.8, "MaxRects Best Short Side")

    assert _arrangement(narrow) == _arrangement(wide)
    assert abs(_minimum_axis_gap(narrow) - 0.3) < 1e-6
    assert abs(_minimum_axis_gap(wide) - 0.8) < 1e-6
    assert validate_plan(narrow, pieces, 122, 244, kerf_cm=0.3) == []
    assert validate_plan(wide, pieces, 122, 244, kerf_cm=0.8) == []


def test_kerf_that_no_longer_fits_the_stable_arrangement_still_validates():
    pieces = expand_piece_groups(_door_rows())
    plan = run_single_method(pieces, 122, 244, 8.0, "MaxRects Best Short Side")

    assert not plan["unplaced"]
    assert validate_plan(plan, pieces, 122, 244, kerf_cm=8.0) == []
