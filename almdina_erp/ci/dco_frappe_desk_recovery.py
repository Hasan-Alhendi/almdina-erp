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
PENDING_REQUESTS: dict[str, dict[str, str | float]] = {}
TRACE_PATH: Path | None = None
ACTIVE_STEP: str | None = None


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
    if TRACE_PATH is not None:
        temporary_path = TRACE_PATH.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                json.dumps(BROWSER_TRACE, ensure_ascii=False), encoding="utf-8"
            )
            temporary_path.replace(TRACE_PATH)
        except OSError:
            pass


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
    def capture_document_state() -> None:
        try:
            state = page.evaluate("""() => {
                const boot = window.frappe && frappe.boot;
                return {
                    url: location.href,
                    title: document.title,
                    readyState: document.readyState,
                    frappePresent: Boolean(window.frappe),
                    bootPresent: Boolean(boot),
                    setupComplete: boot && Boolean(boot.sysdefaults && boot.sysdefaults.setup_complete),
                    sysSetupComplete: boot && boot.sysdefaults && Boolean(boot.sysdefaults.setup_complete),
                    user: window.frappe && frappe.session && frappe.session.user,
                    ajaxCount: window.frappe && frappe.request && frappe.request.ajax_count,
                    route: window.frappe && frappe.get_route
                        ? frappe.get_route().map(String).join("/")
                        : "",
                    bodyText: (document.body && document.body.innerText || "").slice(0, 400),
                };
            }""")
            _trace_event(
                "document_loaded",
                url=_safe_url(str(state.get("url", ""))),
                title=_redact_text(str(state.get("title", "")), 120),
                ready_state=str(state.get("readyState", "")),
                frappe_present=bool(state.get("frappePresent")),
                boot_present=bool(state.get("bootPresent")),
                setup_complete=bool(state.get("setupComplete")),
                sys_setup_complete=bool(state.get("sysSetupComplete")),
                user=_redact_text(str(state.get("user") or ""), 80),
                ajax_count=state.get("ajaxCount") if isinstance(state.get("ajaxCount"), int) else None,
                route=_redact_text(str(state.get("route", "")), 120),
                body_text=_redact_text(str(state.get("bodyText", "")), 400),
            )
        except Exception as exc:
            _trace_event("document_state_unavailable", error=_redact_text(str(exc), 180))

    page.on("load", lambda: capture_document_state())
    page.on("request", lambda request: (
        PENDING_REQUESTS.__setitem__(request.url, {
            "url": _safe_url(request.url),
            "resource_type": request.resource_type,
            "started": round(time.time(), 3),
        }),
        _trace_event("request_started", url=_safe_url(request.url), resource_type=request.resource_type,
            active_step=ACTIVE_STEP),
    ))
    page.on("console", lambda message: (append("console", {
        "type": message.type,
        "text": _redact_text(message.text),
        "location": _safe_url(message.location.get("url", "")) if message.location.get("url") else "",
    }), _trace_event("console", type=message.type, text=_redact_text(message.text)))
        if message.type in {"error", "warning"} else None)
    page.on("pageerror", lambda error: (append("page_errors", {"text": _redact_text(str(error))}),
        _trace_event("page_error", text=_redact_text(str(error)))))
    page.on("requestfailed", lambda request: (PENDING_REQUESTS.pop(request.url, None), append("request_failures", {
        "url": _safe_url(request.url),
        "resource_type": request.resource_type,
        "failure": _redact_text(str(request.failure), 500) if request.failure else "unknown",
    }), _trace_event("request_failed", url=_safe_url(request.url),
        resource_type=request.resource_type,
        failure=_redact_text(str(request.failure), 500) if request.failure else "unknown")))
    page.on("response", lambda response: (PENDING_REQUESTS.pop(response.url, None), append("responses", {
        "url": _safe_url(response.url),
        "status": response.status,
        "resource_type": response.request.resource_type,
        "content_type": response.headers.get("content-type", "")[:120],
    }), _trace_event("response", url=_safe_url(response.url), status=response.status,
        resource_type=response.request.resource_type, active_step=ACTIVE_STEP))
        if response.request.resource_type in {"document", "script", "xhr", "fetch"}
        or response.status >= 400 else None)


