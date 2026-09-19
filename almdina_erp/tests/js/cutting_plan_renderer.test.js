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
const pieceGeometrySource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_piece_geometry.js"),
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
vm.runInContext(pieceGeometrySource, context, {
    filename: "door_cutting_order_piece_geometry.js",
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
                {
                    id: 3,
                    x: 80,
                    y: 90,
                    w: 20,
                    h: 20,
                    original_w: 20,
                    original_h: 20,
                    area_m2: 0.03,
                    label: "3.1",
                    piece_type: "Special",
                    rotated: true,
                    edge_long_left: 1,
                    geometry: {
                        schema_version: 1,
                        unit: "mm",
                        coordinate_space: "usable_sheet",
                        outer: [[800, 900], [1000, 900], [1000, 1100], [800, 1100]],
                        holes: [[[860, 960], [940, 960], [940, 1040], [860, 1040]]],
                    },
                },
                {
                    id: 4,
                    x: 0,
                    y: 90,
                    w: 40,
                    h: 60,
                    original_w: 40,
                    original_h: 60,
                    area_m2: 0.24,
                    label: "4.1",
                    source_piece_no: 4,
                    piece_type: "Extra",
                    rotated: false,
                    geometry: {
                        schema_version: 1,
                        unit: "mm",
                        coordinate_space: "usable_sheet",
                        outer: [[0, 900], [400, 900], [400, 1500], [0, 1500]],
                        holes: [],
                    },
                    overlays: [
                        {
                            kind: "liner",
                            layer: "Liner",
                            geometry: {
                                schema_version: 1,
                                unit: "mm",
                                coordinate_space: "usable_sheet",
                                path: [[40, 940], [180, 940], [180, 1060], [40, 1060]],
                                closed: true,
                            },
                        },
                        {
                            kind: "back_groove",
                            layer: "Rear Groove",
                            geometry: {
                                schema_version: 1,
                                unit: "mm",
                                coordinate_space: "usable_sheet",
                                path: [[20, 1480], [380, 1480]],
                                closed: false,
                            },
                        },
                        {
                            kind: "recessed_handle_cutout",
                            layer: "Handle Recess",
                            geometry: {
                                schema_version: 1,
                                unit: "mm",
                                coordinate_space: "usable_sheet",
                                path: [[80, 980], [160, 980], [160, 1020], [80, 1020]],
                                closed: true,
                            },
                        },
                    ],
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
assert.match(html, /<path d="/);
assert.match(html, /data-geometry-source="manual-special"/);
assert.match(html, /data-geometry-source="dxf"/);
assert.match(html, /dco-extra-overlay/);
assert.match(html, /data-overlay-layer="Liner"/);
assert.match(html, /data-overlay-kind="liner"[^>]*stroke-width="0.7"/);
assert.match(html, /data-overlay-kind="back_groove"[^>]*stroke-width="0.7"/);
assert.match(html, /data-overlay-kind="liner"[^>]*stroke="#1d6fbf"/);
assert.match(html, /data-overlay-kind="liner"[^>]*stroke-dasharray="3 2.2"/);
assert.match(html, /data-overlay-kind="liner"[^>]*d="M[\d.-]+ [\d.-]+ L[\d.-]+ [\d.-]+"/);
assert.doesNotMatch(html, /data-overlay-kind="liner"[^>]* Z"/);
assert.match(html, /<rect class="dco-extra-overlay-path dco-extra-overlay-handle"/);
assert.match(html, /data-overlay-kind="recessed_handle_cutout"[^>]*stroke-width="0.65"/);
assert.doesNotMatch(html, /stroke-width="1.75"/);
assert.match(html, /dco-extra-addon-legend/);
assert.match(html, /رموز إضافات Extra/);
assert.match(html, /دبل قشاط/);
assert.match(html, /دبل كامل الدرفة/);
assert.doesNotMatch(html, /dco-extra-addon-marks/);
assert.match(html, /data-geometry-id="pg-/);
assert.match(html, /fill-rule="evenodd"/);
assert.match(html, /clip-rule="evenodd"/);
assert.match(html, /dco-edge-line-svg/);
assert.doesNotMatch(html, /undefined/);

const doubledFrm = {
    doc: {
        ...frm.doc,
        pieces: [
            {
                width_cm: 60,
                length_cm: 80,
                qty: 3,
                extra_full_door_double: 1,
                piece_type: "Extra",
            },
        ],
    },
};
const doubledHtml = renderer.build(doubledFrm, renderer.parse(doubledFrm));
assert.match(doubledHtml, /عدد 6/);

const extraAddonFrm = {
    doc: {
        ...frm.doc,
        pieces: [
            { width_cm: 60, length_cm: 80, qty: 1, piece_type: "Regular" },
            { width_cm: 62, length_cm: 80, qty: 1, piece_type: "Special" },
            { width_cm: 20, length_cm: 20, qty: 1, piece_type: "Special" },
            {
                width_cm: 40,
                length_cm: 60,
                qty: 1,
                piece_type: "Extra",
                extra_double: 1,
                extra_full_door_double: 1,
                extra_liner: 1,
            },
        ],
    },
};
const extraAddonHtml = renderer.build(extraAddonFrm, renderer.parse(extraAddonFrm));
assert.match(extraAddonHtml, /dco-extra-addon-marks/);
assert.match(extraAddonHtml, /dco-extra-addon-text[^>]*data-addon-kind="double"/);
assert.match(extraAddonHtml, /dco-extra-addon-text[^>]*data-addon-kind="full_door_double"/);
assert.match(extraAddonHtml, /data-addon-kind="double"/);
assert.match(extraAddonHtml, /data-addon-kind="full_door_double"/);
assert.match(extraAddonHtml, /data-addon-slot="top-end"/);
assert.match(extraAddonHtml, /data-addon-slot="top-start"/);
assert.match(extraAddonHtml, /dco-extra-addon-mark/);
assert.match(extraAddonHtml, /دبل قشاط/);
assert.match(extraAddonHtml, /دبل كامل الدرفة/);
assert.doesNotMatch(extraAddonHtml, /dco-extra-addon-icon/);
assert.match(extraAddonHtml, /dco-extra-overlay/);
assert.match(extraAddonHtml, /data-overlay-layer="Liner"/);
assert.match(extraAddonHtml, /dco-extra-addon-legend/);

const regularOnlyFrm = {
    doc: {
        ...frm.doc,
        pieces: [
            {
                width_cm: 60,
                length_cm: 80,
                qty: 1,
                piece_type: "Regular",
                extra_double: 1,
                extra_full_door_double: 1,
            },
        ],
    },
};
const regularOnlyPlan = {
    ...plan,
    sheets: [
        {
            sheet_no: 1,
            pieces: [plan.sheets[0].pieces[0]],
        },
    ],
};
const regularOnlyHtml = renderer.build(regularOnlyFrm, regularOnlyPlan);
assert.doesNotMatch(regularOnlyHtml, /dco-extra-addon-marks/);
assert.match(regularOnlyHtml, /dco-extra-addon-legend/);
assert.doesNotMatch(regularOnlyHtml, /dco-sheet-text-labels/);
assert.match(regularOnlyHtml, /dco-piece-number/);

const pastFiftyPlan = {
    ...plan,
    sheets: [
        {
            sheet_no: 2,
            pieces: [
                {
                    x: 0,
                    y: 0,
                    w: 40,
                    h: 50,
                    original_w: 40,
                    original_h: 50,
                    area_m2: 0.2,
                    label: "50.1",
                    source_piece_no: 50,
                    piece_type: "Regular",
                    rotated: false,
                },
                {
                    x: 40,
                    y: 0,
                    w: 40,
                    h: 50,
                    original_w: 40,
                    original_h: 50,
                    area_m2: 0.2,
                    label: "51.1",
                    source_piece_no: 51,
                    piece_type: "Regular",
                    rotated: false,
                },
            ],
        },
        {
            sheet_no: 1,
            pieces: [
                {
                    x: 0,
                    y: 0,
                    w: 40,
                    h: 50,
                    original_w: 40,
                    original_h: 50,
                    area_m2: 0.2,
                    label: "1.1",
                    source_piece_no: 1,
                    piece_type: "Regular",
                    rotated: false,
                },
            ],
        },
    ],
};
const pastFiftyFrm = {
    doc: {
        ...frm.doc,
        pieces: Array.from({ length: 51 }, (_, index) => ({
            width_cm: 40,
            length_cm: 50,
            qty: 1,
            piece_type: "Regular",
            piece_no: index + 1,
        })),
    },
};
const pastFiftyHtml = renderer.build(pastFiftyFrm, pastFiftyPlan);
assert.match(pastFiftyHtml, />50</);
assert.match(pastFiftyHtml, />51</);
assert.match(pastFiftyHtml, /لوح 2/);
assert.match(pastFiftyHtml, /لوح 1/);
assert.ok(pastFiftyHtml.indexOf("لوح 2") < pastFiftyHtml.indexOf("لوح 1"));

console.log("Cutting-plan renderer simulation passed");
