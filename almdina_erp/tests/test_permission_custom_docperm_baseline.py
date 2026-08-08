from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


REPOSITORY_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "permission_matrix_repository.py"
)


class Row(dict):
    __getattr__ = dict.get


class Field:
    def __init__(self, fieldname: str) -> None:
        self.fieldname = fieldname


PERMISSION_FIELDS = (
    "role",
    "permlevel",
    "if_owner",
    "read",
    "write",
    "create",
    "delete",
    "report",
    "print",
    "email",
    "view_costs",
)


class Meta:
    def __init__(self, fields: tuple[str, ...]) -> None:
        self.fields = [Field(fieldname) for fieldname in fields]
        self._fieldnames = frozenset(fields)

    def has_field(self, fieldname: str) -> bool:
        return fieldname in self._fieldnames


class Document(Row):
    def __init__(self, payload: dict[str, Any], inserted: list[dict[str, Any]]) -> None:
        super().__init__(payload)
        self.meta = Meta(PERMISSION_FIELDS)
        self._inserted = inserted

    def insert(self, ignore_permissions: bool = False) -> "Document":
        self._inserted.append(dict(self))
        return self


class FakeDatabase:
    def __init__(self, harness: "RepositoryHarness") -> None:
        self.harness = harness

    def exists(self, doctype: str, filters: dict[str, Any]) -> bool:
        if doctype != "Custom DocPerm":
            return False
        return any(
            all(row.get(key) == value for key, value in filters.items())
            for row in self.harness.custom_rows
        )


class RepositoryHarness:
    def __init__(
        self,
        *,
        standard_rows: list[dict[str, Any]],
        custom_rows: list[dict[str, Any]],
    ) -> None:
        self.standard_rows = [Row(row) for row in standard_rows]
        self.custom_rows = [Row(row) for row in custom_rows]
        self.inserted: list[dict[str, Any]] = []
        self.setup_calls: list[str] = []

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        return all(row.get(key) == value for key, value in (filters or {}).items())

    def get_all(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        fields: list[str] | str | None = None,
        **_kwargs: Any,
    ) -> list[Row]:
        source = self.standard_rows if doctype == "DocPerm" else self.custom_rows
        return [Row(row) for row in source if self._matches(row, filters)]

    def get_doc(self, doctype: str | dict[str, Any], name: str | None = None) -> Document:
        if isinstance(doctype, dict):
            return Document(dict(doctype), self.inserted)
        if doctype != "DocPerm" or not name:
            raise AssertionError((doctype, name))
        row = next(row for row in self.standard_rows if row["name"] == name)
        return Document(dict(row), self.inserted)

    def load_repository(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.db = FakeDatabase(self)
        fake_frappe.get_all = self.get_all
        fake_frappe.get_doc = self.get_doc
        fake_frappe.get_meta = lambda _doctype: Meta(PERMISSION_FIELDS)

        permissions = types.ModuleType("frappe.permissions")
        permissions.setup_custom_perms = self.setup_calls.append

        previous_frappe = sys.modules.get("frappe")
        previous_permissions = sys.modules.get("frappe.permissions")
        sys.modules["frappe"] = fake_frappe
        sys.modules["frappe.permissions"] = permissions
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_permission_baseline_test_repository",
                REPOSITORY_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load permission repository")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.FrappePermissionMatrixRepository()
        finally:
            if previous_frappe is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = previous_frappe
            if previous_permissions is None:
                sys.modules.pop("frappe.permissions", None)
            else:
                sys.modules["frappe.permissions"] = previous_permissions


def standard_row(name: str, role: str) -> dict[str, Any]:
    return {
        "name": name,
        "parent": "Door Cutting Order",
        "role": role,
        "permlevel": 0,
        "if_owner": 0,
        "read": 1,
        "write": 0,
        "create": 0,
        "delete": 0,
        "report": 1,
        "print": 1,
        "email": 0,
        # Simulate a polluted historical business Permission Type field.
        "view_costs": 1,
    }


class TestPermissionCustomDocPermBaseline(unittest.TestCase):
    def test_partial_custom_overrides_copy_native_rights_but_not_business_grants(self) -> None:
        harness = RepositoryHarness(
            standard_rows=[
                standard_row("STD-ENTRY", "Order Entry"),
                standard_row("STD-REVIEW", "Review Role"),
            ],
            custom_rows=[
                {
                    **standard_row("CUSTOM-ENTRY", "Order Entry"),
                    "name": "CUSTOM-ENTRY",
                }
            ],
        )
        repository = harness.load_repository()

        repository.ensure_custom_permission_baseline(["Door Cutting Order"])

        self.assertEqual(len(harness.inserted), 1)
        copied = harness.inserted[0]
        self.assertEqual(copied["role"], "Review Role")
        self.assertEqual(copied["read"], 1)
        self.assertEqual(copied["report"], 1)
        self.assertEqual(copied["print"], 1)
        self.assertEqual(copied["view_costs"], 0)

    def test_first_customization_uses_frappe_complete_baseline_setup(self) -> None:
        harness = RepositoryHarness(
            standard_rows=[standard_row("STD-ENTRY", "Order Entry")],
            custom_rows=[],
        )
        repository = harness.load_repository()

        repository.ensure_custom_permission_baseline(["Door Cutting Order"])

        self.assertEqual(harness.setup_calls, ["Door Cutting Order"])
        self.assertEqual(harness.inserted, [])

    def test_repository_source_never_reads_docperm_as_business_authority(self) -> None:
        source = REPOSITORY_PATH.read_text(encoding="utf-8")
        role_state = source[source.index("    def role_state("):source.index("    def role_states(")]
        self.assertIn("self._canonical.read", role_state)
        self.assertNotIn("Custom DocPerm", role_state)
        self.assertNotIn("DocPerm", role_state)
        self.assertNotIn("_effective_rows", source)


if __name__ == "__main__":
    unittest.main()
