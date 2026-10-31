from __future__ import annotations

from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cnc.workspace import (
    build_operational_workspace,
    operational_board_layout,
    prepare_sheet_settings,
)
from almdina_erp.almdina_erp.domain.cnc.operations import DEFAULT_MACHINING_ORDER
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    OperationalFileError,
    ApprovedPlanRef,
    assert_viewed_plan_token,
    catalog_sheet,
    cut_path_precedes_internal,
    default_operation_order,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


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
NESTING = APP_ROOT / "almdina_erp" / "domain" / "cutting"


def _raw(**overrides):
    values = {
        "preset_name": "Finish T9",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 6,
        "final_depth_mm": 18.5,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 10200,
        "plunge_rate_mm_min": 1800,
        "pass_depth_mm": 7,
        "enabled": True,
    }
    values.update(overrides)
    return values


def _piece(instance_id, **extra):
    piece = {
        "piece_instance_id": instance_id,
        "label": extra.pop("label", instance_id),
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
    piece.update(extra)
    return piece


def _plan():
    return ApprovedPlanRef("PLAN-1", 3, "System", "Approved")


def _prepare(pieces, *, sheet_no=1, existing=None, presets=None, paths=None, order=None, confirmed=False, plan=None):
    return prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=plan or _plan(),
        plan_is_current=True,
        pieces=pieces,
        sheet_no=sheet_no,
        existing=existing,
        operation_presets=presets or {},
        path_overrides=paths or {},
        known_presets={
            "Finish": _raw(preset_name="Finish"),
            "Shallow": _raw(preset_name="Shallow", final_depth_mm=7, pass_depth_mm=2),
            "Wide": _raw(preset_name="Wide", tool_diameter_mm=8),
            "Other": _raw(preset_name="Other", tool_number="T8"),
            "Disabled": _raw(preset_name="Disabled", enabled=False),
        },
        machine_profile={"fingerprint_payload": {}},
        operation_order=order,
        cut_path_early_confirmed=confirmed,
    )


def test_default_order_lists_only_operations_present_on_the_sheet():
    assert DEFAULT_MACHINING_ORDER == (
        "liner",
        "recessed_handle_cutout",
        "back_groove",
        "cut_path",
    )
    catalog = catalog_sheet(1, [_piece("piece-a", extra_liner=1, extra_recessed_handle_cutout=1)])
    assert default_operation_order(catalog.operations) == (
        "liner",
        "recessed_handle_cutout",
        "cut_path",
    )
    assert "back_groove" not in catalog.operations
    illustrative = catalog_sheet(
        1,
        [_piece("piece-b", overlays=[{"kind": "note", "layer": "TEXT", "geometry": {"holes": [[0, 0]]}}])],
    )
    assert illustrative.operations == ("cut_path",)


def test_workspace_lists_every_approved_sheet_and_factory_defaults():
    pieces = [
        _piece("piece-a", sheet_no=1, extra_liner=1),
        _piece("piece-b", sheet_no=2),
    ]
    workspace = build_operational_workspace(
        order_name="DCO-1",
        approved_plan=_plan(),
        plan_is_current=True,
        pieces=pieces,
        saved_files=[],
        factory_defaults={"liner": "Finish", "cut_path": "Shallow"},
        known_presets={},
        machine_profile={"production_approved": False, "source_note": "", "fingerprint_payload": {}},
        can_prepare=True,
    )
    assert [sheet["sheet_no"] for sheet in workspace["sheets"]] == [1, 2]
    first = {row["operation_key"]: row["tool_preset"] for row in workspace["sheets"][0]["operations"]}
    assert first["liner"] == "Finish"
    assert first["cut_path"] == "Shallow"
    assert [row["operation_key"] for row in workspace["sheets"][0]["operations"]] == ["liner", "cut_path"]
    assert workspace["sheets"][1]["operations"][0]["operation_key"] == "cut_path"
    assert workspace["can_prepare"] is True


def test_path_override_is_kept_when_the_layer_preset_changes_and_can_be_cleared():
    piece = _piece("piece-a", extra_liner=1)
    path_key = "liner:piece-a:liner_1"
    custom = _prepare(
        [piece],
        presets={"liner": "Finish", "cut_path": "Finish"},
        paths={path_key: "Shallow"},
        order=["liner", "cut_path"],
    )
    saved_path = next(row for row in custom["paths"] if row["path_key"] == path_key)
    assert saved_path["tool_preset"] == "Shallow"
    layer = next(row for row in custom["operations"] if row["operation_key"] == "liner")
    assert layer["tool_preset"] == "Finish"

    changed_layer = _prepare(
        [piece],
        presets={"liner": "Finish", "cut_path": "Finish"},
        paths={path_key: "Shallow"},
        order=["liner", "cut_path"],
    )
    assert next(row for row in changed_layer["paths"] if row["path_key"] == path_key)["tool_preset"] == "Shallow"

    reset = _prepare(
        [piece],
        presets={"liner": "Finish", "cut_path": "Finish"},
        paths={},
        order=["liner", "cut_path"],
    )
    assert next(row for row in reset["paths"] if row["path_key"] == path_key)["tool_preset"] == ""
    assert next(row for row in reset["paths"] if row["path_key"] == path_key)["piece_label"] == "piece-a"


