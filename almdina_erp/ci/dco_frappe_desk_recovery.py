from __future__ import annotations

import json
import os
import re
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
LAST_FAILED_STEP: str | None = None
LAST_PAGE_STATE: dict[str, object] | None = None
LAST_ACTIVE_PAGE: Page | None = None
PAGE_STATE_CACHE: dict[int, dict[str, object]] = {}
PAGE_LIFECYCLE: dict[int, dict[str, object]] = {}


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


def _savedocs_request_data(request) -> tuple[dict[str, object], str]:
    """Read document and Save action from the observed official-save request."""
    body = request.post_data or ""
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        fields = parse_qs(body, keep_blank_values=True)
        raw_doc = fields.get("doc", [""])[0]
        try:
            payload = json.loads(raw_doc)
        except (TypeError, ValueError):
            return {}, str(fields.get("action", [""])[0])
    document = payload.get("doc") if isinstance(payload, dict) else None
    action = str(payload.get("action") or "") if isinstance(payload, dict) else ""
    if isinstance(document, str):
        try:
            document = json.loads(document)
        except (TypeError, ValueError):
            return {}, action
    return (document if isinstance(document, dict) else {}), action


def _page_lifecycle(page: Page) -> dict[str, object]:
    return PAGE_LIFECYCLE.setdefault(id(page), {
        "closed": False,
        "crashed": False,
        "url": "",
        "last_event": "attached",
    })


def _page_unusable(page: Page) -> bool:
    lifecycle = _page_lifecycle(page)
    return bool(lifecycle["closed"] or lifecycle["crashed"])


def _safe_page_url(page: Page) -> str:
    lifecycle = _page_lifecycle(page)
    # URL comes only from main-frame navigation events so diagnostics never
    # query a renderer that may already be stalled.
    return _safe_url(str(lifecycle.get("url") or ""))


def ui_step(page: Page, step: str, action):
    """Trace each user-like locator operation before touching the page."""
    global ACTIVE_STEP, LAST_ACTIVE_PAGE, LAST_FAILED_STEP
    LAST_ACTIVE_PAGE = page
    ACTIVE_STEP = step
    LAST_FAILED_STEP = None
    # The trace writer persists atomically before the Playwright action starts.
    _trace_event("step_started", step=step)
    try:
        result = action()
    except Exception as exc:
        LAST_FAILED_STEP = step
        _trace_event("step_failed", step=step, error=_redact_text(str(exc)))
        ACTIVE_STEP = None
        raise RuntimeError(f"Desk UI step '{step}' failed: {exc}") from exc
    _trace_event("step_completed", step=step)
    ACTIVE_STEP = None
    return result


def attach_browser_diagnostics(page: Page) -> None:
    global LAST_PAGE_STATE
    LAST_PAGE_STATE = None
    lifecycle = _page_lifecycle(page)
    PAGE_STATE_CACHE[id(page)] = {}

    def mark_lifecycle(event: str, **details) -> None:
        lifecycle["last_event"] = event
        if event == "page_closed":
            lifecycle["closed"] = True
        elif event == "page_crashed":
            lifecycle["crashed"] = True
        _trace_event(event, **details)

    def append(bucket: str, item: dict[str, str | int | None]) -> None:
        events = DIAGNOSTIC_EVENTS[bucket]
        events.append(item)
        if len(events) > 100:
            del events[:-100]

    def on_frame_navigated(frame) -> None:
        try:
            if frame == page.main_frame:
                lifecycle["url"] = frame.url
                mark_lifecycle("navigation", url=_safe_url(frame.url))
        except Exception as exc:
            mark_lifecycle("navigation_event_unavailable", error=_redact_text(str(exc), 180))

    page.on("close", lambda: mark_lifecycle("page_closed", url=_safe_url(str(lifecycle.get("url", "")))))
    page.on("crash", lambda: mark_lifecycle("page_crashed", url=_safe_url(str(lifecycle.get("url", "")))))
    page.on("framenavigated", on_frame_navigated)

    page.on("load", lambda: _trace_event(
        "page_load_event", url=_safe_url(str(lifecycle.get("url") or ""))
    ))
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
    page.on("pageerror", lambda error: (
        append("page_errors", {
            "text": _redact_text(str(error)),
            "stack": _redact_text(str(getattr(error, "stack", "") or ""), 2500),
        }),
        _trace_event(
            "page_error",
            text=_redact_text(str(error)),
            stack=_redact_text(str(getattr(error, "stack", "") or ""), 2500),
        ),
    ))
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


