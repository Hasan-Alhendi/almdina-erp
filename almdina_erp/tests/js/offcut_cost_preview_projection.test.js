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

let legacyInvoiceCalls = 0;
const payload = {
    order_name: "DCO-178-PREVIEW",
    order: {
        required_boards: 0,
        board_rate_usd: 40,
        cutting_cost_per_board_usd: 5,
        offcut_price_usd: 75,
        offcut_price_applicable: true,
        offcut_factory_factory: true,
    },
    pieces: [
        {
            name: "ROW-1",
            qty: 5,
            factory_execution_qty: 4,
            factory_execution_ratio: 0.8,
        },
        {
            name: "ROW-2",
            qty: 1,
            factory_execution_qty: 0,
            factory_execution_ratio: 0,
        },
    ],
    invoice_preview_lines: [
        {
            type: "offcut",
            description: "سعر الفضلة",
            quantity: 1,
            unit: "مجموعة",
            rate_usd: 75,
            amount_usd: 75,
            note: "سعر إجمالي للمجموعة",
        },
        {
            type: "extra_addon",
            description: "إضافة Liner — درفة رقم 1",
            quantity: 4,
            unit: "درفة",
            rate_usd: 3,
            amount_usd: 12,
        },
    ],
    invoice_preview_total_usd: 87,
    pending_factory_price_labels: [],
};

const legacy = {
    render() {
        return true;
    },
    refreshInvoiceSection() {
        return true;
    },
    invoiceLines() {
        legacyInvoiceCalls += 1;
        return [{ type: "legacy", amount: 999 }];
    },
    invoiceTotal() {
        return 999;
    },
    quoteTotal() {
        return 999;
    },
};

const fakeWindow = {
    AlmdinaOrderCostUX: legacy,
    AlmdinaCostWorkspaceState: {
        snapshot() {
            return { status: "ready", data: payload };
        },
        canView() {
            return true;
        },
    },
    addEventListener() {},
    cur_frm: null,
};
const fakeFrappe = {
    utils: {
        escape_html(value) {
            return String(value);
        },
    },
};
const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    console,
    Object,
    Array,
    Map,
    Set,
    Boolean,
    Number,
    String,
    Math,
    Promise,
    __: value => value,
});

vm.runInContext(source, context, {
    filename: "door_cutting_order_cost_workspace_presenter_adapter.js",
});

const api = fakeWindow.AlmdinaOrderCostUX;
assert.ok(api && api.__a52WorkspaceOwned, "Cost presenter must be workspace-owned");

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-178-PREVIEW",
        pieces: [
            { name: "ROW-1", qty: 5 },
            { name: "ROW-2", qty: 1 },
        ],
    },
    fields_dict: {},
};

const lines = api.invoiceLines(frm);
assert.deepEqual(
    JSON.parse(JSON.stringify(lines)),
    [
        {
            type: "offcut",
            description: "سعر الفضلة",
            quantity: 1,
            unit: "مجموعة",
            rate: 75,
            amount: 75,
            pending: false,
            note: "سعر إجمالي للمجموعة",
        },
        {
            type: "extra_addon",
            description: "إضافة Liner — درفة رقم 1",
            quantity: 4,
            unit: "درفة",
            rate: 3,
            amount: 12,
            pending: false,
            note: "",
        },
    ],
    "Cost UI must consume the canonical server invoice preview"
);
assert.equal(legacyInvoiceCalls, 0, "ready Cost workspace must not rebuild invoice from legacy DCO qty");
assert.equal(api.invoiceTotal(frm), 87);
assert.equal(api.quoteTotal(frm), 87);
assert.equal(frm.doc.pieces[0].qty, 5, "customer requirement qty must remain unchanged");
assert.equal(frm.doc.pieces[0].factory_execution_qty, 4);
assert.equal(frm.doc.pieces[1].factory_execution_qty, 0);
assert.equal(
    source.includes("setTimeout("),
    false,
    "canonical preview adapter must not introduce timer-based reconciliation"
);

console.log("ALMADINA-178 Cost preview projection simulation passed");
