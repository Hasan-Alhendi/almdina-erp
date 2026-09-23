"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(filename) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", filename), "utf8");
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

function jqueryThenable(promise) {
    return {
        then(onFulfilled, onRejected) {
            return jqueryThenable(promise.then(onFulfilled, onRejected));
        },
        catch(onRejected) {
            return jqueryThenable(promise.catch(onRejected));
        },
    };
}

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}

function loadProductionUx({ userInfo = {}, getValue } = {}) {
    const fakeWindow = {
        cur_frm: null,
        AlmdinaPermissions: {
            canDocument() { return false; },
            can() { return false; },
            profile() { return "admin"; },
        },
        AlmdinaDocumentContext: {
            capture(frm) {
                return `${frm.doctype}::${frm.doc.name}`;
            },
            isCurrent() { return true; },
        },
        addEventListener() {},
        setTimeout() { return 1; },
    };
    const fakeFrappe = {
        almdina: {},
        session: { user: "manager@example.com" },
        boot: { user_info: userInfo },
        utils: { escape_html: value => String(value) },
        user_info(id) {
            return (this.boot.user_info || {})[id] || {};
        },
        update_user_info(map) {
            this.boot.user_info = Object.assign({}, this.boot.user_info || {}, map);
        },
        db: {
            get_value(doctype, name, field) {
                if (typeof getValue === "function") {
                    return jqueryThenable(Promise.resolve(getValue({ doctype, name, field })));
                }
                return jqueryThenable(Promise.resolve({ message: {} }));
            },
        },
        ui: {
            Dialog: class FakeDialog {
                constructor(config) {
                    this.config = config;
                    this.fields_dict = {
                        route_preview: { $wrapper: { html() {} } },
                    };
                    fakeWindow.__dialog = this;
                }
                show() {}
                hide() {}
                get_value() { return ""; }
                set_value() {}
                set_df_property() {}
            },
            form: {
                on() {},
            },
        },
        provide() {},
        show_alert() {},
        msgprint() {},
        call() {
            return jqueryThenable(Promise.resolve({ message: {} }));
        },
        prompt() {},
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Set,
        Map,
        String,
        Number,
        Boolean,
        Array,
        __: value => value,
    });
    vm.runInContext(
        source("door_cutting_order/production/shop_floor_order_ux.js"),
        context
    );
    return { fakeWindow, fakeFrappe };
}

function trackingFrm(htmlHolder, doc) {
    const wrapper = {
        htmlContent: "",
        children: { length: 0 },
        empty() {
            this.htmlContent = "";
            this.children.length = 0;
            return this;
        },
        html(value) {
            this.htmlContent = value;
            this.children.length = 1;
            return this;
        },
        get() {
            return htmlHolder;
        },
    };
    return {
        doctype: "Door Cutting Order",
        doc,
        fields_dict: { operator_status_strip: { $wrapper: wrapper } },
        is_new() { return false; },
    };
}

async function verifyTrackingStripShowsFullNameFromBoot() {
    const { fakeWindow } = loadProductionUx({
        userInfo: {
            "cutting@example.com": { fullname: "أحمد القص", email: "cutting@example.com" },
        },
    });
    const htmlHolder = {};
    const frm = trackingFrm(htmlHolder, {
        name: "DCO-1",
        status: "At CNC",
        current_department: "CNC",
        current_assignee: "cutting@example.com",
        department_status: "قيد العمل",
        production_path: "Drawing",
    });
    fakeWindow.AlmdinaShopFloorOrderUX.renderTrackingStrip(frm);
    const html = frm.fields_dict.operator_status_strip.$wrapper.htmlContent;
    assert.match(html, /أحمد القص/);
    assert.doesNotMatch(html, /cutting@example.com/);
}

async function verifyTrackingStripHydratesMissingFullName() {
    const pending = deferred();
    const { fakeWindow, fakeFrappe } = loadProductionUx({
        getValue() {
            return pending.promise;
        },
    });
    const htmlHolder = {};
    const frm = trackingFrm(htmlHolder, {
        name: "DCO-2",
        status: "At Drawing",
        current_department: "رسم",
        current_assignee: "designer@example.com",
        department_status: "بحاجة للعمل",
        production_path: "Drawing",
    });
    fakeWindow.AlmdinaShopFloorOrderUX.renderTrackingStrip(frm);
    assert.match(
        frm.fields_dict.operator_status_strip.$wrapper.htmlContent,
        /designer@example.com/
    );

    pending.resolve({ message: { full_name: "سارة الرسم" } });
    await flushPromises();
    const html = frm.fields_dict.operator_status_strip.$wrapper.htmlContent;
    assert.match(html, /سارة الرسم/);
    assert.doesNotMatch(html, /designer@example.com/);
    assert.equal(
        fakeFrappe.user_info("designer@example.com").fullname,
        "سارة الرسم"
    );
}

async function verifyDispatchPickerUsesNameOnly() {
    const pending = deferred();
    const { fakeWindow, fakeFrappe } = loadProductionUx();
    fakeFrappe.call = function call() {
        return jqueryThenable(pending.promise);
    };
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-3", status: "Draft" },
        fields_dict: {},
        is_new() { return false; },
        reload_doc() { return Promise.resolve(); },
    };
    fakeFrappe.almdina.open_dispatch_dialog(frm);
    pending.resolve({
        message: {
            default_path: "Drawing",
            paths: [{
                value: "Drawing",
                label: "Drawing",
                stages: [{ department: "رسم", stage_type: "Drawing", operational_role: "عامل رسم" }],
            }],
            workers: {
                Drawing: [{ name: "cnc@example.com", full_name: "باسم CNC" }],
            },
        },
    });
    await flushPromises();
    const assignee = fakeWindow.__dialog.config.fields.find(field => field.fieldname === "assignee");
    assert.equal(assignee.options[0].label, "باسم CNC");
    assert.equal(assignee.options[0].value, "cnc@example.com");
    assert.equal(String(assignee.options[0].label).includes("@"), false);
}

(async () => {
    await verifyTrackingStripShowsFullNameFromBoot();
    await verifyTrackingStripHydratesMissingFullName();
    await verifyDispatchPickerUsesNameOnly();
    console.log("Shop-floor worker display simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
