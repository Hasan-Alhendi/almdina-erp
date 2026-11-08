"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js",
    ),
    "utf8",
);
const catalog = fs.readFileSync(
    path.resolve(__dirname, "../../translations/ar.csv"),
    "utf8",
);

assert.ok(catalog.includes("Deduct edge banding thickness automatically,خصم سماكة القشاط تلقائياً"));
assert.ok(catalog.includes("Deduct edge banding thickness by default,خصم سماكة القشاط افتراضياً"));

function loadApi() {
    const calls = [];
    const frappe = {
        call(request) {
            calls.push(request);
            return Promise.resolve({ message: { ok: true } });
        },
    };
    const context = vm.createContext({
        window: { frappe },
        frappe,
        __: (value) => value,
        Promise,
        Object,
        String,
        Boolean,
        Number,
    });
    vm.runInContext(source, context);
    return { api: context.window.AlmdinaPlanWorkspaceAPI, calls };
}

(async () => {
    const off = loadApi();
    await off.api.preview("DCO-1", {
        packing_mode: "smart",
        cutting_machine_type: "Auto",
        kerf_mm: 3,
        trim_margin_mm: 5,
        optimization_time_limit_sec: 10,
        deduct_edge_thickness: 0,
    });
    assert.equal(off.calls[0].args.deduct_edge_thickness, 0);

    const absent = loadApi();
    await absent.api.preview("DCO-1", {
        packing_mode: "smart",
        cutting_machine_type: "Auto",
        kerf_mm: 3,
        trim_margin_mm: 5,
        optimization_time_limit_sec: 10,
    });
    assert.equal(Object.prototype.hasOwnProperty.call(absent.calls[0].args, "deduct_edge_thickness"), false);

    const on = loadApi();
    await on.api.saveSettings("DCO-2", {
        packing_mode: "smart",
        cutting_machine_type: "Auto",
        kerf_mm: 3,
        trim_margin_mm: 5,
        optimization_time_limit_sec: 10,
        deduct_edge_thickness: false,
    });
    assert.equal(on.calls[0].args.deduct_edge_thickness, 0);
})();
