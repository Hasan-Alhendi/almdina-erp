"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");
const catalog = fs.readFileSync(
    path.resolve(__dirname, "../../translations/ar.csv"),
    "utf8",
);

function read(relativePath) {
    return fs.readFileSync(path.join(root, relativePath), "utf8");
}

const rendererSource = read("cutting_plan/door_cutting_order_cutting_plan_renderer.js");
assert.match(catalog, /^Default edge banding,قشاط افتراضي$/m);
assert.match(catalog, /^Non-default edge banding,قشاط غير افتراضي$/m);
assert.match(rendererSource, /dco-edge-line--custom/);
assert.match(rendererSource, /#1d4ed8/);
assert.match(rendererSource, /EDGE_BAND_CUSTOM_DASHARRAY/);
assert.match(rendererSource, /render_edge_band_legend/);
assert.match(
    rendererSource,
    /\.dco-edge-line-svg\.dco-edge-line--custom[\s\S]*?#1d4ed8 !important/,
);
assert.match(
    rendererSource,
    /\.dco-piece-double-edge-svg[\s\S]*?stroke-dasharray: none !important/,
);

const marker = "    window.AlmdinaCuttingPlanRender = {";
assert.ok(rendererSource.includes(marker));
const instrumented = rendererSource.replace(
    marker,
    `
    window.__edgeFlags = piece_edge_flags;
    window.__edgeCustomFlags = piece_edge_custom_flags;
    window.__renderEdges = render_piece_edge_lines;
${marker}`,
);

const fakeWindow = {};
const frappe = {
    boot: { lang: "ar" },
    msgprint() {},
    ui: { form: { on() {} } },
    utils: { escape_html(value) { return String(value ?? ""); } },
};
const context = vm.createContext({
    window: fakeWindow,
    document: {
        documentElement: {
            lang: "ar",
            getAttribute(name) { return name === "dir" ? "rtl" : null; },
        },
    },
    frappe,
    console,
    Math,
    Number,
    JSON,
    Object,
    Array,
    Set,
    Map,
    Boolean,
    String,
    Error,
    __: (message) => message,
});

[
    "drawing/door_cutting_order_special_shape_geometry.js",
    "drawing/door_cutting_order_shape_output_contract.js",
    "drawing/door_cutting_order_clipped_corner_ux.js",
    "drawing/door_cutting_order_liner_geometry.js",
    "cutting_plan/door_cutting_order_piece_geometry.js",
].forEach((relativePath) => {
    vm.runInContext(read(relativePath), context, { filename: relativePath });
});
vm.runInContext(instrumented, context, { filename: "cutting_plan_renderer.js" });

const renderer = fakeWindow.AlmdinaCuttingPlanRender;
assert.ok(renderer);

function planFor(piece) {
    return {
        usable_board_width_cm: 122,
        usable_board_length_cm: 244,
        full_board_width_cm: 122,
        full_board_length_cm: 244,
        sheets: [{ sheet_no: 1, pieces: [piece] }],
    };
}

function regularPiece(overrides = {}) {
    return {
        id: "edge-1",
        x: 0,
        y: 0,
        w: 40,
        h: 60,
        original_w: 40,
        original_h: 60,
        area_m2: 0.24,
        label: "1.1",
        piece_type: "Regular",
        rotated: false,
        edge_long_right: 1,
        edge_long_left: 1,
        edge_width_top: 1,
        edge_width_bottom: 1,
        edge_long_right_type_override: "",
        edge_long_left_type_override: "",
        edge_width_top_type_override: "",
        edge_width_bottom_type_override: "",
        ...overrides,
    };
}

const frm = {
    doc: {
        name: "DCO-EDGE-STYLE",
        customer: "عميل",
        default_edge_type: "PVC Default",
        pieces: [],
    },
};

const allDefaultHtml = renderer.build(frm, planFor(regularPiece()));
assert.match(allDefaultHtml, /Default edge banding/);
assert.match(allDefaultHtml, /Non-default edge banding/);
assert.match(allDefaultHtml, /dco-edge-band-legend/);
assert.equal((allDefaultHtml.match(/border-(?:left|right|top|bottom):3px solid #d00000/g) || []).length, 4);
assert.doesNotMatch(allDefaultHtml, /dco-edge-line--custom/);

const oneCustom = regularPiece({
    edge_width_top_type_override: "ABS Special",
});
const oneCustomHtml = renderer.build(frm, planFor(oneCustom));
assert.match(oneCustomHtml, /dco-edge-line--custom[^>]*stroke="#1d4ed8"/);
assert.match(oneCustomHtml, /stroke-dasharray="5px 2\.5px 1\.5px 2\.5px"/);
assert.equal((oneCustomHtml.match(/dco-edge-line--custom/g) || []).length, 1);
assert.equal((oneCustomHtml.match(/border-(?:left|right|top|bottom):3px solid #d00000/g) || []).length, 3);
// Custom top must be the SVG near y=1, not a misplaced side.
assert.match(
    oneCustomHtml,
    /dco-edge-line--custom[^>]*y1="1"[^>]*y2="1"|dco-edge-line--custom[^>]*y1="1"/,
);

const mixed = regularPiece({
    edge_long_left_type_override: "ABS Special",
    edge_width_bottom_type_override: "PVC Other",
    edge_width_top_type_override: "PVC Default", // explicit default stays solid red
});
const mixedHtml = renderer.build(frm, planFor(mixed));
assert.equal((mixedHtml.match(/dco-edge-line--custom/g) || []).length, 2);
assert.match(mixedHtml, /border-top:3px solid #d00000/);
assert.match(mixedHtml, /border-right:3px solid #d00000/);
assert.doesNotMatch(mixedHtml, /border-left:3px solid #d00000/);
assert.doesNotMatch(mixedHtml, /border-bottom:3px solid #d00000/);

const customFlags = fakeWindow.__edgeCustomFlags(frm, mixed, null);
assert.equal(customFlags.left, 1);
assert.equal(customFlags.right, 0);
assert.equal(customFlags.top, 0);
assert.equal(customFlags.bottom, 1);

const rotatedCustom = regularPiece({
    rotated: true,
    edge_long_left: 1,
    edge_long_right: 0,
    edge_width_top: 0,
    edge_width_bottom: 0,
    edge_long_left_type_override: "ABS Special",
});
const rotatedFlags = fakeWindow.__edgeFlags(rotatedCustom, null);
const rotatedCustomFlags = fakeWindow.__edgeCustomFlags(frm, rotatedCustom, null);
assert.equal(rotatedFlags.top, 1);
assert.equal(rotatedCustomFlags.top, 1);
assert.equal(rotatedCustomFlags.left, 0);
const rotatedHtml = renderer.build(frm, planFor(rotatedCustom));
assert.match(rotatedHtml, /dco-edge-line--custom[^>]*(?:y1="1"|x1="16\.667")/);

const allFourCustom = regularPiece({
    edge_long_right_type_override: "A",
    edge_long_left_type_override: "B",
    edge_width_top_type_override: "C",
    edge_width_bottom_type_override: "D",
});
const allFourHtml = renderer.build(frm, planFor(allFourCustom));
assert.equal((allFourHtml.match(/dco-edge-line--custom/g) || []).length, 4);
assert.doesNotMatch(allFourHtml, /border-(?:left|right|top|bottom):3px solid #d00000/);

const lPiece = {
    id: "l-1",
    x: 0,
    y: 0,
    w: 40,
    h: 80,
    original_w: 40,
    original_h: 80,
    area_m2: 0.32,
    label: "2.1",
    piece_type: "L-Shaped Corner",
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 10,
    clipped_corner_length_cm: 16,
    rotated: false,
    edge_long_right: 1,
    edge_long_left: 0,
    edge_width_top: 1,
    edge_width_bottom: 0,
    edge_break: 1,
    edge_break_only: 0,
    edge_type: "ABS Special",
    edge_long_right_type_override: "",
    edge_width_top_type_override: "ABS Special",
    edge_long_left_type_override: "",
    edge_width_bottom_type_override: "",
};
const lHtml = renderer.build(frm, planFor(lPiece));
assert.match(lHtml, /dco-edge-line--custom/);
assert.match(lHtml, /dco-edge-break-svg/);
assert.ok(
    (lHtml.match(/dco-edge-line--custom/g) || []).length >= 2,
    "L outer custom side and inner break both classify as non-default",
);

const clippedPiece = {
    ...lPiece,
    id: "clip-1",
    piece_type: "Clipped Corner",
    edge_break: 0,
    edge_break_only: 1,
    edge_type: "ABS Special",
    edge_width_top_type_override: "",
    edge_long_right_type_override: "PVC Default",
};
const clippedHtml = renderer.build(frm, planFor(clippedPiece));
assert.match(clippedHtml, /dco-edge-break-only-svg/);
assert.match(clippedHtml, /dco-edge-line--custom/);
// Explicit default on the right stays solid (inherits parent red, no custom class on that path).
assert.ok(
    (clippedHtml.match(/dco-edge-line--custom/g) || []).length >= 1,
    "break-only non-default keeps dash-dot classification",
);

const withDouble = regularPiece({
    edge_width_top: 1,
    edge_width_top_type_override: "ABS Special",
    extra_double: 1,
    extra_double_reference_sides: '["edge_width_top"]',
});
const doubleHtml = renderer.build(frm, planFor(withDouble));
assert.match(doubleHtml, /dco-edge-line--custom/);
assert.match(doubleHtml, /stroke="#5a2d82"/);
assert.match(doubleHtml, /data-double-edge-side="edge_width_top"/);

console.log("cutting_plan_edge_band_style tests passed");
