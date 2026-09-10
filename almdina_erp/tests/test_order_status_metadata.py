from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "order_status_metadata.py"
)


class StatusMetadataHarness:
    def __init__(self) -> None:
        self.stage_rows = [
            SimpleNamespace(stage_label="الرسم"),
            SimpleNamespace(stage_label="CNC"),
            SimpleNamespace(stage_label="الرسم"),
            SimpleNamespace(stage_label=""),
        ]
        self.in_flight_rows = [("التقشيط",), ("CNC",), ("",)]
        self.set_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.cache_clears: list[str | None] = []
        self.get_all_calls: list[tuple[str, dict[str, Any]]] = []
        self.docfield_name = "status-docfield"
        self.kanban_enabled = False
        self.kanban_boards: dict[str, Any] = {}

    def load(self):
        fake_frappe = types.ModuleType("frappe")

        def exists(doctype: str, filters: Any = None) -> bool:
            if doctype == "DocType":
                return filters != "Kanban Board" or self.kanban_enabled
            if doctype == "Production Stage Definition":
                return True
            return False

        def get_value(doctype: str, filters: Any, fieldname: str, **_kwargs: Any) -> Any:
            if doctype == "DocField" and fieldname == "name":
                return self.docfield_name
            return None

        def sql(_query: str, *_args: Any, **_kwargs: Any) -> list[tuple[str]]:
            return list(self.in_flight_rows)

        def set_value(*args: Any, **kwargs: Any) -> None:
            self.set_calls.append((args, kwargs))

        fake_frappe.db = SimpleNamespace(
            exists=exists,
            get_value=get_value,
            sql=sql,
            set_value=set_value,
        )

        def get_all(doctype: str, **kwargs: Any) -> list[Any]:
            self.get_all_calls.append((doctype, kwargs))
            if doctype == "Kanban Board":
                return list(self.kanban_boards)
            return list(self.stage_rows)

        fake_frappe.get_all = get_all
        fake_frappe.get_doc = lambda doctype, name: self.kanban_boards[name]
        fake_frappe.clear_cache = lambda doctype=None: self.cache_clears.append(doctype)

        previous = sys.modules.get("frappe")
        sys.modules["frappe"] = fake_frappe
        try:
            spec = importlib.util.spec_from_file_location("_order_status_metadata_test", MODULE_PATH)
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load order_status_metadata.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            if previous is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = previous


class FakeKanbanBoard:
    def __init__(self, columns: list[tuple[str, str]]) -> None:
        self.columns = [
            SimpleNamespace(column_name=name, indicator=indicator, order="[]")
            for name, indicator in columns
        ]
        self.saved = False

    def set(self, fieldname: str, value: list[Any]) -> None:
        self.columns = list(value)

    def append(self, fieldname: str, value: dict[str, Any]) -> None:
        self.columns.append(SimpleNamespace(**value))

    def save(self, **kwargs: Any) -> None:
        self.saved = True


class TestOrderStatusMetadata(unittest.TestCase):
    def test_build_options_uses_active_library_labels_and_runtime_snapshots(self) -> None:
        harness = StatusMetadataHarness()
        metadata = harness.load()

        options = metadata.build_order_status_options()

        self.assertEqual(
            options,
            (
                "Draft",
                "الرسم",
                "CNC",
                "التقشيط",
                "Delivered",
                "Cancelled",
            ),
        )
        self.assertEqual(len(harness.get_all_calls), 1)
        doctype, kwargs = harness.get_all_calls[0]
        self.assertEqual(doctype, "Production Stage Definition")
        self.assertEqual(kwargs["filters"], {"disabled": 0})
        self.assertEqual(kwargs["fields"], ["stage_label"])

    def test_sync_materializes_options_and_invalidates_doctype_cache(self) -> None:
        harness = StatusMetadataHarness()
        metadata = harness.load()

        options = metadata.sync_order_status_options()

        self.assertTrue(options)
        self.assertEqual(len(harness.set_calls), 1)
        args, kwargs = harness.set_calls[0]
        self.assertEqual(args[0:3], ("DocField", harness.docfield_name, "options"))
        self.assertEqual(args[3], "\n".join(options))
        self.assertFalse(kwargs["update_modified"])
        self.assertEqual(harness.cache_clears, ["Door Cutting Order"])

    def test_sync_replaces_persisted_kanban_columns_and_removes_legacy_values(self) -> None:
        harness = StatusMetadataHarness()
        harness.kanban_enabled = True
        board = FakeKanbanBoard([
            ("Completed", "Green"),
            ("At Drawing", "Blue"),
            ("Draft", "Gray"),
        ])
        harness.kanban_boards["Orders"] = board
        metadata = harness.load()

        options = metadata.sync_order_status_options()

        self.assertTrue(board.saved)
        self.assertEqual(
            [column.column_name for column in board.columns],
            list(options),
        )
        self.assertNotIn("Completed", [column.column_name for column in board.columns])
        self.assertNotIn("At Drawing", [column.column_name for column in board.columns])
        self.assertEqual(
            next(column.indicator for column in board.columns if column.column_name == "Draft"),
            "Gray",
        )

    def test_sync_is_safe_when_status_docfield_is_missing(self) -> None:
        harness = StatusMetadataHarness()
        harness.docfield_name = ""
        metadata = harness.load()

        self.assertEqual(metadata.sync_order_status_options(), ())
        self.assertEqual(harness.set_calls, [])
        self.assertEqual(harness.cache_clears, [])


if __name__ == "__main__":
    unittest.main()
