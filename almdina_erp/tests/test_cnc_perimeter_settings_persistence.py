"""Persistence and sequence contract for connected perimeter settings."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cnc.perimeter import (
    CUT_PATH_INTERNAL_SEQUENCE_KEY,
    SHEET_PERIMETER_PATH_KEY,
)
from almdina_erp.almdina_erp.infrastructure.frappe import cnc_operational_file_repository as repo


class _FakeJsonField:
    """Mimic a Frappe JSON field that rejects raw Python lists on set."""

    def __init__(self, name: str = "CNC-OF-1"):
        self.name = name
        self._values: dict[str, object] = {
            "generation_snapshot_json": None,
            "generated_file": None,
            "generated_by": None,
            "generated_on": None,
            "operations": [],
            "paths": [],
            "name": name,
        }
        self.flags = SimpleNamespace(ignore_permissions=False)
        self._saved = False
        self.generation_snapshot_json = None
        self.generated_file = None
        self.generated_by = None
        self.generated_on = None

    def get(self, field):
        return self._values.get(field)

    def set(self, field, value):
        if field == "cut_path_sequence" and isinstance(value, list):
            raise TypeError("Cut Path Sequence cannot be a list")
        self._values[field] = value
        setattr(self, field, value)

    def append(self, childtable, row):
        self._values.setdefault(childtable, []).append(row)

    def save(self):
        # Round-trip like MariaDB/Frappe JSON storage: keep a string, expose list on read.
        raw = self._values.get("cut_path_sequence")
        if isinstance(raw, list):
            raise TypeError("Cut Path Sequence cannot be a list")
        if isinstance(raw, str):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise TypeError("Cut Path Sequence must be a JSON list")
            self._values["cut_path_sequence"] = raw
            self.cut_path_sequence = parsed
        self._saved = True


def test_sequence_json_encodes_list_without_double_encoding():
    encoded = repo._sequence_json(
        [CUT_PATH_INTERNAL_SEQUENCE_KEY, SHEET_PERIMETER_PATH_KEY]
    )
    assert isinstance(encoded, str)
    assert json.loads(encoded) == [
        CUT_PATH_INTERNAL_SEQUENCE_KEY,
        SHEET_PERIMETER_PATH_KEY,
    ]
    assert repo._sequence_list(encoded) == [
        CUT_PATH_INTERNAL_SEQUENCE_KEY,
        SHEET_PERIMETER_PATH_KEY,
    ]
    assert repo._sequence_json(encoded) == encoded
    assert repo._sequence_list(None) == []
    assert repo._sequence_list("") == []
    assert repo._sequence_json(None) == "[]"


def test_save_sheet_persists_cut_path_sequence_as_json(monkeypatch):
    document = _FakeJsonField()

    monkeypatch.setattr(repo.frappe, "new_doc", lambda *_a, **_k: document)
    monkeypatch.setattr(repo, "_without_permission_check", lambda fn: fn())

    name = repo.save_sheet(
        "",
        {
            "door_cutting_order": "DCO-1",
            "cutting_plan": "PLAN-1",
            "plan_revision": 1,
            "plan_source_type": "System",
            "sheet_no": 1,
            "sheet_key": "sheet:1",
            "status": "Draft",
            "settings_fingerprint": "fp",
            "cut_path_early_confirmed": 0,
            "perimeter_join_mode": "connected",
            "cut_path_sequence": [
                CUT_PATH_INTERNAL_SEQUENCE_KEY,
                SHEET_PERIMETER_PATH_KEY,
            ],
            "perimeter_cut_early_confirmed": 0,
            "operations": [
                {
                    "operation_key": "sheet_perimeter",
                    "dxf_layer": "CUT_PATH",
                    "sequence": 1,
                    "tool_preset": "",
                    "preset_source": "Factory",
                }
            ],
            "paths": [
                {
                    "path_key": SHEET_PERIMETER_PATH_KEY,
                    "operation_key": "sheet_perimeter",
                    "piece_instance_id": "",
                    "dxf_layer": "CUT_PATH",
                    "sequence": 1,
                    "tool_preset": "",
                },
                {
                    "path_key": "cut_path:piece-a:outer",
                    "operation_key": "cut_path",
                    "piece_instance_id": "piece-a",
                    "dxf_layer": "CUT_PATH",
                    "sequence": 2,
                    "tool_preset": "",
                },
            ],
        },
    )
    assert name == "CNC-OF-1"
    assert document._saved is True
    stored = document.get("cut_path_sequence")
    assert isinstance(stored, str)
    assert json.loads(stored) == [
        CUT_PATH_INTERNAL_SEQUENCE_KEY,
        SHEET_PERIMETER_PATH_KEY,
    ]
    assert repo._sequence_list(document.cut_path_sequence) == [
        CUT_PATH_INTERNAL_SEQUENCE_KEY,
        SHEET_PERIMETER_PATH_KEY,
    ]
    paths = document.get("paths") or []
    peri = next(row for row in paths if row["path_key"] == SHEET_PERIMETER_PATH_KEY)
    assert peri["piece_instance_id"] == ""
    assert peri["operation_key"] == "sheet_perimeter"


def test_save_sheet_from_generate_payload_keeps_snapshot(monkeypatch):
    document = _FakeJsonField("CNC-OF-2")
    document._values.update(
        {
            "generation_snapshot_json": {"settings_fingerprint": "old"},
            "generated_file": "/private/files/old.sim.nc",
            "generated_by": "user@example.com",
            "generated_on": "2026-01-01",
        }
    )
    document.generation_snapshot_json = {"settings_fingerprint": "old"}
    document.generated_file = "/private/files/old.sim.nc"
    document.generated_by = "user@example.com"
    document.generated_on = "2026-01-01"

    monkeypatch.setattr(repo, "_without_permission_check", lambda fn: fn())
    monkeypatch.setattr(repo.frappe, "get_doc", lambda *_a, **_k: document)

    # Existing-name path used by save after prepare during Generate NC.
    name = repo.save_sheet(
        "CNC-OF-2",
        {
            "door_cutting_order": "DCO-1",
            "cutting_plan": "PLAN-1",
            "plan_revision": 1,
            "plan_source_type": "System",
            "sheet_no": 2,
            "sheet_key": "sheet:2",
            "status": "Needs Regeneration",
            "settings_fingerprint": "fp2",
            "cut_path_early_confirmed": 0,
            "perimeter_join_mode": "connected",
            "cut_path_sequence": [SHEET_PERIMETER_PATH_KEY, CUT_PATH_INTERNAL_SEQUENCE_KEY],
            "perimeter_cut_early_confirmed": 1,
            "operations": [{"operation_key": "cut_path", "sequence": 1, "tool_preset": "Finish"}],
            "paths": [],
        },
    )
    assert name == "CNC-OF-2"
    assert document.generation_snapshot_json == {"settings_fingerprint": "old"}
    assert document.generated_file == "/private/files/old.sim.nc"
    assert json.loads(document.get("cut_path_sequence"))[0] == SHEET_PERIMETER_PATH_KEY
