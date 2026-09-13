from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


APP_ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = APP_ROOT / "patches" / "v1_0" / "backfill_legacy_piece_instance_ids.py"


class FakeDB:
    def __init__(self) -> None:
        self.values = {
            "legacy-empty": "",
            "legacy-whitespace": "   ",
            "already-modern": "piece:existing",
        }
        self.writes: list[tuple[str, str, str, str, bool]] = []

    def table_exists(self, doctype: str) -> bool:
        return doctype == "Door Cutting Order Detail"

    def sql(self, _query: str, params, *, as_dict: bool = False):
        assert as_dict is True
        limit = int(params[0])
        missing = [
            SimpleNamespace(name=name)
            for name, value in sorted(self.values.items())
            if not str(value or "").strip()
        ]
        return missing[:limit]

    def set_value(
        self,
        doctype: str,
        name: str,
        fieldname: str,
        value: str,
        *,
        update_modified: bool,
    ) -> None:
        self.writes.append((doctype, name, fieldname, value, update_modified))
        self.values[name] = value


def _load_patch(monkeypatch, db: FakeDB):
    frappe = types.ModuleType("frappe")
    frappe.db = db
    monkeypatch.setitem(sys.modules, "frappe", frappe)

    spec = importlib.util.spec_from_file_location("legacy_piece_instance_backfill_under_test", PATCH_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_piece_instance_backfill_is_idempotent_and_preserves_existing_ids(monkeypatch) -> None:
    db = FakeDB()
    patch = _load_patch(monkeypatch, db)

    patch.execute()

    assert db.values["already-modern"] == "piece:existing"
    assert db.values["legacy-empty"].startswith("piece:")
    assert db.values["legacy-whitespace"].startswith("piece:")
    assert db.values["legacy-empty"] != db.values["legacy-whitespace"]
    assert len(db.writes) == 2
    assert all(write[4] is False for write in db.writes)

    first_pass = dict(db.values)
    patch.execute()

    assert db.values == first_pass
    assert len(db.writes) == 2


def test_legacy_piece_instance_id_is_deterministic(monkeypatch) -> None:
    patch = _load_patch(monkeypatch, FakeDB())

    first = patch.legacy_piece_instance_id("child-row-a")
    second = patch.legacy_piece_instance_id("child-row-a")
    other = patch.legacy_piece_instance_id("child-row-b")

    assert first == second
    assert first.startswith("piece:")
    assert len(first) == len("piece:") + 32
    assert first != other
