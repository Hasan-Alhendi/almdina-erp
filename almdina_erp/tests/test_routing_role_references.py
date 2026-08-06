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
        self.db = _FakeDatabase(self)

    def get_meta(self, doctype: str) -> _FakeMeta:
        return self.meta

    def get_all(self, doctype: str, **kwargs):
        requested = kwargs.get("fields") or []
        return [
            {field: row.get(field) for field in requested}
            for row in self.rows
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

    def test_rename_updates_all_snapshot_fields_and_deduplicates(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-1",
                    "eligible_roles_json": json.dumps(
                        ["Primary", "Old Role", "New Role"]
                    ),
                    "eligible_roles_display": "Primary، Old Role، New Role",
                    "operational_role": "Primary",
                }
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
        self.assertEqual(
            json.loads(fake.rows[0]["eligible_roles_json"]),
            ["Primary", "New Role"],
        )
        self.assertEqual(
            fake.rows[0]["eligible_roles_display"],
            "Primary، New Role",
        )
        self.assertEqual(fake.rows[0]["operational_role"], "Primary")
        self.assertFalse(fake.writes[0][3])

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


if __name__ == "__main__":
    unittest.main()
