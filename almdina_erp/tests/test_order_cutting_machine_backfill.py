from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EMPTY_PATCH_PATH = ROOT / "patches" / "v1_0" / "backfill_order_cutting_machine.py"
NULL_PATCH_PATH = ROOT / "patches" / "v1_0" / "null_legacy_order_cutting_machine.py"
PATCHES = ROOT / "patches.txt"
CONTROLLER = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_controller.py"
)


class FakeDB:
    def __init__(self, *, has_column: bool = True) -> None:
        self.has_column_flag = has_column
        self.sql_calls: list[str] = []
        self.rows = {
            "old-empty": "",
            "old-null": None,
            "already-cnc": "CNC",
            "mashraha": "مشرحة",
        }

    def has_column(self, doctype: str, column: str) -> bool:
        return self.has_column_flag and doctype == "Door Cutting Order" and column == "order_cutting_machine"

    def sql(self, query: str, *args, **kwargs):
        normalized = " ".join(query.split())
        self.sql_calls.append(normalized)
        empty_only = "ifnull(order_cutting_machine, '') = ''" in normalized
        nonempty_only = "ifnull(order_cutting_machine, '') != ''" in normalized
        for name, value in list(self.rows.items()):
            is_empty = not str(value or "").strip()
            if empty_only and is_empty:
                self.rows[name] = None
            elif nonempty_only and not is_empty:
                self.rows[name] = None


def _load_patch(path: Path, db: FakeDB, module_name: str):
    frappe = types.ModuleType("frappe")
    frappe.db = db
    sys.modules["frappe"] = frappe
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestOrderCuttingMachineBackfill(unittest.TestCase):
    def tearDown(self) -> None:
        sys.modules.pop("frappe", None)

    def test_patches_are_registered_after_model_sync(self) -> None:
        patches = PATCHES.read_text(encoding="utf-8")
        empty_module = "almdina_erp.patches.v1_0.backfill_order_cutting_machine"
        null_module = "almdina_erp.patches.v1_0.null_legacy_order_cutting_machine"
        pre, post = patches.split("[post_model_sync]", 1)

        self.assertNotIn(empty_module, pre)
        self.assertNotIn(null_module, pre)
        self.assertIn(empty_module, post)
        self.assertIn(null_module, post)
        self.assertLess(post.index(empty_module), post.index(null_module))
        self.assertTrue(EMPTY_PATCH_PATH.is_file())
        self.assertTrue(NULL_PATCH_PATH.is_file())

    def test_legacy_orders_are_cleared_to_null_without_inventing_cnc(self) -> None:
        empty_source = EMPTY_PATCH_PATH.read_text(encoding="utf-8")
        null_source = NULL_PATCH_PATH.read_text(encoding="utf-8")

        self.assertIn("order_cutting_machine = NULL", empty_source)
        self.assertIn("ifnull(order_cutting_machine, '') = ''", empty_source)
        self.assertNotIn("= 'CNC'", empty_source)
        self.assertIn("order_cutting_machine = NULL", null_source)
        self.assertIn("ifnull(order_cutting_machine, '') != ''", null_source)

        db = FakeDB()
        empty_patch = _load_patch(EMPTY_PATCH_PATH, db, "empty_order_cutting_machine_under_test")
        empty_patch.execute()
        self.assertIsNone(db.rows["old-empty"])
        self.assertIsNone(db.rows["old-null"])
        self.assertEqual(db.rows["already-cnc"], "CNC")
        self.assertEqual(db.rows["mashraha"], "مشرحة")

        null_patch = _load_patch(NULL_PATCH_PATH, db, "null_order_cutting_machine_under_test")
        null_patch.execute()
        self.assertEqual(
            db.rows,
            {
                "old-empty": None,
                "old-null": None,
                "already-cnc": None,
                "mashraha": None,
            },
        )

        first_pass = dict(db.rows)
        empty_patch.execute()
        null_patch.execute()
        self.assertEqual(db.rows, first_pass)

    def test_missing_column_is_a_no_op(self) -> None:
        db = FakeDB(has_column=False)
        empty_patch = _load_patch(EMPTY_PATCH_PATH, db, "empty_order_cutting_machine_missing")
        null_patch = _load_patch(NULL_PATCH_PATH, db, "null_order_cutting_machine_missing")

        empty_patch.execute()
        null_patch.execute()
        self.assertEqual(db.sql_calls, [])
        self.assertEqual(db.rows["old-empty"], "")
        self.assertEqual(db.rows["already-cnc"], "CNC")

    def test_server_validate_does_not_require_order_cutting_machine(self) -> None:
        source = CONTROLLER.read_text(encoding="utf-8")
        validate = source.split("def validate(self) -> None:", 1)[1].split("def before_insert", 1)[0]
        self.assertNotIn("order_cutting_machine", validate)
        self.assertNotIn("order_cutting_machine", source)


if __name__ == "__main__":
    unittest.main()