def test_operation_order_is_saved_per_sheet_and_an_early_cut_needs_confirmation():
    pieces = [
        _piece("piece-a", sheet_no=1, extra_liner=1),
        _piece("piece-b", sheet_no=2, extra_liner=1),
    ]
    with pytest.raises(OperationalFileError) as warning:
        _prepare(
            pieces,
            sheet_no=1,
            presets={"liner": "Finish", "cut_path": "Finish"},
            order=["cut_path", "liner"],
            confirmed=False,
        )
    assert warning.value.code == "cut_path_early_unconfirmed"
    assert cut_path_precedes_internal(("cut_path", "liner")) is True

    first = _prepare(
        pieces,
        sheet_no=1,
        presets={"liner": "Finish", "cut_path": "Finish"},
        order=["cut_path", "liner"],
        confirmed=True,
    )
    second = _prepare(
        pieces,
        sheet_no=2,
        presets={"liner": "Finish", "cut_path": "Finish"},
    )
    assert [row["operation_key"] for row in first["operations"]] == ["cut_path", "liner"]
    assert [row["sequence"] for row in first["operations"]] == [1, 2]
    assert first["cut_path_early_confirmed"] is True
    assert [row["operation_key"] for row in second["operations"]] == ["liner", "cut_path"]
    assert second["cut_path_early_confirmed"] is False
    assert first["cutting_plan"] == "PLAN-1"
    assert first["plan_revision"] == 3

    restored = _prepare(
        pieces,
        sheet_no=1,
        existing={
            "operations": first["operations"],
            "paths": first["paths"],
            "cut_path_early_confirmed": True,
        },
        presets={"liner": "Finish", "cut_path": "Finish"},
        paths={row["path_key"]: row["tool_preset"] for row in first["paths"] if row["tool_preset"]},
    )
    assert [row["operation_key"] for row in restored["operations"]] == ["cut_path", "liner"]
    assert restored["cut_path_early_confirmed"] is True


def test_sheet_settings_reject_a_disabled_preset_a_tool_conflict_and_a_stale_plan():
    piece = _piece("piece-a", extra_back_groove=1)
    with pytest.raises(OperationalFileError) as disabled:
        _prepare(
            [piece],
            presets={"cut_path": "Disabled", "back_groove": "Disabled"},
            order=["back_groove", "cut_path"],
        )
    assert disabled.value.code == "preset_disabled"

    with pytest.raises(OperationalFileError) as diameter:
        _prepare(
            [piece],
            presets={"cut_path": "Finish", "back_groove": "Finish"},
            paths={"back_groove:piece-a:primary": "Wide"},
            order=["back_groove", "cut_path"],
        )
    assert diameter.value.code == "tool_diameter_conflict"

    with pytest.raises(OperationalFileError) as number:
        _prepare(
            [piece],
            presets={"cut_path": "Finish", "back_groove": "Other"},
            order=["back_groove", "cut_path"],
        )
    assert number.value.code == "tool_identity_conflict"

    plan = _plan()
    assert_viewed_plan_token(plan, "PLAN-1::3")
    with pytest.raises(OperationalFileError) as stale:
        assert_viewed_plan_token(plan, "PLAN-1::2")
    assert stale.value.code == "plan_not_current"
    with pytest.raises(OperationalFileError) as replaced:
        assert_viewed_plan_token(plan, "PLAN-OLD::3")
    assert replaced.value.code == "plan_not_current"


def test_board_layout_keeps_placement_and_drops_financial_fields():
    layout = operational_board_layout(
        {
            "approved_cost": 50,
            "full_board_width_cm": 122,
            "full_board_length_cm": 244,
            "sheets": [
                {
                    "sheet_no": 1,
                    "pieces": [
                        {
                            "id": 1,
                            "label": "1.1",
                            "x": 1,
                            "y": 2,
                            "w": 10,
                            "h": 20,
                            "special_shape_price_usd": 9,
                        }
                    ],
                }
            ],
        }
    )
    assert layout["full_board_width_cm"] == 122
    piece = layout["sheets"][0]["pieces"][0]
    assert piece["x"] == 1
    assert "approved_cost" not in layout
    assert "special_shape_price_usd" not in piece


def test_phase2_surface_does_not_generate_nc_or_recompute_cutting():
    service = SERVICE.read_text(encoding="utf-8")
    signature = service.split("def save_cnc_operational_sheet", 1)[1].split(") ->", 1)[0]
    assert "viewed_plan_token" in signature
    assert "operation_order" in signature
    assert "cutting_plan" not in signature
    assert "Capability.PREPARE_CNC_OPERATIONAL_FILES" in service
    assert "Capability.VIEW_CNC_OPERATIONAL_FILES" in service
    assert "approve_cutting_plan" not in service
    assert "export_dxf" not in service
    for path in NESTING.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cnc_operational" not in text

    panel = PANEL.read_text(encoding="utf-8")
    assert "AlmdinaCuttingPlanRender.build" in panel
    assert "data-path-key" in panel
    assert "Move earlier" in panel
    assert "draggable" in panel
    assert "Cutting first may let the pieces move" in panel
    assert "G01" not in panel
    assert ".nc" not in panel
    assert "Download" not in panel
    assert Capability.VIEW_CNC_OPERATIONAL_FILES
