from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)
METADATA = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "order_cost_surface_metadata.py"
)
LIFECYCLE = ROOT / "lifecycle.py"
COST_SERVICE = ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
COST_EDIT_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_cost_edit_session_ux.js"
)


COST_FIELDS = ("board_rate_usd", "cutting_cost_per_board_usd")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cost_inputs_are_not_native_mandatory_on_initial_order_save() -> None:
    doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in doc["fields"]}

    for fieldname in COST_FIELDS:
        assert not fields[fieldname].get("reqd")
        assert fields[fieldname].get("permlevel") == 1


def test_migration_repairs_stale_required_cost_metadata_only() -> None:
    source = _source(METADATA)
    lifecycle = _source(LIFECYCLE)

    assert 'COST_INPUT_FIELDS = (' in source
    assert '"board_rate_usd"' in source
    assert '"cutting_cost_per_board_usd"' in source
    assert '"property": "reqd"' in source
    assert "set reqd = 0" in source
    assert "frappe.clear_cache(doctype=DOCTYPE)" in source
    assert "permlevel" not in source
    assert "sync_order_cost_surface_metadata()" in lifecycle


def test_cost_workspace_save_keeps_both_values_mandatory() -> None:
    service = _source(COST_SERVICE)
    ux = _source(COST_EDIT_UX)

    assert "def _required_cost_input" in service
    assert '_("سعر اللوح")' in service
    assert '_("أجور القص / لوح")' in service
    assert "board_rate_usd: float | None = None" in service
    assert "cutting_cost_per_board_usd: float | None = None" in service

    assert "validateRequiredCostSettings" in ux
    assert 'board_rate_usd: "سعر اللوح"' in ux
    assert 'cutting_cost_per_board_usd: "أجور القص / لوح"' in ux
    assert 'control.attr("required", "required")' in ux
    assert "if (!validateRequiredCostSettings(frm, state.draft || {})) return false;" in ux
    assert "api.saveSettings(frm.doc.name, state.draft || {})" in ux


def test_cost_workspace_validation_does_not_make_whole_order_required() -> None:
    ux = _source(COST_EDIT_UX)
    service = _source(COST_SERVICE)

    assert 'frm.set_df_property("board_rate_usd", "reqd"' not in ux
    assert 'frm.set_df_property("cutting_cost_per_board_usd", "reqd"' not in ux
    assert "order.save(" not in service.split("def update_order_cost_settings", 1)[1].split(
        "def approve_special_piece_price", 1
    )[0]
