import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    ContourCandidate,
    DxfTopologyError,
    ExpectedPieceEvidence,
    PartGeometry,
    PlacedPartGeometry,
    resolve_contour_ownership,
    validate_material_layout,
)


def _rect(x1: float, y1: float, x2: float, y2: float):
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def _candidate(key: int, x1: float, y1: float, x2: float, y2: float):
    return ContourCandidate(key=key, polygon=_rect(x1, y1, x2, y2))


def _expected(
    width: float,
    height: float,
    *,
    rotate: bool = False,
    arbitrary: bool = False,
):
    return ExpectedPieceEvidence(
        width=width,
        height=height,
        allow_rotation=rotate,
        arbitrary_outline=arbitrary,
    )


def _concave_shape(
    key: int,
    x: float,
    y: float,
    *,
    width: float,
    height: float,
):
    arm = min(width, height) / 3
    return ContourCandidate(
        key=key,
        polygon=(
            (x, y),
            (x + width, y),
            (x + width, y + arm),
            (x + arm, y + arm),
            (x + arm, y + height),
            (x, y + height),
        ),
    )


def test_canonical_twelve_piece_plan_ignores_glass_opening_as_phantom_piece():
    # 9 ordinary pieces + one glass-door panel + 2 pieces nested inside the
    # panel opening = 12 actual order pieces. The opening is the 13th contour.
    contours = [
        _candidate(1, 0, 0, 900, 2100),
        _candidate(2, 150, 300, 750, 1800),  # internal glass opening
        _candidate(3, 220, 450, 420, 650),
        _candidate(4, 480, 450, 680, 650),
    ]
    expected = [
        _expected(900, 2100),
        _expected(200, 200),
        _expected(200, 200),
    ]
    for index in range(9):
        x = 1100 + (index * 150)
        contours.append(_candidate(5 + index, x, 0, x + 100, 100))
        expected.append(_expected(100, 100))

    topology = resolve_contour_ownership(
        contours,
        expected,
        dimension_tolerance=0.2,
        geometry_tolerance=0.01,
    )

    assert len(topology.parts) == 12
    assert len(topology.actual_contour_keys) == 12
    assert topology.hole_contour_keys == (2,)
    owner = next(part for part in topology.parts if part.contour_key == 1)
    assert owner.hole_contour_keys == (2,)

    validate_material_layout(
        [PlacedPartGeometry(key=part.contour_key, geometry=part.geometry) for part in topology.parts],
        required_clearance=3.0,
        geometry_tolerance=0.01,
        numeric_tolerance=0.0,
    )


def test_piece_inside_hole_is_valid_when_material_and_kerf_clearance_are_valid():
    owner = PartGeometry(
        outer=_rect(0, 0, 100, 100),
        holes=(_rect(20, 20, 80, 80),),
    )
    nested = PartGeometry(outer=_rect(30, 30, 50, 50))

    validate_material_layout(
        [
            PlacedPartGeometry(key="owner", geometry=owner),
            PlacedPartGeometry(key="nested", geometry=nested),
        ],
        required_clearance=3.0,
        geometry_tolerance=0.01,
    )


def test_material_overlap_is_rejected_when_nested_piece_crosses_hole_boundary():
    owner = PartGeometry(
        outer=_rect(0, 0, 100, 100),
        holes=(_rect(20, 20, 80, 80),),
    )
    crossing = PartGeometry(outer=_rect(70, 30, 90, 50))

    with pytest.raises(DxfTopologyError) as exc_info:
        validate_material_layout(
            [
                PlacedPartGeometry(key="owner", geometry=owner),
                PlacedPartGeometry(key="crossing", geometry=crossing),
            ],
            required_clearance=0.0,
            geometry_tolerance=0.01,
        )

    assert exc_info.value.code == "MATERIAL_FOOTPRINT_OVERLAP"


def test_piece_inside_hole_is_rejected_when_hole_clearance_is_below_kerf():
    owner = PartGeometry(
        outer=_rect(0, 0, 100, 100),
        holes=(_rect(20, 20, 80, 80),),
    )
    too_close = PartGeometry(outer=_rect(21, 30, 40, 50))

    with pytest.raises(DxfTopologyError) as exc_info:
        validate_material_layout(
            [
                PlacedPartGeometry(key="owner", geometry=owner),
                PlacedPartGeometry(key="nested", geometry=too_close),
            ],
            required_clearance=3.0,
            geometry_tolerance=0.01,
        )

    assert exc_info.value.code == "HOLE_CLEARANCE_VIOLATION"


