from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
SERVICE = ROOT / "almdina_erp" / "services" / "order_kanban_service.py"
LIST_VIEW = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_list.js"
)


def test_status_kanban_mutations_are_blocked_at_the_server_boundary() -> None:
    hooks = runpy.run_path(str(HOOKS))
    overrides = hooks["override_whitelisted_methods"]
    prefix = "frappe.desk.doctype.kanban_board.kanban_board."
    target = "almdina_erp.almdina_erp.services.order_kanban_service."
    assert overrides[prefix + "update_order"] == target + "update_order"
    assert (
        overrides[prefix + "update_order_for_single_card"]
        == target + "update_order_for_single_card"
    )
    assert overrides[prefix + "add_card"] == target + "add_card"

    service = SERVICE.read_text(encoding="utf-8")
    assert 'board.reference_doctype == _ORDER_DOCTYPE' in service
    assert 'board.field_name == _STATUS_FIELD' in service
    assert "frappe.throw(_BLOCKED_MESSAGE" in service


def test_status_kanban_is_read_only_without_frontend_database_writes_or_timers() -> None:
    source = LIST_VIEW.read_text(encoding="utf-8")
    assert 'sortable.option("disabled", true)' in source
    assert 'find(".add-card, .new-card-area").remove()' in source
    assert "frappe.db.set_value" not in source
    hydration = source.split("function hydrateStatusFilterOptions", 1)[1].split(
        "function reconcileStatusFilterLayout", 1
    )[0]
    assert "setTimeout" not in hydration
