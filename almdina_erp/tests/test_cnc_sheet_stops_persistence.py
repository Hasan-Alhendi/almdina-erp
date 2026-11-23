"""Sheet-stop JSON persistence for CNC Operational File saves."""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.application.cnc.workspace import prepare_sheet_settings
from almdina_erp.almdina_erp.domain.cnc.operational_file import ApprovedPlanRef
from almdina_erp.almdina_erp.domain.cnc.placement import PlacementError
from almdina_erp.almdina_erp.infrastructure.frappe import cnc_operational_file_repository as repo
from almdina_erp.almdina_erp.services import cnc_operational_file_service as service


class _FakeJsonField:
    """Mimic Frappe JSON storage that rejects empty strings like MariaDB errno 4025."""

    _JSON_FIELDS = frozenset(
        {
            "cut_path_sequence",
            "sheet_stops_json",
            "machining_profiles_json",
            "vector_associations_json",
            "toolpath_snapshots_json",
            "reversed_path_keys",
        }
    )

    def __init__(self, name: str = "CNC-OF-STOPS"):
        self.name = name
        self._values: dict[str, object] = {
            "generation_snapshot_json": None,
            "generated_file": None,
            "generated_by": None,
            "generated_on": None,
            "operations": [],
            "paths": [],
            "settings_revision": 1,
            "sheet_stops_json": None,
            "name": name,
        }
        self.flags = SimpleNamespace(ignore_permissions=False, ignore_links=False)
        self._saved = False
        self.settings_revision = 1
        self.sheet_stops_json = None

    def get(self, field):
        return self._values.get(field)

    def set(self, field, value):
        if field in self._JSON_FIELDS and value == "":
            raise RuntimeError(
                "CONSTRAINT `tabcnc operational file.%s` failed" % field
            )
        if field in self._JSON_FIELDS and isinstance(value, (list, dict)):
            raise TypeError("%s cannot be a raw Python container" % field)
        self._values[field] = value
        setattr(self, field, value)

    def append(self, childtable, row):
        self._values.setdefault(childtable, []).append(row)

    def save(self):
        for field in self._JSON_FIELDS:
            raw = self._values.get(field)
            if raw == "":
                raise RuntimeError(
                    "CONSTRAINT `tabcnc operational file.%s` failed" % field
                )
            if isinstance(raw, str):
                json.loads(raw)
        self._saved = True


def _base_payload(**overrides):
    payload = {
        "door_cutting_order": "DCO-1",
        "cutting_plan": "PLAN-1",
        "plan_revision": 1,
        "plan_source_type": "System",
        "sheet_no": 1,
        "sheet_key": "sheet:1",
        "status": "Settings Saved",
        "settings_fingerprint": "fp-stops",
        "cut_path_early_confirmed": 0,
        "perimeter_join_mode": "separate",
        "cut_path_sequence": [],
        "perimeter_cut_early_confirmed": 0,
        "cnc_machine": "IMA",
        "offset_left_cm": 80,
        "offset_bottom_cm": 160,
        "operations": [],
        "paths": [],
    }
    payload.update(overrides)
    return payload


def _stops(width_side="Right Side", width_cm=34, length_side="Bottom Side", length_cm=156):
    return {
        "width_stop_side": width_side,
        "width_stop_cm": width_cm,
        "length_stop_side": length_side,
        "length_stop_cm": length_cm,
    }


def _machine(**overrides):
    row = {
        "name": "IMA",
        "machine_name": "IMA",
        "enabled": True,
        "width_cm": 200,
        "length_cm": 400,
        "work_zero_position": "Bottom Left",
        "width_stop_side": "Left Side",
        "length_stop_side": "Bottom Side",
        "post_processor": "ima_wh_ncstudio",
    }
    row.update(overrides)
    return row


def _piece():
    return {
        "piece_instance_id": "A",
        "label": "A",
        "sheet_no": 1,
        "extra_liner": 0,
        "liner_reference_side": "Left",
        "liner_offset_cm": 2,
        "liner_width_cm": 1.5,
        "liner_start_cm": 0,
        "liner_length_cm": 10,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }


def _snapshot():
    return {"full_board_width_cm": 120, "full_board_length_cm": 240}


def test_sheet_stops_json_unset_is_null_not_empty_string():
    assert repo._sheet_stops_json(None) is None
    assert repo._sheet_stops_json("") is None
    assert repo._sheet_stops_json("null") is None
    assert repo._sheet_stops_json({}) is None
    assert repo._sheet_stops_json({"width_stop_side": ""}) is None


def test_sheet_stops_json_round_trips_valid_custom_stops():
    raw = _stops()
    encoded = repo._sheet_stops_json(raw)
    assert isinstance(encoded, str)
    assert json.loads(encoded)["width_stop_cm"] == 34
    assert repo._sheet_stops_dict(encoded) == {
        "width_stop_side": "Right Side",
        "width_stop_cm": 34.0,
        "length_stop_side": "Bottom Side",
        "length_stop_cm": 156.0,
    }


