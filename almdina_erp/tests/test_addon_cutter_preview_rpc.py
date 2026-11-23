"""The preview RPC is registered. The refusal helper is not an endpoint."""

from __future__ import annotations

from types import SimpleNamespace

import frappe

from almdina_erp.almdina_erp.services import cutting_plan_preview_service as service


def test_preview_cutting_plan_is_whitelisted_and_the_helper_is_not():
    assert service.preview_cutting_plan in frappe.whitelisted
    assert service.preview_cutting_plan.__name__ == "preview_cutting_plan"
    assert service._rejected_addon_preview not in frappe.whitelisted
    registered = {fn.__name__ for fn in frappe.whitelisted}
    assert "preview_cutting_plan" in registered
    assert "_rejected_addon_preview" not in registered


def test_an_authorized_preview_call_returns_the_plan(monkeypatch):
    frappe.local.session = frappe._dict(user="Administrator")
    order = SimpleNamespace(
        name="DCO-AUTH",
        doctype="Door Cutting Order",
        docstatus=0,
        status="Draft",
        revision_state="Current",
        approved_plan=None,
        current_production_stage=None,
        production_path=None,
        check_permission=lambda *_args, **_kwargs: None,
    )
    source = SimpleNamespace(
        name="CP-1",
        revision=2,
        modified="2026-11-22",
        optimization_mode="smart",
        machine_type="CNC Router",
        kerf_mm=4,
        trim_margin_mm=0,
        optimization_time_limit_sec=5,
        deduct_edge_thickness=1,
    )
    session = SimpleNamespace(
        version=2,
        preview_id="preview-auth",
        order_name="DCO-AUTH",
        source_plan_name="CP-1",
        source_plan_modified="2026-11-22",
        settings_fingerprint="settings",
        input_fingerprint="input",
        search_round=0,
        settings={"optimization_time_limit_sec": 5},
        expires_at=None,
        candidates={
            "one": {
                "candidate_id": "one",
                "snapshot": {"sheets": []},
                "summary": {"validation": {"status": "Valid"}},
            }
        },
    )

    def get_doc(doctype, name=None):
        assert doctype == "Door Cutting Order"
        assert name == "DCO-AUTH"
        return order

    monkeypatch.setattr(service.frappe, "get_doc", get_doc)
    monkeypatch.setattr(
        service.frappe,
        "get_cached_doc",
        lambda *_args, **_kwargs: SimpleNamespace(
            edge_protection_horizontal_mm=0,
            edge_protection_vertical_mm=0,
            max_centerable_edge_gap_cm=5,
            alignment_search_budget_sec=1,
        ),
    )
    monkeypatch.setattr(service, "_system_draft", lambda *_args, **_kwargs: source)
    monkeypatch.setattr(
        frappe,
        "get_meta",
        lambda _doctype: SimpleNamespace(get_field=lambda _name: SimpleNamespace()),
    )
    monkeypatch.setattr(service, "_build_session", lambda *_args, **_kwargs: session)
    monkeypatch.setattr(service, "_selected_summary", lambda *_args, **_kwargs: {"validation": {"status": "Valid"}})

    result = service.preview_cutting_plan(
        "DCO-AUTH",
        packing_mode="smart",
        cutting_machine_type="CNC Router",
        kerf_mm=4,
        trim_margin_mm=0,
        optimization_time_limit_sec=5,
        deduct_edge_thickness=1,
    )

    assert result["preview_id"] == "preview-auth"
    assert result["order_name"] == "DCO-AUTH"
    assert result["plan"]["sheets"] == []
    assert result["is_preview"] is True
