from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    parse_geometry_mm,
    serialize_geometry_mm,
    validate_snapshot_material_layout,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry


def _contract(outer, holes=()):
    return serialize_geometry_mm(
        PartGeometry(
            outer=tuple(tuple(point) for point in outer),
            holes=tuple(tuple(tuple(point) for point in hole) for hole in holes),
        )
    )


def test_parse_geometry_rejects_self_intersecting_outer():
    bow_tie = _contract(
        ((0, 0), (100, 100), (0, 100), (100, 0)),
    )

    with pytest.raises(DxfGeometrySnapshotError, match="self_intersection"):
        parse_geometry_mm(bow_tie)


def test_parse_geometry_rejects_zero_area_outer():
    zero_area = _contract(
        ((0, 0), (50, 0), (100, 0)),
    )

    with pytest.raises(DxfGeometrySnapshotError, match="zero_area"):
        parse_geometry_mm(zero_area)


def test_single_piece_snapshot_rejects_hole_outside_outer():
    invalid_geometry = _contract(
        ((0, 0), (100, 0), (100, 100), (0, 100)),
        (((80, 20), (120, 20), (120, 60), (80, 60)),),
    )
    snapshot = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "geometry": invalid_geometry,
                    }
                ],
            }
        ]
    }

    with pytest.raises(DxfGeometrySnapshotError, match="strictly inside"):
        validate_snapshot_material_layout(snapshot, required_clearance_mm=5.0)


def test_snapshot_sanitizer_rejects_overlapping_holes():
    invalid_geometry = _contract(
        ((0, 0), (200, 0), (200, 200), (0, 200)),
        (
            ((20, 20), (100, 20), (100, 100), (20, 100)),
            ((80, 80), (160, 80), (160, 160), (80, 160)),
        ),
    )
    snapshot = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "geometry": invalid_geometry,
                    }
                ],
            }
        ]
    }

    with pytest.raises(DxfGeometrySnapshotError, match="overlap"):
        sanitize_plan_snapshot(snapshot)
