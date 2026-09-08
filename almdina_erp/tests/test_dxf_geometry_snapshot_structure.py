from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    canonicalize_snapshot_geometries,
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

    with pytest.raises(DxfGeometrySnapshotError, match="too_few_vertices|zero_area"):
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


def test_canonicalize_keeps_extra_overlays_off_the_hole_contract():
    snapshot = canonicalize_snapshot_geometries(
        {
            "sheets": [
                {
                    "sheet_no": 1,
                    "pieces": [
                        {
                            "id": 1,
                            "label": "1.1",
                            "piece_type": "Extra",
                            "geometry": _contract(((0, 0), (400, 0), (400, 600), (0, 600))),
                            "overlays": [
                                {
                                    "kind": "liner",
                                    "layer": " liner ",
                                    "geometry": {
                                        "schema_version": 1,
                                        "unit": "mm",
                                        "coordinate_space": "usable_sheet",
                                        "path": [[40, 40], [180, 40], [180, 160], [40, 160]],
                                        "closed": True,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )
    overlay = snapshot["sheets"][0]["pieces"][0]["overlays"][0]
    assert overlay["kind"] == "liner"
    assert overlay["layer"] == "Liner"
    assert overlay["geometry"]["path"][0] == [40.0, 40.0]
    assert overlay["geometry"]["closed"] is True
    assert "holes" not in overlay["geometry"]
    assert snapshot["sheets"][0]["pieces"][0]["geometry"]["holes"] == []


def test_canonicalize_accepts_open_overlay_line_inside_extra():
    snapshot = canonicalize_snapshot_geometries(
        {
            "sheets": [
                {
                    "sheet_no": 1,
                    "pieces": [
                        {
                            "id": 1,
                            "label": "1.1",
                            "piece_type": "Extra",
                            "geometry": _contract(((0, 0), (400, 0), (400, 600), (0, 600))),
                            "overlays": [
                                {
                                    "kind": "back_groove",
                                    "layer": "Rear Groove",
                                    "geometry": {
                                        "schema_version": 1,
                                        "unit": "mm",
                                        "coordinate_space": "usable_sheet",
                                        "path": [[360, 40], [360, 560]],
                                        "closed": False,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )
    overlay = snapshot["sheets"][0]["pieces"][0]["overlays"][0]
    assert overlay["kind"] == "back_groove"
    assert overlay["geometry"]["path"] == [[360.0, 40.0], [360.0, 560.0]]
    assert overlay["geometry"]["closed"] is False


def test_canonicalize_rejects_overlay_on_regular_piece():
    snapshot = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 1,
                        "piece_type": "Regular",
                        "geometry": _contract(((0, 0), (400, 0), (400, 600), (0, 600))),
                        "overlays": [
                            {
                                "kind": "liner",
                                "layer": "Liner",
                                "geometry": {
                                    "schema_version": 1,
                                    "unit": "mm",
                                    "coordinate_space": "usable_sheet",
                                    "path": [[40, 40], [180, 40], [180, 160], [40, 160]],
                                    "closed": True,
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    with pytest.raises(DxfGeometrySnapshotError, match="Extra"):
        canonicalize_snapshot_geometries(snapshot)


def test_sanitize_keeps_extra_overlays_inside_after_applied_trim():
    from almdina_erp.almdina_erp.domain.cutting.dxf_applied_trim import (
        apply_adaptive_trim_to_fixed_dxf_layout,
    )

    snapshot = {
        "full_board_width_cm": 122.0,
        "full_board_length_cm": 244.0,
        "usable_board_width_cm": 122.0,
        "usable_board_length_cm": 244.0,
        "trim_cm": 0.0,
        "sheets": [
            {
                "sheet_no": 1,
                "full_width_cm": 122.0,
                "full_length_cm": 244.0,
                "usable_width_cm": 122.0,
                "usable_length_cm": 244.0,
                "w": 122.0,
                "h": 244.0,
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "piece_type": "Extra",
                        "x": 10.0,
                        "y": 10.0,
                        "w": 33.0,
                        "h": 89.9,
                        "geometry": _contract(
                            ((100, 100), (430, 100), (430, 999), (100, 999))
                        ),
                        "overlays": [
                            {
                                "kind": "liner",
                                "layer": "Liner",
                                "geometry": {
                                    "schema_version": 1,
                                    "unit": "mm",
                                    "coordinate_space": "usable_sheet",
                                    "path": [[97.5, 102.0], [97.5, 997.0]],
                                    "closed": False,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
    trimmed = apply_adaptive_trim_to_fixed_dxf_layout(snapshot, preferred_trim_mm=5.0)
    sanitized = sanitize_plan_snapshot(trimmed)
    overlay = sanitized["sheets"][0]["pieces"][0]["overlays"][0]
    assert overlay["kind"] == "liner"
    assert overlay["geometry"]["path"][0][0] == pytest.approx(92.5)
