"""Path-direction reverse persists current sheet settings atomically."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cnc.artcam_machining import (
    MachiningSetupError,
    apply_reversed_directions,
    path_geometry_id,
    shape_id,
    toggle_reversed_path,
)
from almdina_erp.almdina_erp.domain.cnc.program import _motions
from almdina_erp.almdina_erp.services import cnc_operational_file_service as service


APP_ROOT = Path(__file__).resolve().parents[1]
SERVICE = APP_ROOT / "almdina_erp" / "services" / "cnc_operational_file_service.py"
PANEL = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cnc"
    / "door_cutting_order_operational_files_ux.js"
)


def _path(
    path_key: str = "cut_path:piece-a:outer",
    *,
    points=((0.0, 0.0), (10.0, 0.0), (10.0, 5.0)),
    closed: bool = False,
):
    motions = _motions(points, closed=closed, depths=(5.0, 10.0))
    return {
        "path_key": path_key,
        "closed": closed,
        "ready": True,
        "points": [[point[0], point[1]] for point in points],
        "motions": [
            {
                "kind": motion.kind,
                "x_mm": motion.x_mm,
                "y_mm": motion.y_mm,
                "depth_mm": motion.depth_mm,
            }
            for motion in motions
        ],
        "preset": {
            "tool_number": "T9",
            "spindle_speed_rpm": 18000,
            "feed_rate_mm_min": 2400,
            "plunge_rate_mm_min": 600,
            "safe_z_mm": 5,
        },
        "safe_z_mm": 5,
    }


def _program(*paths):
    return {
        "operations": [{"operation_key": "cut_path", "toolpaths": list(paths)}],
        "issues": [],
        "geometry_ready": True,
        "ready": True,
    }


def test_reverse_endpoint_no_longer_requires_a_prior_sheet_save():
    source = SERVICE.read_text(encoding="utf-8")
    body = source.split("def set_cnc_path_direction", 1)[1].split(
        "def _compile_authorized_program", 1
    )[0]
    assert "sheet_settings_required" not in body
    assert "Save the sheet settings before reversing" not in body
    assert "_reject_stale_sheet(saved, base_revision)" in body
    assert "reversed_path_keys=records" in body
    assert "save_sheet(" in body
    assert 'str((saved or {}).get("name") or "")' in body
    assert "(saved or {}).get(\"toolpath_snapshots\")" in body or "(saved or {}).get('toolpath_snapshots')" in body


def test_reverse_endpoint_accepts_current_sheet_settings_from_the_client():
    params = inspect.signature(service.set_cnc_path_direction).parameters
    for name in (
        "operation_presets",
        "path_overrides",
        "operation_order",
        "operation_sources",
        "cnc_machine",
        "width_stop_side",
        "width_stop_cm",
        "length_stop_side",
        "length_stop_cm",
        "base_revision",
        "viewed_plan_token",
    ):
        assert name in params


def test_ui_sends_current_sheet_args_with_reverse_and_syncs_after_success():
    panel = PANEL.read_text(encoding="utf-8")
    assert "set_cnc_path_direction" in panel
    assert "sheetGenerateArgs(frm, workspace, sheet, state)" in panel
    assert "state.reverseBusy = pathKey" in panel
    assert "The path direction was not changed." in panel
    assert "state.sheetStops = next.sheetStops" in panel
    assert "state.settingsRevision = next.settingsRevision" in panel
    assert "Save the sheet settings before reversing" not in panel


def test_toggle_before_any_saved_sheet_creates_one_direction_record():
    path = _path()
    program = _program(path)
    first = toggle_reversed_path([], program, path["path_key"], shape_id(path))
    assert len(first) == 1
    assert first[0]["path_key"] == path["path_key"]
    assert first[0]["geometry_id"] == path_geometry_id(path)
    applied = apply_reversed_directions(program, first)
    assert applied["operations"][0]["toolpaths"][0]["points"][0] == [10.0, 5.0]


def test_toggle_twice_restores_original_direction_without_extra_rows():
    path = _path()
    program = _program(path)
    identity = shape_id(path)
    once = toggle_reversed_path([], program, path["path_key"], identity)
    twice = toggle_reversed_path(once, program, path["path_key"], identity)
    assert twice == []
    restored = apply_reversed_directions(program, twice)
    assert restored["operations"][0]["toolpaths"][0]["points"] == path["points"]


def test_toggle_keeps_other_path_directions_and_does_not_duplicate_rows():
    first = _path("cut_path:a")
    second = _path("cut_path:b", points=((0.0, 20.0), (12.0, 20.0), (12.0, 28.0)))
    program = _program(first, second)
    saved = toggle_reversed_path([], program, first["path_key"], shape_id(first))
    saved = toggle_reversed_path(saved, program, second["path_key"], shape_id(second))
    assert [row["path_key"] for row in saved] == ["cut_path:a", "cut_path:b"]
    again = toggle_reversed_path(saved, program, first["path_key"], shape_id(first))
    assert [row["path_key"] for row in again] == ["cut_path:b"]
    assert len(again) == 1


def test_unsupported_reverse_raises_without_mutating_records():
    path = _path()
    program = _program(path)
    with pytest.raises(MachiningSetupError) as missing:
        toggle_reversed_path([], program, "cut_path:missing", "")
    assert missing.value.code == "path_reverse_missing"
    assert toggle_reversed_path([], program, path["path_key"], shape_id(path))


def test_reject_stale_sheet_blocks_concurrent_revision_on_existing_and_new(monkeypatch):
    assert service._revision(None) == -1
    assert service._revision("3") == 3

    class _Boom(Exception):
        pass

    monkeypatch.setattr(service, "_message", lambda code: code)
    monkeypatch.setattr(
        service.frappe,
        "throw",
        lambda message, exc_type=None: (_ for _ in ()).throw(_Boom(str(message))),
    )
    with pytest.raises(_Boom):
        service._reject_stale_sheet({"settings_revision": 2}, base_revision=1)
    with pytest.raises(_Boom):
        service._reject_stale_sheet(None, base_revision=4)
    service._reject_stale_sheet(None, base_revision=0)
    service._reject_stale_sheet({"settings_revision": 2}, base_revision=2)


def test_set_cnc_path_direction_saves_once_for_first_reverse(monkeypatch):
    order = SimpleNamespace(name="DCO-1")
    plan = SimpleNamespace(name="PLAN-1", revision=1, source_type="System")
    path = _path()
    program = _program(path)
    prepared = {
        "door_cutting_order": "DCO-1",
        "sheet_no": 1,
        "reversed_path_keys": [],
        "operations": [],
        "paths": [],
    }
    saved_payloads = []

    monkeypatch.setattr(service, "_authorized_order", lambda *_a, **_k: order)
    monkeypatch.setattr(service, "approved_plan_ref", lambda *_a, **_k: plan)
    monkeypatch.setattr(service, "_existing_sheet", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "_reject_stale_sheet", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "factory_operation_defaults", lambda: {})
    monkeypatch.setattr(
        service,
        "_settings_from_saved",
        lambda *_a, **_k: ({}, {}, [], False, {}, "separate", [], False),
    )
    monkeypatch.setattr(
        service,
        "_compile_authorized_program",
        lambda *_a, **_k: (plan, program, {}),
    )
    monkeypatch.setattr(service, "unreversed_operational_program", lambda prog, **_k: prog)
    monkeypatch.setattr(
        service,
        "clear_reversed_direction_conflicts",
        lambda prog, rows: list(rows or []),
    )
    monkeypatch.setattr(
        service,
        "toggle_reversed_path",
        lambda records, prog, key, shape, clear=False: [
            {"path_key": key, "geometry_id": "g1", "shape_id": shape or "s1"}
        ],
    )
    monkeypatch.setattr(service, "known_tool_presets", lambda: {})
    monkeypatch.setattr(service, "machine_profile_view", lambda: {"fingerprint_payload": {}})
    monkeypatch.setattr(service, "list_cnc_machines", lambda: [])
    monkeypatch.setattr(service, "placed_piece_views", lambda *_a, **_k: [])
    monkeypatch.setattr(service, "approved_plan_snapshot", lambda *_a, **_k: {})
    monkeypatch.setattr(
        service,
        "prepare_sheet_settings",
        lambda **kwargs: dict(prepared, reversed_path_keys=kwargs.get("reversed_path_keys")),
    )

    def fake_save(name, payload, expected_revision=None):
        saved_payloads.append(
            {
                "name": name,
                "payload": dict(payload),
                "expected_revision": expected_revision,
            }
        )
        return "CNC-OF-NEW"

    monkeypatch.setattr(service, "save_sheet", fake_save)
    monkeypatch.setattr(
        service,
        "_workspace_for",
        lambda *_a, **_k: {
            "sheets": [
                {
                    "sheet_no": 1,
                    "settings_revision": 1,
                    "reversed_path_keys": saved_payloads[-1]["payload"]["reversed_path_keys"],
                    "machining": {"associations": [], "profiles": [], "snapshots": []},
                }
            ]
        },
    )

    result = service.set_cnc_path_direction(
        order_name="DCO-1",
        sheet_no=1,
        path_key=path["path_key"],
        shape_id="s1",
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        viewed_plan_token="PLAN-1::1",
        base_revision=0,
    )
    assert len(saved_payloads) == 1
    assert saved_payloads[0]["name"] == ""
    assert saved_payloads[0]["expected_revision"] == 0
    assert saved_payloads[0]["payload"]["reversed_path_keys"] == [
        {"path_key": path["path_key"], "geometry_id": "g1", "shape_id": "s1"}
    ]
    assert "machining_profiles_json" not in saved_payloads[0]["payload"]
    assert "toolpath_snapshots_json" not in saved_payloads[0]["payload"]
    assert result["reversed_path_key"] == path["path_key"]


def test_set_cnc_path_direction_preserves_snapshots_on_existing_sheet(monkeypatch):
    order = SimpleNamespace(name="DCO-1")
    plan = SimpleNamespace(name="PLAN-1", revision=1, source_type="System")
    path = _path()
    program = _program(path)
    snapshots = [{"toolpath_id": "snap-1", "association_id": "a1"}]
    associations = [{"association_id": "a1", "toolpath_id": "snap-1"}]
    existing = {
        "name": "CNC-OF-1",
        "settings_revision": 3,
        "cnc_machine": "IMA",
        "toolpath_snapshots": snapshots,
        "vector_associations": associations,
        "machining_profiles": [{"profile_id": "p1"}],
        "reversed_path_keys": [],
        "operations": [{"operation_key": "cut_path", "tool_preset": "Finish", "sequence": 1}],
        "paths": [],
    }
    captured = {}

    monkeypatch.setattr(service, "_authorized_order", lambda *_a, **_k: order)
    monkeypatch.setattr(service, "approved_plan_ref", lambda *_a, **_k: plan)
    monkeypatch.setattr(service, "_existing_sheet", lambda *_a, **_k: existing)
    monkeypatch.setattr(service, "_reject_stale_sheet", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "factory_operation_defaults", lambda: {})
    monkeypatch.setattr(
        service,
        "_settings_from_saved",
        lambda *_a, **_k: (
            {"cut_path": "Finish"},
            {},
            ["cut_path"],
            False,
            {"cut_path": "factory"},
            "separate",
            [],
            False,
        ),
    )
    monkeypatch.setattr(
        service,
        "_compile_authorized_program",
        lambda *_a, **_k: (plan, program, {}),
    )
    monkeypatch.setattr(service, "unreversed_operational_program", lambda prog, **_k: prog)
    monkeypatch.setattr(
        service,
        "clear_reversed_direction_conflicts",
        lambda prog, rows: list(rows or []),
    )
    monkeypatch.setattr(
        service,
        "toggle_reversed_path",
        lambda records, prog, key, shape, clear=False: [
            {"path_key": key, "geometry_id": "g1", "shape_id": "s1"}
        ],
    )
    monkeypatch.setattr(service, "known_tool_presets", lambda: {})
    monkeypatch.setattr(service, "machine_profile_view", lambda: {"fingerprint_payload": {}})
    monkeypatch.setattr(service, "list_cnc_machines", lambda: [{"name": "IMA"}])
    monkeypatch.setattr(service, "placed_piece_views", lambda *_a, **_k: [])
    monkeypatch.setattr(service, "approved_plan_snapshot", lambda *_a, **_k: {})

    def fake_prepare(**kwargs):
        captured["prepare"] = kwargs
        return {
            "door_cutting_order": "DCO-1",
            "sheet_no": 1,
            "cnc_machine": kwargs.get("cnc_machine"),
            "reversed_path_keys": kwargs.get("reversed_path_keys"),
            "operations": [],
            "paths": [],
        }

    monkeypatch.setattr(service, "prepare_sheet_settings", fake_prepare)
    monkeypatch.setattr(
        service,
        "save_sheet",
        lambda name, payload, expected_revision=None: captured.update(
            {"save_name": name, "save_payload": payload, "revision": expected_revision}
        ) or name,
    )
    monkeypatch.setattr(
        service,
        "_workspace_for",
        lambda *_a, **_k: {"sheets": [{"sheet_no": 1, "settings_revision": 4}]},
    )

    service.set_cnc_path_direction(
        order_name="DCO-1",
        sheet_no=1,
        path_key=path["path_key"],
        shape_id="s1",
        cnc_machine="IMA",
        width_stop_side="Right Side",
        width_stop_cm=10,
        length_stop_side="Bottom Side",
        length_stop_cm=0,
        base_revision=3,
    )
    assert captured["save_name"] == "CNC-OF-1"
    assert captured["revision"] == 3
    assert captured["prepare"]["toolpath_snapshots"] == snapshots
    assert captured["prepare"]["vector_associations"] == associations
    assert captured["prepare"]["cnc_machine"] == "IMA"
    assert captured["prepare"]["width_stop_cm"] == 10
    assert "machining_profiles_json" not in captured["save_payload"]
    assert "toolpath_snapshots_json" not in captured["save_payload"]
    assert captured["save_payload"]["reversed_path_keys"][0]["path_key"] == path["path_key"]


def test_set_cnc_path_direction_does_not_save_when_toggle_fails(monkeypatch):
    order = SimpleNamespace(name="DCO-1")
    plan = SimpleNamespace(name="PLAN-1", revision=1, source_type="System")
    path = _path()
    program = _program(path)
    saves = []

    monkeypatch.setattr(service, "_authorized_order", lambda *_a, **_k: order)
    monkeypatch.setattr(service, "approved_plan_ref", lambda *_a, **_k: plan)
    monkeypatch.setattr(service, "_existing_sheet", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "_reject_stale_sheet", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "factory_operation_defaults", lambda: {})
    monkeypatch.setattr(
        service,
        "_settings_from_saved",
        lambda *_a, **_k: ({}, {}, [], False, {}, "separate", [], False),
    )
    monkeypatch.setattr(
        service,
        "_compile_authorized_program",
        lambda *_a, **_k: (plan, program, {}),
    )
    monkeypatch.setattr(service, "unreversed_operational_program", lambda prog, **_k: prog)
    monkeypatch.setattr(
        service,
        "clear_reversed_direction_conflicts",
        lambda prog, rows: list(rows or []),
    )

    def boom(*_a, **_k):
        raise MachiningSetupError("path_reverse_unsupported", detail="cut_path:x")

    monkeypatch.setattr(service, "toggle_reversed_path", boom)
    monkeypatch.setattr(service, "save_sheet", lambda *a, **k: saves.append((a, k)) or "x")
    monkeypatch.setattr(service, "_issue_message", lambda code, detail: code)

    class _Throw(Exception):
        pass

    monkeypatch.setattr(
        service.frappe,
        "throw",
        lambda message, exc=None: (_ for _ in ()).throw(_Throw(str(message))),
    )

    with pytest.raises(_Throw):
        service.set_cnc_path_direction(
            order_name="DCO-1",
            sheet_no=1,
            path_key=path["path_key"],
            base_revision=0,
        )
    assert saves == []


def test_set_cnc_path_direction_uses_unsaved_client_machine_not_stale_saved(monkeypatch):
    order = SimpleNamespace(name="DCO-1")
    plan = SimpleNamespace(name="PLAN-1", revision=1, source_type="System")
    path = _path()
    program = _program(path)
    existing = {
        "name": "CNC-OF-1",
        "settings_revision": 2,
        "cnc_machine": "OLD",
        "toolpath_snapshots": [],
        "vector_associations": [],
        "reversed_path_keys": [],
    }
    captured = {}

    monkeypatch.setattr(service, "_authorized_order", lambda *_a, **_k: order)
    monkeypatch.setattr(service, "approved_plan_ref", lambda *_a, **_k: plan)
    monkeypatch.setattr(service, "_existing_sheet", lambda *_a, **_k: existing)
    monkeypatch.setattr(service, "_reject_stale_sheet", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "factory_operation_defaults", lambda: {})
    monkeypatch.setattr(
        service,
        "_settings_from_saved",
        lambda *_a, **_k: ({}, {}, [], False, {}, "separate", [], False),
    )
    monkeypatch.setattr(
        service,
        "_compile_authorized_program",
        lambda *_a, **_k: (plan, program, {}),
    )
    monkeypatch.setattr(service, "unreversed_operational_program", lambda prog, **_k: prog)
    monkeypatch.setattr(
        service,
        "clear_reversed_direction_conflicts",
        lambda prog, rows: [],
    )
    monkeypatch.setattr(
        service,
        "toggle_reversed_path",
        lambda *a, **k: [{"path_key": path["path_key"], "geometry_id": "g", "shape_id": "s"}],
    )
    monkeypatch.setattr(service, "known_tool_presets", lambda: {})
    monkeypatch.setattr(service, "machine_profile_view", lambda: {"fingerprint_payload": {}})
    monkeypatch.setattr(service, "list_cnc_machines", lambda: [])
    monkeypatch.setattr(service, "placed_piece_views", lambda *_a, **_k: [])
    monkeypatch.setattr(service, "approved_plan_snapshot", lambda *_a, **_k: {})
    monkeypatch.setattr(
        service,
        "prepare_sheet_settings",
        lambda **kwargs: captured.setdefault("kwargs", kwargs) or {
            "reversed_path_keys": kwargs["reversed_path_keys"],
            "operations": [],
            "paths": [],
        },
    )
    monkeypatch.setattr(service, "save_sheet", lambda *a, **k: "CNC-OF-1")
    monkeypatch.setattr(service, "_workspace_for", lambda *_a, **_k: {"sheets": []})

    service.set_cnc_path_direction(
        order_name="DCO-1",
        sheet_no=1,
        path_key=path["path_key"],
        cnc_machine="NEW",
        base_revision=2,
    )
    assert captured["kwargs"]["cnc_machine"] == "NEW"


def test_direction_function_is_a_single_atomic_save_in_source():
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"))
    func = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "set_cnc_path_direction"
    )
    saves = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "save_sheet"
    ]
    assert len(saves) == 1
