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
        "_offcut_only_cut_segments",
        "DESIGNER_DEFAULT_LAYER",
        "infer_sheets",
        "_missing_role_layer_guidance",
        "_parse_r12_lines",
        "_match_pieces_to_order",
        "read_dxf_geometry",
        "assemble_contours",
        "إذا وُجدت طبقة GEOMETRY فهي الحدود النهائية للدرفات",
        "درف OFFCUT الموجودة فقط على OFFCUT تُحسب مع درف GEOMETRY",
    ]:
        assert token in src
    assert DXF_READER.exists()
    assert DXF_GEOMETRY.exists()


def test_dxf_import_mirrors_secure_export_layers():
    secure = _source(SECURE_DXF)
    importer = _source(DXF_IMPORT)
    assert 'layer("SHEET_OUTLINE", 8)' in secure
    assert 'layer("CUT_PATH", 1)' in secure
    assert 'layer(FINISHED_GEOMETRY_LAYER, 4)' in secure
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
    assert "FORBIDDEN_ROTATION" in src
    assert "CUT_SIZE_MISMATCH" in src
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
    assert "CUT_OPEN" in src
    assert "CUT_SELF_INTERSECTION" in src
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
    assert "SHEET_SIZE_MISMATCH" in src


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
    with pytest.raises(DxfImportError) as exc_info:
        _validate_sheet_contours(
            [_board_contour(actual_width, actual_height)],
            expected_width_mm=1220,
            expected_height_mm=2440,
        )
    assert "SHEET_SIZE_MISMATCH" in exc_info.value.codes
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issues_as_strings
    assert "أبعاد اللوح لا تطابق الطلب" in " ".join(present_issues_as_strings(exc_info.value.issues))


def test_sheet_outline_accepts_same_fractional_dimension_after_normalization():
    sheets = _validate_sheet_contours(
        [_board_contour(1220.1000000000001, 2440.0)],
        expected_width_mm=1220.1,
        expected_height_mm=2440.0,
    )
    assert len(sheets) == 1


# Boundary-regression fixtures: no customer drawing or database mutation.
def _fixed_dxf_snapshot(*positions_mm):
    sheets = []
    for i, (x_mm, y_mm) in enumerate(positions_mm, start=1):
        x, y = x_mm / 10, y_mm / 10
        sheets.append({
            "sheet_no": i,
            "full_width_cm": 122,
            "full_length_cm": 244,
            "usable_width_cm": 122,
            "usable_length_cm": 244,
            "pieces": [{
                "id": i, "x": x, "y": y, "w": 20, "h": 30,
                "geometry": {
                    "schema_version": 1, "unit": "mm",
                    "coordinate_space": "usable_sheet",
                    "outer": [
                        [x_mm, y_mm], [x_mm + 200, y_mm],
                        [x_mm + 200, y_mm + 300], [x_mm, y_mm + 300],
                    ],
                    "holes": [],
                },
            }],
        })
    return {
        "full_board_width_cm": 122, "full_board_length_cm": 244,
        "usable_board_width_cm": 122, "usable_board_length_cm": 244,
        "sheets": sheets,
    }


def test_fixed_dxf_applied_trim_uses_the_same_mandatory_minimum_on_each_sheet():
    from almdina_erp.almdina_erp.domain.cutting.dxf_applied_trim import (
        apply_adaptive_trim_to_fixed_dxf_layout,
    )

    physical = _fixed_dxf_snapshot((5, 10), (10, 10), (10, 5))
    result = apply_adaptive_trim_to_fixed_dxf_layout(physical, preferred_trim_mm=5)
    actual = [
        (s["applied_trim_width_cm"], s["applied_trim_length_cm"])
        for s in result["sheets"]
    ]
    for measured in actual:
        expected = (0.5, 0.5)
        assert measured == pytest.approx(expected)
    for original, adjusted in zip(physical["sheets"], result["sheets"]):
        p, q = original["pieces"][0], adjusted["pieces"][0]
        assert q["x"] + adjusted["applied_trim_width_cm"] == pytest.approx(p["x"])
        assert q["y"] + adjusted["applied_trim_length_cm"] == pytest.approx(p["y"])


def test_fixed_dxf_rejects_material_inside_less_than_the_requested_minimum():
    from almdina_erp.almdina_erp.domain.cutting.dxf_applied_trim import (
        apply_adaptive_trim_to_fixed_dxf_layout,
    )

    # The uploaded layout is fixed; 1.995 mm cannot satisfy a 5 mm minimum.
    from almdina_erp.almdina_erp.domain.cutting.dxf_applied_trim import DxfAppliedTrimError
    with pytest.raises(DxfAppliedTrimError):
        apply_adaptive_trim_to_fixed_dxf_layout(
            _fixed_dxf_snapshot((1.995, 10)), preferred_trim_mm=5,
        )


