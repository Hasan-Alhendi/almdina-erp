from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect, sync_playwright


REPOSITORY = Path(__file__).resolve().parents[2]
DESK_URL = os.environ.get("FRAPPE_DESK_URL", "").rstrip("/")
FIXTURE_PATH = os.environ.get("DCO_AL128_FIXTURE_FILE", "")
EVIDENCE_PATH = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "al128-desk-evidence.json"
TRACE_PATH = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "al128-desk-trace.json"
BASE_FILES = {
    "infrastructure/door_cutting_order_local_draft_repository.js": (
        "almdina_erp/public/js/door_cutting_order/recovery/infrastructure/"
        "door_cutting_order_local_draft_repository.js"
    ),
    "infrastructure/door_cutting_order_recovery_indexeddb.js": (
        "almdina_erp/public/js/door_cutting_order/recovery/infrastructure/"
        "door_cutting_order_recovery_indexeddb.js"
    ),
    "presentation/door_cutting_order_local_checkpoint.js": (
        "almdina_erp/public/js/door_cutting_order/recovery/presentation/"
        "door_cutting_order_local_checkpoint.js"
    ),
}
TRACE: list[dict[str, Any]] = []
TEST_RESULTS: list[dict[str, Any]] = []


def trace(event: str, **details: Any) -> None:
    TRACE.append({"time": round(time.time(), 3), "event": event, **details})
    if len(TRACE) > 1200:
        del TRACE[:-1200]
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACE_PATH.write_text(json.dumps(TRACE, ensure_ascii=False), encoding="utf-8")


def fixtures() -> dict[str, Any]:
    if not DESK_URL or not FIXTURE_PATH:
        pytest.fail("The pinned Frappe Desk URL and isolated fixture file are required.")
    return json.loads(Path(FIXTURE_PATH).read_text(encoding="utf-8"))


def _safe_path(url: str) -> str:
    parsed = urlsplit(url)
    return parsed.path


def attach_diagnostics(page: Page) -> None:
    page.on("pageerror", lambda error: trace("page_error", text=str(error)[:900]))
    page.on(
        "requestfailed",
        lambda request: trace(
            "request_failed",
            method=request.method,
            path=_safe_path(request.url),
            failure=str(request.failure or "unknown")[:300],
        ),
    )
    page.on(
        "console",
        lambda message: trace("console_error", text=message.text[:700])
        if message.type == "error"
        else None,
    )
    page.on(
        "request",
        lambda request: trace("official_save_request", method=request.method)
        if request.method == "POST" and "frappe.desk.form.save.savedocs" in request.url
        else None,
    )


def _browser(playwright_instance) -> Browser:
    executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
    args = ["--no-sandbox", "--disable-dev-shm-usage"] if os.geteuid() == 0 else ["--disable-dev-shm-usage"]
    return playwright_instance.chromium.launch(
        headless=True,
        executable_path=executable,
        args=args,
    )


def _login(page: Page, user: str, password: str) -> None:
    response = page.goto(f"{DESK_URL}/login", wait_until="domcontentloaded", timeout=60_000)
    assert response is not None and response.status == 200
    page.locator("#login_email").fill(user)
    page.locator("#login_password").fill(password)
    page.get_by_role("button", name=re.compile(r"^(Login|Continue)$")).click()
    page.wait_for_function(
        "user => window.frappe && frappe.session && frappe.session.user === user",
        arg=user,
        timeout=45_000,
    )
    page.wait_for_function(
        "() => window.frappe && frappe.boot && frappe.boot.sysdefaults "
        "&& Boolean(frappe.boot.sysdefaults.setup_complete) && frappe.app && frappe.router",
        timeout=45_000,
    )
    trace("desk_login_and_boot_ready")


def _logout(page: Page) -> None:
    page.evaluate("async () => { await frappe.call('logout'); }")
    page.goto(f"{DESK_URL}/login", wait_until="domcontentloaded", timeout=30_000)
    trace("desk_logout_completed_in_existing_browser_context")


