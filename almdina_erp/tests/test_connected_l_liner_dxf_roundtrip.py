"""Export and reimport a door whose two liners meet as one L toolpath."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    has_self_intersection,
    point_in_polygon,
    point_to_polygon_distance,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import GEOMETRY_TOLERANCE_MM
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    merged_liner_region_polygons_mm,
    merged_liner_toolpaths_mm,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.services import dxf_import_service as legacy
from almdina_erp.almdina_erp.services.strict_dxf_import_service import parse_production_dxf

BIT_MM = 5.0
WIDTH_CM = 1.5
ORIGIN = (40.0, 2000.0)


def _place(point):
    return (ORIGIN[0] + point[0], ORIGIN[1] - point[1])


def _specs():
    return [
        {"side": "edge_width_top", "offset_cm": 2, "start_cm": 0, "length_cm": 0},
        {"side": "edge_long_left", "offset_cm": 2, "start_cm": 0, "length_cm": 0},
    ]


def _order():
    row = SimpleNamespace(
        name="row-1",
        piece_instance_id="connected-l:1",
        piece_type="Regular",
        width_cm=40,
        length_cm=60,
        cut_width_cm=40,
        cut_length_cm=60,
        qty=1,
        allow_rotation=0,
        default_edge_type="",
        extra_liner=1,
        extra_back_groove=0,
        extra_recessed_handle_cutout=0,
        extra_double=0,
        extra_full_door_double=0,
        liner_reference_side="edge_width_top",
        liner_offset_cm=2,
        liner_width_cm=WIDTH_CM,
        liner_start_cm=0,
        liner_length_cm=0,
        liner_specs_json=json.dumps({
            "width_cm": WIDTH_CM,
            "liners": [
                {"id": "liner_1", "side": "edge_width_top", "offset_cm": 2, "start_cm": 0, "length_cm": 0},
                {"id": "liner_2", "side": "edge_long_left", "offset_cm": 2, "start_cm": 0, "length_cm": 0},
            ],
        }),
    )
    return SimpleNamespace(
        trim_margin_mm=0,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        kerf_mm=3,
        default_edge_type="",
        deduct_edge_thickness=False,
        pieces=[row],
    )


def _interior_overlap_edge(start, end) -> bool:
    def inside(point):
        return point[0] <= 35.0 + 1e-6 and point[1] <= 35.0 + 1e-6

    def on_outer(point):
        return abs(point[0] - 20.0) <= 1e-6 or abs(point[1] - 20.0) <= 1e-6

    return inside(start) and inside(end) and not (on_outer(start) and on_outer(end))


def test_connected_l_liner_dxf_round_trip_keeps_one_corner(tmp_path):
    piece = LinerPiece("Regular", 40, 60)
    specs = _specs()
    path = merged_liner_toolpaths_mm(piece, specs, WIDTH_CM, BIT_MM)[0]
    ring = merged_liner_region_polygons_mm(piece, specs, WIDTH_CM)[0]
    assert len(ring) == 6
    assert not has_self_intersection(ring, GEOMETRY_TOLERANCE_MM)
    assert point_in_polygon((27.5, 27.5), ring)
    assert point_to_polygon_distance((27.5, 27.5), ring) > 1.0
    assert not any(_interior_overlap_edge(start, end) for start, end in zip(ring, ring[1:] + ring[:1]))

    dxf_path = tmp_path / "connected-l.dxf"
    document = ezdxf.new("R2010")
    model = document.modelspace()
    model.add_lwpolyline(
        [(0, 0), (1220, 0), (1220, 2440), (0, 2440)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )
    outline = [(0, 0), (400, 0), (400, 600), (0, 600)]
    for start, end in zip(outline, outline[1:] + outline[:1]):
        model.add_line(_place(start), _place(end), dxfattribs={"layer": "GEOMETRY"})
    model.add_lwpolyline(
        [_place(point) for point in ring],
        close=True,
        dxfattribs={"layer": "GEOMETRY"},
    )
    model.add_lwpolyline(
        [_place(point) for point in path],
        dxfattribs={"layer": "Liner"},
    )
    document.saveas(dxf_path)

    written = ezdxf.readfile(dxf_path)
    geometry = [
        entity for entity in written.modelspace()
        if entity.dxf.layer.upper() == "GEOMETRY" and entity.dxftype() == "LWPOLYLINE"
    ]
    assert len(geometry) == 1
    assert geometry[0].closed
    assert len(list(geometry[0].vertices())) == 6
    liner_paths = [
        entity for entity in written.modelspace()
        if entity.dxf.layer == "Liner" and entity.dxftype() == "LWPOLYLINE"
    ]
    assert len(liner_paths) == 1
    assert not liner_paths[0].closed

    with patch.object(legacy.frappe, "get_site_path", return_value=str(dxf_path)):
        snapshot = parse_production_dxf(
            "/private/files/connected-l.dxf",
            _order(),
            settings=PlanSettings("Auto", "CNC", 5, 3, 0, deduct_edge_thickness=False),
            tool_diameters={"liner_tool_diameter_mm": BIT_MM},
        )
    pieces = [item for sheet in snapshot["sheets"] for item in sheet["pieces"]]
    assert len(pieces) == 1
    liners = [overlay for overlay in pieces[0]["overlays"] if overlay["kind"] == "liner"]
    assert len(liners) == 1
    assert len(liners[0]["geometry"]["path"]) == len(path)
