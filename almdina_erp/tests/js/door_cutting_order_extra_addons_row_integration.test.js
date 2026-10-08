"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", relativePath), "utf8");
}

const triggered = [];
const fakeWindow = {};
const checkbox = { checked:false, disabled:false, dataset:{} };
const selectorCell = {
    querySelector(selector) {
        return selector === "input.dco-row-selector" ? checkbox : null;
    },
    appendChild() {},
    replaceChildren() {},
};
const classes = new Set();
const tr = {
    dataset:{rowName:"ROW-1"},
    classList:{
        contains(name) { return classes.has(name); },
        toggle(name, enabled) {
            if (enabled) classes.add(name);
            else classes.delete(name);
        },
    },
    querySelector(selector) {
        if (selector === ":scope > td.dco-select-col") return selectorCell;
        return null;
    },
};
const root = {
    querySelector() { return null; },
    querySelectorAll(selector) {
        if (selector === ".dco-fast-table tbody tr[data-row-name]") return [tr];
        return [];
    },
};
const row = {
    name:"ROW-1",
    doctype:"Door Cutting Order Detail",
    piece_type:"Regular",
    extra_liner:0,
    extra_back_groove:0,
    extra_double:0,
    extra_full_door_double:0,
    extra_recessed_handle_cutout:0,
};
const frm = {
    doc:{docstatus:0,status:"Draft",pieces:[row]},
    fields_dict:{pieces_fast_entry:{$wrapper:{get(){return root;}}}},
    script_manager:{trigger(fieldname){triggered.push(fieldname);return Promise.resolve();}},
    dirtyCalls:0,
    dirty(){this.dirtyCalls += 1;},
};

const context = vm.createContext({
    window:fakeWindow,
    document:{documentElement:{lang:"ar"}},
    frappe:{
        boot:{lang:"ar"},
        utils:{escape_html:value => String(value)},
        ui:{form:{on(){}}},
        show_alert(){},
    },
    MutationObserver:class MutationObserver {},
    Object,
    Array,
    Boolean,
    Number,
    String,
    Set,
    console,
    queueMicrotask,
    setTimeout,
    clearTimeout,
    requestAnimationFrame:callback => callback(),
});

vm.runInContext(
    source("door_cutting_order/order_entry/extra_addons/door_cutting_order_extra_addons_ux.js"),
    context
);
vm.runInContext(
    source("door_cutting_order/order_entry/measurements/door_cutting_order_table_performance_ux.js"),
    context
);

const performance = fakeWindow.AlmdinaTablePerformanceUX;
assert.ok(performance, "The in-place type mutation owner must be published");

row.extra_liner = 1;
row.extra_double = 1;
assert.equal(performance.setPieceType(frm, tr, "Special"), row);
assert.equal(row.piece_type, "Special");
assert.equal(row.extra_liner, 1);
assert.equal(row.extra_double, 1);
assert.ok(frm.dirtyCalls >= 1);

assert.equal(performance.setPieceType(frm, tr, "Clipped Corner"), row);
assert.equal(row.piece_type, "Clipped Corner");
assert.equal(row.extra_liner, 1);
assert.equal(row.extra_double, 1);

setTimeout(() => {
    assert.ok(triggered.includes("piece_type"));
    assert.equal(triggered.includes("extra_liner"), false);
    assert.equal(triggered.includes("extra_double"), false);
    console.log("Independent add-ons survive in-place piece-type changes");
}, 5);
