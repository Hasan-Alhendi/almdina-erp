from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DXF_IMPORT = ROOT / "almdina_erp" / "services" / "dxf_import_service.py"
SECURE_DXF = ROOT / "public" / "js" / "secure_dxf_export.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dxf_import_service_exists_with_core_functions():
    src = _source(DXF_IMPORT)
    for token in [
        "def parse_production_dxf",
        "def validate_imported_plan",
        "SHEET_OUTLINE_LAYER",
        "CUT_PATH_LAYER",
        "_parse_r12_lines",
        "_match_pieces_to_order",
    ]:
        assert token in src


def test_dxf_import_mirrors_secure_export_layers():
    secure = _source(SECURE_DXF)
    importer = _source(DXF_IMPORT)
    assert 'layer("SHEET_OUTLINE", 8)' in secure
    assert 'layer("CUT_PATH", 1)' in secure
    assert 'SHEET_OUTLINE_LAYER = "SHEET_OUTLINE"' in importer
    assert 'CUT_PATH_LAYER = "CUT_PATH"' in importer


def test_round_trip_line_parser_is_implemented_for_r12_pairs():
    src = _source(DXF_IMPORT)
    assert "def _parse_r12_lines" in src
    assert 'if code == "0":' in src
    assert 'entity_type == "LINE"' in src


def test_validate_imported_plan_checks_piece_count_contract():
    src = _source(DXF_IMPORT)
    assert "def validate_imported_plan" in src
    assert "placed_count != expected_count" in src
    assert "exceeds board bounds" in src
