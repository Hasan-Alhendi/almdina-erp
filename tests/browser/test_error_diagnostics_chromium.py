"""Real Chromium checks for the app-owned transport/dialog, using a local RPC server.

This exercises the shipped scripts, DOM/SVG and fetch. The native Frappe
serializer/database is certified separately by TestErrorResponseIntegration.
"""

import csv
import os
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_PATH") or shutil.which("chromium"),
            headless=True, args=["--no-sandbox"] if os.geteuid() == 0 else [],
        )
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def origin():
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()


def setup_page(browser, origin, language="en", width=1200):
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(origin)
    with (ROOT / "almdina_erp/translations/ar.csv").open(newline="") as handle:
        catalog = {row[0]: row[1] for row in csv.reader(handle) if len(row) >= 2}
    page.evaluate("""({catalog, language}) => {
        document.body.innerHTML = '';
        document.documentElement.lang = language;
        document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
        window.__ = text => language === 'ar' ? catalog[text] || text : text;
        window.nativeCalls = 0; window.alerts = 0; window.reloads = 0; window.frozen = 0;
        window.frappe = {
            csrf_token: 'test-csrf', almdina: {}, provide() {},
            dom: {freeze() {window.frozen++;}, unfreeze() {window.frozen--;}},
            ui: {
                FileUploader: function(options) {window.uploader = options;},
                Dialog: function(options) {
                    const root = document.createElement('section');
                    root.setAttribute('role', 'dialog');
                    root.innerHTML = '<h2>' + options.title + '</h2><div class="dialog-body"></div>';
                    this.$body = {html: html => root.querySelector('.dialog-body').innerHTML = html};
                    this.$wrapper = {remove: () => root.remove()};
                    this.show = () => document.body.appendChild(root);
                    this.hide = () => {root.remove(); options.onhide();};
                }
            },
            call() {window.nativeCalls++; throw Error('native handler must not own this request');},
            show_alert() {window.alerts++;},
            msgprint(options) {
                if (typeof options === 'string') options = {title:'Message', message:options};
                const root = document.createElement('section');
                root.setAttribute('role', 'dialog');
                root.innerHTML = '<h2>' + options.title + '</h2>' + options.message;
                document.body.appendChild(root);
                return {hide() {root.remove();}};
            }
        };
        window.frm = {generation: 1, doc: {name: 'A', production_dxf: '/private/files/original.dxf'},
            is_new: () => false, reload_doc: async () => {window.reloads++;}};
        window.cleanups = [];
        window.AlmdinaDocumentContext = {
            capture: form => ({name: form.doc.name, generation: form.generation}),
            isCurrent: (form, token) => form.doc.name === token.name && form.generation === token.generation,
            registerCleanup: (_form, _key, cleanup) => window.cleanups.push(cleanup),
        };
        window.visit = name => {
            window.cleanups.splice(0).forEach(cleanup => cleanup());
            window.frm.doc.name = name; window.frm.generation++;
        };
    }""", {"catalog": catalog, "language": language})
    for script in ["frontend_foundation.js", "almdina_ui.js", "door_cutting_order/cutting_plan/secure_dxf_upload.js"]:
        page.add_script_tag(path=str(ROOT / "almdina_erp/public/js" / script))
    page.add_style_tag(path=str(ROOT / "almdina_erp/public/css/almdina_components.css"))
    page.evaluate("frappe.almdina.upload_production_dxf(frm)")
    return page


def envelope():
    return {"almdina_error": {
        "schema_version": 1, "operation": "dxf_upload", "outcome": "rejected",
        "title": "DXF <img src=x onerror=window.pwned=true>",
        "validation_coverage": "partial", "request_reference": "ref-123",
        "issues": [{"code": "KERF_VIOLATION", "problem": "3 mm; required 5 mm",
                    "target": "Board 3; doors 15 and 16", "action": "Move the pieces",
                    "details": ["<img src=x onerror=window.pwned=true>"],
                    "preview": {"paths": [
                        [[[0, 0], [100, 0], [100, 100], [0, 100]]],
                        [[[103, 0], [203, 0], [203, 100], [103, 100]]],
                    ]}}],
    }}


@pytest.mark.parametrize("language,width", [("en", 1200), ("ar", 375)])
def test_rejected_upload_has_one_safe_dialog_numeric_preview_and_no_mutation(browser, origin, language, width):
    page = setup_page(browser, origin, language, width)
    try:
        page.route("**/api/method/**", lambda route: route.fulfill(status=417, json=envelope()))
        page.evaluate("async () => await uploader.on_success({file_url:'/private/files/rejected.dxf'})")
        assert page.get_by_role("dialog").count() == 1
        assert page.locator("img,script[src=x]").count() == 0
        assert not page.evaluate("Boolean(window.pwned)")
        assert page.evaluate("[nativeCalls, reloads, alerts, frozen]") == [0, 0, 0, 0]
        assert page.evaluate("frm.doc.production_dxf") == "/private/files/original.dxf"
        page.locator("summary").first.click()
        assert page.locator("svg path").count() == 2
        assert page.locator("svg").is_visible()
        assert page.get_by_text("ref-123", exact=True).count() == 1
        assert page.locator("body").evaluate("el => el.scrollWidth <= innerWidth")
        page.evaluate("visit('B')")
        assert page.get_by_role("dialog").count() == 0
    finally:
        page.close()


@pytest.mark.parametrize("return_to_a", [False, True])
def test_late_error_never_opens_in_a_different_document_visit(browser, origin, return_to_a):
    page = setup_page(browser, origin)
    routes = []
    try:
        def hold(route):
            routes.append(route)
            page.evaluate("window.requestObserved = true")
        page.route("**/api/method/**", hold)
        page.evaluate("window.pending = uploader.on_success({file_url:'/private/files/rejected.dxf'}); void 0")
        page.wait_for_function("window.requestObserved === true")
        page.evaluate("visit('B')")
        if return_to_a:
            page.evaluate("visit('A')")
        assert len(routes) == 1
        routes[0].fulfill(status=417, json=envelope())
        page.evaluate("async () => await pending")
        assert page.get_by_role("dialog").count() == 0
        assert page.evaluate("[nativeCalls, reloads, alerts, frozen]") == [0, 0, 0, 0]
    finally:
        page.close()


def test_proxy_timeout_reports_uncertainty_without_retrying(browser, origin):
    page = setup_page(browser, origin)
    requests = []
    try:
        def timeout(route):
            requests.append(route.request)
            route.fulfill(status=504, content_type="text/html", body="<h1>Gateway timeout</h1>")
        page.route("**/api/method/**", timeout)
        page.evaluate("async () => await uploader.on_success({file_url:'/private/files/pending.dxf'})")
        assert len(requests) == 1
        assert "could not be confirmed" in page.locator("body").inner_text()
        assert "was not replaced" not in page.locator("body").inner_text()
        assert page.evaluate("frozen") == 0
    finally:
        page.close()


def test_incomplete_or_old_client_context_never_submits_an_upload(browser, origin):
    page = setup_page(browser, origin)
    try:
        page.evaluate("delete window.AlmdinaDocumentContext; window.uploader = null")
        page.evaluate("frappe.almdina.upload_production_dxf(frm)")
        assert page.evaluate("window.uploader") is None
        assert "reload the page" in page.locator("body").inner_text()
        assert page.evaluate("[nativeCalls, reloads, alerts, frozen]") == [0, 0, 0, 0]
    finally:
        page.close()
