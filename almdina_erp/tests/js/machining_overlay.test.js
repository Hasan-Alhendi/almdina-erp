"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(relativePath, context) {
    vm.runInContext(fs.readFileSync(path.resolve(__dirname, relativePath), "utf8"), context);
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
load("../../public/js/door_cutting_order/drawing/door_cutting_order_machining_overlay.js", context);
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_ux.js", context);

const geometry = fakeWindow.AlmdinaLinerGeometry;
const engine = fakeWindow.AlmdinaMachiningOverlay;
const editor = fakeWindow.AlmdinaLinerEditor;
const piece = geometry.pieceFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
});
const linerPath = geometry.toolpathMm(piece, "edge_width_top", 2, 1.8, 6, 0, 40);
const shared = engine.ADDONS.map(addon => engine.generateToolpath({
    type: addon.kind,
    piece,
    referenceSide: "edge_width_top",
    offsetCm: 2,
    widthCm: 1.8,
    startCm: 0,
    lengthCm: 40,
    cutterDiameterMm: 6,
}));
assert.deepEqual(shared[0], linerPath);
assert.deepEqual(shared[1], linerPath);
assert.deepEqual(shared[2], linerPath);

const row = {
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
    liner_start_cm: 0,
    liner_length_cm: 40,
    extra_back_groove: 1,
    back_groove_reference_side: "edge_long_right",
    back_groove_offset_cm: 1,
    back_groove_width_cm: 0.8,
    back_groove_start_cm: 5,
    back_groove_length_cm: 20,
    extra_recessed_handle_cutout: 1,
    recessed_handle_reference_side: "edge_width_bottom",
    recessed_handle_offset_cm: 3,
    recessed_handle_width_cm: 1.2,
    recessed_handle_start_cm: 0,
    recessed_handle_length_cm: 40,
};
const grooveDraft = editor.draftFromRow(row, "back_groove");
const handleDraft = editor.draftFromRow(row, "recessed_handle_cutout");
assert.equal(grooveDraft.side, "edge_long_right");
assert.equal(handleDraft.side, "edge_width_bottom");
assert.equal(editor.draftFromRow(row).side, "edge_width_top");
const savedGroove = editor.valuesFor("back_groove", grooveDraft, true);
assert.equal(savedGroove.back_groove_reference_side, "edge_long_right");
assert.equal(savedGroove.extra_liner, undefined);
assert.equal(savedGroove.liner_reference_side, undefined);
const cleared = editor.valuesFor("recessed_handle_cutout", handleDraft, false);
assert.equal(cleared.extra_recessed_handle_cutout, 0);
assert.equal(cleared.recessed_handle_reference_side, "");
assert.equal(row.liner_reference_side, "edge_width_top");

const host = Object.assign({
    x: 0,
    y: 0,
    rotated: false,
    kerf_mm: 6,
}, row);
const completed = engine.completeToolpaths(host, [], 6, null);
assert.equal(completed.error, undefined);
assert.deepEqual(
    completed.overlays.map(item => item.layer),
    ["Liner", "Rear Groove", "Handle Recess"]
);
assert.equal(new Set(completed.overlays.map(item => item.geometry.path.join("|"))).size, 3);

const operator = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"),
    "utf8"
);
const headerStart = operator.indexOf("<thead>");
const header = operator.slice(headerStart, operator.indexOf("</thead>", headerStart));
const notesAt = header.indexOf("dco-col-notes");
const addonAt = header.indexOf("dco-col-addons");
const rotateAt = header.indexOf("dco-col-rotate");
assert.equal((header.match(/dco-col-addons/g) || []).length, 1);
assert.ok(rotateAt >= 0 && addonAt > rotateAt && addonAt < notesAt);

const multiPreview = editor.previewSvg(editor.draftFromRow(Object.assign({}, row, {
    edge_width_top: 1,
}), "liner"), {
    multi: true,
    companions: [grooveDraft, handleDraft],
});
assert.match(multiPreview, /data-machining-kind="liner"/);
assert.match(multiPreview, /data-machining-kind="back_groove"/);
assert.match(multiPreview, /data-machining-kind="recessed_handle_cutout"/);
assert.match(multiPreview, /data-liner-edge="1"/);
assert.match(multiPreview, /data-liner-strip="1"/);
const quietOnly = editor.previewSvg(Object.assign({}, grooveDraft, { enabled: false, kind: "back_groove" }), {
    multi: true,
    companions: [editor.draftFromRow(row, "liner"), handleDraft],
});
assert.match(quietOnly, /data-machining-kind="liner"/);
assert.match(quietOnly, /data-machining-kind="recessed_handle_cutout"/);
assert.doesNotMatch(quietOnly, /data-machining-role="active"/);

console.log("Shared machining overlay simulation passed");