def capture_page_document_state(page: Page, step: str) -> dict[str, object]:
    def snapshot() -> dict[str, object]:
        result = page.wait_for_function("""() => JSON.stringify((() => {
                const boot = window.frappe && frappe.boot;
                return {
                    url: location.href,
                    title: document.title,
                    readyState: document.readyState,
                    frappePresent: Boolean(window.frappe),
                    bootPresent: Boolean(boot),
                    setupComplete: boot && Boolean(boot.sysdefaults && boot.sysdefaults.setup_complete),
                    sysSetupComplete: boot && boot.sysdefaults && Boolean(boot.sysdefaults.setup_complete),
                    ajaxCount: window.frappe && frappe.request && frappe.request.ajax_count,
                    route: (() => {
                        const value = window.frappe && typeof frappe.get_route === "function"
                            ? frappe.get_route()
                            : null;
                        return Array.isArray(value) ? value.map(String).join("/") : "";
                    })(),
                    bodyText: (document.body && document.body.innerText || "").slice(0, 400),
                };
            })())""", timeout=5_000)
        try:
            state = json.loads(result.json_value())
        finally:
            result.dispose()
        return state

    state = ui_step(page, step, snapshot)
    global LAST_PAGE_STATE
    LAST_PAGE_STATE = state
    PAGE_STATE_CACHE[id(page)] = dict(state)
    _trace_event(
        "document_loaded",
        url=_safe_url(str(state.get("url", ""))),
        title=_redact_text(str(state.get("title", "")), 120),
        ready_state=str(state.get("readyState", "")),
        frappe_present=bool(state.get("frappePresent")),
        boot_present=bool(state.get("bootPresent")),
        setup_complete=bool(state.get("setupComplete")),
        sys_setup_complete=bool(state.get("sysSetupComplete")),
        ajax_count=state.get("ajaxCount") if isinstance(state.get("ajaxCount"), int) else None,
        route=_redact_text(str(state.get("route", "")), 120),
        body_text="" if os.environ.get("DCO_DESK_COMPARISON_CASE") else
            _redact_text(str(state.get("bodyText", "")), 400),
    )
    return state


def evaluate(page: Page, step: str, expression: str, arg=None):
    global ACTIVE_STEP, LAST_ACTIVE_PAGE
    LAST_ACTIVE_PAGE = page
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
    # Chromium's main thread may be unresponsive after a page error. Failure
    # handling must not re-enter it with another evaluate or load-state wait.
    state = dict(PAGE_STATE_CACHE.get(id(page), LAST_PAGE_STATE or {}))
    state["url"] = _safe_page_url(page)
    lifecycle = _page_lifecycle(page)
    state["pageLifecycle"] = {
        "closed": lifecycle["closed"],
        "crashed": lifecycle["crashed"],
        "last_event": lifecycle["last_event"],
    }
    return state


def wait_for_function(page: Page, step: str, expression: str, *, arg=None, timeout: int = 30_000):
    global LAST_ACTIVE_PAGE
    LAST_ACTIVE_PAGE = page
    _trace_event("wait_started", step=step)
    try:
        page.wait_for_function(expression, arg=arg, timeout=timeout)
    except Exception as exc:
        _trace_event("wait_failed", step=step, error=_redact_text(str(exc)))
        state = read_page_state(page)
        raise RuntimeError(f"Desk browser wait '{step}' failed: {exc}; desk_state={state}") from exc
    _trace_event("wait_completed", step=step)


def active_form_page(page: Page, step: str):
    page_locator = ui_step(
        page,
        f"{step}: locate active form container",
        lambda: page.locator(".layout-main-section:visible").last,
    )
    ui_step(
        page,
        f"{step}: wait for visible form container",
        lambda: page_locator.wait_for(state="visible", timeout=15_000),
    )
    return page_locator


def capture_new_form_dom_evidence(
    page: Page,
    step: str,
    *,
    stage: str,
    timeout_ms: int = 2_500,
) -> dict[str, object] | None:
    def inspect():
        result = page.wait_for_function("""() => {
            const visible = element => {
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return rect.width > 0 && rect.height > 0
                    && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const summarize = element => {
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return {
                    tag: element.tagName,
                    classes: String(element.className || '').slice(0, 140),
                    visible: visible(element),
                    display: style.display,
                    visibility: style.visibility,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                };
            };
            const roots = [...document.querySelectorAll('.form-page')];
            const containers = [...document.querySelectorAll('.layout-main-section')];
            const wrapper = containers.filter(visible).at(-1) || containers.at(-1) || document;
            const controls = [...wrapper.querySelectorAll('.frappe-control')];
            const customer = [...wrapper.querySelectorAll(
                '.frappe-control[data-fieldname="customer"]'
            )];
            const inputs = customer.flatMap(wrapper => [...wrapper.querySelectorAll('input')]);
            return JSON.stringify({
                route: location.pathname,
                documentReadyState: document.readyState,
                visibilityState: document.visibilityState,
                formPages: roots.length,
                visibleFormPages: roots.filter(visible).length,
                formPageDom: roots.slice(-4).map(summarize),
                layoutMainSections: containers.length,
                visibleLayoutMainSections: containers.filter(visible).length,
                layoutMainDom: containers.slice(-4).map(summarize),
                visibleControls: controls.filter(visible).length,
                visibleSections: [...wrapper.querySelectorAll('.form-section')].filter(visible).length,
                customerWrappers: customer.length,
                visibleCustomerWrappers: customer.filter(visible).length,
                customerInputs: inputs.length,
                visibleCustomerInputs: inputs.filter(visible).length,
                enabledCustomerInputs: inputs.filter(input => !input.disabled).length,
                customerOwnerClasses: inputs[0]
                    ? [inputs[0].parentElement, inputs[0].parentElement?.parentElement,
                        inputs[0].parentElement?.parentElement?.parentElement]
                        .filter(Boolean).map(element => String(element.className || '').slice(0, 120))
                    : [],
            });
        }""", timeout=timeout_ms)
        try:
            return json.loads(result.json_value())
        finally:
            result.dispose()

    try:
        evidence = ui_step(page, f"{step}: capture DOM evidence ({stage})", inspect)
    except Exception as exc:
        _trace_event(
            "new_form_dom_capture_failed",
            step=step,
            stage=stage,
            error=_redact_text(str(exc), 300),
        )
        return None
    _trace_event(
        "new_form_dom_evidence",
        step=step,
        stage=stage,
        diagnostic=json.dumps(evidence, ensure_ascii=False),
    )
    return evidence


