from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_ux.js"
)


def test_plan_presenter_delegates_commands_and_fails_closed() -> None:
    source = PLAN_UX.read_text(encoding="utf-8")

    assert "AlmdinaPlanWorkspaceState" in source
    assert "AlmdinaPlanControlsUX" in source
    assert "controls.runRecalculation(frm)" in source
    assert "upload_production_dxf" in source
    assert "export_order_dxf" in source

    # A5.2 forbids the legacy DCO-owned command fallbacks from returning.
    assert 'frm.set_value("packing_mode"' not in source
    assert "new frappe.ui.FileUploader" not in source
    assert "frm.reload_doc" not in source
    assert "frm.save(" not in source
    assert "frm.call(" not in source
    assert "frappe.call(" not in source
    assert "recalculate_cutting_plan" not in source
    assert "shop_floor_service.upload_production_dxf" not in source


def test_plan_presenter_does_not_restore_duplicate_algorithm_buttons() -> None:
    source = PLAN_UX.read_text(encoding="utf-8")

    assert ".dco-recalculate-plan" in source
    assert ".dco-print-cutting-plan" in source
    assert ".dco-export-dxf" in source
    assert ".dco-upload-dxf-plan" in source
    assert "إعادة الحساب بالإعدادات الحالية" in source

    for retired in (
        ".dco-auto-pro-plan",
        ".dco-deep-plan",
        ".dco-optimal-plan",
        ".dco-algorithm-palette",
    ):
        assert retired not in source
