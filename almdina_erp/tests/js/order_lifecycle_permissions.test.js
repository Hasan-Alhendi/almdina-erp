"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/order_lifecycle.js"),
    "utf8"
);
const planEditSource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js"
    ),
    "utf8"
);

function makeForm(name = "DCO-TEST-001", status = "Draft") {
    const added = [];
    const removed = [];
    return {
        doc: { name, status, docstatus: 0 },
        __almdina_lifecycle_context: null,
        added,
        removed,
        is_new() {
            return false;
        },
        add_custom_button(label, handler, group) {
            added.push({ label, handler, group });
        },
        remove_custom_button(label, group) {
            removed.push({ label, group });
            for (let i = added.length - 1; i >= 0; i -= 1) {
                const item = added[i];
                if (item.label !== label) continue;
                if (group !== undefined && item.group !== group) continue;
                added.splice(i, 1);
            }
        },
        reload_doc() {
            return Promise.resolve();
        },
    };
}

function load(capabilities, responseFactory) {
    const handlers = {};
    const calls = [];
    const alerts = [];
    const routes = [];
    const fakeWindow = {
        AlmdinaPermissions: {
            can(capability) {
                return capabilities.has(capability);
            },
        },
        AlmdinaDocumentContext: {
            capture(frm) {
                return { name: frm.doc.name };
            },
            isCurrent(frm, identity) {
                return frm.doc.name === identity.name;
            },
        },
    };
    const fakeFrappe = {
        almdina: {},
        ui: {
            form: {
                on(doctype, map) {
                    handlers[doctype] = map;
                },
            },
        },
        provide(namespace) {
            assert.equal(namespace, "frappe.almdina");
            this.almdina = this.almdina || {};
        },
        call(options) {
            calls.push(options);
            return Promise.resolve({ message: responseFactory(options) });
        },
        confirm(message, callback) {
            assert.ok(message);
            callback();
        },
        prompt(fields, callback) {
            assert.ok(fields.length);
            callback({ reason: "اختبار" });
        },
        show_alert(payload) {
            alerts.push(payload);
        },
        set_route(...args) {
            routes.push(args);
        },
    };

    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Number,
        String,
        Boolean,
        setTimeout,
        clearTimeout,
        __: value => value,
    });
    vm.runInContext(source, context, { filename: "order_lifecycle.js" });
    return {
        api: fakeWindow.AlmdinaOrderLifecycleUX,
        calls,
        alerts,
        routes,
        frappe: fakeFrappe,
        handlers,
    };
}

function loadPlanEditSession({ allowed = true } = {}) {
    const fakeWindow = {
        AlmdinaPermissions: {
            canDocument(_frm, capability) {
                return allowed && capability === "edit_optimizer_settings";
            },
        },
        AlmdinaPlanWorkspaceState: {
            storeFor(frm) {
                return {
                    snapshot() {
                        return {
                            status: "ready",
                            data: {
                                approved_plan: String(
                                    (frm && frm.doc && frm.doc.approved_plan) || ""
                                ),
                            },
                        };
                    },
                };
            },
        },
        addEventListener() {},
        requestAnimationFrame() {},
    };
    const fakeFrappe = {
        ui: {
            form: {
                on() {},
            },
        },
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Object,
        Set,
        String,
        Number,
        Boolean,
        Promise,
    });
    vm.runInContext(planEditSource, context, {
        filename: "door_cutting_order_plan_edit_session_ux.js",
    });
    return fakeWindow.AlmdinaPlanEditSessionUX;
}

function makePlanEditForm(overrides = {}) {
    return {
        doctype: "Door Cutting Order",
        is_new() {
            return false;
        },
        doc: {
            name: "DCO-2026-00005",
            docstatus: 0,
            approved_plan: null,
            revision_state: "Current",
            status: "At Drawing",
            production_path: "ROUTE-DRAWING",
            current_production_stage: null,
            ...overrides,
        },
    };
}