def capture_form_wait_failure(page: Page, step: str, failure: Exception) -> None:
    global LAST_FAILED_STEP
    failed_step = LAST_FAILED_STEP or step
    snapshot = None
    capture_failure = None
    if not _page_unusable(page):
        try:
            snapshot = capture_new_form_dom_evidence(
                page,
                step,
                stage="at_wait_failure",
                timeout_ms=1_500,
            )
            if snapshot is None:
                capture_failure = "DOM snapshot unavailable; see new_form_dom_capture_failed trace event"
        except Exception as exc:
            capture_failure = _redact_text(str(exc), 300)

    now = time.time()
    pending_methods = [
        {
            "url": item["url"],
            "resource_type": item["resource_type"],
            "age_seconds": round(max(0, now - float(item["started"])), 1),
        }
        for item in PENDING_REQUESTS.values()
        if "/api/method/" in str(item.get("url", ""))
    ][-20:]
    _trace_event(
        "new_form_wait_diagnosis",
        step=step,
        failed_step=failed_step,
        failure=_redact_text(str(failure), 500),
        dom_snapshot=json.dumps(snapshot, ensure_ascii=False) if snapshot else "unavailable",
        dom_capture_failure=capture_failure,
        pending_api_requests=json.dumps(pending_methods, ensure_ascii=False),
    )
    LAST_FAILED_STEP = failed_step


def wait_for_new_form_loaded(page: Page, step: str):
    try:
        form_page = active_form_page(page, step)
        ui_step(
            page,
            f"{step}: verify visible DCO form control",
            lambda: expect(form_page.locator(".frappe-control:visible").first).to_be_visible(),
        )
        return form_page
    except Exception as exc:
        capture_form_wait_failure(page, step, exc)
        raise


def wait_for_customer_interactive(page: Page, form_page, step: str):
    capture_new_form_dom_evidence(page, step, stage="before_customer_wait")
    try:
        customer = ui_step(
            page,
            f"{step}: locate Customer input in active form page",
            lambda: form_page.locator('.frappe-control[data-fieldname="customer"] input').first,
        )
        ui_step(page, f"{step}: wait for visible Customer control", lambda: customer.wait_for(state="visible", timeout=15_000))
        enabled = ui_step(page, f"{step}: verify Customer control enabled", customer.is_enabled)
        if not enabled:
            raise RuntimeError(f"Customer field is visible but disabled during {step}.")
        return customer
    except Exception as exc:
        capture_form_wait_failure(page, step, exc)
        raise


def ui_fill(page: Page, form_page, step: str, selector: str, value: str) -> None:
    ui_step(page, step, lambda: form_page.locator(selector).first.fill(value))


def ui_select(page: Page, form_page, step: str, selector: str, *, label: str) -> None:
    ui_step(page, step, lambda: form_page.locator(selector).first.select_option(label=label))


def ui_click(page: Page, step: str, selector: str, *, scope=None) -> None:
    root = scope if scope is not None else page
    ui_step(page, step, lambda: root.locator(selector).first.click())


def open_dco(page: Page, name: str) -> None:
    target_url = f"{DESK_URL}/app/door-cutting-order/{name}"
    _trace_event("open_dco_started", url=_safe_url(target_url))
    response = page.goto(target_url, wait_until="domcontentloaded")
    # Desk may satisfy this navigation through its SPA router and history API;
    # Playwright then returns None because there was no top-level HTTP response.
    if response is not None and response.status >= 400:
        raise RuntimeError(f"DCO navigation returned HTTP {response.status}: {_safe_page_url(page)}")
    try:
        wait_for_function(page, f"load DCO {name}",
            "name => window.cur_frm && window.cur_frm.doc && window.cur_frm.doc.name === name",
            arg=name,
            timeout=30_000,
        )
    except Exception as exc:
        state = read_page_state(page)
        raise RuntimeError(
            f"Loading DCO {name} in Desk timed out: {exc}; desk_state={state}"
        ) from exc
    _trace_event("open_dco_completed", url=_safe_page_url(page))


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


def login_to_desk(page: Page, user: str, password: str) -> None:
    response = page.goto(f"{DESK_URL}/login", wait_until="domcontentloaded")
    if response is None or response.status >= 400:
        status = response.status if response is not None else None
        raise RuntimeError(f"Frappe login page returned HTTP {status}: {_safe_page_url(page)}")
    email = ui_step(page, f"{user} login: locate email field", lambda: page.locator("#login_email"))
    ui_step(page, f"{user} login: wait for email field", lambda: email.wait_for(state="visible", timeout=15_000))
    ui_step(page, f"{user} login: enter email", lambda: email.fill(user))
    ui_step(page, f"{user} login: enter password", lambda: page.locator("#login_password").fill(password))
    ui_step(page, f"{user} login: submit credentials", lambda: page.get_by_role("button", name=re.compile(r"^(Login|Continue)$")).click())
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
    capture_page_document_state(page, f"capture {user} Desk boot state")
    _trace_event("login_established")


def certify_worker_identity_and_dynamic_permissions(admin_page: Page) -> None:
    browser = admin_page.context.browser
    if browser is None:
        raise RuntimeError("Desk identity certification requires a browser context.")
    worker_context = browser.new_context()
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
        worker_page.locator('[data-edit-recovery-action="continue"]').wait_for(
            state="visible", timeout=30_000
        )
        worker_page.locator('[data-edit-recovery-action="continue"]').click()
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


