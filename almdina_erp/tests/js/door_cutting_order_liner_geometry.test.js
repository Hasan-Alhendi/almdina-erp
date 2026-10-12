"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(relativePath, context) {
    vm.runInContext(
        fs.readFileSync(path.resolve(__dirname, relativePath), "utf8"),
        context
    );
}

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    document: { documentElement: { lang: "ar" } },
    frappe: { utils: { escape_html(value) { return String(value ?? ""); } } },
    __(value) { return Array.isArray(value) ? value[0] : value; },
    Object,
    Array,
    Boolean,
    Number,
    String,
    Math,
    console,
});
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js", context);
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_ux.js", context);

const geometry = fakeWindow.AlmdinaLinerGeometry;
const editor = fakeWindow.AlmdinaLinerEditor;
const regular = geometry.pieceFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
});

function copy(value) {
    return JSON.parse(JSON.stringify(value));
}

assert.deepEqual(
    copy(geometry.availableSides("Regular")),
    ["edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right"]
);
assert.deepEqual(
    copy(geometry.availableSides("Clipped Corner")),
    ["edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right", "edge_break", "edge_break_only"]
);
assert.deepEqual(
    copy(geometry.availableSides("L-Shaped Corner")),
    ["edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right", "edge_break"]
);
assert.deepEqual(copy(geometry.availableSides("Special")), []);

for (const side of geometry.availableSides("Regular")) {
    const strip = geometry.stripPolygonMm(regular, side, 2, 1.5);
    assert.equal(geometry.validationCode(regular, side, 2, 1.5), "");
    assert.ok(strip.length >= 4);
}

assert.deepEqual(
    copy(geometry.stripPolygonMm(regular, "edge_width_top", 2, 1.5).map(point => point.map(value => Math.round(value)))),
    [[0, 20], [400, 20], [400, 35], [0, 35]]
);

const clipped = geometry.pieceFromRow({
    piece_type: "Clipped Corner",
    width_cm: 40,
    length_cm: 60,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 10,
    clipped_corner_length_cm: 16,
});
for (const side of geometry.availableSides("Clipped Corner")) {
    assert.equal(geometry.validationCode(clipped, side, 1, 1), "");
}
const breakOnly = geometry.stripPolygonMm(clipped, "edge_break_only", 1, 1);
assert.ok(breakOnly.some(point => point[0] !== breakOnly[0][0] && point[1] !== breakOnly[0][1]));

const shaped = geometry.pieceFromRow({
    piece_type: "L-Shaped Corner",
    width_cm: 40,
    length_cm: 60,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 12,
    clipped_corner_length_cm: 18,
});
assert.equal(geometry.validationCode(shaped, "edge_break", 1, 1), "");
assert.equal(geometry.validationCode(shaped, "edge_break_only", 1, 1), "side_unavailable");

assert.equal(geometry.validationCode(regular, "edge_width_top", -1, 1), "offset_invalid");
assert.equal(geometry.validationCode(regular, "edge_width_top", 0, 0), "width_invalid");
assert.equal(geometry.validationCode(regular, "edge_width_top", 50, 20), "strip_outside");

const near = geometry.stripPolygonMm(regular, "edge_width_top", 2, 1.5);
const far = geometry.stripPolygonMm(regular, "edge_width_top", 4, 3);
assert.notDeepEqual(copy(near), copy(far));

const overlay = geometry.syntheticOverlay({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
    rotated: true,
    x: 0,
    y: 0,
});
assert.equal(overlay.kind, "liner");
assert.equal(overlay.synthetic, true);
assert.equal(overlay.geometry.closed, true);
const xs = overlay.geometry.path.map(point => point[0]);
const ys = overlay.geometry.path.map(point => point[1]);
assert.ok(Math.min(...xs) > 540);
assert.ok(Math.max(...ys) > 300);

const imported = geometry.syntheticOverlay({
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_width_cm: 1.5,
    overlays: [{ kind: "liner", geometry: { path: [[0, 0], [1, 1]] } }],
    geometry: { outer: [[0, 0], [10, 0], [10, 10]] },
});
assert.equal(imported, null);