def test_sheet_stops_dict_accepts_legacy_empty_and_null_payloads():
    assert repo._sheet_stops_dict(None) is None
    assert repo._sheet_stops_dict("") is None
    assert repo._sheet_stops_dict("null") is None
    assert repo._sheet_stops_dict("   ") is None
    assert repo._sheet_stops_dict('{"width_stop_side":""}') is None


def test_save_sheet_stores_null_when_sheet_stops_unset(monkeypatch):
    document = _FakeJsonField()
    monkeypatch.setattr(repo.frappe, "new_doc", lambda *_a, **_k: document)
    monkeypatch.setattr(repo, "_without_permission_check", lambda fn: fn())

    name = repo.save_sheet("", _base_payload(sheet_stops=None))
    assert name == "CNC-OF-STOPS"
    assert document._saved is True
    assert document.get("sheet_stops_json") is None
    assert document.sheet_stops_json is None


def test_save_sheet_rejects_legacy_empty_string_encoding(monkeypatch):
    """Guardrail: empty string must never reach the JSON column."""

    document = _FakeJsonField()
    monkeypatch.setattr(repo.frappe, "new_doc", lambda *_a, **_k: document)
    monkeypatch.setattr(repo, "_without_permission_check", lambda fn: fn())
    monkeypatch.setattr(repo, "_sheet_stops_json", lambda _raw: "")

    with pytest.raises(RuntimeError, match="sheet_stops_json"):
        repo.save_sheet("", _base_payload(sheet_stops=None))


def test_save_sheet_persists_custom_stops_and_keeps_revision_stable_on_noop(monkeypatch):
    document = _FakeJsonField()
    document.set("settings_revision", 3)
    document.settings_revision = 3
    encoded = repo._sheet_stops_json(_stops())
    document.set("sheet_stops_json", encoded)
    for field, value in _base_payload(
        sheet_stops=_stops(),
        settings_fingerprint="fp-stops",
    ).items():
        if field in ("operations", "paths", "sheet_stops"):
            continue
        if field == "cut_path_sequence":
            document.set(field, repo._sequence_json(value))
        else:
            document.set(field, value)
    document._saved = False

    monkeypatch.setattr(repo, "_without_permission_check", lambda fn: fn())
    monkeypatch.setattr(repo.frappe, "get_doc", lambda *_a, **_k: document)
    monkeypatch.setattr(repo, "_lock_existing_revision", lambda _name: 3)

    name = repo.save_sheet(
        "CNC-OF-STOPS",
        _base_payload(sheet_stops=_stops()),
        expected_revision=3,
    )
    assert name == "CNC-OF-STOPS"
    # Identical settings must not bump revision or call save.
    assert document.settings_revision == 3
    assert document._saved is False
    assert repo._sheet_stops_dict(document.get("sheet_stops_json"))["width_stop_cm"] == 34.0


def test_save_sheet_updates_custom_stops_without_wiping_machining_json(monkeypatch):
    document = _FakeJsonField()
    document.set("settings_revision", 2)
    document.settings_revision = 2
    document.set(
        "machining_profiles_json",
        json.dumps([{"profile_id": "p1"}], ensure_ascii=True, separators=(",", ":")),
    )
    document.set(
        "vector_associations_json",
        json.dumps([{"association_id": "a1"}], ensure_ascii=True, separators=(",", ":")),
    )
    document.set(
        "toolpath_snapshots_json",
        json.dumps([{"toolpath_id": "t1"}], ensure_ascii=True, separators=(",", ":")),
    )
    document.set("sheet_stops_json", repo._sheet_stops_json(_stops(width_cm=10)))
    for field, value in _base_payload().items():
        if field in ("operations", "paths", "sheet_stops"):
            continue
        if field == "cut_path_sequence":
            document.set(field, repo._sequence_json(value))
        else:
            document.set(field, value)

    monkeypatch.setattr(repo, "_without_permission_check", lambda fn: fn())
    monkeypatch.setattr(repo.frappe, "get_doc", lambda *_a, **_k: document)
    monkeypatch.setattr(repo, "_lock_existing_revision", lambda _name: 2)

    repo.save_sheet(
        "CNC-OF-STOPS",
        _base_payload(
            sheet_stops=_stops(width_cm=34, length_cm=156),
            machining_profiles_json=[{"profile_id": "p1"}],
            vector_associations_json=[{"association_id": "a1"}],
            toolpath_snapshots_json=[{"toolpath_id": "t1"}],
        ),
        expected_revision=2,
    )
    assert document._saved is True
    assert document.settings_revision == 3
    assert repo._sheet_stops_dict(document.get("sheet_stops_json")) == {
        "width_stop_side": "Right Side",
        "width_stop_cm": 34.0,
        "length_stop_side": "Bottom Side",
        "length_stop_cm": 156.0,
    }
    assert json.loads(document.get("machining_profiles_json"))[0]["profile_id"] == "p1"
    assert json.loads(document.get("vector_associations_json"))[0]["association_id"] == "a1"
    assert json.loads(document.get("toolpath_snapshots_json"))[0]["toolpath_id"] == "t1"


