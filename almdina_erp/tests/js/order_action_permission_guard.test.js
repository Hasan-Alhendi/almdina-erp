"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order_action_permission_guard.js"),
    "utf8"
);

const handlers = {};
const rendererCalls = [];
const authorizedInvoice = () => "authorized-invoice";
const root = {
    querySelectorAll() { return []; },
    addEventListener() {},
    contains() { return true; },
};
const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-TEST", approved_plan: "" },
    wrapper: root,
    fields_dict: {},
};

const fakeWindow = {
    cur_frm: frm,
    AlmdinaPermissions: {
        canDocument() { return true; },
        can() { return true; },
    },
    AlmdinaDocumentContext: {
        canTuneCuttingAlgorithm() { return true; },
        canMutateCurrentStage() { return true; },
        scheduleFrame(_frm, _key, callback) { callback(); },
        schedule(_frm, _key, callback) { callback(); },
    },
    AlmdinaCuttingPlanRender: {
        print(targetFrm, planOverride) {
            rendererCalls.push({ targetFrm, planOverride });
            return true;
        },
    },
    AlmdinaPlanTabsUX: {
        printActivePlan() { return true; },
    },
    AlmdinaOrderDocumentPrint: {
        printInvoice() {},
        printAuthorizedInvoice: authorizedInvoice,
        printMeasurements() { return true; },
        html() { return "html"; },
    },
    addEventListener() {},
};

const fakeDocument = {
    documentElement: {},
    addEventListener() {},
};
class FakeMutationObserver {
    observe() {}
    disconnect() {}
}
const fakeFrappe = {
    ui: {
        form: {
            on(doctype, events) {
                assert.equal(doctype, "Door Cutting Order");
                Object.assign(handlers, events);
            },
        },
    },
    msgprint() {},
};

const context = vm.createContext({
    window: fakeWindow,
    document: fakeDocument,
    frappe: fakeFrappe,
    MutationObserver: FakeMutationObserver,
    requestAnimationFrame(callback) { callback(); },
    setTimeout(callback) { callback(); },
    console,
    Object,
    String,
    Boolean,
    Promise,
    __: value => value,
});
vm.runInContext(source, context, {
    filename: "door_cutting_order_action_permission_guard.js",
});

handlers.refresh(frm);

const override = { sheets: [{ source: "Approved" }] };
fakeWindow.AlmdinaCuttingPlanRender.print(frm, override);
assert.equal(rendererCalls.length, 1);
assert.equal(rendererCalls[0].targetFrm, frm);
assert.equal(rendererCalls[0].planOverride, override, "the permission wrapper must preserve the selected plan source");
assert.equal(
    fakeWindow.AlmdinaOrderDocumentPrint.printAuthorizedInvoice,
    authorizedInvoice,
    "the permission wrapper must preserve the server-authorized invoice presenter"
);

console.log("Order action permission guard preserves secure print contracts");