@pytest.mark.parametrize("usable_mm,x_mm,expected_trim,invalid", [
    (1220, -2, 0, True),
    (1220, 0, 0, False),
    (1210, -2, 0.5, False),
])
def test_saved_historical_frame_matches_export_without_mutating_plan(
    usable_mm, x_mm, expected_trim, invalid, monkeypatch, tmp_path,
):
    import json
    from copy import deepcopy
    from almdina_erp.tests.test_dxf_special_export_validation import _saved_plan
    from almdina_erp.almdina_erp.services import export_validation_service as export

    plan, order, piece, _ = _saved_plan(piece_type="Regular", width_cm=30, length_cm=40)
    plan.sources[0].full_width_mm = plan.full_board_width_mm = 1220
    plan.sources[0].full_length_mm = plan.full_board_length_mm = 2440
    plan.sources[0].usable_width_mm = plan.usable_board_width_mm = usable_mm
    plan.sources[0].usable_length_mm = plan.usable_board_length_mm = 2440
    plan.trim_margin_mm = 5
    piece.x_mm = x_mm
    stored = json.loads(plan.snapshot_json)
    stored["trim_cm"] = 0.5
    stored_piece = stored["sheets"][0]["pieces"][0]
    stored_piece.update(x=x_mm / 10, y=0, w=30, h=40)
    for point in stored_piece["geometry"]["outer"]:
        point[0] += x_mm
    plan.snapshot_json = json.dumps(stored)
    before = deepcopy(vars(plan))
    monkeypatch.setattr(export.frappe, "get_doc", lambda *args: order, raising=False)
    issues = export.validate_cutting_plan_issues(plan)
    assert ("PIECE_OUTSIDE_SHEET" in [i.code for i in issues]) is invalid
    rebuilt = export._plan_to_export_snapshot(plan)
    assert rebuilt["sheets"][0]["applied_trim_width_cm"] == expected_trim
    assert rebuilt["sheets"][0]["applied_trim_length_cm"] == 0
    assert rebuilt["sheets"][0]["pieces"][0]["x"] * 10 + expected_trim * 10 == pytest.approx(
        x_mm + expected_trim * 10,
    )
    assert vars(plan) == before
    if not invalid:
        import os
        import subprocess
        import ezdxf
        from almdina_erp.tests.test_cutter_center_paths import _layer_segments

        cases = tmp_path / "saved-frame.json"
        cases.write_text(json.dumps([rebuilt]))
        subprocess.run(
            ["node", str(ROOT / "tests/js/secure_dxf_topology_export.test.js")],
            check=True, capture_output=True, text=True,
            env=dict(os.environ, PERIMETER_CASES=str(cases), PERIMETER_OUTPUT_DIR=str(tmp_path)),
        )
        geometry = _layer_segments(ezdxf.readfile(tmp_path / "0.dxf"), "GEOMETRY")
        assert min(point[0] for segment in geometry for point in segment) == pytest.approx(
            x_mm + expected_trim * 10,
        )


def test_contradictory_source_frame_is_rejected_by_validator_and_export(monkeypatch):
    from almdina_erp.tests.test_dxf_special_export_validation import _saved_plan
    from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import DxfGeometrySnapshotError
    from almdina_erp.almdina_erp.services import export_validation_service as export

    plan, order, _, _ = _saved_plan(piece_type="Regular", width_cm=30, length_cm=40)
    plan.sources[0].usable_width_mm = plan.sources[0].full_width_mm + 1
    monkeypatch.setattr(export.frappe, "get_doc", lambda *args: order, raising=False)
    assert "CUT_INVALID_GEOMETRY" in [i.code for i in export.validate_cutting_plan_issues(plan)]
    with pytest.raises(DxfGeometrySnapshotError):
        export._plan_to_export_snapshot(plan)


def test_imported_plan_bounds_follow_each_sheet_usable_dimensions():
    from types import SimpleNamespace
    from almdina_erp.almdina_erp.services.dxf_import_service import validate_imported_plan_issues

    snapshot = _fixed_dxf_snapshot((10, 10), (10, 10))
    snapshot["usable_board_width_cm"] = 122
    snapshot["sheets"][0]["usable_width_cm"] = 121
    snapshot["sheets"][0]["pieces"][0].update(x=120.5, w=1)
    snapshot["sheets"][1]["pieces"][0].update(x=120.5, w=1)
    order = SimpleNamespace(pieces=[SimpleNamespace(qty=2, extra_full_door_double=0)])
    issues = validate_imported_plan_issues(snapshot, order)
    assert [i.code for i in issues].count("PIECE_OUTSIDE_SHEET") == 1


