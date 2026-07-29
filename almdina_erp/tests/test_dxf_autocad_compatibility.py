from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECURE_DXF = ROOT / "public" / "js" / "secure_dxf_export.js"
WORKFLOW_JS = ROOT / "public" / "js" / "door_cutting_order_workflow.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_secure_export_uses_r12_ascii_and_simple_line_entities():
    src = _source(SECURE_DXF)
    assert 'const DXF_VERSION = "AC1009"' in src
    assert 'pair(0, "LINE")' in src
    assert 'pair(10, dxfNumber(x1))' in src
    assert 'pair(11, dxfNumber(x2))' in src
    assert 'pair(21, dxfNumber(y2))' in src
    assert 'pair(31, 0)' in src


def test_secure_export_avoids_legacy_polyline_and_r12_insunits_mix():
    src = _source(SECURE_DXF)
    assert 'pair(0, "POLYLINE")' not in src
    assert 'pair(0, "VERTEX")' not in src
    assert '$INSUNITS' not in src


def test_secure_export_has_minimal_sections_layers_and_eof_self_check():
    src = _source(SECURE_DXF)
    for token in [
        'pair(2, "HEADER")',
        'pair(2, "TABLES")',
        'pair(2, "BLOCKS")',
        'pair(2, "ENTITIES")',
        'layer("SHEET_OUTLINE", 8)',
        'layer("CUT_PATH", 1)',
        'pair(0, "EOF")',
        'validateDxfText(dxf)',
        'content.endsWith("0\\r\\nEOF\\r\\n")',
    ]:
        assert token in src


def test_autocad_export_button_is_distinct_from_legacy_exporter():
    src = _source(SECURE_DXF)
    assert 'تصدير DXF لأوتوكاد' in src
    assert 'Export DXF for AutoCAD' in src
    assert 'const STRIP_EXPORT_LABELS = [' in src
    assert '"تصدير DXF"' in src
    assert '"Export DXF"' in src


def test_export_keeps_required_cut_and_preview_layers():
    src = _source(SECURE_DXF)
    assert 'rectangle("SHEET_OUTLINE"' in src
    assert 'rectangle("CUT_PATH"' in src
    assert 'const fullWidth = num(sheet.full_width_cm || plan.full_board_width_cm) * 10' in src
    assert 'const pieceWidth = num(piece.w) * 10' in src
    assert 'pair(0, "LINE")' in src
    assert '_AutoCAD2020_R12.dxf' in src
    assert 'application/dxf;charset=us-ascii' in src


def test_legacy_workflow_exporter_is_identifiable_for_removal():
    # The historical source-aware workflow still contains the old exporter, so
    # the secure exporter must remove every legacy label through one canonical
    # label predicate rather than depending on one exact source-code expression.
    workflow = _source(WORKFLOW_JS)
    secure = _source(SECURE_DXF)
    assert 'frm.add_custom_button("تصدير DXF"' in workflow
    assert 'const STRIP_EXPORT_LABELS = [' in secure
    assert 'function isExportButtonLabel(text)' in secure
    assert 'STRIP_EXPORT_LABELS.includes(t)' in secure
    assert 'frm.remove_custom_button(label)' in secure


def test_dxf_import_service_is_wired_for_round_trip():
    importer = ROOT / "almdina_erp" / "services" / "dxf_import_service.py"
    src = _source(importer)
    assert "def parse_production_dxf" in src
    assert "_parse_r12_lines" in src
