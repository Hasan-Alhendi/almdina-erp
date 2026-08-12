from pathlib import Path

import pytest

pytest.importorskip("ezdxf")
import ezdxf

from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import (
    SUPPORTED_DXF_ENTITY_TYPES,
    read_dxf_geometry,
)


def test_reader_supports_production_line_and_curve_entities(tmp_path: Path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (1220, 0), (1220, 2440), (0, 2440)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )
    msp.add_line((10, 10), (200, 10), dxfattribs={"layer": "CUT_PATH"})
    msp.add_polyline2d(
        [(210, 10), (230, 10), (230, 30), (210, 30)],
        close=True,
        dxfattribs={"layer": "CUT_PATH"},
    )
    msp.add_arc((250, 100), 40, 0, 180, dxfattribs={"layer": "CUT_PATH"})
    msp.add_circle((400, 100), 25, dxfattribs={"layer": "CUT_PATH"})
    msp.add_ellipse((520, 100), major_axis=(45, 0), ratio=0.5, dxfattribs={"layer": "CUT_PATH"})
    spline = msp.add_spline(dxfattribs={"layer": "CUT_PATH"})
    spline.fit_points = [(600, 50, 0), (630, 100, 0), (660, 50, 0)]
    path = tmp_path / "entities.dxf"
    doc.saveas(path)

    result = read_dxf_geometry(
        str(path),
        relevant_layers={"SHEET_OUTLINE", "CUT_PATH"},
    )

    assert result["segments"]
    assert result["unsupported"] == []
    entity_types = {row["entity_type"] for row in result["segments"]}
    assert {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"} <= entity_types
    assert "POLYLINE" in SUPPORTED_DXF_ENTITY_TYPES
