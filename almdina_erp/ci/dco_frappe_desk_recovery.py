from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Page, expect, sync_playwright


DESK_URL = os.environ["FRAPPE_DESK_URL"].rstrip("/")
FIXTURES = json.loads(Path(os.environ["DCO_DESK_FIXTURE_FILE"]).read_text(encoding="utf-8"))
DIAGNOSTIC_EVENTS: dict[str, list[dict[str, str | int | None]]] = {
    "console": [],
    "page_errors": [],
    "request_failures": [],
    "responses": [],
}
BROWSER_TRACE: list[dict[str, str | int | float | None]] = []


def _redact_text(value: str, limit: int = 1000) -> str:
    scrubbed = re.sub(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+", "Authorization: Bearer REDACTED", value)
    scrubbed = re.sub(
        r"(?i)\b(password|passwd|pwd|access[_-]?token|token|authorization|cookie|secret|session[_-]?id|sid)\b"
        r"([\s\"']*[:=][\s\"']*)([^\s,;\"']+)",
        r"\1\2REDACTED",
        scrubbed,
    )
    return scrubbed[:limit]


def _trace_event(event: str, **details: str | int | float | None) -> None:
    BROWSER_TRACE.append({"time": round(time.time(), 3), "event": event, **details})
    if len(BROWSER_TRACE) > 500:
        del BROWSER_TRACE[:-500]


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    query_keys = sorted({part.split("=", 1)[0] for part in parsed.query.split("&") if part})
    query = "?" + "&".join(f"{key}=REDACTED" for key in query_keys) if query_keys else ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{query}"


def attach_browser_diagnostics(page: Page) -> None:
    def append(bucket: str, item: dict[str, str | int | None]) -> None:
        events = DIAGNOSTIC_EVENTS[bucket]
        events.append(item)
        if len(events) > 100:
            del events[:-100]

    page.on("framenavigated", lambda frame: _trace_event(
        "navigation", url=_safe_url(frame.url)
    ) if frame == page.main_frame else None)
    page.on("console", lambda message: (append("console", {
        "type": message.type,
        "text": _redact_text(message.text),
        "location": _safe_url(message.location.get("url", "")) if message.location.get("url") else "",
    }), _trace_event("console", type=message.type, text=_redact_text(message.text)))
        if message.type in {"error", "warning"} else None)
    page.on("pageerror", lambda error: (append("page_errors", {"text": _redact_text(str(error))}),
        _trace_event("page_error", text=_redact_text(str(error)))))
    page.on("requestfailed", lambda request: (append("request_failures", {
        "url": _safe_url(request.url),
        "resource_type": request.resource_type,
        "failure": _redact_text(str(request.failure), 500) if request.failure else "unknown",
    }), _trace_event("request_failed", url=_safe_url(request.url),
        resource_type=request.resource_type,
        failure=_redact_text(str(request.failure), 500) if request.failure else "unknown")))
    page.on("response", lambda response: (append("responses", {
        "url": _safe_url(response.url),
        "status": response.status,
        "resource_type": response.request.resource_type,
        "content_type": response.headers.get("content-type", "")[:120],
    }), _trace_event("response", url=_safe_url(response.url), status=response.status,
        resource_type=response.request.resource_type))
        if response.request.resource_type in {"document", "script", "xhr", "fetch"}
        or response.status >= 400 else None)


def evaluate(page: Page, step: str, expression: str, arg=None):
    try:
        return page.evaluate(expression) if arg is None else page.evaluate(expression, arg)
    except Exception as exc:
        raise RuntimeError(f"Desk browser step '{step}' failed: {exc}") from exc


def wait_for_function(page: Page, step: str, expression: str, *, arg=None, timeout: int = 30_000):
    try:
        page.wait_for_function(expression, arg=arg, timeout=timeout)
    except Exception as exc:
        try:
            state = page.evaluate(
                """() => {
                    const frm = window.cur_frm;
                    const coordinator = window.AlmdinaDcoEditSessionCoordinator;
                    const session = frm && coordinator && coordinator.snapshot(frm);
                    return {
                        url: window.location.href,
                        route: window.frappe && frappe.get_route && frappe.get_route(),
                        form: frm && frm.doc ? {
                            name: frm.doc.name,
                            status: frm.doc.status,
                            order_notes: frm.doc.order_notes,
                            dirty: frm.is_dirty(),
                        } : null,
                        editSession: session && {
                            phase: session.phase,
                            activeKind: session.activeKind,
                            sessionGeneration: session.sessionGeneration,
                        },
                        recoveryButtons: [...document.querySelectorAll('[data-edit-recovery-action="continue"]')]
                            .map(button => ({disabled: button.disabled, text: button.innerText})).slice(-4),
                        visibleModals: [...document.querySelectorAll('.modal.show')]
                            .map(modal => (modal.innerText || '').slice(-500)).slice(-4),
                        alerts: [...document.querySelectorAll('.msgprint, .alert, .modal .modal-body')]
                            .map(item => (item.innerText || '').slice(-500)).slice(-4),
                    };
                }"""
            )
        except Exception as diagnostic_error:
            state = f"unavailable: {diagnostic_error}"
        raise RuntimeError(f"Desk browser wait '{step}' failed: {exc}; desk_state={state}") from exc


def open_dco(page: Page, name: str) -> None:
    target_url = f"{DESK_URL}/app/door-cutting-order/{name}"
    response = page.goto(target_url, wait_until="domcontentloaded")
    if response is None or response.status >= 400:
        status = response.status if response is not None else None
        raise RuntimeError(f"DCO navigation returned HTTP {status}: {_safe_url(page.url)}")
    try:
        wait_for_function(page, f"load DCO {name}",
            "name => window.cur_frm && window.cur_frm.doc && window.cur_frm.doc.name === name",
            arg=name,
            timeout=60_000,
        )
    except Exception as exc:
        state = evaluate(page, f"load DCO {name} diagnostics",
            """() => ({
                url: window.location.href,
                route: window.frappe && window.frappe.get_route && window.frappe.get_route(),
                user: window.frappe && window.frappe.session && window.frappe.session.user,
                body: (document.body && document.body.innerText || '').slice(0, 1200),
            })"""
        )
        raise RuntimeError(
            f"Loading DCO {name} in Desk timed out: {exc}; desk_state={state}"
        ) from exc


def start_edit_and_set_note(page: Page, name: str, value: str, checkpoint: bool) -> dict:
    return evaluate(page, f"start EDIT for {name}",
        """async ({name, value, checkpoint}) => {
            const frm = window.cur_frm;
            const coordinator = window.AlmdinaDcoEditSessionCoordinator;
            const recovery = window.AlmdinaDcoRecovery.LocalCheckpoint;
            if (!frm || frm.doc.name !== name || !coordinator || !recovery) {
                throw new Error('Frappe Desk DCO recovery assets are not ready');
            }
            const started = await coordinator.start(frm, 'order');
            if (!started) throw new Error('The actual EDIT session did not start');
            await frm.set_value('order_notes', value);
            if (!checkpoint) return {started, dirty: frm.is_dirty()};
            if (!recovery.ensureState(frm)) throw new Error('EDIT checkpoint session was not created');
            if (!recovery.markDirty(frm, 'DCO')) throw new Error('EDIT checkpoint was not marked dirty');
            const flushed = await recovery.flush(frm);
            if (!flushed || !flushed.ok) throw new Error('IndexedDB checkpoint flush failed');
            const found = await recovery.repository().discover({
                site: String(frappe.boot && (frappe.boot.sitename || frappe.boot.site_name)
                    || window.location.host || '').trim(),
                user: String(frappe.session && frappe.session.user || '').trim(),
                target_doctype: 'Door Cutting Order',
                mode: 'EDIT',
                target_name: name,
            });
            if (!found || !found.ok || !found.value.records.length) {
                throw new Error(`IndexedDB EDIT snapshot was not readable: ${found && found.error && found.error.code || 'no_record'}`);
            }
            return {
                started,
                dirty: frm.is_dirty(),
                draftId: found.value.records[0].draft_id,
                expectedServerModified: found.value.records[0].expected_server_modified,
            };
        }""",
        {"name": name, "value": value, "checkpoint": checkpoint},
    )


def certify_actual_frappe_desk_edit_recovery(page: Page) -> None:
    response = page.goto(f"{DESK_URL}/login", wait_until="domcontentloaded")
    if response is None or response.status >= 400:
        status = response.status if response is not None else None
        raise RuntimeError(f"Frappe login page returned HTTP {status}: {_safe_url(page.url)}")
    page.locator("#login_email").wait_for(state="visible", timeout=15_000)
    page.locator("#login_email").fill("Administrator")
    page.locator("#login_password").fill("admin")
    page.get_by_role("button", name=re.compile(r"^(Login|Continue)$")).click()
    try:
        wait_for_function(page, "Administrator login establishes a Desk session",
            "() => window.frappe && frappe.session && frappe.session.user === 'Administrator'",
            timeout=60_000,
        )
    except Exception as exc:
        raise RuntimeError(f"Desk login did not establish an Administrator session: {exc}") from exc

    _trace_event("login_established", user="Administrator")

    # A route selected on a Draft is not dispatch. Exercise the real edit-session
    # Cancel and Save adapters, and the real IndexedDB restore dialog.
    name = FIXTURES["restore"]
    baseline = page.request.get(
        f"{DESK_URL}/api/method/frappe.client.get?doctype=Door%20Cutting%20Order&name={name}"
    ).json()["message"]["order_notes"]
    open_dco(page, name)
    cancelled = "Desk cancel must not persist"
    start_edit_and_set_note(page, name, cancelled, checkpoint=False)
    evaluate(page, "cancel EDIT session", "() => window.AlmdinaDcoEditSessionCoordinator.cancel(window.cur_frm, 'order')")
    wait_for_function(page, "Cancel returns EDIT session to idle",
        "baseline => window.cur_frm && window.cur_frm.doc.order_notes === baseline && "
        "window.AlmdinaDcoEditSessionCoordinator.snapshot(window.cur_frm).phase === 'idle'",
        arg=baseline,
        timeout=30_000,
    )

    recovered = "Desk explicit EDIT recovery"
    start_edit_and_set_note(page, name, recovered, checkpoint=True)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector('[data-edit-recovery-action="continue"]', timeout=30_000)
    page.locator('[data-edit-recovery-action="continue"]').click()
    wait_for_function(page, "restore applies dirty EDIT snapshot",
        "value => window.cur_frm && window.cur_frm.doc.order_notes === value && "
        "window.cur_frm.is_dirty() && "
        "window.AlmdinaDcoEditSessionCoordinator.isEditing(window.cur_frm, 'order')",
        arg=recovered,
        timeout=30_000,
    )
    evaluate(page, "commit recovered EDIT session", "() => window.AlmdinaOrderRevisionUX.commitEditSession(window.cur_frm)")
    wait_for_function(page, "commit ends restored EDIT session",
        "value => window.cur_frm && window.cur_frm.doc.order_notes === value && "
        "!window.cur_frm.is_dirty() && "
        "!window.AlmdinaDcoEditSessionCoordinator.isEditing(window.cur_frm, 'order')",
        arg=recovered,
        timeout=30_000,
    )

    # A local snapshot retained from before a real dispatch cannot be offered or
    # applied. Direct Frappe save is rejected; the production lifecycle command
    # and official Return-to-Draft remain available through their own services.
    dispatch_name = FIXTURES["dispatch"]
    open_dco(page, dispatch_name)
    dispatch_baseline = evaluate(page, "read dispatch baseline", "() => window.cur_frm.doc.order_notes")
    dispatch_checkpoint = start_edit_and_set_note(
        page, dispatch_name, "Must remain local after dispatch", checkpoint=True
    )
    page.wait_for_timeout(1100)
    evaluate(page, "dispatch DCO",
        """async ({name, route}) => {
            await frappe.xcall('almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order', {
                order_name: name, path: route, assignee: 'Administrator'
            });
        }""",
        {"name": dispatch_name, "route": FIXTURES["route"]},
    )
    dispatched_doc = evaluate(page, "read dispatched DCO",
        """async name => frappe.xcall('frappe.client.get', {
            doctype: 'Door Cutting Order', name
        })""",
        dispatch_name,
    )
    assert dispatched_doc["modified"] != dispatch_checkpoint["expectedServerModified"]
    open_dco(page, dispatch_name)
    wait_for_function(page, "dispatch exposes active production stage",
        "() => Boolean(window.cur_frm && window.cur_frm.doc.current_production_stage)")
    expect(page.locator("body")).to_contain_text("لا يمكن استعادتها بعد بدء مرحلة الإنتاج")
    expect(page.locator('[data-edit-recovery-action="continue"]')).to_have_count(0)
    retained = evaluate(page, "verify retained EDIT snapshot after dispatch",
        """async name => {
            const result = await window.AlmdinaDcoRecovery.LocalCheckpoint.repository()
                .discover({
                    site: String(frappe.boot && (frappe.boot.sitename || frappe.boot.site_name)
                        || window.location.host || '').trim(),
                    user: String(frappe.session && frappe.session.user || '').trim(),
                    target_doctype: 'Door Cutting Order',
                    mode: 'EDIT',
                    target_name: name,
                });
            return Boolean(result && result.ok && result.value.records.length);
        }""",
        dispatch_name,
    )
    assert retained, "Dispatch must retain the old local snapshot without offering restoration"

    direct_save_rejected = evaluate(page, "reject direct save after dispatch",
        """async () => {
            const doc = JSON.parse(JSON.stringify(window.cur_frm.doc));
            doc.order_notes = 'Forged direct save after dispatch';
            try {
                await frappe.xcall('frappe.client.save', {doc: JSON.stringify(doc)});
                return false;
            } catch (error) {
                return true;
            }
        }"""
    )
    assert direct_save_rejected, "A regular Frappe save must not mutate a dispatched order"
    persisted = page.request.get(
        f"{DESK_URL}/api/method/frappe.client.get?doctype=Door%20Cutting%20Order&name={dispatch_name}"
    ).json()["message"]
    assert persisted["order_notes"] == dispatch_baseline

    page.wait_for_timeout(1100)
    evaluate(page, "return DCO to Draft",
        """async name => frappe.xcall(
            'almdina_erp.almdina_erp.services.order_lifecycle_service.return_order_to_draft',
            {order_name: name, reason: 'Desk recovery lifecycle certification'}
        )""",
        dispatch_name,
    )
    open_dco(page, dispatch_name)
    wait_for_function(page, "Return-to-Draft updates the Desk document",
        "() => window.cur_frm && window.cur_frm.doc.status === 'Draft'")
    assert evaluate(page, "read returned DCO notes", "() => window.cur_frm.doc.order_notes") == dispatch_baseline
    returned_doc = evaluate(page, "read returned DCO",
        """async name => frappe.xcall('frappe.client.get', {
            doctype: 'Door Cutting Order', name
        })""",
        dispatch_name,
    )
    assert returned_doc["modified"] != dispatch_checkpoint["expectedServerModified"]
    page.wait_for_selector('[data-edit-recovery-action="continue"]', timeout=30_000)
    # Continue is explicit after Return-to-Draft; a changed official modified
    # value must produce a conflict without applying any recovered field.
    page.locator('[data-edit-recovery-action="continue"]').click()
    expect(page.locator("body")).to_contain_text("تغير الطلب على الخادم")
    assert evaluate(page, "verify conflict preserved DCO notes", "() => window.cur_frm.doc.order_notes") == dispatch_baseline


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        attach_browser_diagnostics(page)
        evidence_dir = Path(os.environ.get("DCO_DESK_EVIDENCE_DIR", "/tmp/dco-desk-evidence"))
        try:
            certify_actual_frappe_desk_edit_recovery(page)
        except BaseException:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            screenshot = evidence_dir / "dco-desk-failure.png"
            trace = evidence_dir / "dco-desk-trace.json"
            try:
                page.screenshot(path=str(screenshot), full_page=True, timeout=10_000)
            except Exception as exc:
                print(f"Desk screenshot capture failed: {_redact_text(str(exc), 500)}")
            try:
                state = page.evaluate("""() => ({
                    url: location.href,
                    title: document.title,
                    readyState: document.readyState,
                    bodyLength: (document.body && document.body.innerText || '').length,
                    bodyText: (document.body && document.body.innerText || '').slice(0, 1000),
                    user: window.frappe && frappe.session && frappe.session.user,
                    route: window.frappe && frappe.get_route && frappe.get_route(),
                    form: window.cur_frm && window.cur_frm.doc && window.cur_frm.doc.name,
                })""")
            except Exception as exc:
                state = {"diagnostic_error": _redact_text(str(exc), 500)}
            state["url"] = _safe_url(state.get("url", ""))
            state["bodyText"] = _redact_text(state.get("bodyText", ""))
            diagnostic = {"state": state, **DIAGNOSTIC_EVENTS}
            (evidence_dir / "browser-diagnostics.json").write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            trace.write_text(json.dumps(BROWSER_TRACE, ensure_ascii=False, indent=2), encoding="utf-8")
            print("DESK_BROWSER_STATE " + json.dumps(state, ensure_ascii=False))
            print("DESK_BROWSER_EVENT_COUNTS " + json.dumps({
                key: len(events) for key, events in DIAGNOSTIC_EVENTS.items()
            }))
            print("DESK_BROWSER_RECENT_NETWORK " + json.dumps({
                "request_failures": DIAGNOSTIC_EVENTS["request_failures"][-12:],
                "responses": DIAGNOSTIC_EVENTS["responses"][-20:],
                "console": DIAGNOSTIC_EVENTS["console"][-12:],
                "page_errors": DIAGNOSTIC_EVENTS["page_errors"][-12:],
            }, ensure_ascii=False))
            print(f"Desk failure evidence saved to {evidence_dir}")
            raise
        finally:
            browser.close()
