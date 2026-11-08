"""Guard against recurring User-table writes during migrations."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
MEMBERSHIP = ROOT / "almdina_erp/infrastructure/frappe/workforce_membership.py"
LIFECYCLE = ROOT / "lifecycle.py"
PATCH = ROOT / "patches/v1_0/backfill_legacy_workforce_membership.py"
PATCH_LINE = "almdina_erp.patches.v1_0.backfill_legacy_workforce_membership"
FIELD = "custom_almdina_workforce_member"


def _isolated_functions(frappe, create_custom_fields):
    """Run the actual functions without importing database-backed Frappe."""
    tree = ast.parse(MEMBERSHIP.read_text(encoding="utf-8"))
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "sync_workforce_membership_metadata",
            "backfill_legacy_workforce_membership",
        }
    ]
    if len(selected) != 2:
        raise AssertionError("Both membership functions must exist")
    namespace = {
        "frappe": frappe,
        "create_custom_fields": create_custom_fields,
        "MEMBERSHIP_FIELD": FIELD,
        "LEGACY_ALMDINA_APP": "almdina_erp",
        "cint": lambda value: int(value or 0),
    }
    code = compile(ast.Module(body=selected, type_ignores=[]), str(MEMBERSHIP), "exec")
    exec(code, namespace)
    return namespace


class TestWorkforceMembershipMigration(unittest.TestCase):
    def test_metadata_sync_never_writes_user_rows(self):
        frappe = Mock()
        frappe.db.exists.return_value = True
        create_fields = Mock()
        functions = _isolated_functions(frappe, create_fields)

        functions["sync_workforce_membership_metadata"]()

        create_fields.assert_called_once()
        frappe.get_all.assert_not_called()
        frappe.db.set_value.assert_not_called()
        frappe.clear_cache.assert_called_once_with(doctype="User")

    def test_one_time_backfill_updates_only_unmarked_existing_users(self):
        frappe = Mock()
        frappe.db.exists.return_value = True
        frappe.get_all.side_effect = [
            ["already", "new", "Administrator"],
            ["audited", "removed-from-db"],
            [
                {"name": "already", FIELD: 1},
                {"name": "new", FIELD: 0},
                {"name": "audited", FIELD: None},
            ],
            ["already", "new", "Administrator"],
            ["audited", "removed-from-db"],
            [
                {"name": "already", FIELD: 1},
                {"name": "new", FIELD: 1},
                {"name": "audited", FIELD: 1},
            ],
        ]
        functions = _isolated_functions(frappe, Mock())

        self.assertEqual(functions["backfill_legacy_workforce_membership"](), 2)
        self.assertEqual(
            [call.args[:3] for call in frappe.db.set_value.call_args_list],
            [("User", "new", FIELD), ("User", "audited", FIELD)],
        )
        self.assertEqual(functions["backfill_legacy_workforce_membership"](), 0)
        self.assertEqual(frappe.db.set_value.call_count, 2)
        self.assertEqual(frappe.clear_cache.call_count, 1)

    def test_backfill_occurs_only_in_registered_patch(self):
        self.assertIn(PATCH_LINE, (ROOT / "patches.txt").read_text(encoding="utf-8"))
        lifecycle = LIFECYCLE.read_text(encoding="utf-8")
        patch = PATCH.read_text(encoding="utf-8")
        self.assertIn("sync_workforce_membership_metadata()", lifecycle)
        self.assertNotIn("backfill_legacy_workforce_membership", lifecycle)
        self.assertIn("backfill_legacy_workforce_membership()", patch)
        self.assertIn("sync_workforce_membership_metadata()", patch)


if __name__ == "__main__":
    unittest.main()
