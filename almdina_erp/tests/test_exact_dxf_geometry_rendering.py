from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIECE_GEOMETRY = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_piece_geometry.js"
)
RENDERER = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_cutting_plan_renderer.js"
)
BOOTSTRAP = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_surface_bootstrap.js"
)
REGISTRY = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_workspace_asset_registry.js"
)
DXF_READER = ROOT / "almdina_erp" / "infrastructure" / "cutting" / "dxf_reader.py"
DXF_IMPORT = ROOT / "almdina_erp" / "services" / "dxf_import_service.py"
SNAPSHOT = ROOT / "almdina_erp" / "domain" / "cutting" / "dxf_geometry_snapshot.py"
SNAPSHOT_SECURITY = ROOT / "almdina_erp" / "application" / "orders" / "plan_snapshot_security.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_renderer_consumes_one_canonical_geometry_model() -> None:
    renderer = source(RENDERER)
    model = source(PIECE_GEOMETRY)

    assert "AlmdinaCuttingPlanPieceGeometry" in renderer
    assert renderer.count("geometry.resolve(piece)") == 1
    assert "special_shape_geometry_json" not in renderer
    assert "geometry.schema_version" not in renderer
    assert "clippedGeometry.points" not in renderer
    assert "function persistedDxfModel(piece)" in model
    assert "function manualSpecialModel(piece)" in model
    assert "function cornerModel(piece)" in model
    assert "function rectangleModel(piece" in model


def test_exact_geometry_remains_vector_and_holes_use_even_odd_paths() -> None:
    renderer = source(RENDERER)
    model = source(PIECE_GEOMETRY)

    assert 'geometry.unit !== DXF_UNIT' in model
    assert 'geometry.coordinate_space !== DXF_COORDINATE_SPACE' in model
    assert "geometry.holes.map" in model
    assert 'fill-rule="evenodd"' in renderer
    assert 'clip-rule="evenodd"' in renderer
    assert 'class="dco-shaped-piece-outline"' in renderer
    for forbidden in ("<canvas", "toDataURL", "html2canvas", ".png", "screenshot"):
        assert forbidden not in renderer.lower()
        assert forbidden not in model.lower()


def test_dxf_rendering_reuses_the_accepted_manufacturing_tessellation() -> None:
    reader = source(DXF_READER)
    importer = source(DXF_IMPORT)
    snapshot = source(SNAPSHOT)

    for entity in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE", "ELLIPSE"):
        assert f'"{entity}"' in reader
    assert "CURVE_FLATTENING_TOLERANCE_MM = 0.25" in reader
    assert 'public_piece["geometry"] = serialize_geometry_from_cm(' in importer
    assert '"outer": [[float(x), float(y)]' in snapshot
    assert '"holes": [' in snapshot


def test_snapshot_lifecycle_preserves_geometry_without_live_piece_reconstruction() -> None:
    snapshot = source(SNAPSHOT)
    security = source(SNAPSHOT_SECURITY)
    model = source(PIECE_GEOMETRY)

    assert "canonicalize_snapshot_geometries" in security
    assert 'normalized_piece["geometry"] = serialize_geometry_mm(' in snapshot
    assert "piece.geometry" in model
    assert "frm.doc.pieces" not in model
    assert "setTimeout" not in model
    assert "addEventListener" not in model


def test_web_and_print_share_path_data_but_keep_print_presentation_rules() -> None:
    renderer = source(RENDERER)

    assert "geometryModel.geometry.pathData" in renderer
    assert "planRootFromVisibleDom" in renderer
    assert "planRootFromPlan" in renderer
    assert "buildPrintDocument" in renderer
    assert ".dco-shaped-piece-outline path" in renderer
    assert ".dco-edge-line-svg" in renderer


def test_piece_geometry_loads_before_renderer_in_both_lazy_paths() -> None:
    geometry_asset = "door_cutting_order_piece_geometry.js"
    renderer_asset = "door_cutting_order_cutting_plan_renderer.js"
    for path in (REGISTRY, BOOTSTRAP):
        text = source(path)
        assert geometry_asset in text
        assert renderer_asset in text
        assert text.index(geometry_asset) < text.index(renderer_asset)