(async () => {
    const capabilities = new Set([
        "create_order",
        "edit_order",
        "submit_order",
        "approve_order",
        "return_order_to_draft",
        "cancel_order",
    ]);
    const lifecycle = {
        order_name: "DCO-TEST-001",
        editable: true,
        actions: {
            submit_for_review: { allowed: true },
            approve: { allowed: true },
            return_to_draft: { allowed: true },
            cancel: { allowed: false },
        },
    };
    const loaded = load(capabilities, options => {
        if (options.method.endsWith("get_order_lifecycle_context")) return lifecycle;
        if (options.method.endsWith("return_order_to_draft")) {
            return { name: "DCO-TEST-002", status: "Draft" };
        }
        return { name: "DCO-TEST-001" };
    });

    const editForm = makeForm();
    assert.equal(loaded.api.orderCanEdit(editForm), false);
    editForm.__almdina_edit_session = { active: true };
    assert.equal(loaded.api.orderCanEdit(editForm), true);

    const frm = makeForm("DCO-TEST-001", "At Drawing");
    await loaded.api.loadContext(frm);
    assert.equal(frm.__almdina_lifecycle_context.order_name, "DCO-TEST-001");
    assert.equal(loaded.api.orderCanEdit(frm), false);
    // Review/approve were retired. A non-draft order gets only the valid
    // standalone return action; draft never gets a meaningless return action.
    assert.deepEqual(
        frm.added.map(item => item.label).sort(),
        ["إعادة للمسودة"].sort()
    );
    assert.equal(
        frm.added.find(item => item.label === "إعادة للمسودة").group,
        undefined
    );
    assert.equal(
        loaded.calls[0].method,
        "almdina_erp.almdina_erp.services.order_lifecycle_permission_service.get_order_lifecycle_context"
    );
    loaded.api.installButtons(frm, lifecycle);
    assert.equal(
        frm.added.filter(item => item.label === "إعادة للمسودة").length,
        1,
        "reinstalling the same lifecycle state must not remove and recreate the action"
    );

    const returned = frm.added.find(item => item.label === "إعادة للمسودة");
    returned.handler();
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.ok(
        loaded.calls.some(call =>
            call.method.endsWith("order_revision_service.return_order_to_draft")
        )
    );
    assert.equal(loaded.routes.length, 0);

    const draftLoaded = load(capabilities, () => lifecycle);
    const draftForm = makeForm();
    await draftLoaded.api.loadContext(draftForm);
    assert.deepEqual(draftForm.added, []);

    const cancellableLifecycle = {
        ...lifecycle,
        actions: {
            ...lifecycle.actions,
            return_to_draft: { allowed: false },
            cancel: { allowed: true },
        },
    };
    const cancellable = load(capabilities, () => cancellableLifecycle);
    const cancellableForm = makeForm();
    await cancellable.api.loadContext(cancellableForm);
    assert.deepEqual(
        cancellableForm.added.map(item => ({ label: item.label, group: item.group })),
        [{ label: "إلغاء الطلب", group: undefined }]
    );
    cancellable.api.installButtons(cancellableForm, cancellableLifecycle);
    assert.equal(
        cancellableForm.added.filter(item => item.label === "إلغاء الطلب").length,
        1,
        "the cancel action must remain stable across repeated permission refreshes"
    );

    const denied = load(new Set(), () => lifecycle);
    const deniedForm = makeForm();
    deniedForm.__almdina_edit_session = { active: true };
    deniedForm.__almdina_lifecycle_context = lifecycle;
    assert.equal(denied.api.orderCanEdit(deniedForm), true);
    deniedForm.__almdina_lifecycle_context = null;
    assert.equal(denied.api.orderCanEdit(deniedForm), false);

    const stale = load(capabilities, () => ({ ...lifecycle, order_name: "DCO-OLD" }));
    const staleForm = makeForm("DCO-NEW");
    await stale.api.loadContext(staleForm);
    assert.equal(staleForm.__almdina_lifecycle_context, null);
    assert.deepEqual(staleForm.added, []);

    // Regression for DCO-2026-00005 from the real designer surface: an order at
    // `At Drawing` remains in an active routed lifecycle even when the form
    // snapshot does not expose current_production_stage. A previous approved
    // snapshot remains immutable, but it does not permanently lock preparation
    // of its replacement while the order is still at Drawing. Approved-plan
    // identity is supplied through PlanWorkspaceState, matching the A5.2 owner.
    const authorizedPlanEdit = loadPlanEditSession({ allowed: true });
    assert.equal(
        authorizedPlanEdit.canEditPlanSettings(makePlanEditForm()),
        true,
        "authorized designer at At Drawing must be able to start plan settings editing without a current stage snapshot"
    );
    assert.equal(
        authorizedPlanEdit.canEditPlanSettings(makePlanEditForm({ status: "Completed" })),
        false,
        "finished routed orders must remain locked when no active stage exists"
    );
    assert.equal(
        authorizedPlanEdit.canEditPlanSettings(
            makePlanEditForm({ approved_plan: "CP-APPROVED-001" })
        ),
        true,
        "an approved snapshot must not permanently lock plan settings while the order is still at Drawing"
    );
    assert.equal(
        authorizedPlanEdit.canEditPlanSettings(
            makePlanEditForm({
                approved_plan: "CP-APPROVED-001",
                status: "At CNC",
                current_production_stage: "STAGE-CNC",
            })
        ),
        false,
        "approved cutting plans must be locked after the order leaves Drawing"
    );

    const deniedPlanEdit = loadPlanEditSession({ allowed: false });
    assert.equal(
        deniedPlanEdit.canEditPlanSettings(makePlanEditForm()),
        false,
        "At Drawing must never bypass edit_optimizer_settings"
    );
    assert.equal(
        deniedPlanEdit.canEditPlanSettings(
            makePlanEditForm({ approved_plan: "CP-APPROVED-001" })
        ),
        false,
        "an approved plan at Drawing must still require edit_optimizer_settings"
    );

    console.log("Order lifecycle permission simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
