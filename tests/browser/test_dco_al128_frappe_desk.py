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
        "     qty: row.qty, extra_liner: row.extra_liner, edge_long_left: row.edge_long_left,"
        "     edge_long_right: row.edge_long_right, edge_width_top: row.edge_width_top,"
        "     edge_width_bottom: row.edge_width_bottom, notes: row.notes,"
        "     edge_long_left_type_override: row.edge_long_left_type_override,"
        "     edge_long_right_type_override: row.edge_long_right_type_override,"
        "     edge_width_top_type_override: row.edge_width_top_type_override,"
        "     edge_width_bottom_type_override: row.edge_width_bottom_type_override"
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
    # PageEditAction owns the action and uses a translated label ("Edit order").
    # Locate its stable component class rather than assuming the test user's locale.
    edit_action = page.locator("button.dco-tab-edit-start").first
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
            # The current measurements UI opens add-ons in a native Frappe dialog,
            # rather than rendering five independent toggles in each table row.
            second.locator("button.dco-addons-open[data-open-addons='1']").click()
            addons = page.locator(".dco-addons-modal [data-addons-dialog]")
            expect(addons).to_be_visible(timeout=10_000)
            addons.locator('[data-addon-tab="extra_liner"]').click()
            addons.locator('[data-liner-side="edge_width_top"]').click()
            expect(addons.locator("[data-addons-apply]")).to_be_enabled()
            addons.locator("[data-addons-apply]").click()
            expect(addons).to_be_hidden(timeout=30_000)
            # Bulk options are populated asynchronously from the profile owner.
            # Wait for the actual fixture profile rather than clicking an empty menu.
            page.wait_for_function(
                "value => Boolean(window.AlmdinaMultiEdgeBanding && window.cur_frm "
                "&& AlmdinaMultiEdgeBanding.profiles(cur_frm).has(value))",
                arg=fixture["bulk_edge_type"],
                timeout=30_000,
            )
            bulk_button = second.locator(
                ".dco-all-sides-profile-button[data-bulk-edge-profile-button]"
            )
            page.evaluate("""() => {
                window.__al128PopoverEvents = [];
                const events = window.__al128PopoverEvents;
                const capture = type => e => {
                    if (!e.target?.closest?.('[data-bulk-edge-profile-button]')) return;
                    events.push({type, path: e.target.tagName, at: performance.now()});
                };
                document.addEventListener('pointerdown', capture('pointerdown'), true);
                document.addEventListener('click', capture('click'), true);
                const observer = new MutationObserver(records => {
                    for (const item of records) {
                        for (const node of item.addedNodes) if (node.id === 'dco-edge-profile-popover') {
                            events.push({type: 'menu-added', at: performance.now()});
                        }
                        for (const node of item.removedNodes) if (node.id === 'dco-edge-profile-popover') {
                            events.push({type: 'menu-removed', at: performance.now()});
                        }
                    }
                });
                observer.observe(document.body, {childList: true, subtree: true});
                window.__al128PopoverObserver = observer;
            }""")
            bulk_button.click()
            bulk_option = page.locator(
                "#dco-edge-profile-popover "
                f"[data-bulk-profile-value={json.dumps(fixture['bulk_edge_type'])}]"
            )
            try:
                expect(bulk_option).to_be_visible(timeout=5_000)
            except Exception:
                # Distinguish a stale row / detached popover / missing option.
                # Do not retry or silently bypass the real pointer interaction.
                state = page.evaluate(
                    """({value}) => {
                        const root = cur_frm.fields_dict.pieces_fast_entry.$wrapper.get(0);
                        const rows = [...root.querySelectorAll(
                            '.dco-fast-table tbody tr[data-row-name]:not(.dco-virtual-row)')];
                        const tr = rows[1];
                        const button = tr && tr.querySelector('[data-bulk-edge-profile-button]');
                        const menu = document.getElementById('dco-edge-profile-popover');
                        const row = tr && (cur_frm.doc.pieces || []).find(
                            piece => piece.name === tr.dataset.rowName);
                        return {
                            rowName: tr && tr.dataset.rowName,
                            rowExists: Boolean(row),
                            editable: Boolean(window.frappe?.almdina?.orderCanEdit?.(cur_frm)),
                            buttonExists: Boolean(button),
                            buttonDisabled: button && button.disabled,
                            ariaExpanded: button && button.getAttribute('aria-expanded'),
                            menuExists: Boolean(menu),
                            menuValues: menu ? [...menu.querySelectorAll('[data-bulk-profile-value]')]
                                .map(option => option.dataset.bulkProfileValue) : [],
                            handlerBound: Boolean(root._dcoCompactEdgeProfileControlsBound),
                            popoverEvents: window.__al128PopoverEvents || [],
                            profileLoaded: Boolean(cur_frm._dco_side_edge_profiles_loaded),
                            profileExists: Boolean(window.AlmdinaMultiEdgeBanding
                                && AlmdinaMultiEdgeBanding.profiles(cur_frm).has(value))
                        };
                    }""",
                    {"value": fixture["bulk_edge_type"]},
                )
                trace("bulk_profile_real_click_failed", **state)
                raise AssertionError(f"Real bulk-profile menu failed to open/select: {state}")
            bulk_option.click()
            bulk_edge_state_after_action = page.evaluate(
                "pieceName => {"
                " const row = cur_frm.doc.pieces.find(item => item.name === pieceName);"
                " return Object.fromEntries(["
                "  'edge_long_left', 'edge_long_right', 'edge_width_top', 'edge_width_bottom',"
                "  'edge_long_left_type_override', 'edge_long_right_type_override',"
                "  'edge_width_top_type_override', 'edge_width_bottom_type_override'"
                " ].map(field => [field, row && row[field]]));"
                "}",
                piece_names[1],
            )
            trace("bulk_edge_profile_form_state", state=bulk_edge_state_after_action)
            assert bulk_edge_state_after_action["edge_width_top"] == 1, (
                "Bulk edge profile action did not set the live form model: "
                f"{bulk_edge_state_after_action}"
            )

            special = rows.nth(2)
            special_notes = "AL128 special geometry checkpoint note"
            revision_before_special_notes = page.evaluate(
                "() => AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm).recovery_revision"
            )
            special_notes_input = special.locator('input[data-field="notes"]')
            special_notes_input.fill(special_notes)
            page.wait_for_function(
                "({pieceName, value}) => cur_frm.doc.pieces.some(row =>"
                " row.name === pieceName && row.notes === value)",
                arg={"pieceName": piece_names[2], "value": special_notes},
                timeout=10_000,
            )
            special_notes_input.press("Tab")
            page.wait_for_function(
                "revision => {"
                " const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);"
                " return state && state.recovery_revision > revision;"
                "}",
                arg=revision_before_special_notes,
                timeout=10_000,
            )
            page.wait_for_function(
                "() => {"
                " const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);"
                " return state && state.state === 'LOCAL_SAVED'"
                "   && state.saved_revision === state.recovery_revision;"
                "}",
                timeout=30_000,
            )
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
            for fieldname in (
                "edge_long_left",
                "edge_long_right",
                "edge_width_top",
                "edge_width_bottom",
            ):
                assert int(second_saved[fieldname]) == 1, (
                    f"Bulk edge profile did not persist {fieldname}: {second_saved}"
                )
            for fieldname in (
                "edge_long_left_type_override",
                "edge_long_right_type_override",
                "edge_width_top_type_override",
                "edge_width_bottom_type_override",
            ):
                assert second_saved[fieldname] == fixture["bulk_edge_type"], (
                    f"Bulk edge profile did not persist {fieldname}: {second_saved}"
                )
            assert float(first_saved["width_cm"]) == 61.5
            assert float(first_saved["length_cm"]) == 101.25
            assert int(first_saved["qty"]) == 4
            assert int(first_saved["edge_long_left"]) == 0
            assert int(second_saved["extra_liner"]) == 1
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
                "special_geometry_mutation_via_supported_ui": (
                    "NOT_TESTED_NO_SUPPORTED_MANUFACTURING_EDITOR"
                ),
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