def evaluate(page: Page, step: str, expression: str, arg=None):
    global ACTIVE_STEP
    ACTIVE_STEP = step
    _trace_event("step_started", step=step)
    try:
        # page.evaluate has no operation timeout. Bound async xcall/IndexedDB
        # work in the browser so an unresolved Promise cannot hang certification.
        wrapped_expression = """
            async payload => {
                const operation = """ + expression + """;
                let timeoutHandle;
                const timeoutMs = payload.timeoutMs;
                const timeout = new Promise((_, reject) => {
                    timeoutHandle = setTimeout(
                        () => reject(new Error(`Browser operation timed out after ${timeoutMs}ms`)),
                        timeoutMs,
                    );
                });
                try {
                    return await Promise.race([Promise.resolve(operation(payload.arg)), timeout]);
                } finally {
                    clearTimeout(timeoutHandle);
                }
            }
        """
        timeout_ms = 35_000 if step == "commit recovered EDIT session" else 90_000
        result = page.evaluate(wrapped_expression, {"arg": arg, "timeoutMs": timeout_ms})
        _trace_event("step_completed", step=step)
        ACTIVE_STEP = None
        return result
    except Exception as exc:
        _trace_event("step_failed", step=step, error=_redact_text(str(exc)))
        ACTIVE_STEP = None
        raise RuntimeError(f"Desk browser step '{step}' failed: {exc}") from exc


def read_page_state(page: Page) -> dict:
    last_error = "document state unavailable"
    for _ in range(3):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=3_000)
            return page.evaluate("""() => {
                const boot = window.frappe && frappe.boot;
                return {
                    url: location.href,
                    title: document.title,
                    readyState: document.readyState,
                    bodyLength: (document.body && document.body.innerText || "").length,
                    bodyText: (document.body && document.body.innerText || "").slice(0, 1000),
                    frappePresent: Boolean(window.frappe),
                    bootPresent: Boolean(boot),
                    user: window.frappe && frappe.session && frappe.session.user,
                    setupComplete: boot && Boolean(boot.sysdefaults && boot.sysdefaults.setup_complete),
                    sysSetupComplete: boot && boot.sysdefaults && Boolean(boot.sysdefaults.setup_complete),
                    ajaxCount: window.frappe && frappe.request && frappe.request.ajax_count,
                    route: window.frappe && frappe.get_route && frappe.get_route(),
                    routePath: window.frappe && frappe.get_route
                        ? frappe.get_route().map(String).join("/")
                        : "",
                    scriptAssets: [...document.scripts]
                        .map(script => script.src).filter(Boolean).slice(-30),
                    form: window.cur_frm && window.cur_frm.doc && window.cur_frm.doc.name,
                    saveProbe: window.__dcoDeskSaveProbe || null,
                };
            }""")
        except Exception as exc:
            last_error = _redact_text(str(exc), 500)
            page.wait_for_timeout(250)
    return {"url": _safe_url(page.url), "diagnostic_error": last_error}


def wait_for_function(page: Page, step: str, expression: str, *, arg=None, timeout: int = 30_000):
    _trace_event("wait_started", step=step)
    try:
        page.wait_for_function(expression, arg=arg, timeout=timeout)
    except Exception as exc:
        _trace_event("wait_failed", step=step, error=_redact_text(str(exc)))
        state = read_page_state(page)
        raise RuntimeError(f"Desk browser wait '{step}' failed: {exc}; desk_state={state}") from exc
    _trace_event("wait_completed", step=step)


