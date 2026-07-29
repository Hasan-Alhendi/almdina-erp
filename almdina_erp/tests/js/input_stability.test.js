"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/input_stability.js"),
    "utf8"
);

const documentListeners = new Map();
const wrapperListeners = new Map();
const originalRefreshCalls = [];
const intervalHandlers = [];

const wrapper = {
    dataset: {},
    parentElement: null,
    contains(element) {
        let current = element;
        while (current) {
            if (current === this) return true;
            current = current.parentElement;
        }
        return false;
    },
    addEventListener(name, handler) {
        wrapperListeners.set(name, handler);
    },
};

const boardControl = {
    dataset: { fieldname: "board_description" },
    parentElement: wrapper,
};
const input = {
    tagName: "INPUT",
    disabled: false,
    readOnly: false,
    isContentEditable: false,
    dataset: {},
    parentElement: boardControl,
};
const body = { tagName: "BODY", parentElement: null };

function Form(name = "DCO-2026-00001") {
    this.doc = {
        doctype: "Door Cutting Order",
        name,
    };
    this.wrapper = wrapper;
    this.fields_dict = {
        board_description: {
            $wrapper: { get: () => boardControl },
        },
    };
}
Form.prototype.refresh_field = function refreshField(fieldname) {
    originalRefreshCalls.push(fieldname);
    return this;
};

function schedule_recalculate() {}
function safe_handler() {}

const fakeDocument = {
    body,
    activeElement: body,
    addEventListener(name, handler) {
        documentListeners.set(name, handler);
    },
};

const fakeFrappe = {
    call(options) {
        return options;
    },
    ui: {
        form: {
            Form,
            handlers: {
                "Door Cutting Order": {
                    board_description: [schedule_recalculate, safe_handler],
                },
                "Door Cutting Order Detail": {
                    notes: [schedule_recalculate, safe_handler],
                },
            },
        },
    },
};
const originalFrappeCall = fakeFrappe.call;

const fakeWindow = {
    frappe: fakeFrappe,
    cur_frm: null,
    setTimeout(handler) {
        handler();
        return 1;
    },
    setInterval(handler) {
        intervalHandlers.push(handler);
        return intervalHandlers.length;
    },
    clearInterval() {},
};

const context = vm.createContext({
    window: fakeWindow,
    document: fakeDocument,
    frappe: fakeFrappe,
    Date,
    Set,
    console,
});
vm.runInContext(source, context, { filename: "input_stability.js" });
intervalHandlers.forEach(handler => handler());

// Input stability no longer scans or mutates Frappe's private handler registry.
assert.deepEqual(
    fakeFrappe.ui.form.handlers["Door Cutting Order"].board_description,
    [schedule_recalculate, safe_handler]
);
assert.deepEqual(
    fakeFrappe.ui.form.handlers["Door Cutting Order Detail"].notes,
    [schedule_recalculate, safe_handler]
);
assert.equal(fakeFrappe.call, originalFrappeCall);

// Refreshing the field under the cursor must be deferred rather than rebuilding it.
const form = new Form();
fakeWindow.cur_frm = form;
fakeDocument.activeElement = input;
documentListeners.get("focusin")({ target: input });
form.refresh_field("board_description");
assert.deepEqual(originalRefreshCalls, []);
assert.equal(form._almdinaDeferredFieldRefreshes.has("board_description"), true);
assert.equal(input.dataset.almdinaFormIdentity, "Door Cutting Order::DCO-2026-00001");

// Once focus leaves the field, the queued refresh is safe to execute.
fakeDocument.activeElement = body;
wrapperListeners.get("focusout")({ target: input });
assert.deepEqual(originalRefreshCalls, ["board_description"]);
assert.equal(form._almdinaDeferredFieldRefreshes.size, 0);

// The same focused DOM node belongs to the old order after route navigation.
// It must not block the new order's refresh or leave its old values visible.
fakeDocument.activeElement = input;
documentListeners.get("focusin")({ target: input });
form.doc.name = "DCO-2026-00002";
form.refresh_field("board_description");
assert.deepEqual(originalRefreshCalls, ["board_description", "board_description"]);
assert.equal(form._almdinaDeferredFieldRefreshes.size, 0);
assert.equal(form._almdinaInputStabilityIdentity, "Door Cutting Order::DCO-2026-00002");

console.log("Input stability browser simulation passed");
