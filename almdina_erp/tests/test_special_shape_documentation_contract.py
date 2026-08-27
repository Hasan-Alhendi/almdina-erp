from __future__ import annotations

import copy

import frappe
import pytest

from almdina_erp.almdina_erp.services.special_shape_drawing_validation_service import (
    DOCUMENTATION_SCHEMA,
    validate_special_shape_drawing,
)


def _documentation() -> dict:
    return {
        "schema": DOCUMENTATION_SCHEMA,
        "version": 1,
        "canvas": {"widthMm": 800, "heightMm": 2100},
        "reference": {
            "fileUrl": "/private/files/sample.jpg",
            "rotationDeg": 0,
            "opacity": 0.72,
            "locked": True,
        },
        "elements": [
            {
                "id": "dimension-1",
                "type": "dimension",
                "start": {"xMm": 0, "yMm": 0},
                "end": {"xMm": 800, "yMm": 0},
                "valueMm": 800,
                "unit": "mm",
            },
            {
                "id": "note-1",
                "type": "text",
                "position": {"xMm": 300, "yMm": 200},
                "text": "قوس علوي حسب العينة",
            },
        ],
        "notes": "مطابقة القوس مع العينة المرفقة",
        "source": "mixed",
        "templateId": "top-arch",
    }


def test_documentation_with_private_reference_and_elements_is_accepted():
    documentation = _documentation()
    assert validate_special_shape_drawing(documentation) == documentation


def test_image_only_documentation_is_accepted():
    documentation = _documentation()
    documentation["elements"] = []
    assert validate_special_shape_drawing(documentation) == documentation


def test_non_destructive_reference_crop_is_accepted():
    documentation = _documentation()
    documentation["reference"].update({
        "crop": {"x": 0.2, "y": 0.15, "width": 0.55, "height": 0.7},
        "imageSize": {"widthPx": 2480, "heightPx": 3508},
    })
    assert validate_special_shape_drawing(documentation) == documentation


@pytest.mark.parametrize(
    "crop",
    [
        {"x": -0.1, "y": 0, "width": 0.5, "height": 0.5},
        {"x": 0.8, "y": 0, "width": 0.3, "height": 0.5},
        {"x": 0, "y": 0, "width": 0.01, "height": 0.5},
    ],
)
def test_invalid_reference_crop_is_rejected(crop):
    documentation = _documentation()
    documentation["reference"]["crop"] = crop
    documentation["reference"]["imageSize"] = {"widthPx": 2480, "heightPx": 3508}
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(documentation)


def test_cropped_reference_requires_original_image_dimensions():
    documentation = _documentation()
    documentation["reference"]["crop"] = {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(documentation)


def test_element_only_documentation_is_accepted():
    documentation = _documentation()
    documentation["reference"] = None
    assert validate_special_shape_drawing(documentation) == documentation


@pytest.mark.parametrize("schema", ["almdina.door-drawing", "", None])
def test_old_or_missing_editor_schema_is_rejected(schema):
    documentation = _documentation()
    documentation["schema"] = schema
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(documentation)


def test_public_or_foreign_reference_url_is_rejected():
    documentation = _documentation()
    documentation["reference"]["fileUrl"] = "/files/sample.jpg"
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(documentation)


def test_empty_documentation_is_rejected():
    documentation = _documentation()
    documentation["reference"] = None
    documentation["elements"] = []
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(documentation)


def test_invalid_element_type_and_duplicate_id_are_rejected():
    documentation = _documentation()
    documentation["elements"][0]["type"] = "manufacturing-path"
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(documentation)

    documentation = _documentation()
    documentation["elements"][1]["id"] = documentation["elements"][0]["id"]
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(documentation)


def test_validator_does_not_mutate_documentation():
    documentation = _documentation()
    before = copy.deepcopy(documentation)
    validate_special_shape_drawing(documentation)
    assert documentation == before


def test_dictionary_payload_is_subject_to_the_global_size_limit():
    documentation = _documentation()
    documentation["elements"][0]["metadata"] = "x" * (2 * 1024 * 1024)
    with pytest.raises(frappe.ValidationError):
        validate_special_shape_drawing(documentation)
