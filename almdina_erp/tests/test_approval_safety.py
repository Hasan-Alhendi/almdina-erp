from __future__ import annotations

from types import SimpleNamespace

import frappe
import pytest

from almdina_erp.almdina_erp.services import cutting_plan_service


def test_core_approve_locks_order_row_before_status_check(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(cutting_plan_service, "require_any_role", lambda *roles: None)

    def fake_sql(query, values=None, **kwargs):
        calls.append(query.lower())
        return []

    def fake_get_doc(doctype, name):
        calls.append("get_doc")
        return SimpleNamespace(name=name, status="Approved")

    monkeypatch.setattr(cutting_plan_service.frappe.db, "sql", fake_sql)
    monkeypatch.setattr(cutting_plan_service.frappe, "get_doc", fake_get_doc)

    with pytest.raises(frappe.ValidationError):
        cutting_plan_service.approve_order("DCO-TEST")

    assert calls
    assert "for update" in calls[0]
    assert calls[1] == "get_doc"


def test_core_reject_locks_order_row_before_status_check(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(cutting_plan_service, "require_any_role", lambda *roles: None)

    def fake_sql(query, values=None, **kwargs):
        calls.append(query.lower())
        return []

    def fake_get_doc(doctype, name):
        calls.append("get_doc")
        return SimpleNamespace(name=name, status="Approved")

    monkeypatch.setattr(cutting_plan_service.frappe.db, "sql", fake_sql)
    monkeypatch.setattr(cutting_plan_service.frappe, "get_doc", fake_get_doc)

    with pytest.raises(frappe.ValidationError):
        cutting_plan_service.reject_order("DCO-TEST", "test")

    assert "for update" in calls[0]
    assert calls[1] == "get_doc"


def test_unplaced_piece_always_blocks_plan_snapshot(monkeypatch):
    order = SimpleNamespace(
        name="DCO-TEST",
        cutting_plan_json=frappe.as_json(
            {
                "validation": {"is_valid": True, "errors": []},
                "unplaced": [{"id": 1, "label": "1.1"}],
                "sheets": [{"sheet_no": 1, "pieces": []}],
            }
        ),
    )

    with pytest.raises(frappe.ValidationError):
        cutting_plan_service.create_plan_from_order(order)
