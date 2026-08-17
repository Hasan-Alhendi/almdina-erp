from __future__ import annotations

import copy

import frappe
import pytest

from almdina_erp.almdina_erp.services.special_shape_drawing_validation_service import (
    validate_special_shape_drawing,
)


def _rectangle_document() -> dict:
    return {
        "schema": "almdina.door-drawing",
        "version": 4,
        "units": "mm",
        "blank": {"widthMm": 600, "heightMm": 1200},
        "nodes": [
            {"id": "n1", "xMm": 0, "yMm": 0},
            {"id": "n2", "xMm": 600, "yMm": 0},
            {"id": "n3", "xMm": 600, "yMm": 1200},
            {"id": "n4", "xMm": 0, "yMm": 1200},
        ],
        "segments": [
            {"id": "s1", "type": "line", "startNodeId": "n1", "endNodeId": "n2"},
            {"id": "s2", "type": "line", "startNodeId": "n2", "endNodeId": "n3"},
            {"id": "s3", "type": "line", "startNodeId": "n3", "endNodeId": "n4"},
            {"id": "s4", "type": "line", "startNodeId": "n4", "endNodeId": "n1"},
        ],
        "paths": [
            {
                "id": "p1",
                "startNodeId": "n1",
                "segmentIds": ["s1", "s2", "s3", "s4"],
                "closed": True,
            }
        ],
    }


def test_v4_drawing_document_is_accepted():
    drawing = _rectangle_document()
    assert validate_special_shape_drawing(drawing) == drawing


def test_v4_drawing_accepts_segment_length_dimension():
    drawing = _rectangle_document()
    drawing["dimensions"] = [
        {"id": "d1", "type": "segment-length", "segmentId": "s1"}
    ]
    assert validate_special_shape_drawing(drawing) == drawing


def test_v4_drawing_rejects_dimension_with_missing_segment():
    drawing = _rectangle_document()
    drawing["dimensions"] = [
        {"id": "d1", "type": "segment-length", "segmentId": "missing"}
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_duplicate_length_dimensions_for_segment():
    drawing = _rectangle_document()
    drawing["dimensions"] = [
        {"id": "d1", "type": "segment-length", "segmentId": "s1"},
        {"id": "d2", "type": "segment-length", "segmentId": "s1"},
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_accepts_constraint_foundation():
    drawing = _rectangle_document()
    drawing["constraints"] = [
        {"id": "c1", "type": "horizontal", "segmentId": "s1"},
        {"id": "c2", "type": "vertical", "segmentId": "s2"},
        {
            "id": "c3",
            "type": "fixed-length",
            "segmentId": "s1",
            "valueMm": 600,
            "anchorNodeId": "n1",
        },
    ]
    assert validate_special_shape_drawing(drawing) == drawing


def test_v4_drawing_rejects_constraint_with_missing_segment():
    drawing = _rectangle_document()
    drawing["constraints"] = [
        {"id": "c1", "type": "horizontal", "segmentId": "missing"}
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_duplicate_constraint_for_segment():
    drawing = _rectangle_document()
    drawing["constraints"] = [
        {"id": "c1", "type": "horizontal", "segmentId": "s1"},
        {"id": "c2", "type": "horizontal", "segmentId": "s1"},
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_conflicting_axis_constraints():
    drawing = _rectangle_document()
    drawing["constraints"] = [
        {"id": "c1", "type": "horizontal", "segmentId": "s1"},
        {"id": "c2", "type": "vertical", "segmentId": "s1"},
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_unsatisfied_axis_constraint():
    drawing = _rectangle_document()
    drawing["constraints"] = [
        {"id": "c1", "type": "horizontal", "segmentId": "s2"}
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_invalid_fixed_length_anchor():
    drawing = _rectangle_document()
    drawing["constraints"] = [
        {
            "id": "c1",
            "type": "fixed-length",
            "segmentId": "s1",
            "valueMm": 750,
            "anchorNodeId": "n3",
        }
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_non_positive_fixed_length():
    drawing = _rectangle_document()
    drawing["constraints"] = [
        {
            "id": "c1",
            "type": "fixed-length",
            "segmentId": "s1",
            "valueMm": 0,
            "anchorNodeId": "n1",
        }
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_unsatisfied_fixed_length():
    drawing = _rectangle_document()
    drawing["constraints"] = [
        {
            "id": "c1",
            "type": "fixed-length",
            "segmentId": "s1",
            "valueMm": 750,
            "anchorNodeId": "n1",
        }
    ]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_missing_node_reference():
    drawing = _rectangle_document()
    drawing["segments"][1]["endNodeId"] = "missing"
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_disconnected_path():
    drawing = _rectangle_document()
    drawing["paths"][0]["segmentIds"] = ["s1", "s3", "s2", "s4"]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_false_closed_flag():
    drawing = _rectangle_document()
    drawing["segments"][-1]["endNodeId"] = "n2"
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_drawing_rejects_duplicate_global_entity_ids():
    drawing = _rectangle_document()
    drawing["segments"][0]["id"] = drawing["nodes"][0]["id"]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(drawing)


def test_v4_validation_does_not_mutate_document():
    drawing = _rectangle_document()
    drawing["dimensions"] = [
        {"id": "d1", "type": "segment-length", "segmentId": "s1"}
    ]
    drawing["constraints"] = [
        {"id": "c1", "type": "horizontal", "segmentId": "s1"}
    ]
    before = copy.deepcopy(drawing)
    validate_special_shape_drawing(drawing)
    assert drawing == before