def _changed_base_files(base_sha: str) -> set[str]:
    """Only actual source differences qualify as substituted benchmark assets."""
    changed = set()
    for suffix, path in BASE_FILES.items():
        head_source = subprocess.check_output(
            ["git", "show", f"HEAD:{path}"], cwd=REPOSITORY, text=True,
        )
        base_source = subprocess.check_output(
            ["git", "show", f"{base_sha}:{path}"], cwd=REPOSITORY, text=True,
        )
        if head_source != base_source:
            changed.add(suffix)
    return changed


def _install_base_metadata_overrides(
    context: BrowserContext,
    base_sha: str,
) -> set[str]:
    replaced: set[str] = set()

    def replace_doctype_metadata(route) -> None:
        response = route.fetch()
        payload = response.json()
        documents = payload.get("docs") or []
        metadata = next(
            (item for item in documents if item.get("name") == "Door Cutting Order"),
            None,
        )
        if metadata is None:
            route.fulfill(response=response)
            return

        script = str(metadata.get("__js") or "")
        if not script:
            raise AssertionError("Frappe DCO metadata response did not contain __js.")
        for suffix, repository_path in BASE_FILES.items():
            head_source = subprocess.check_output(
                ["git", "show", f"HEAD:{repository_path}"],
                cwd=REPOSITORY,
                text=True,
            )
            base_source = subprocess.check_output(
                ["git", "show", f"{base_sha}:{repository_path}"],
                cwd=REPOSITORY,
                text=True,
            )
            # Unchanged assets are a valid equality result for latest-Develop
            # comparisons. Replacing them would create a fictional difference.
            if head_source == base_source:
                continue
            if head_source in script:
                script = script.replace(head_source, base_source, 1)
                replaced.add(suffix)
            elif base_source not in script:
                raise AssertionError(
                    f"Frappe DCO __js did not contain either revision of {repository_path}."
                )
            else:
                raise AssertionError(
                    f"Frappe DCO __js already contains Base content for {repository_path}; "
                    "the Base variant was not produced from the checked-out HEAD source."
                )

        metadata["__js"] = script
        headers = {
            key: value
            for key, value in response.headers.items()
            if key not in {"content-length", "content-encoding", "transfer-encoding"}
        }
        route.fulfill(status=response.status, headers=headers, json=payload)
        trace("base_doctype_metadata_overridden", assets=sorted(replaced))

    context.route("**/api/method/frappe.desk.form.load.getdoctype**", replace_doctype_metadata)
    return replaced


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(percentile * len(ordered)) - 1)], 2)


