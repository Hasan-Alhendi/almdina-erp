"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(
    __dirname, "../../public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js"
), "utf8");

let observer;
let primarySyncs = 0;
const frames = [];
const head = {
    isConnected: true,
    querySelector() { return null; },
    querySelectorAll() { return []; },
};
const frm = {
    doctype: "Door Cutting Order",
    fields_dict: {},
    _dco_presentation_head: head,
    remove_custom_button() {},
};
const windowObj = {
    AlmdinaDocumentContext: {
        scheduleFrame(_frm, _key, callback) { frames.push(callback); },
    },
    AlmdinaOrderRevisionUX: {
        syncPrimaryAction() {
            primarySyncs += 1;
            assert.ok(primarySyncs < 5, "observed primary-action changes must not recurse");
            observer.callback(); // Frappe rebuilds the button while we reconcile it.
        },
    },
    addEventListener() {},
    innerWidth: 1024,
};
vm.runInNewContext(source, {
    window: windowObj,
    document: {},
    MutationObserver: class {
        constructor(callback) { this.callback = callback; observer = this; }
        observe() {}
        disconnect() {}
    },
    __: message => message,
}, { filename: "door_cutting_order_toolbar_stability_ux.js" });

assert.equal(windowObj.AlmdinaDcoToolbarStabilityUx.recoverPresentation(frm, head), true);
observer.callback();
observer.callback();
assert.equal(primarySyncs, 0, "a DOM mutation must not update observed DOM synchronously");
assert.equal(frames.length, 1, "mutations in one turn share an animation frame");
frames.shift()();
assert.equal(primarySyncs, 1);
assert.equal(frames.length, 1, "feedback from the primary action waits for another frame");
console.log("DCO toolbar observer frame regression passed");
