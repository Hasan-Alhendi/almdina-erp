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
PERMISSION_MATRIX = (
    ROOT / "almdina_erp" / "application" / "security" / "permission_matrix.py"
)
PERMISSION_REPOSITORY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "permission_matrix_repository.py"
)
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


def test_cost_field_access_is_projected_from_the_configurable_matrix():
    matrix = _source(PERMISSION_MATRIX)
    repository = _source(PERMISSION_REPOSITORY)
    assert "def field_permission_projection" in matrix
    assert "Capability.VIEW_COSTS" in matrix
    assert "Capability.EDIT_COST_SETTINGS" in matrix
    assert "def _save_field_permission_state" in repository
    assert "field_permission_projection" in repository


def test_cost_ui_hides_and_scrubs_unauthorized_data():
    source = _source(COST_UX)
    assert 'can(frm, "view_costs")' in source
    assert "canDocument" in source
    assert 'setCostTabVisibility(frm, false)' in source
    assert "scrubCostData(frm)" in source
    assert "get_order_cost_snapshot" in source
    assert 'can(frm, "edit_cost_settings")' in source
    assert "configureCostInputFields" in source
    assert "ensurePrintInvoiceButton" in source
    assert "canUseCostTab" in source
    assert "COST_INPUT_FIELDS" in source
    assert 'can(frm, "print_customer_invoice")' in source
    assert 'can(frm, "view_costs") && can(frm, "print_customer_invoice")' not in source
    assert '"edit_special_price"' in source
    assert '"approve_special_price"' in source
    assert "bindInlinePriceInputs" in source
    assert "canEditInlinePiecePrice" in source
    assert "editSessionActive" in source
    assert "flushPendingPriceEdits" in source
    assert "clearPriceOnlyDirty" in source
    assert 'dco-capability-special-price">${__("تعديل السعر")}' not in source
    assert "frappe.prompt" not in source
    assert '__("حفظ السعر")' not in source
    assert "__almdina_pending_price_edit" in source
    assert "preserveEditSessionForPriceSave" not in source
    assert "finalizeAfterPriceSave" not in source
    assert 'frm.doc.costing_currency = "USD"' in source
    assert 'set_df_property(fieldname, "options", "costing_currency")' in source
    assert "return frm.reload_doc();" not in source
    assert "MutationObserver" in source
    assert 'class="btn btn-default btn-sm dco-edit-cost-settings"' not in source
    assert "تعديل إعدادات التكلفة" not in source
    assert "update_order_cost_settings" not in source
    assert "Accounts Management" not in source
    assert "System Manager" not in source


def test_cost_input_fields_live_on_cost_tab():
    schema = json.loads(_source(ORDER_SCHEMA))
    order = schema["field_order"]
    cost_index = order.index("cost_tab")
    currency_index = order.index("costing_currency")
    board_index = order.index("board_rate_usd")
    cutting_index = order.index("cutting_cost_per_board_usd")
    html_index = order.index("order_cost_invoice_html")
    assert cost_index < currency_index < board_index < cutting_index < html_index
    assert "board_rate_usd" not in order[:order.index("pieces_section")]
    fields = {field["fieldname"]: field for field in schema["fields"]}
    assert fields["costing_currency"]["default"] == "USD"
    assert fields["board_rate_usd"]["options"] == "costing_currency"
    assert fields["cutting_cost_per_board_usd"]["options"] == "costing_currency"


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
