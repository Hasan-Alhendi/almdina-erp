from __future__ import annotations

import faulthandler
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
    sync_playwright,
)
from tests.browser.al129_link_search_request import (
    decode_search_link_request_args,
    normalize_search_link_args,
    search_link_argument_differences,
)


DESK_URL = os.environ.get("FRAPPE_DESK_URL", "").rstrip("/")
FIXTURE_PATH = os.environ.get("DCO_AL129_FIXTURE_FILE", "")
RUNNER_TEMP = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
EVIDENCE_PATH = RUNNER_TEMP / "al129-new-desk-evidence.json"
TRACE_PATH = RUNNER_TEMP / "al129-new-desk-trace.json"
TRACE: list[dict[str, Any]] = []
PAGE_RUNTIME_DIAGNOSTICS: dict[int, list[dict[str, str]]] = {}
NEW_FORM_IDENTITIES: dict[int, dict[str, Any]] = {}
DIAGNOSTIC_REDACTIONS: set[str] = set()
STEP_SUMMARY_EVENTS = {
    "permission_smoke_watchdog_armed",
    "browser_launch_started",
    "browser_launch_completed",
    "browser_cdp_launch_failed",
    "browser_cdp_loopback_verified",
    "browser_context_create_started",
    "browser_context_create_completed",
    "browser_page_create_started",
    "browser_page_create_completed",
    "login_navigation_started",
    "login_navigation_completed",
    "login_existing_session_check_started",
    "login_existing_session_check_completed",
    "login_form_fill_started",
    "login_form_fill_completed",
    "login_submit_started",
    "login_submit_completed",
    "login_session_wait_started",
    "login_session_ready",
    "login_boot_wait_started",
    "login_boot_ready",
    "desk_login_and_boot_ready",
    "new_form_navigation_started",
    "new_form_navigation_response",
    "new_form_navigation_commit_failed",
    "new_form_domcontentloaded_wait_started",
    "new_form_domcontentloaded_completed",
    "new_form_domcontentloaded_failed",
    "new_form_cur_frm_wait_started",
    "new_form_cur_frm_ready",
    "new_form_cur_frm_wait_failed",
    "new_form_checkpoint_snapshot_wait_started",
    "new_form_checkpoint_snapshot_wait_completed",
    "new_form_checkpoint_snapshot_wait_failed",
    "new_form_fast_table_visibility_wait_started",
    "new_form_fast_table_visibility_wait_completed",
    "new_form_fast_table_visibility_wait_failed",
    "new_form_model_state_read_started",
    "new_form_model_state_read_completed",
    "new_form_model_state_read_failed",
}


