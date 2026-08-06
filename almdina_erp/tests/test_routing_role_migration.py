from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "patches" / "v1_0" / "migrate_routing_stage_eligible_roles.py"


class _FakeMeta:
    @staticmethod
    def has_field(fieldname: str) -> bool:
        return fieldname in {
            "operational_role",
            "eligible_roles_json",
            "eligible_roles_display",
        }


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


class _FakeFrappe(types.ModuleType):
    def __init__(self, rows: list[dict[str, object]]):
        super().__init__("frappe")
        self.rows = rows
        self.writes: list[tuple[str, str, dict[str, object], bool]] = []
        self.db = _FakeDatabase(self)

    @staticmethod
    def get_meta(doctype: str) -> _FakeMeta:
        return _FakeMeta()

    def get_all(self, doctype: str, **kwargs):
        return [dict(row) for row in self.rows]


def _load_patch(fake_frappe: _FakeFrappe):
    module_name = "almdina_test_routing_role_migration"
    spec = importlib.util.spec_from_file_location(module_name, PATCH_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": fake_frappe}):
        assert spec and spec.loader
        spec.loader.exec_module(module)
    return module


class TestRoutingRoleMigration(unittest.TestCase):
    def test_malformed_json_is_repaired_from_the_historical_link(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-1",
                    "operational_role": "Night CNC",
                    "eligible_roles_json": "{broken",
                    "eligible_roles_display": "stale",
                }
            ]
        )
        module = _load_patch(fake)

        module._migrate("Production Routing Stage")

        self.assertEqual(len(fake.writes), 1)
        doctype, name, values, update_modified = fake.writes[0]
        self.assertEqual(doctype, "Production Routing Stage")
        self.assertEqual(name, "ROW-1")
        self.assertEqual(json.loads(values["eligible_roles_json"]), ["Night CNC"])
        self.assertEqual(values["eligible_roles_display"], "Night CNC")
        self.assertEqual(values["operational_role"], "Night CNC")
        self.assertFalse(update_modified)

    def test_normalized_snapshot_is_idempotent(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-1",
                    "operational_role": "CNC Supervisor",
                    "eligible_roles_json": '["CNC Supervisor","Night CNC"]',
                    "eligible_roles_display": "CNC Supervisor، Night CNC",
                }
            ]
        )
        module = _load_patch(fake)

        module._migrate("Production Stage")
        module._migrate("Production Stage")

        self.assertEqual(fake.writes, [])

    def test_empty_sources_do_not_invent_a_role(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-1",
                    "operational_role": "",
                    "eligible_roles_json": "",
                    "eligible_roles_display": "",
                }
            ]
        )
        module = _load_patch(fake)

        module._migrate("Production Stage")

        self.assertEqual(fake.writes, [])


if __name__ == "__main__":
    unittest.main()
