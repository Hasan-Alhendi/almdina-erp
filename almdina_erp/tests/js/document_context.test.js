"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order_document_context.js"),
    "utf8"
);

const handlers = {};
const clearedTimers = [];

function htmlWrapper(content) {
    return {
        content,
        emptyCalls: 0,
        empty() {
            this.content = "";
            this.emptyCalls += 1;
        },
    };
}

function form(name) {
    const fields = [
        "operator_status_strip",
        "pieces_fast_entry",
        "order_cost_invoice_html",
        "plan_control_actions",
        "plan_controls_intro",
        "cutting_plan_html",
    ];
    return {
        doc: { doctype: "Door Cutting Order", name },
        fields_dict: Object.fromEntries(
            fields.map(fieldname => [fieldname, { $wrapper: htmlWrapper(`old:${fieldname}`) }])
        ),
        _dco_calc_timer: 77,
        _dco_calc_version: 4,
        _dco_selected_piece_rows: new Set(["ROW-OLD"]),
        _dco_edge_color_map: { Old: "red" },
        _dco_cost_render_deferred: true,
        _dco_piece_type_restore_token: "old-token",
        _dco_plan_recalculation_running: true,
        _dcoTextBoardPlanBusy: true,
        __almdina_active_plan_tab: "Approved",
        __almdina_stage_type: "Drawing",
        _almdina_factory_defaults_loaded: true,
        _dco_added_buttons: true,
    };
}

const fakeWindow = {
    cur_frm: null,
    clearTimeout(timer) {
        clearedTimers.push(timer);
    },
};
const fakeFrappe = {
    ui: {
        form: {
            on(doctype, events) {
                assert.equal(doctype, "Door Cutting Order");
                Object.assign(handlers, events);
            },
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
});
vm.runInContext(source, context, { filename: "door_cutting_order_document_context.js" });

const frm = form("DCO-2026-00001");
fakeWindow.cur_frm = frm;
handlers.before_load(frm);

assert.equal(frm._almdinaDocumentContextIdentity, "Door Cutting Order::DCO-2026-00001");
assert.deepEqual(clearedTimers, [77]);
assert.equal(frm._dco_calc_timer, null);
assert.equal(frm._dco_calc_version, 5);
assert.equal(frm._dco_selected_piece_rows.size, 0);
assert.deepEqual(Object.keys(frm._dco_edge_color_map), []);
assert.equal(frm._dco_cost_render_deferred, false);
assert.equal(frm._dco_piece_type_restore_token, null);
assert.equal(frm._dco_plan_recalculation_running, false);
assert.equal(frm._dcoTextBoardPlanBusy, false);
assert.equal(frm.__almdina_active_plan_tab, null);
assert.equal(frm.__almdina_stage_type, null);
assert.equal("_almdina_factory_defaults_loaded" in frm, false);
assert.equal("_dco_added_buttons" in frm, false);
Object.values(frm.fields_dict).forEach(field => {
    assert.equal(field.$wrapper.content, "");
    assert.equal(field.$wrapper.emptyCalls, 1);
});

// A normal refresh of the same order keeps freshly rendered UI intact.
Object.values(frm.fields_dict).forEach(field => {
    field.$wrapper.content = "fresh current order";
});
handlers.refresh(frm);
Object.values(frm.fields_dict).forEach(field => {
    assert.equal(field.$wrapper.content, "fresh current order");
    assert.equal(field.$wrapper.emptyCalls, 1);
});

// Reusing the Form object for another route clears every stale document region.
frm.doc.name = "DCO-2026-00002";
frm._dco_selected_piece_rows.add("ROW-FROM-FIRST-ORDER");
frm._dco_piece_type_restore_token = "first-order-token";
handlers.onload(frm);

assert.equal(frm._almdinaDocumentContextIdentity, "Door Cutting Order::DCO-2026-00002");
assert.equal(frm._dco_selected_piece_rows.size, 0);
assert.equal(frm._dco_piece_type_restore_token, null);
Object.values(frm.fields_dict).forEach(field => {
    assert.equal(field.$wrapper.content, "");
    assert.equal(field.$wrapper.emptyCalls, 2);
});

assert.equal(
    fakeWindow.AlmdinaDocumentContext.isCurrent(frm, "Door Cutting Order::DCO-2026-00001"),
    false
);
assert.equal(
    fakeWindow.AlmdinaDocumentContext.isCurrent(frm, "Door Cutting Order::DCO-2026-00002"),
    true
);

console.log("Door cutting order document-context simulation passed");