def test_unowned_extra_contour_fails_closed_instead_of_becoming_phantom_hole():
    contours = [
        _candidate(1, 0, 0, 100, 100),
        _candidate(2, 200, 0, 220, 20),
    ]

    with pytest.raises(DxfTopologyError) as exc_info:
        resolve_contour_ownership(
            contours,
            [_expected(100, 100)],
            dimension_tolerance=0.2,
            geometry_tolerance=0.01,
        )

    assert exc_info.value.code == "UNRESOLVED_CONTOUR_OWNERSHIP"


def test_piece_like_extra_contour_fails_closed_as_ambiguous():
    contours = [
        _candidate(1, 0, 0, 100, 100),
        _candidate(2, 20, 20, 40, 40),  # could be a 20x20 hole or a real piece
        _candidate(3, 150, 0, 170, 20),
    ]

    with pytest.raises(DxfTopologyError) as exc_info:
        resolve_contour_ownership(
            contours,
            [_expected(100, 100), _expected(20, 20)],
            dimension_tolerance=0.2,
            geometry_tolerance=0.01,
        )

    assert exc_info.value.code == "AMBIGUOUS_CONTOUR_OWNERSHIP"


def test_special_outer_accepts_concave_shape_with_exact_manufacturing_bbox():
    contours = [
        _candidate(1, 0, 0, 100, 100),
        _candidate(2, 20, 20, 70, 70),  # ordinary internal opening
        _concave_shape(3, 150, 0, width=80, height=120),
    ]

    topology = resolve_contour_ownership(
        contours,
        [_expected(100, 100), _expected(80, 120, arbitrary=True)],
        dimension_tolerance=0.2,
        geometry_tolerance=0.01,
    )

    assert topology.actual_contour_keys == (1, 3)
    assert topology.hole_contour_keys == (2,)
    assert [part.expected_piece_index for part in topology.parts] == [0, 1]


def test_special_outer_rejects_wrong_manufacturing_bbox_even_when_shape_is_valid():
    with pytest.raises(DxfTopologyError) as exc_info:
        resolve_contour_ownership(
            [_concave_shape(1, 0, 0, width=60, height=60)],
            [_expected(120, 200, arbitrary=True)],
            dimension_tolerance=0.2,
            geometry_tolerance=0.01,
        )

    assert exc_info.value.code == "EXPECTED_PIECE_MISMATCH"


def test_special_outer_allows_rotated_manufacturing_bbox_only_when_enabled():
    contour = _concave_shape(1, 0, 0, width=200, height=120)

    topology = resolve_contour_ownership(
        [contour],
        [_expected(120, 200, rotate=True, arbitrary=True)],
        dimension_tolerance=0.2,
        geometry_tolerance=0.01,
    )
    assert topology.parts[0].expected_piece_index == 0

    with pytest.raises(DxfTopologyError) as exc_info:
        resolve_contour_ownership(
            [contour],
            [_expected(120, 200, rotate=False, arbitrary=True)],
            dimension_tolerance=0.2,
            geometry_tolerance=0.01,
        )

    assert exc_info.value.code == "EXPECTED_PIECE_MISMATCH"


def test_many_internal_openings_resolve_without_subset_search():
    contours = []
    expected = []
    for index in range(12):
        x = index * 150
        owner_key = (index * 2) + 1
        hole_key = owner_key + 1
        contours.append(_candidate(owner_key, x, 0, x + 100, 100))
        contours.append(_candidate(hole_key, x + 30, 30, x + 70, 70))
        expected.append(_expected(100, 100))

    topology = resolve_contour_ownership(
        contours,
        expected,
        dimension_tolerance=0.2,
        geometry_tolerance=0.01,
    )

    assert len(topology.parts) == 12
    assert len(topology.hole_contour_keys) == 12
    assert all(len(part.geometry.holes) == 1 for part in topology.parts)


def test_legacy_no_hole_topology_keeps_original_contour_order():
    contours = [
        _candidate(1, 200, 0, 300, 200),
        _candidate(2, 0, 0, 100, 200),
    ]
    topology = resolve_contour_ownership(
        contours,
        [_expected(100, 200), _expected(100, 200)],
        dimension_tolerance=0.2,
        geometry_tolerance=0.01,
    )

    assert topology.actual_contour_keys == (1, 2)
    assert topology.hole_contour_keys == ()
    assert all(part.geometry.holes == () for part in topology.parts)