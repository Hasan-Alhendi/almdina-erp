"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order_cutting_plan_renderer.js"),
    "utf8"
);

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    console,
    JSON,
    Number,
    String,
    Math,
});
vm.runInContext(source, context, {
    filename: "door_cutting_order_cutting_plan_renderer.js",
});

const renderer = fakeWindow.AlmdinaCuttingPlanRender;
assert.ok(renderer);
assert.equal(typeof renderer.build, "function");
assert.equal(typeof renderer.parse, "function");
assert.equal(typeof renderer.print, "function");

const plan = {
    usable_board_width_cm: 122,
    usable_board_length_cm: 244,
    full_board_width_cm: 122,
    full_board_length_cm: 244,
    kerf_cm: 0.3,
    trim_cm: 0.5,
    used_area_m2: 0.48,
    total_board_area_m2: 2.9768,
    waste_area_m2: 2.4968,
    method_label: "Auto Pro",
    sheets: [
        {
            sheet_no: 1,
            pieces: [
                {
                    x: 0,
                    y: 0,
                    w: 60,
                    h: 80,
                    original_w: 60,
                    original_h: 80,
                    area_m2: 0.48,
                    label: "1",
                    piece_type: "Regular",
                    rotated: false,
                },
            ],
        },
    ],
    unplaced: [],
};
const frm = {
    doc: {
        name: "DCO-2026-00999",
        customer: "زبون الاختبار",
        board_description: "MDF أبيض 18 مم",
        cutting_plan_json: JSON.stringify(plan),
        pieces: [{ width_cm: 60, length_cm: 80, qty: 1 }],
    },
};

assert.equal(renderer.parse(frm).sheets.length, 1);
const html = renderer.build(frm, renderer.parse(frm));
assert.match(html, /DCO-2026-00999/);
assert.match(html, /زبون الاختبار/);
assert.match(html, /MDF أبيض 18 مم/);
assert.match(html, /dco-cutting-plan/);
assert.match(html, /dco-sheet-board/);
assert.doesNotMatch(html, /undefined/);

console.log("Cutting-plan renderer simulation passed");
