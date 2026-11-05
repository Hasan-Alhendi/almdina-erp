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
    document: { documentElement: { lang: "ar", getAttribute: () => "rtl" } },
    frappe: { utils: { escape_html(value) { return String(value ?? ""); } } },
    __(value) { return Array.isArray(value) ? value[0] : value; },
    Object,
    Array,
    Boolean,
    Number,
    String,
    Math,
    Set,
    JSON,
    console,
});
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js", context);
load("../../public/js/door_cutting_order/drawing/door_cutting_order_machining_overlay.js", context);

const geometry = fakeWindow.AlmdinaLinerGeometry;
const engine = fakeWindow.AlmdinaMachiningOverlay;

function piece(extra = {}) {
    return Object.assign({
        piece_type: "Regular",
        w: 40,
        h: 80,
        width_cm: 40,
        length_cm: 80,
        x: 0,
        y: 0,
        kerf_mm: 6,
    }, extra);
}

function planWith(pieces) {
    return { sheets: [{ pieces }] };
}

const cutOnly = engine.layersInPlan(planWith([piece()]));
assert.equal(cutOnly.readable, true);
assert.equal(cutOnly.cut, true);
assert.equal(cutOnly.liner, false);
assert.equal(cutOnly.recessed_handle_cutout, false);
assert.equal(cutOnly.back_groove, false);

assert.equal(engine.layersInPlan({ snapshot_json: "{" }).readable, false);
assert.equal(engine.layersInPlan(null).liner, false);

const linerOnly = planWith([piece({
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.8,
    liner_start_cm: 0,
    liner_length_cm: 40,
})]);
const linerLayers = engine.layersInPlan(linerOnly);
assert.equal(linerLayers.liner, true);
assert.equal(linerLayers.recessed_handle_cutout, false);
assert.equal(linerLayers.back_groove, false);

const storedHandle = planWith([piece({
    overlays: [{
        kind: "recessed_handle_cutout",
        geometry: { path: [[0, 0], [12, 0]] },
    }],
})]);
assert.equal(engine.layersInPlan(storedHandle).recessed_handle_cutout, true);
assert.equal(engine.layersInPlan(storedHandle).liner, false);

const host = piece({
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 0,
    liner_width_cm: 1.8,
    liner_start_cm: 0,
    liner_length_cm: 40,
    extra_back_groove: 1,
    back_groove_reference_side: "edge_long_right",
    back_groove_offset_cm: 1,
    back_groove_width_cm: 1.8,
    back_groove_start_cm: 0,
    back_groove_length_cm: 40,
    extra_recessed_handle_cutout: 1,
    recessed_handle_reference_side: "edge_width_bottom",
    recessed_handle_offset_cm: 2,
    recessed_handle_width_cm: 1.8,
    recessed_handle_start_cm: 0,
    recessed_handle_length_cm: 40,
    tool_diameters: {
        liner: 3,
        recessed_handle_cutout: 8,
        back_groove: 5,
    },
});
const first = engine.completeToolpaths(host, [], 6, null);
assert.equal(first.error, undefined);
const byKind = Object.fromEntries(first.overlays.map(item => [item.kind, item.geometry.path]));
assert.equal(geometry.cutterCenterOffsetsMm(18, 3).length > 1, true);
assert.notDeepEqual(byKind.liner, byKind.recessed_handle_cutout);
assert.notDeepEqual(byKind.liner, byKind.back_groove);

host.tool_diameters = { liner: 4, recessed_handle_cutout: 8, back_groove: 5 };
const second = engine.completeToolpaths(host, [], 6, null);
const next = Object.fromEntries(second.overlays.map(item => [item.kind, item.geometry.path]));
assert.notDeepEqual(next.liner, byKind.liner);
assert.deepEqual(next.recessed_handle_cutout, byKind.recessed_handle_cutout);
assert.deepEqual(next.back_groove, byKind.back_groove);

const inherited = engine.completeToolpaths(piece({
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 0,
    liner_width_cm: 1.8,
    liner_start_cm: 0,
    liner_length_cm: 40,
    kerf_mm: 6,
}), [], 6, null);
const explicitKerf = engine.completeToolpaths(piece({
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 0,
    liner_width_cm: 1.8,
    liner_start_cm: 0,
    liner_length_cm: 40,
    tool_diameters: { liner: 6 },
}), [], 6, null);
assert.deepEqual(inherited.overlays[0].geometry.path, explicitKerf.overlays[0].geometry.path);

const tooWide = engine.completeToolpaths(piece({
    extra_back_groove: 1,
    back_groove_reference_side: "edge_long_left",
    back_groove_offset_cm: 1,
    back_groove_width_cm: 0.4,
    back_groove_start_cm: 0,
    back_groove_length_cm: 20,
    tool_diameters: { back_groove: 6 },
}), [], 3, null);
assert.equal(tooWide.error.code, "liner_narrower_than_cutter");

const persistedPiece = piece({
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_width_cm: 0.4,
    overlays: [{
        kind: "liner",
        layer: "Liner",
        geometry: {
            schema_version: 1,
            unit: "mm",
            coordinate_space: "usable_sheet",
            closed: false,
            toolpath: true,
            path: [[1, 2], [3, 2]],
        },
    }],
    tool_diameters: { liner: 12 },
});
const persisted = engine.completeToolpaths(
    persistedPiece,
    persistedPiece.overlays,
    6,
    null
);
assert.equal(persisted.error, undefined);
assert.deepEqual(persisted.overlays[0].geometry.path, [[1, 2], [3, 2]]);

const special = engine.completeToolpaths(piece({
    piece_type: "Special",
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_width_cm: 1.8,
}), [], 6, null);
assert.deepEqual(special.overlays, []);

const centers = geometry.cutterCenterOffsetsMm(18, 6);
assert.equal(Array.from(centers).join(","), "3,9,15");
const shifted = geometry.cutterCenterOffsetsMm(18, 4);
assert.notEqual(Array.from(shifted).join(","), Array.from(centers).join(","));
assert.equal(shifted[0], 2);
assert.equal(shifted[shifted.length - 1], 16);

console.log("Per-layer tool diameter simulation passed");
