from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "patches" / "v1_0" / "normalize_executable_routing_stages.py"


class _FakeMeta:
    def __init__(self, fields: set[str]):
        self.fields = fields

    def has_field(self, fieldname: str) -> bool:
        return fieldname in self.fields


class _FakeDatabase:
    def __init__(self, owner: "_FakeFrappe", *, doctype_exists: bool):
        self.owner = owner
        self.doctype_exists = doctype_exists

    def exists(self, doctype: str, name: str) -> bool:
        return doctype == "DocType" and self.doctype_exists and bool(name)

    def set_value(
        self,
        doctype: str,
        name: str,
        values: dict[str, int],
        *,
        update_modified: bool,
    ) -> None:
        self.owner.writes.append((doctype, name, dict(values), update_modified))


class _FakeFrappe(types.ModuleType):
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        fields: set[str],
        doctype_exists: bool = True,
    ):
        super().__init__("frappe")
        self.rows = rows
        self.meta = _FakeMeta(fields)
        self.writes: list[tuple[str, str, dict[str, int], bool]] = []
        self.db = _FakeDatabase(self, doctype_exists=doctype_exists)

    def get_meta(self, doctype: str) -> _FakeMeta:
        return self.meta

    def get_all(self, doctype: str, **kwargs):
        return [dict(row) for row in self.rows]


def _load_patch(fake_frappe: _FakeFrappe):
    module_name = "almdina_test_executable_routing_stage_migration"
    spec = importlib.util.spec_from_file_location(module_name, PATCH_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": fake_frappe}):
        assert spec and spec.loader
        spec.loader.exec_module(module)
    return module


class TestExecutableRoutingStageMigration(unittest.TestCase):
    FIELDS = {"required", "auto_complete_if_not_applicable"}

    def test_old_optional_flags_are_normalized(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-1",
                    "required": 0,
                    "auto_complete_if_not_applicable": 1,
                }
            ],
            fields=self.FIELDS,
        )
        module = _load_patch(fake)

        module.execute()

        self.assertEqual(
            fake.writes,
            [
                (
                    "Production Routing Stage",
                    "ROW-1",
                    {"required": 1, "auto_complete_if_not_applicable": 0},
                    False,
                )
            ],
        )

    def test_normalized_rows_are_idempotent(self) -> None:
        fake = _FakeFrappe(
            [
                {
                    "name": "ROW-1",
                    "required": 1,
                    "auto_complete_if_not_applicable": 0,
                }
            ],
            fields=self.FIELDS,
        )
        module = _load_patch(fake)

        module.execute()
        module.execute()

        self.assertEqual(fake.writes, [])

    def test_missing_schema_is_a_safe_noop(self) -> None:
        fake = _FakeFrappe(
            [],
            fields=set(),
            doctype_exists=False,
        )
        module = _load_patch(fake)

        module.execute()

        self.assertEqual(fake.writes, [])


if __name__ == "__main__":
    unittest.main()
