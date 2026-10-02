from pathlib import Path

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.services.dxf_import_service import (
    DxfImportError,
    _validate_sheet_contours,
)


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
        "OFFCUT_LAYER",
        "EXTRA_OVERLAY_LAYER_NAMES",
        "_overlay_source_paths",
        "_collect_extra_overlay_candidates",
        "_attach_extra_overlays",
        "_attach_text_labels",
        "TEXT_LABEL_LAYER",
        "_default_layer_role_segments",
        "DESIGNER_DEFAULT_LAYER",
        "infer_sheets",
        "_missing_role_layer_guidance",
        "_parse_r12_lines",
        "_match_pieces_to_order",
        "read_dxf_geometry",
        "assemble_contours",
        "أي طبقة غير SHEET_OUTLINE أو CUT_PATH أو OFFCUT",
    ]:
        assert token in src
    assert DXF_READER.exists()
    assert DXF_GEOMETRY.exists()


def test_dxf_import_mirrors_secure_export_layers():
    secure = _source(SECURE_DXF)
    importer = _source(DXF_IMPORT)
    assert 'layer("SHEET_OUTLINE", 8)' in secure
    assert 'layer("CUT_PATH", 1)' in secure
    assert 'layer("OFFCUT", EXTRA_OVERLAY_LAYER_COLORS.OFFCUT)' in secure
    assert 'layer("Liner", EXTRA_OVERLAY_LAYER_COLORS.Liner)' in secure
    assert 'layer(TEXT_LABEL_LAYER, 7)' in secure
    assert 'SHEET_OUTLINE_LAYER = "SHEET_OUTLINE"' in importer
    assert 'CUT_PATH_LAYER = "CUT_PATH"' in importer
    assert "EXTRA_OVERLAY_LAYER_NAMES" in importer
    assert "TEXT_LABEL_LAYER" in importer


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
    assert "entity_id" in src


def test_board_area_uses_correct_cm2_to_m2_conversion():
    src = _source(DXF_IMPORT)
    assert "total_board_area_m2" in src
    assert "/ 10000.0" in src


def test_board_dimensions_are_exact_for_sheet_outline_and_layer0_inference():
    src = _source(DXF_IMPORT)
    assert "dimensions_match_exact" in src
    assert "width_mm / 10.0" in src
    assert "height_mm / 10.0" in src
    assert "BOARD_DIMENSION_TOLERANCE_MM" not in src
    assert "تتطابق أبعاد اللوح تمامًا دون سماحية" in src


def _board_contour(width_mm: float, height_mm: float) -> dict:
    return {
        "points": [
            (0.0, 0.0),
            (width_mm, 0.0),
            (width_mm, height_mm),
            (0.0, height_mm),
        ],
        "closed": True,
        "branched": False,
    }


def test_sheet_outline_accepts_canonical_exact_board_dimensions():
    sheets = _validate_sheet_contours(
        [_board_contour(1220, 2440)],
        expected_width_mm=1220,
        expected_height_mm=2440,
    )
    assert len(sheets) == 1


@pytest.mark.parametrize(
    "actual_width,actual_height",
    [(1219, 2440), (1219.9, 2440), (2440, 1220)],
)
def test_sheet_outline_rejects_real_or_swapped_board_dimension_difference(
    actual_width: float,
    actual_height: float,
):
    with pytest.raises(DxfImportError, match="يجب أن تتطابق أبعاد اللوح تمامًا"):
        _validate_sheet_contours(
            [_board_contour(actual_width, actual_height)],
            expected_width_mm=1220,
            expected_height_mm=2440,
        )


def test_sheet_outline_accepts_same_fractional_dimension_after_normalization():
    sheets = _validate_sheet_contours(
        [_board_contour(1220.1000000000001, 2440.0)],
        expected_width_mm=1220.1,
        expected_height_mm=2440.0,
    )
    assert len(sheets) == 1
