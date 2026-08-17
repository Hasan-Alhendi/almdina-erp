from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PROFILER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "hot_query_profiler.py"
)


class _FakeDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object], bool]] = []

    def sql(self, query, values=None, *, as_dict=False):
        self.calls.append((str(query), list(values or []), as_dict))
        return [
            {
                "table": "ps",
                "type": "ALL",
                "possible_keys": None,
                "key": None,
                "key_len": None,
                "ref": None,
                "rows": 250,
                "filtered": 10.0,
                "Extra": "Using where; Using filesort",
            }
        ]


class TestHotQueryProfiler(unittest.TestCase):
    def _load_profiler(self):
        database = _FakeDatabase()
        frappe_module = types.ModuleType("frappe")
        frappe_module.db = database

        spec = importlib.util.spec_from_file_location(
            "_almdina_test_hot_query_profiler",
            PROFILER_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"frappe": frappe_module}):
            spec.loader.exec_module(module)
        return module, database

    def test_profiles_only_fixed_explain_select_statements(self) -> None:
        profiler, database = self._load_profiler()

        result = profiler.profile_hot_queries(
            user="worker@example.com",
            order_names=["DCO-2026-00001", "DCO-2026-00002"],
        )

        self.assertTrue(result["read_only"])
        self.assertEqual(result["profiled_query_count"], 5)
        self.assertEqual(result["order_sample_size"], 2)
        self.assertEqual(len(database.calls), 5)
        for query, _, as_dict in database.calls:
            normalized = query.strip().lower()
            self.assertTrue(normalized.startswith("explain select "))
            self.assertNotIn("alter table", normalized)
            self.assertNotIn("create index", normalized)
            self.assertNotIn("drop index", normalized)
            self.assertTrue(as_dict)

    def test_runtime_parameters_never_become_sql_text(self) -> None:
        profiler, database = self._load_profiler()
        actor = "worker'@example.com"
        order_name = "DCO-2026-00001' OR 1=1 --"

        profiler.profile_hot_queries(
            user=actor,
            order_names=[order_name],
        )

        rendered_sql = "\n".join(query for query, _, _ in database.calls)
        self.assertNotIn(actor, rendered_sql)
        self.assertNotIn(order_name, rendered_sql)
        self.assertIn(actor, [value for _, values, _ in database.calls for value in values])
        self.assertIn(order_name, [value for _, values, _ in database.calls for value in values])

    def test_plan_output_surfaces_evidence_without_auto_recommending_indexes(self) -> None:
        profiler, _ = self._load_profiler()

        result = profiler.profile_hot_queries(user="worker@example.com")
        self.assertEqual(result["profiled_query_count"], 4)
        self.assertEqual(result["order_sample_size"], 0)
        first_plan = result["profiles"][0]["plan"][0]
        self.assertEqual(first_plan["access_type"], "ALL")
        self.assertEqual(first_plan["estimated_rows"], 250)
        self.assertIn("full_scan", first_plan["risk_flags"])
        self.assertIn("no_selected_key", first_plan["risk_flags"])
        self.assertIn("filesort", first_plan["risk_flags"])
        self.assertNotIn("recommended_index", first_plan)

    def test_order_sample_is_bounded(self) -> None:
        profiler, database = self._load_profiler()

        with self.assertRaisesRegex(ValueError, "at most 100"):
            profiler.profile_hot_queries(
                user="worker@example.com",
                order_names=[f"DCO-{index}" for index in range(101)],
            )

        self.assertEqual(database.calls, [])

    def test_profiler_is_not_exposed_as_whitelisted_http_method(self) -> None:
        source = PROFILER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("@frappe.whitelist", source)
        self.assertNotIn("allow_guest", source)
        self.assertNotIn("ALTER TABLE", source)
        self.assertNotIn("CREATE INDEX", source)
        self.assertNotIn("DROP INDEX", source)


if __name__ == "__main__":
    unittest.main()