def open_dco(page: Page, name: str) -> None:
    target_url = f"{DESK_URL}/app/door-cutting-order/{name}"
    _trace_event("open_dco_started", url=_safe_url(target_url))
    response = page.goto(target_url, wait_until="domcontentloaded")
    # Desk may satisfy this navigation through its SPA router and history API;
    # Playwright then returns None because there was no top-level HTTP response.
    if response is not None and response.status >= 400:
        raise RuntimeError(f"DCO navigation returned HTTP {response.status}: {_safe_url(page.url)}")
    try:
        wait_for_function(page, f"load DCO {name}",
            "name => window.cur_frm && window.cur_frm.doc && window.cur_frm.doc.name === name",
            arg=name,
            timeout=30_000,
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
    _trace_event("open_dco_completed", url=_safe_url(page.url))


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
    _trace_event("certification_started")
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

    wait_for_function(page, "Desk boot ready for Administrator",
        "() => window.frappe && frappe.boot && frappe.boot.sysdefaults && "
        "Boolean(frappe.boot.sysdefaults.setup_complete) && "
        "frappe.session && frappe.session.user === 'Administrator' && "
        "frappe.app && frappe.router && "
        "window.location.pathname.startsWith('/desk')",
        timeout=30_000,
    )

    _trace_event("login_established", user="Administrator")

    # Phase B is intentionally limited to Desk startup and loading one real
    # DCO form. Recovery scenarios must never run when this smoke fails.
    name = FIXTURES["restore"]
    _trace_event("phase_b_desk_smoke_started", target_doctype="Door Cutting Order")
    open_dco(page, name)
    wait_for_function(page, "DCO form is ready",
        "name => window.cur_frm && window.cur_frm.doc && "
        "window.cur_frm.doc.name === name && window.cur_frm.doctype === 'Door Cutting Order'",
        arg=name,
        timeout=30_000,
    )
    _trace_event("phase_b_desk_smoke_completed", doctype="Door Cutting Order")

    # A route selected on a Draft is not dispatch. Exercise the real edit-session
    # Cancel and Save adapters, and the real IndexedDB restore dialog.
    _trace_event("scenario_started", scenario="cancel_and_restore")
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
    evaluate(page, "instrument recovered EDIT save", """() => {
        const frm = window.cur_frm;
        const costUx = window.AlmdinaCostPermissionsUX;
        const probe = window.__dcoDeskSaveProbe = {
            dirtyBeforeSave: frm.is_dirty(),
            ajaxCountAtSave: window.frappe.request && window.frappe.request.ajax_count,
            costUxPresent: Boolean(costUx),
            pendingPriceEdits: costUx && typeof costUx.pendingPricePieces === 'function'
                ? costUx.pendingPricePieces(frm).length
                : null,
            session: window.AlmdinaDcoEditSessionCoordinator.snapshot(frm),
            saveStarted: false,
            saveSettled: null,
            beforeSaveHandlers: null,
            beforeSaveTriggerStarted: false,
            beforeSaveTriggerSettled: null,
            activeBeforeSaveHandler: null,
            handlerCalls: [],
            afterServerCalls: [],
            scriptEvents: [],
            runSeriallyCalls: 0,
            runSeriallySettled: null,
        };
        const manager = frm.script_manager;
        if (manager && typeof manager.get_handlers === 'function') {
            const originalGetHandlers = manager.get_handlers;
            manager.get_handlers = function(eventName, doctype) {
                const result = originalGetHandlers.call(this, eventName, doctype);
                if (!probe.saveStarted || !['validate', 'before_save'].includes(eventName)) return result;
                if (eventName === 'before_save') {
                    probe.beforeSaveHandlers = result.new_style.length + result.old_style.length;
                }
                result.new_style = result.new_style.map((handler, index) => function(...args) {
                    const record = {event: eventName, style: 'new', index, state: 'started'};
                    probe.handlerCalls.push(record);
                    if (eventName === 'before_save') probe.activeBeforeSaveHandler = index;
                    let handlerResult;
                    try {
                        handlerResult = handler.apply(this, args);
                    } catch (error) {
                        record.state = String(error).slice(0, 160);
                        throw error;
                    }
                    if (handlerResult && typeof handlerResult.then === 'function') {
                        handlerResult.then(
                            () => {
                                record.state = 'resolved';
                                if (probe.activeBeforeSaveHandler === index) probe.activeBeforeSaveHandler = null;
                            },
                            error => {
                                record.state = String(error).slice(0, 160);
                                if (probe.activeBeforeSaveHandler === index) probe.activeBeforeSaveHandler = null;
                            },
                        );
                    } else {
                        record.state = 'resolved';
                        if (probe.activeBeforeSaveHandler === index) probe.activeBeforeSaveHandler = null;
                    }
                    return handlerResult;
                });
                return result;
            };
        }
        if (window.frappe && typeof frappe.after_server_call === 'function') {
            const originalAfterServerCall = frappe.after_server_call;
            frappe.after_server_call = function(...args) {
                const result = originalAfterServerCall.apply(this, args);
                if (probe.saveStarted) {
                    const record = {
                        ajaxCount: frappe.request && frappe.request.ajax_count,
                        state: result && typeof result.then === 'function' ? 'waiting' : 'resolved',
                    };
                    probe.afterServerCalls.push(record);
                    if (result && typeof result.then === 'function') {
                        result.then(
                            () => { record.state = 'resolved'; },
                            error => { record.state = String(error).slice(0, 160); },
                        );
                    }
                }
                return result;
            };
        }
        if (manager && typeof manager.trigger === 'function') {
            const originalTrigger = manager.trigger;
            manager.trigger = function(eventName, ...args) {
                if (!probe.saveStarted || !['validate', 'before_save', 'after_save'].includes(eventName)) {
                    return originalTrigger.call(this, eventName, ...args);
                }
                probe.scriptEvents.push({event: eventName, state: 'started'});
                if (eventName === 'before_save') probe.beforeSaveTriggerStarted = true;
                const result = originalTrigger.call(this, eventName, ...args);
                if (result && typeof result.then === 'function') {
                    result.then(
                        () => {
                            probe.scriptEvents.push({event: eventName, state: 'resolved'});
                            if (eventName === 'before_save') probe.beforeSaveTriggerSettled = 'resolved';
                        },
                        error => {
                            const message = String(error).slice(0, 160);
                            probe.scriptEvents.push({event: eventName, state: message});
                            if (eventName === 'before_save') probe.beforeSaveTriggerSettled = message;
                        },
                    );
                } else {
                    probe.scriptEvents.push({event: eventName, state: 'non_thenable'});
                    if (eventName === 'before_save') probe.beforeSaveTriggerSettled = 'non_thenable';
                }
                return result;
            };
        }
        const originalRunSerially = frappe.run_serially;
        frappe.run_serially = function(tasks, ...args) {
            if (probe.saveStarted) probe.runSeriallyCalls += 1;
            const result = originalRunSerially.call(this, tasks, ...args);
            if (probe.saveStarted && result && typeof result.then === 'function') {
                result.then(
                    () => { probe.runSeriallySettled = 'resolved'; },
                    error => { probe.runSeriallySettled = String(error).slice(0, 160); },
                );
            }
            return result;
        };
        const originalSave = frm.save;
        frm.save = function(...args) {
            probe.saveStarted = true;
            const result = originalSave.apply(this, args);
            if (result && typeof result.then === 'function') {
                result.then(
                    () => { probe.saveSettled = 'resolved'; },
                    error => { probe.saveSettled = String(error).slice(0, 200); },
                );
            } else {
                probe.saveSettled = 'non_thenable';
            }
            return result;
        };
        return probe;
    }""")
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
    _trace_event("certification_completed")


if __name__ == "__main__":
    with sync_playwright() as playwright:
        evidence_dir = Path(os.environ.get("DCO_DESK_EVIDENCE_DIR", "/tmp/dco-desk-evidence"))
        evidence_dir.mkdir(parents=True, exist_ok=True)
        TRACE_PATH = evidence_dir / "dco-desk-trace.json"
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(30_000)
        attach_browser_diagnostics(page)
        try:
            certify_actual_frappe_desk_edit_recovery(page)
        except BaseException as failure:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            screenshot = evidence_dir / "dco-desk-failure.png"
            trace = evidence_dir / "dco-desk-trace.json"
            failure_text = _redact_text(str(failure))
            _trace_event("certification_failed", error=failure_text)
            trace.write_text(json.dumps(BROWSER_TRACE, ensure_ascii=False, indent=2), encoding="utf-8")
            diagnostic_path = evidence_dir / "browser-diagnostics.json"
            diagnostic_path.write_text(json.dumps({
                "state": {"failure": failure_text}, **DIAGNOSTIC_EVENTS,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                page.screenshot(path=str(screenshot), full_page=True, timeout=10_000)
            except Exception as exc:
                print(f"Desk screenshot capture failed: {_redact_text(str(exc), 500)}")
            state = read_page_state(page)
            state["url"] = _safe_url(state.get("url", ""))
            state["bodyText"] = _redact_text(state.get("bodyText", ""))
            state["failure"] = _redact_text(str(failure))
            state["pendingRequests"] = list(PENDING_REQUESTS.values())[-25:]
            state["apiResponses"] = [
                {"url": event["url"], "status": event["status"]}
                for event in DIAGNOSTIC_EVENTS["responses"]
                if event.get("resource_type") in {"xhr", "fetch"}
            ][-35:]
            diagnostic = {"state": state, **DIAGNOSTIC_EVENTS}
            (evidence_dir / "browser-diagnostics.json").write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            diagnostic_path.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8")
            print("DESK_BROWSER_STATE " + json.dumps(state, ensure_ascii=False))
            print("DESK_BROWSER_EVENT_COUNTS " + json.dumps({
                key: len(events) for key, events in DIAGNOSTIC_EVENTS.items()
            }))
            print("DESK_BROWSER_API_STATE " + json.dumps({
                "pending": state["pendingRequests"],
                "responses": state["apiResponses"],
            }, ensure_ascii=False))
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
