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
    assert '["تصدير DXF", "Export DXF"]' in src


def test_export_keeps_required_cut_and_preview_layers():
    src = _source(SECURE_DXF)
    assert 'rectangle("SHEET_OUTLINE"' in src
    assert 'rectangle("CUT_PATH"' in src
    assert 'coordinate_units: DXF_UNITS' in src
    assert 'geometry_entity: "LINE"' in src
    assert 'compatibility_target: "AutoCAD 2020+"' in src


def test_legacy_workflow_exporter_is_identifiable_for_removal():
    # The historical source-aware workflow still contains the old exporter, so
    # the secure exporter must remove its old button label whenever it appears.
    workflow = _source(WORKFLOW_JS)
    secure = _source(SECURE_DXF)
    assert 'frm.add_custom_button("تصدير DXF"' in workflow
    assert 'text === "تصدير DXF" || text === "Export DXF"' in secure
