"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const UX_SOURCE = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_final_price_approval_ux.js"
    ),
    "utf8"
);
const API_SOURCE = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_api.js"
    ),
    "utf8"
);
const REGISTRY_SOURCE = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js"
    ),
    "utf8"
);
const EDIT_SESSION_SOURCE = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_edit_session_ux.js"
    ),
    "utf8"
);
const PRESENTER_SOURCE = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_presenter.js"
    ),
    "utf8"
);
const AR_CSV = fs.readFileSync(
    path.resolve(__dirname, "../../translations/ar.csv"),
    "utf8"
);

function baseSnapshotData(overrides = {}) {
    return {
        price_approval_status: "Unapproved",
        current_price_approval: null,
        price_approval: null,
        price_basis_token: "1:abc123token",
        can_approve_final_price: true,
        can_cancel_final_price_approval: false,
        final_price_approval_blocker: null,
        final_price_cancellation_blocker: null,
        can_edit_cost_settings: true,
        invoice_preview_total_usd: 120,
        currency: "USD",
        ...overrides,
    };
}

function loadUx(options = {}) {
    const grants = new Set(options.grants || ["view_costs", "approve_final_price"]);
    const messages = [];
    const alerts = [];
    const approveCalls = [];
    const cancelCalls = [];
    const loadCalls = [];
    const commitCalls = [];
    const syncCalls = [];
    const dialogs = [];
    let generation = options.generation == null ? 1 : options.generation;
    let storeData = options.data === undefined ? baseSnapshotData() : options.data;
    let storeStatus = options.status || (storeData ? "ready" : "loading");
    let storeFreshness = options.freshness || "fresh";
    let storeEditing = Boolean(options.editing);
    let storeDirty = Boolean(options.dirty);
    let formDirty = Boolean(options.formDirty);
    let activeKind = options.activeKind || null;
    let approveImpl = options.approveImpl || null;
    let cancelImpl = options.cancelImpl || null;
    let reloadImpl = options.reloadImpl || null;
    let clickHandlers = 0;

    const panelHost = {
        outerHTML: "",
        setAttribute() {},
    };
    const card = {
        firstChild: null,
        children: [],
        appendChild(child) {
            this.children.push(child);
            return child;
        },
        querySelector(selector) {
            if (selector === "[data-price-approval-panel]") return panelHost;
            return null;
        },
    };
    const root = {
        querySelector(selector) {
            if (selector === ".dco-invoice-total-card") return card;
            return null;
        },
        contains() { return true; },
        addEventListener(type) {
            if (type === "click") clickHandlers += 1;
        },
    };
    const wrapper = {
        get() { return root; },
        0: root,
        querySelector: root.querySelector.bind(root),
    };

    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            name: options.orderName || "DCO-PRICE-1",
            docstatus: 0,
            status: "Draft",
            revision_state: "Current",
        },
        fields_dict: {
            order_cost_invoice_html: { $wrapper: wrapper },
            board_rate_usd: { df: {}, refresh() {} },
            cutting_cost_per_board_usd: { df: {}, refresh() {} },
            offcut_price_usd: { df: {}, refresh() {} },
        },
        is_new() { return false; },
        is_dirty() { return formDirty; },
        refresh_field() {},
    };

    class FakeDialog {
        constructor(config) {
            this.config = config;
            this.hidden = false;
            this.values = { approval_note: "" };
            this.fields_dict = {
                approval_note: {
                    $wrapper: {
                        length: 1,
                        find() { return [{ className: "", textContent: "", classList: { toggle() {} } }]; },
                        append() {},
                    },
                    $input: {
                        length: 1,
                        attr() { return this; },
                        on() { return this; },
                    },
                },
            };
            this.$wrapper = {
                addClass() { return this; },
                find() { return [{ textContent: "" }]; },
            };
            this._primaryDisabled = false;
            this._primaryLabel = config.primary_action_label;
            dialogs.push(this);
        }
        show() { this.hidden = false; }
        hide() {
            this.hidden = true;
            if (typeof this.onhide === "function") this.onhide();
        }
        get_value(field) { return this.values[field]; }
        set_value(field, value) { this.values[field] = value; }
        get_values() { return { ...this.values }; }
        get_primary_btn() {
            const self = this;
            return {
                prop(name, value) {
                    if (name === "disabled") self._primaryDisabled = value;
                    return this;
                },
                text(label) {
                    self._primaryLabel = label;
                    return this;
                },
            };
        }
        async runPrimary(values = {}) {
            Object.assign(this.values, values);
            return this.config.primary_action(this.values);
        }
        runSecondary() {
            if (typeof this.config.secondary_action === "function") {
                return this.config.secondary_action();
            }
            return this.hide();
        }
    }

    const fakeWindow = {
        cur_frm: frm,
        document: {
            getElementById() { return { id: "dco-final-price-approval-style" }; },
            createElement() {
                return {
                    id: "",
                    textContent: "",
                    classList: { toggle() {}, remove() {}, add() {} },
                    setAttribute() {},
                    remove() {},
                    querySelector() { return null; },
                    closest() { return null; },
                };
            },
            head: { appendChild() {} },
        },
        AlmdinaDocumentContext: {
            capture(target) {
                return Object.freeze({
                    identity: `Door Cutting Order::${target.doc.name}`,
                    generation,
                });
            },
            isCurrent(target, token) {
                return fakeWindow.cur_frm === target
                    && token
                    && token.generation === generation
                    && token.identity === `Door Cutting Order::${target.doc.name}`;
            },
        },
        AlmdinaPermissions: {
            canDocument(_frm, capability) { return grants.has(capability); },
            can(capability) { return grants.has(capability); },
        },
        AlmdinaDcoEditSessionCoordinator: {
            activeKind() { return activeKind; },
        },
        AlmdinaCostWorkspaceState: {
            snapshot() {
                return {
                    status: storeStatus,
                    freshness: storeFreshness,
                    editing: storeEditing,
                    dirty: storeDirty,
                    data: storeData,
                    draft: storeData ? {
                        board_rate_usd: 10,
                        cutting_cost_per_board_usd: 2,
                        offcut_price_usd: 0,
                    } : null,
                };
            },
            async load(_frm, opts) {
                loadCalls.push(opts || {});
                if (typeof reloadImpl === "function") {
                    return reloadImpl(opts);
                }
                storeStatus = "ready";
                storeFreshness = "fresh";
                return fakeWindow.AlmdinaCostWorkspaceState.snapshot(_frm);
            },
            commit(_frm, nextData) {
                commitCalls.push(nextData);
                storeData = nextData;
                storeStatus = "ready";
                return fakeWindow.AlmdinaCostWorkspaceState.snapshot(_frm);
            },
        },
        AlmdinaCostWorkspaceAPI: {
            async approveFinalPrice(orderName, token, note) {
                approveCalls.push({ orderName, token, note });
                if (typeof approveImpl === "function") {
                    return approveImpl(orderName, token, note);
                }
                return {
                    order_name: orderName,
                    price_approval_status: "Approved",
                    current_price_approval: "DCPA-1",
                    approved_amount_usd: 120,
                    currency: "USD",
                    cutting_plan: "PLAN-1",
                    approved_by: "finance@example.com",
                    approved_on: "2026-10-15 09:00:00",
                    approval_note: note || null,
                    fingerprint_formula_version: 1,
                    price_basis_token: token,
                };
            },
            async cancelFinalPriceApproval(orderName, expected) {
                cancelCalls.push({ orderName, expected });
                if (typeof cancelImpl === "function") {
                    return cancelImpl(orderName, expected);
                }
                return {
                    order_name: orderName,
                    price_approval_status: "Unapproved",
                    current_price_approval: null,
                    cancelled_approval: expected,
                    cancelled_now: true,
                    reason: "manual_price_approval_cancelled",
                    can_approve_final_price: true,
                    can_cancel_final_price_approval: false,
                    final_price_approval_invalidated: false,
                };
            },
        },
        AlmdinaCostEditSessionUX: {
            sync(target) { syncCalls.push(target.doc.name); },
        },
        AlmdinaWorkspaceKeepPaint: {
            presentationData(state) {
                if (!state) return null;
                if (state.status === "ready") return state.data;
                return state.data || null;
            },
        },
        AlmdinaLocale: {
            translate(message, replacements) {
                let text = String(message);
                if (Array.isArray(replacements)) {
                    replacements.forEach((value, index) => {
                        text = text.split(`{${index}}`).join(String(value));
                    });
                }
                return text;
            },
        },
        AlmdinaUi: {
            button({ variant, className, label, disabled, attrs }) {
                const attrHtml = Object.entries(attrs || {})
                    .map(([k, v]) => `${k}="${String(v)}"`)
                    .join(" ");
                return `<button class="btn alm-btn-${variant} ${className || ""}" ${disabled ? "disabled" : ""} ${attrHtml}>${label}</button>`;
            },
        },
    };

    const fakeFrappe = {
        msgprint(payload) { messages.push(payload); },
        show_alert(payload) { alerts.push(payload); },
        response: options.response || {},
        ui: { Dialog: FakeDialog },
        utils: {
            escape_html(value) {
                return String(value ?? "")
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;");
            },
        },
        datetime: {
            str_to_user(value) { return value; },
        },
    };
    fakeWindow.frappe = fakeFrappe;

    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        document: fakeWindow.document,
        console,
        Object,
        Array,
        Boolean,
        Number,
        String,
        Math,
        Promise,
        Error,
        setTimeout(callback) { callback(); return 1; },
        __: (value, replacements) => fakeWindow.AlmdinaLocale.translate(value, replacements),
    });
    vm.runInContext(UX_SOURCE, context);

    return {
        ux: fakeWindow.AlmdinaFinalPriceApprovalUX,
        frm,
        fakeWindow,
        fakeFrappe,
        messages,
        alerts,
        approveCalls,
        cancelCalls,
        loadCalls,
        commitCalls,
        syncCalls,
        dialogs,
        get clickHandlers() { return clickHandlers; },
        get panelHtml() { return panelHost.outerHTML; },
        setData(next) { storeData = next; },
        setStatus(next) { storeStatus = next; },
        setFreshness(next) { storeFreshness = next; },
        setEditing(next) { storeEditing = Boolean(next); },
        setDirty(next) { storeDirty = Boolean(next); },
        setFormDirty(next) { formDirty = Boolean(next); },
        setActiveKind(next) { activeKind = next; },
        setGeneration(next) { generation = next; },
        setApproveImpl(next) { approveImpl = next; },
        setCancelImpl(next) { cancelImpl = next; },
        setReloadImpl(next) { reloadImpl = next; },
        grants,
        async confirmApprove(note = "") {
            assert.equal(this.ux.approve(this.frm), true);
            assert.equal(this.dialogs.length >= 1, true);
            const dialog = this.dialogs[this.dialogs.length - 1];
            return dialog.runPrimary({ approval_note: note });
        },
        async confirmCancel() {
            assert.equal(this.ux.cancel(this.frm), true);
            assert.equal(this.dialogs.length >= 1, true);
            const dialog = this.dialogs[this.dialogs.length - 1];
            return dialog.runPrimary();
        },
    };
}

