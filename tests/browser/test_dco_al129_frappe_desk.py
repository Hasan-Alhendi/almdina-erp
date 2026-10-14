from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright


DESK_URL = os.environ.get("FRAPPE_DESK_URL", "").rstrip("/")
FIXTURE_PATH = os.environ.get("DCO_AL129_FIXTURE_FILE", "")
RUNNER_TEMP = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
EVIDENCE_PATH = RUNNER_TEMP / "al129-new-desk-evidence.json"
TRACE_PATH = RUNNER_TEMP / "al129-new-desk-trace.json"
TRACE: list[dict[str, Any]] = []
PAGE_RUNTIME_DIAGNOSTICS: dict[int, list[dict[str, str]]] = {}
NEW_FORM_IDENTITIES: dict[int, dict[str, Any]] = {}
DIAGNOSTIC_REDACTIONS: set[str] = set()


def trace(event: str, **details: Any) -> None:
    record = {"time": round(time.time(), 3), "event": event, **details}
    TRACE.append(record)
    if len(TRACE) > 1600:
        del TRACE[:-1600]
    RUNNER_TEMP.mkdir(parents=True, exist_ok=True)
    TRACE_PATH.write_text(json.dumps(TRACE, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False), flush=True)


def _fixtures() -> dict[str, Any]:
    if not DESK_URL or not FIXTURE_PATH:
        pytest.fail("Pinned Frappe Desk URL and isolated AL129 fixture are required.")
    fixture = json.loads(Path(FIXTURE_PATH).read_text(encoding="utf-8"))
    DIAGNOSTIC_REDACTIONS.update(
        str(fixture[key])
        for key in ("password", "customer", "user", "second_user")
        if fixture.get(key)
    )
    return fixture


def _safe_diagnostic_text(value: str, *, limit: int = 240) -> str:
    result = value.splitlines()[0] if value else ""
    for secret in sorted(DIAGNOSTIC_REDACTIONS, key=len, reverse=True):
        result = result.replace(secret, "[redacted]")
    return result[:limit]


def _browser(playwright_instance) -> Browser:
    executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
    args = ["--no-sandbox", "--disable-dev-shm-usage"] if os.geteuid() == 0 else ["--disable-dev-shm-usage"]
    return playwright_instance.chromium.launch(
        headless=True,
        executable_path=executable,
        args=args,
    )


def _attach_diagnostics(page: Page) -> None:
    diagnostics: list[dict[str, str]] = []
    PAGE_RUNTIME_DIAGNOSTICS[id(page)] = diagnostics

    def record_runtime_error(kind: str, message: str) -> None:
        diagnostics.append({"kind": kind, "message": _safe_diagnostic_text(message)})
        del diagnostics[:-20]

    def record_page_error(error) -> None:
        message = _safe_diagnostic_text(str(error), limit=700)
        record_runtime_error("pageerror", message)
        trace("page_error", message=message)

    page.on(
        "requestfailed",
        lambda request: record_failed_request(request, diagnostics),
    )

    def record_console_error(message) -> None:
        safe_message = _safe_diagnostic_text(message.text, limit=500)
        record_runtime_error("console_error", safe_message)
        trace("console_error", message=safe_message)

    page.on(
        "console",
        lambda message: record_console_error(message) if message.type == "error" else None,
    )
    page.on("pageerror", record_page_error)
    page.on(
        "response",
        lambda response: record_http_error(response, diagnostics)
        if response.status >= 400
        else None,
    )


def record_failed_request(request, diagnostics: list[dict[str, str]]) -> None:
    path = urlsplit(request.url).path
    failure = _safe_diagnostic_text(str(request.failure or "unknown"))
    diagnostics.append({"kind": "requestfailed", "message": f"{request.method} {path}: {failure}"})
    del diagnostics[:-20]
    trace("request_failed", method=request.method, path=path, failure=failure)


def record_http_error(response, diagnostics: list[dict[str, str]]) -> None:
    path = urlsplit(response.url).path
    message = f"{response.request.method} {path}: HTTP {response.status}"
    diagnostics.append({"kind": "http_error", "message": message})
    del diagnostics[:-20]
    trace("http_error_response", method=response.request.method, path=path, status=response.status)


def _login(page: Page, fixture: dict[str, Any], user: str | None = None) -> None:
    expected_user = user or fixture["user"]
    response = page.goto(f"{DESK_URL}/login", wait_until="domcontentloaded", timeout=60_000)
    assert response is not None and response.status == 200
    current_user = page.evaluate(
        "() => window.frappe && frappe.session ? frappe.session.user : null"
    )
    if current_user == expected_user:
        page.wait_for_function(
            "() => window.frappe && frappe.boot && frappe.boot.sysdefaults "
            "&& Boolean(frappe.boot.sysdefaults.setup_complete) && frappe.router && frappe.app",
            timeout=45_000,
        )
        trace("desk_existing_session_and_boot_ready")
        return
    page.locator("#login_email").fill(expected_user)
    page.locator("#login_password").fill(fixture["password"])
    page.get_by_role("button", name=re.compile(r"^(Login|Continue)$")).click()
    page.wait_for_function(
        "user => window.frappe && frappe.session && frappe.session.user === user",
        arg=expected_user,
        timeout=45_000,
    )
    page.wait_for_function(
        "() => window.frappe && frappe.boot && frappe.boot.sysdefaults "
        "&& Boolean(frappe.boot.sysdefaults.setup_complete) && frappe.router && frappe.app",
        timeout=45_000,
    )
    trace("desk_login_and_boot_ready")


