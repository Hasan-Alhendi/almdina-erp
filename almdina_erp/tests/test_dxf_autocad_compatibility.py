import io
from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")

from almdina_erp.almdina_erp.services.dxf_autocad_normalization import (
    assert_single_dxf_document,
    rebuild_autocad_dxf,
)


ROOT = Path(__file__).resolve().parents[1]
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
SECURE_DXF = CUTTING_PLAN / "secure_dxf_export.js"
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
        'layer("Liner", EXTRA_OVERLAY_LAYER_COLORS.Liner)',
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
    assert '"تنزيل DXF المرفوع"' in src
    assert "download_uploaded_dxf" in src
    assert "shouldDownloadOriginalUpload" in src


def test_export_keeps_required_cut_and_preview_layers():
    src = _source(SECURE_DXF)
    assert 'rectangle("SHEET_OUTLINE"' in src
    assert 'rectangle("CUT_PATH"' in src
    assert 'const fullWidth = num(sheet.full_width_cm || plan.full_board_width_cm) * 10' in src
    assert 'const pieceWidth = num(piece.w) * 10' in src
    assert 'pair(0, "LINE")' in src
    assert 'const NORMALIZE_DXF_METHOD =' in src
    assert 'normalize_dxf_for_autocad' in src
    assert 'content_b64: btoa(dxf)' in src
    assert 'application/dxf;charset=utf-8' in src


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


def test_secure_exporter_strips_legacy_buttons_and_legacy_workflow_stays_deleted():
    secure = _source(SECURE_DXF)
    hooks = _source(HOOKS)

    assert not WORKFLOW_JS.exists()
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
    plan = _source(CUTTING_PLAN / "door_cutting_order_plan_ux.js")
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


def test_secure_export_declares_exact_layer_table_count():
    src = _source(SECURE_DXF)
    assert "const DXF_LAYER_COUNT = 7" in src
    assert 'pair(2, "LAYER") + pair(70, DXF_LAYER_COUNT)' in src



def _sample_r12_bytes(newline: bytes) -> bytes:
    source = ezdxf.new("R12")
    source.layers.add(name="SHEET_OUTLINE", color=8)
    source.layers.add(name="CUT_PATH", color=1)
    modelspace = source.modelspace()
    modelspace.add_line((10, 20), (110, 20), dxfattribs={"layer": "SHEET_OUTLINE"})
    modelspace.add_line((15.5, 25.25), (15.5, 95.75), dxfattribs={"layer": "CUT_PATH"})
    output = io.StringIO()
    source.write(output)
    return output.getvalue().replace("\n", "\r\n").encode("ascii").replace(b"\r\n", newline)


@pytest.mark.parametrize("newline", [b"\r\n", b"\n"])
def test_rebuild_autocad_dxf_preserves_geometry_for_crlf_and_lf(newline):
    raw = _sample_r12_bytes(newline)
    source = ezdxf.read(io.StringIO(raw.decode("ascii").replace("\r\n", "\n")))
    source_lines = list(source.modelspace())

    normalized = rebuild_autocad_dxf(raw)
    text = normalized.decode("utf-8")
    assert_single_dxf_document(text)

    result = ezdxf.read(io.StringIO(text))
    result_lines = list(result.modelspace())
    assert result.dxfversion == "AC1024"
    assert len(result_lines) == len(source_lines)
    assert {line.dxf.layer for line in result_lines} == {"SHEET_OUTLINE", "CUT_PATH"}
    assert [
        (tuple(line.dxf.start), tuple(line.dxf.end))
        for line in result_lines
    ] == [
        (tuple(line.dxf.start), tuple(line.dxf.end))
        for line in source_lines
    ]
    assert result.audit().has_errors is False


def test_rebuild_autocad_dxf_rejects_non_line_geometry():
    source = ezdxf.new("R12")
    source.modelspace().add_circle((0, 0), 10)
    output = io.StringIO()
    source.write(output)

    with pytest.raises(ValueError, match="LINE entities only"):
        rebuild_autocad_dxf(output.getvalue().encode("ascii"))

def test_secure_dxf_export_asset_is_cache_busted():
    registry = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_workspace_asset_registry.js"
    src = _source(registry)
    assert "cutting_plan/secure_dxf_export.js" in src
    assert "?v=2" not in src

