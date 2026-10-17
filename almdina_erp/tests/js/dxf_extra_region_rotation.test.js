"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const src = fs.readFileSync(path.resolve(
    __dirname, "../../public/js/door_cutting_order/cutting_plan/secure_dxf_export.js"
), "utf8");
const anchor = '    frappe.ui.form.on("Door Cutting Order", {';
assert.ok(src.includes(anchor));
const instrumented = src.replace(anchor, `
    window.__testDxfRegion = linerRegionPoints;
    window.__testPersistedOverlays = persistedOverlays;
${anchor}`);
const transform = (point, _mirror, turns, width, height) => {
    let [x, y] = point;
    for (let t = 0; t < turns; t++) {
        [x, y] = [height - y, x];
        [width, height] = [height, width];
    }
    return [x, y];
};
const fakeWindow = {
    AlmdinaLinerGeometry: {
        regionPolygonMm: () => [[0, 0], [10, 0], [10, 20], [0, 20]],
        pieceFromRow: () => ({widthCm: 54.9, lengthCm: 100}),
        transformPoint: transform,
    },
    AlmdinaMachiningOverlay: {
        completeToolpaths: (_piece, overlays) => ({ overlays }),
    },
};
const fakeFrappe = {almdina: {}, provide() {}, ui: {form: {on() {}}}};
const c = vm.createContext({
    window: fakeWindow, frappe: fakeFrappe, console, Number, Array, Object, Set, Math,
    __: message => message,
});
vm.runInContext(instrumented, c, {filename: "secure_dxf_export.js"});

const placement = {
    offsetX: 0, offsetY: 0, fullHeight: 1100,
    appliedTrim: {width: 0, length: 0},
};
const spec = {side: "edge_long_right", offsetCm: 10, widthCm: 1.8};
for (let turns = 0; turns < 4; turns++) {
    const piece = {x: 0, y: 0, rotated: turns % 2 === 1, rotation_quarter_turns: turns};
    const result = fakeWindow.__testDxfRegion(piece, placement, spec);
    const expected = [0, 0, 10, 20].length;
    assert.equal(result.length, expected);
    // AutoCAD y-up export of original 0,0 after the physical clockwise turn.
    const original = transform([0, 0], false, turns, 549, 1000);
    assert.equal(result[0][0], original[0], `x at turn ${turns}`);
    assert.equal(result[0][1], 1100 - original[1], `y at turn ${turns}`);
}
const corner = fakeWindow.__testDxfRegion(
    {x: 0, y: 0, rotated: false, corner_rotation_quarter_turns: 2},
    placement, spec
);
assert.equal(corner[0][0], 549);
assert.equal(corner[0][1], 100);

const overlay = {
    kind: "liner", layer: "Liner",
    geometry: {
        schema_version: 1, unit: "mm", coordinate_space: "usable_sheet",
        path: [[438.5, 902.5], [443.5, 902.5], [446.5, 902.5]],
        closed: false,
    },
};
const persisted = fakeWindow.__testPersistedOverlays(
    {rotation_quarter_turns: 3, overlays: [overlay]}, 5, null
);
assert.equal(persisted.length, 1);
assert.equal(JSON.stringify(persisted[0].path), JSON.stringify(overlay.geometry.path));
console.log("DXF verified rotation GEOMETRY and physical overlay export passed");
