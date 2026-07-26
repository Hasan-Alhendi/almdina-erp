"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

global.window = {};
global.document = { documentElement: { lang: "ar" } };
global.frappe = { boot: { lang: "ar" } };

const source = fs.readFileSync(
    path.join(__dirname, "../public/js/door_cutting_order_clipped_corner_ux.js"),
    "utf8"
);
vm.runInThisContext(source, { filename: "door_cutting_order_clipped_corner_ux.js" });

const geometry = window.AlmdinaClippedCornerGeometry;
assert.ok(geometry, "The shared clipped-corner geometry API should be available");

const piece = {
    piece_type: "Clipped Corner",
    width_cm: 100,
    length_cm: 200,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 40,
};

assert.deepEqual(
    geometry.points(piece, 100, 100),
    [[0, 0], [80, 0], [100, 20], [100, 100], [0, 100]],
    "Top-right clipping should create one diagonal and five polygon vertices"
);

const rotated = {
    ...piece,
    original_w: 100,
    original_h: 200,
    w: 200,
    h: 100,
    rotated: true,
};
assert.deepEqual(
    geometry.points(rotated, 200, 100),
    [[0, 0], [200, 0], [200, 80], [160, 100], [0, 100]],
    "A clockwise rotation should move top-right to bottom-right and swap cut distances"
);
assert.deepEqual(
    geometry.dxfPoints(rotated, 10, 20, 200, 100),
    [[10, 120], [210, 120], [210, 40], [170, 20], [10, 20]],
    "DXF coordinates should preserve the same rotated shape in a bottom-left coordinate system"
);

const defaults = geometry.baseConfig({
    piece_type: "Clipped Corner",
    width_cm: 80,
    length_cm: 200,
});
assert.equal(defaults.position, "Top Right");
assert.equal(defaults.cutWidth, 16);
assert.equal(defaults.cutLength, 40);
assert.match(geometry.summary(piece), /أعلى اليمين/);
assert.equal(geometry.isClipped({ piece_type: "Regular" }), false);

console.log("Clipped-corner geometry, rotation, DXF, defaults, and labels passed");
