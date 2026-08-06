from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "routing_role_references.py"
)


class _FakeMeta:
    def __init__(self, fields: set[str]):
        self.fields = fields

    def has_field(self, fieldname: str) -> bool:
        return fieldname in self.fields


class _FakeDatabase:
    def __init__(self, owner: "_FakeFrappe"):
        self.owner = owner

    @staticmethod
    def exists(doctype: str, name: str) -> bool:
        return doctype == "DocType" and bool(name)

    def sql(self, query: str, values=()):
        self.owner.sql_calls.append((query, tuple(values or ())))
        return []

    def set_value(
        self,
        doctype: str,
        name: str,
        values: dict[str, object],
        *,
        update_modified: bool,
    ) -> None:
        self.owner.writes.append((doctype, name, dict(values), update_modified))
        row = next(item for item in self.owner.rows if item["name"] == name)
        row.update(values)


class _FakeFrappe(types.ModuleType):
    def __init__(self, rows: list[dict[str, object]], fields: set[str]):
        super().__init__("frappe")
        self.rows = rows
        self.meta = _FakeMeta(fields)
        self.writes: list[tuple[str, str, dict[str, object], bool]] = []
        self.sql_calls: list[tuple[str, tuple[object, ...]]] = []
        self.db = _FakeDatabase(self)

    def get_meta(self, doctype: str) -> _FakeMeta:
        return self.meta

    def get_all(self, doctype: str, **kwargs):
        requested = kwargs.get("fields") or []
        rows = list(self.rows)
        filters = kwargs.get("filters") or {}
        name_filter = filters.get("name") if isinstance(filters, dict) else None
        if isinstance(name_filter, list) and len(name_filter) == 2 and name_filter[0] == "in":
            allowed = set(name_filter[1])
            rows = [row for row in rows if row.get("name") in allowed]
        if kwargs.get("order_by") == "name asc":
            rows.sort(key=lambda row: str(row.get("name") or ""))
        return [
            {field: row.get(field) for field in requested}
            for row in rows
        ]


def _load_module(fake_frappe: _FakeFrappe):
    module_name = "almdina_test_routing_role_references"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": fake_frappe}):
        assert spec and spec.loader
        spec.loader.exec_module(module)
    return module


class TestRoutingRoleReferences(unittest.TestCase):
    FIELDS = {
        "eligible_roles_json",
        "eligible_roles_display",
        "operational_role",
    }

    def test_count_finds_roles_anywhere_in_the_json_set(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-1",
                    "eligible_roles_json": json.dumps(["First", "Target"]),
                    "operational_role": "First",
                }
            ],
            self.FIELDS,
        )
        module = _load_module(fake)

        counts = module.configured_role_counts(
            "Production Routing Stage",
            ["Target", "Missing"],
        )

        self.assertEqual(counts, {"Target": 1})
        self.assertEqual(fake.sql_calls, [])

    def test_rename_locks_then_updates_all_snapshot_fields(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-2",
                    "eligible_roles_json": json.dumps(["Unrelated"]),
                    "eligible_roles_display": "Unrelated",
                    "operational_role": "Unrelated",
                },
                {
                    "name": "ROW-1",
                    "eligible_roles_json": json.dumps(
                        ["Primary", "Old Role", "New Role"]
                    ),
                    "eligible_roles_display": "Primary، Old Role، New Role",
                    "operational_role": "Primary",
                },
            ],
            self.FIELDS,
        )
        module = _load_module(fake)

        changed = module.rename_configured_role_references(
            "Production Routing Stage",
            "Old Role",
            "New Role",
        )

        self.assertEqual(changed, 1)
        updated = next(row for row in fake.rows if row["name"] == "ROW-1")
        self.assertEqual(
            json.loads(updated["eligible_roles_json"]),
            ["Primary", "New Role"],
        )
        self.assertEqual(updated["eligible_roles_display"], "Primary، New Role")
        self.assertEqual(updated["operational_role"], "Primary")
        self.assertFalse(fake.writes[0][3])
        self.assertEqual(len(fake.sql_calls), 1)
        query, values = fake.sql_calls[0]
        self.assertIn("for update", query.lower())
        self.assertIn("order by name", query.lower())
        self.assertEqual(values, ("ROW-1",))

    def test_malformed_json_uses_and_repairs_the_legacy_role(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-1",
                    "eligible_roles_json": "{broken",
                    "eligible_roles_display": "Old Role",
                    "operational_role": "Old Role",
                }
            ],
            self.FIELDS,
        )
        module = _load_module(fake)

        counts = module.configured_role_counts(
            "Production Stage",
            ["Old Role"],
        )
        changed = module.rename_configured_role_references(
            "Production Stage",
            "Old Role",
            "New Role",
        )

        self.assertEqual(counts, {"Old Role": 1})
        self.assertEqual(changed, 1)
        self.assertEqual(
            json.loads(fake.rows[0]["eligible_roles_json"]),
            ["New Role"],
        )
        self.assertEqual(fake.rows[0]["operational_role"], "New Role")

    def test_dynamic_table_names_are_rejected_by_allowlist(self) -> None:
        fake = _FakeFrappe([], self.FIELDS)
        module = _load_module(fake)

        with self.assertRaisesRegex(ValueError, "Unsupported role snapshot"):
            module.rename_configured_role_references(
                "Role; drop table tabUser",
                "Old",
                "New",
            )
        self.assertEqual(fake.sql_calls, [])
        self.assertEqual(fake.writes, [])


if __name__ == "__main__":
    unittest.main()