def open_new_dco_form(page: Page, step: str):
    new_route = f"{DESK_URL}/app/door-cutting-order/new-door-cutting-order-1"
    response = ui_step(page, f"{step}: navigate to NEW DCO", lambda: page.goto(new_route, wait_until="domcontentloaded"))
    if response is not None and response.status >= 400:
        raise RuntimeError(f"NEW DCO navigation returned HTTP {response.status} at {_safe_page_url(page)}.")
    capture_new_form_dom_evidence(page, f"{step}: DOM after navigation", stage="after_navigation")
    return wait_for_new_form_loaded(page, step)


def certify_actual_frappe_desk_new_recovery(page: Page, *, piece_count: int = 10) -> None:
    """Exercise NEW recovery through Desk UI; the 200-piece path is stress-only."""
    form_page = open_new_dco_form(page, "NEW DCO form loaded")
    customer = wait_for_customer_interactive(page, form_page, "NEW customer field interactive readiness")

    def fill_link(fieldname: str, value: str) -> None:
        if fieldname == "customer":
            control = customer
        else:
            control = ui_step(
                page,
                f"NEW {fieldname}: locate control in active form page",
                lambda: form_page.locator(f'.frappe-control[data-fieldname="{fieldname}"] input').first,
            )
            ui_step(page, f"NEW {fieldname}: wait for visible control", lambda: control.wait_for(state="visible", timeout=15_000))
        ui_step(page, f"NEW {fieldname}: fill Link field", lambda: control.fill(value))
        ui_step(
            page,
            f"NEW {fieldname}: choose Link suggestion",
            lambda: page.locator(".awesomplete li").filter(has_text=value).first.click(timeout=10_000),
        )

    fill_link("customer", FIXTURES["customer"])
    ui_fill(
        page, form_page, "NEW fill long order notes",
        '.frappe-control[data-fieldname="order_notes"] textarea',
        "Local Recovery checkpoint long note — " + "قطع MDF وملاحظات المعمل؛ " * 24,
    )
    ui_fill(page, form_page, "NEW fill board description", '.frappe-control[data-fieldname="board_description"] input', "MDF أبيض 18 مم")
    ui_fill(page, form_page, "NEW fill board length", '.frappe-control[data-fieldname="board_length_cm"] input', "244")
    ui_fill(page, form_page, "NEW fill board width", '.frappe-control[data-fieldname="board_width_cm"] input', "122")
    fill_link("default_edge_type", FIXTURES["edge_type"])
    ui_fill(page, form_page, "NEW fill edge color", '.frappe-control[data-fieldname="edge_color"] input', "White")
    ui_select(page, form_page, "NEW select cutting machine", '.frappe-control[data-fieldname="order_cutting_machine"] select', label="CNC")

    ui_step(
        page,
        "NEW measurements table visible in active form page",
        lambda: expect(form_page.locator('[data-fieldname="pieces_fast_entry"] .dco-fast-table')).to_be_visible(),
    )
    for index in range(piece_count):
        ui_step(page, f"NEW piece {index + 1}: enter width", lambda index=index: form_page.locator('[data-fieldname="pieces_fast_entry"] .dco-fast-table tbody tr.dco-virtual-row input[data-field="width_cm"]').fill(str(40 + index)))
        row_selector = '[data-fieldname="pieces_fast_entry"] .dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)'
        ui_step(page, f"NEW piece {index + 1}: enter length", lambda index=index: form_page.locator(row_selector).last.locator('input[data-field="length_cm"]').fill(str(180 + index)))
        ui_step(page, f"NEW piece {index + 1}: enter quantity", lambda index=index: form_page.locator(row_selector).last.locator('input[data-field="qty"]').fill(str(1 + index % 3)))
        ui_step(page, f"NEW piece {index + 1}: enter notes", lambda index=index: form_page.locator(row_selector).last.locator('input[data-field="notes"]').fill(f"قياس القطعة {index + 1}: ملاحظة معملية طويلة " * 4))
        if index % 2 == 0:
            ui_step(page, f"NEW piece {index + 1}: select Liner extra", lambda: form_page.locator(row_selector).last.locator('button[data-check-field="extra_liner"]').click())
        if index == 0:
            ui_step(page, "NEW piece 1: select Back Groove extra", lambda: form_page.locator(row_selector).last.locator('button[data-check-field="extra_back_groove"]').click())

    ui_step(page, "NEW checkpoint: verify row count", lambda: expect(form_page.locator('[data-fieldname="pieces_fast_entry"] .dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)')).to_have_count(piece_count))
    ui_step(page, "NEW checkpoint: wait for LOCAL_SAVED acknowledgement", lambda: expect(page.locator(".dco-recovery-status[data-recovery-state='LOCAL_SAVED']")).to_be_visible(timeout=30_000))
    _trace_event("new_recovery_checkpoint_confirmed", piece_count=piece_count)

    save_requests = []
    def record_save_request(request) -> None:
        if request.method != "POST" or "/api/method/frappe.desk.form.save.savedocs" not in request.url:
            return
        document, action = _savedocs_request_data(request)
        save_requests.append({"document": document, "action": action})

    page.on("request", record_save_request)
    ui_step(page, "NEW recovery: reload Desk form", lambda: page.reload(wait_until="domcontentloaded"))
    form_page = wait_for_new_form_loaded(page, "NEW DCO form loaded after refresh")
    wait_for_customer_interactive(page, form_page, "NEW customer field ready after refresh")
    ui_step(page, "NEW recovery: wait for Continue action", lambda: page.locator('[data-recovery-action="continue"]').wait_for(state="visible", timeout=30_000))
    ui_click(page, "NEW recovery: Continue draft", '[data-recovery-action="continue"]')
    ui_step(page, "NEW recovery: wait for Continue dialog to close", lambda: page.locator('[data-recovery-action="continue"]').wait_for(state="hidden", timeout=30_000))

    table_selector = '[data-fieldname="pieces_fast_entry"] .dco-fast-table'
    ui_step(page, "NEW recovery: verify customer restored", lambda: expect(form_page.locator('.frappe-control[data-fieldname="customer"] input')).to_have_value(FIXTURES["customer"]))
    ui_step(page, "NEW recovery: verify order notes restored", lambda: expect(form_page.locator('.frappe-control[data-fieldname="order_notes"] textarea')).to_have_value("Local Recovery checkpoint long note — " + "قطع MDF وملاحظات المعمل؛ " * 24))
    ui_step(page, "NEW recovery: verify board description restored", lambda: expect(form_page.locator('.frappe-control[data-fieldname="board_description"] input')).to_have_value("MDF أبيض 18 مم"))
    ui_step(page, "NEW recovery: verify board length restored", lambda: expect(form_page.locator('.frappe-control[data-fieldname="board_length_cm"] input')).to_have_value("244"))
    ui_step(page, "NEW recovery: verify board width restored", lambda: expect(form_page.locator('.frappe-control[data-fieldname="board_width_cm"] input')).to_have_value("122"))
    ui_step(page, "NEW recovery: verify edge type restored", lambda: expect(form_page.locator('.frappe-control[data-fieldname="default_edge_type"] input')).to_have_value(FIXTURES["edge_type"]))
    ui_step(page, "NEW recovery: verify edge color restored", lambda: expect(form_page.locator('.frappe-control[data-fieldname="edge_color"] input')).to_have_value("White"))
    ui_step(page, "NEW recovery: verify cutting machine restored", lambda: expect(form_page.locator('.frappe-control[data-fieldname="order_cutting_machine"] select')).to_have_value("CNC"))
    rows_selector = f"{table_selector} tbody tr[data-row-name]:not(.dco-virtual-row)"
    ui_step(page, "NEW recovery: verify restored row count", lambda: expect(form_page.locator(rows_selector)).to_have_count(piece_count))
    for index in range(piece_count):
        ui_step(page, f"NEW recovery: verify piece {index + 1} width", lambda index=index: expect(form_page.locator(rows_selector).nth(index).locator('input[data-field="width_cm"]')).to_have_value(str(40 + index)))
        ui_step(page, f"NEW recovery: verify piece {index + 1} length", lambda index=index: expect(form_page.locator(rows_selector).nth(index).locator('input[data-field="length_cm"]')).to_have_value(str(180 + index)))
        ui_step(page, f"NEW recovery: verify piece {index + 1} quantity", lambda index=index: expect(form_page.locator(rows_selector).nth(index).locator('input[data-field="qty"]')).to_have_value(str(1 + index % 3)))
        ui_step(page, f"NEW recovery: verify piece {index + 1} notes", lambda index=index: expect(form_page.locator(rows_selector).nth(index).locator('input[data-field="notes"]')).to_have_value(f"قياس القطعة {index + 1}: ملاحظة معملية طويلة " * 4))
        ui_step(page, f"NEW recovery: verify piece {index + 1} Liner extra", lambda index=index: expect(form_page.locator(rows_selector).nth(index).locator('button[data-check-field="extra_liner"]')).to_have_attribute("aria-pressed", "true" if index % 2 == 0 else "false"))
        ui_step(page, f"NEW recovery: verify piece {index + 1} Back Groove extra", lambda index=index: expect(form_page.locator(rows_selector).nth(index).locator('button[data-check-field="extra_back_groove"]')).to_have_attribute("aria-pressed", "true" if index == 0 else "false"))
    _trace_event("new_recovery_restore_verified", piece_count=piece_count)

    def click_official_save_and_wait_for_response():
        with page.expect_response(
            lambda candidate: "/api/method/frappe.desk.form.save.savedocs" in candidate.url,
            timeout=30_000,
        ) as save_response_info:
            page.locator(".page-head .primary-action").get_by_text("Save", exact=True).click()
        return save_response_info.value

    save_response = ui_step(
        page,
        "NEW recovery: official Save response",
        click_official_save_and_wait_for_response,
    )
    try:
        save_result = save_response.json()
    except Exception as exc:
        raise RuntimeError(f"Official NEW Save returned unreadable JSON: {exc}") from exc
    if (
        save_response.status != 200
        or not isinstance(save_result, dict)
        or save_result.get("exc")
        or save_result.get("exception")
    ):
        raise RuntimeError(
            f"Official NEW Save failed: HTTP {save_response.status}; "
            f"response_keys={sorted(save_result) if isinstance(save_result, dict) else []}."
        )
    if len(save_requests) != 1:
        raise RuntimeError(f"Expected one official DCO Save request, observed {len(save_requests)}.")
    saved_document = save_requests[0]["document"]
    if save_requests[0]["action"] != "Save":
        raise RuntimeError("The observed official DCO action was not the NEW Save operation.")
    creation_token = str(saved_document.get("recovery_creation_token") or "").strip()
    saved_name = str(saved_document.get("name") or "").strip()
    if not creation_token or not saved_name:
        raise RuntimeError("Official Save request did not carry the recovered DCO identity token.")

    canonical_response = page.context.request.get(
        f"{DESK_URL}/api/method/frappe.client.get_list",
        params={
            "doctype": "Door Cutting Order",
            "filters": json.dumps({"recovery_creation_token": creation_token}),
            "fields": json.dumps(["name", "recovery_creation_token"]),
            "limit_page_length": "5",
        },
        timeout=20_000,
    )
    if canonical_response.status != 200:
        raise RuntimeError(f"Canonical NEW DCO lookup returned HTTP {canonical_response.status}.")
    canonical_rows = canonical_response.json().get("message", [])
    if len(canonical_rows) != 1:
        raise RuntimeError(
            "Official Save did not produce exactly one canonical DCO for its creation token."
        )
    canonical_name = str(canonical_rows[0].get("name") or "").strip()
    if not canonical_name:
        raise RuntimeError("Canonical DCO lookup returned no permanent document identity.")
    if canonical_name != saved_name and not saved_name.startswith("new-"):
        # Frappe may rename a NEW form during savedocs; the payload name is then
        # temporary, while the canonical server record is authoritative.
        raise RuntimeError("The canonical DCO identity differs from the non-temporary saved document.")
    expect(page.locator(".dco-recovery-status[data-recovery-state='COMPLETED']")).to_be_visible(
        timeout=15_000
    )
    page.wait_for_function(
        "route => location.pathname === route",
        arg=f"/app/door-cutting-order/{canonical_name}",
        timeout=15_000,
    )
    _trace_event(
        "phase_135_local_new_recovery_completed" if piece_count == 10
        else "phase_135_new_recovery_stress_completed",
        piece_count=piece_count,
        official_save_requests=len(save_requests),
        official_save_http=save_response.status,
        canonical_record_count=len(canonical_rows),
    )


