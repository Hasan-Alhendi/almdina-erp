from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    assemble_contours,
    has_self_intersection,
    polygon_distance,
    polygon_inside_rect,
    polygons_overlap,
    validate_polygon,
)


def _segments(points):
    return list(zip(points, points[1:]))


def test_closed_contour_is_assembled_without_mutating_geometry():
    square = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0), (0.0, 0.0)]
    contours = assemble_contours(_segments(square), tolerance=0.25)
    assert len(contours) == 1
    assert contours[0]["closed"] is True
    assert contours[0]["branched"] is False


def test_open_contour_is_reported_as_open():
    contours = assemble_contours(
        [((0.0, 0.0), (100.0, 0.0)), ((100.0, 0.0), (100.0, 50.0))],
        tolerance=0.25,
    )
    assert len(contours) == 1
    assert contours[0]["closed"] is False


def test_self_intersection_is_rejected_by_polygon_validation():
    bow_tie = [(0.0, 0.0), (100.0, 100.0), (0.0, 100.0), (100.0, 0.0)]
    assert has_self_intersection(bow_tie)
    assert "self_intersection" in validate_polygon(bow_tie, tolerance=0.25)


def test_overlap_and_kerf_distance_are_geometry_aware():
    first = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    overlapping = [(90.0, 0.0), (190.0, 0.0), (190.0, 100.0), (90.0, 100.0)]
    near = [(103.0, 0.0), (203.0, 0.0), (203.0, 100.0), (103.0, 100.0)]
    assert polygons_overlap(first, overlapping)
    assert not polygons_overlap(first, near)
    assert abs(polygon_distance(first, near) - 3.0) < 1e-6


def test_polygon_inside_rect_checks_the_full_contour_not_only_its_center():
    outside = [(-1.0, 10.0), (50.0, 10.0), (50.0, 50.0), (-1.0, 50.0)]
    assert not polygon_inside_rect(
        outside,
        min_x=0,
        min_y=0,
        max_x=100,
        max_y=100,
        tolerance=0.01,
    )
