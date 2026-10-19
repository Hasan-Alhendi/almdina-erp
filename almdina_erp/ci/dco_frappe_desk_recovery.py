from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

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
CERTIFIED_SCENARIOS: dict[str, dict] = {}


def record_scenario(name: str, **evidence) -> None:
    """Persist individual proven scenarios, even if a later scenario fails."""
    CERTIFIED_SCENARIOS[name] = {"result": "PASS", **evidence}
    destination = Path(os.environ.get("DCO_DESK_EVIDENCE_DIR", "/tmp/dco-desk-evidence"))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "edit-scenario-results.json").write_text(
        json.dumps(CERTIFIED_SCENARIOS, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _trace_event("scenario_passed", scenario=name)


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
                    nativeFormTrace: (window.__al131NativeFormTrace || []).slice(-12),
                    form: window.cur_frm && window.cur_frm.doc && window.cur_frm.doc.name,
                    readiness: {
                        docContext: Boolean(window.AlmdinaDocumentContext),
                        coordinator: Boolean(window.AlmdinaDcoEditSessionCoordinator),
                        recovery: Boolean(window.AlmdinaDcoRecovery),
                        checkpoint: Boolean(window.AlmdinaDcoRecovery?.LocalCheckpoint),
                        formFields: Boolean(window.cur_frm?.fields_dict?.order_notes),
                        formDOM: Boolean(window.cur_frm?.wrapper?.isConnected),
                        scriptManager: Boolean(window.cur_frm?.script_manager),
                        setupDone: Boolean(window.cur_frm?.setup_done),
                        hasRead: Boolean(window.cur_frm?.perm?.[0]?.read),
                        permissionRows: (window.cur_frm?.perm || []).slice(0, 2).map(p => ({
                            read: Boolean(p.read), write: Boolean(p.write),
                            permlevel: p.permlevel
                        })),
                        userRoles: (window.frappe?.user_roles || []).slice(0, 20),
                        doctypeMetaLoaded: Boolean(window.frappe?.get_meta?.("Door Cutting Order")),
                        doctypeRoles: (window.frappe?.get_meta?.("Door Cutting Order")?.permissions || [])
                            .slice(0, 20).map(p => p.role),
                        // Pinpoint the native Frappe FormFactory boundary. The
                        // saved document can exist in locals while its Form
                        // is still not rendered; recovery assets load later.
                        documentCached: Boolean(window.cur_frm?.docname
                            && window.frappe?.get_doc?.("Door Cutting Order", cur_frm.docname)),
                        docinfoCached: Boolean(window.cur_frm?.docname
                            && window.frappe?.model?.get_docinfo?.("Door Cutting Order", cur_frm.docname)),
                        formFactoryPage: Boolean(window.frappe?.views?.formview?.["Door Cutting Order"]),
                        formFactoryOwnsCurrent: Boolean(
                            window.frappe?.views?.formview?.["Door Cutting Order"]?.frm
                            === window.cur_frm
                        ),
                        formPageVisible: Boolean(window.cur_frm?.wrapper?.classList?.contains("show")),
                        formHasLayout: Boolean(window.cur_frm?.layout),
                        formDocname: String(window.cur_frm?.docname || ""),
                        formName: String(window.cur_frm?.doc?.name || ""),
                    },
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


def open_dco(page: Page, name: str, *, wait_for_route: bool = True) -> None:
    target_url = f"{DESK_URL}/app/door-cutting-order/{name}"
    _trace_event("open_dco_started", url=_safe_url(target_url))
    # The initial Form must be opened through the same native Desk entry
    # proven by AL128. Calling set_route while Desk's first page is still
    # mounting can leave cur_frm with metadata but without Form.setup.
    # Once a Form is fully mounted, subsequent A -> B transitions use the
    # normal in-app Frappe router.
    same_document = page.evaluate(
        "name => window.cur_frm && cur_frm.doctype === 'Door Cutting Order' "
        "&& cur_frm.doc && cur_frm.doc.name === name",
        name,
    )
    mounted_form = page.evaluate(
        "() => Boolean(window.cur_frm?.script_manager"
        " && window.cur_frm?.fields_dict?.order_notes"
        " && window.cur_frm?.wrapper?.isConnected)"
    )
    if same_document and mounted_form:
        # Frappe router.push_state does not render an unchanged URL. Use
        # native Form.reload_doc() to inspect new server state after dispatch
        # or return-to-Draft without reloading the entire browser.
        # reload_doc returns an asynchronous Frappe request. The real Form
        # may navigate while that request completes, so do not await its
        # Promise inside the old browser execution context. Observe the
        # authoritative native getdoc response instead.
        with page.expect_response(
            lambda response: "frappe.desk.form.load.getdoc" in response.url
            and response.status == 200,
            timeout=60_000,
        ):
            evaluate(page, f"initiate native Form reload for {name}",
                     "() => { setTimeout(() => { void cur_frm.reload_doc(); }, 0); return true; }")
    elif not mounted_form:
        response = page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
        if response is None or response.status >= 400:
            raise RuntimeError(
                f"Initial DCO Form navigation failed: HTTP {response.status if response else 'none'}"
            )
        _trace_event("initial_dco_form_navigation_completed", status=response.status)
    else:
        evaluate(
            page, f"route to DCO {name} through Frappe Desk",
            # Frappe's route promise also waits for outstanding AJAX. A test
            # deliberately holding A's request must still be able to visit B.
            # The exact Form/readiness checks below acknowledge the navigation.
            "name => frappe.set_route('Form', 'Door Cutting Order', name)" if wait_for_route else
            "name => { void frappe.set_route('Form', 'Door Cutting Order', name); return true; }",
            name,
        )
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
    # Frappe sets cur_frm while the Form and its custom scripts are still
    # loading. Only the loaded DCO recovery + Edit Session contracts may be
    # used by subsequent calls; route/document identity alone is premature.
    wait_for_function(
        page, f"DCO recovery assets ready for {name}",
        "name => { const frm = window.cur_frm;"
        " return Boolean(frm && frm.doctype === 'Door Cutting Order'"
        " && frm.doc && frm.doc.name === name"
        " && window.AlmdinaDcoRecovery && AlmdinaDcoRecovery.LocalCheckpoint"
        " && window.AlmdinaDcoEditSessionCoordinator"
        " && frm.fields_dict && frm.fields_dict.order_notes); }",
        arg=name,
        timeout=30_000,
    )
    _trace_event("open_dco_completed", url=_safe_url(page.url))


def start_edit_and_set_note(page: Page, name: str, value: str, checkpoint: bool) -> dict:
    return evaluate(page, f"start EDIT for {name}",
        """async ({name, value, checkpoint}) => {
            const frm = window.cur_frm;
            const coordinator = window.AlmdinaDcoEditSessionCoordinator;
            const recovery = window.AlmdinaDcoRecovery
                && window.AlmdinaDcoRecovery.LocalCheckpoint;
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


def login_to_desk(page: Page, user: str, password: str) -> None:
    response = page.goto(f"{DESK_URL}/login", wait_until="domcontentloaded")
    if response is None or response.status >= 400:
        status = response.status if response is not None else None
        raise RuntimeError(f"Frappe login page returned HTTP {status}: {_safe_url(page.url)}")
    page.locator("#login_email").wait_for(state="visible", timeout=15_000)
    page.locator("#login_email").fill(user)
    page.locator("#login_password").fill(password)
    page.get_by_role("button", name=re.compile(r"^(Login|Continue)$")).click()
    wait_for_function(page, f"{user} login establishes a Desk session",
        f"() => window.frappe && frappe.session && frappe.session.user === {json.dumps(user)}",
        timeout=30_000,
    )
    wait_for_function(page, f"Desk boot ready for {user}",
        "() => window.frappe && frappe.boot && frappe.boot.sysdefaults && "
        "Boolean(frappe.boot.sysdefaults.setup_complete) && "
        "frappe.app && frappe.router && "
        "window.location.pathname.startsWith('/desk')",
        timeout=30_000,
    )
    # Trace the pinned Frappe Form boundary without changing its behavior.
    # A loaded cur_frm.doc is not proof that Form.refresh reached Form.setup.
    evaluate(page, "observe native Frappe Form lifecycle", """() => {
        const proto = window.frappe?.ui?.form?.Form?.prototype;
        if (!proto || proto.__al131TraceInstalled) return false;
        proto.__al131TraceInstalled = true;
        window.__al131NativeFormTrace = [];
        const record = (phase, frm, failure) => {
            if (frm?.doctype !== 'Door Cutting Order') return;
            const steps = window.__al131NativeFormTrace;
            steps.push({
                phase,
                docname: String(frm.docname || ''),
                setupDone: Boolean(frm.setup_done),
                hasLayout: Boolean(frm.layout),
                scriptManager: Boolean(frm.script_manager),
                hasRead: Boolean(frm.perm?.[0]?.read),
                openDoc: Boolean(frm.opendocs?.[frm.docname]),
                failure: failure ? String(failure?.stack || failure).slice(0, 600) : null
            });
            if (steps.length > 24) steps.shift();
        };
        for (const name of ['refresh', 'setup']) {
            const original = proto[name];
            if (typeof original !== 'function') continue;
            proto[name] = function (...args) {
                record(name + ':enter', this);
                try { return original.apply(this, args); }
                catch (error) { record(name + ':throw', this, error); throw error; }
                finally { record(name + ':exit', this); }
            };
        }
        return true;
    }""")
    _trace_event("login_established", user=_redact_text(user, 80))


def certify_worker_identity_and_dynamic_permissions(admin_page: Page) -> None:
    browser = admin_page.context.browser
    if browser is None:
        raise RuntimeError("Desk identity certification requires a browser context.")
    worker_context = browser.new_context(locale="en-US")
    worker_page = worker_context.new_page()
    attach_browser_diagnostics(worker_page)
    try:
        worker = FIXTURES["worker"]
        login_to_desk(worker_page, worker, "dco-test-worker-password")

        identity_a = FIXTURES["identity_a"]
        identity_b = FIXTURES["identity_b"]
        baseline_b = worker_page.request.get(
            f"{DESK_URL}/api/method/frappe.client.get?doctype=Door%20Cutting%20Order&name={identity_b}"
        ).json()["message"]["order_notes"]
        open_dco(worker_page, identity_a)
        start_edit_and_set_note(
            worker_page, identity_a, "Identity-bound EDIT checkpoint", checkpoint=True
        )
        open_dco(worker_page, identity_b)
        expect(worker_page.locator('[data-edit-recovery-action="continue"]')).to_be_hidden()
        assert evaluate(worker_page, "verify document B is isolated",
            "({name, baseline}) => window.cur_frm && window.cur_frm.doc.name === name && "
            "window.cur_frm.doc.order_notes === baseline",
            {"name": identity_b, "baseline": baseline_b},
        )
        open_dco(worker_page, identity_a)
        continue_button = worker_page.locator('[data-edit-recovery-action="continue"]')
        continue_button.wait_for(state="visible", timeout=30_000)
        if continue_button.is_disabled():
            # A → B → A can retain dirty A in Frappe locals. Recovery must
            # not overwrite that form. Prove the guard, then model a real
            # browser restart to load the clean official document before
            # explicitly restoring the IndexedDB checkpoint.
            assert evaluate(
                worker_page, "dirty A correctly blocks recovery",
                "() => Boolean(cur_frm.is_dirty() || cur_frm.doc.__unsaved)"
            ), "Continue was disabled for a reason other than dirty form ownership"
            worker_page.reload(wait_until="domcontentloaded")
            open_dco(worker_page, identity_a)
            continue_button = worker_page.locator('[data-edit-recovery-action="continue"]')
            continue_button.wait_for(state="visible", timeout=30_000)
        expect(continue_button).to_be_enabled(timeout=30_000)
        continue_button.click()
        wait_for_function(worker_page, "document A restores only its own EDIT checkpoint",
            "() => window.cur_frm && window.cur_frm.doc.name === "
            f"{json.dumps(identity_a)} && "
            "window.cur_frm.doc.order_notes === 'Identity-bound EDIT checkpoint'",
            timeout=30_000,
        )
        evaluate(worker_page, "cancel isolated EDIT session",
            "() => window.AlmdinaDcoEditSessionCoordinator.cancel(window.cur_frm, 'order')")
        persisted_b = worker_page.request.get(
            f"{DESK_URL}/api/method/frappe.client.get?doctype=Door%20Cutting%20Order&name={identity_b}"
        ).json()["message"]["order_notes"]
        assert persisted_b == baseline_b, "Document A recovery must not mutate document B"

        permission_name = FIXTURES["permission"]
        permission_baseline = worker_page.request.get(
            f"{DESK_URL}/api/method/frappe.client.get?doctype=Door%20Cutting%20Order&name={permission_name}"
        ).json()["message"]["order_notes"]
        open_dco(worker_page, permission_name)
        start_edit_and_set_note(
            worker_page, permission_name, "Permission-gated EDIT checkpoint", checkpoint=True
        )
        worker_page.reload(wait_until="domcontentloaded")
        worker_page.locator('[data-edit-recovery-action="continue"]').wait_for(
            state="visible", timeout=30_000
        )

        role = FIXTURES["role"]
        revoked = evaluate(admin_page, "revoke dynamic EDIT permission",
            """async role => {
                const current = await frappe.xcall(
                    'almdina_erp.almdina_erp.services.permission_management_service.get_role_permissions',
                    {role}
                );
                if (!current.capabilities || current.capabilities.edit_order !== true) {
                    throw new Error('Fixture role did not begin with EDIT permission');
                }
                const capabilities = {...current.capabilities, edit_order: false};
                return await frappe.xcall(
                    'almdina_erp.almdina_erp.services.permission_management_service.update_role_permissions',
                    {role, capabilities: JSON.stringify(capabilities)}
                );
            }""",
            role,
        )
        if revoked.get("capabilities", {}).get("edit_order") is not False:
            raise RuntimeError("The server did not revoke the fixture role's EDIT permission.")
        permission_refresh = evaluate(worker_page, "refresh worker permission context",
            "() => window.AlmdinaPermissions.refresh()")
        if permission_refresh.get("capabilities", {}).get("edit_order") is not False:
            raise RuntimeError("Desk permission refresh did not observe revoked EDIT permission.")
        expect(worker_page.locator('[data-edit-recovery-action="continue"]')).to_be_hidden()
        assert evaluate(worker_page, "revoked EDIT cannot restore or mutate the draft",
            "name => window.cur_frm && window.cur_frm.doc.name === name && "
            "window.cur_frm.doc.order_notes === " + json.dumps(permission_baseline) + " && "
            "window.AlmdinaPermissions.canDocument(window.cur_frm, 'edit_order') === false",
            permission_name,
        )

        restored = evaluate(admin_page, "restore fixture role EDIT permission",
            """async role => {
                const current = await frappe.xcall(
                    'almdina_erp.almdina_erp.services.permission_management_service.get_role_permissions',
                    {role}
                );
                const capabilities = {...current.capabilities, edit_order: true};
                return await frappe.xcall(
                    'almdina_erp.almdina_erp.services.permission_management_service.update_role_permissions',
                    {role, capabilities: JSON.stringify(capabilities)}
                );
            }""",
            role,
        )
        if restored.get("capabilities", {}).get("edit_order") is not True:
            raise RuntimeError("Could not restore fixture role's EDIT permission after certification.")
        _trace_event("worker_identity_and_dynamic_permissions_completed")
    finally:
        worker_context.close()


def certify_actual_frappe_desk_edit_recovery(page: Page) -> None:
    _trace_event("certification_started")
    login_to_desk(page, "Administrator", "admin")

    # Phase B is intentionally limited to Desk startup and loading one real
    # DCO form. Recovery scenarios must never run when this smoke fails.
    name = FIXTURES["restore"]
    _trace_event("phase_b_desk_smoke_started", target_doctype="Door Cutting Order")
    open_dco(page, name)
    assert evaluate(page, "verify Arabic recovery acceptance locale",
                    "() => AlmdinaLocale.currentLanguage()") == "ar"
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

    certify_worker_identity_and_dynamic_permissions(page)

    # A local snapshot retained from before a real dispatch cannot be offered or
    # applied. Direct Frappe save is rejected; the production lifecycle command
    # and official Return-to-Draft remain available through their own services.
    dispatch_name = FIXTURES["dispatch"]
    open_dco(page, dispatch_name)
    dispatch_baseline = evaluate(page, "read dispatch baseline", "() => window.cur_frm.doc.order_notes")
    dispatch_checkpoint = start_edit_and_set_note(
        page, dispatch_name, "Must remain local after dispatch", checkpoint=True
    )
    dispatch_result = evaluate(page, "dispatch DCO",
        """async ({name, route, worker}) => {
            try {
                const result = await frappe.xcall(
                    'almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order',
                    {order_name: name, path: route, assignee: worker}
                );
                return {ok: true, result};
            } catch (error) {
                const response = window.frappe && frappe.last_response || {};
                return {
                    ok: false,
                    error: error == null ? String(error) : String(error),
                    excType: response.exc_type || '',
                    errorMessage: response._error_message || '',
                    serverMessages: String(response._server_messages || '').slice(0, 800),
                };
            }
        }""",
        {"name": dispatch_name, "route": FIXTURES["route"], "worker": FIXTURES["worker"]},
    )
    if not dispatch_result.get("ok"):
        raise RuntimeError(f"Dispatch service rejected the test order: {dispatch_result}")
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
    # The informational Frappe toast can be localized or expire before the
    # assertion. Safety is established by the authoritative dispatch stage,
    # no offered recovery action, a retained checkpoint and rejected Save.
    # frappe.ui.Dialog.hide() retains its markup in the DOM. It must be
    # invisible and unavailable to the operator after real dispatch, not
    # necessarily removed from the document entirely.
    expect(page.locator('[data-edit-recovery-action="continue"]')).to_be_hidden()
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
    # The operator reopens the returned Draft before reviewing a checkpoint
    # retained from its earlier production session. Keep the SAME Chromium
    # profile/IndexedDB, but use a fresh Frappe Form lifecycle so a previously
    # dismissed dialog cannot masquerade as the current recovery offer.
    response = page.goto(
        f"{DESK_URL}/desk/door-cutting-order/{dispatch_name}",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    assert response is not None and response.status == 200
    open_dco(page, dispatch_name)
    continue_button = page.locator(
        '.modal.show [data-edit-recovery-action="continue"]'
    )
    expect(continue_button).to_be_visible(timeout=30_000)
    # Continue is explicit after Return-to-Draft; a changed official modified
    # value must produce a conflict without applying any recovered field.
    continue_button.click()
    expect(page.locator("body")).to_contain_text("تغير الطلب على الخادم")
    assert evaluate(page, "verify conflict preserved DCO notes", "() => window.cur_frm.doc.order_notes") == dispatch_baseline
    record_scenario("edit_restore_save_cancel_permission_dispatch_return_to_draft", explicit_conflict=True)


def server_document(page: Page, name: str) -> dict:
    response = page.request.get(
        f"{DESK_URL}/api/method/frappe.client.get",
        params={"doctype": "Door Cutting Order", "name": name},
    )
    assert response.ok, f"Authoritative DCO read failed: HTTP {response.status}"
    return response.json()["message"]


def checkpoint_record(page: Page, name: str) -> dict:
    return evaluate(page, "read durable EDIT checkpoint", """async name => {
        const found = await AlmdinaDcoRecovery.LocalCheckpoint.repository().discover({
            site: String(frappe.boot.sitename || frappe.boot.site_name || location.host).trim(),
            user: String(frappe.session.user).trim(),
            target_doctype: 'Door Cutting Order', target_name: name, mode: 'EDIT',
        });
        if (!found.ok || found.value.records.length !== 1) {
            throw new Error('Expected exactly one verified EDIT checkpoint for the scenario');
        }
        return found.value.records[0];
    }""", name)


def flush_edit_checkpoint(page: Page) -> dict:
    return evaluate(page, "acknowledge real EDIT checkpoint", """async () => {
        const recovery = AlmdinaDcoRecovery.LocalCheckpoint;
        if (!recovery.markDirty(cur_frm, 'DCO')) {
            throw new Error('Dirty EDIT not accepted: ' + JSON.stringify({
                checkpoint: recovery.snapshot(cur_frm),
                editActive: AlmdinaOrderRevisionUX.isEditSessionActive(cur_frm),
                coordinator: AlmdinaDcoEditSessionCoordinator.snapshot(cur_frm),
                dirty: cur_frm.is_dirty(),
            }));
        }
        const result = await recovery.flush(cur_frm);
        if (!result || !result.ok) throw new Error('Durable EDIT transaction failed');
        const state = recovery.snapshot(cur_frm);
        if (state.state !== 'LOCAL_SAVED' || state.saved_revision !== state.recovery_revision) {
            throw new Error('Checkpoint was not durably acknowledged');
        }
        return state;
    }""")


def continue_edit_checkpoint(page: Page, name: str, notes: str) -> None:
    button = page.locator('.modal.show [data-edit-recovery-action="continue"]')
    expect(button).to_be_visible(timeout=30_000)
    expect(button).to_be_enabled()
    button.click()
    wait_for_function(page, "explicit EDIT restore completes", """({name, notes}) =>
        cur_frm?.doc?.name === name && cur_frm.doc.order_notes === notes
        && cur_frm.is_dirty() && AlmdinaDcoEditSessionCoordinator.isEditing(cur_frm, 'order')
        && !document.querySelector('.modal.show [data-edit-recovery-action="continue"]')
    """, arg={"name": name, "notes": notes})


def save_other_tab(context, name: str, notes: str) -> dict:
    """An independent browser session commits an actual native Desk Save."""
    browser = context.browser
    if browser is None:
        raise RuntimeError("External-edit certification requires a Chromium browser")
    external_context = browser.new_context(locale="en-US")
    other = external_context.new_page()
    attach_browser_diagnostics(other)
    try:
        login_to_desk(other, "Administrator", "admin")
        open_dco(other, name)
        start_edit_and_set_note(other, name, notes, checkpoint=False)
        evaluate(other, "native Save in independent Desk tab",
                 "() => AlmdinaOrderRevisionUX.commitEditSession(cur_frm)")
        wait_for_function(other, "external native Save is acknowledged", """notes =>
            cur_frm.doc.order_notes === notes && !cur_frm.is_dirty()
            && !AlmdinaDcoEditSessionCoordinator.isEditing(cur_frm, 'order')
        """, arg=notes)
        result = server_document(other, name)
        assert result["order_notes"] == notes
        return result
    finally:
        external_context.close()


def certify_edit_conflicts_and_internal_checkpoint(page: Page) -> None:
    name = FIXTURES["external_conflict"]
    open_dco(page, name)
    original = server_document(page, name)
    start_edit_and_set_note(page, name, "Retain local input during external conflict", checkpoint=True)
    before = checkpoint_record(page, name)
    external = save_other_tab(page.context, name, "New official input from another browser tab")
    assert external["modified"] != original["modified"]
    page.reload(wait_until="domcontentloaded")
    open_dco(page, name)
    button = page.locator('.modal.show [data-edit-recovery-action="continue"]')
    expect(button).to_be_visible()
    button.click()
    expect(page.locator("body")).to_contain_text("تغير الطلب على الخادم")
    assert page.evaluate("() => cur_frm.doc.order_notes") == external["order_notes"]
    after = checkpoint_record(page, name)
    assert after["payload_hash"] == before["payload_hash"]
    assert after["recovery_revision"] == before["recovery_revision"]
    record_scenario("external_server_edit_before_restore", draft_retained=True, auto_merge=False)

    name = FIXTURES["save_conflict"]
    open_dco(page, name)
    local_notes = "Local restored edit must not overwrite a later server edit"
    start_edit_and_set_note(page, name, local_notes, checkpoint=True)
    page.reload(wait_until="domcontentloaded")
    open_dco(page, name)
    continue_edit_checkpoint(page, name, local_notes)
    flush_edit_checkpoint(page)
    before = checkpoint_record(page, name)
    external = save_other_tab(page.context, name, "Official update after restore, before Save")
    with page.expect_response(
        lambda response: "frappe.desk.form.save.savedocs" in response.url,
        timeout=30_000,
    ) as save_response:
        evaluate(page, "initiate stale native Save", """() => {
            window.__al131StaleSave = 'pending';
            Promise.resolve(cur_frm.save()).then(
                () => { window.__al131StaleSave = 'settled'; },
                () => { window.__al131StaleSave = 'rejected'; }
            );
            return true;
        }""")
    response = save_response.value
    payload = response.json()
    assert response.status >= 400, "A stale restored EDIT must be rejected by native Frappe Save"
    assert payload.get("exc_type") == "TimestampMismatchError", payload.get("exc_type")
    assert server_document(page, name)["order_notes"] == external["order_notes"]
    retained = checkpoint_record(page, name)
    assert retained["draft_id"] == before["draft_id"]
    assert retained["payload"]["dco"]["order_notes"] == local_notes
    record_scenario("server_edit_between_restore_and_native_save", native_error=payload["exc_type"], draft_retained=True)

    name = FIXTURES["internal_checkpoint"]
    open_dco(page, name)
    start_edit_and_set_note(page, name, "Native internal pre-plan checkpoint", checkpoint=True)
    before = checkpoint_record(page, name)
    result = evaluate(page, "acknowledge native internal pre-plan Save",
                      "() => AlmdinaOrderRevisionUX.persistOrderEditCheckpoint(cur_frm)")
    assert result is True
    wait_for_function(page, "internal checkpoint keeps active EDIT", """() =>
        !cur_frm.is_dirty() && AlmdinaDcoEditSessionCoordinator.isEditing(cur_frm, 'order')
    """)
    official = server_document(page, name)
    assert official["modified"] != before["expected_server_modified"]
    evaluate(page, "input after acknowledged internal checkpoint",
             "() => cur_frm.set_value('order_notes', 'Unsaved input after pre-plan checkpoint')")
    flush_edit_checkpoint(page)
    after = checkpoint_record(page, name)
    assert after["session_origin_modified"] == before["session_origin_modified"]
    assert after["expected_server_modified"] == official["modified"]
    page.reload(wait_until="domcontentloaded")
    open_dco(page, name)
    continue_edit_checkpoint(page, name, "Unsaved input after pre-plan checkpoint")
    assert server_document(page, name)["order_notes"] == "Native internal pre-plan checkpoint"
    record_scenario("acknowledged_internal_preplan_checkpoint", origin_immutable=True, expected_version_advanced=True)


def certify_edit_two_tab_revision_fence(page: Page) -> None:
    name = FIXTURES["two_tabs"]
    open_dco(page, name)
    notes = "Shared EDIT checkpoint before two-tab conflict"
    start_edit_and_set_note(page, name, notes, checkpoint=True)
    page.reload(wait_until="domcontentloaded")
    open_dco(page, name)
    continue_edit_checkpoint(page, name, notes)
    flush_edit_checkpoint(page)
    other = page.context.new_page()
    attach_browser_diagnostics(other)
    try:
        open_dco(other, name)
        continue_edit_checkpoint(other, name, notes)
        flush_edit_checkpoint(other)
        # Reopen only the first tab to acknowledge the second tab's durable
        # revision. The second tab then retains that older base while A writes.
        page.reload(wait_until="domcontentloaded")
        open_dco(page, name)
        continue_edit_checkpoint(page, name, notes)
        flush_edit_checkpoint(page)
        evaluate(page, "first tab writes a newer local revision",
                 "() => cur_frm.set_value('order_notes', 'Newer checkpoint owned by first tab')")
        flush_edit_checkpoint(page)
        newer = checkpoint_record(page, name)
        evaluate(other, "stale second tab attempts checkpoint", """async () => {
            await cur_frm.set_value('order_notes', 'Stale second tab must not overwrite');
            AlmdinaDcoRecovery.LocalCheckpoint.markDirty(cur_frm, 'DCO');
            await AlmdinaDcoRecovery.LocalCheckpoint.flush(cur_frm);
        }""")
        wait_for_function(other, "stale second tab is quarantined", """() => {
            const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);
            return state?.state === 'ERROR'
                && ['stale_revision', 'revision_conflict'].includes(state.error?.code)
                && AlmdinaDcoRecovery.LocalCheckpoint.markDirty(cur_frm, 'DCO') === false;
        }""")
        retained = checkpoint_record(page, name)
        assert retained["payload_hash"] == newer["payload_hash"]
        assert retained["recovery_revision"] == newer["recovery_revision"]
        assert retained["payload"]["dco"]["order_notes"] == "Newer checkpoint owned by first tab"
        record_scenario("two_tab_revision_conflict", newer_revision_preserved=True)
    finally:
        other.close()


def certify_edit_late_responses(page: Page) -> None:
    name = FIXTURES["late_restore"]
    other_name = FIXTURES["identity_b"]
    open_dco(page, name)
    start_edit_and_set_note(page, name, "Late restore must remain bound to its source DCO", checkpoint=True)
    page.reload(wait_until="domcontentloaded")
    open_dco(page, name)
    original = checkpoint_record(page, name)
    other_baseline = server_document(page, other_name)
    held = []
    paused_once = False

    def pause_real_request(route) -> None:
        # Delay delivery only. continue_ below sends this exact original request
        # to Frappe; no response, permission result or server data is fabricated.
        nonlocal paused_once
        query = parse_qs(urlsplit(route.request.url).query)
        if paused_once or (route.request.method == "GET" and query.get("name") != [name]):
            route.continue_()
            return
        paused_once = True
        held.append(route)
        page.evaluate("() => { window.__al131RequestPaused = true; }")

    pattern = "**/api/method/frappe.client.get?**"
    page.route(pattern, pause_real_request)
    try:
        button = page.locator('.modal.show [data-edit-recovery-action="continue"]')
        expect(button).to_be_enabled()
        button.click()
        page.wait_for_function("() => window.__al131RequestPaused === true")
        assert len(held) == 1
        open_dco(page, other_name, wait_for_route=False)
        with page.expect_response(lambda response: "frappe.client.get?" in response.url) as late:
            held.pop().continue_()
        assert late.value.status == 200
        late.value.finished()
        wait_for_function(page, "late restore response settles without changing B", """({name, notes}) =>
            frappe.request.ajax_count === 0 && cur_frm.doc.name === name
            && cur_frm.doc.order_notes === notes
        """, arg={"name": other_name, "notes": other_baseline["order_notes"]})
        expect(page.locator('.modal.show [data-edit-recovery-action="continue"]')).to_have_count(0)
        retained = checkpoint_record(page, name)
        assert retained["payload_hash"] == original["payload_hash"]
        assert retained["recovery_revision"] == original["recovery_revision"]
        record_scenario("late_restore_api_response_after_navigation", source_draft_retained=True, other_document_unchanged=True)
    finally:
        # Removing the handler can release pending routes. Release our owned
        # request first and remove it from the list so it is continued once.
        while held:
            held.pop().continue_()
        page.unroute(pattern, pause_real_request)

    name = FIXTURES["pending_checkpoint"]
    open_dco(page, name)
    start_edit_and_set_note(page, name, "Internal checkpoint with unacknowledged request", checkpoint=True)
    original = checkpoint_record(page, name)
    held = []
    paused_once = False
    pattern = "**/api/method/frappe.desk.form.save.savedocs"
    page.route(pattern, pause_real_request)
    try:
        evaluate(page, "start actual internal checkpoint without pretending acknowledgement", """() => {
            window.__al131RequestPaused = false;
            window.__al131CheckpointSettled = false;
            Promise.resolve(AlmdinaOrderRevisionUX.persistOrderEditCheckpoint(cur_frm)).then(
                () => { window.__al131CheckpointSettled = true; },
                () => { window.__al131CheckpointSettled = true; }
            );
            return true;
        }""")
        page.wait_for_function("() => window.__al131RequestPaused === true")
        assert len(held) == 1
        unacknowledged = checkpoint_record(page, name)
        assert unacknowledged["session_origin_modified"] == original["session_origin_modified"]
        assert unacknowledged["expected_server_modified"] == original["expected_server_modified"]
        assert server_document(page, name)["modified"] == original["expected_server_modified"]
        open_dco(page, other_name, wait_for_route=False)
        with page.expect_response(lambda response: "frappe.desk.form.save.savedocs" in response.url) as late:
            held.pop().continue_()
        assert late.value.status == 200
        late.value.finished()
        wait_for_function(page, "late internal checkpoint completion remains bound to A", """({name, notes}) =>
            frappe.request.ajax_count === 0 && window.__al131CheckpointSettled
            && cur_frm.doc.name === name && cur_frm.doc.order_notes === notes
        """, arg={"name": other_name, "notes": other_baseline["order_notes"]})
        assert server_document(page, name)["order_notes"] == "Internal checkpoint with unacknowledged request"
        assert server_document(page, other_name)["modified"] == other_baseline["modified"]
        record_scenario("unacknowledged_internal_checkpoint_and_late_save_response",
                        no_premature_version_advance=True, other_document_unchanged=True)
    finally:
        while held:
            held.pop().continue_()
        page.unroute(pattern, pause_real_request)


def certify_assignment_change(admin_page: Page) -> None:
    browser = admin_page.context.browser
    if browser is None:
        raise RuntimeError("Assignment certification requires Chromium")
    context = browser.new_context(locale="en-US")
    worker_page = context.new_page()
    attach_browser_diagnostics(worker_page)
    name = FIXTURES["assignment"]
    try:
        login_to_desk(worker_page, FIXTURES["worker"], "dco-test-worker-password")
        open_dco(worker_page, name)
        start_edit_and_set_note(worker_page, name, "Retained original-worker draft", checkpoint=True)
        original = checkpoint_record(worker_page, name)
        baseline = server_document(admin_page, name)
        evaluate(admin_page, "dispatch assignment fixture", """args => frappe.xcall(
            'almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order', args
        )""", {"order_name": name, "path": FIXTURES["route"], "assignee": FIXTURES["worker"]})
        dispatched = server_document(admin_page, name)
        assert dispatched["current_assignee"] == FIXTURES["worker"]
        evaluate(admin_page, "reassign stage through actual production command", """args => frappe.xcall(
            'almdina_erp.almdina_erp.services.shop_floor_commands.reassign_worker', args
        )""", {"stage_name": dispatched["current_production_stage"], "assignee": FIXTURES["replacement_worker"]})
        reassigned = server_document(admin_page, name)
        assert reassigned["current_assignee"] == FIXTURES["replacement_worker"]
        result = evaluate(worker_page, "original worker cannot save after reassignment", """async () => {
            const doc = JSON.parse(JSON.stringify(cur_frm.doc));
            doc.order_notes = 'Forbidden original-worker mutation';
            try { await frappe.xcall('frappe.client.save', {doc: JSON.stringify(doc)}); return {rejected: false}; }
            catch (error) { return {rejected: true, type: frappe.last_response?.exc_type || null}; }
        }""")
        assert result["rejected"] is True
        assert server_document(admin_page, name)["order_notes"] == baseline["order_notes"]
        retained = checkpoint_record(worker_page, name)
        assert retained["payload_hash"] == original["payload_hash"]
        # This is an authoritative lifecycle/scope transition. A fresh native
        # Form navigation may show permission denial, but may never offer EDIT.
        with worker_page.expect_response(
            lambda response: "frappe.desk.form.load.getdoc" in response.url,
            timeout=60_000,
        ) as loaded:
            worker_page.reload(wait_until="domcontentloaded")
        assert loaded.value.status in {200, 403}, loaded.value.status
        loaded.value.finished()
        wait_for_function(worker_page, "reassignment navigation settles", """() =>
            window.frappe?.boot && frappe.request.ajax_count === 0
        """)
        expect(worker_page.locator('.modal.show [data-edit-recovery-action="continue"]')).to_have_count(0)
        record_scenario("assignment_change_after_dispatch", old_worker_save_rejected=True, local_draft_retained=True)
    finally:
        context.close()


def certify_edit_restart_rows_and_offline(playwright_instance) -> None:
    """Close/reopen a tab and restart real Chromium with the same disk profile."""
    name = FIXTURES["rows_restart"]
    notes = "Offline EDIT with added, deleted and reordered rows"
    with tempfile.TemporaryDirectory(prefix="al131-chromium-profile-") as profile:
        context = playwright_instance.chromium.launch_persistent_context(profile, locale="en-US")
        page = context.new_page()
        attach_browser_diagnostics(page)
        try:
            login_to_desk(page, "Administrator", "admin")
            open_dco(page, name)
            original = server_document(page, name)
            start_edit_and_set_note(page, name, notes, checkpoint=False)
            context.set_offline(True)
            expected = evaluate(page, "real offline child-row lifecycle", """async edgeType => {
                const frm = cur_frm;
                const removed = frm.doc.pieces[1];
                await frm.script_manager.trigger('before_pieces_remove', removed.doctype, removed.name);
                frappe.model.clear_doc(removed.doctype, removed.name);
                await frm.script_manager.trigger('pieces_remove', removed.doctype, removed.name);
                const added = frm.add_child('pieces', {
                    piece_type: 'Regular', width_cm: 47, length_cm: 87, qty: 2,
                    notes: 'New unsaved row returns after real browser restart',
                });
                await frm.script_manager.trigger('pieces_add', added.doctype, added.name);
                const last = frm.doc.pieces.pop();
                frm.doc.pieces.unshift(last);
                frm.doc.pieces.forEach((row, index) => { row.idx = index + 1; row.piece_no = index + 1; });
                const row = frm.doc.pieces[1];
                await frappe.model.set_value(row.doctype, row.name, {
                    edge_long_left: 1, edge_long_left_type_override: edgeType,
                    extra_full_door_double: 1, extra_liner: 1,
                    liner_reference_side: 'edge_long_left', liner_offset_cm: 0,
                    liner_width_cm: 1.8, liner_start_cm: 0, liner_length_cm: 100,
                    notes: 'Edges and extras survive EDIT hydration',
                });
                frm.refresh_field('pieces');
                frm.dirty();
                return {
                    removedName: removed.name,
                    retainedNames: frm.doc.pieces.filter(item => item !== added).map(item => item.name),
                    rowNotes: frm.doc.pieces.map(item => item.notes),
                    widths: frm.doc.pieces.map(item => Number(item.width_cm)),
                };
            }""", FIXTURES["edge_type"])
            ack = flush_edit_checkpoint(page)
            durable = checkpoint_record(page, name)
            assert durable["payload"]["dco"]["order_notes"] == notes
            assert len(durable["payload"]["dco"]["pieces"]) == 3
            context.set_offline(False)
            assert server_document(page, name)["modified"] == original["modified"]
            record_scenario("offline_edit_checkpoint", acknowledged_revision=ack["saved_revision"], server_unchanged=True)

            page.close()
            page = context.new_page()
            attach_browser_diagnostics(page)
            open_dco(page, name)
            continue_edit_checkpoint(page, name, notes)
            flush_edit_checkpoint(page)
            record_scenario("edit_tab_close_reopen", same_profile=True, explicit_continue=True)
        finally:
            context.set_offline(False)
            context.close()

        # Closing the persistent context above terminates its Chromium process;
        # the next launch reuses its real on-disk IndexedDB and session cookies.
        context = playwright_instance.chromium.launch_persistent_context(profile, locale="en-US")
        page = context.new_page()
        attach_browser_diagnostics(page)
        try:
            open_dco(page, name)
            continue_edit_checkpoint(page, name, notes)
            result = evaluate(page, "verify actual child-row hydration after browser restart", """() => ({
                names: cur_frm.doc.pieces.map(row => row.name),
                notes: cur_frm.doc.pieces.map(row => row.notes),
                widths: cur_frm.doc.pieces.map(row => Number(row.width_cm)),
                edge: cur_frm.doc.pieces[1].edge_long_left,
                override: cur_frm.doc.pieces[1].edge_long_left_type_override,
                double: cur_frm.doc.pieces[1].extra_full_door_double,
                liner: cur_frm.doc.pieces[1].extra_liner,
                linerWidth: cur_frm.doc.pieces[1].liner_width_cm,
            })""")
            assert result["notes"] == expected["rowNotes"]
            assert result["widths"] == expected["widths"]
            assert expected["removedName"] not in result["names"]
            assert result["names"][1:] == expected["retainedNames"]
            assert len(result["names"]) == len(set(result["names"])) == 3
            assert int(result["edge"]) == int(result["double"]) == int(result["liner"]) == 1
            assert result["override"] == FIXTURES["edge_type"]
            assert float(result["linerWidth"]) == 1.8
            assert server_document(page, name)["modified"] == original["modified"]
            record_scenario("edit_full_browser_restart_rows_edges_extras", browser=context.browser.version,
                            deleted_row_absent=True, retained_identity_preserved=True, no_duplicate_rows=True)

            # Native history navigation must never apply A's dirty projection to B.
            other_name = FIXTURES["identity_b"]
            other_baseline = server_document(page, other_name)["order_notes"]
            open_dco(page, other_name)
            page.go_back(wait_until="domcontentloaded")
            wait_for_function(page, "browser Back returns exact DCO", "name => cur_frm?.doc?.name === name", arg=name)
            page.go_forward(wait_until="domcontentloaded")
            wait_for_function(page, "browser Forward returns isolated DCO", """({name, notes}) =>
                cur_frm?.doc?.name === name && cur_frm.doc.order_notes === notes
            """, arg={"name": other_name, "notes": other_baseline})
            expect(page.locator('.modal.show [data-edit-recovery-action="continue"]')).to_have_count(0)
            assert server_document(page, other_name)["order_notes"] == other_baseline
            record_scenario("edit_browser_back_forward_isolation", other_document_unchanged=True)
        finally:
            context.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        evidence_dir = Path(os.environ.get("DCO_DESK_EVIDENCE_DIR", "/tmp/dco-desk-evidence"))
        evidence_dir.mkdir(parents=True, exist_ok=True)
        TRACE_PATH = evidence_dir / "dco-desk-trace.json"
        browser = playwright.chromium.launch()
        # Frappe v16 uses Intl.Locale(navigator.language) while creating a Form.
        # The CI host locale may be an invalid BCP-47 value (for example C).
        # Match other pinned Desk suites with a valid browser locale.
        context = browser.new_context(locale="en-US")
        # Instrument the first native Form creation in every new document.
        # Hooks installed after login are lost on full navigation; this
        # init script observes the pinned Form lifecycle before the route loads.
        context.add_init_script(script="""(() => {
            const events = [];
            window.__al131NativeFormTrace = events;
            const record = (phase, frm, error) => {
                if (frm?.doctype !== 'Door Cutting Order') return;
                events.push({
                    phase, name: String(frm.docname || ''),
                    setupDone: Boolean(frm.setup_done),
                    formLayout: Boolean(frm.layout),
                    hasRead: Boolean(frm.perm?.[0]?.read),
                    opened: Boolean(frm.opendocs?.[frm.docname]),
                    error: error ? String(error?.stack || error).slice(0, 800) : null
                });
                if (events.length > 32) events.shift();
            };
            const install = () => {
                const proto = window.frappe?.ui?.form?.Form?.prototype;
                if (!proto) return false;
                if (proto.__al131TraceInstalled) return true;
                proto.__al131TraceInstalled = true;
                for (const name of ['refresh', 'setup', 'check_doctype_conflict', 'check_reload']) {
                    const original = proto[name];
                    if (typeof original !== 'function') continue;
                    proto[name] = function (...args) {
                        record(name + ':enter', this);
                        try {
                            const value = original.apply(this, args);
                            record(name + ':return', this);
                            return value;
                        } catch (error) {
                            record(name + ':throw', this, error);
                            throw error;
                        }
                    };
                }
                return true;
            };
            const interval = setInterval(() => {
                if (install()) clearInterval(interval);
            }, 10);
        })();""")
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(30_000)
        attach_browser_diagnostics(page)
        try:
            certify_actual_frappe_desk_edit_recovery(page)
            certify_edit_conflicts_and_internal_checkpoint(page)
            certify_edit_two_tab_revision_fence(page)
            certify_edit_late_responses(page)
            certify_assignment_change(page)
            certify_edit_restart_rows_and_offline(playwright)
            _trace_event("certification_completed")
            print("AL131_REAL_DESK_EVIDENCE " + json.dumps(CERTIFIED_SCENARIOS, ensure_ascii=False))
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