def certify_new_dco_form_smoke(page: Page) -> None:
    """Stop at visible NEW DCO form content; no field-interaction claim."""
    login_to_desk(page, "Administrator", "admin")
    open_new_dco_form(page, "NEW DCO Desk form-loaded Smoke")
    _trace_event("phase_135_new_form_smoke_completed")


def certify_new_customer_field_smoke(page: Page) -> None:
    """Prove the active NEW form's Customer link is interactive without recovery."""
    form_page = wait_for_new_form_loaded(page, "NEW Customer field Smoke")
    customer = wait_for_customer_interactive(page, form_page, "NEW Customer field Smoke")
    customer_name = FIXTURES["customer"]
    ui_step(page, "NEW Customer field Smoke: fill customer", lambda: customer.fill(customer_name))
    ui_step(
        page,
        "NEW Customer field Smoke: select customer suggestion",
        lambda: page.locator(".awesomplete li").filter(has_text=customer_name).first.click(timeout=10_000),
    )
    ui_step(
        page,
        "NEW Customer field Smoke: assert exact selected customer",
        lambda: expect(customer).to_have_value(customer_name),
    )
    _trace_event("phase_135_new_customer_field_smoke_completed")


def _start_comparison_cdp(browser, page):
    """Record only browser timing metadata, before DCO navigation begins."""
    browser_session = browser.new_browser_cdp_session()
    page_session = page.context.new_cdp_session(page)
    renderer_main_threads = set()
    trace_state = {"complete": False, "batches": 0, "events": 0}

    def on_trace_data(message):
        events = message.get("value", [])
        trace_state["batches"] += 1
        trace_state["events"] += len(events)
        previous_thread_count = len(renderer_main_threads)
        renderer_main_threads.update(
            (event.get("pid"), event.get("tid"))
            for event in events
            if event.get("name") == "thread_name"
            and (event.get("args") or {}).get("name") == "CrRendererMain"
        )
        long_tasks = [
            {
                "name": str(event.get("name", ""))[:80],
                "duration_ms": round(event.get("dur", 0) / 1000, 1),
            }
            for event in events
            if isinstance(event.get("dur"), (int, float)) and event["dur"] >= 100_000
            and (event.get("pid"), event.get("tid")) in renderer_main_threads
        ]
        if long_tasks:
            _trace_event("cdp_renderer_main_long_tasks", tasks=json.dumps(long_tasks[:12]))
        if len(renderer_main_threads) > previous_thread_count:
            _trace_event("cdp_renderer_main_identified", thread_count=len(renderer_main_threads))

    def on_trace_complete(_message):
        trace_state["complete"] = True
        _trace_event("comparison_cdp_tracing_complete",
            batches=trace_state["batches"], events=trace_state["events"])

    def on_metrics(message):
        selected = {
            metric["name"]: round(metric["value"], 3)
            for metric in message.get("metrics", [])
            if metric.get("name") in {"TaskDuration", "ScriptDuration", "JSHeapUsedSize"}
        }
        if selected:
            _trace_event("cdp_performance_metrics", metrics=json.dumps(selected))

    browser_session.on("Tracing.dataCollected", on_trace_data)
    browser_session.on("Tracing.tracingComplete", on_trace_complete)
    page_session.on("Performance.metrics", on_metrics)
    page_session.send("Performance.enable")
    browser_session.send("Tracing.start", {
        "categories": "devtools.timeline,v8.execute,toplevel",
        "options": "record-continuously",
        "transferMode": "ReportEvents",
    })
    _trace_event("comparison_cdp_started")
    return browser_session, trace_state


