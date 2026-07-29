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
let capturedCallOptions = null;

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
    parentElement: boardControl,
};
const body = { tagName: "BODY", parentElement: null };

function Form() {
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
        capturedCallOptions = options;
        return { then() { return this; } };
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

const fakeWindow = {
    frappe: fakeFrappe,
    cur_frm: null,
    setTimeout(handler) {
        handler();
        return 1;
    },
    setInterval(handler) {
        handler();
        return 1;
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

// Old automatic preview handlers are removed, while unrelated handlers remain.
assert.deepEqual(
    fakeFrappe.ui.form.handlers["Door Cutting Order"].board_description,
    [safe_handler]
);
assert.deepEqual(
    fakeFrappe.ui.form.handlers["Door Cutting Order Detail"].notes,
    [safe_handler]
);

// Refreshing the field under the cursor must be deferred rather than rebuilding it.
const form = new Form();
fakeWindow.cur_frm = form;
fakeDocument.activeElement = input;
form.refresh_field("board_description");
assert.deepEqual(originalRefreshCalls, []);
assert.equal(form._almdinaDeferredFieldRefreshes.has("board_description"), true);

// Once focus leaves the field, the queued refresh is safe to execute.
fakeDocument.activeElement = body;
wrapperListeners.get("focusout")({ target: input });
assert.deepEqual(originalRefreshCalls, ["board_description"]);
assert.equal(form._almdinaDeferredFieldRefreshes.size, 0);

// A server preview that started before newer typing must never call the legacy
// callback that writes old input values back into the form.
let callbackApplied = false;
fakeDocument.activeElement = body;
fakeFrappe.call({
    method: "almdina_erp.almdina_erp.api.preview_door_cutting_order",
    callback() {
        callbackApplied = true;
    },
});
assert.ok(capturedCallOptions);
documentListeners.get("beforeinput")({ target: input });
capturedCallOptions.callback({ message: { board_description: "old" } });
assert.equal(callbackApplied, false);

// Even without a newer generation, a response is not applied while the operator
// is actively editing a control inside the form.
callbackApplied = false;
fakeDocument.activeElement = input;
fakeFrappe.call({
    method: "almdina_erp.almdina_erp.api.preview_door_cutting_order",
    callback() {
        callbackApplied = true;
    },
});
capturedCallOptions.callback({ message: { board_description: "old" } });
assert.equal(callbackApplied, false);

// A current response is still allowed when no field is being edited.
callbackApplied = false;
fakeDocument.activeElement = body;
fakeFrappe.call({
    method: "almdina_erp.almdina_erp.api.preview_door_cutting_order",
    callback() {
        callbackApplied = true;
    },
});
capturedCallOptions.callback({ message: {} });
assert.equal(callbackApplied, true);

console.log("Input stability browser simulation passed");