function assertNoTechnicalLeak(html) {
    assert.doesNotMatch(html, /price_basis_token|fingerprint|1:abc123token|DCPA-/i);
}

(async () => {
    // 1. Approve button only with approve capability
    {
        const none = loadUx({ grants: ["view_costs"] });
        none.ux.reconcile(none.frm);
        assert.doesNotMatch(none.panelHtml, /data-approve-final-price/);
        assert.equal(none.ux.approve(none.frm), false);

        const env = loadUx({ grants: ["view_costs", "approve_final_price"] });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /data-approve-final-price/);
        assert.equal(env.ux.approve(env.frm), true);
        assert.equal(env.dialogs.length, 1);
        assert.match(env.dialogs[0].config.title, /Approve final price/);
        assert.match(env.dialogs[0].config.primary_action_label, /Confirm approval/);
        assert.equal(env.approveCalls.length, 0);
    }

    // 2. Empty / Arabic multiline note approve
    {
        const env = loadUx();
        assert.equal(await env.confirmApprove(""), true);
        assert.equal(env.approveCalls[0].note, "");
        assert.equal(env.commitCalls[0].price_approval.approval_note, null);

        const ar = loadUx({ orderName: "DCO-NOTE" });
        const note = "ملاحظة\nسطر 2";
        assert.equal(await ar.confirmApprove(note), true);
        assert.equal(ar.approveCalls[0].note, note);
        assert.equal(ar.commitCalls[0].price_approval.approval_note, note);
    }

    // 3. Note length limit constant and counter wiring
    {
        assert.equal(loadUx().ux.NOTE_MAX, 500);
        assert.match(UX_SOURCE, /NOTE_MAX = 500/);
        assert.match(UX_SOURCE, /dco-approve-note-counter/);
        assert.match(API_SOURCE, /approval_note/);
    }

    // 4. Dismiss dialog without saving
    {
        const env = loadUx();
        assert.equal(env.ux.approve(env.frm), true);
        env.dialogs[0].runSecondary();
        assert.equal(env.approveCalls.length, 0);
        assert.equal(env.commitCalls.length, 0);
        assert.notEqual(env.frm.doc.price_approval_status, "Approved");
    }

    // 5. Unsaved changes block opening dialog
    {
        const env = loadUx();
        env.setFormDirty(true);
        assert.equal(env.ux.approve(env.frm), false);
        assert.equal(env.dialogs.length, 0);
        assert.equal(env.messages[0].title, "Unsaved changes");
    }

    // 6. Keep note on failure / stale token; no auto re-approve
    {
        const env = loadUx();
        env.setApproveImpl(async () => {
            throw new Error("The price basis changed since this page was loaded.");
        });
        env.setData(baseSnapshotData({
            price_basis_token: "1:newtoken",
            invoice_preview_total_usd: 130,
        }));
        assert.equal(env.ux.approve(env.frm), true);
        const dialog = env.dialogs[0];
        dialog.values.approval_note = "احتفظ بالملاحظة";
        const failed = await dialog.runPrimary({ approval_note: "احتفظ بالملاحظة" });
        assert.equal(failed, false);
        assert.equal(dialog.values.approval_note, "احتفظ بالملاحظة");
        assert.equal(env.commitCalls.length, 0);
        assert.equal(env.messages.some((m) => m.title === "Price changed"), true);
    }

    // 7. Stale response after navigation does not mutate other order
    {
        const env = loadUx({ orderName: "DCO-A" });
        let resolveApprove;
        env.setApproveImpl(() => new Promise((resolve) => {
            resolveApprove = resolve;
        }));
        assert.equal(env.ux.approve(env.frm), true);
        const pending = env.dialogs[0].runPrimary({ approval_note: "" });
        env.frm.doc.name = "DCO-B";
        env.fakeWindow.cur_frm = {
            doctype: "Door Cutting Order",
            doc: { name: "DCO-B" },
        };
        env.setGeneration(2);
        resolveApprove({
            order_name: "DCO-A",
            price_approval_status: "Approved",
            current_price_approval: "DCPA-OLD",
            price_basis_token: "1:abc123token",
        });
        assert.equal(await pending, false);
        assert.equal(env.commitCalls.length, 0);
    }

    // 8. Safe note display including HTML-like text
    {
        const env = loadUx({
            data: baseSnapshotData({
                price_approval_status: "Approved",
                can_approve_final_price: false,
                can_cancel_final_price_approval: false,
                price_approval: {
                    approved_by: "finance@example.com",
                    approved_on: "2026-10-15 09:00:00",
                    approval_note: "<script>alert(1)</script>\nسطر",
                },
            }),
        });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /Approval note/);
        assert.match(env.panelHtml, /&lt;script&gt;/);
        assert.doesNotMatch(env.panelHtml, /<script>alert/);
    }

    // 9. Cancel button for cancel capability only (even without approve)
    {
        const cancelOnly = loadUx({
            grants: ["view_costs", "cancel_final_price_approval"],
            data: baseSnapshotData({
                price_approval_status: "Approved",
                can_approve_final_price: false,
                can_cancel_final_price_approval: true,
                current_price_approval: "DCPA-9",
                price_approval: {
                    name: "DCPA-9",
                    approved_by: "a@x.com",
                    approved_on: "2026-10-15 09:00:00",
                    approval_note: "نص",
                },
            }),
        });
        cancelOnly.ux.reconcile(cancelOnly.frm);
        assert.match(cancelOnly.panelHtml, /data-cancel-final-price/);
        assert.doesNotMatch(cancelOnly.panelHtml, /data-approve-final-price/);

        const approveOnly = loadUx({
            grants: ["view_costs", "approve_final_price"],
            data: baseSnapshotData({
                price_approval_status: "Approved",
                can_approve_final_price: false,
                can_cancel_final_price_approval: false,
                current_price_approval: "DCPA-9",
                price_approval: {
                    name: "DCPA-9",
                    approved_by: "a@x.com",
                    approved_on: "2026-10-15 09:00:00",
                },
            }),
        });
        approveOnly.ux.reconcile(approveOnly.frm);
        assert.doesNotMatch(approveOnly.panelHtml, /data-cancel-final-price/);
        assert.equal(approveOnly.ux.cancel(approveOnly.frm), false);
    }

    // 10–12. Cancel sends reviewed approval id; success updates UI without lock
    {
        const env = loadUx({
            grants: ["view_costs", "cancel_final_price_approval", "edit_cost_settings"],
            data: baseSnapshotData({
                price_approval_status: "Approved",
                can_approve_final_price: false,
                can_cancel_final_price_approval: true,
                can_edit_cost_settings: true,
                current_price_approval: "DCPA-VIEWED",
                price_approval: {
                    name: "DCPA-VIEWED",
                    approved_by: "a@x.com",
                    approved_on: "2026-10-15 09:00:00",
                    approval_note: "قديمة",
                },
            }),
        });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /قديمة/);
        assert.equal(await env.confirmCancel(), true);
        assert.equal(env.cancelCalls[0].expected, "DCPA-VIEWED");
        assert.equal(env.commitCalls[0].price_approval_status, "Unapproved");
        assert.equal(env.commitCalls[0].price_approval, null);
        assert.equal(env.commitCalls[0].can_edit_cost_settings, true);
        assert.equal(env.alerts.some((a) => /Final price approval cancelled/i.test(a.message)), true);
        assert.equal(
            env.alerts.some((a) => /price approval for this order has been cancelled/i.test(a.message)),
            false
        );

        env.setData(baseSnapshotData({
            price_approval_status: "Unapproved",
            can_approve_final_price: true,
            can_cancel_final_price_approval: false,
            price_approval: null,
        }));
        env.ux.reconcile(env.frm);
        assert.doesNotMatch(env.panelHtml, /قديمة/);
        assert.doesNotMatch(env.panelHtml, /data-cancel-final-price/);
    }

    // 11. Newer-approval conflict does not auto-cancel again
    {
        const env = loadUx({
            grants: ["view_costs", "cancel_final_price_approval"],
            data: baseSnapshotData({
                price_approval_status: "Approved",
                can_cancel_final_price_approval: true,
                current_price_approval: "DCPA-OLD",
                price_approval: { name: "DCPA-OLD", approved_by: "a", approved_on: "x" },
            }),
        });
        env.setCancelImpl(async () => {
            throw new Error("The price approval changed since this page was loaded. Refresh and review before cancelling.");
        });
        assert.equal(await env.confirmCancel(), false);
        assert.equal(env.cancelCalls.length, 1);
        assert.equal(env.commitCalls.length, 0);
        assert.equal(env.loadCalls.length >= 1, true);
    }

    // 13. Bind once; busy blocks second open
    {
        const env = loadUx();
        env.ux.reconcile(env.frm);
        env.ux.reconcile(env.frm);
        assert.equal(env.clickHandlers, 1);
        let resolveApprove;
        env.setApproveImpl(() => new Promise((resolve) => {
            resolveApprove = resolve;
        }));
        assert.equal(env.ux.approve(env.frm), true);
        const pending = env.dialogs[0].runPrimary({ approval_note: "" });
        assert.equal(env.ux.approve(env.frm), false);
        resolveApprove({
            order_name: "DCO-PRICE-1",
            price_approval_status: "Approved",
            current_price_approval: "DCPA-1",
            price_basis_token: "1:abc123token",
        });
        assert.equal(await pending, true);
    }

    // 14. Sync does not mark form dirty
    {
        const env = loadUx();
        await env.confirmApprove("x");
        assert.equal(env.frm.is_dirty(), false);
    }

    // 15. Auto-invalidation toast still capability-gated and once
    {
        const env = loadUx({
            grants: ["view_costs", "approve_final_price"],
            data: baseSnapshotData({ price_approval_status: "Approved" }),
        });
        assert.equal(
            env.ux.consumeInvalidationSignal(env.frm, {
                final_price_approval_invalidated: true,
                order_name: "DCO-PRICE-1",
            }),
            true
        );
        assert.equal(env.alerts.length, 1);
        assert.equal(env.ux.notifyAutoInvalidation(env.frm, { signal: true }), false);
        assert.equal(env.alerts.length, 1);

        const none = loadUx({
            grants: ["view_costs", "edit_cost_settings"],
            orderName: "DCO-NONE",
        });
        assert.equal(
            none.ux.consumeInvalidationSignal(none.frm, {
                final_price_approval_invalidated: true,
                order_name: "DCO-NONE",
            }),
            false
        );
    }

    // 16. Total card order and API/registry wiring
    {
        assert.match(PRESENTER_SOURCE, /dco-price-approval-slot/);
        const end = PRESENTER_SOURCE.split("dco-invoice-total-end").slice(1).join("dco-invoice-total-end");
        assert.ok(end.indexOf("approvalSlot") < end.indexOf("${amount}"));
        assert.match(API_SOURCE, /cancel_order_final_price_approval/);
        assert.match(API_SOURCE, /cancelFinalPriceApproval/);
        assert.match(REGISTRY_SOURCE, /AlmdinaFinalPriceApprovalUX/);
        for (const key of [
            "Confirm approval",
            "Cancel final price approval",
            "Approval note",
            "Optional",
            "Show more",
            "Go back",
            "Final price approval cancelled",
        ]) {
            assert.ok(
                AR_CSV.includes(`${key},`) || AR_CSV.includes(`"${key}",`),
                `missing Arabic for ${key}`
            );
        }
    }

    // Edit session: approve alone never unlocks cost settings
    {
        const editGrants = new Set(["view_costs", "approve_final_price"]);
        const frm = {
            doctype: "Door Cutting Order",
            doc: {
                name: "DCO-LOCK-1",
                docstatus: 0,
                status: "Draft",
                revision_state: "Current",
            },
            fields_dict: {},
            is_new() { return false; },
            is_dirty() { return false; },
        };
        const snapshotData = baseSnapshotData({
            price_approval_status: "Approved",
            can_edit_cost_settings: false,
        });
        const fakeWindow = {
            cur_frm: frm,
            AlmdinaDocumentContext: {
                formIdentity(target) {
                    return `Door Cutting Order::${target.doc.name}`;
                },
                capture(target) {
                    return Object.freeze({
                        identity: `Door Cutting Order::${target.doc.name}`,
                        generation: 1,
                    });
                },
                isCurrent() { return true; },
                scheduleFrame(_t, _k, cb) { cb(); return 1; },
            },
            AlmdinaPermissions: {
                canDocument(_f, capability) { return editGrants.has(capability); },
                can(capability) { return editGrants.has(capability); },
            },
            AlmdinaWorkspaceStore: {
                forDocument() {
                    return {
                        snapshot() {
                            return {
                                status: "ready",
                                editing: false,
                                dirty: false,
                                data: snapshotData,
                                draft: null,
                            };
                        },
                    };
                },
            },
            AlmdinaCostWorkspaceState: {
                storeFor() {
                    return {
                        snapshot() {
                            return {
                                status: "ready",
                                editing: false,
                                dirty: false,
                                data: snapshotData,
                                draft: null,
                            };
                        },
                    };
                },
                snapshot() {
                    return {
                        status: "ready",
                        editing: false,
                        dirty: false,
                        data: snapshotData,
                        draft: null,
                    };
                },
                settings() { return {}; },
            },
            AlmdinaDcoEditSessionCoordinator: {
                register() {},
                begin() { return true; },
                end() {},
                activeKind() { return null; },
            },
            AlmdinaWorkspaceFieldEditor: {
                mount() {},
                unmount() {},
                focus() {},
            },
            addEventListener() {},
            dispatchEvent() {},
            requestAnimationFrame(cb) { cb(); return 1; },
        };
        const context = vm.createContext({
            window: fakeWindow,
            frappe: { msgprint() {}, ui: { form: { on() {} } } },
            console,
            Object,
            Array,
            Boolean,
            Number,
            String,
            Math,
            Promise,
            Error,
            setTimeout(cb) { cb(); return 1; },
            __: (v) => v,
        });
        vm.runInContext(EDIT_SESSION_SOURCE, context);
        assert.equal(fakeWindow.AlmdinaCostEditSessionUX.canEditCostSettings(frm), false);
    }

    console.log("Final price approval UX behavior simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
