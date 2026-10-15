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
        final_price_approval_blocker: null,
        can_edit_cost_settings: true,
        invoice_preview_total_usd: 120,
        ...overrides,
    };
}

function loadUx(options = {}) {
    const grants = new Set(options.grants || ["view_costs", "approve_final_price"]);
    const messages = [];
    const approveCalls = [];
    const loadCalls = [];
    const commitCalls = [];
    const syncCalls = [];
    let generation = options.generation == null ? 1 : options.generation;
    let storeData = options.data === undefined ? baseSnapshotData() : options.data;
    let storeStatus = options.status || (storeData ? "ready" : "loading");
    let storeFreshness = options.freshness || "fresh";
    let storeEditing = Boolean(options.editing);
    let storeDirty = Boolean(options.dirty);
    let formDirty = Boolean(options.formDirty);
    let activeKind = options.activeKind || null;
    let approveImpl = options.approveImpl || null;
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
            if (selector === "[data-price-approval-panel]") {
                return panelHost.outerHTML.includes("data-price-approval-panel")
                    || panelHost.getAttribute
                    ? panelHost
                    : null;
            }
            return null;
        },
    };
    // Always expose a panel node so reconcile paints into it.
    card.querySelector = (selector) => {
        if (selector === "[data-price-approval-panel]") return panelHost;
        return null;
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
    };

    const fakeWindow = {
        cur_frm: frm,
        document: {
            getElementById() { return { id: "dco-final-price-approval-style" }; },
            createElement() {
                return { id: "", textContent: "", setAttribute() {} };
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
            canDocument(_frm, capability) {
                return grants.has(capability);
            },
            can(capability) {
                return grants.has(capability);
            },
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
            async approveFinalPrice(orderName, token) {
                approveCalls.push({ orderName, token });
                if (typeof approveImpl === "function") {
                    return approveImpl(orderName, token);
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
                    fingerprint_formula_version: 1,
                    price_basis_token: token,
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
    };

    const fakeFrappe = {
        msgprint(payload) { messages.push(payload); },
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
        messages,
        approveCalls,
        loadCalls,
        commitCalls,
        syncCalls,
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
        setReloadImpl(next) { reloadImpl = next; },
        grants,
    };
}

function assertNoTechnicalLeak(html) {
    assert.doesNotMatch(html, /price_basis_token|fingerprint|1:abc123token|DCPA-/i);
}

(async () => {
    // 1. No approve capability → no button
    {
        const env = loadUx({ grants: ["view_costs"] });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /Price approval status/);
        assert.match(env.panelHtml, /Unapproved/);
        assert.doesNotMatch(env.panelHtml, /data-approve-final-price/);
        assertNoTechnicalLeak(env.panelHtml);
    }

    // 2. Approve capability without edit_cost_settings / edit_order still shows button
    {
        const env = loadUx({
            grants: ["view_costs", "approve_final_price"],
        });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /data-approve-final-price/);
        assert.match(env.panelHtml, /alm-btn-primary/);
        assert.match(env.panelHtml, /aria-disabled="false"/);
        assert.doesNotMatch(env.panelHtml, /\sdisabled[\s>]/);
    }

    // 3. Incomplete price → disabled button + server blocker message
    {
        const env = loadUx({
            data: baseSnapshotData({
                can_approve_final_price: false,
                final_price_approval_blocker: {
                    code: "stale_cost_reference_plan",
                    message: "The cost-reference cutting plan is outdated. Recalculate and review the price first.",
                },
            }),
        });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /data-approve-final-price/);
        assert.match(env.panelHtml, /aria-disabled="true"/);
        assert.match(env.panelHtml, /outdated/);
        assert.doesNotMatch(env.panelHtml, /stale_cost_reference_plan/);
    }

    // 4. Unsaved changes in any workspace block approve
    {
        const env = loadUx();
        env.setFormDirty(true);
        const blockedForm = await env.ux.approve(env.frm);
        assert.equal(blockedForm, false);
        assert.equal(env.approveCalls.length, 0);
        assert.equal(env.messages[0].title, "Unsaved changes");

        env.setFormDirty(false);
        env.setActiveKind("cutting_plan");
        const blockedPlan = await env.ux.approve(env.frm);
        assert.equal(blockedPlan, false);
        assert.equal(env.approveCalls.length, 0);

        env.setActiveKind(null);
        env.setEditing(true);
        const blockedCost = await env.ux.approve(env.frm);
        assert.equal(blockedCost, false);
        assert.equal(env.approveCalls.length, 0);
    }

    // 5. Sends displayed token and blocks double-submit
    {
        const env = loadUx();
        let resolveApprove;
        env.setApproveImpl(() => new Promise((resolve) => {
            resolveApprove = resolve;
        }));
        const first = env.ux.approve(env.frm);
        // Second call while in-flight must no-op
        const second = await env.ux.approve(env.frm);
        assert.equal(second, false);
        assert.equal(env.approveCalls.length, 1);
        assert.equal(env.approveCalls[0].orderName, "DCO-PRICE-1");
        assert.equal(env.approveCalls[0].token, "1:abc123token");
        resolveApprove({
            order_name: "DCO-PRICE-1",
            price_approval_status: "Approved",
            current_price_approval: "DCPA-1",
            approved_by: "finance@example.com",
            approved_on: "2026-10-15 09:00:00",
            price_basis_token: "1:abc123token",
        });
        assert.equal(await first, true);
    }

    // 6. After success: badge Approved, lock note, no button; store updated without manual reload API
    {
        const env = loadUx();
        const ok = await env.ux.approve(env.frm);
        assert.equal(ok, true);
        assert.ok(env.commitCalls.length >= 1);
        assert.equal(env.commitCalls[0].price_approval_status, "Approved");
        assert.equal(env.commitCalls[0].can_edit_cost_settings, false);
        assert.equal(env.loadCalls.length, 1);
        assert.equal(env.loadCalls[0].force, true);
        assert.ok(env.syncCalls.includes("DCO-PRICE-1"));
        env.setData(baseSnapshotData({
            price_approval_status: "Approved",
            can_approve_final_price: false,
            can_edit_cost_settings: false,
            price_approval: {
                approved_by: "finance@example.com",
                approved_on: "2026-10-15 09:00:00",
            },
        }));
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /is-approved/);
        assert.match(env.panelHtml, /Approved by/);
        assert.match(env.panelHtml, /Cost settings are locked/);
        assert.doesNotMatch(env.panelHtml, /data-approve-final-price/);
        assertNoTechnicalLeak(env.panelHtml);
    }

    // 7. Stale token: reload snapshot, ask review, no auto re-approve
    {
        const env = loadUx();
        env.setApproveImpl(async () => {
            throw new Error("The price basis changed since this page was loaded.");
        });
        const failed = await env.ux.approve(env.frm);
        assert.equal(failed, false);
        assert.equal(env.approveCalls.length, 1);
        assert.equal(env.loadCalls.length, 1);
        assert.equal(env.messages.some((m) => m.title === "Price changed"), true);
    }

    // 8. Approve succeeds but reload fails → keep Approved merge, do not revert
    {
        const env = loadUx();
        env.setReloadImpl(async () => {
            throw new Error("network down");
        });
        const originalError = console.error;
        console.error = () => {};
        let ok;
        try {
            ok = await env.ux.approve(env.frm);
        } finally {
            console.error = originalError;
        }
        assert.equal(ok, true);
        assert.equal(env.commitCalls[0].price_approval_status, "Approved");
        assert.equal(
            env.messages.some((m) => m.title === "Final price approved"),
            true
        );
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /is-approved|Approved/);
    }

    // 9. After invalidation snapshot → Unapproved + button again
    {
        const env = loadUx({
            data: baseSnapshotData({
                price_approval_status: "Approved",
                can_approve_final_price: false,
                can_edit_cost_settings: false,
                price_approval: {
                    approved_by: "finance@example.com",
                    approved_on: "2026-10-15 09:00:00",
                },
            }),
        });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /is-approved/);
        env.setData(baseSnapshotData({
            price_approval_status: "Unapproved",
            can_approve_final_price: true,
            can_edit_cost_settings: true,
            price_approval: null,
        }));
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /is-unapproved/);
        assert.match(env.panelHtml, /data-approve-final-price/);
        assert.doesNotMatch(env.panelHtml, /Approved by/);
        assert.doesNotMatch(env.panelHtml, /Cost settings are locked/);
    }

    // 10. Non-impacting note save path: server still returns Approved → UI stays locked
    {
        const env = loadUx({
            data: baseSnapshotData({
                price_approval_status: "Approved",
                can_approve_final_price: false,
                can_edit_cost_settings: false,
                price_approval: {
                    approved_by: "finance@example.com",
                    approved_on: "2026-10-15 09:00:00",
                },
            }),
        });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /is-approved/);
        assert.doesNotMatch(env.panelHtml, /data-approve-final-price/);
    }

    // 11. Edit-session: settings locked by server while piece-price capability remains independent
    {
        const editGrants = new Set([
            "view_costs",
            "edit_cost_settings",
            "approve_special_price",
        ]);
        const frm = {
            doctype: "Door Cutting Order",
            doc: {
                name: "DCO-LOCK-1",
                docstatus: 0,
                status: "Draft",
                revision_state: "Current",
            },
            fields_dict: {
                board_rate_usd: { df: {}, refresh() {} },
                cutting_cost_per_board_usd: { df: {}, refresh() {} },
                offcut_price_usd: { df: {}, refresh() {} },
            },
            is_new() { return false; },
            is_dirty() { return false; },
            trigger() {},
        };
        let snapshotData = baseSnapshotData({
            price_approval_status: "Approved",
            can_edit_cost_settings: false,
            can_approve_final_price: false,
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
            frappe: {
                msgprint() {},
                ui: { form: { on() {} } },
            },
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
        const session = fakeWindow.AlmdinaCostEditSessionUX;
        assert.equal(session.canEditCostSettings(frm), false);
        assert.equal(session.canEditPiecePrices(frm), true);
        assert.equal(session.canEditCostWorkspace(frm), true);
        // Approve capability alone must not unlock settings
        editGrants.add("approve_final_price");
        editGrants.delete("edit_cost_settings");
        assert.equal(session.canEditCostSettings(frm), false);
    }

    // 12. Stale response after navigation must not mutate the other order
    {
        const env = loadUx({ orderName: "DCO-A" });
        let resolveApprove;
        env.setApproveImpl(() => new Promise((resolve) => {
            resolveApprove = resolve;
        }));
        const pending = env.ux.approve(env.frm);
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

    // 13. Bind once per cost root (no duplicate listeners)
    {
        const env = loadUx();
        env.ux.reconcile(env.frm);
        env.ux.reconcile(env.frm);
        env.ux.reconcile(env.frm);
        assert.equal(env.clickHandlers, 1);
    }

    // 14. i18n keys present; keep-last-paint disables actions while untrusted
    {
        for (const key of [
            "Price approval status",
            "Approve final price",
            "Approved",
            "Unapproved",
            "Cost settings are locked because the final price is approved.",
            "Save or cancel unsaved changes before approving the final price.",
            "The price basis changed. Review the total, then approve again.",
        ]) {
            assert.ok(
                AR_CSV.includes(`${key},`) || AR_CSV.includes(`"${key}",`),
                `missing Arabic translation for: ${key}`
            );
        }

        const env = loadUx({ freshness: "stale" });
        env.ux.reconcile(env.frm);
        assert.match(env.panelHtml, /aria-disabled="true"/);
        assert.equal(env.ux.actionsTrusted(env.frm), false);

        const loading = loadUx({ status: "loading", data: baseSnapshotData() });
        // Keep paint may still show prior badge text, but approve must refuse.
        assert.equal(await loading.ux.approve(loading.frm), false);
        assert.equal(loading.approveCalls.length, 0);
    }

    // API method wiring (approve uses freeze → legacy frappe.call)
    {
        const calls = [];
        const frappeRuntime = {
            call(request) {
                calls.push(request);
                request.callback({ message: { ok: true } });
            },
        };
        const context = vm.createContext({
            window: { frappe: frappeRuntime },
            frappe: frappeRuntime,
            Promise,
            Object,
            __: (v) => v,
        });
        vm.runInContext(API_SOURCE, context);
        const api = context.window.AlmdinaCostWorkspaceAPI;
        await api.approveFinalPrice("DCO-1", "1:token");
        assert.equal(
            calls[0].method,
            "almdina_erp.almdina_erp.services.final_price_approval_service.approve_order_final_price"
        );
        assert.equal(calls[0].args.order_name, "DCO-1");
        assert.equal(calls[0].args.expected_price_basis_token, "1:token");
        assert.equal(calls[0].freeze, true);
    }

    // Asset registry includes UX after edit session
    {
        const fakeWindow = { dispatchEvent() {} };
        const context = vm.createContext({
            window: fakeWindow,
            console,
            Promise,
            Object,
            Array,
            Map,
            Set,
            String,
            CustomEvent: class CustomEvent {
                constructor(type, options = {}) {
                    this.type = type;
                    this.detail = options.detail;
                }
            },
        });
        vm.runInContext(REGISTRY_SOURCE, context);
        const assets = Array.from(
            fakeWindow.AlmdinaDcoWorkspaceAssetRegistry.assetsFor("cost")
        );
        const approval = assets.find((a) => a.endsWith("door_cutting_order_final_price_approval_ux.js"));
        const editSession = assets.find((a) => a.endsWith("door_cutting_order_cost_edit_session_ux.js"));
        assert.ok(approval);
        assert.ok(editSession);
        assert.ok(assets.indexOf(approval) > assets.indexOf(editSession));
        assert.match(REGISTRY_SOURCE, /AlmdinaFinalPriceApprovalUX/);
    }

    // Presenter exposes approval slot beside total; panel HTML never paints technical ids
    {
        assert.match(PRESENTER_SOURCE, /data-price-approval-panel/);
        assert.match(PRESENTER_SOURCE, /dco-price-approval-slot/);
        const approvedEnv = loadUx({
            data: baseSnapshotData({
                price_approval_status: "Approved",
                can_approve_final_price: false,
                can_edit_cost_settings: false,
                price_basis_token: "1:secret-token-xyz",
                price_approval: {
                    name: "DCPA-HIDDEN",
                    approved_by: "finance@example.com",
                    approved_on: "2026-10-15 09:00:00",
                    fingerprint_formula_version: 1,
                },
            }),
        });
        approvedEnv.ux.reconcile(approvedEnv.frm);
        assertNoTechnicalLeak(approvedEnv.panelHtml);
        assert.doesNotMatch(approvedEnv.panelHtml, /secret-token|DCPA-HIDDEN|fingerprint/i);
    }

    console.log("Final price approval UX behavior simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