const firstPreview = editor.previewSvg(editor.draftFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
}));
const moved = editor.draftFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_long_right",
    liner_offset_cm: 5,
    liner_width_cm: 3,
});
const secondPreview = editor.previewSvg(moved);
assert.match(firstPreview, /data-liner-strip="1"/);
assert.match(firstPreview, /data-liner-offset-line="1"/);
assert.match(firstPreview, /data-liner-width-line="1"/);
assert.match(firstPreview, /data-liner-side="edge_width_top"/);
assert.notEqual(firstPreview, secondPreview);
assert.match(secondPreview, /data-liner-side="edge_long_right"/);
assert.equal(editor.validationMessage(Object.assign({}, moved, { widthCm: 0 })), "عرض اللاينر يجب أن يكون أكبر من صفر.");

const operator = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"),
    "utf8"
);
const ux = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_liner_ux.js"),
    "utf8"
);
assert.match(operator, /fieldname === "extra_liner"/);
assert.match(ux, /commitChildValues/);
assert.match(ux, /resolveChildRow/);
assert.match(ux, /queueChildApply/);
assert.match(ux, /if \(saved\) dialog.hide\(\)/);
assert.match(ux, /extra_liner: 0/);
assert.doesNotMatch(ux, /createElement\("style"\)/);

const shapedLiner = geometry.pieceFromRow({
    piece_type: "L-Shaped Corner",
    width_cm: 100,
    length_cm: 80,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 30,
});
assert.deepEqual(
    copy(geometry.stripPolygonMm(shapedLiner, "edge_break", 1, 0.8).map(point => point.map(value => Math.round(value)))),
    [[790, 0], [790, 310], [1000, 310], [1000, 318], [782, 318], [782, 0]]
);
assert.deepEqual(
    copy(geometry.contourNotchCm({
        pieceType: "L-Shaped Corner",
        notchWidthCm: 8,
        notchLengthCm: 16,
        position: "Top Right",
        sideThicknessMm: { long_right: 3, width_top: 2, width_bottom: 1 },
        edgeBreak: true,
        innerMm: 1,
    })),
    { cutWidthCm: 7.8, cutLengthCm: 15.9 }
);
assert.deepEqual(
    copy(geometry.contourNotchCm({
        pieceType: "L-Shaped Corner",
        notchWidthCm: 8,
        notchLengthCm: 16,
        position: "Top Right",
        edgeBreak: true,
        innerMm: null,
    })),
    { cutWidthCm: 8, cutLengthCm: 16 }
);

async function persistenceChecks() {
context.frappe.msgprint = () => {};
context.frappe.model = { set_value() { throw new Error("stale row write"); } };
const writes = [];
let releaseSave = () => {};
const saveGate = new Promise(resolve => { releaseSave = resolve; });
const currentRow = {
    doctype: "Door Cutting Order Detail",
    name: "current-row",
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
};
const staleRow = {
    doctype: "Door Cutting Order Detail",
    name: "stale-row",
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
};
fakeWindow.AlmdinaClippedCornerEditor = {
    resolveChildRow() { return currentRow; },
    queueChildApply(_frm, task) { return task(); },
    commitChildValues(_frm, row, values) {
        writes.push({ name: row.name, values });
        return saveGate;
    },
};
fakeWindow.AlmdinaDoorCuttingFastEntry = { render() {} };
const frm = { dirty() {}, doc: {} };
const linerValues = {
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
};
const firstSave = editor.applyLiner(frm, staleRow, linerValues);
const secondSave = editor.applyLiner(frm, staleRow, linerValues);
assert.equal(await secondSave, false);
releaseSave();
assert.equal(await firstSave, true);
assert.equal(writes.length, 1);
assert.equal(writes[0].name, "current-row");

fakeWindow.AlmdinaClippedCornerEditor.resolveChildRow = () => null;
assert.equal(await editor.applyLiner(frm, staleRow, linerValues), false);
assert.equal(writes.length, 1);

fakeWindow.AlmdinaClippedCornerEditor.resolveChildRow = () => Object.assign({}, currentRow, {
    piece_type: "Special",
});
assert.equal(await editor.applyLiner(frm, staleRow, linerValues), false);
assert.equal(writes.length, 1);
}

persistenceChecks().catch(error => {
    console.error(error);
    process.exit(1);
});