def test_prepare_keeps_saved_stops_when_toolpath_args_omit_stop_fields():
    catalog = [_machine()]
    prepared = prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=ApprovedPlanRef("PLAN-1", 1, "System", "Approved"),
        plan_is_current=True,
        pieces=[_piece()],
        sheet_no=1,
        existing={
            "cnc_machine": "IMA",
            "sheet_stops": _stops(),
            "toolpath_snapshots": [{"toolpath_id": "old"}],
            "vector_associations": [{"association_id": "a1"}],
            "settings_revision": 4,
        },
        operation_presets={},
        path_overrides={},
        known_presets={},
        machine_profile={"fingerprint_payload": {}},
        cnc_machine="IMA",
        machine_catalog=catalog,
        plan_snapshot=_snapshot(),
        toolpath_snapshots=[{"toolpath_id": "old"}, {"toolpath_id": "new"}],
        vector_associations=[{"association_id": "a1"}],
    )
    assert prepared["sheet_stops"]["width_stop_side"] == "Right Side"
    assert prepared["sheet_stops"]["width_stop_cm"] == 34
    assert prepared["sheet_stops"]["length_stop_cm"] == 156
    assert prepared["offset_left_cm"] == 46
    assert prepared["offset_bottom_cm"] == 156


def test_prepare_applies_explicit_stop_edits_and_validates_bounds():
    catalog = [_machine()]
    edited = prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=ApprovedPlanRef("PLAN-1", 1, "System", "Approved"),
        plan_is_current=True,
        pieces=[_piece()],
        sheet_no=1,
        existing={"cnc_machine": "IMA", "sheet_stops": _stops(width_cm=10)},
        operation_presets={},
        path_overrides={},
        known_presets={},
        machine_profile={"fingerprint_payload": {}},
        cnc_machine="IMA",
        width_stop_side="Right Side",
        width_stop_cm=34,
        length_stop_side="Bottom Side",
        length_stop_cm=156,
        machine_catalog=catalog,
        plan_snapshot=_snapshot(),
    )
    assert edited["sheet_stops"]["width_stop_cm"] == 34
    assert edited["sheet_stops"]["length_stop_cm"] == 156

    with pytest.raises(PlacementError) as oversize:
        prepare_sheet_settings(
            order_name="DCO-1",
            approved_plan=ApprovedPlanRef("PLAN-1", 1, "System", "Approved"),
            plan_is_current=True,
            pieces=[_piece()],
            sheet_no=1,
            existing={"cnc_machine": "IMA"},
            operation_presets={},
            path_overrides={},
            known_presets={},
            machine_profile={"fingerprint_payload": {}},
            cnc_machine="IMA",
            width_stop_side="Left Side",
            width_stop_cm=999,
            length_stop_side="Bottom Side",
            length_stop_cm=0,
            machine_catalog=catalog,
            plan_snapshot=_snapshot(),
        )
    assert oversize.value.code == "width_stop_invalid"


def test_prepare_without_custom_stops_leaves_sheet_stops_unset():
    prepared = prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=ApprovedPlanRef("PLAN-1", 1, "System", "Approved"),
        plan_is_current=True,
        pieces=[_piece()],
        sheet_no=1,
        existing={"cnc_machine": "IMA"},
        operation_presets={},
        path_overrides={},
        known_presets={},
        machine_profile={"fingerprint_payload": {}},
        cnc_machine="IMA",
        machine_catalog=[_machine()],
        plan_snapshot=_snapshot(),
    )
    assert prepared["sheet_stops"] is None
    assert prepared["offset_left_cm"] == 80
    assert prepared["offset_bottom_cm"] == 160
    assert repo._sheet_stops_json(prepared["sheet_stops"]) is None


def test_calculate_and_direction_endpoints_accept_sheet_stop_fields():
    calculate = inspect.signature(service.calculate_cnc_association_toolpath).parameters
    direction = inspect.signature(service.set_cnc_path_direction).parameters
    for name in (
        "width_stop_side",
        "width_stop_cm",
        "length_stop_side",
        "length_stop_cm",
    ):
        assert name in calculate
        assert name in direction

    source = inspect.getsource(service.calculate_cnc_association_toolpath)
    assert "width_stop_side=width_stop_side" in source
    assert "length_stop_cm=length_stop_cm" in source
    direction_source = inspect.getsource(service.set_cnc_path_direction)
    assert "width_stop_side=width_stop_side" in direction_source