def _stop_comparison_cdp(browser_session, trace_state, page: Page, case: str) -> None:
    """Let CDP deliver trace events after Tracing.end before closing Chromium."""
    browser_session.send("Tracing.end")
    deadline = time.monotonic() + 2.5
    while not trace_state["complete"] and time.monotonic() < deadline:
        # This advances Playwright's dispatcher; it does not wait for Desk.
        page.wait_for_timeout(100)
    _trace_event(
        "comparison_cdp_stopped" if trace_state["complete"] else "comparison_cdp_flush_timeout",
        case=case,
        batches=trace_state["batches"],
        events=trace_state["events"],
    )


def _comparison_renderer_heartbeat(page: Page, case: str) -> None:
    """Check a trivial renderer task before interpreting a DOM inspection."""
    try:
        handle = page.wait_for_function("() => true", timeout=1_200)
        handle.dispose()
    except Exception as exc:
        _trace_event("comparison_renderer_heartbeat_failed", case=case,
            error=_redact_text(str(exc), 200))
    else:
        _trace_event("comparison_renderer_heartbeat_completed", case=case)


def certify_phase_a_comparison_case(browser, page: Page, case: str) -> None:
    """One independently bounded case; the workflow runs all four processes."""
    if case not in {"A", "B", "C", "D"}:
        raise ValueError(f"Unsupported Phase A comparison case: {case}")
    _trace_event("comparison_case_started", case=case)
    login_to_desk(page, "Administrator", "admin")

    if case == "D":
        failed_services = []
        for method in (
            "almdina_erp.almdina_erp.services.order_defaults_service.get_order_defaults",
            "almdina_erp.almdina_erp.services.edge_banding_lookup_service.get_order_edge_banding_options",
        ):
            started = time.monotonic()
            _trace_event("comparison_service_started", case=case, method=method)
            try:
                response = page.request.get(f"{DESK_URL}/api/method/{method}", timeout=10_000)
                status = response.status
                payload = response.json()
                result_class = "ok" if isinstance(payload, dict) and "message" in payload \
                    and not ("exc" in payload or "exception" in payload) else "error_payload"
            except Exception as exc:
                _trace_event("comparison_service_failed", case=case, method=method,
                    error=_redact_text(str(exc), 250), elapsed_seconds=round(time.monotonic() - started, 1))
                failed_services.append(method)
                continue
            _trace_event("comparison_service_completed", case=case, method=method,
                status=status, result_class=result_class,
                elapsed_seconds=round(time.monotonic() - started, 1))
            if status != 200 or result_class != "ok":
                failed_services.append(method)
        if failed_services:
            failure = f"Phase A services failed: {', '.join(failed_services)}"
            _trace_event("comparison_case_failed", case=case, error=failure)
            raise RuntimeError(failure)
    else:
        cdp_session = None
        cdp_trace_state = None
        if case in {"B", "C"}:
            try:
                cdp_session, cdp_trace_state = _start_comparison_cdp(browser, page)
            except Exception as exc:
                _trace_event("comparison_cdp_unavailable", case=case,
                    error=_redact_text(str(exc), 250))
        try:
            if case == "A":
                route = f"{DESK_URL}/app/todo/new-todo-1"
                _trace_event("comparison_navigation_started", case=case, route="/app/todo/new-todo-1")
                response = page.goto(route, wait_until="domcontentloaded", timeout=20_000)
                _trace_event("comparison_navigation_response", case=case,
                    status=response.status if response else None)
                if response is not None and response.status >= 400:
                    raise RuntimeError(f"Standard ToDo form returned HTTP {response.status}")
                _comparison_renderer_heartbeat(page, case)
                form = active_form_page(page, "standard Frappe ToDo form")
                form.locator(".frappe-control:visible").first.wait_for(state="visible", timeout=15_000)
                _trace_event("comparison_form_ready", case=case, doctype="ToDo")
            elif case == "B":
                _trace_event("comparison_navigation_started", case=case, route="/app/door-cutting-order")
                response = page.goto(f"{DESK_URL}/app/door-cutting-order",
                    wait_until="domcontentloaded", timeout=20_000)
                _trace_event("comparison_navigation_response", case=case,
                    status=response.status if response else None)
                if response is not None and response.status >= 400:
                    raise RuntimeError(f"DCO list returned HTTP {response.status}")
                # v16.17.5 list_view.js calls page.set_primary_action(...,
                # make_new_doc); page.js places it under .page-actions.
                new_action = page.locator(".page-actions .primary-action").first
                _trace_event("comparison_list_new_action_wait_started", case=case)
                new_action.wait_for(state="visible", timeout=15_000)
                _trace_event("comparison_list_new_action_ready", case=case)
                _trace_event("comparison_list_new_action_click_started", case=case)
                new_action.click(timeout=15_000)
                _trace_event("comparison_list_new_action_clicked", case=case)
                _comparison_renderer_heartbeat(page, case)
                capture_new_form_dom_evidence(page, "DCO NEW from Desk list",
                    stage="after_navigation", timeout_ms=1_200)
                wait_for_new_form_loaded(page, "DCO NEW from Desk list")
                certify_new_customer_field_smoke(page)
                _trace_event("comparison_form_ready", case=case, doctype="Door Cutting Order")
            else:
                _trace_event("comparison_navigation_started", case=case,
                    route="/app/door-cutting-order/new-door-cutting-order-1")
                response = page.goto(f"{DESK_URL}/app/door-cutting-order/new-door-cutting-order-1",
                    wait_until="domcontentloaded", timeout=20_000)
                _trace_event("comparison_navigation_response", case=case,
                    status=response.status if response else None)
                if response is not None and response.status >= 400:
                    raise RuntimeError(f"Direct DCO route returned HTTP {response.status}")
                _comparison_renderer_heartbeat(page, case)
                capture_new_form_dom_evidence(page, "DCO NEW via direct route",
                    stage="after_navigation", timeout_ms=1_200)
                wait_for_new_form_loaded(page, "DCO NEW via direct route")
                certify_new_customer_field_smoke(page)
                _trace_event("comparison_form_ready", case=case, doctype="Door Cutting Order")
            _trace_event("comparison_case_completed", case=case)
        except Exception as exc:
            _trace_event("comparison_case_failed", case=case,
                error=_redact_text(str(exc), 300))
            raise
        finally:
            if cdp_session is not None:
                try:
                    _stop_comparison_cdp(cdp_session, cdp_trace_state, page, case)
                except Exception as exc:
                    _trace_event("comparison_cdp_stop_failed", case=case,
                        error=_redact_text(str(exc), 250))
    if case == "D":
        _trace_event("comparison_case_completed", case=case)