def _publish_benchmark_progress(result: dict[str, Any]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    keyboard = result["input_to_second_animation_frame_ms"]
    checkpoint = result["checkpoint_ack_ms"]
    with open(summary_path, "a", encoding="utf-8") as output:
        output.write(
            f"\n### AL128 measurement benchmark — {result['rows']} pieces, "
            f"{result['variant']}\n\n"
        )
        output.write(
            f"- Keyboard input → second animation frame: "
            f"P50 {keyboard['p50']} ms, P95 {keyboard['p95']} ms "
            f"({result['keyboard_samples']} samples).\n"
        )
        output.write(
            f"- IndexedDB checkpoint acknowledgement: "
            f"P50 {checkpoint['p50']} ms, P95 {checkpoint['p95']} ms "
            f"({result['checkpoint_ack_samples']} samples).\n"
        )
        output.write(
            f"- Phase durations: `{json.dumps(result['phase_durations_seconds'], sort_keys=True)}`\n"
        )
        output.write(f"- Official Save requests: {result['official_save_requests']}\n")


def _remaining_benchmark_timeout_ms(deadline: float) -> int:
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining <= 0:
        raise TimeoutError("AL128 benchmark exceeded its 8-minute measurement budget.")
    return remaining


def _prime_checkpoint_with_real_measurement_edit(page: Page) -> None:
    """Create an acknowledged starting checkpoint before collecting metrics."""
    width = page.locator(
        '[data-fieldname="pieces_fast_entry"] .dco-fast-table '
        'tbody tr[data-row-name]:not(.dco-virtual-row) input[data-field="width_cm"]'
    ).first
    width.click()
    width.press("Control+A")
    width.press_sequentially("41.2")
    width.press("Tab")
    page.wait_for_function(
        "() => {"
        " const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);"
        " return state && state.state === 'LOCAL_SAVED'"
        "   && state.saved_revision > 0"
        "   && state.saved_revision === state.recovery_revision;"
        "}",
        timeout=30_000,
    )
    trace("measurement_benchmark_initial_checkpoint_acknowledged")


def _benchmark_order(
    browser: Browser,
    fixture: dict[str, Any],
    name: str,
    count: int,
    variant: str,
    base_sha: str,
    deadline: float,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1800, "height": 1200})
    replaced: set[str] = set()
    phase_durations: dict[str, float] = {}
    phase = "login"
    if variant == "base":
        replaced = _install_base_metadata_overrides(context, base_sha)
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
        phase_started = time.monotonic()
        _login(page, fixture["editor"], fixture["password"])
        phase_durations["login"] = round(time.monotonic() - phase_started, 2)
        phase = "open_order"
        phase_started = time.monotonic()
        _open_order(page, name, count)
        phase_durations["open_order"] = round(time.monotonic() - phase_started, 2)
        if variant == "base":
            expected = _changed_base_files(base_sha)
            assert replaced == expected, (
                "Frappe DCO metadata did not supply changed base recovery assets; "
                f"expected={sorted(expected)}, matched={sorted(replaced)}"
            )
        phase = "edit_session_and_initial_checkpoint"
        phase_started = time.monotonic()
        _start_real_edit_session(page)
        _prime_checkpoint_with_real_measurement_edit(page)
        phase_durations["edit_session_and_initial_checkpoint"] = round(
            time.monotonic() - phase_started, 2
        )
        page.evaluate(
            """() => {
                const root = cur_frm.fields_dict.pieces_fast_entry.$wrapper.get(0);
                window.__al128KeyboardFrameSamples = [];
                window.__al128CheckpointSamples = [];
                window.__al128KeyboardAction = null;
                window.__al128AckAction = null;
                root.addEventListener("input", () => {
                    const keyboardAction = window.__al128KeyboardAction;
                    if (keyboardAction && !keyboardAction.started) {
                        keyboardAction.started = true;
                        const startedAt = performance.now();
                        requestAnimationFrame(() => requestAnimationFrame(() => {
                            window.__al128KeyboardFrameSamples.push(performance.now() - startedAt);
                        }));
                    }
                    const ackAction = window.__al128AckAction;
                    if (ackAction && !ackAction.started) {
                        ackAction.started = true;
                        ackAction.startedAt = performance.now();
                        const awaitCheckpoint = () => {
                            const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);
                            if (state && state.state === "LOCAL_SAVED"
                                && state.saved_revision > ackAction.savedRevision) {
                                window.__al128CheckpointSamples.push(
                                    performance.now() - ackAction.startedAt
                                );
                                ackAction.completed = true;
                                return;
                            }
                            setTimeout(awaitCheckpoint, 16);
                        };
                        setTimeout(awaitCheckpoint, 16);
                    }
                }, true);
            }"""
        )
        row = page.locator(
            '[data-fieldname="pieces_fast_entry"] .dco-fast-table '
            'tbody tr[data-row-name]:not(.dco-virtual-row)'
        ).first
        sample_count = 40
        width_control = row.locator('[data-field="width_cm"]')

        # Capture each input-to-paint sample independently, but wait for the
        # complete sample set only once. IndexedDB acknowledgement is measured
        # separately below, so per-sample Playwright polling adds no evidence.
        phase = "keyboard_ui_samples"
        phase_started = time.monotonic()
        for index in range(sample_count):
            page.evaluate("() => { window.__al128KeyboardAction = { started: false }; }")
            width_control.click()
            width_control.press("Control+A")
            width_control.press_sequentially(str(round(45 + (index % 20) / 10, 1)))
            width_control.press("Tab")
            page.evaluate("() => { window.__al128KeyboardAction = null; }")
        page.wait_for_function(
            "count => window.__al128KeyboardFrameSamples.length >= count",
            arg=sample_count,
            timeout=min(30_000, _remaining_benchmark_timeout_ms(deadline)),
        )
        phase_durations["keyboard_ui_samples"] = round(time.monotonic() - phase_started, 2)
        phase = "keyboard_ui_checkpoint_settle"
        phase_started = time.monotonic()
        page.wait_for_function(
            "() => {"
            " const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);"
            " return state && state.state === 'LOCAL_SAVED'"
            "   && state.saved_revision === state.recovery_revision;"
            "}",
            timeout=min(30_000, _remaining_benchmark_timeout_ms(deadline)),
        )
        phase_durations["keyboard_ui_checkpoint_settle"] = round(
            time.monotonic() - phase_started, 2
        )

        # Measure checkpoint acknowledgement separately, with enough independent
        # writes to report descriptive empirical P50/P95 values.
        phase = "checkpoint_ack_samples"
        phase_started = time.monotonic()
        for index in range(sample_count):
            phase = f"checkpoint_ack_sample_{index + 1}_of_{sample_count}"
            before = page.evaluate("() => window.__al128CheckpointSamples.length")
            page.evaluate(
                "() => {"
                " const state = AlmdinaDcoRecovery.LocalCheckpoint.snapshot(cur_frm);"
                " window.__al128AckAction = {"
                "   started: false, completed: false, savedRevision: state.saved_revision"
                " };"
                "}"
            )
            width_control.click()
            width_control.press("Control+A")
            width_control.press_sequentially(str(round(50 + (index % 20) / 10, 1)))
            width_control.press("Tab")
            page.wait_for_function(
                "count => window.__al128CheckpointSamples.length > count",
                arg=before,
                timeout=min(10_000, _remaining_benchmark_timeout_ms(deadline)),
            )
            page.evaluate("() => { window.__al128AckAction = null; }")
        phase_durations["checkpoint_ack_samples"] = round(time.monotonic() - phase_started, 2)

        samples = page.evaluate(
            "() => ({"
            " keyboard: window.__al128KeyboardFrameSamples.slice(-40),"
            " checkpoint: window.__al128CheckpointSamples.slice(-40)"
            "})"
        )
        frame_ms = samples["keyboard"]
        checkpoint_ms = samples["checkpoint"]
        assert len(frame_ms) == sample_count, (
            f"Expected {sample_count} key-to-paint samples, got {len(frame_ms)}"
        )
        assert len(checkpoint_ms) == sample_count
        assert not save_requests, "Measurement checkpoint unexpectedly invoked Official Save."
        if variant == "base":
            assert replaced == _changed_base_files(base_sha), "Changed Base metadata was not substituted"
        result = {
            "variant": variant,
            "rows": count,
            "keyboard_samples": len(frame_ms),
            "checkpoint_ack_samples": len(checkpoint_ms),
            "keyboard_response_and_checkpoint_ack_measured_separately": True,
            "input_samples": len(frame_ms),
            "keyboard_response_method": "first input event to second requestAnimationFrame",
            "input_to_second_animation_frame_ms": {
                "p50": _percentile(frame_ms, 0.50),
                "p95": _percentile(frame_ms, 0.95),
            },
            "checkpoint_ack_ms": {
                "p50": _percentile(checkpoint_ms, 0.50),
                "p95": _percentile(checkpoint_ms, 0.95),
            },
            "base_assets_replaced": sorted(replaced),
            "official_save_requests": len(save_requests),
            "phase_durations_seconds": phase_durations,
        }
        trace("measurement_entry_benchmark_completed", **result)
        _publish_benchmark_progress(result)
        return result
    except Exception as error:
        trace(
            "measurement_entry_benchmark_failed",
            variant=variant,
            rows=count,
            phase=phase,
            phase_durations_seconds=phase_durations,
            error=str(error)[:900],
        )
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as output:
                output.write(
                    f"\n### AL128 measurement benchmark — {count} pieces, {variant}: "
                    "NOT CERTIFIED\n\n"
                    f"- Failed phase: `{phase}`.\n"
                    f"- Time in failed phase: `{round(time.monotonic() - phase_started, 2)} s`.\n"
                    f"- Completed phase durations: `{json.dumps(phase_durations, sort_keys=True)}`\n"
                    f"- Error: `{str(error)[:700]}`\n"
                )
        try:
            page.screenshot(path=str(TRACE_PATH.parent / "al128-desk-failure.png"), timeout=5_000)
        except Exception:
            pass
        raise
    finally:
        context.close()


