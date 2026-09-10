from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "v1_0" / "migrate_production_stage_library.py"


def test_stage_library_backfill_is_idempotent_and_data_driven() -> None:
    definitions: dict[str, str] = {}
    links: dict[str, str] = {}
    rows = [
        SimpleNamespace(name="ROW-A", stage_type="ALPHA", department_label="ألفا"),
        SimpleNamespace(name="ROW-B", stage_type="BETA", department_label="بيتا"),
    ]

    fake_frappe = types.ModuleType("frappe")

    class FakeDB:
        @staticmethod
        def exists(doctype, name):
            return doctype == "DocType" and name == "Production Stage Definition"

        @staticmethod
        def get_table_columns(doctype):
            return ["stage_definition", "stage_type", "department_label"]

        @staticmethod
        def sql(query, as_dict=False):
            return [row for row in rows if not links.get(row.name)]

        @staticmethod
        def get_value(doctype, filters, fieldname, as_dict=False):
            if "stage_code" in filters:
                return definitions.get(filters["stage_code"])
            if "stage_label" in filters:
                return None
            return None

        @staticmethod
        def set_value(doctype, name, fieldname, value, **kwargs):
            links[name] = value

    fake_frappe.db = FakeDB()

    def get_doc(payload):
        def insert(ignore_permissions=False):
            definitions[payload["stage_code"]] = payload["stage_code"]
            return SimpleNamespace(name=payload["stage_code"])

        return SimpleNamespace(
            name=payload["stage_code"],
            insert=insert,
        )

    fake_frappe.get_doc = get_doc
    previous = sys.modules.get("frappe")
    sys.modules["frappe"] = fake_frappe
    try:
        spec = importlib.util.spec_from_file_location("_stage_library_patch_test", PATCH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.execute()
        module.execute()
    finally:
        if previous is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = previous

    assert definitions == {"ALPHA": "ALPHA", "BETA": "BETA"}
    assert links == {"ROW-A": "ALPHA", "ROW-B": "BETA"}
    source = PATCH.read_text(encoding="utf-8")
    assert "Drawing" not in source
    assert "CNC" not in source