def certify_edit_to_new_transition(page: Page) -> None:
    """Preserve the real EDIT → NEW navigation in the EDIT certification page."""
    form_page = open_new_dco_form(page, "EDIT to NEW transition")
    wait_for_customer_interactive(page, form_page, "EDIT to NEW Customer field readiness")
    _trace_event("edit_to_new_transition_completed", url=_safe_page_url(page))


def certify_new_dco_local_gate(browser) -> None:
    """Run NEW certification in a fresh browser context independent of EDIT."""
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(30_000)
    page.set_default_navigation_timeout(30_000)
    attach_browser_diagnostics(page)
    try:
        login_to_desk(page, "Administrator", "admin")
        certify_actual_frappe_desk_new_recovery(page)
    finally:
        context.close()


def certify_new_dco_recovery_stress(browser, piece_count: int) -> None:
    """Run the independent 200/500-piece Stress/Performance path through Desk UI."""
    if piece_count not in {200, 500}:
        raise ValueError("NEW recovery stress piece count must be 200 or 500.")
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(30_000)
    page.set_default_navigation_timeout(30_000)
    attach_browser_diagnostics(page)
    try:
        login_to_desk(page, "Administrator", "admin")
        certify_actual_frappe_desk_new_recovery(page, piece_count=piece_count)
    finally:
        context.close()