@pytest.mark.parametrize(
    "x_mm,explicit_trim,expected_invalid,missing_sheet_dimensions,plan_zero,offcut",
    [
        (-2, None, False, False, False, False),
        (-2, 0.0, True, False, False, False),
        (-6, None, True, False, False, False),
        (0, 0.0, False, False, False, False),
        # Legacy sheets can omit dimensions; recover them from persisted sources,
        # not from a plan-wide zero that loses an earlier per-sheet inset.
        (-2, None, False, True, True, False),
        # OFFCUT retains its established usable-frame boundary gate.
        (-2, None, True, False, False, True),
    ],
)
def test_saved_export_checks_physical_sheet_not_virtual_usable_frame(
    x_mm, explicit_trim, expected_invalid, missing_sheet_dimensions, plan_zero, offcut, monkeypatch,
):
    import json
    from types import SimpleNamespace
    from almdina_erp.almdina_erp.services import export_validation_service as export

    sheet = {
        "sheet_no": 1,
        "full_width_cm": 122,
        "full_length_cm": 244,
        "usable_width_cm": 121,
        "usable_length_cm": 243,
        "pieces": [],
    }
    if explicit_trim is not None:
        sheet["applied_trim_width_cm"] = explicit_trim
        sheet["applied_trim_length_cm"] = explicit_trim
    if missing_sheet_dimensions:
        for field in ("full_width_cm", "full_length_cm", "usable_width_cm", "usable_length_cm"):
            sheet.pop(field)
    snapshot = {"sheets": [sheet], "full_board_width_cm": 122,
                "full_board_length_cm": 244, "trim_cm": 0.5}
    if plan_zero:
        snapshot["applied_trim_width_cm"] = 0
        snapshot["applied_trim_length_cm"] = 0
    source = SimpleNamespace(
        sheet_no=1, source_type="Full Board", full_width_mm=1220,
        full_length_mm=2440, usable_width_mm=1210, usable_length_mm=2430,
        resource_kind="OFFCUT" if offcut else "FULL_BOARD",
    )
    placed = SimpleNamespace(
        sheet_no=1, piece_label="1-1", source_piece_no=1,
        copy_no=1, piece_id=1, x_mm=x_mm, y_mm=0,
        width_mm=200, height_mm=300,
    )
    plan = SimpleNamespace(
        door_cutting_order="fixture", sources=[source], placed_pieces=[placed],
        snapshot_json=json.dumps(snapshot), kerf_mm=5, plan_kind="Custom DXF",
    )
    monkeypatch.setattr(export.frappe, "get_doc", lambda *args: SimpleNamespace(), raising=False)
    monkeypatch.setattr(export.frappe, "parse_json", json.loads, raising=False)
    monkeypatch.setattr(export, "_validate_source_identity", lambda *args: [])
    monkeypatch.setattr(export, "validate_snapshot_material_layout", lambda *args, **kwargs: True)
    codes = [item.code for item in export.validate_cutting_plan_issues(plan)]
    assert ("PIECE_OUTSIDE_SHEET" in codes) is expected_invalid



def _write_adaptive_boundary_dxf(path, *, sheets_and_pieces, include_saw_centers=False):
    import ezdxf
    from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
        cutter_center_segments,
    )

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    overhanging_centers = []
    for offset_x, local_x, local_y in sheets_and_pieces:
        board = (offset_x, 0, offset_x + 1220, 2440)
        outer = [
            (offset_x + local_x, local_y),
            (offset_x + local_x + 200, local_y),
            (offset_x + local_x + 200, local_y + 300),
            (offset_x + local_x, local_y + 300),
        ]
        msp.add_lwpolyline(
            [(offset_x, 0), (offset_x + 1220, 0),
             (offset_x + 1220, 2440), (offset_x, 2440)],
            close=True, dxfattribs={"layer": "SHEET_OUTLINE"},
        )
        msp.add_lwpolyline(outer, close=True, dxfattribs={"layer": "GEOMETRY"})
        if include_saw_centers:
            segments = cutter_center_segments([(outer, ())], 2.5, board=board)
            overhanging_centers.extend(segments)
            for a, b in segments:
                msp.add_line(a, b, dxfattribs={"layer": "CUT_PATH"})
    doc.saveas(path)
    return overhanging_centers


def _strict_boundary_import(path, *, count):
    from unittest.mock import patch
    from almdina_erp.tests.test_dxf_manufacturing_identity import order_for
    from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
    from almdina_erp.almdina_erp.services import dxf_import_service as legacy
    from almdina_erp.almdina_erp.services import strict_dxf_import_service as strict

    order = order_for([(20, 30, count)])
    with patch.object(legacy.frappe, "get_site_path", return_value=str(path)):
        return strict.parse_production_dxf(
            "/private/files/physical-boundary.dxf",
            order,
            settings=PlanSettings("Auto", "CNC", 5, 5, 5),
        )