def _logout_and_login_as(page: Page, fixture: dict[str, Any], user: str) -> None:
    page.evaluate("async () => { await frappe.call('logout'); }")
    page.context.clear_cookies()
    _login(page, fixture, user=user)


def _track_reconciliation_responses(page: Page, statuses: list[str]) -> None:
    def record(response) -> None:
        if "reconcile_new_order_creation" not in response.url:
            return
        try:
            envelope = response.json()
            result = envelope.get("message") if isinstance(envelope, dict) else None
            status = result.get("status") if isinstance(result, dict) else None
            if status:
                statuses.append(str(status))
                trace("creation_reconciliation_response", status=str(status))
        except Exception as error:
            trace("creation_reconciliation_response_unreadable", message=str(error)[:180])

    page.on("response", record)


def _open_new_form(page: Page, suffix: str, *, expected_state: str) -> None:
    if expected_state not in {"ready_for_entry", "awaiting_draft_selection"}:
        raise ValueError(f"Unsupported NEW form state: {expected_state}")
    PAGE_RUNTIME_DIAGNOSTICS.setdefault(id(page), []).clear()
    response = page.goto(
        f"{DESK_URL}/app/door-cutting-order/new-door-cutting-order-al129-{suffix}",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    trace("new_form_navigation_response", status=response.status if response else None)
    page.wait_for_function(
        "() => window.cur_frm && cur_frm.doctype === 'Door Cutting Order' "
        "&& cur_frm.is_new() && cur_frm.fields_dict.pieces_fast_entry "
        "&& cur_frm.fields_dict.pieces_fast_entry.$wrapper",
        timeout=60_000,
    )
    if expected_state == "awaiting_draft_selection":
        page.wait_for_function(
            "() => { const modal = document.querySelector('.modal.show');"
            " return Boolean(modal && modal.querySelector('[data-recovery-action=\"continue\"]')"
            " && modal.querySelector('[data-recovery-action=\"new\"]')); }",
            timeout=30_000,
        )
        state = page.evaluate(
            "() => ({name: cur_frm.doc.name, doctype: cur_frm.doctype,"
            " isNew: Boolean(cur_frm.is_new()),"
            " continueActions: document.querySelectorAll("
            "'.modal.show [data-recovery-action=\"continue\"]').length,"
            " newActions: document.querySelectorAll("
            "'.modal.show [data-recovery-action=\"new\"]').length})"
        )
        trace(
            "real_new_dco_awaiting_draft_selection",
            name=state["name"],
            doctype=state["doctype"],
            is_new=state["isNew"],
            continue_actions=state["continueActions"],
            new_actions=state["newActions"],
            checkpoint_not_required=True,
        )
        assert state["isNew"] is True
        assert state["continueActions"] >= 1 and state["newActions"] == 1
        NEW_FORM_IDENTITIES[id(page)] = {"name": state["name"], "is_new": state["isNew"]}
        return

    page.wait_for_function(
        "() => window.AlmdinaDcoRecovery && AlmdinaDcoRecovery.LocalCheckpoint "
        "&& AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm)",
        timeout=30_000,
    )
    expect(page.locator("[data-fieldname='pieces_fast_entry'] .dco-fast-table")).to_be_visible(
        timeout=30_000
    )
    state = page.evaluate(
        "() => ({name: cur_frm.doc.name, doctype: cur_frm.doctype,"
        " isNew: Boolean(cur_frm.is_new()),"
        " checkpoint: Boolean(AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm)),"
        " discoveryVisible: Boolean(document.querySelector("
        "'.modal.show [data-recovery-action=\"continue\"]'))})"
    )
    trace(
        "real_new_dco_form_ready",
        name=state["name"],
        doctype=state["doctype"],
        is_new=state["isNew"],
        checkpoint=state["checkpoint"],
        discovery_visible=state["discoveryVisible"],
    )
    assert state["isNew"] is True and state["checkpoint"] is True
    assert state["discoveryVisible"] is False
    NEW_FORM_IDENTITIES[id(page)] = {"name": state["name"], "is_new": state["isNew"]}


def _read_local_drafts(page: Page) -> dict[str, Any]:
    return page.evaluate(
        "async () => {"
        " const repo = window.AlmdinaDcoRecovery.LocalDraftRepository.create();"
        " const identity = {site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
        " user: frappe.session.user, target_doctype: 'Door Cutting Order'};"
        " const result = await repo.discover(identity);"
        " if (!result.ok) throw new Error(result.error.code);"
        " return {identity, records: result.value.records};"
        "}"
    )


def _set_link(page: Page, fieldname: str, value: str) -> None:
    if fieldname == "customer":
        state = page.evaluate(
            "() => {"
            " const frm = window.cur_frm;"
            " const field = frm && frm.fields_dict && frm.fields_dict.customer;"
            " const unwrap = value => value && typeof value.get === 'function'"
            " ? value.get(0) : (value && value[0]) || value || null;"
            " const wrapper = unwrap(field && field.$wrapper);"
            " const input = unwrap(field && field.$input);"
            " const visible = node => { if (!node || !node.isConnected) return false;"
            " const style = getComputedStyle(node); return node.getClientRects().length > 0"
            " && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'; };"
            " const matches = [...document.querySelectorAll(\"[data-fieldname='customer'] input\")];"
            " const modals = [...document.querySelectorAll('.modal.show')].filter(visible);"
            " const activeTabs = [...document.querySelectorAll('.nav-link.active, .tab-pane.active')]"
            " .map(node => ({kind: node.matches('.tab-pane') ? 'pane' : 'tab',"
            " label: (node.getAttribute('aria-label') || node.textContent || '').trim().slice(0, 80),"
            " fieldname: node.getAttribute('data-fieldname'), visible: visible(node)}));"
            " const route = window.frappe && typeof frappe.get_route === 'function'"
            " ? frappe.get_route() : null;"
            " const allInputs = [...document.querySelectorAll('input')];"
            " const pane = wrapper && wrapper.closest('.tab-pane');"
            " const formWrapper = unwrap(frm && (frm.$wrapper || frm.wrapper));"
            " return {documentName: frm && frm.doc && frm.doc.name || null,"
            " isNew: Boolean(cur_frm && typeof cur_frm.is_new === 'function' && cur_frm.is_new()),"
            " doctype: frm && frm.doctype || null,"
            " route: Array.isArray(route) ? route.join('/') : null,"
            " customerFieldExists: Boolean(field),"
            " fieldType: field && field.df && field.df.fieldtype || null,"
            " hidden: field && field.df ? Boolean(field.df.hidden) : null,"
            " readOnly: field ? Boolean(field.read_only || (field.df && field.df.read_only)) : null,"
            " permlevel: field && field.df ? field.df.permlevel : null,"
            " dispStatus: field && field.disp_status || null,"
            " wrapperExists: Boolean(wrapper), wrapperConnected: Boolean(wrapper && wrapper.isConnected),"
            " wrapperVisible: visible(wrapper), wrapperHiddenAttribute: Boolean(wrapper && wrapper.hidden),"
            " tabPaneVisible: pane ? visible(pane) : null,"
            " fieldInputExists: Boolean(input), fieldInputConnected: Boolean(input && input.isConnected),"
            " fieldInputVisible: visible(input), fieldInputTag: input && input.tagName || null,"
            " fieldInputId: input && input.id || null,"
            " fieldInputIndex: input ? allInputs.indexOf(input) : -1,"
            " fieldInputDisabled: input ? Boolean(input.disabled) : null,"
            " fieldInputReadOnly: input ? Boolean(input.readOnly) : null,"
            " fieldInputAriaLabel: input && input.getAttribute('aria-label') || null,"
            " customerDomMatchCount: matches.length,"
            " visibleCustomerDomMatchCount: matches.filter(visible).length,"
            " overlays: modals.map(modal => ({recoveryContinue: modal.querySelectorAll("
            "'[data-recovery-action=\"continue\"]').length, recoveryNew: modal.querySelectorAll("
            "'[data-recovery-action=\"new\"]').length})),"
            " activeTabs, formRendering: Boolean(formWrapper && formWrapper.isConnected),"
            " formVisible: visible(formWrapper),"
            " pageReadyState: document.readyState}; }"
        )
        initial_identity = NEW_FORM_IDENTITIES.get(id(page), {})
        state["identityUnchangedSinceOpen"] = (
            state.get("documentName") == initial_identity.get("name")
            and state.get("isNew") is initial_identity.get("is_new") is True
        )
        state["runtimeErrors"] = PAGE_RUNTIME_DIAGNOSTICS.get(id(page), [])[-12:]
        trace("customer_field_state_before_fill", **state)
        if not state.get("identityUnchangedSinceOpen"):
            raise AssertionError(f"Customer field is not on the NEW document verified by _open_new_form: {state}")
        if (
            state.get("hidden")
            or state.get("readOnly")
            or not state.get("fieldInputVisible")
            or state.get("fieldInputDisabled")
            or state.get("fieldInputReadOnly")
        ):
            raise AssertionError(f"Customer Frappe input is not an enabled visible user control: {state}")

        input_id = state.get("fieldInputId")
        input_index = state.get("fieldInputIndex", -1)
        if isinstance(input_id, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", input_id):
            control = page.locator(f"#{input_id}")
        elif isinstance(input_index, int) and input_index >= 0:
            control = page.locator("input").nth(input_index)
        else:
            raise AssertionError(f"Frappe exposes no addressable visible Customer input: {state}")
        if control.count() != 1 or not control.is_visible():
            raise AssertionError(f"Resolved Customer input is not uniquely visible: {state}")
        is_frappe_customer_input = control.evaluate(
            "node => { const field = window.cur_frm && cur_frm.fields_dict.customer;"
            " const input = field && field.$input;"
            " const element = input && typeof input.get === 'function'"
            " ? input.get(0) : (input && input[0]) || input;"
            " return element === node; }"
        )
        if not is_frappe_customer_input:
            raise AssertionError(f"Resolved locator no longer matches Frappe's Customer control: {state}")
    else:
        control = page.locator(f"[data-fieldname='{fieldname}'] input").first
    control.fill(value)
    suggestions = page.locator(".awesomplete ul li:visible")
    expect(suggestions.first).to_be_visible(timeout=20_000)
    exact = suggestions.filter(has_text=re.compile(rf"^{re.escape(value)}(?:\s|$)"))
    (exact.first if exact.count() else suggestions.first).click()
    page.wait_for_function(
        "({fieldname, value}) => window.cur_frm && cur_frm.doc[fieldname] === value",
        arg={"fieldname": fieldname, "value": value},
        timeout=10_000,
    )


def _fill_header(page: Page, fixture: dict[str, Any], notes: str) -> None:
    _set_link(page, "customer", fixture["customer"])
    page.locator("[data-fieldname='board_description'] input").fill("AL129 recovery test MDF")
    page.locator("[data-fieldname='board_length_cm'] input").fill("244")
    page.locator("[data-fieldname='board_width_cm'] input").fill("122")
    _set_link(page, "default_edge_type", fixture["edge_type"])
    page.locator("[data-fieldname='edge_color'] input").fill("White")
    page.locator("[data-fieldname='order_notes'] textarea").fill(notes)


def _enter_real_measurements(page: Page, count: int) -> list[dict[str, Any]]:
    table = page.locator("[data-fieldname='pieces_fast_entry'] .dco-fast-table")
    expect(table).to_be_visible()
    expected = []
    for index in range(count):
        row = table.locator("tbody tr.dco-virtual-row")
        width = 35 + index % 45
        length = 75 + index % 90
        row.locator("input[data-field='width_cm']").fill(str(width))
        row.locator("input[data-field='width_cm']").press("Tab")
        row.locator("input[data-field='length_cm']").fill(str(length))
        row.locator("input[data-field='length_cm']").press("Enter")
        expected.append({"width_cm": width, "length_cm": length, "qty": 1})
    page.wait_for_function(
        "count => window.cur_frm && cur_frm.doc.pieces.length === count",
        arg=count,
        timeout=30_000,
    )
    trace("fast_entry_completed", pieces=count)
    return expected


def _capture_evidence(payload: dict[str, Any]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if EVIDENCE_PATH.exists():
        try:
            existing = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    existing.update(payload)
    EVIDENCE_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_recovery_record(page: Page, *, draft_id: str, user: str, fixture: dict[str, Any],
                          count: int, with_geometry: bool) -> dict[str, Any]:
    return page.evaluate(
        "async ({draftId, user, fixture, count, withGeometry}) => {"
        " const recovery = window.AlmdinaDcoRecovery;"
        " const rows = Array.from({length: count}, (_, index) => {"
        "   const special = withGeometry && index === 2;"
        "   return {name: 'fixture-piece-' + index, piece_type: special ? 'Special' : 'Regular',"
        "     width_cm: 44 + index % 35, length_cm: 80 + index % 65, qty: 1 + index % 3,"
        "     notes: index === 0 ? 'restored note with long Arabic العربية text' : 'Fixture ' + index,"
        "     extra_liner: index === 0 ? 1 : 0, edge_long_left: index === 0 ? 1 : 0,"
        "     edge_type: fixture.edge_type,"
        "     special_shape_geometry_json: special ? JSON.stringify({version: 1, kind: 'polygon',"
        "       units: 'cm', template: 'rectangle', blank_width_cm: 60, blank_length_cm: 100,"
        "       points: [[0,0],[60,0],[60,100],[0,100]], exact: true}) : ''};"
        " });"
        " const dco = recovery.Projection.createDcoInput({customer: fixture.customer,"
        "   order_date: frappe.datetime.get_today(), order_notes: 'Recovery fixture notes',"
        "   board_description: 'AL129 fixture MDF', board_length_cm: 244, board_width_cm: 122,"
        "   default_edge_type: fixture.edge_type, edge_color: 'White', pieces: rows},"
        "   {pieceKey: row => row.name});"
        " const payload = recovery.Projection.createPayload({dco, dirtyScope: 'DCO'});"
        " const now = new Date().toISOString();"
        " const repo = recovery.LocalDraftRepository.create();"
        " const site = frappe.boot.sitename || frappe.boot.site_name || location.host;"
        " const result = await repo.write({site, user, target_doctype: 'Door Cutting Order',"
        "   draft_id: draftId, tab_session_id: 'al129-fixture-' + draftId, mode: 'NEW',"
        "   dirty_scope: 'DCO', target_name: null, session_origin_modified: null,"
        "   expected_server_modified: null, recovery_revision: 1, expected_recovery_revision: 0,"
        "   created_at: now, captured_at: now, asset_refs: [], payload});"
        " if (!result.ok) throw new Error(result.error.code);"
        " return {revision: result.value.recovery_revision, payload: result.value.payload};"
        "}",
        {"draftId": draft_id, "user": user, "fixture": fixture, "count": count,
         "withGeometry": with_geometry},
    )


def test_real_desk_multiple_drafts_start_new_delete_and_restore_geometry() -> None:
    fixture = _fixtures()
    assert fixture["versions"] == {"frappe": "16.17.5", "erpnext": "16.17.0"}
    assert all(fixture["permission_evidence"].values())
    first_id = str(uuid4())
    retained_id = str(uuid4())
    foreign_id = str(uuid4())
    with sync_playwright() as playwright_instance:
        browser = _browser(playwright_instance)
        context = browser.new_context(viewport={"width": 1800, "height": 1200})
        page = context.new_page()
        _attach_diagnostics(page)
        try:
            _login(page, fixture)
            _open_new_form(page, "multiple-drafts", expected_state="ready_for_entry")
            _seed_recovery_record(
                page, draft_id=first_id, user=fixture["user"], fixture=fixture,
                count=10, with_geometry=False,
            )
            _seed_recovery_record(
                page, draft_id=retained_id, user=fixture["user"], fixture=fixture,
                count=100, with_geometry=True,
            )
            _seed_recovery_record(
                page, draft_id=foreign_id, user="other-user@example.com", fixture=fixture,
                count=1, with_geometry=False,
            )
            _open_new_form(page, "discover-multiple", expected_state="awaiting_draft_selection")
            modal = page.locator(".modal.show").last
            expect(modal.locator("[data-recovery-action='continue']")).to_have_count(2, timeout=30_000)
            expect(modal.locator(f"[data-draft-id='{foreign_id}']")).to_have_count(0)
            trace("multiple_drafts_discovered_with_user_site_scope", visible_count=2)

            first_card = modal.locator(f"[data-draft-id='{first_id}']")
            first_card.locator("[data-recovery-action='delete']").click()
            confirm = page.locator(".modal.show").last
            confirm_button = confirm.get_by_role("button", name=re.compile(r"^(Yes|نعم)$", re.I))
            expect(confirm_button).to_be_visible(timeout=10_000)
            confirm_button.click()
            expect(modal.locator(f"[data-draft-id='{first_id}']")).to_have_count(0, timeout=20_000)
            expect(modal.locator(f"[data-draft-id='{retained_id}']")).to_have_count(1)
            retained = page.evaluate(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const value = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " return value.ok && value.value ? value.value.recovery_revision : null; }",
                retained_id,
            )
            assert retained == 1

            _logout_and_login_as(page, fixture, fixture["second_user"])
            _open_new_form(page, "second-user-scope", expected_state="ready_for_entry")
            second_user_drafts = _read_local_drafts(page)
            assert second_user_drafts["records"] == []
            expect(page.locator(".modal.show [data-recovery-action='continue']")).to_have_count(0)
            trace("browser_user_switch_isolated_first_users_drafts")

            _logout_and_login_as(page, fixture, fixture["user"])
            _open_new_form(page, "return-first-user", expected_state="awaiting_draft_selection")
            modal = page.locator(".modal.show").last
            expect(modal.locator(f"[data-draft-id='{retained_id}']")).to_be_visible(timeout=30_000)

            modal.locator("[data-recovery-action='new']").click()
            page.wait_for_function(
                "() => cur_frm && cur_frm.is_new() && "
                "!document.querySelector('.modal.show [data-recovery-action]')",
                timeout=20_000,
            )
            saved = _read_local_drafts(page)
            assert [item["draft_id"] for item in saved["records"]] == [retained_id]
            trace("start_new_retained_other_users_draft", remaining_count=1)

            _open_new_form(page, "continue-retained", expected_state="awaiting_draft_selection")
            modal = page.locator(".modal.show").last
            expect(modal.locator(f"[data-draft-id='{retained_id}']")).to_be_visible(timeout=30_000)
            modal.locator(f"[data-draft-id='{retained_id}'] [data-recovery-action='continue']").click()
            page.wait_for_function(
                "count => cur_frm && cur_frm.doc.pieces.length === count "
                "&& cur_frm.doc.customer && cur_frm.doc.pieces[2].special_shape_geometry_json",
                arg=100,
                timeout=45_000,
            )
            restored = page.evaluate(
                "() => ({customer: cur_frm.doc.customer, notes: cur_frm.doc.order_notes,"
                " count: cur_frm.doc.pieces.length, firstWidth: cur_frm.doc.pieces[0].width_cm,"
                " specialType: cur_frm.doc.pieces[2].piece_type,"
                " geometry: cur_frm.doc.pieces[2].special_shape_geometry_json,"
                " liner: cur_frm.doc.pieces[0].extra_liner})"
            )
            assert restored["customer"] == fixture["customer"]
            assert restored["notes"] == "Recovery fixture notes"
            assert restored["count"] == 100
            assert restored["firstWidth"] == 44
            assert restored["specialType"] == "Special"
            assert json.loads(restored["geometry"])["exact"] is True
            assert restored["liner"] == 1
            trace("real_desk_restored_100_rows_and_geometry", count=restored["count"])
            _capture_evidence({
                "multi_draft_ui": "PASS",
                "browser_user_switch_isolation": "PASS",
                "geometry_restore_100_rows": "PASS",
            })
        except Exception as error:
            page.screenshot(path=str(RUNNER_TEMP / "al129-desk-failure.png"), full_page=True)
            trace("multi_draft_test_failed", message=str(error)[:900])
            raise
        finally:
            context.close()
            browser.close()


def test_real_desk_100_piece_checkpoint_restore_and_lost_save_response() -> None:
    fixture = _fixtures()
    assert fixture["versions"] == {"frappe": "16.17.5", "erpnext": "16.17.0"}
    assert all(fixture["permission_evidence"].values())
    save_posts: list[dict[str, Any]] = []

    def record_save_request(request) -> None:
        if request.method == "POST" and "frappe.desk.form.save.savedocs" in request.url:
            save_posts.append({"url": urlsplit(request.url).path})
            trace("official_save_request_observed", count=len(save_posts))

    with sync_playwright() as playwright_instance, tempfile.TemporaryDirectory(
        prefix="al129-chromium-profile-"
    ) as profile:
        executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
        args = ["--no-sandbox", "--disable-dev-shm-usage"] if os.geteuid() == 0 else ["--disable-dev-shm-usage"]
        context = playwright_instance.chromium.launch_persistent_context(
            profile,
            viewport={"width": 1800, "height": 1200},
            executable_path=executable,
            args=args,
        )
        page = context.new_page()
        _attach_diagnostics(page)
        page.on("request", record_save_request)
        try:
            _login(page, fixture)
            _open_new_form(page, "create-100", expected_state="ready_for_entry")
            _fill_header(page, fixture, "Recovery notes with عربي طويل\n" + ("Batch note. " * 80))
            expected = _enter_real_measurements(page, 100)
            first_row = page.locator(
                "[data-fieldname='pieces_fast_entry'] .dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)"
            ).first
            first_row.locator("button.dco-addon-toggle[data-check-field='extra_liner']").click()
            first_row.locator("button.dco-check-toggle[data-check-field='edge_long_left']").click()
            first_row.locator("input[data-field='notes']").fill("First piece retained through NEW recovery")
            page.locator("[data-fieldname='order_notes'] textarea").fill(
                "Recovery notes with عربي طويل\n" + ("Batch note. " * 80)
            )
            page.wait_for_function(
                "() => cur_frm.doc.customer && cur_frm.doc.pieces.length === 100 "
                "&& cur_frm.doc.pieces[0].extra_liner === 1 "
                "&& cur_frm.doc.pieces[0].edge_long_left === 1 "
                "&& cur_frm.doc.pieces[0].notes === 'First piece retained through NEW recovery'",
                timeout=20_000,
            )

            page.wait_for_function(
                "async () => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const identity = {site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order'};"
                " const found = await repo.discover(identity);"
                " return found.ok && found.value.records.length === 1 &&"
                " found.value.records[0].payload.dco.pieces.length === 100 &&"
                " found.value.records[0].payload.dco.pieces[0].extra_liner === 1 &&"
                " found.value.records[0].payload.dco.pieces[0].edge_long_left === 1; }",
                timeout=30_000,
            )
            before_save = page.evaluate(
                "async () => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const identity = {site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order'};"
                " const result = await repo.discover(identity);"
                " const record = result.value.records[0];"
                " return {draftId: record.draft_id, revision: record.recovery_revision,"
                " pieces: record.payload.dco.pieces, header: record.payload.dco}; }"
            )
            assert len(before_save["pieces"]) == 100
            assert before_save["pieces"][0]["width_cm"] == expected[0]["width_cm"]
            assert before_save["pieces"][99]["length_cm"] == expected[99]["length_cm"]
            assert before_save["pieces"][0]["extra_liner"] == 1
            assert before_save["pieces"][0]["edge_long_left"] == 1
            assert "عربي طويل" in before_save["header"]["order_notes"]
            assert page.locator(".page-actions .primary-action").count() > 0
            assert save_posts == [], "Checkpointing and reload must not call Official Save"
            trace("checkpoint_payload_acknowledged_no_official_save", pieces=100)
            _capture_evidence({
                "runtime_versions": fixture["versions"],
                "new_ui_checkpoint_100_rows": "PASS",
                "checkpoint_piece_count": len(before_save["pieces"]),
                "official_save_before_user_action": "NONE",
                "dynamic_permission_evidence": fixture["permission_evidence"],
            })

            page.close()
            trace("new_form_page_closed_after_checkpoint")
            page = context.new_page()
            _attach_diagnostics(page)
            page.on("request", record_save_request)
            _login(page, fixture)
            _open_new_form(page, "restore-after-page-close", expected_state="awaiting_draft_selection")
            dialog = page.locator(".modal.show").last
            expect(dialog.locator("[data-recovery-action='continue']")).to_have_count(1)
            dialog.locator("[data-recovery-action='continue']").click()
            page.wait_for_function(
                "({customer, count}) => cur_frm && cur_frm.doc.customer === customer "
                "&& cur_frm.doc.pieces.length === count "
                "&& cur_frm.doc.pieces[0].notes === 'First piece retained through NEW recovery'",
                arg={"customer": fixture["customer"], "count": 100},
                timeout=45_000,
            )
            actual = page.evaluate(
                "() => ({pieceCount: cur_frm.doc.pieces.length, customer: cur_frm.doc.customer,"
                " orderNotes: cur_frm.doc.order_notes, width: cur_frm.doc.pieces[0].width_cm,"
                " lastLength: cur_frm.doc.pieces[99].length_cm, liner: cur_frm.doc.pieces[0].extra_liner,"
                " edge: cur_frm.doc.pieces[0].edge_long_left})"
            )
            assert actual == {
                "pieceCount": 100,
                "customer": fixture["customer"],
                "orderNotes": before_save["header"]["order_notes"],
                "width": expected[0]["width_cm"],
                "lastLength": expected[99]["length_cm"],
                "liner": 1,
                "edge": 1,
            }
            trace("reload_restore_values_verified", pieces=actual["pieceCount"])

            def commit_then_drop_response(route) -> None:
                response = route.fetch(timeout=60_000)
                response_body = response.text()
                if not save_posts:
                    save_posts.append({"url": "frappe.desk.form.save.savedocs"})
                save_posts[-1]["server_status"] = response.status
                trace(
                    "server_save_response_received_by_test_proxy",
                    status=response.status,
                    body_length=len(response_body),
                )
                if response.status != 200:
                    raise AssertionError(f"Native save did not reach the server successfully: {response.status}")
                trace("native_save_committed_response_withheld", status=response.status)
                route.abort("failed")

            page.route("**/api/method/frappe.desk.form.save.savedocs", commit_then_drop_response)
            page.locator(".page-actions .primary-action").filter(has_text=re.compile(r"Save|حفظ")).click()
            page.wait_for_function(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const record = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " return record.ok && record.value &&"
                " record.value.official_save_state === 'PENDING_RECONCILIATION'; }",
                arg=before_save["draftId"],
                timeout=45_000,
            )
            assert len(save_posts) == 1 and save_posts[0]["server_status"] == 200
            pending = page.evaluate(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const read = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " return {state: read.value.official_save_state, token: cur_frm.doc.recovery_creation_token,"
                " revision: read.value.recovery_revision}; }",
                before_save["draftId"],
            )
            assert pending["state"] == "PENDING_RECONCILIATION"
            assert pending["token"] == before_save["draftId"]
            page.unroute("**/api/method/frappe.desk.form.save.savedocs")
            page.close()
            context.close()
            trace("isolated_chromium_profile_closed_after_lost_save_response")

            context = playwright_instance.chromium.launch_persistent_context(
                profile,
                viewport={"width": 1800, "height": 1200},
                executable_path=executable,
                args=args,
            )
            recovery_page = context.new_page()
            _attach_diagnostics(recovery_page)
            recovery_page.on("request", record_save_request)
            _login(recovery_page, fixture)
            recovery_page.goto(f"{DESK_URL}/app/door-cutting-order/new-door-cutting-order-al129-reconcile", wait_until="domcontentloaded", timeout=60_000)
            recovery_page.wait_for_function(
                "() => cur_frm && cur_frm.doctype === 'Door Cutting Order' "
                "&& (cur_frm.is_new() || cur_frm.doc.name.startsWith('DCO-'))",
                timeout=60_000,
            )
            recovery_page.wait_for_function(
                "draftId => cur_frm && !cur_frm.is_new() "
                "&& cur_frm.doc.recovery_creation_token === draftId "
                "&& cur_frm.doc.pieces.length === 100",
                arg=before_save["draftId"],
                timeout=60_000,
            )
            local_after = recovery_page.evaluate(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const identity = {site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId};"
                " const draft = await repo.read(identity);"
                " const docs = await frappe.xcall('frappe.client.get_list', {"
                "  doctype: 'Door Cutting Order', fields: ['name'],"
                "  filters: {recovery_creation_token: draftId}, limit_page_length: 10});"
                " return {remainingDraft: Boolean(draft.ok && draft.value), documents: docs}; }",
                before_save["draftId"],
            )
            assert local_after["remainingDraft"] is False
            assert len(local_after["documents"]) == 1
            assert local_after["documents"][0]["name"] == recovery_page.evaluate("() => cur_frm.doc.name")
            assert len(save_posts) == 1, "Recovery reconciliation must not issue a second Official Save"
            trace("lost_response_reconciled_to_single_native_dco", document_count=1)
            _capture_evidence({
                "same_isolated_chromium_profile_reopened": "PASS",
                "reload_restore_100_rows": "PASS",
                "native_save_response_lost_after_server_commit": "PASS",
                "server_documents_for_creation_token": len(local_after["documents"]),
                "local_pending_checkpoint_cleaned_after_created_proof": not local_after["remainingDraft"],
                "native_save_requests": len(save_posts),
                "single_document_identity": local_after["documents"][0]["name"],
            })

            retry_reconciliation_statuses: list[str] = []
            retry_page = context.new_page()
            _attach_diagnostics(retry_page)
            retry_page.on("request", record_save_request)
            _track_reconciliation_responses(retry_page, retry_reconciliation_statuses)
            _login(retry_page, fixture)
            _open_new_form(retry_page, "same-token-retry", expected_state="ready_for_entry")
            _fill_header(retry_page, fixture, "Same-token retry after confirmed pre-delivery abort")
            _enter_real_measurements(retry_page, 1)
            retry_page.wait_for_function(
                "async () => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const found = await repo.discover({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order'});"
                " return found.ok && found.value.records.length === 1; }",
                timeout=30_000,
            )
            retry_identity = retry_page.evaluate(
                "async () => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const found = await repo.discover({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order'});"
                " const record = found.value.records[0];"
                " return {draftId: record.draft_id, revision: record.recovery_revision}; }"
            )
            first_save_attempts = len(save_posts)

            def abort_before_server(route) -> None:
                trace("native_save_aborted_before_server_delivery")
                route.abort("failed")

            retry_page.route("**/api/method/frappe.desk.form.save.savedocs", abort_before_server)
            retry_page.locator(".page-actions .primary-action").filter(
                has_text=re.compile(r"Save|حفظ")
            ).click()
            retry_page.wait_for_function(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const record = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " return record.ok && record.value &&"
                " record.value.official_save_state === 'PENDING_RECONCILIATION'; }",
                arg=retry_identity["draftId"],
                timeout=30_000,
            )
            pending_retry = retry_page.evaluate(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const record = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " return {state: record.value.official_save_state, revision: record.value.recovery_revision,"
                " attempt: record.value.official_save_attempted_at, token: cur_frm.doc.recovery_creation_token}; }",
                retry_identity["draftId"],
            )
            assert pending_retry == {
                "state": "PENDING_RECONCILIATION",
                "revision": retry_identity["revision"],
                "attempt": pending_retry["attempt"],
                "token": retry_identity["draftId"],
            }
            assert pending_retry["attempt"]
            missing_documents = retry_page.evaluate(
                "draftId => frappe.xcall('frappe.client.get_list', {doctype: 'Door Cutting Order',"
                " fields: ['name'], filters: {recovery_creation_token: draftId}, limit_page_length: 10})",
                retry_identity["draftId"],
            )
            assert missing_documents == [], "the first request was stopped before reaching Frappe"
            retry_page.unroute("**/api/method/frappe.desk.form.save.savedocs")
            retry_page.locator(".page-actions .primary-action").filter(
                has_text=re.compile(r"Save|حفظ")
            ).click()
            retry_page.wait_for_function(
                "() => cur_frm && !cur_frm.is_new() && cur_frm.doc.recovery_creation_token",
                timeout=45_000,
            )
            retry_documents = retry_page.evaluate(
                "draftId => frappe.xcall('frappe.client.get_list', {doctype: 'Door Cutting Order',"
                " fields: ['name'], filters: {recovery_creation_token: draftId}, limit_page_length: 10})",
                retry_identity["draftId"],
            )
            assert len(retry_documents) == 1
            assert retry_page.evaluate("() => cur_frm.doc.recovery_creation_token") == retry_identity["draftId"]
            assert "NOT_FOUND" in retry_reconciliation_statuses
            assert len(save_posts) == first_save_attempts + 2
            retry_local_draft = retry_page.evaluate(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const result = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " return Boolean(result.ok && result.value); }",
                retry_identity["draftId"],
            )
            assert retry_local_draft is False
            _capture_evidence({
                "same_token_retry_after_not_found": "PASS",
                "retry_reconciliation_statuses": retry_reconciliation_statuses,
                "retry_saved_documents_for_token": len(retry_documents),
                "retry_used_original_creation_token": True,
                "retry_attempt_count": 2,
            })
            trace("same_token_not_found_retry_created_one_document")
        except Exception as error:
            try:
                page.screenshot(path=str(RUNNER_TEMP / "al129-desk-failure.png"), full_page=True)
            except Exception:
                pass
            trace("new_save_test_failed", message=str(error)[:900])
            raise
        finally:
            context.close()