def certify_actual_frappe_desk_edit_recovery(page: Page) -> None:
    _trace_event("certification_started")
    login_to_desk(page, "Administrator", "admin")


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
    page.wait_for_timeout(1100)
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
    certify_edit_to_new_transition(page)
    browser = page.context.browser
    if browser is None:
        raise RuntimeError("NEW Local Gate requires a browser after the EDIT→NEW transition.")
    certify_new_dco_local_gate(browser)


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
            comparison_case = os.environ.get("DCO_DESK_COMPARISON_CASE")
            if comparison_case:
                certify_phase_a_comparison_case(browser, page, comparison_case)
            elif os.environ.get("DCO_DESK_NEW_FORM_SMOKE_ONLY") == "1":
                certify_new_dco_form_smoke(page)
            elif os.environ.get("DCO_DESK_NEW_CUSTOMER_FIELD_SMOKE_ONLY") == "1":
                certify_new_dco_form_smoke(page)
                certify_new_customer_field_smoke(page)
            elif os.environ.get("DCO_DESK_NEW_STRESS_ONLY") == "1":
                stress_piece_count = int(os.environ.get("DCO_DESK_NEW_STRESS_PIECE_COUNT", "200"))
                certify_new_dco_recovery_stress(browser, stress_piece_count)
            elif os.environ.get("DCO_DESK_NEW_LOCAL_GATE_ONLY") == "1":
                certify_new_dco_local_gate(browser)
            else:
                certify_actual_frappe_desk_edit_recovery(page)
        except BaseException as failure:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            screenshot = evidence_dir / "dco-desk-failure.png"
            trace = evidence_dir / "dco-desk-trace.json"
            failure_text = _redact_text(str(failure))
            _trace_event(
                "certification_failed",
                error=failure_text,
                step=ACTIVE_STEP or LAST_FAILED_STEP,
            )
            trace.write_text(json.dumps(BROWSER_TRACE, ensure_ascii=False, indent=2), encoding="utf-8")
            diagnostic_path = evidence_dir / "browser-diagnostics.json"
            diagnostic_path.write_text(json.dumps({
                "state": {"failure": failure_text}, **DIAGNOSTIC_EVENTS,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            # A renderer timeout can leave the page unresponsive without a
            # close/crash event. Do not issue another Playwright command here.
            _trace_event("screenshot_skipped_after_failure", step=ACTIVE_STEP or LAST_FAILED_STEP)
            diagnostic_page = LAST_ACTIVE_PAGE or page
            state = read_page_state(diagnostic_page)
            state["url"] = _safe_url(state.get("url", ""))
            if os.environ.get("DCO_DESK_COMPARISON_CASE"):
                state.pop("bodyText", None)
            else:
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
