from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECURE_DXF = ROOT / "public" / "js" / "secure_dxf_export.js"
WORKFLOW_JS = ROOT / "public" / "js" / "door_cutting_order_workflow.js"
HOOKS = ROOT / "hooks.py"


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


def test_export_uses_resolved_per_axis_trim_without_rewriting_optimizer_spacing():
    src = _source(SECURE_DXF)
    assert "function appliedTrimMm(plan, sheet)" in src
    assert "sheet && sheet.applied_trim_width_cm" in src
    assert "sheet && sheet.applied_trim_length_cm" in src
    assert "plan.applied_trim_width_cm" in src
    assert "plan.applied_trim_length_cm" in src
    assert "const appliedTrim = appliedTrimMm(plan, sheet);" in src
    assert "const x = offsetX + appliedTrim.width + num(piece.x) * 10;" in src
    assert (
        "const y = offsetY + fullHeight - appliedTrim.length - num(piece.y) * 10 - pieceHeight;"
        in src
    )
    assert "const trimMm = num(plan.trim_cm) * 10;" not in src
    assert "piece.x) * 10" in src
    assert "piece.y) * 10" in src


def test_secure_exporter_removes_legacy_buttons_without_loading_legacy_workflow():
    workflow = _source(WORKFLOW_JS)
    secure = _source(SECURE_DXF)
    hooks = _source(HOOKS)
    assert 'frm.add_custom_button("تصدير DXF"' in workflow
    assert '"public/js/door_cutting_order_workflow.js"' not in hooks
    assert 'const STRIP_EXPORT_LABELS = [' in secure
    assert 'function isExportButtonLabel(text)' in secure
    assert 'STRIP_EXPORT_LABELS.includes(value)' in secure
    assert '/تصدير\\s*DXF/i.test(value)' in secure
    assert 'function installToolbarGuard(frm)' in secure
    assert "plan_control_actions" in secure
    assert 'frm.remove_custom_button(label)' in secure
    assert 'new MutationObserver(() => stripUnauthorizedExportButtons(frm))' in secure
    # AutoCAD export is hosted in the cutting-plan section, not the toolbar.
    assert "frm.add_custom_button(label, () => validatedExport(frm))" not in secure
    assert "frm.add_custom_button(buttonLabel()" not in secure


def test_plan_section_hosts_permissioned_print_and_dxf_actions():
    plan = _source(ROOT / "public" / "js" / "door_cutting_order_plan_ux.js")
    assert "dco-print-cutting-plan" in plan
    assert "dco-export-dxf" in plan
    assert "dco-upload-dxf-plan" in plan
    assert 'can(frm, "print_cutting_plan")' in plan or "print_cutting_plan" in plan
    assert 'can(frm, "upload_dxf")' in plan
    assert 'can(frm, "replace_dxf")' in plan
    assert "printCuttingPlan" in plan
    assert "exportCuttingPlanDxf" in plan
    assert "uploadCuttingPlanDxf" in plan
    assert "export_order_dxf" in plan
    assert "upload_production_dxf" in plan


def test_dxf_import_service_is_wired_for_round_trip():
    importer = ROOT / "almdina_erp" / "services" / "dxf_import_service.py"
    src = _source(importer)
    assert "def parse_production_dxf" in src
    assert "_parse_r12_lines" in src