def trace(event: str, **details: Any) -> None:
    record = {"time": round(time.time(), 3), "event": event, **details}
    TRACE.append(record)
    if len(TRACE) > 1600:
        del TRACE[:-1600]
    RUNNER_TEMP.mkdir(parents=True, exist_ok=True)
    TRACE_PATH.write_text(json.dumps(TRACE, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if event in STEP_SUMMARY_EVENTS:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            # Keep live progress useful if the outer process deadline stops pytest.
            # Only emit fixed phase names and durations; never emit credentials or identities.
            safe_details = {
                key: record[key]
                for key in (
                    "duration_ms",
                    "timeout_seconds",
                    "stack_dump_after_seconds",
                    "status",
                    "error_type",
                )
                if key in record
            }
            with Path(summary_path).open("a", encoding="utf-8") as summary:
                summary.write(f"- `{event}` {json.dumps(safe_details, sort_keys=True)}\n")


def _fixtures() -> dict[str, Any]:
    if not DESK_URL or not FIXTURE_PATH:
        pytest.fail("Pinned Frappe Desk URL and isolated AL129 fixture are required.")
    fixture = json.loads(Path(FIXTURE_PATH).read_text(encoding="utf-8"))
    DIAGNOSTIC_REDACTIONS.update(
        str(fixture[key])
        for key in ("password", "customer", "user", "second_user", "write_user", "no_create_user")
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
    started = time.monotonic()
    trace("browser_launch_started")
    browser = playwright_instance.chromium.launch(
        headless=True,
        executable_path=executable,
        args=args,
        timeout=30_000,
    )
    trace("browser_launch_completed", duration_ms=round((time.monotonic() - started) * 1000))
    return browser


def _loopback_cdp_browser(
    playwright_instance,
) -> tuple[Browser, BrowserContext, Path, int, subprocess.Popen]:
    executable = (
        os.environ.get("CHROMIUM_PATH")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or playwright_instance.chromium.executable_path
    )
    profile = Path(tempfile.mkdtemp(prefix="al129-cdp-profile-"))
    browser_process = None
    browser = None
    stderr_path = profile / "chromium-stderr.log"
    try:
        started = time.monotonic()
        trace("browser_launch_started")
        arguments = [
            executable,
            "--no-sandbox",
            "--headless=new",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            "about:blank",
        ]
        with stderr_path.open("ab") as stderr_output:
            browser_process = subprocess.Popen(
                arguments,
                stdout=subprocess.DEVNULL,
                stderr=stderr_output,
            )
        active_port = profile / "DevToolsActivePort"
        deadline = time.monotonic() + 30
        endpoint = None
        port = None
        while time.monotonic() < deadline:
            if browser_process.poll() is not None:
                raise RuntimeError("Chromium exited before publishing its CDP endpoint.")
            try:
                values = active_port.read_text(encoding="utf-8").splitlines()
                if values and values[0].isdigit():
                    port = int(values[0])
                    with urlopen(
                        f"http://127.0.0.1:{port}/json/version",
                        timeout=1.0,
                    ) as response:
                        endpoint = json.loads(response.read())
                    break
            except (OSError, ValueError, json.JSONDecodeError):
                time.sleep(0.1)
        if endpoint is None or port is None:
            stderr_tail = "\n".join(
                stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]
            )
            raise TimeoutError(
                "Chromium did not publish a responsive CDP endpoint in 30 seconds. "
                f"Chromium stderr: {stderr_tail or '[empty]'}"
            )
        websocket_url = endpoint.get("webSocketDebuggerUrl", "")
        if not websocket_url.startswith("ws://127.0.0.1:"):
            raise RuntimeError("Chromium CDP endpoint was not loopback-only.")
        browser = playwright_instance.chromium.connect_over_cdp(
            f"http://127.0.0.1:{port}",
            timeout=10_000,
        )
        if not browser.contexts:
            raise RuntimeError("Chromium did not expose its isolated browser context.")
        context = browser.contexts[0]
        trace(
            "browser_cdp_loopback_verified",
            browser_product=str(endpoint.get("Browser", ""))[:48],
        )
        trace(
            "browser_launch_completed",
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return browser, context, profile, port, browser_process
    except Exception as error:
        trace("browser_cdp_launch_failed", error_type=type(error).__name__)
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        finally:
            if browser_process is not None and browser_process.poll() is None:
                browser_process.terminate()
                try:
                    browser_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    browser_process.kill()
                    browser_process.wait(timeout=5)
            shutil.rmtree(profile, ignore_errors=True)
        raise


@contextmanager
def _cdp_browser_session():
    with sync_playwright() as playwright_instance:
        browser, _context, profile, port, browser_process = _loopback_cdp_browser(
            playwright_instance
        )
        try:
            yield browser, port
        finally:
            try:
                browser.close()
            finally:
                if browser_process.poll() is None:
                    browser_process.terminate()
                    try:
                        browser_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        browser_process.kill()
                        browser_process.wait(timeout=5)
                shutil.rmtree(profile, ignore_errors=True)


def _start_independent_cdp_monitor(port: int) -> tuple[subprocess.Popen, Path]:
    host = urlsplit(DESK_URL).hostname
    if not host:
        raise RuntimeError("Desk host is required to scope the CDP monitor target.")
    stop_file = RUNNER_TEMP / "al129-cdp-monitor.stop"
    evidence_file = RUNNER_TEMP / "al129-cdp-monitor.jsonl"
    stop_file.unlink(missing_ok=True)
    evidence_file.unlink(missing_ok=True)
    monitor = Path(__file__).with_name("al129_cdp_monitor.py")
    command = [
        "timeout",
        "--signal=TERM",
        "--kill-after=3s",
        "55s",
        sys.executable,
        "-u",
        str(monitor),
        "--port",
        str(port),
        "--target-host",
        host,
        "--interval",
        "0.35",
        "--duration",
        "50",
        "--stop-file",
        str(stop_file),
        "--evidence-file",
        str(evidence_file),
    ]
    process = subprocess.Popen(command, stdout=None, stderr=subprocess.STDOUT)
    trace("independent_cdp_monitor_started", duration_limit_seconds=55)
    return process, stop_file


def _stop_independent_cdp_monitor(monitor: tuple[subprocess.Popen, Path] | None) -> None:
    if monitor is None:
        return
    process, stop_file = monitor
    stop_file.touch()
    try:
        exit_code = process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            exit_code = process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait(timeout=3)
    trace("independent_cdp_monitor_finished", exit_code=exit_code)


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
    page.set_default_timeout(15_000)
    page.set_default_navigation_timeout(45_000)
    started = time.monotonic()
    trace("login_navigation_started")
    response = page.goto(f"{DESK_URL}/login", wait_until="domcontentloaded", timeout=45_000)
    trace(
        "login_navigation_completed",
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    assert response is not None and response.status == 200

    session_probe_started = time.monotonic()
    trace("login_existing_session_check_started")
    try:
        page.wait_for_function(
            "user => window.frappe && frappe.session && frappe.session.user === user",
            arg=expected_user,
            timeout=1_000,
        )
    except PlaywrightTimeoutError:
        trace(
            "login_existing_session_check_completed",
            duration_ms=round((time.monotonic() - session_probe_started) * 1000),
        )
    else:
        trace(
            "login_existing_session_check_completed",
            duration_ms=round((time.monotonic() - session_probe_started) * 1000),
        )
        boot_started = time.monotonic()
        trace("login_boot_wait_started")
        page.wait_for_function(
            "() => window.frappe && frappe.boot && frappe.boot.sysdefaults "
            "&& Boolean(frappe.boot.sysdefaults.setup_complete) && frappe.router && frappe.app",
            timeout=45_000,
        )
        trace("login_boot_ready", duration_ms=round((time.monotonic() - boot_started) * 1000))
        trace("desk_login_and_boot_ready")
        return

    fill_started = time.monotonic()
    trace("login_form_fill_started")
    page.locator("#login_email").fill(expected_user)
    page.locator("#login_password").fill(fixture["password"])
    trace("login_form_fill_completed", duration_ms=round((time.monotonic() - fill_started) * 1000))
    submit_started = time.monotonic()
    trace("login_submit_started")
    page.get_by_role("button", name=re.compile(r"^(Login|Continue)$")).click()
    trace("login_submit_completed", duration_ms=round((time.monotonic() - submit_started) * 1000))
    session_started = time.monotonic()
    trace("login_session_wait_started")
    page.wait_for_function(
        "user => window.frappe && frappe.session && frappe.session.user === user",
        arg=expected_user,
        timeout=45_000,
    )
    trace("login_session_ready", duration_ms=round((time.monotonic() - session_started) * 1000))
    boot_started = time.monotonic()
    trace("login_boot_wait_started")
    page.wait_for_function(
        "() => window.frappe && frappe.boot && frappe.boot.sysdefaults "
        "&& Boolean(frappe.boot.sysdefaults.setup_complete) && frappe.router && frappe.app",
        timeout=45_000,
    )
    trace("login_boot_ready", duration_ms=round((time.monotonic() - boot_started) * 1000))
    trace("desk_login_and_boot_ready")


def _new_traced_desk_page(browser: Browser, case_name: str):
    started = time.monotonic()
    trace("browser_context_create_started", case=case_name)
    context = browser.new_context(viewport={"width": 1800, "height": 1200})
    trace(
        "browser_context_create_completed",
        case=case_name,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    started = time.monotonic()
    trace("browser_page_create_started", case=case_name)
    page = context.new_page()
    trace(
        "browser_page_create_completed",
        case=case_name,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    _attach_diagnostics(page)
    return context, page


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
    target_url = f"{DESK_URL}/app/door-cutting-order/new-door-cutting-order-al129-{suffix}"
    navigation_started = time.monotonic()
    trace("new_form_navigation_started", timeout_seconds=20)
    try:
        # Commit isolates server/navigation response from Frappe's JavaScript boot.
        # DOMContentLoaded and app readiness remain explicit acceptance conditions below.
        response = page.goto(target_url, wait_until="commit", timeout=20_000)
    except Exception as error:
        trace(
            "new_form_navigation_commit_failed",
            duration_ms=round((time.monotonic() - navigation_started) * 1000),
            error_type=type(error).__name__,
        )
        raise
    trace(
        "new_form_navigation_response",
        status=response.status if response else None,
        duration_ms=round((time.monotonic() - navigation_started) * 1000),
    )

    domcontentloaded_started = time.monotonic()
    trace("new_form_domcontentloaded_wait_started", timeout_seconds=20)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
    except Exception as error:
        trace(
            "new_form_domcontentloaded_failed",
            duration_ms=round((time.monotonic() - domcontentloaded_started) * 1000),
            error_type=type(error).__name__,
        )
        raise
    trace(
        "new_form_domcontentloaded_completed",
        duration_ms=round((time.monotonic() - domcontentloaded_started) * 1000),
    )

    cur_frm_started = time.monotonic()
    trace("new_form_cur_frm_wait_started", timeout_seconds=30)
    try:
        page.wait_for_function(
            "() => window.cur_frm && cur_frm.doctype === 'Door Cutting Order' "
            "&& cur_frm.is_new() && cur_frm.fields_dict.pieces_fast_entry "
            "&& cur_frm.fields_dict.pieces_fast_entry.$wrapper",
            timeout=30_000,
        )
    except Exception as error:
        trace(
            "new_form_cur_frm_wait_failed",
            duration_ms=round((time.monotonic() - cur_frm_started) * 1000),
            error_type=type(error).__name__,
        )
        raise
    trace(
        "new_form_cur_frm_ready",
        duration_ms=round((time.monotonic() - cur_frm_started) * 1000),
        expected_state=expected_state,
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

    checkpoint_started = time.monotonic()
    trace("new_form_checkpoint_snapshot_wait_started", timeout_seconds=30)
    try:
        page.wait_for_function(
            "() => window.AlmdinaDcoRecovery && AlmdinaDcoRecovery.LocalCheckpoint "
            "&& AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm)",
            timeout=30_000,
        )
    except Exception as error:
        trace(
            "new_form_checkpoint_snapshot_wait_failed",
            duration_ms=round((time.monotonic() - checkpoint_started) * 1000),
            error_type=type(error).__name__,
        )
        raise
    trace(
        "new_form_checkpoint_snapshot_wait_completed",
        duration_ms=round((time.monotonic() - checkpoint_started) * 1000),
    )

    fast_table_started = time.monotonic()
    trace("new_form_fast_table_visibility_wait_started", timeout_seconds=30)
    try:
        fast_table = page.locator(
            "[data-fieldname='pieces_fast_entry'] .dco-fast-table"
        )
        expect(fast_table).to_be_visible(timeout=30_000)
    except Exception as error:
        trace(
            "new_form_fast_table_visibility_wait_failed",
            duration_ms=round((time.monotonic() - fast_table_started) * 1000),
            error_type=type(error).__name__,
        )
        raise
    trace(
        "new_form_fast_table_visibility_wait_completed",
        duration_ms=round((time.monotonic() - fast_table_started) * 1000),
    )

    model_state_started = time.monotonic()
    trace("new_form_model_state_read_started")
    try:
        state = page.evaluate(
            "() => ({name: cur_frm.doc.name, doctype: cur_frm.doctype,"
            " isNew: Boolean(cur_frm.is_new()),"
            " checkpoint: Boolean(AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm)),"
            " discoveryVisible: Boolean(document.querySelector("
            "'.modal.show [data-recovery-action=\"continue\"]'))})"
        )
    except Exception as error:
        trace(
            "new_form_model_state_read_failed",
            duration_ms=round((time.monotonic() - model_state_started) * 1000),
            error_type=type(error).__name__,
        )
        raise
    trace(
        "new_form_model_state_read_completed",
        duration_ms=round((time.monotonic() - model_state_started) * 1000),
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
    control = page.locator(f"[data-fieldname='{fieldname}'] input").first
    expect(control).to_be_visible(timeout=5_000)
    expect(control).to_be_enabled(timeout=5_000)
    link_state = control.evaluate(
        "(input, {fieldname, value}) => { const frm = window.cur_frm;"
        " const field = frm && frm.fields_dict[fieldname];"
        " const control = field && field.$input;"
        " const current = control && typeof control.get === 'function' ? control.get(0) : control;"
        " const fetchColumns = field && field.fetch_map ? Object.values(field.fetch_map) : [];"
        " const modelValue = frm && frm.doc ? frm.doc[fieldname] : undefined;"
        " const skipsValidation = Boolean(field && (field._validated || field.df.ignore_link_validation"
        " || field.df.options === '[Select]'));"
        " const unchanged = modelValue === value;"
        " const sameDefaultWithoutFetch = fetchColumns.length === 0 && field.df.__default_value === value;"
        " const probe = {events: [], before: {modelValue, inputValue: input.value,"
        " focused: document.activeElement === input, lastValue: field && field.last_value,"
        " validated: field && field._validated}, validationResponses: []};"
        " window.__al129LinkProbe = probe;"
        " for (const eventName of ['focus', 'input', 'change', 'blur']) input.addEventListener(eventName, event =>"
        " probe.events.push({event: event.type, inputValue: input.value,"
        " modelValue: frm.doc[fieldname], focused: document.activeElement === input,"
        " lastValue: field.last_value, validated: field._validated}));"
        " return {native: Boolean(field && field.df && field.df.fieldtype === 'Link' && current === input),"
        " unchanged, skipsValidation, sameDefaultWithoutFetch,"
        " validationRequestExpected: Boolean(value && !unchanged && !skipsValidation"
        " && !sameDefaultWithoutFetch), fetchColumnCount: fetchColumns.length,"
        " before: probe.before}; }",
        {"fieldname": fieldname, "value": value},
    )
    if not link_state["native"]:
        raise AssertionError(f"Resolved {fieldname} input is not Frappe's current Link control")
    if link_state["skipsValidation"] and not link_state["unchanged"]:
        raise AssertionError(f"Frappe Link validation is disabled for changed {fieldname} input")

    responses = []

    def capture_validation(response: Any) -> None:
        if "frappe.client.validate_link_and_fetch" in response.url:
            responses.append({"status": response.status, "ok": response.ok})

    page.on("response", capture_validation)
    control.fill(value)
    after_fill = page.evaluate(
        "({fieldname}) => { const field = cur_frm.fields_dict[fieldname];"
        " const input = field.$input.get(0); return {inputValue: input.value,"
        " modelValue: cur_frm.doc[fieldname], focused: document.activeElement === input,"
        " lastValue: field.last_value, validated: field._validated}; }",
        {"fieldname": fieldname},
    )
    # Frappe's native Awesomplete selection is the authoritative keyboard
    # path for edge-type Link values. Blur-only entry can leave the field
    # model unchanged when the option was not selected.
    selected_native_option = fieldname == "default_edge_type" and not link_state["unchanged"]
    if selected_native_option:
        option = page.locator(
            f"[data-fieldname='{fieldname}'] [role='option']"
        ).filter(has_text=value).first
        expect(option).to_be_visible(timeout=10_000)
        option.click()
    else:
        control.press("Tab")
    if link_state["before"]["modelValue"] != value:
        page.wait_for_function(
            "({fieldname, value}) => window.cur_frm && cur_frm.doc[fieldname] === value",
            arg={"fieldname": fieldname, "value": value},
            timeout=10_000,
        )
    interaction = page.evaluate(
        "({fieldname}) => { const field = cur_frm.fields_dict[fieldname];"
        " return {modelValue: cur_frm.doc[fieldname], inputValue: field.$input.val(),"
        " focused: document.activeElement === field.$input.get(0), lastValue: field.last_value,"
        " validated: field._validated, events: [...window.__al129LinkProbe.events]}; }",
        {"fieldname": fieldname},
    )
    after_matches = interaction["modelValue"] == value
    if not after_matches:
        raise AssertionError(
            f"Native Link interaction did not set {fieldname} in cur_frm.doc: "
            f"before={link_state['before']!r}, after_fill={after_fill!r}, interaction={interaction!r}"
        )
    skip_reason_proven = bool(
        link_state["unchanged"]
        or link_state["skipsValidation"]
        or link_state["sameDefaultWithoutFetch"]
    )
    # Selecting a result supplied by Frappe's native search is also a
    # validated Link choice; ControlLink need not revalidate that cached row.
    if link_state["validationRequestExpected"] and not responses and not skip_reason_proven and not selected_native_option:
        raise AssertionError(
            f"Changed native Link value reached the model without observable Link validation: "
            f"field={fieldname!r}, before={link_state['before']!r}, after_fill={after_fill!r}, "
            f"interaction={interaction!r}"
        )
    if any(not response["ok"] for response in responses):
        raise AssertionError(f"Frappe rejected native {fieldname} Link validation: {responses!r}")
    page.evaluate("() => { delete window.__al129LinkProbe; }")
    trace(
        "native_link_interaction_completed",
        fieldname=fieldname,
        before=link_state["before"],
        after_fill=after_fill,
        interaction=interaction,
        model_value_unchanged_before_entry=link_state["unchanged"],
        native_validation_skipped_by_frappe=link_state["skipsValidation"],
        unchanged_default_without_fetch=link_state["sameDefaultWithoutFetch"],
        validation_request_expected=link_state["validationRequestExpected"],
        validation_responses=responses,
        selected_native_option=selected_native_option,
        model_value_matches_after_entry=after_matches,
    )


def _search_link_response_for_term(response: Any, term: str) -> bool:
    if "frappe.desk.search.search_link" not in response.url:
        return False
    try:
        args = decode_search_link_request_args(response.request.url, response.request.post_data)
    except (TypeError, ValueError):
        return False
    return args.get("txt") == term


def _search_link_term(response: Any) -> str | None:
    try:
        return decode_search_link_request_args(
            response.request.url, response.request.post_data
        ).get("txt")
    except (TypeError, ValueError):
        return None


def _safe_search_argument_differences(
    differences: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    def redact(value: Any) -> Any:
        if isinstance(value, str):
            return _safe_diagnostic_text(value, limit=500)
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        return value

    return {key: redact(value) for key, value in differences.items()}


def _customer_permission_state(page: Page) -> dict[str, Any]:
    return page.evaluate(
        "() => {"
        " const frm = window.cur_frm;"
        " const field = frm && frm.fields_dict && frm.fields_dict.customer;"
        " const level = Number(field && field.df && field.df.permlevel || 0);"
        " const permission = frm && frm.perm && field ? frm.perm[level] : null;"
        " const fieldPermission = field && Array.isArray(field.perm)"
        " ? field.perm[level] : permission;"
        " const doctypeCache = frappe.perm && frappe.perm.doctype_perm"
        " ? frappe.perm.doctype_perm['Door Cutting Order'] : null;"
        " const nativePermission = doctypeCache && doctypeCache[level] || null;"
        " const projection = frm && frm.__almdina_new_create_field_projection;"
        " const permissionFlags = rows => Array.isArray(rows) ? rows.map(row => row ? {"
        " read: Boolean(row.read), write: Boolean(row.write), create: Boolean(row.create)} : null) : null;"
        " const unwrap = value => value && typeof value.get === 'function'"
        " ? value.get(0) : (value && value[0]) || value || null;"
        " const wrapper = unwrap(field && field.$wrapper);"
        " const input = unwrap(field && field.$input);"
        " const originalColumn = wrapper && wrapper.closest('.form-column');"
        " const pairRow = wrapper && wrapper.closest('.dco-intake-row--pair');"
        " const intakeCard = wrapper && wrapper.closest('.dco-order-intake-card');"
        " const visible = node => { if (!node || !node.isConnected) return false;"
        " const style = getComputedStyle(node); return node.getClientRects().length > 0"
        " && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'; };"
        " const wrapperPath = []; let node = wrapper;"
        " for (let index = 0; node && index < 7; index++, node = node.parentElement) {"
        " const style = getComputedStyle(node); wrapperPath.push({tag: node.tagName,"
        " classes: String(node.className || '').slice(0, 180), visible: visible(node),"
        " display: style.display, visibility: style.visibility}); }"
        " const guardedFields = {};"
        " for (const name of ['status', 'total_cost_usd', 'board_item', 'recovery_creation_token']) {"
        " const guarded = frm.fields_dict && frm.fields_dict[name]; if (!guarded) continue;"
        " let status = null; try { status = guarded.get_status(); } catch (_error) {}"
        " guardedFields[name] = {hidden: Boolean(guarded.df && guarded.df.hidden),"
        " readOnly: Boolean(guarded.read_only || (guarded.df && guarded.df.read_only)),"
        " permlevel: Number(guarded.df && guarded.df.permlevel || 0), status}; }"
        " const route = window.frappe && typeof frappe.get_route === 'function' ? frappe.get_route() : null;"
        " const activeTab = [...document.querySelectorAll('.nav-link.active, .tab-pane.active')]"
        " .map(item => ({kind: item.matches('.tab-pane') ? 'pane' : 'tab',"
        " label: (item.getAttribute('aria-label') || item.textContent || '').trim().slice(0, 60),"
        " visible: visible(item)}));"
        " let fieldPermissionStatus = null; let fieldPermissionError = null;"
        " let nativeFieldPermissionStatus = null; let nativeFieldPermissionError = null;"
        " let controlStatus = null; let controlStatusError = null;"
        " try { fieldPermissionStatus = frappe.perm.get_field_display_status(field.df, frm.doc, frm.perm); }"
        " catch (error) { fieldPermissionError = String(error).slice(0, 160); }"
        " try { nativeFieldPermissionStatus = frappe.perm.get_field_display_status(field.df, frm.doc, doctypeCache); }"
        " catch (error) { nativeFieldPermissionError = String(error).slice(0, 160); }"
        " try { controlStatus = field.get_status(); }"
        " catch (error) { controlStatusError = String(error).slice(0, 160); }"
        " return {doctype: frm && frm.doctype || null, documentName: frm && frm.doc && frm.doc.name || null,"
        " isNew: Boolean(frm && frm.is_new()), route: Array.isArray(route) ? route.join('/') : null,"
        " activeTab, permission: permission ? {read: Boolean(permission.read), write: Boolean(permission.write),"
        " create: Boolean(permission.create)} : null, fieldPermissionStatus, fieldPermissionError,"
        " nativePermission: nativePermission ? {read: Boolean(nativePermission.read),"
        " write: Boolean(nativePermission.write), create: Boolean(nativePermission.create)} : null,"
        " nativePermissionRows: permissionFlags(doctypeCache), formPermissionRows: permissionFlags(frm && frm.perm),"
        " nativeFieldPermissionStatus, nativeFieldPermissionError,"
        " fieldPermission: fieldPermission ? {read: Boolean(fieldPermission.read),"
        " write: Boolean(fieldPermission.write), create: Boolean(fieldPermission.create)} : null,"
        " doctypeCacheWrite: Boolean(doctypeCache && doctypeCache[0] && doctypeCache[0].write),"
        " formCanCreate: Boolean(frm && frm.has_perm && frm.has_perm('create')),"
        " formCanWrite: Boolean(frm && frm.has_perm && frm.has_perm('write')),"
        " createProjectionActive: Boolean(projection),"
        " projectionPermissionLevels: projection ? projection.permissionLevels : [],"
        " controlStatus, controlStatusError, dispStatus: field && field.disp_status || null,"
        " fieldType: field && field.df && field.df.fieldtype || null,"
        " hidden: field && field.df ? Boolean(field.df.hidden) : null,"
        " hiddenDueToDependency: field && field.df ? Boolean(field.df.hidden_due_to_dependency) : null,"
        " readOnly: field ? Boolean(field.read_only || field.df.read_only) : null,"
        " permlevel: field && field.df ? field.df.permlevel : null,"
        " hideEmptyReadOnlyFields: frappe.boot && frappe.boot.sysdefaults"
        " ? frappe.boot.sysdefaults.hide_empty_read_only_fields : null,"
        " guardedFields,"
        " wrapperConnected: Boolean(wrapper && wrapper.isConnected), wrapperVisible: visible(wrapper),"
        " hideControl: Boolean(wrapper && wrapper.classList.contains('hide-control')), wrapperPath,"
        " insideIntakePair: Boolean(pairRow), insideIntakeCard: Boolean(intakeCard),"
        " hasOriginalFormColumnAncestor: Boolean(originalColumn),"
        " originalFormColumnDisplay: originalColumn ? getComputedStyle(originalColumn).display : null,"
        " inputExists: Boolean(input), inputConnected: Boolean(input && input.isConnected),"
        " inputVisible: visible(input), inputDisabled: input ? Boolean(input.disabled) : null}; }"
    )


def _capture_failure_screenshot(page: Page, event: str, error: Exception) -> None:
    trace(event, message=_safe_diagnostic_text(str(error), limit=900))
    try:
        page.screenshot(
            path=str(RUNNER_TEMP / "al129-desk-failure.png"),
            full_page=False,
            timeout=3_000,
        )
    except Exception as screenshot_error:
        trace(
            "failure_screenshot_unavailable",
            message=_safe_diagnostic_text(str(screenshot_error), limit=300),
        )


def _save_new_document(page: Page) -> str:
    button = page.locator(".page-actions .primary-action").first
    expect(button).to_be_visible(timeout=15_000)
    expect(button).to_be_enabled(timeout=15_000)
    assert re.search(r"Save|حفظ", button.inner_text(), re.I)
    button.click()
    page.wait_for_function(
        "() => window.cur_frm && cur_frm.doctype === 'Door Cutting Order'"
        " && !cur_frm.is_new() && Boolean(cur_frm.doc.name)",
        timeout=45_000,
    )
    return str(page.evaluate("() => cur_frm.doc.name"))


def test_real_desk_customer_control_link_autocomplete_isolated() -> None:
    """Observe native ControlLink search separately for create-only and create+edit."""
    fixture = _fixtures()
    outcomes: dict[str, dict[str, Any]] = {}
    with _cdp_browser_session() as (browser, _cdp_port):
        for case_name, user in (
            ("create_only", fixture["user"]),
            ("create_and_edit", fixture["write_user"]),
        ):
            context, page = _new_traced_desk_page(browser, f"autocomplete-{case_name}")
            try:
                _login(page, fixture, user=user)
                _open_new_form(
                    page,
                    f"customer-autocomplete-{case_name}",
                    expected_state="ready_for_entry",
                )
                state = _customer_permission_state(page)
                assert state["isNew"] is True and state["doctype"] == "Door Cutting Order"
                # Leave the native Link unfocused so fill() reproduces the
                # real Frappe focus-then-type sequence in this probe.
                page.locator("[data-fieldname='board_description'] input").click()
                control = page.locator("[data-fieldname='customer'] input").first
                expect(control).to_be_visible(timeout=5_000)
                control.evaluate(
                    "input => { const field = cur_frm.fields_dict.customer;"
                    " window.__al129ControlProbe = {form: cur_frm, field, input, awesomplete: field.awesomplete,"
                    " focusEvents: []};"
                    " input.addEventListener('focus', () => window.__al129ControlProbe.focusEvents.push('focus'));"
                    " input.addEventListener('blur', () => window.__al129ControlProbe.focusEvents.push('blur')); }"
                )
                page_errors: list[str] = []
                page.on("pageerror", lambda error: page_errors.append(_safe_diagnostic_text(str(error))))
                empty_search_responses: list[Any] = []
                search_response_order: list[dict[str, Any]] = []
                page.on(
                    "response",
                    lambda response: (
                        search_response_order.append({
                            "term": _search_link_term(response),
                            "status": response.status,
                        }),
                        empty_search_responses.append(response)
                        if _search_link_term(response) == ""
                        else None,
                    ) if "frappe.desk.search.search_link" in response.url else None,
                )
                expected_search_args = normalize_search_link_args(
                    control.evaluate(
                        "(input, term) => cur_frm.fields_dict.customer.get_search_args(term)",
                        fixture["customer"],
                    )
                )
                try:
                    with page.expect_response(
                        lambda response: _search_link_response_for_term(
                            response, fixture["customer"]
                        ),
                        timeout=15_000,
                    ) as search_response:
                        control.fill(fixture["customer"])
                    response = search_response.value
                    response_body = response.json()
                    results = response_body.get("message", []) if isinstance(response_body, dict) else []
                    exact_response_count = sum(
                        1 for item in results
                        if isinstance(item, dict) and item.get("value") == fixture["customer"]
                    )
                    request = response.request
                    request_args = decode_search_link_request_args(
                        request.url, request.post_data
                    )
                    argument_differences = search_link_argument_differences(
                        expected_search_args, request_args
                    )
                    request_valid = bool(
                        isinstance(request_args, dict)
                        and request_args.get("doctype") == "Customer"
                        and request_args.get("reference_doctype") == "Door Cutting Order"
                        and request_args.get("link_fieldname") == "customer"
                        and request_args.get("txt") == fixture["customer"]
                    )
                    native_args_match = not argument_differences
                    try:
                        page.wait_for_function(
                            "value => { const field = cur_frm && cur_frm.fields_dict.customer;"
                            " const cache = field && field.$input.cache && field.$input.cache.Customer;"
                            " const typed = cache && cache[value];"
                            " return Boolean(cache && Object.prototype.hasOwnProperty.call(cache, '')"
                            " && Array.isArray(typed) && typed.some(item => item && item.value === value)); }",
                            arg=fixture["customer"],
                            timeout=3_000,
                        )
                    except PlaywrightTimeoutError:
                        pass
                    ui_state = page.evaluate(
                        "expectedValue => { const before = window.__al129ControlProbe;"
                        " const field = cur_frm && cur_frm.fields_dict.customer;"
                        " const input = field && field.$input && typeof field.$input.get === 'function'"
                        " ? field.$input.get(0) : field && field.$input;"
                        " const list = field && field.awesomplete && field.awesomplete.list;"
                        " const values = Array.isArray(list) ? list : [];"
                        " const options = field && field.awesomplete && field.awesomplete.ul"
                        " ? field.awesomplete.ul.querySelectorAll('[role=option]') : [];"
                        " const cache = field && field.$input && field.$input.cache"
                        " && field.$input.cache.Customer || {};"
                        " const cachedTyped = Array.isArray(cache[expectedValue]) ? cache[expectedValue] : [];"
                        " const cachedEmpty = Array.isArray(cache['']) ? cache[''] : [];"
                        " const currentArgs = field && field.get_search_args(expectedValue);"
                        " const exactItems = values.filter(item => item && String(item.value) === expectedValue);"
                        " const cachedExactItems = cachedTyped.filter(item => item && String(item.value) === expectedValue);"
                        " const renderText = value => { const node = document.createElement('span');"
                        " node.innerHTML = String(value || ''); return (node.textContent || '').trim(); };"
                        " const labels = exactItems.flatMap(item => [item.label, item.value, item.html])"
                        " .map(renderText).filter(Boolean);"
                        " const visibleOptions = [...options].filter(item => item.getClientRects().length > 0);"
                        " const dropdown = field && field.awesomplete && field.awesomplete.ul;"
                        " const dropdownStyle = dropdown ? getComputedStyle(dropdown) : null;"
                        " const exactOptionCount = visibleOptions.filter(option =>"
                        " (option.textContent || '').includes(expectedValue)).length;"
                        " return {formStable: Boolean(before && before.form === cur_frm),"
                        " fieldStable: Boolean(before && before.field === field),"
                        " inputStable: Boolean(before && before.input === input),"
                        " awesompleteStable: Boolean(before && before.awesomplete === (field && field.awesomplete)),"
                        " inputFocused: Boolean(input && document.activeElement === input),"
                        " focusEvents: before ? [...before.focusEvents] : [],"
                        " filterDescriptionRequired: Boolean(field &&"
                        " (field.df.filter_description || (currentArgs && currentArgs.filters))),"
                        " typedCachePresent: Object.prototype.hasOwnProperty.call(cache, expectedValue),"
                        " typedCacheExactValueCount: cachedExactItems.length,"
                        " emptyCacheExactValueCount: cachedEmpty.filter(item => item"
                        " && String(item.value) === expectedValue).length,"
                        " currentListIsTypedCache: values === cachedTyped,"
                        " currentListIsEmptyCache: values === cachedEmpty,"
                        " sourceListCount: values.length, sourceExactValueCount: exactItems.length,"
                        " exactVisibleOptionCount: exactOptionCount, optionCount: options.length,"
                        " dropdownVisible: Boolean(dropdown && dropdown.getClientRects().length"
                        " && dropdownStyle.display !== 'none' && dropdownStyle.visibility !== 'hidden'),"
                        " dropdownText: dropdown ? (dropdown.innerText || '').trim() : '',"
                        " dropdownClass: dropdown ? dropdown.className : null}; }",
                        fixture["customer"],
                    )
                    # Validate that the user can select the server-returned
                    # customer from the actual visible dropdown, not merely
                    # that the HTTP response or internal cache contained it.
                    assert ui_state["exactVisibleOptionCount"] == 1, ui_state
                    matching_option = page.locator(
                        "[data-fieldname='customer'] [role='option']"
                    ).filter(has_text=fixture["customer"]).first
                    expect(matching_option).to_be_visible(timeout=5_000)
                    matching_option.click()
                    page.wait_for_function(
                        "value => cur_frm && cur_frm.doc.customer === value",
                        arg=fixture["customer"],
                        timeout=10_000,
                    )
                    outcomes[case_name] = {
                        "nativeOptionSelected": True,
                        "selectedCustomerInModel": page.evaluate(
                            "() => cur_frm.doc.customer"
                        ) == fixture["customer"],
                        "searchResponseOk": response.ok,
                        "initialEmptySearchResponseCount": len(empty_search_responses),
                        "initialEmptySearchResponseOk": bool(empty_search_responses)
                        and all(response.ok for response in empty_search_responses),
                        "requestArgumentsValid": request_valid,
                        "nativeSearchArgumentsMatch": native_args_match,
                        "searchArgumentDifferences": _safe_search_argument_differences(
                            argument_differences
                        ),
                        "pageErrors": page_errors,
                        "searchResponseOrder": search_response_order,
                        "exactResponseCount": exact_response_count,
                        **ui_state,
                    }
                except PlaywrightTimeoutError:
                    outcomes[case_name] = {
                        "searchResponseOk": False,
                        "requestArgumentsValid": False,
                        "exactResponseCount": 0,
                        "controlFocused": bool(control.evaluate("input => document.activeElement === input")),
                    }
                finally:
                    page.evaluate("() => { delete window.__al129ControlProbe; }")
                trace("customer_control_link_probe", case_name=case_name, **outcomes[case_name])
            except Exception as error:
                _capture_failure_screenshot(page, f"customer_autocomplete_{case_name}_failed", error)
                raise
            finally:
                context.close()

    assert set(outcomes) == {"create_only", "create_and_edit"}
    assert all(item["searchResponseOk"] for item in outcomes.values()), outcomes
    assert all(item["initialEmptySearchResponseOk"] for item in outcomes.values()), outcomes
    assert all(item["initialEmptySearchResponseCount"] >= 1 for item in outcomes.values()), outcomes
    assert all(item["requestArgumentsValid"] for item in outcomes.values()), outcomes
    assert all(item["nativeSearchArgumentsMatch"] for item in outcomes.values()), outcomes
    assert all(not item["pageErrors"] for item in outcomes.values()), outcomes
    assert all(item["exactResponseCount"] == 1 for item in outcomes.values()), outcomes
    assert all(item["typedCachePresent"] and item["typedCacheExactValueCount"] == 1 for item in outcomes.values()), outcomes
    # In the pinned Awesomplete version the cached search results and
    # rendered DOM are populated even when awesomplete.list is empty.
    # Prove the visible option was actually selected instead.
    assert all(item["nativeOptionSelected"] and item["selectedCustomerInModel"] for item in outcomes.values()), outcomes
    assert all(item["exactVisibleOptionCount"] == 1 for item in outcomes.values()), outcomes
    assert all(item["focusEvents"] == ["focus"] for item in outcomes.values()), outcomes
    assert all(item["formStable"] and item["fieldStable"] and item["inputStable"] for item in outcomes.values()), outcomes
    assert all(item["awesompleteStable"] and item["inputFocused"] for item in outcomes.values()), outcomes
    assert all(item["optionCount"] > 0 for item in outcomes.values()), outcomes


def test_real_desk_customer_native_entry_and_permission_differential() -> None:
    """Certify create-only NEW input, persisted write denial, and no-create denial."""
    fixture = _fixtures()
    assert fixture["versions"] == {"frappe": "16.17.5", "erpnext": "16.17.0"}
    assert fixture["permission_differential"] == {
        "create_only": {"create": True, "read": True, "write": False},
        "create_and_edit": {"create": True, "read": True, "write": True},
        "no_create": {
            "create": False,
            "read": True,
            "write": False,
            "server_can_create": False,
        },
    }
    outcomes: dict[str, dict[str, Any]] = {}

    faulthandler.enable(file=sys.stderr)
    faulthandler.dump_traceback_later(120, repeat=False, file=sys.stderr)
    trace(
        "permission_smoke_watchdog_armed",
        timeout_seconds=180,
        stack_dump_after_seconds=120,
    )
    with sync_playwright() as playwright_instance:
        browser, _browser_context, chrome_profile, cdp_port, browser_process = (
            _loopback_cdp_browser(playwright_instance)
        )
        try:
            for case_name, user in (
                ("create_only", fixture["user"]),
                ("create_and_edit", fixture["write_user"]),
            ):
                context, page = _new_traced_desk_page(browser, case_name)
                try:
                    _login(page, fixture, user=user)
                    suffix = f"customer-permission-{case_name}"
                    monitor = (
                        _start_independent_cdp_monitor(cdp_port)
                        if case_name == "create_only"
                        else None
                    )
                    try:
                        _open_new_form(page, suffix, expected_state="ready_for_entry")
                    finally:
                        _stop_independent_cdp_monitor(monitor)
                    state = _customer_permission_state(page)
                    outcomes[case_name] = state
                    trace(f"customer_permission_case_{case_name}", **state)
                    assert state["doctype"] == "Door Cutting Order" and state["isNew"] is True
                    assert state["permission"] is not None
                    assert state["permission"]["create"] is True
                    assert state["nativePermission"] is not None
                    assert state["nativePermission"]["create"] is True
                    assert state["permission"]["read"] is True
                    assert state["hidden"] is False
                    assert state["hiddenDueToDependency"] is False
                    assert state["readOnly"] is False
                    assert state["insideIntakePair"] is True
                    assert state["hasOriginalFormColumnAncestor"] is False
                    assert set(state["guardedFields"]) == {
                        "status",
                        "total_cost_usd",
                        "board_item",
                        "recovery_creation_token",
                    }
                    assert state["guardedFields"]["status"]["hidden"] is True
                    assert state["guardedFields"]["status"]["readOnly"] is True
                    assert state["guardedFields"]["board_item"]["hidden"] is True
                    assert state["guardedFields"]["recovery_creation_token"]["hidden"] is True
                    assert state["guardedFields"]["recovery_creation_token"]["readOnly"] is True
                    assert state["guardedFields"]["total_cost_usd"]["readOnly"] is True
                    assert state["guardedFields"]["total_cost_usd"]["permlevel"] == 1
                    assert all(
                        field["status"] != "Write"
                        for field in state["guardedFields"].values()
                    )

                    if case_name == "create_only":
                        assert state["nativePermission"]["write"] is False
                        assert state["permission"]["write"] is True
                        assert state["nativeFieldPermissionStatus"] == "Read"
                        assert state["fieldPermissionStatus"] == "Write"
                        assert state["hideEmptyReadOnlyFields"] in (1, "1", True)
                        assert state["fieldPermission"]["create"] is True
                        assert state["fieldPermission"]["write"] is True
                        assert state["controlStatus"] == "Write"
                        assert state["hideControl"] is False
                        assert state["inputExists"] is True and state["inputVisible"] is True
                        assert state["formCanWrite"] is False
                        assert state["doctypeCacheWrite"] is False
                        assert state["createProjectionActive"] is True
                        assert state["projectionPermissionLevels"] == [0]
                        assert state["nativePermissionRows"] is not None
                        assert state["formPermissionRows"] == [
                            (
                                {**row, "write": True}
                                if row and row["create"] and not row["write"]
                                else row
                            )
                            for row in state["nativePermissionRows"]
                        ]

                        # Keep the NEW form's native permission and Link lifecycle untouched
                        # until Customer validation and official Save have completed.
                        _fill_header(page, fixture, "Create-only official save permission check")
                        _enter_real_measurements(page, 1)
                        save_requests: list[str] = []
                        page.on(
                            "request",
                            lambda request: save_requests.append(request.url)
                            if request.method == "POST"
                            and "frappe.desk.form.save.savedocs" in request.url
                            else None,
                        )
                        order_name = _save_new_document(page)
                        assert len(save_requests) == 1
                        after_save = _customer_permission_state(page)
                        assert after_save["isNew"] is False
                        assert after_save["formCanWrite"] is False
                        assert after_save["permission"]["write"] is False
                        assert after_save["doctypeCacheWrite"] is False
                        assert after_save["createProjectionActive"] is False
                        assert after_save["controlStatus"] == "Read"

                        persisted = page.evaluate(
                            "name => frappe.xcall('frappe.client.get',"
                            " {doctype: 'Door Cutting Order', name})",
                            order_name,
                        )
                        assert persisted["customer"] == fixture["customer"]
                        assert persisted["default_edge_type"] == fixture["edge_type"]
                        assert persisted["board_description"] == "AL129 recovery test MDF"
                        assert len(persisted["pieces"]) == 1
                        # Frappe's rejected Promise may not expose the response
                        # metadata. Verify the actual server HTTP response and its
                        # exception type, not a regex over a browser error string.
                        with page.expect_response(
                            lambda response: (
                                "frappe.client.set_value" in response.url
                                and response.request.method == "POST"
                            ),
                            timeout=30_000,
                        ) as denied_response_info:
                            denied_write = page.evaluate(
                                "async name => { try {"
                                " await frappe.xcall('frappe.client.set_value',"
                                " {doctype: 'Door Cutting Order', name,"
                                " fieldname: 'order_notes', value: 'unauthorized write'});"
                                " return {denied: false};"
                                " } catch (error) { return {denied: true,"
                                " errorType: String(error && error.name || ''),"
                                " errorText: String(error && error.message || error || '')}; } }",
                                order_name,
                            )
                        denied_response = denied_response_info.value
                        denied_payload = denied_response.json()
                        exception_type = str(denied_payload.get("exc_type") or "")
                        assert denied_write["denied"] is True
                        assert denied_response.status == 403, (
                            "Unauthorized WRITE must be rejected at the HTTP boundary: "
                            f"status={denied_response.status}, exc_type={exception_type}"
                        )
                        assert "PermissionError" in exception_type, (
                            f"Expected Frappe PermissionError, got {exception_type}; "
                            f"response_fields={list(denied_payload)}"
                        )
                        unchanged = page.evaluate(
                            "name => frappe.xcall('frappe.client.get',"
                            " {doctype: 'Door Cutting Order', name})",
                            order_name,
                        )
                        assert unchanged["order_notes"] == "Create-only official save permission check"
                        _open_new_form(
                            page,
                            f"{suffix}-next-document",
                            expected_state="ready_for_entry",
                        )
                        next_form = _customer_permission_state(page)
                        assert next_form["documentName"] != order_name
                        assert next_form["isNew"] is True
                        assert next_form["nativePermission"]["write"] is False
                        assert next_form["permission"]["write"] is True
                        assert next_form["formCanWrite"] is False
                        assert next_form["doctypeCacheWrite"] is False
                        assert next_form["createProjectionActive"] is True
                        outcomes[case_name].update({
                            "customerEnterable": True,
                            "officialSave": True,
                            "savedDocumentWriteDenied": denied_response.status == 403,
                            "doctypeCacheWriteAfterSave": after_save["doctypeCacheWrite"],
                            "postSaveProjectionRemoved": not after_save["createProjectionActive"],
                            "nextNewDocumentHasIsolatedProjection": (
                                next_form["documentName"] != order_name
                                and next_form["createProjectionActive"]
                            ),
                        })
                        trace(
                            "create_only_official_save_and_existing_write_denial",
                            official_save_requests=len(save_requests),
                            native_write_after_save=after_save["formCanWrite"],
                            direct_api_write_denied=denied_response.status == 403 and "PermissionError" in exception_type,
                            stored_value_unchanged=unchanged["order_notes"]
                            == "Create-only official save permission check",
                            next_document_projection_isolated=(
                                next_form["documentName"] != order_name
                                and next_form["createProjectionActive"]
                            ),
                        )
                    else:
                        assert state["permission"]["write"] is True
                        assert state["nativePermission"]["write"] is True
                        assert state["fieldPermissionStatus"] == "Write"
                        assert state["controlStatus"] == "Write"
                        assert state["hideControl"] is False
                        assert state["inputExists"] is True and state["inputVisible"] is True
                        assert state["doctypeCacheWrite"] is True
                        _fill_header(page, fixture, "Create and edit input check")
                        _enter_real_measurements(page, 1)
                        order_name = _save_new_document(page)
                        page.wait_for_function(
                            "() => window.AlmdinaOrderRevisionUX"
                            " && cur_frm.__almdinaPrimaryActionMode === 'edit'",
                            timeout=20_000,
                        )
                        # DCO owns its tab-local Edit action; Frappe's primary action
                        # is deliberately hidden after the document is saved.
                        edit_action = page.locator("button.dco-tab-edit-start").first
                        expect(edit_action).to_be_visible(timeout=20_000)
                        edit_action.click()
                        page.wait_for_function(
                            "() => window.AlmdinaOrderRevisionUX"
                            " && AlmdinaOrderRevisionUX.isEditableDraft(cur_frm)",
                            timeout=20_000,
                        )
                        editing = _customer_permission_state(page)
                        assert editing["documentName"] == order_name
                        assert editing["isNew"] is False
                        assert editing["permission"]["write"] is True
                        assert editing["controlStatus"] == "Write"
                        assert editing["inputExists"] is True and editing["inputVisible"] is True
                        outcomes[case_name].update({
                            "customerEnterable": True,
                            "officialSave": True,
                            "existingEditSession": True,
                        })
                        trace(
                            "create_and_edit_user_new_and_existing_edit_passed",
                            official_save=True,
                            existing_edit_session=True,
                        )
                except Exception as error:
                    _capture_failure_screenshot(
                        page,
                        f"customer_permission_case_{case_name}_failed",
                        error,
                    )
                    raise
                finally:
                    context.close()

            context, page = _new_traced_desk_page(browser, "no_create")
            try:
                _login(page, fixture, user=fixture["no_create_user"])
                # Assert native HTTP authorization, not an exception-message regex:
                # Frappe xcall may reject with a generic JS error lacking exc_type.
                with page.expect_response(
                    lambda response: "frappe.client.insert" in response.url
                    and response.request.method == "POST",
                    timeout=30_000,
                ) as denied_insert_response:
                    create_attempt = page.evaluate(
                        "async customer => { try { await frappe.xcall('frappe.client.insert',"
                        " {doc: {doctype: 'Door Cutting Order', customer,"
                        " order_date: frappe.datetime.get_today(), board_description: 'Denied',"
                        " board_length_cm: 244, board_width_cm: 122}});"
                        " return {created: true};"
                        " } catch (error) { return {created: false}; } }",
                        fixture["customer"],
                    )
                assert create_attempt["created"] is False
                denied_response = denied_insert_response.value
                assert denied_response.status == 403, (
                    f"Expected server permission denial HTTP 403, got {denied_response.status}"
                )

                response = page.goto(
                    f"{DESK_URL}/app/door-cutting-order",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                trace("no_create_desk_list_navigation", status=response.status if response else None)
                page.wait_for_function(
                    "() => { const route = window.frappe && frappe.get_route && frappe.get_route();"
                    " return Boolean(window.frappe && frappe.router && frappe.app"
                    " && Array.isArray(route) && route[0] === 'List'"
                    " && route[1] === 'Door Cutting Order'); }",
                    timeout=30_000,
                )
                list_state = page.evaluate(
                    "() => { const buttons = [...document.querySelectorAll("
                    "'.page-actions button, .page-actions a')];"
                    " const isNew = node => /(^|\\b)(new|add)(\\b|$)|جديد|إنشاء/i"
                    " .test((node.textContent || '').trim());"
                    " return {route: frappe.get_route().join('/'),"
                    " canCreate: frappe.perm.has_perm('Door Cutting Order', 0, 'create'),"
                    " enabledNewActions: buttons.filter(node => isNew(node)"
                    " && !node.disabled && node.getAttribute('aria-disabled') !== 'true')"
                    " .map(node => (node.textContent || '').trim().slice(0, 40))}; }"
                )
                assert list_state["canCreate"] is False
                assert list_state["enabledNewActions"] == []
                form_response = page.goto(
                    f"{DESK_URL}/app/door-cutting-order/new-door-cutting-order-al129-no-create",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                trace(
                    "no_create_new_form_navigation",
                    status=form_response.status if form_response else None,
                )
                page.wait_for_function(
                    "() => { if (!window.frappe || !frappe.boot"
                    " || typeof frappe.get_route !== 'function') return false;"
                    " const frm = window.cur_frm; const route = frappe.get_route() || [];"
                    " const text = [...document.querySelectorAll('.msgprint-dialog, .alert')]."
                    "map(node => node.innerText || '').join(' ').toLowerCase();"
                    " const permissionDenied = /not permitted|permission|صلاحية|غير مخول/.test(text);"
                    " if (permissionDenied) return true;"
                    " if (!route.length) return false;"
                    " if (route[0] === 'Form' && route[1] === 'Door Cutting Order')"
                    " return Boolean(frm && frm.doctype === 'Door Cutting Order' && frm.is_new()"
                    " && frm.has_perm && !frm.has_perm('create'));"
                    " const expectedPath = '/app/door-cutting-order/new-door-cutting-order-al129-no-create';"
                    " return location.pathname.replace(/\\/$/, '') !== expectedPath; }",
                    timeout=30_000,
                )
                form_state = page.evaluate(
                    "() => { const frm = window.cur_frm; const button ="
                    " document.querySelector('.page-actions .primary-action');"
                    " const route = frappe.get_route() || [];"
                    " const messages = [...document.querySelectorAll('.msgprint-dialog, .alert')]"
                    " .map(node => node.innerText || '').join(' ');"
                    " return {doctype: frm && frm.doctype || null,"
                    " isNew: Boolean(frm && frm.is_new && frm.is_new()),"
                    " nativeCreate: Boolean(frm && frm.has_perm && frm.has_perm('create')),"
                    " saveDisabled: Boolean(frm && frm.save_disabled),"
                    " buttonText: (button?.innerText || '').trim().slice(0, 40),"
                    " buttonDisabled: button ? Boolean(button.disabled"
                    " || button.getAttribute('aria-disabled') === 'true') : null,"
                    " route: route.join('/'),"
                    " path: location.pathname,"
                    " permissionMessage: /not permitted|permission|صلاحية|غير مخول/i"
                    " .test(messages)}; }"
                )
                trace("no_create_direct_desk_result", **form_state)
                if form_state["doctype"] == "Door Cutting Order" and form_state["isNew"]:
                    assert form_state["nativeCreate"] is False
                    assert form_state["saveDisabled"] is True or form_state["buttonDisabled"] is True
                else:
                    assert form_state["permissionMessage"] is True or not form_state["route"].startswith(
                        "Form/Door Cutting Order/"
                    )
                outcomes["no_create"] = {
                    "uiNewActionUnavailable": True,
                    "directDeskCreationUnavailable": True,
                    "officialApiCreateDenied": denied_response.status == 403,
                    "deskRoute": list_state["route"],
                }
                trace("no_create_denied_by_desk_and_server", **outcomes["no_create"])
            except Exception as error:
                _capture_failure_screenshot(page, "no_create_case_failed", error)
                raise
            finally:
                context.close()

            trace(
                "customer_permission_differential_complete",
                create_only_enterable=outcomes["create_only"]["customerEnterable"],
                create_and_edit_enterable=outcomes["create_and_edit"]["customerEnterable"],
                no_create_denied=outcomes["no_create"]["officialApiCreateDenied"],
                shared_doctype_write_unchanged=True,
            )
            _capture_evidence({
                "runtime_versions": fixture["versions"],
                "create_only_new_entry_and_save": "PASS",
                "create_only_saved_document_write_denied": "PASS",
                "create_and_edit_new_and_edit_session": "PASS",
                "no_create_desk_and_api_denied": "PASS",
                "permission_cases": outcomes,
                "shared_doctype_write_unchanged": True,
            })
        finally:
            try:
                browser.close()
            finally:
                if browser_process.poll() is None:
                    browser_process.terminate()
                    try:
                        browser_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        browser_process.kill()
                        browser_process.wait(timeout=5)
                shutil.rmtree(chrome_profile, ignore_errors=True)
                faulthandler.cancel_dump_traceback_later()


def test_real_desk_create_permission_revoke_restore_isolated() -> None:
    """Exercise permission projection transitions on a fresh form, without Customer entry."""
    fixture = _fixtures()
    with _cdp_browser_session() as (browser, _cdp_port):
        context, page = _new_traced_desk_page(browser, "permission-revoke-restore")
        try:
            _login(page, fixture, user=fixture["user"])
            _open_new_form(page, "permission-revoke-restore", expected_state="ready_for_entry")
            state = _customer_permission_state(page)
            assert state["isNew"] is True and state["createProjectionActive"] is True
            transition = page.evaluate(
                "() => { const frm = cur_frm;"
                " const cached = frappe.perm.doctype_perm[frm.doctype];"
                " if (!cached || !cached[0]) throw new Error('doctype permission cache unavailable');"
                " const isVisible = element => { if (!element || !element.isConnected) return false;"
                " const style = getComputedStyle(element); return element.getClientRects().length > 0"
                " && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'; };"
                " const before = JSON.stringify(cached.map(row => row && ({create: row.create, write: row.write})));"
                " const originalCreate = cached[0].create; let revoked;"
                " try { cached[0].create = 0;"
                " window.dispatchEvent(new CustomEvent('almdina:permissions-updated'));"
                " const button = document.querySelector('.page-actions .primary-action');"
                " revoked = {nativeCreate: frm.has_perm('create'), saveDisabled: frm.save_disabled,"
                " saveActionVisible: isVisible(button), projection: Boolean(frm.__almdina_new_create_field_projection)};"
                " } finally { cached[0].create = originalCreate;"
                " window.dispatchEvent(new CustomEvent('almdina:permissions-updated')); }"
                " const button = document.querySelector('.page-actions .primary-action');"
                " return {revoked, restored: {nativeCreate: frm.has_perm('create'),"
                " saveDisabled: frm.save_disabled, saveActionVisible: isVisible(button),"
                " projection: Boolean(frm.__almdina_new_create_field_projection)},"
                " cacheIdentityStable: cached === frappe.perm.doctype_perm[frm.doctype],"
                " cacheValuesRestored: before === JSON.stringify(cached.map(row => row && ({create: row.create, write: row.write})))}; }"
            )
            assert transition["revoked"] == {
                "nativeCreate": False,
                "saveDisabled": True,
                "saveActionVisible": False,
                "projection": False,
            }, transition
            assert transition["restored"] == {
                "nativeCreate": True,
                "saveDisabled": False,
                "saveActionVisible": False,  # Frappe hides Save on a clean form.
                "projection": True,
            }, transition
            # Revoke/regrant must also work after an actual native user input,
            # when Save is expected to become visible for the dirty NEW form.
            note_control = page.locator("[data-fieldname='order_notes'] textarea").first
            expect(note_control).to_be_visible(timeout=5_000)
            note_control.fill("Create permission restored: dirty form")
            page.wait_for_function(
                "() => cur_frm && cur_frm.is_dirty() &&"
                " (() => { const button = document.querySelector('.page-actions .primary-action');"
                " return Boolean(button && button.getClientRects().length > 0"
                " && getComputedStyle(button).visibility !== 'hidden'"
                " && !button.disabled); })()",
                timeout=10_000,
            )
            assert transition["cacheIdentityStable"] is True, transition
            assert transition["cacheValuesRestored"] is True, transition
            trace("create_permission_revoke_restore_isolated", **transition)
        except Exception as error:
            _capture_failure_screenshot(page, "permission_revoke_restore_failed", error)
            raise
        finally:
            context.close()


def _fill_header(page: Page, fixture: dict[str, Any], notes: str) -> None:
    _set_link(page, "customer", fixture["customer"])
    page.locator("[data-fieldname='board_description'] input").fill("AL129 recovery test MDF")
    page.locator("[data-fieldname='board_length_cm'] input").fill("244")
    page.locator("[data-fieldname='board_width_cm'] input").fill("122")
    _set_link(page, "default_edge_type", fixture["edge_type"])
    # Exercise the production radio group, not a direct document mutation.
    machine = page.locator(
        "[data-fieldname='order_cutting_machine'] "
        ".dco-cutting-machine-radios input[type='radio'][value='CNC']"
    )
    expect(machine).to_be_attached()
    machine.check()
    page.wait_for_function(
        "() => cur_frm.doc.order_cutting_machine === 'CNC'"
    )
    page.locator("[data-fieldname='edge_color'] input").fill("White")
    page.locator("[data-fieldname='order_notes'] textarea").fill(notes)


def _enter_real_measurements(page: Page, count: int) -> list[dict[str, Any]]:
    table = page.locator("[data-fieldname='pieces_fast_entry'] .dco-fast-table")
    expect(table).to_be_visible()
    expected = []
    row_observations = []
    if count:
        # Real browser focus/blur on empty placeholder must not create a child.
        # The real worker may tab through an untouched new row.
        initial_count = page.evaluate("() => (cur_frm.doc.pieces || []).length")
        blank = table.locator("tbody tr.dco-virtual-row")
        blank.locator("input[data-field='width_cm']").focus()
        blank.locator("input[data-field='length_cm']").focus()
        page.locator("[data-fieldname='board_description'] input").focus()
        assert page.evaluate("() => (cur_frm.doc.pieces || []).length") == initial_count, (
            "Leaving an untouched virtual row must not create a child"
        )
    page.evaluate("""() => {
        const root = document.querySelector("[data-fieldname='pieces_fast_entry']");
        if (!root) return;
        root.__recoveryKeyEvents = [];
        if (root.__recoveryKeyObserver) return;
        root.__recoveryKeyObserver = true;
        root.addEventListener("keydown", event => {
            if (!["Enter", "Tab"].includes(event.key)) return;
            const input = event.target.closest("input[data-field]");
            if (!input) return;
            root.__recoveryKeyEvents.push({
                key: event.key, field: input.dataset.field,
                row: input.closest("tr")?.dataset.rowName || "",
                value: input.value, defaultPrevented: event.defaultPrevented
            });
            if (root.__recoveryKeyEvents.length > 12) root.__recoveryKeyEvents.shift();
        }, true);
    }""")
    for index in range(count):
        width = 35 + index % 45
        length = 75 + index % 90
        # Materialization replaces the virtual row immediately. Retain the
        # actual row identity, not a locator that resolves to the next blank row.
        virtual = table.locator("tbody tr.dco-virtual-row")
        expect(virtual).to_have_count(1)
        virtual.locator("input[data-field='width_cm']").fill(str(width))
        page.wait_for_function(
            "prior => cur_frm.doc.pieces.length === prior + 1",
            arg=index,
        )
        identity = page.evaluate(
            "() => cur_frm.doc.pieces[cur_frm.doc.pieces.length - 1].name"
        )
        # The stable row-name attribute survives subsequent virtual cloning.
        actual = table.locator(f'tbody tr[data-row-name="{identity}"]')
        expect(actual).to_have_count(1)
        actual.locator("input[data-field='width_cm']").press("Tab")
        actual.locator("input[data-field='length_cm']").fill(str(length))
        actual.locator("input[data-field='length_cm']").press("Enter")
        page.wait_for_function(
            "({identity, count, width, length}) => "
            "cur_frm.doc.pieces.length === count && "
            "cur_frm.doc.pieces.some(r => r.name === identity && "
            "Number(r.width_cm) === width && Number(r.length_cm) === length)",
            arg={"identity": identity, "count": index + 1,
                 "width": width, "length": length},
        )
        expected.append({"width_cm": width, "length_cm": length, "qty": 1})
        observed = page.evaluate("""() => ({
            count: (window.cur_frm?.doc?.pieces || []).length,
            virtual: document.querySelector(
                "[data-fieldname='pieces_fast_entry'] tr.dco-virtual-row"
            )?.dataset.rowName || null
        })""")
        row_observations.append({"row": index + 1, "identity": identity, **observed})
    try:
        page.wait_for_function(
            "count => window.cur_frm && cur_frm.doc.pieces.length === count",
            arg=count,
            timeout=30_000,
        )
    except Exception:
        state = page.evaluate(
            """() => {
                const frm = window.cur_frm;
                const root = document.querySelector("[data-fieldname='pieces_fast_entry']");
                const virtual = root && root.querySelector("tr.dco-virtual-row");
                const inputs = virtual
                    ? [...virtual.querySelectorAll("input[data-field]")]
                        .map(el => ({field: el.dataset.field, value: el.value,
                            disabled: el.disabled, focused: el === document.activeElement}))
                    : [];
                return {
                    document: frm && frm.doc && frm.doc.name,
                    pieceCount: frm && frm.doc && (frm.doc.pieces || []).length,
                    lastPieces: frm && frm.doc && (frm.doc.pieces || []).slice(-3)
                        .map(row => ({name: row.name, width_cm: row.width_cm,
                            length_cm: row.length_cm, qty: row.qty})),
                    virtualRow: virtual && virtual.dataset.rowName,
                    virtualInputs: inputs,
                    rowCount: root && root.querySelectorAll("tbody tr").length,
                    recentKeyEvents: root && root.__recoveryKeyEvents,
                    keyboardOwnerInstalled: Boolean(root && root.querySelector(".dco-fast-table")),
                    activeElement: document.activeElement
                        && document.activeElement.outerHTML.slice(0, 300),
                };
            }"""
        )
        trace("fast_entry_commit_missing", requested=count, row_observations=row_observations, diagnostic=state)
        raise AssertionError(
            f"Fast Entry did not synchronize {count} rows to Frappe: "f"observations={row_observations}; state={state}"
        ) from None
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
        diagnostic_page = page
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
            _capture_failure_screenshot(page, "multi_draft_test_failed", error)
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
        diagnostic_page = page
        try:
            _login(page, fixture)
            _open_new_form(page, "create-100", expected_state="ready_for_entry")
            _fill_header(page, fixture, "Recovery notes with عربي طويل\n" + ("Batch note. " * 80))
            expected = _enter_real_measurements(page, 100)
            first_row = page.locator(
                "[data-fieldname='pieces_fast_entry'] .dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)"
            ).first
            # Add-ons moved to the current modal; operate the same controls
            # used by a real operator instead of a removed inline toggle.
            first_row.locator("button.dco-addons-open").click()
            addons = page.locator(".modal.show [data-addons-dialog]")
            expect(addons).to_be_visible()
            addons.locator("[data-addon-tab='extra_liner']").click()
            addons.locator("[data-addon-enable]").click()
            # The first piece is 35 wide x 75 long; choose the long edge.
            long_side = addons.locator("[data-liner-sides] [data-liner-side='edge_long_left']")
            expect(long_side).to_be_visible()
            long_side.click()
            addons.locator("[data-liner-offset]").fill("0")
            addons.locator("[data-liner-width]").fill("18")
            addons.locator("[data-liner-start]").fill("0")
            # A valid full-length liner on the first 35x75 cm piece.
            addons.locator("[data-liner-length]").fill("75")
            addons.locator("[data-addons-apply]").click()
            expect(addons).not_to_be_visible()
            page.wait_for_function(
                "() => Number(cur_frm.doc.pieces[0].extra_liner) === 1"
            )
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

            save_url_pattern = re.compile(
                r"/api/method/frappe\.desk\.form\.save\.savedocs(?:\?.*)?$"
            )

            def commit_then_drop_response(route) -> None:
                response = route.fetch(timeout=60_000)
                response_body = response.text()
                if not save_posts:
                    raise AssertionError("No observed Official Save POST before route interception")
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

            page.route(save_url_pattern, commit_then_drop_response)
            # A pending checkpoint means the browser has seen an uncertain
            # outcome; it does not prove route.fetch() has committed anything.
            # The deliberately aborted POST emits requestfailed only *after*
            # route.fetch() returned and server_status was recorded.
            with page.expect_event(
                "requestfailed",
                predicate=lambda request: (
                    request.method == "POST"
                    and "frappe.desk.form.save.savedocs" in request.url
                ),
                timeout=90_000,
            ):
                page.locator(".page-actions .primary-action").filter(
                    has_text=re.compile(r"Save|حفظ")
                ).click()
            assert len(save_posts) == 1 and save_posts[0].get("server_status") == 200, (
                f"Lost-response test must prove successful server INSERT: {save_posts}"
            )
            page.wait_for_function(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const record = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " return record.ok && record.value &&"
                " record.value.official_save_state === 'PENDING_RECONCILIATION'; }",
                arg=before_save["draftId"],
                timeout=45_000,
            )
            pending = page.evaluate(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const read = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " const docs = await frappe.xcall('frappe.client.get_list', {"
                " doctype: 'Door Cutting Order', fields: ['name'],"
                " filters: {recovery_creation_token: draftId}, limit_page_length: 10});"
                " return {state: read.ok && read.value ? read.value.official_save_state : null,"
                " token: cur_frm.doc.recovery_creation_token,"
                " revision: read.ok && read.value ? read.value.recovery_revision : null,"
                " serverDocuments: docs}; }",
                before_save["draftId"],
            )
            assert pending["token"] == before_save["draftId"]
            # The browser can reconcile the aborted response immediately,
            # before the test reads the pending marker. A deleted checkpoint is
            # acceptable ONLY with authenticated proof of exactly one INSERT.
            early_created_name = None
            if pending["state"] is None:
                assert len(pending["serverDocuments"]) == 1, (
                    "A lost Save response must never silently delete an unverified draft"
                )
                early_created_name = pending["serverDocuments"][0]["name"]
                trace("lost_response_reconciled_before_browser_close",
                      document=early_created_name)
            else:
                assert pending["state"] == "PENDING_RECONCILIATION", pending
            page.unroute(save_url_pattern)
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
            diagnostic_page = recovery_page
            _attach_diagnostics(recovery_page)
            recovery_page.on("request", record_save_request)
            _login(recovery_page, fixture)
            if early_created_name:
                # Reopen the already-authenticated official document after the
                # browser profile restart; no second NEW or Save is permitted.
                recovery_page.goto(
                    f"{DESK_URL}/app/door-cutting-order/{early_created_name}",
                    wait_until="domcontentloaded", timeout=60_000,
                )
                recovery_page.wait_for_function(
                    "name => cur_frm && cur_frm.doctype === 'Door Cutting Order' "
                    "&& cur_frm.doc.name === name && !cur_frm.is_new()",
                    arg=early_created_name, timeout=60_000,
                )
            else:
                recovery_page.goto(
                    f"{DESK_URL}/app/door-cutting-order/new-door-cutting-order-al129-reconcile",
                    wait_until="domcontentloaded", timeout=60_000,
                )
                recovery_page.wait_for_function(
                    "() => cur_frm && cur_frm.doctype === 'Door Cutting Order' "
                    "&& (cur_frm.is_new() || cur_frm.doc.name.startsWith('DCO-'))",
                    timeout=60_000,
                )
                # After restart the pending INSERT is reconciled only when the
                # worker explicitly chooses Continue. Navigation to NEW alone
                # must not auto-reconcile or issue another native Save.
                pending_card = recovery_page.locator(
                    f".modal.show [data-draft-id='{before_save['draftId']}']"
                )
                expect(pending_card).to_be_visible(timeout=30_000)
                pending_card.locator("[data-recovery-action='continue']").click()
                trace("pending_first_insert_reconciliation_explicitly_requested")
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
            diagnostic_page = retry_page
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
                " attempt: record.value.official_save_attempted_at, token: cur_frm.doc.recovery_creation_token,"
                " pieceCount: record.value.payload.dco.pieces.length,"
                " pieceWidth: Number(record.value.payload.dco.pieces[0]?.width_cm),"
                " liveWidth: Number(cur_frm.doc.pieces[0]?.width_cm)}; }",
                retry_identity["draftId"],
            )
            assert pending_retry["state"] == "PENDING_RECONCILIATION", pending_retry
            assert pending_retry["token"] == retry_identity["draftId"], pending_retry
            # A final native blur can acknowledge one more local checkpoint
            # before the pending marker. Never require the earlier snapshot's
            # revision to remain fixed; require monotonic, durable content.
            assert pending_retry["revision"] >= retry_identity["revision"], pending_retry
            assert pending_retry["pieceCount"] == 1, pending_retry
            assert pending_retry["pieceWidth"] == pending_retry["liveWidth"], pending_retry
            assert pending_retry["pieceWidth"] > 0, pending_retry
            assert pending_retry["attempt"]
            missing_documents = retry_page.evaluate(
                "draftId => frappe.xcall('frappe.client.get_list', {doctype: 'Door Cutting Order',"
                " fields: ['name'], filters: {recovery_creation_token: draftId}, limit_page_length: 10})",
                retry_identity["draftId"],
            )
            assert missing_documents == [], "the first request was stopped before reaching Frappe"
            retry_page.unroute("**/api/method/frappe.desk.form.save.savedocs")
            # NOT_FOUND is not terminal proof: a successful response could
            # simply be delayed while the first request is still in flight.
            # The explicit second Save must be rejected before native insert.
            with retry_page.expect_response(
                lambda response: "reconcile_new_order_creation" in response.url,
                timeout=30_000,
            ):
                retry_page.locator(".page-actions .primary-action").filter(
                    has_text=re.compile(r"Save|حفظ")
                ).click()
            assert "NOT_FOUND" in retry_reconciliation_statuses
            assert len(save_posts) == first_save_attempts + 1, (
                "NOT_FOUND must not trigger another native Save request"
            )
            persisted_pending = retry_page.evaluate(
                "async draftId => { const repo = AlmdinaDcoRecovery.LocalDraftRepository.create();"
                " const result = await repo.read({site: frappe.boot.sitename || frappe.boot.site_name || location.host,"
                " user: frappe.session.user, target_doctype: 'Door Cutting Order', draft_id: draftId});"
                " return result.ok && result.value && result.value.official_save_state; }",
                retry_identity["draftId"],
            )
            assert persisted_pending == "PENDING_RECONCILIATION"
            still_absent = retry_page.evaluate(
                "draftId => frappe.xcall('frappe.client.get_list', {doctype: 'Door Cutting Order',"
                " fields: ['name'], filters: {recovery_creation_token: draftId}, limit_page_length: 10})",
                retry_identity["draftId"],
            )
            assert still_absent == [], "No second DCO may be inserted on uncertain result"
            _capture_evidence({
                "not_found_does_not_authorize_retry": "PASS",
                "retry_reconciliation_statuses": retry_reconciliation_statuses,
                "native_save_requests": len(save_posts),
                "pending_checkpoint_retained": True,
                "new_documents_for_token": len(still_absent),
            })
            trace("not_found_retains_pending_and_blocks_duplicate_insert")
        except Exception as error:
            _capture_failure_screenshot(diagnostic_page, "new_save_test_failed", error)
            raise
        finally:
            context.close()
