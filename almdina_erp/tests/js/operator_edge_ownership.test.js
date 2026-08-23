"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

const registered = [];

global.window = {
    setTimeout,
    clearTimeout,
    requestAnimationFrame(callback) {
        callback();
        return 1;
    },
    AlmdinaMeasurementLifecycle: {
        schedule(_frm, _key, callback) {
            callback();
        },
    },
};

global.document = {
    activeElement: null,
    getElementById() { return null; },
    createElement() {
        return { id: "", textContent: "" };
    },
    head: { appendChild() {} },
};

global.frappe = {
    ui: {
        form: {
            on(doctype, handlers) {
                registered.push({ doctype, handlers });
            },
        },
    },
};

global.MutationObserver = class MutationObserver {
    constructor(callback) {
        this.callback = callback;
        this.disconnected = false;
    }
    observe() {}
    disconnect() { this.disconnected = true; }
};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_render_owner.js"
));

const keyboard = window.AlmdinaFastEntryKeyboardUX;
const owner = window.AlmdinaEdgeRenderOwner;

assert.ok(keyboard, "Fast-entry keyboard API must be installed");
assert.equal(Object.isFrozen(keyboard), true, "Fast-entry keyboard API must be immutable");
assert.equal(keyboard.normalizeQty("3.9"), 3);
assert.equal(keyboard.normalizeQty("0"), 1);
assert.equal(keyboard.normalizeQty("-4"), 1);
assert.equal(keyboard.normalizeQty("2,8"), 2);
assert.equal(keyboard.normalizeQty("abc"), 1);

assert.ok(owner, "Edge render owner API must be installed");
assert.equal(Object.isFrozen(owner), true, "Edge render owner API must be immutable");

let sideDisconnects = 0;
let profileDisconnects = 0;
const wrapper = {
    _dcoSideEdgeObserver: { disconnect() { sideDisconnects += 1; } },
    _dcoCompactEdgeProfileControlsObserver: { disconnect() { profileDisconnects += 1; } },
};
assert.equal(owner.disconnectLegacyObservers(wrapper), 2);
assert.equal(sideDisconnects, 1);
assert.equal(profileDisconnects, 1);
assert.equal(wrapper._dcoSideEdgeObserver, null);
assert.equal(wrapper._dcoCompactEdgeProfileControlsObserver, null);
assert.equal(owner.disconnectLegacyObservers(wrapper), 0, "Disconnect must be idempotent");

function node(matchesResult, queryResult = false) {
    return {
        nodeType: 1,
        matches() { return matchesResult; },
        querySelector() { return queryResult ? {} : null; },
    };
}

assert.equal(
    owner.structuralMeasurementMutation({ addedNodes: [node(true)], removedNodes: [] }),
    true,
    "Structural row/shell additions must trigger edge rendering"
);
assert.equal(
    owner.structuralMeasurementMutation({ addedNodes: [node(false, true)], removedNodes: [] }),
    true,
    "Nested measurement controls must trigger edge rendering"
);
assert.equal(
    owner.structuralMeasurementMutation({ addedNodes: [node(false, false)], removedNodes: [] }),
    false,
    "Pure decoration mutations must not trigger structural rerendering"
);

assert.ok(
    registered.some(entry => entry.doctype === "Door Cutting Order"),
    "Both focused owners must register against Door Cutting Order lifecycle"
);

console.log("Operator/edge ownership checks passed");
