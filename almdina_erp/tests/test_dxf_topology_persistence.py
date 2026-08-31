from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    DxfTopologyError,
    parse_geometry_mm,
    serialize_geometry_mm,
    validate_snapshot_material_layout,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.services.dxf_import_service import _public_piece
from almdina_erp.almdina_erp.services.export_validation_service import (
    _plan_to_export_snapshot,
)


def _geometry(outer, holes=()):
    return serialize_geometry_mm(
        PartGeometry(
            outer=tuple(tuple(point) for point in outer),
            holes=tuple(tuple(tuple(point) for point in hole) for hole in holes),
        )
    )


def _snapshot(nested_outer=None):
    owner = _geometry(
        ((0, 0), (100, 0), (100, 100), (0, 100)),
        (((20, 20), (80, 20), (80, 80), (20, 80)),),
    )
    nested = _geometry(
        nested_outer or ((30, 30), (50, 30), (50, 50), (30, 50))
    )
    return {
        "kerf_cm": 0.5,
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "x": 0,
                        "y": 0,
                        "w": 10,
                        "h": 10,
                        "geometry": owner,
                    },
                    {
                        "id": 2,
                        "label": "2.1",
                        "x": 3,
                        "y": 3,
                        "w": 2,
                        "h": 2,
                        "geometry": nested,
                    },
                ],
            }
        ],
        "validation": {"is_valid": True, "errors": []},
        "unplaced": [],
    }


def test_geometry_contract_is_versioned_mm_and_round_trips_holes():
    geometry = _geometry(
        ((0, 0), (100, 0), (100, 100), (0, 100)),
        (((20, 20), (80, 20), (80, 80), (20, 80)),),
    )

    assert geometry["schema_version"] == 1
    assert geometry["unit"] == "mm"
    assert geometry["coordinate_space"] == "usable_sheet"
    parsed = parse_geometry_mm(geometry)
    assert parsed.outer[2] == (100.0, 100.0)
    assert parsed.holes[0][0] == (20.0, 20.0)


def test_snapshot_sanitizer_preserves_valid_geometry_and_fails_closed_on_malformed():
    snapshot = _snapshot()
    sanitized = sanitize_plan_snapshot(snapshot)
    assert sanitized["sheets"][0]["pieces"][0]["geometry"]["holes"]

    malformed = _snapshot()
    malformed["sheets"][0]["pieces"][0]["geometry"]["holes"] = "not-an-array"
    with pytest.raises(DxfGeometrySnapshotError):
        sanitize_plan_snapshot(malformed)


def test_valid_nested_piece_survives_topology_aware_reload_validation():
    assert validate_snapshot_material_layout(
        _snapshot(),
        required_clearance_mm=5.0,
    ) is True


def test_crossing_hole_boundary_is_rejected_after_reload():
    crossing = _snapshot(((70, 30), (90, 30), (90, 50), (70, 50)))
    with pytest.raises(DxfTopologyError) as exc_info:
        validate_snapshot_material_layout(crossing, required_clearance_mm=5.0)
    assert exc_info.value.code == "MATERIAL_FOOTPRINT_OVERLAP"


def test_hole_clearance_is_rejected_after_reload():
    near_hole_edge = _snapshot(((22, 30), (42, 30), (42, 50), (22, 50)))
    with pytest.raises(DxfTopologyError) as exc_info:
        validate_snapshot_material_layout(near_hole_edge, required_clearance_mm=5.0)
    assert exc_info.value.code == "HOLE_CLEARANCE_VIOLATION"


def test_legacy_rectangle_snapshot_keeps_legacy_validation_path():
    legacy = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {"id": 1, "x": 0, "y": 0, "w": 10, "h": 10},
                ],
            }
        ]
    }
    assert validate_snapshot_material_layout(legacy, required_clearance_mm=5.0) is False


