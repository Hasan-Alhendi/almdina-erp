from __future__ import annotations

import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCTYPE_JSON = (
    REPOSITORY_ROOT
    / "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order.json"
)
DOCUMENT_ACCESS = (
    REPOSITORY_ROOT
    / "almdina_erp/almdina_erp/infrastructure/frappe/orders/document_access.py"
)
SAVE_USE_CASE = (
    REPOSITORY_ROOT
    / "almdina_erp/almdina_erp/application/orders/process_order_save.py"
)
SAVE_GATEWAY = (
    REPOSITORY_ROOT
    / "almdina_erp/almdina_erp/infrastructure/frappe/orders/save_gateway.py"
)


class HiddenPiecesContractTests(unittest.TestCase):
    def test_hidden_table_is_not_schema_mandatory(self) -> None:
        definition = json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))
        pieces = next(
            field for field in definition["fields"] if field.get("fieldname") == "pieces"
        )

        self.assertEqual(pieces.get("fieldtype"), "Table")
        self.assertEqual(pieces.get("hidden"), 1)
        self.assertNotEqual(pieces.get("reqd"), 1)

    def test_business_requirement_remains_enforced_on_server(self) -> None:
        access = DOCUMENT_ACCESS.read_text(encoding="utf-8")
        gateway = SAVE_GATEWAY.read_text(encoding="utf-8")
        use_case = SAVE_USE_CASE.read_text(encoding="utf-8")

        self.assertIn("def validate_piece_inputs(self) -> None:", access)
        self.assertIn("if not self.document.pieces:", access)
        self.assertIn('frappe.throw(_("At least one piece row is required."))', access)
        self.assertIn("self.access.validate_piece_inputs()", gateway)
        self.assertIn("gateway.validate_piece_inputs()", use_case)


if __name__ == "__main__":
    unittest.main()
