"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_presenter_adapter.js"
    ),
    "utf8"
);

const listeners = new Map();
let legacyRenderCount = 0;
let permissionApplyCount = 0;

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-TEST-0001",
        pieces: [{ name: "ROW-1", piece_type: "Special" }],
    },
};

const fakeWindow = {
    cur_frm: frm,
    setTimeout(callback) {
        callback();
        return 1;
    },
    addEventListener(name, callback) {
        listeners.set(name, callback);
    },
    AlmdinaCostWorkspaceState: {
        snapshot() {
            return {
                status: "ready",
                data: {
                    order: {},
                    pieces: [{
                        name: "ROW-1",
                        special_shape_price_status: "Estimated",
                        special_shape_custom_unit_price_usd: 0,
                        special_shape_final_unit_price_usd: 0,
                    }],
                },
            };
        },
        canView() {
            return true;
        },
        load() {
            return Promise.resolve(null);
        },
    },
    AlmdinaOrderCostUX: {
        render() {
            legacyRenderCount += 1;
            return true;
        },
        refreshInvoiceSection() {
            return true;
        },
        invoiceLines() {
            return [];
        },
        invoiceTotal() {
            return 0;
        },
        quoteTotal() {
            return 0;
        },
    },
    AlmdinaCostPermissionsUX: {
        apply(receivedFrm) {
            assert.equal(receivedFrm, frm);
            permissionApplyCount += 1;
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    console,
    Object,
    Array,
    Map,
    Boolean,
    Promise,
    String,
    Number,
    __: value => value,
    frappe: {
        utils: {
            escape_html(value) {
                return String(value);
            },
        },
    },
});

vm.runInContext(source, context, {
    filename: "door_cutting_order_cost_workspace_presenter_adapter.js",
});

const refreshListener = listeners.get("almdina:cost-workspace-updated");
assert.equal(typeof refreshListener, "function");

refreshListener();

assert.equal(legacyRenderCount, 1, "Workspace refresh must render the latest cost snapshot once");
assert.equal(
    permissionApplyCount,
    1,
    "Workspace refresh must re-apply permission-owned inline price controls after rendering"
);
assert.equal(
    frm.doc.pieces[0].special_shape_price_status,
    "Estimated",
    "The workspace projection should update an ordinary live piece financial snapshot"
);

// Reproduce the production race: the user types a Special price while an older
// Cost snapshot still contains the previous zero/Estimated value. Rendering must
// preserve the local pending draft until Save/Cancel resolves it.
frm.doc.pieces[0].special_shape_custom_unit_price_usd = 150;
frm.doc.pieces[0].special_shape_final_unit_price_usd = 150;
frm.doc.pieces[0].special_shape_price_status = "Approved";
frm.doc.pieces[0].__almdina_pending_price_edit = "special";
refreshListener();

assert.equal(legacyRenderCount, 2);
assert.equal(permissionApplyCount, 2);
assert.equal(
    frm.doc.pieces[0].special_shape_custom_unit_price_usd,
    150,
    "An asynchronous Cost snapshot must not overwrite the Special price draft"
);
assert.equal(frm.doc.pieces[0].special_shape_price_status, "Approved");
assert.equal(frm.doc.pieces[0].__almdina_pending_price_edit, "special");

// Once Save/Cancel clears the pending marker, authoritative snapshots own the
// financial piece projection again.
delete frm.doc.pieces[0].__almdina_pending_price_edit;
refreshListener();
assert.equal(legacyRenderCount, 3);
assert.equal(permissionApplyCount, 3);
assert.equal(frm.doc.pieces[0].special_shape_custom_unit_price_usd, 0);
assert.equal(frm.doc.pieces[0].special_shape_price_status, "Estimated");

fakeWindow.cur_frm = { doctype: "Customer" };
refreshListener();
assert.equal(legacyRenderCount, 3, "A stale/non-order route must not repaint the prior order");
assert.equal(permissionApplyCount, 3, "A stale/non-order route must not re-apply order permissions");

console.log("Special price workspace refresh regression simulation passed");
