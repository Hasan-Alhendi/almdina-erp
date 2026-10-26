from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


PATCH_PATH = (
    Path(__file__).resolve().parents[1]
    / "patches"
    / "v1_0"
    / "migrate_extra_piece_type_to_regular.py"
)


class Row(dict):
    def __getattr__(self, name: str):
        return self[name]


def _load_patch(monkeypatch, frappe_stub):
    monkeypatch.setitem(sys.modules, "frappe", frappe_stub)
    spec = importlib.util.spec_from_file_location("test_extra_piece_type_patch", PATCH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_normalizer_changes_only_legacy_piece_type_and_preserves_history(monkeypatch) -> None:
    module = _load_patch(monkeypatch, SimpleNamespace())
    original = {
        "piece_type": "Extra",
        "extra_liner": 1,
        "extra_liner_unit_price_usd": 2.5,
        "extra_addons_total_usd": 5,
        "notes": "historical",
        "nested": [{"piece_type": "Special", "extra_back_groove": 1}],
    }
    normalized, changed = module.normalize_extra_piece_types(original)
    assert changed is True
    assert normalized == {
        **original,
        "piece_type": "Regular",
    }
    assert normalized["nested"] == original["nested"]
    assert original["piece_type"] == "Extra"


def test_execute_is_targeted_and_idempotent_for_rows_and_snapshots(monkeypatch) -> None:
    sql_calls = []
    set_calls = []
    snapshot = json.dumps(
        {
            "sheets": [
                {
                    "pieces": [
                        {
                            "piece_type": "Extra",
                            "extra_liner": 1,
                            "extra_liner_unit_price_usd": 2.5,
                            "notes": "keep",
                        }
                    ]
                }
            ]
        }
    )

    class DB:
        @staticmethod
        def has_column(_doctype, _fieldname):
            return True

        @staticmethod
        def sql(statement):
            sql_calls.append(statement)

        @staticmethod
        def set_value(doctype, name, fieldname, value, update_modified=False):
            set_calls.append((doctype, name, fieldname, value, update_modified))

    def get_all(doctype, **_kwargs):
        if doctype == "Cutting Plan":
            return [Row(name="PLAN-1", snapshot_json=snapshot)]
        return []

    module = _load_patch(monkeypatch, SimpleNamespace(db=DB(), get_all=get_all))
    module.execute()

    assert len(sql_calls) == 2
    assert all("where piece_type = 'Extra'" in statement for statement in sql_calls)
    assert all("set piece_type = 'Regular'" in statement for statement in sql_calls)
    assert len(set_calls) == 1
    migrated = json.loads(set_calls[0][3])
    piece = migrated["sheets"][0]["pieces"][0]
    assert piece == {
        "piece_type": "Regular",
        "extra_liner": 1,
        "extra_liner_unit_price_usd": 2.5,
        "notes": "keep",
    }
    assert set_calls[0][4] is False

    normalized_again, changed_again = module.normalize_extra_piece_types(migrated)
    assert normalized_again == migrated
    assert changed_again is False
