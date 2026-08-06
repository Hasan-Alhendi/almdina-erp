"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/order_lifecycle.js"),
    "utf8"
);

function makeForm(name = "DCO-TEST-001") {
    const added = [];
    const removed = [];
    return {
        doc: { name, status: "Pending Review", docstatus: 0 },
        __almdina_lifecycle_context: null,
        __almdina_edit_session: null,
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
            submit_for_review: { allowed: false },
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

    const frm = makeForm();
    assert.equal(loaded.api.orderCanEdit(frm), false);
    frm.__almdina_edit_session = { active: true };
    assert.equal(loaded.api.orderCanEdit(frm), true);
    await loaded.api.loadContext(frm);
    assert.equal(frm.__almdina_lifecycle_context.order_name, "DCO-TEST-001");
    assert.deepEqual(
        frm.added.map(item => item.label).sort(),
        ["اعتماد الطلب", "إعادة للمسودة"].sort()
    );
    assert.equal(
        loaded.calls[0].method,
        "almdina_erp.almdina_erp.services.order_lifecycle_permission_service.get_order_lifecycle_context"
    );

    const approve = frm.added.find(item => item.label === "اعتماد الطلب");
    approve.handler();
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.ok(
        loaded.calls.some(call =>
            call.method.endsWith("order_approval_service.approve_order")
        )
    );

    const returned = frm.added.find(item => item.label === "إعادة للمسودة");
    returned.handler();
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.ok(
        loaded.calls.some(call =>
            call.method.endsWith("order_revision_service.return_order_to_draft")
        )
    );
    assert.deepEqual(loaded.routes.at(-1), ["Form", "Door Cutting Order", "DCO-TEST-002"]);

    const denied = load(new Set(), () => lifecycle);
    const deniedForm = makeForm();
    deniedForm.__almdina_lifecycle_context = lifecycle;
    deniedForm.__almdina_edit_session = { active: true };
    assert.equal(denied.api.orderCanEdit(deniedForm), true);
    deniedForm.__almdina_lifecycle_context = null;
    assert.equal(denied.api.orderCanEdit(deniedForm), false);

    const stale = load(capabilities, () => ({ ...lifecycle, order_name: "DCO-OLD" }));
    const staleForm = makeForm("DCO-NEW");
    await stale.api.loadContext(staleForm);
    assert.equal(staleForm.__almdina_lifecycle_context, null);
    assert.equal(staleForm.added.length, 0);

    console.log("Order lifecycle permission simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
