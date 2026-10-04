from __future__ import annotations

from almdina_erp.almdina_erp.domain.cutting.dxf_default_layer import (
    classify_default_layer_polygons,
    is_overlay_framing_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.extra_overlays import ExtraOverlayCandidate


def _rect(x1: float, y1: float, x2: float, y2: float):
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def test_classify_uses_board_sized_rect_as_sheet_and_keeps_door():
    sheet = _rect(0, 0, 1220, 2440)
    door = _rect(100, 100, 500, 700)

    sheets, cuts = classify_default_layer_polygons(
        [sheet, door],
        expected_width_mm=1220,
        expected_height_mm=2440,
        geometry_tolerance=0.25,
    )

    assert sheets == (sheet,)
    assert cuts == (door,)


def test_classify_drops_layer0_boxes_that_only_frame_extra_overlays():
    door = _rect(100, 100, 500, 700)
    liner_box = _rect(480, 80, 510, 720)
    handle_box = _rect(220, 280, 300, 480)
    overlays = (
        ExtraOverlayCandidate(
            key=1,
            kind="liner",
            layer="Liner",
            path=((485, 120), (485, 680), (500, 680), (500, 120)),
        ),
        ExtraOverlayCandidate(
            key=2,
            kind="recessed_handle_cutout",
            layer="Handle Recess",
            path=((230, 300), (290, 300), (290, 460), (230, 460)),
        ),
    )

    assert is_overlay_framing_polygon(
        liner_box,
        larger_hosts=(door, liner_box, handle_box),
        overlays=overlays,
        tolerance=0.25,
    )
    sheets, cuts = classify_default_layer_polygons(
        [_rect(0, 0, 1220, 2440), door, liner_box, handle_box],
        expected_width_mm=1220,
        expected_height_mm=2440,
        overlays=overlays,
        geometry_tolerance=0.25,
    )

    assert len(sheets) == 1
    assert cuts == (door,)


def test_layer0_is_cut_path_when_sheets_are_already_known():
    sheet_sized_door = _rect(0, 0, 1220, 2440)
    door = _rect(100, 100, 500, 700)

    sheets, cuts = classify_default_layer_polygons(
        [sheet_sized_door, door],
        expected_width_mm=1220,
        expected_height_mm=2440,
        geometry_tolerance=0.25,
        infer_sheets=False,
    )

    assert sheets == ()
    assert set(cuts) == {sheet_sized_door, door}


def test_layer0_board_dimensions_use_canonical_exact_equality():
    exact_sheet = _rect(0, 0, 1220, 2440)
    one_mm_short = _rect(2000, 0, 3219, 2440)
    fractional_short = _rect(4000, 0, 5219.9, 2440)
    swapped = _rect(6000, 0, 8440, 1220)

    sheets, cuts = classify_default_layer_polygons(
        [exact_sheet, one_mm_short, fractional_short, swapped],
        expected_width_mm=1220,
        expected_height_mm=2440,
        geometry_tolerance=0.25,
    )

    assert sheets == (exact_sheet,)
    assert set(cuts) == {one_mm_short, fractional_short, swapped}


def test_layer0_board_dimensions_normalize_float_representation_only():
    expected_width = 1220.1
    actual_sheet = _rect(0, 0, 1220.1000000000001, 2440.0)

    sheets, cuts = classify_default_layer_polygons(
        [actual_sheet],
        expected_width_mm=expected_width,
        expected_height_mm=2440.0,
        geometry_tolerance=0.25,
    )

    assert sheets == (actual_sheet,)
    assert cuts == ()
