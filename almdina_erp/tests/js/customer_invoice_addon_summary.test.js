"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const summarySource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_customer_invoice_addon_summary.js"
    ),
    "utf8"
);
const registrySource = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js"
    ),
    "utf8"
);

const originalLines = [
    {
        type: "material",
        description: "ألواح MDF",
        quantity: 2,
        unit: "لوح",
        rate: 10,
        amount: 20,
    },
    {
        type: "extra_addon",
        description: "إضافة Liner — درفة رقم 28",
        quantity: 2,
        unit: "درفة",
        rate: 3,
        amount: 6,
        note: "ملاحظة الدرفة 28",
    },
    {
        type: "extra_addon",
        description: "إضافة Liner — درفة رقم 29",
        quantity: 3,
        unit: "درفة",
        rate: 3,
        amount: 9,
        note: "ملاحظة الدرفة 29",
    },
    {
        type: "extra_addon",
        description: "إضافة حفر مسكة غطس — درفة رقم 30",
        quantity: 1,
        unit: "درفة",
        rate: 4,
        amount: 4,
        note: "تفصيل داخلي",
    },
];

const baseCostApi = Object.freeze({
    invoiceLines() {
        return originalLines.map(line => ({ ...line }));
    },
    invoiceTotal() {
        return originalLines.reduce((sum, line) => sum + Number(line.amount || 0), 0);
    },
});
const fakeWindow = { AlmdinaOrderCostUX: baseCostApi };
const context = vm.createContext({
    window: fakeWindow,
    Object,
    Array,
    Map,
    Number,
    String,
});
vm.runInContext(summarySource, context, {
    filename: "door_cutting_order_customer_invoice_addon_summary.js",
});

const api = fakeWindow.AlmdinaCustomerInvoiceAddonSummary;
assert.ok(api, "customer invoice addon summary API must be installed");
assert.notEqual(fakeWindow.AlmdinaOrderCostUX, baseCostApi, "cost API should be decorated, not mutated");

const lines = fakeWindow.AlmdinaOrderCostUX.invoiceLines({});
assert.equal(lines.length, 3);
assert.equal(lines[0].description, "ألواح MDF");
assert.equal(lines[1].description, "لاينر");
assert.equal(lines[1].quantity, 5);
assert.equal(lines[1].rate, 3);
assert.equal(lines[1].amount, 15);
assert.equal(lines[1].note, "");
assert.equal(lines[2].description, "مسكة غطس");
assert.equal(lines[2].quantity, 1);
assert.equal(lines[2].amount, 4);
assert.ok(lines.every(line => !String(line.description).includes("درفة رقم")));
assert.equal(
    lines.reduce((sum, line) => sum + Number(line.amount || 0), 0),
    originalLines.reduce((sum, line) => sum + Number(line.amount || 0), 0),
    "summarization must preserve the customer invoice total"
);
assert.equal(originalLines[1].description, "إضافة Liner — درفة رقم 28");

const mixedRates = api.summarizeLines([
    {
        type: "extra_addon",
        description: "إضافة Liner — درفة رقم 1",
        quantity: 1,
        unit: "درفة",
        rate: 4,
        amount: 4,
    },
    {
        type: "extra_addon",
        description: "إضافة لاينر — درفة رقم 2",
        quantity: 1,
        unit: "درفة",
        rate: 6,
        amount: 6,
    },
]);
assert.equal(mixedRates.length, 1);
assert.equal(mixedRates[0].description, "لاينر");
assert.equal(mixedRates[0].quantity, 2);
assert.equal(mixedRates[0].amount, 10);
assert.equal(mixedRates[0].rate, 5);

const presenterIndex = registrySource.indexOf("door_cutting_order_cost_presenter.js");
const summaryIndex = registrySource.indexOf("door_cutting_order_customer_invoice_addon_summary.js");
const adapterIndex = registrySource.indexOf("door_cutting_order_cost_workspace_presenter_adapter.js");
assert.ok(presenterIndex >= 0);
assert.ok(summaryIndex > presenterIndex, "summary decorator must load after the cost presenter");
assert.ok(adapterIndex > summaryIndex, "summary decorator must load before the Cost workspace adapter renders");

console.log("Customer invoice add-on summary simulation passed");
