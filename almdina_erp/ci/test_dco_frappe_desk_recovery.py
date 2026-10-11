from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import Page, expect


DESK_URL = os.environ["FRAPPE_DESK_URL"].rstrip("/")
FIXTURES = json.loads(Path(os.environ["DCO_DESK_FIXTURE_FILE"]).read_text(encoding="utf-8"))


def open_dco(page: Page, name: str) -> None:
    page.goto(f"{DESK_URL}/app/door-cutting-order/{name}", wait_until="domcontentloaded")
    page.wait_for_function(
        "name => window.cur_frm && window.cur_frm.doc && window.cur_frm.doc.name === name",
        arg=name,
        timeout=60_000,
    )


def start_edit_and_set_note(page: Page, name: str, value: str, checkpoint: bool) -> dict:
    return page.evaluate(
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
            const found = await recovery.repository().discover({mode: 'EDIT', target_name: name});
            if (!found || !found.ok || !found.value.records.length) {
                throw new Error('IndexedDB EDIT snapshot was not readable');
            }
            return {started, dirty: frm.is_dirty(), draftId: found.value.records[0].draft_id};
        }""",
        {"name": name, "value": value, "checkpoint": checkpoint},
    )


def test_actual_frappe_desk_edit_recovery_boundary(page: Page) -> None:
    page.goto(DESK_URL)
    if page.locator("#login_email").count():
        page.locator("#login_email").fill("Administrator")
        page.locator("#login_password").fill("admin")
        page.locator("button[type='submit']").click()
        page.wait_for_function(
            "() => window.frappe && frappe.session && frappe.session.user === 'Administrator'",
            timeout=60_000,
        )

    # A route selected on a Draft is not dispatch. Exercise the real edit-session
    # Cancel and Save adapters, and the real IndexedDB restore dialog.
    name = FIXTURES["restore"]
    baseline = page.request.get(
        f"{DESK_URL}/api/method/frappe.client.get?doctype=Door%20Cutting%20Order&name={name}"
    ).json()["message"]["order_notes"]
    open_dco(page, name)
    cancelled = "Desk cancel must not persist"
    start_edit_and_set_note(page, name, cancelled, checkpoint=False)
    page.evaluate("() => window.AlmdinaDcoEditSessionCoordinator.cancel(window.cur_frm, 'order')")
    page.wait_for_function(
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
    page.wait_for_function(
        "value => window.cur_frm && window.cur_frm.doc.order_notes === value && "
        "window.cur_frm.is_dirty() && "
        "window.AlmdinaDcoEditSessionCoordinator.isEditing(window.cur_frm, 'order')",
        arg=recovered,
        timeout=30_000,
    )
    page.evaluate("() => window.AlmdinaOrderRevisionUX.commitEditSession(window.cur_frm)")
    page.wait_for_function(
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
    dispatch_baseline = page.evaluate("() => window.cur_frm.doc.order_notes")
    start_edit_and_set_note(page, dispatch_name, "Must remain local after dispatch", checkpoint=True)
    page.evaluate(
        """async ({name, route}) => {
            await frappe.xcall('almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order', {
                order_name: name, path: route, assignee: 'Administrator'
            });
        }""",
        {"name": dispatch_name, "route": FIXTURES["route"]},
    )
    open_dco(page, dispatch_name)
    page.wait_for_function("() => Boolean(window.cur_frm.doc.current_production_stage)")
    expect(page.locator("body")).to_contain_text("لا يمكن استعادتها بعد بدء مرحلة الإنتاج")
    expect(page.locator('[data-edit-recovery-action="continue"]')).to_have_count(0)
    retained = page.evaluate(
        """async name => {
            const result = await window.AlmdinaDcoRecovery.LocalCheckpoint.repository()
                .discover({mode: 'EDIT', target_name: name});
            return Boolean(result && result.ok && result.value.records.length);
        }""",
        dispatch_name,
    )
    assert retained, "Dispatch must retain the old local snapshot without offering restoration"

    direct_save_rejected = page.evaluate(
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

    page.evaluate(
        """async name => frappe.xcall(
            'almdina_erp.almdina_erp.services.order_lifecycle_service.return_order_to_draft',
            {order_name: name, reason: 'Desk recovery lifecycle certification'}
        )""",
        dispatch_name,
    )
    open_dco(page, dispatch_name)
    page.wait_for_function("() => window.cur_frm.doc.status === 'Draft'")
    assert page.evaluate("() => window.cur_frm.doc.order_notes") == dispatch_baseline
    page.wait_for_selector('[data-edit-recovery-action="continue"]', timeout=30_000)
    # Continue is explicit after Return-to-Draft; a changed official modified
    # value must produce a conflict without applying any recovered field.
    page.locator('[data-edit-recovery-action="continue"]').click()
    expect(page.locator("body")).to_contain_text("تغير الطلب على الخادم")
    assert page.evaluate("() => window.cur_frm.doc.order_notes") == dispatch_baseline
