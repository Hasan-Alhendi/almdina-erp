from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "almdina_erp" / "almdina_erp" / "services" / "special_shape_reference_image_service.py"
DETAIL = ROOT / "almdina_erp" / "almdina_erp" / "doctype" / "door_cutting_order_detail" / "door_cutting_order_detail.json"
PAGE = ROOT / "almdina_erp" / "almdina_erp" / "page" / "door_drawing" / "door_drawing.js"


class TestSpecialShapeReferenceImageArchitecture(unittest.TestCase):
    def test_reference_fields_are_schema_owned(self) -> None:
        payload = json.loads(DETAIL.read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in payload["fields"]}
        self.assertIn("special_shape_reference_image", fields)
        self.assertIn("special_shape_reference_image_meta_json", fields)
        self.assertEqual(fields["special_shape_reference_image"]["fieldtype"], "Attach Image")
        self.assertTrue(fields["special_shape_reference_image"]["read_only"])

    def test_service_is_capability_and_stage_guarded(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("Capability.EDIT_SPECIAL_DRAWING", source)
        self.assertIn("require_document_capability", source)
        self.assertIn("require_stage_operational_access", source)
        self.assertIn("assert_order_editable", source)
        self.assertNotIn("ignore_permissions", source)
        self.assertNotIn("order.save(", source)

    def test_reference_image_never_mutates_exact_geometry_or_plan(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("special_shape_drawing_json", source)
        self.assertNotIn("special_shape_geometry_json", source)
        self.assertNotIn("plan_needs_recalculation", source)
        self.assertNotIn("calculated_plan_input_hash", source)
        self.assertNotIn("reset_price_values", source)
        self.assertIn('"Door Cutting Order Detail"', source)
        self.assertIn("is_private=1", source)

    def test_page_loads_reference_pipeline_before_workspace_controller(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        domain = source.index('/reference/domain.js')
        cropper = source.index('/reference/cropper.js')
        scanner = source.index('/reference/scanner_bridge.js')
        controller = source.index('/reference/reference_controller.js')
        workspace = source.index('/professional/workspace_controller.js')
        self.assertLess(domain, cropper)
        self.assertLess(cropper, scanner)
        self.assertLess(scanner, controller)
        self.assertLess(controller, workspace)
        self.assertIn("door_drawing_reference.css", source)


if __name__ == "__main__":
    unittest.main()
