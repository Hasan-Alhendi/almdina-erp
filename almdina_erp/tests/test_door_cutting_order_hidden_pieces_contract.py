from __future__ import annotations

import json
import unittest
from pathlib import Path


DOCTYPE_JSON = Path(
    "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order.json"
)
CONTROLLER = Path(
    "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order.py"
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
        source = CONTROLLER.read_text(encoding="utf-8")

        self.assertIn("def _validate_piece_inputs(self) -> None:", source)
        self.assertIn("if not self.pieces:", source)
        self.assertIn('frappe.throw(_("At least one piece row is required."))', source)
        self.assertIn("self._validate_piece_inputs()", source)


if __name__ == "__main__":
    unittest.main()
