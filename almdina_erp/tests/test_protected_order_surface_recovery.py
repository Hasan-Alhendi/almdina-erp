from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js"
SERVICES = ROOT / "almdina_erp" / "services"


PERMISSION_CONTEXT = PUBLIC / "permission_context.js"
COST_PRESENTER = PUBLIC / "door_cutting_order_cost_presenter.js"
PERMISSION_REFRESH = PUBLIC / "door_cutting_order_permission_refresh_ux.js"
CONTEXT_SERVICE = SERVICES / "permission_context_service.py"


def test_runtime_permission_context_can_be_refreshed_from_server() -> None:
    browser = PERMISSION_CONTEXT.read_text(encoding="utf-8")
    service = CONTEXT_SERVICE.read_text(encoding="utf-8")

    assert "permission_context_service.get_permission_context" in browser
    assert "refresh()" in browser
    assert "almdina:permissions-updated" in browser
    assert "granted_capabilities(user=frappe.session.user)" in service
    assert "build_permission_context" in service


def test_cost_presenter_is_loaded_without_reintroducing_role_gates() -> None:
    context = PERMISSION_CONTEXT.read_text(encoding="utf-8")
    presenter = COST_PRESENTER.read_text(encoding="utf-8")

    assert "/assets/almdina_erp/js/door_cutting_order_cost_presenter.js" in context
    assert "window.AlmdinaOrderCostUX" in presenter
    assert 'can(frm, "view_costs")' in presenter
    assert "canDocument" in presenter
    assert "order_cost_invoice_html" in presenter
    assert "dco-cost-shell" in presenter
    assert "invoiceLines" in presenter
    assert "frappe.user_roles" not in presenter
    assert "Accounts Management" not in presenter
    assert "System Manager" not in presenter


def test_permission_refresh_reapplies_both_protected_surfaces() -> None:
    context = PERMISSION_CONTEXT.read_text(encoding="utf-8")
    refresh = PERMISSION_REFRESH.read_text(encoding="utf-8")

    assert "/assets/almdina_erp/js/door_cutting_order_permission_refresh_ux.js" in context
    assert "AlmdinaCostPermissionsUX" in refresh
    assert "AlmdinaPlanTabsUX" in refresh
    assert "AlmdinaOrderRevisionUX" in refresh
    assert "AlmdinaOrderTabPermissionsUX" in refresh
    assert "permissions.refresh()" in refresh
    assert "applySurfaces(frm)" in refresh
    assert "__almdinaPermissionRefreshPromise" in refresh
