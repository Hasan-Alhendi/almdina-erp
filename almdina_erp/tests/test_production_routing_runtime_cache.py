from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "production_routing_repository.py"
)


class _FakeDatabase:
    def __init__(self) -> None:
        self.exists_calls = 0

    def exists(self, doctype: str, name: str) -> bool:
        self.exists_calls += 1
        return doctype == "Production Routing" and name == "Drawing"


class TestProductionRoutingRuntimeCache(unittest.TestCase):
    def _load_repository(self, *, disabled: int = 0):
        database = _FakeDatabase()
        get_doc_calls = {"count": 0}

        stage = types.SimpleNamespace(
            sequence=10,
            stage_type="Drawing",
            department_label="رسم",
            operational_role="عامل رسم",
            is_planning_stage=1,
            required=1,
        )
        document = types.SimpleNamespace(
            name="Drawing",
            routing_name="الرسم",
            disabled=disabled,
            stages=[stage],
        )

        frappe_module = types.ModuleType("frappe")
        frappe_module.local = types.SimpleNamespace()
        frappe_module.db = database

        def get_doc(doctype: str, name: str):
            self.assertEqual(doctype, "Production Routing")
            self.assertEqual(name, "Drawing")
            get_doc_calls["count"] += 1
            return document

        frappe_module.get_doc = get_doc
        frappe_module.get_all = lambda *args, **kwargs: []

        utils_module = types.ModuleType("frappe.utils")
        utils_module.cint = lambda value: int(value or 0)

        spec = importlib.util.spec_from_file_location(
            "_almdina_test_production_routing_repository",
            REPOSITORY_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {"frappe": frappe_module, "frappe.utils": utils_module},
        ):
            spec.loader.exec_module(module)

        return module, frappe_module, database, get_doc_calls

    def test_same_route_is_loaded_once_within_one_frappe_request(self) -> None:
        repository, _, database, get_doc_calls = self._load_repository()

        first = repository.get_route("Drawing")
        second = repository.get_route("Drawing")

        self.assertIs(first, second)
        self.assertEqual(database.exists_calls, 1)
        self.assertEqual(get_doc_calls["count"], 1)

    def test_new_frappe_local_context_reloads_route_from_database(self) -> None:
        repository, frappe_module, database, get_doc_calls = self._load_repository()

        repository.get_route("Drawing")
        frappe_module.local = types.SimpleNamespace()
        repository.get_route("Drawing")

        self.assertEqual(database.exists_calls, 2)
        self.assertEqual(get_doc_calls["count"], 2)

    def test_disabled_policy_is_reapplied_without_reloading_projection(self) -> None:
        repository, _, database, get_doc_calls = self._load_repository(disabled=1)

        route = repository.get_route("Drawing", require_enabled=False)
        self.assertEqual(route.name, "Drawing")
        with self.assertRaisesRegex(ValueError, "معطّل"):
            repository.get_route("Drawing", require_enabled=True)

        self.assertEqual(database.exists_calls, 1)
        self.assertEqual(get_doc_calls["count"], 1)

    def test_empty_route_fails_before_touching_database(self) -> None:
        repository, _, database, get_doc_calls = self._load_repository()

        with self.assertRaisesRegex(ValueError, "<فارغ>"):
            repository.get_route("  ")

        self.assertEqual(database.exists_calls, 0)
        self.assertEqual(get_doc_calls["count"], 0)


if __name__ == "__main__":
    unittest.main()
