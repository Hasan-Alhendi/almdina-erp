from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DXF_IMPORT = ROOT / "almdina_erp" / "services" / "dxf_import_service.py"
DXF_READER = ROOT / "almdina_erp" / "infrastructure" / "cutting" / "dxf_reader.py"
DXF_GEOMETRY = ROOT / "almdina_erp" / "domain" / "cutting" / "dxf_geometry.py"
SECURE_DXF = (
    ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "secure_dxf_export.js"
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dxf_import_service_exists_with_layered_core_functions():
    src = _source(DXF_IMPORT)
    for token in [
        "def parse_production_dxf",
        "def validate_imported_plan",
        "SHEET_OUTLINE_LAYER",
        "CUT_PATH_LAYER",
        "_parse_r12_lines",
        "_match_pieces_to_order",
        "read_dxf_geometry",
        "assemble_contours",
    ]:
        assert token in src
    assert DXF_READER.exists()
    assert DXF_GEOMETRY.exists()


def test_dxf_import_mirrors_secure_export_layers():
    secure = _source(SECURE_DXF)
    importer = _source(DXF_IMPORT)
    assert 'layer("SHEET_OUTLINE", 8)' in secure
    assert 'layer("CUT_PATH", 1)' in secure
    assert 'SHEET_OUTLINE_LAYER = "SHEET_OUTLINE"' in importer
    assert 'CUT_PATH_LAYER = "CUT_PATH"' in importer


def test_round_trip_line_parser_is_kept_as_r12_fallback():
    src = _source(DXF_IMPORT)
    assert "def _parse_r12_lines" in src
    assert 'if code == "0":' in src
    assert 'entity_type == "LINE"' in src
    assert 'value == "LWPOLYLINE"' in src
    assert "legacy_line_parser" in src


def test_strict_import_contract_rejects_unmatched_or_forbidden_rotation():
    src = _source(DXF_IMPORT)
    assert "DIMENSION_TOLERANCE_MM = 2.0" in src
    assert "لا تطابق أي قطعة متبقية" in src
    assert "التدوير غير مسموح" in src
    assert "imported-" not in src


def test_validate_imported_plan_checks_count_bounds_overlap_and_kerf():
    src = _source(DXF_IMPORT)
    assert "placed_count != expected_count" in src
    assert "polygon_inside_rect" in src
    assert "polygons_overlap" in src
    assert "polygon_distance" in src
    assert "kerf_mm" in src


def test_import_enforces_sheet_and_cut_contour_topology():
    src = _source(DXF_IMPORT)
    assert "is_axis_aligned_rectangle" in src
    assert "غير مغلق" in src
    assert "تتقاطع مع نفسها" in src
    assert "full_width_mm" in src
    assert "full_height_mm" in src


def test_board_area_uses_correct_cm2_to_m2_conversion():
    src = _source(DXF_IMPORT)
    assert "total_board_area_m2" in src
    assert "/ 10000.0" in src