def _open_order(page: Page, name: str, count: int) -> None:
    page.goto(
        f"{DESK_URL}/app/door-cutting-order/{name}",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    page.wait_for_function(
        "({name, count}) => window.cur_frm && cur_frm.doctype === 'Door Cutting Order' "
        "&& cur_frm.doc.name === name && Array.isArray(cur_frm.doc.pieces) "
        "&& cur_frm.doc.pieces.length === count && cur_frm.fields_dict.pieces_fast_entry",
        arg={"name": name, "count": count},
        timeout=60_000,
    )
    table = page.locator('[data-fieldname="pieces_fast_entry"] .dco-fast-table')
    expect(table).to_be_visible(timeout=30_000)
    expect(
        page.locator(
            '[data-fieldname="pieces_fast_entry"] .dco-fast-table '
            'tbody tr[data-row-name]:not(.dco-virtual-row)'
        ).first
    ).to_be_visible(timeout=30_000)
    trace("real_dco_form_ready", piece_count=count)


def _server_document(page: Page, name: str) -> dict[str, Any]:
    return page.evaluate(
        "async name => {"
        " const doc = await frappe.xcall('frappe.client.get', "
        "   {doctype: 'Door Cutting Order', name});"
        " return {"
        "   modified: doc.modified,"
        "   order_notes: doc.order_notes,"
        "   pieces: (doc.pieces || []).map(row => ({"
        "     name: row.name, width_cm: row.width_cm, length_cm: row.length_cm,"
        "     qty: row.qty, extra_liner: row.extra_liner, edge_long_left: row.edge_long_left"
        "   }))"
        " };"
        "}",
        name,
    )


def _start_real_edit_session(page: Page) -> None:
    page.wait_for_function(
        "() => window.AlmdinaPermissions && frappe.almdina "
        "&& typeof frappe.almdina.orderCanEdit === 'function' "
        "&& window.cur_frm && window.cur_frm.doc.status === 'Draft'",
        timeout=30_000,
    )
    edit_action = page.get_by_role("button", name="تعديل", exact=True).first
    expect(edit_action).to_be_visible(timeout=30_000)
    edit_action.click()
    page.wait_for_function(
        "() => window.cur_frm && frappe.almdina.orderCanEdit(cur_frm) "
        "&& !cur_frm.fields_dict.pieces_fast_entry.$wrapper "
        ".find('input[data-field=width_cm]').first().prop('disabled')",
        timeout=30_000,
    )
    trace("edit_started_through_frappe_toolbar")


def _checkpoint_record(page: Page, name: str) -> dict[str, Any]:
    return page.evaluate(
        "async name => {"
        " const site = frappe.boot.sitename || frappe.boot.site_name || location.host;"
        " const user = String(frappe.session.user || '').trim();"
        " const repo = window.AlmdinaDcoRecovery.LocalDraftRepository.create();"
        " const found = await repo.discover({"
        "   site, user, target_doctype: 'Door Cutting Order', mode: 'EDIT', target_name: name"
        " });"
        " if (!found.ok) throw new Error(found.error.code);"
        " return {site, user, records: found.value.records};"
        "}",
        name,
    )


def test_real_desk_edits_checkpoint_and_permission_isolation() -> None:
    """Drive the supported Desk controls and inspect IndexedDB after refresh."""
    fixture = fixtures()
    assert fixture["versions"] == {"frappe": "16.17.5", "erpnext": "16.17.0"}
    save_requests: list[str] = []
    with sync_playwright() as playwright_instance:
        browser = _browser(playwright_instance)
        context = browser.new_context(viewport={"width": 1800, "height": 1200})
        page = context.new_page()
        attach_diagnostics(page)
        page.on(
            "request",
            lambda request: save_requests.append(request.method)
            if request.method == "POST" and "frappe.desk.form.save.savedocs" in request.url
            else None,
        )
        try:
            _login(page, fixture["editor"], fixture["password"])
            _open_order(page, fixture["edit_order"], 10)
            page.wait_for_function(
                "() => window.AlmdinaPermissions && cur_frm "
                "&& AlmdinaPermissions.canDocument(cur_frm, 'view_orders') "
                "&& AlmdinaPermissions.canDocument(cur_frm, 'edit_order')",
                timeout=30_000,
            )
            permission_state = page.evaluate(
                "() => ({"
                "  viewOrders: AlmdinaPermissions.canDocument(cur_frm, 'view_orders'),"
                "  editOrder: AlmdinaPermissions.canDocument(cur_frm, 'edit_order'),"
                "  customerRead: Boolean(frappe.perm.get_perm('Customer')[0].read),"
                "  edgeTypeRead: Boolean(frappe.perm.get_perm('Edge Banding Type')[0].read)"
                "})"
            )
            assert permission_state["viewOrders"] is True
            assert permission_state["editOrder"] is True
            assert permission_state["customerRead"] is True
            assert permission_state["edgeTypeRead"] is True
            server_permissions = fixture["permission_evidence"]["server_checks"]
            assert server_permissions == {
                "editor_can_read": True,
                "editor_can_write": True,
                "viewer_can_read": True,
                "viewer_can_write": False,
            }
            before_server = _server_document(page, fixture["edit_order"])
            piece_names = page.evaluate("() => cur_frm.doc.pieces.slice(0, 3).map(row => row.name)")
            _start_real_edit_session(page)

            rows = page.locator(
                '[data-fieldname="pieces_fast_entry"] .dco-fast-table '
                'tbody tr[data-row-name]:not(.dco-virtual-row)'
            )
            first = rows.nth(0)
            first.locator('input[data-field="width_cm"]').fill("61.5")
            first.locator('input[data-field="width_cm"]').press("Tab")
            first.locator('input[data-field="length_cm"]').fill("101.25")
            first.locator('input[data-field="length_cm"]').press("Tab")
            first.locator('input[data-field="qty"]').fill("4")
            first.locator('input[data-field="qty"]').press("Tab")
            first.locator('.dco-check-toggle[data-check-field="edge_long_left"]').click()

            second = rows.nth(1)
            second.locator('.dco-addon-toggle[data-check-field="extra_liner"]').click()
            second.locator(".dco-all-sides-profile-button[data-bulk-edge-profile-button]").click()
            page.locator(
                "#dco-edge-profile-popover "
                f"[data-bulk-profile-value={json.dumps(fixture['bulk_edge_type'])}]"
            ).click()

            special = rows.nth(2)
            special.locator('input[data-field="notes"]').fill("AL128 special geometry checkpoint note")
            page.wait_for_function(
                "() => {"
                " const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);"
                " return state && state.state === 'LOCAL_SAVED' "
                "   && state.saved_revision > 0 "
                "   && state.saved_revision === state.recovery_revision;"
                "}",
                timeout=30_000,
            )
            expect(page.locator(".dco-recovery-status[data-recovery-state='LOCAL_SAVED']")).to_be_visible()

            current_record = _checkpoint_record(page, fixture["edit_order"])
            assert len(current_record["records"]) == 1
            record = current_record["records"][0]
            by_key = {piece["piece_key"]: piece for piece in record["payload"]["dco"]["pieces"]}
            first_saved = by_key[piece_names[0]]
            second_saved = by_key[piece_names[1]]
            special_saved = by_key[piece_names[2]]
            assert float(first_saved["width_cm"]) == 61.5
            assert float(first_saved["length_cm"]) == 101.25
            assert int(first_saved["qty"]) == 4
            assert int(first_saved["edge_long_left"]) == 0
            assert int(second_saved["extra_liner"]) == 1
            assert int(second_saved["edge_width_top"]) == 1
            assert second_saved["edge_width_top_type_override"] == fixture["bulk_edge_type"]
            assert special_saved["notes"] == "AL128 special geometry checkpoint note"
            special_geometry = json.loads(special_saved["special_shape_geometry_json"])
            assert special_geometry["kind"] == "polygon"
            assert special_geometry["points"] == [[0, 0], [60, 0], [60, 100], [0, 100]]
            assert save_requests == []

            page.reload(wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(
                "name => window.cur_frm && cur_frm.doctype === 'Door Cutting Order' "
                "&& cur_frm.doc.name === name && window.AlmdinaDcoRecovery "
                "&& AlmdinaDcoRecovery.LocalDraftRepository",
                arg=fixture["edit_order"],
                timeout=60_000,
            )
            after_reload = _checkpoint_record(page, fixture["edit_order"])
            assert len(after_reload["records"]) == 1
            assert after_reload["records"][0]["recovery_revision"] == record["recovery_revision"]
            assert after_reload["records"][0]["payload"]["dco"]["pieces"] == record["payload"]["dco"]["pieces"]
            server_after_reload = _server_document(page, fixture["edit_order"])
            assert server_after_reload == before_server
            assert save_requests == []

            _open_order(page, fixture["identity_b"], 10)
            order_b_drafts = _checkpoint_record(page, fixture["identity_b"])
            assert order_b_drafts["records"] == []

            editor_browser_user = current_record["user"]
            _logout(page)
            _login(page, fixture["viewer"], fixture["password"])
            _open_order(page, fixture["edit_order"], 10)
            page.wait_for_function(
                "() => window.AlmdinaPermissions && cur_frm "
                "&& AlmdinaPermissions.canDocument(cur_frm, 'view_orders') "
                "&& !AlmdinaPermissions.canDocument(cur_frm, 'edit_order')",
                timeout=30_000,
            )
            viewer_state = page.evaluate(
                "() => ({"
                "  user: frappe.session.user,"
                "  read: Boolean(frappe.perm.get_perm('Door Cutting Order')[0].read),"
                "  write: Boolean(frappe.perm.get_perm('Door Cutting Order')[0].write),"
                "  editCapability: AlmdinaPermissions.canDocument(cur_frm, 'edit_order'),"
                "  canEdit: frappe.almdina.orderCanEdit(cur_frm),"
                "  widthDisabled: Boolean(cur_frm.fields_dict.pieces_fast_entry.$wrapper"
                "    .find('input[data-field=width_cm]').first().prop('disabled'))"
                "})"
            )
            assert viewer_state == {
                "user": fixture["viewer"],
                "read": True,
                "write": False,
                "editCapability": False,
                "canEdit": False,
                "widthDisabled": True,
            }
            viewer_drafts = _checkpoint_record(page, fixture["edit_order"])
            viewer_document = page.evaluate(
                "pieceName => {"
                " const row = cur_frm.doc.pieces.find(item => item.name === pieceName);"
                " return {width_cm: row.width_cm, length_cm: row.length_cm, qty: row.qty,"
                "   notes: row.notes, extra_liner: row.extra_liner};"
                "}",
                piece_names[0],
            )
            server_first = next(
                piece for piece in before_server["pieces"] if piece["name"] == piece_names[0]
            )
            assert editor_browser_user == fixture["editor"]
            assert viewer_drafts["user"] == fixture["viewer"]
            assert viewer_drafts["records"] == []
            assert viewer_document == {
                "width_cm": server_first["width_cm"],
                "length_cm": server_first["length_cm"],
                "qty": server_first["qty"],
                "notes": server_first["notes"],
                "extra_liner": server_first["extra_liner"],
            }
            assert save_requests == []

            evidence = {
                "result": "PASS",
                "versions": fixture["versions"],
                "desk_boot_setup_complete": True,
                "actual_editor_permissions": permission_state,
                "server_permission_checks": server_permissions,
                "checkpoint_revision": record["recovery_revision"],
                "changed_measurement_qty_edge_extra_special_notes": True,
                "special_geometry_in_checkpoint": True,
                "special_geometry_preserved": True,
                "checkpoint_survived_reload": True,
                "server_document_unchanged": True,
                "cross_order_data_leak": False,
                "read_only_user_cannot_edit_or_discover_checkpoint": True,
                "editor_to_viewer_same_browser_context": True,
                "official_save_requests": len(save_requests),
            }
            TEST_RESULTS.append({"test": "real_desk_edit_checkpoint_permissions", "evidence": evidence})
            print(f"AL128_REAL_DESK_EVIDENCE {json.dumps(evidence, ensure_ascii=False)}")
            trace("real_desk_acceptance_passed", evidence=evidence)
        except Exception:
            try:
                page.screenshot(path=str(TRACE_PATH.parent / "al128-desk-failure.png"), timeout=5_000)
            except Exception:
                pass
            raise
        finally:
            context.close()
            browser.close()


def _install_base_source_overrides(
    context: BrowserContext,
    base_sha: str,
) -> set[str]:
    replaced: set[str] = set()

    def replace_source(route) -> None:
        path = urlsplit(route.request.url).path
        for suffix, repository_path in BASE_FILES.items():
            if path.endswith(suffix):
                body = subprocess.check_output(
                    ["git", "show", f"{base_sha}:{repository_path}"],
                    cwd=REPOSITORY,
                    text=True,
                )
                route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    headers={"cache-control": "no-store"},
                    body=body,
                )
                replaced.add(suffix)
                return
        route.continue_()

    context.route("**/assets/almdina_erp/js/door_cutting_order/recovery/**", replace_source)
    return replaced


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(percentile * len(ordered)) - 1)], 2)