def test_strict_uploaded_dxf_retains_trim_per_sheet_through_real_parser(tmp_path):
    path = tmp_path / "two-physical-boards.dxf"
    _write_adaptive_boundary_dxf(
        path, sheets_and_pieces=[(0, 5, 5), (1400, 10, 10)],
    )
    snapshot = _strict_boundary_import(path, count=2)
    assert snapshot["saw_center_status"] == "Absent"
    assert [s["applied_trim_width_cm"] for s in snapshot["sheets"]] == pytest.approx([0.5, 0.5])
    assert [s["applied_trim_length_cm"] for s in snapshot["sheets"]] == pytest.approx([0.5, 0.5])


def test_import_persistence_adapter_reload_and_export_preserve_physical_positions(tmp_path, monkeypatch):
    """Exercise real adapters with JSON-backed child rows, without a site DB."""
    import json
    from types import SimpleNamespace
    from almdina_erp.tests.test_dxf_manufacturing_identity import order_for
    from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_workspace as workspace
    from almdina_erp.almdina_erp.domain.cutting.plan_settings import DEFAULT_MACHINE_TYPE
    from almdina_erp.almdina_erp.services import export_validation_service as export

    class MemoryPlan(SimpleNamespace):
        def set(self, key, value):
            setattr(self, key, value)

        def append(self, key, value):
            getattr(self, key).append(SimpleNamespace(
                **({"remnant": None, "board_item": "", "material": "", "color": "", "thickness_mm": 0} | value)
            ))

    class DefaultFields(SimpleNamespace):
        def __getattr__(self, key):
            return None

    path = tmp_path / "persisted-frames.dxf"
    _write_adaptive_boundary_dxf(path, sheets_and_pieces=[(0, 5, 5), (1400, 10, 10)])
    snapshot = _strict_boundary_import(path, count=2)
    order = order_for([(20, 30, 2)])
    order.pieces = [DefaultFields(**vars(row)) for row in order.pieces]
    order.name = "FRAME-ROUND-TRIP"
    order.board_description = ""
    plan = MemoryPlan(
        door_cutting_order=order.name, plan_kind="Custom DXF", board_item="",
        source_type="Uploaded DXF", trim_margin_mm=5, kerf_mm=5, machine_type=DEFAULT_MACHINE_TYPE,
    )
    monkeypatch.setattr(workspace.frappe, "as_json", json.dumps, raising=False)
    workspace.apply_validated_dxf_snapshot(order, plan, snapshot)
    # Rehydrate exactly the scalar/child data produced by the persistence adapter.
    saved_json = json.dumps(vars(plan), default=vars)
    reloaded = json.loads(saved_json, object_hook=lambda row: SimpleNamespace(**row))
    monkeypatch.setattr(export.frappe, "get_doc", lambda *args: order, raising=False)
    assert export.validate_cutting_plan_issues(reloaded) == []
    rebuilt = export._plan_to_export_snapshot(reloaded)
    for original, result in zip(snapshot["sheets"], rebuilt["sheets"]):
        for axis, trim_key in (("x", "applied_trim_width_cm"), ("y", "applied_trim_length_cm")):
            assert result[trim_key] == pytest.approx(original[trim_key])
            assert result["pieces"][0][axis] + result[trim_key] == pytest.approx(
                original["pieces"][0][axis] + original[trim_key],
            )
    assert reloaded.snapshot_json == plan.snapshot_json
    assert reloaded.input_fingerprint == plan.input_fingerprint


@pytest.mark.parametrize("with_saw_paths", [False, True])
def test_uploaded_material_inside_requested_margin_is_rejected_even_with_safe_saw_centers(
    tmp_path, with_saw_paths,
):
    path = tmp_path / "near-boundary.dxf"
    centers = _write_adaptive_boundary_dxf(
        path, sheets_and_pieces=[(0, 1, 10)],
        include_saw_centers=with_saw_paths,
    )
    if with_saw_paths:
        assert min(p[0] for segment in centers for p in segment) == pytest.approx(-1.5)
    with pytest.raises(DxfImportError) as error:
        _strict_boundary_import(path, count=1)
    assert "APPLIED_TRIM_OVERFLOW" in error.value.codes



def test_strict_dxf_rejects_finished_material_outside_physical_board(tmp_path):
    path = tmp_path / "outside-material.dxf"
    _write_adaptive_boundary_dxf(path, sheets_and_pieces=[(0, -1, 10)])
    with pytest.raises(DxfImportError) as error:
        _strict_boundary_import(path, count=1)
    assert "PIECE_OUTSIDE_SHEET" in error.value.codes
