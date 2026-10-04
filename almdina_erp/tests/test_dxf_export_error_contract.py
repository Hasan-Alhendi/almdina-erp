from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CUT_INVALID_GEOMETRY,
    KERF_VIOLATION,
    MATERIAL_OVERLAP,
    TARGET_CONTOUR_PAIR,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import DxfTopologyError
from almdina_erp.almdina_erp.services import dxf_export_service, export_validation_service


def _rect_snapshot(second_x_cm: float) -> dict:
    return {
        "kerf_cm": 0.5,
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {"id": 1, "label": "1.1", "x": 0, "y": 0, "w": 10, "h": 10},
                    {"id": 2, "label": "2.1", "x": second_x_cm, "y": 0, "w": 10, "h": 10},
                ],
            }
        ],
    }


def test_export_kerf_validation_returns_structured_issue_and_keeps_clearance_rule():
    issues = dxf_export_service._kerf_errors(_rect_snapshot(10.2))
    assert len(issues) == 1
    assert issues[0].code == KERF_VIOLATION
    assert issues[0].target.kind == TARGET_CONTOUR_PAIR
    assert issues[0].target.pair_contour_nos == ("1.1", "2.1")

    # The existing 5 mm pass/fail boundary remains unchanged.
    assert dxf_export_service._kerf_errors(_rect_snapshot(10.5)) == []

    with pytest.raises(ValueError) as exc_info:
        dxf_export_service._assert_export_kerf(_rect_snapshot(10.2))
    assert "المسافة بين مساري القص أقل من Kerf" in str(exc_info.value)
    assert "أعد تصدير DXF" in str(exc_info.value)
    assert "لم يتم استبدال خطة DXF" not in str(exc_info.value)


def test_export_topology_errors_reuse_existing_overlap_code():
    snapshot = _rect_snapshot(10.5)
    error = DxfTopologyError(
        "MATERIAL_FOOTPRINT_OVERLAP",
        first_key="1.1",
        second_key="2.1",
    )
    with patch.object(
        dxf_export_service,
        "validate_snapshot_material_layout",
        side_effect=error,
    ):
        issues = dxf_export_service._kerf_errors(snapshot)

    assert len(issues) == 1
    assert issues[0].code == MATERIAL_OVERLAP
    assert issues[0].target.kind == TARGET_CONTOUR_PAIR


def test_strict_editable_snapshot_wraps_geometry_failures_as_export_issues():
    class EditableOrder:
        name = "DCO-TEST"
        status = "Draft"
        cutting_plan_json = ""
        pieces = []

        def is_new(self):
            return False

        def check_permission(self, _permission):
            return None

        def _set_piece_numbers(self):
            pass

        def _validate_numeric_inputs(self):
            pass

        def _validate_piece_inputs(self):
            pass

        def _validate_special_shape_rows(self):
            pass

        def _load_board_snapshot(self):
            pass

        def _calculate_piece_rows(self):
            pass

        def _get_settings(self):
            return SimpleNamespace()

        def _plan_input_fingerprint(self, _settings):
            return "fingerprint"

        def _calculate_cutting_plan(self, _settings, _fingerprint):
            self.cutting_plan_json = json.dumps(
                {"validation": {"is_valid": False, "errors": ["legacy geometry detail"]}}
            )

    captured = {}

    def capture_issues(issues, *, context):
        captured["issues"] = issues
        captured["context"] = context
        raise RuntimeError("captured")

    with (
        patch.object(export_validation_service.frappe, "get_doc", return_value=EditableOrder(), create=True),
        patch(
            "almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter.render_error_cards_html",
            side_effect=capture_issues,
        ),
        pytest.raises(RuntimeError, match="captured"),
    ):
        export_validation_service._strict_editable_snapshot({"name": "DCO-TEST"})

    assert captured["context"] == "export"
    assert captured["issues"][0].code == CUT_INVALID_GEOMETRY