def _benchmark_order(
    browser: Browser,
    fixture: dict[str, Any],
    name: str,
    count: int,
    variant: str,
    base_sha: str,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1800, "height": 1200})
    replaced: set[str] = set()
    if variant == "base":
        replaced = _install_base_source_overrides(context, base_sha)
    page = context.new_page()
    attach_diagnostics(page)
    save_requests: list[str] = []
    page.on(
        "request",
        lambda request: save_requests.append(request.method)
        if request.method == "POST" and "frappe.desk.form.save.savedocs" in request.url
        else None,
    )
    try:
        _login(page, fixture["editor"], fixture["password"])
        _open_order(page, name, count)
        _start_real_edit_session(page)
        page.evaluate(
            """() => {
                const root = cur_frm.fields_dict.pieces_fast_entry.$wrapper.get(0);
                window.__al128FrameSamples = [];
                window.__al128CheckpointSamples = [];
                window.__al128MeasureAction = null;
                root.addEventListener("input", () => {
                    const action = window.__al128MeasureAction;
                    if (!action || action.started) return;
                    action.started = true;
                    action.startedAt = performance.now();
                    const startedAt = action.startedAt;
                    requestAnimationFrame(() => requestAnimationFrame(() => {
                        window.__al128FrameSamples.push(performance.now() - startedAt);
                    }));
                    const awaitCheckpoint = () => {
                        const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);
                        if (state && state.state === "LOCAL_SAVED"
                            && state.saved_revision > action.savedRevision) {
                            window.__al128CheckpointSamples.push(performance.now() - startedAt);
                            action.completed = true;
                            return;
                        }
                        setTimeout(awaitCheckpoint, 16);
                    };
                    setTimeout(awaitCheckpoint, 16);
                }, true);
            }"""
        )
        row = page.locator(
            '[data-fieldname="pieces_fast_entry"] .dco-fast-table '
            'tbody tr[data-row-name]:not(.dco-virtual-row)'
        ).first
        sample_specs = (
            ("width_cm", lambda index: 45 + (index % 20) / 10),
            ("length_cm", lambda index: 90 + (index % 20) / 10),
            ("qty", lambda index: 2 + index % 2),
        )
        for index in range(30):
            for fieldname, value_for in sample_specs:
                sample_count = page.evaluate(
                    "() => window.__al128CheckpointSamples.length"
                )
                page.evaluate(
                    "() => {"
                    " const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);"
                    " window.__al128MeasureAction = {"
                    "   started: false, completed: false, savedRevision: state.saved_revision"
                    " };"
                    "}"
                )
                control = row.locator(f'[data-field="{fieldname}"]')
                control.click()
                control.press("Control+A")
                control.press_sequentially(str(value_for(index)))
                control.press("Tab")
                page.wait_for_function(
                    "count => window.__al128CheckpointSamples.length > count",
                    arg=sample_count,
                    timeout=10_000,
                )
                page.evaluate("() => { window.__al128MeasureAction = null; }")
        samples = page.evaluate(
            "() => ({"
            " frame: window.__al128FrameSamples.slice(-90),"
            " checkpoint: window.__al128CheckpointSamples.slice(-90)"
            "})"
        )
        frame_ms = samples["frame"]
        checkpoint_ms = samples["checkpoint"]
        assert len(frame_ms) == 90, f"Expected 90 real input-frame samples, got {len(frame_ms)}"
        assert len(checkpoint_ms) == 90
        assert not save_requests, "Measurement checkpoint unexpectedly invoked Official Save."
        if variant == "base":
            assert replaced == set(BASE_FILES), f"Base asset intercept missed: {set(BASE_FILES) - replaced}"
        result = {
            "variant": variant,
            "rows": count,
            "input_samples": len(frame_ms),
            "input_to_next_paint_frame_ms": {
                "p50": _percentile(frame_ms, 0.50),
                "p95": _percentile(frame_ms, 0.95),
            },
            "checkpoint_ack_ms": {
                "p50": _percentile(checkpoint_ms, 0.50),
                "p95": _percentile(checkpoint_ms, 0.95),
            },
            "base_assets_replaced": sorted(replaced),
            "official_save_requests": len(save_requests),
        }
        trace("measurement_entry_benchmark_completed", **result)
        return result
    except Exception as error:
        trace(
            "measurement_entry_benchmark_failed",
            variant=variant,
            rows=count,
            error=str(error)[:900],
        )
        try:
            page.screenshot(path=str(TRACE_PATH.parent / "al128-desk-failure.png"), timeout=5_000)
        except Exception:
            pass
        raise
    finally:
        context.close()


