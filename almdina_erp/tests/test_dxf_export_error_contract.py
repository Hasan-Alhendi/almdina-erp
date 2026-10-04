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
    PLAN_UNPLACED_PIECES,
    PLAN_VALIDATION_FAILED,
    TARGET_CONTOUR_PAIR,
    TARGET_PIECE_PAIR,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import DxfTopologyError
from almdina_erp.almdina_erp.services import dxf_export_service, export_validation_service
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
    present_issue,
    present_issues_as_strings,
    render_error_cards_html,
)


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


def test_strict_editable_snapshot_uses_neutral_issue_for_legacy_validation_errors():
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
                {
                    "validation": {
                        "is_valid": False,
                        "errors": ["legacy geometry detail", "legacy bounds detail"],
                    },
                    "unplaced": ["piece-1"],
                }
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
    validation_failures = [item for item in captured["issues"] if item.code == PLAN_VALIDATION_FAILED]
    assert len(validation_failures) == 1
    assert validation_failures[0].debug["legacy_validation_errors"] == [
        "legacy geometry detail",
        "legacy bounds detail",
    ]
    assert validation_failures[0].code != CUT_INVALID_GEOMETRY
    assert [item.code for item in captured["issues"]].count(PLAN_UNPLACED_PIECES) == 1
    card = present_issue(captured["issues"][0])
    assert card.problem == "خطة القص الحالية غير صالحة للتصدير."
    assert card.target == "خطة القص."
    assert card.action == "أعد حساب الخطة ثم حاول التصدير مرة أخرى."
    assert "legacy geometry detail" not in " ".join((card.problem, card.target, card.action))


def _validate_plan_pair_identity(first_source_no, second_source_no):
    plan = SimpleNamespace(
        door_cutting_order="DCO-TEST",
        sources=[],
        placed_pieces=[],
        snapshot_json=json.dumps(
            {
                "sheets": [
                    {
                        "pieces": [
                            {"id": "a", "label": "a", "source_piece_no": first_source_no},
                            {"id": "b", "label": "b", "source_piece_no": second_source_no},
                        ]
                    }
                ]
            }
        ),
        kerf_mm=5,
        plan_kind="Remnant",
    )
    topology_error = DxfTopologyError(
        "MATERIAL_FOOTPRINT_OVERLAP", first_key="a", second_key="b"
    )
    with (
        patch.object(
            export_validation_service.frappe,
            "get_doc",
            return_value=SimpleNamespace(),
            create=True,
        ),
        patch.object(
            export_validation_service,
            "validate_snapshot_material_layout",
            side_effect=topology_error,
        ),
    ):
        return export_validation_service.validate_cutting_plan_issues(plan)


def test_plan_topology_pair_with_proven_piece_identity_is_piece_pair():
    issues = _validate_plan_pair_identity(3, 7)
    overlap = next(item for item in issues if item.code == MATERIAL_OVERLAP)
    assert overlap.target.kind == TARGET_PIECE_PAIR
    assert overlap.target.pair_piece_nos == (3, 7)
    assert present_issue(overlap).target == "الدرفتان 3 و7."


def test_plan_topology_pair_with_same_source_identity_stays_contour_pair():
    issues = _validate_plan_pair_identity(3, 3)
    overlap = next(item for item in issues if item.code == MATERIAL_OVERLAP)
    assert overlap.target.kind == TARGET_CONTOUR_PAIR
    assert overlap.target.pair_contour_nos == ("a", "b")
    assert "الدرفة" not in present_issue(overlap).target


def test_legacy_and_card_presentations_use_where_is_the_problem_label():
    from almdina_erp.almdina_erp.domain.cutting.dxf_issue import issue

    item = issue(CUT_INVALID_GEOMETRY, "CONTOUR")
    legacy = present_issues_as_strings([item])[0]
    cards = render_error_cards_html([item], context="export")
    assert "أين المشكلة؟" in legacy
    assert "أي موضع؟" not in legacy
    assert "أين المشكلة؟" in cards
    assert "أي موضع؟" not in cards