def test_import_public_piece_replaces_private_topology_with_canonical_geometry():
    piece = {
        "id": 7,
        "label": "1.1",
        "x": 1,
        "y": 2,
        "w": 10,
        "h": 10,
        "_outline_cm": [(1, 2), (11, 2), (11, 12), (1, 12)],
        "_holes_cm": [[(3, 4), (9, 4), (9, 10), (3, 10)]],
        "_outline_mm": [(10, 20), (110, 20), (110, 120), (10, 120)],
        "_holes_mm": [[(30, 40), (90, 40), (90, 100), (30, 100)]],
        "_sheet_no": 1,
    }

    public = _public_piece(piece)
    assert all(not key.startswith("_") for key in public)
    assert public["geometry"]["outer"][0] == [10.0, 20.0]
    assert public["geometry"]["holes"][0][0] == [30.0, 40.0]


def _saved_piece(piece_id: int, label: str, x_mm: float):
    return SimpleNamespace(
        sheet_no=1,
        piece_id=piece_id,
        piece_label=label,
        source_piece_no=piece_id,
        copy_no=1,
        x_mm=x_mm,
        y_mm=0,
        width_mm=100,
        height_mm=100,
        original_width_cm=10,
        original_length_cm=10,
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
    )


def _source():
    return SimpleNamespace(
        sheet_no=1,
        source_type="Full Board",
        remnant=None,
        board_item=None,
        material="",
        color="",
        thickness_mm=18,
        full_width_mm=1000,
        full_length_mm=1000,
        usable_width_mm=1000,
        usable_length_mm=1000,
        source_area_m2=1,
    )


def test_export_reconstruction_rebinds_geometry_by_piece_id_not_dimensions():
    first_geometry = _geometry(((0, 0), (100, 0), (100, 100), (0, 100)))
    second_geometry = _geometry(((200, 0), (300, 0), (300, 100), (200, 100)))
    persisted = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {"id": 1, "label": "1.1", "geometry": first_geometry},
                    {"id": 2, "label": "2.1", "geometry": second_geometry},
                ],
            }
        ]
    }
    plan = SimpleNamespace(
        snapshot_json=json.dumps(persisted),
        placed_pieces=[
            _saved_piece(2, "2.1", 200),
            _saved_piece(1, "1.1", 0),
        ],
        sources=[_source()],
        engine_version="dxf-import-v2",
        method_key="custom_dxf",
        method_label="Uploaded DXF",
        full_board_width_mm=1000,
        full_board_length_mm=1000,
        usable_board_width_mm=1000,
        usable_board_length_mm=1000,
        kerf_mm=5,
        trim_margin_mm=0,
        used_area_m2=0.02,
        total_source_area_m2=1,
        waste_area_m2=0.98,
        required_boards=1,
    )

    rebuilt = _plan_to_export_snapshot(plan)
    pieces = rebuilt["sheets"][0]["pieces"]
    assert pieces[0]["id"] == 2
    assert pieces[0]["geometry"] == second_geometry
    assert pieces[1]["id"] == 1
    assert pieces[1]["geometry"] == first_geometry


def test_export_reconstruction_fails_closed_when_saved_piece_identity_is_missing():
    persisted = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "geometry": _geometry(((0, 0), (100, 0), (100, 100), (0, 100))),
                    }
                ],
            }
        ]
    }
    plan = SimpleNamespace(
        snapshot_json=json.dumps(persisted),
        placed_pieces=[_saved_piece(2, "2.1", 0)],
        sources=[_source()],
        engine_version="dxf-import-v2",
        method_key="custom_dxf",
        method_label="Uploaded DXF",
        full_board_width_mm=1000,
        full_board_length_mm=1000,
        usable_board_width_mm=1000,
        usable_board_length_mm=1000,
        kerf_mm=5,
        trim_margin_mm=0,
        used_area_m2=0.01,
        total_source_area_m2=1,
        waste_area_m2=0.99,
        required_boards=1,
    )

    with pytest.raises(DxfGeometrySnapshotError):
        _plan_to_export_snapshot(plan)
