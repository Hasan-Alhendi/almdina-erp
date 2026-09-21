from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COSTING = ROOT / "public/js/door_cutting_order/costing"
PRESENTER = COSTING / "door_cutting_order_cost_presenter.js"
EDIT_SESSION = COSTING / "door_cutting_order_cost_edit_session_ux.js"
ADAPTER = COSTING / "door_cutting_order_cost_workspace_presenter_adapter.js"


def test_presenter_owns_offcut_price_structure_and_edit_session_only_binds_it():
    presenter = PRESENTER.read_text(encoding="utf-8")
    edit_session = EDIT_SESSION.read_text(encoding="utf-8")

    assert "data-offcut-price-section" in presenter
    assert "data-offcut-price-input" in presenter
    assert "offcut_price_applicable" in presenter

    assert '[data-offcut-price-input]' in edit_session
    assert "dco-offcut-price-editor" not in edit_session
    assert '.find(\".dco-cost-shell\").first().prepend(control)' not in edit_session


def test_every_full_cost_presenter_render_rebinds_an_active_cost_edit_session():
    adapter = ADAPTER.read_text(encoding="utf-8")

    assert "function reconcileActiveCostEditSession(frm)" in adapter
    assert 'typeof editSession.isEditing === "function"' in adapter
    assert "editSession.sync(frm);" in adapter
    assert "function parkHostedCostSettings(frm)" in adapter
    assert "function paintCostHtml(frm, painter)" in adapter

    render_start = adapter.index("paintCostHtml(frm, () => legacy.render(frm))")
    rebind = adapter.index("reconcileActiveCostEditSession(frm);", render_start)
    render_return = adapter.index("return result;", rebind)
    assert render_start < rebind < render_return
    assert "setTimeout(" not in adapter