def test_actual_measurement_entry_performance_100_before_after() -> None:
    fixture = fixtures()
    base_sha = os.environ.get("AL128_BASE_SHA", "").strip()
    if not base_sha:
        pytest.fail("AL128_BASE_SHA is required to compare the pinned PR base and HEAD behavior.")
    subprocess.run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"], cwd=REPOSITORY, check=True)
    results = []
    benchmark_deadline = time.monotonic() + 8 * 60
    with sync_playwright() as playwright_instance:
        browser = _browser(playwright_instance)
        try:
            for count, fixture_key, variants in (
                (100, "performance_100", ("base", "head")),
            ):
                for variant in variants:
                    result = _benchmark_order(
                        browser,
                        fixture,
                        str(fixture[fixture_key]),
                        count,
                        variant,
                        base_sha,
                        benchmark_deadline,
                    )
                    results.append(result)
        finally:
            browser.close()

    by_rows = {
        count: {result["variant"]: result for result in results if result["rows"] == count}
        for count in (100,)
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
            for metric in ("input_to_second_animation_frame_ms", "checkpoint_ack_ms")
        }
    evidence = {
        "interaction_run": "PASS",
        "performance_rating": "NOT_ASSESSED_NO_ACCEPTANCE_THRESHOLD_DEFINED",
        "performance_metrics_are_comparative_evidence": True,
        "sample_method": "40 independent samples per metric, Base and HEAD, for each row count",
        "performance_test_budget_minutes": 10,
        "versions": fixture["versions"],
        "base_sha": base_sha,
        "benchmarks": results,
        "p95_comparison": comparisons,
        "source_files_identical": not _changed_base_files(base_sha),
        "interpretation": (
            "Baseline and HEAD recovery assets identical: these are same-code "
            "measurement samples, NOT evidence of a runtime optimization."
            if not _changed_base_files(base_sha)
            else "Baseline and HEAD contain changed recovery source assets."
        ),
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
            if any(
                result.get("test") == "real_desk_edit_checkpoint_permissions"
                for result in TEST_RESULTS
            ):
                output.write(
                    "\nSpecial manufacturing geometry mutation remains NOT TESTED: "
                    "the current Special Shape Desk control is documentation-only, "
                    "and `special_shape_geometry_json` has no supported editable control.\n"
                )
