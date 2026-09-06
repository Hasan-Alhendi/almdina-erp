from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "notes_service.py"
PANEL = ROOT / "public" / "js" / "notes" / "notes_panel.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(text: str, name: str, next_name: str) -> str:
    return text.split(f"def {name}", 1)[1].split(f"def {next_name}", 1)[0]


def test_optional_customer_permission_probe_uses_silent_capable_frappe_api() -> None:
    service = source(SERVICE)
    body = function_body(service, "_customer_has_read_access", "_linked_customer")

    # Frappe v16 exposes print_logs on frappe.permissions.has_permission, not on
    # the public frappe.has_permission facade. Keep this contract explicit so a
    # future refactor cannot reintroduce the runtime TypeError seen in production.
    assert "import frappe.permissions" in service
    assert "frappe.permissions.has_permission(" in body
    assert "frappe.has_permission(" not in body
    assert 'ptype="read"' in body
    assert "doc=customer" in body
    assert "user=frappe.session.user" in body
    assert "print_logs=False" in body


def test_inaccessible_customer_is_not_published_as_available_context() -> None:
    service = source(SERVICE)
    body = function_body(service, "_customer_notes_payload", "_context")
    inaccessible = body.split("if not customer:", 1)[1].split("notes = _decorate_notes", 1)[0]

    assert '"customer": ""' in inaccessible
    assert '"available": False' in inaccessible
    assert '"notes": []' in inaccessible
    assert '"count": 0' in inaccessible
    assert '"customer": customer_name' not in inaccessible


def test_existing_panel_contract_disables_unavailable_customer_context() -> None:
    panel = source(PANEL)

    assert "const customerDisabled = !state.context || !state.context.customer;" in panel
    assert 'if (state.activeTab === "customer" && !context.customer) state.activeTab = "order";' in panel
    assert 'permissions.can_view_customer_notes === true' in panel


def test_explicit_customer_note_access_still_fails_closed() -> None:
    service = source(SERVICE)
    body = function_body(service, "_linked_customer", "_authorize_reference")

    assert "if required:" in body
    assert "frappe.PermissionError" in body
    assert "لا تملك صلاحية الوصول إلى ملاحظات هذا العميل." in body
