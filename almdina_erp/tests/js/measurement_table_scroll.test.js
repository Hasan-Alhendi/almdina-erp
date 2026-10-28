"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../");
const operatorPath = path.join(
    root,
    "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"
);
const keyboardPath = path.join(
    root,
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js"
);
const resiliencePath = path.join(
    root,
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_resilience_ux.js"
);
const actionsPath = path.join(
    root,
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js"
);

const formHandlers = {};
const window = {};
const sandbox = {
    window,
    document: {},
    frappe: {
        ui: { form: { on(doctype, handlers) { formHandlers[doctype] = handlers; } } },
        utils: { escape_html(value) { return String(value); } },
    },
    __: (message) => String(message),
    Object,
    String,
    Number,
    Boolean,
    Promise,
    Set,
    Map,
    console,
};
window.frappe = sandbox.frappe;
vm.runInNewContext(fs.readFileSync(operatorPath, "utf8"), sandbox, { filename: operatorPath });

const reveal = window.AlmdinaDoorCuttingFastEntry.revealInMeasurementTable;
assert.equal(typeof reveal, "function");

function box(top, height, left = 0, width = 200) {
    return {
        top,
        bottom: top + height,
        left,
        right: left + width,
        height,
        width,
    };
}

function node(tag, rect) {
    const element = {
        tagName: String(tag).toUpperCase(),
        parentElement: null,
        className: "",
        scrollTop: 0,
        scrollLeft: 40,
        children: [],
        querySelector(selector) {
            if (selector === ".dco-fast-table thead") {
                return this._thead || null;
            }
            return null;
        },
        closest(selector) {
            let current = this;
            while (current) {
                if (selector === ".dco-fast-entry-scroll" && current.className.includes("dco-fast-entry-scroll")) {
                    return current;
                }
                if (selector === "tr[data-row-name]" && current.tagName === "TR") {
                    return current;
                }
                current = current.parentElement;
            }
            return null;
        },
        getBoundingClientRect() {
            return this._rect;
        },
    };
    element._rect = rect;
    return element;
}

const scroller = node("div", box(0, 100));
scroller.className = "dco-fast-entry-scroll";
const thead = node("thead", box(0, 20));
scroller._thead = thead;
const visible = node("tr", box(30, 40));
visible.parentElement = scroller;
assert.equal(reveal(visible), false);
assert.equal(scroller.scrollTop, 0);
assert.equal(scroller.scrollLeft, 40);

const below = node("tr", box(90, 40));
below.parentElement = scroller;
assert.equal(reveal(below), true);
assert.equal(scroller.scrollTop, 30);
assert.equal(scroller.scrollLeft, 40);

scroller.scrollTop = 80;
const above = node("tr", box(5, 30));
above.parentElement = scroller;
assert.equal(reveal(above), true);
assert.equal(scroller.scrollTop, 65);
assert.equal(scroller.scrollLeft, 40);

const operatorSource = fs.readFileSync(operatorPath, "utf8");
assert.match(operatorSource, /function revealInMeasurementTable\(target\)/);
assert.match(operatorSource, /revealInMeasurementTable\(next\)/);
assert.doesNotMatch(
    operatorSource.split("function moveToNextWidth")[1].split("function applyCornerEdgeCheck")[0],
    /scrollIntoView/
);
assert.match(operatorSource, /document\.activeElement === input/);
assert.match(operatorSource, /revealInMeasurementTable\(input\)/);

const keyboardSource = fs.readFileSync(keyboardPath, "utf8");
assert.match(keyboardSource, /revealInMeasurementTable/);
assert.doesNotMatch(keyboardSource, /scrollIntoView/);

const resilienceSource = fs.readFileSync(resiliencePath, "utf8");
assert.match(resilienceSource, /overscroll-behavior-x:contain/);
assert.match(resilienceSource, /overscroll-behavior-y:auto/);
assert.match(resilienceSource, /\.dco-entry-window-host \.dco-fast-entry-scroll \{[\s\S]*overscroll-behavior:contain/);
assert.doesNotMatch(resilienceSource, /overscroll-behavior:contain;\s*overflow-anchor/);

const actionsSource = fs.readFileSync(actionsPath, "utf8");
assert.match(actionsSource, /body\.dco-measurement-entry-open\{overflow:hidden!important\}/);
assert.match(actionsSource, /dco-entry-window-host \.dco-fast-entry-scroll\{[^}]*overscroll-behavior:contain/);

console.log("measurement table scroll tests passed");
