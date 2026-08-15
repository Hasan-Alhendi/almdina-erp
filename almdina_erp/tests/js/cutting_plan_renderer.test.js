"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js"),
    "utf8"
);
const geometrySource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"),
    "utf8"
);
const contractSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"),
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
vm.runInContext(geometrySource, context, {
    filename: "door_cutting_order_special_shape_geometry.js",
});
vm.runInContext(contractSource, context, {
    filename: "door_cutting_order_shape_output_contract.js",
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
                {
                    x: 60,
                    y: 0,
                    w: 62,
                    h: 80,
                    original_w: 62,
                    original_h: 80,
                    area_m2: 0.496,
                    label: "2",
                    piece_type: "Special",
                    rotated: false,
                    special_shape_geometry_json:
                        fakeWindow.AlmdinaSpecialShapeGeometry.serialize(
                            fakeWindow.AlmdinaSpecialShapeGeometry.create(
                                "single-slope",
                                62,
                                80
                            )
                        ),
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
assert.match(html, /dco-special-exact-piece/);
assert.match(html, /◆ درفة خاصة · مسار هندسي/);
assert.match(html, /<polygon points="/);
assert.doesNotMatch(html, /undefined/);

console.log("Cutting-plan renderer simulation passed");
