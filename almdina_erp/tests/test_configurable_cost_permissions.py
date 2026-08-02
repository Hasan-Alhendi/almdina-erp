from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORDER_SCHEMA = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)
COST_SERVICE = ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
COST_UX = ROOT / "public" / "js" / "door_cutting_order_cost_permissions_ux.js"
HOOKS = ROOT / "hooks.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cost_fields_keep_permlevel_without_fixed_role_grants():
    schema = json.loads(_source(ORDER_SCHEMA))
    cost_fields = {
        "board_rate_usd",
        "cutting_cost_per_board_usd",
        "mdf_cost_usd",
        "cutting_cost_usd",
        "edge_cost_usd",
        "total_cost_usd",
        "customer_quote_total_usd",
        "customer_quote_status",
        "internal_loss_cost_usd",
        "actual_cost_usd",
    }
    fields = {field["fieldname"]: field for field in schema["fields"]}
    assert all(fields[fieldname].get("permlevel") == 1 for fieldname in cost_fields)
    assert not [
        permission
        for permission in schema["permissions"]
        if permission.get("permlevel") == 1
    ]


def test_cost_service_uses_capabilities_instead_of_role_names():
    source = _source(COST_SERVICE)
    assert "Capability.VIEW_COSTS" in source
    assert "Capability.EDIT_COST_SETTINGS" in source
    assert "Capability.EDIT_SPECIAL_PRICE" in source
    assert "Capability.APPROVE_SPECIAL_PRICE" in source
    assert "require_document_capability" in source
    assert "get_order_cost_snapshot" in source
    assert "Accounts Management" not in source
    assert "System Manager" not in source
    assert "frappe.get_roles" not in source


def test_cost_ui_hides_and_scrubs_unauthorized_data():
    source = _source(COST_UX)
    assert 'can(frm, "view_costs")' in source
    assert "canDocument" in source
    assert 'setCostTabVisibility(frm, false)' in source
    assert "scrubCostData(frm)" in source
    assert "get_order_cost_snapshot" in source
    assert 'can(frm, "edit_cost_settings")' in source
    assert 'can(frm, "print_customer_invoice")' in source
    assert '"edit_special_price"' in source
    assert '"approve_special_price"' in source
    assert "MutationObserver" in source
    assert "Accounts Management" not in source
    assert "System Manager" not in source


def test_hooks_route_legacy_price_api_to_capability_service():
    source = _source(HOOKS)
    assert '"public/js/door_cutting_order_cost_permissions_ux.js"' in source
    assert (
        '"almdina_erp.almdina_erp.services.special_shape_service.approve_special_piece_price"'
        in source
    )
    assert (
        '"almdina_erp.almdina_erp.services.cost_permission_service.approve_special_piece_price"'
        in source
    )