def test_actual_measurement_entry_performance_200_and_500_before_after() -> None:
    fixture = fixtures()
    base_sha = os.environ.get("AL128_BASE_SHA", "").strip()
    if not base_sha:
        pytest.fail("AL128_BASE_SHA is required to compare the pinned PR base and HEAD behavior.")
    subprocess.run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"], cwd=REPOSITORY, check=True)
    results = []
    with sync_playwright() as playwright_instance:
        browser = _browser(playwright_instance)
        try:
            for count, fixture_key, variants in (
                (200, "performance_200", ("base", "head")),
                (500, "performance_500", ("head", "base")),
            ):
                for variant in variants:
                    result = _benchmark_order(
                        browser,
                        fixture,
                        str(fixture[fixture_key]),
                        count,
                        variant,
                        base_sha,
                    )
                    results.append(result)
        finally:
            browser.close()

    by_rows = {
        count: {result["variant"]: result for result in results if result["rows"] == count}
        for count in (200, 500)
    }
    comparisons = {}
    for count, variants in by_rows.items():
        baseline = variants["base"]
        candidate = variants["head"]
        comparisons[str(count)] = {
            metric: {
                "base_p95_ms": baseline[metric]["p95"],
                "head_p95_ms": candidate[metric]["p95"],
                "delta_ms": round(candidate[metric]["p95"] - baseline[metric]["p95"], 2),
                "delta_percent": round(
                    (candidate[metric]["p95"] - baseline[metric]["p95"])
                    / max(baseline[metric]["p95"], 0.01)
                    * 100,
                    2,
                ),
            }
            for metric in ("input_to_next_paint_frame_ms", "checkpoint_ack_ms")
        }
    evidence = {
        "interaction_run": "PASS",
        "performance_rating": "NOT_ASSESSED_NO_ACCEPTANCE_THRESHOLD_DEFINED",
        "performance_metrics_are_comparative_evidence": True,
        "versions": fixture["versions"],
        "base_sha": base_sha,
        "benchmarks": results,
        "p95_comparison": comparisons,
    }
    TEST_RESULTS.append({"test": "actual_measurement_entry_performance", "evidence": evidence})
    print(f"AL128_MEASUREMENT_PERFORMANCE {json.dumps(evidence, ensure_ascii=False)}")
    trace("measurement_entry_benchmarks_passed", benchmarks=results)


def pytest_sessionfinish(session, exitstatus) -> None:
    del session
    summary = {
        "test_exit_status": exitstatus,
        "results": TEST_RESULTS,
        "trace_events": len(TRACE),
    }
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    TRACE_PATH.write_text(json.dumps(TRACE, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as output:
            output.write("\n### ALMADINA-128 real Desk acceptance evidence\n\n")
            output.write("```json\n")
            output.write(json.dumps(summary, ensure_ascii=False, indent=2))
            output.write("\n```\n")
