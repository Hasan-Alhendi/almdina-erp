"""Public diagnostics must retain evidence without changing manufacturing decisions."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    DxfTopologyError, PartGeometry, PlacedPartGeometry, validate_material_layout,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    KERF_VIOLATION, contour_pair_target, issue, topology_error_to_issue,
)
from almdina_erp.almdina_erp.services import dxf_import_service as importer
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
    present_target, present_issue,
)


def rectangle(x, width=100):
    return ((x, 0), (x + width, 0), (x + width, 100), (x, 100))


def test_clearance_failure_retains_measured_distance_in_native_units():
    with pytest.raises(DxfTopologyError) as error:
        validate_material_layout(
            (PlacedPartGeometry(71, PartGeometry(rectangle(0))),
             PlacedPartGeometry(77, PartGeometry(rectangle(103)))),
            required_clearance=5,
        )
    assert error.value.code == "PART_CLEARANCE_VIOLATION"
    assert error.value.actual_clearance == pytest.approx(3)
    assert error.value.required_clearance == 5
    mapped = topology_error_to_issue(error.value, kerf_mm=5, geometry_unit_mm=1)
    assert mapped.params["actual_clearance_mm"] == pytest.approx(3)


def test_missing_measurement_is_not_reported_as_zero():
    mapped = topology_error_to_issue(DxfTopologyError("PART_CLEARANCE_VIOLATION"), kerf_mm=5)
    assert "actual_clearance_mm" not in mapped.params


def test_layout_target_preserves_sheet_and_two_copies_of_one_door():
    error = DxfTopologyError("PART_CLEARANCE_VIOLATION", first_key=71, second_key=77)
    mapped = topology_error_to_issue(
        error, kerf_mm=5, sheet_no=3, pair_identity_proven=True,
        pair_source_piece_nos=(15, 15), pair_copy_nos=(1, 2),
    )
    assert mapped.target.sheet_no == 3
    assert mapped.target.pair_copy_nos == (1, 2)
    label = present_target(mapped.target)
    assert "15" in label and "1" in label and "2" in label and "3" in label
    assert "71" not in label and "77" not in label


def test_early_spacing_preserves_sheet_measurement_and_does_not_mutate_input():
    pieces = [
        dict(id=71, _sheet_no=3, _outline_mm=rectangle(0), _holes_mm=[]),
        dict(id=77, _sheet_no=3, _outline_mm=rectangle(103), _holes_mm=[]),
    ]
    before = deepcopy(pieces)
    with pytest.raises(importer.DxfImportError) as error:
        importer._validate_piece_spacing(pieces, kerf_mm=5)
    diagnostic = error.value.issues[0]
    assert diagnostic.target.sheet_no == 3
    assert diagnostic.target.pair_contour_nos == (71, 77)
    assert diagnostic.params["actual_clearance_mm"] == pytest.approx(3)
    assert pieces == before


def test_public_response_excludes_debug_and_keeps_original_exception():
    from almdina_erp.almdina_erp.infrastructure.frappe.error_response import attach_error_response
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import public_dxf_issues

    item = issue(KERF_VIOLATION, "LAYOUT", target=contour_pair_target(71, 77),
                 params={"kerf_mm": 5, "password": "secret"},
                 debug={"sql": "secret table"})
    response = {}
    with patch.object(importer.frappe, "local", SimpleNamespace(response=response)):
        with patch.object(importer.frappe, "logger", create=True) as logger:
            attach_error_response(operation="dxf_upload", title="Validation", issues=public_dxf_issues([item]), outcome="rejected")
    envelope = response["almdina_error"]
    assert envelope["schema_version"] == 1
    assert envelope["outcome"] == "rejected"
    assert envelope["issues"][0]["code"] == KERF_VIOLATION
    assert "secret" not in str(envelope)
    assert envelope["request_reference"]
    logger.assert_called_once()


def test_logging_failure_cannot_replace_the_business_error():
    from almdina_erp.almdina_erp.infrastructure.frappe.error_response import attach_error_response
    response = {}
    with patch.object(importer.frappe, "local", SimpleNamespace(response=response)):
        with patch.object(importer.frappe, "logger", side_effect=RuntimeError("unavailable"), create=True):
            attach_error_response(operation="dxf_upload", title="Validation", issues=[], outcome="rejected")
    assert response["almdina_error"]["request_reference"] is None


@pytest.mark.parametrize("parser", ["legacy", "strict"])
def test_near_sized_doors_with_a_real_clearance_failure_have_proven_identity(tmp_path, parser):
    import ezdxf
    from almdina_erp.tests.test_dxf_manufacturing_identity import order_for, parse

    path = tmp_path / "clearance.dxf"
    document = ezdxf.new("R2010")
    model = document.modelspace()
    model.add_lwpolyline([(0, 0), (1220, 0), (1220, 2440), (0, 2440)], close=True, dxfattribs={"layer": "SHEET_OUTLINE"})
    for x, y, height in [(10, 10, 310), (611, 10, 308), (10, 400, 310)]:
        model.add_lwpolyline([(x, y), (x + 598, y), (x + 598, y + height), (x, y + height)], close=True, dxfattribs={"layer": "CUT_PATH"})
    # Misleading drawing text must not become manufacturing identity.
    model.add_text("999.999", dxfattribs={"layer": "TEXT", "insert": (300, 200)})
    document.saveas(path)
    order = order_for([(59.8, 31, 2), (59.8, 30.8, 1)])
    original = deepcopy(vars(order))
    with pytest.raises(importer.DxfImportError) as rejected:
        parse(path, order, parser)
    diagnostic = rejected.value.issues[0]
    assert diagnostic.code == KERF_VIOLATION
    assert diagnostic.target.sheet_no == 1
    assert set(diagnostic.target.pair_piece_nos) == {1, 2}
    assert diagnostic.target.pair_copy_nos is not None
    assert diagnostic.params["actual_clearance_mm"] == pytest.approx(3)
    assert len(diagnostic.params["layout_preview"]["paths"]) == 2
    assert vars(order) == original


def test_identity_enrichment_failure_keeps_original_layout_rejection():
    pieces = [dict(id=i, _sheet_no=1, _outline_mm=rectangle(x), _holes_mm=[]) for i, x in [(71, 0), (77, 103)]]
    failure = importer.DxfImportError(issues=[issue(KERF_VIOLATION, "LAYOUT", target=contour_pair_target(71, 77))])
    with patch.object(importer, "_identify_imported_pieces", side_effect=RuntimeError("unexpected private detail")):
        diagnosed = importer._diagnose_layout_failure(failure, pieces, None, (), [], 0, validate_regular_machining=False)
    assert diagnosed.codes == [KERF_VIOLATION]
    assert diagnosed.issues[0].target.pair_contour_nos == (71, 77)
    assert diagnosed.issues[0].target.pair_piece_nos is None
    assert "private detail" not in str(diagnosed.issues)


def test_preview_rejects_nonfinite_over_budget_and_script_geometry():
    from almdina_erp.almdina_erp.domain.cutting.layout_diagnostics import public_layout_preview
    from almdina_erp.almdina_erp.presentation.cutting.dxf_layout_preview import render_layout_preview

    valid = {"paths": [[rectangle(0)], [rectangle(103)]]}
    assert public_layout_preview(valid)
    assert "<svg" in render_layout_preview(valid)
    assert not render_layout_preview({"paths": [[[("<script>", 0)] * 3], [rectangle(0)]]})
    assert not public_layout_preview({"paths": [[[(float("nan"), 0)] * 3], [rectangle(0)]]})
    assert not public_layout_preview({"paths": [[[point for _ in range(200) for point in rectangle(0)]], [rectangle(0)]]})


def test_export_retains_board_measurement_and_same_door_copies():
    from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import serialize_geometry_mm
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors

    snapshot = {"kerf_cm": .5, "sheets": [{"sheet_no": 3, "pieces": [
        {"id": 71, "label": "15.1", "source_piece_no": 15, "copy_no": 1,
         "geometry": serialize_geometry_mm(PartGeometry(rectangle(0)))},
        {"id": 77, "label": "15.2", "source_piece_no": 15, "copy_no": 2,
         "geometry": serialize_geometry_mm(PartGeometry(rectangle(103)))},
    ]}]}
    diagnostic = _kerf_errors(snapshot)[0]
    assert diagnostic.code == KERF_VIOLATION
    assert diagnostic.target.sheet_no == 3
    assert diagnostic.target.pair_piece_nos == (15, 15)
    assert diagnostic.target.pair_copy_nos == (1, 2)
    assert diagnostic.params["actual_clearance_mm"] == pytest.approx(3)


def test_identity_diagnosis_budget_never_rejects_or_reidentifies_large_orders():
    pieces = [dict(id=i, _sheet_no=1, _outline_mm=rectangle(i * 103), _holes_mm=[]) for i in range(201)]
    failure = importer.DxfImportError(issues=[issue(KERF_VIOLATION, "LAYOUT", target=contour_pair_target(0, 1))])
    with patch.object(importer, "_identify_imported_pieces") as identity:
        result = importer._diagnose_layout_failure(failure, pieces, None, (), [], 0, validate_regular_machining=False)
    identity.assert_not_called()
    assert result.codes == failure.codes
    assert result.issues[0].target.pair_piece_nos is None
    assert result.issues[0].params["layout_preview"]


def test_unexpected_exception_is_logged_safely_and_original_type_is_preserved():
    from almdina_erp.almdina_erp.infrastructure.frappe.error_response import record_unexpected_errors

    @record_unexpected_errors("dxf_upload")
    def fail():
        raise RuntimeError("private SQL or credentials")

    response = {}
    with patch.object(importer.frappe, "local", SimpleNamespace(response=response)):
        with patch.object(importer.frappe, "logger", create=True):
            with pytest.raises(RuntimeError, match="private SQL"):
                fail()
    assert response["almdina_error"]["issues"][0]["code"] == "UNEXPECTED_ERROR"
    assert response["almdina_error"]["outcome"] == "unknown"
    assert "private SQL" not in str(response)
