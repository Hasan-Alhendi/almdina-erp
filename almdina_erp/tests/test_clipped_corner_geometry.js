"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

global.window = {};
global.document = { documentElement: { lang: "ar" } };
global.frappe = { boot: { lang: "ar" } };

const source = fs.readFileSync(
    path.join(
        __dirname,
        "../public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js"
    ),
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
assert.equal(geometry.isCornerCut({ piece_type: "Regular" }), false);
assert.equal(geometry.isCornerCut(piece), true);
assert.equal(geometry.cutStyle(piece), "diagonal");

const lPiece = {
    piece_type: "L-Shaped Corner",
    width_cm: 100,
    length_cm: 100,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 20,
};
assert.equal(geometry.isClipped(lPiece), false);
assert.equal(geometry.isLShaped(lPiece), true);
assert.equal(geometry.isCornerCut(lPiece), true);
assert.equal(geometry.cutStyle(lPiece), "L");
assert.equal(geometry.typeLabel(lPiece), "زاوية L");
assert.deepEqual(
    geometry.points(lPiece, 100, 100),
    [[0, 0], [80, 0], [80, 20], [100, 20], [100, 100], [0, 100]],
    "Top-right L clipping should insert a right-angle vertex instead of a diagonal"
);
assert.deepEqual(
    geometry.points({ ...lPiece, clipped_corner_position: "Top Left" }, 100, 100),
    [[20, 0], [100, 0], [100, 100], [0, 100], [0, 20], [20, 20]]
);
assert.deepEqual(
    geometry.points({ ...lPiece, clipped_corner_position: "Bottom Right" }, 100, 100),
    [[0, 0], [100, 0], [100, 80], [80, 80], [80, 100], [0, 100]]
);
assert.deepEqual(
    geometry.points({ ...lPiece, clipped_corner_position: "Bottom Left" }, 100, 100),
    [[0, 0], [100, 0], [100, 100], [20, 100], [20, 80], [0, 80]]
);

const rotatedL = {
    ...lPiece,
    width_cm: 100,
    length_cm: 200,
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 40,
    original_w: 100,
    original_h: 200,
    w: 200,
    h: 100,
    rotated: true,
};
assert.deepEqual(
    geometry.points(rotatedL, 200, 100),
    [[0, 0], [200, 0], [200, 80], [160, 80], [160, 100], [0, 100]],
    "A clockwise rotation should move an L top-right cut to a six-vertex bottom-right L"
);
assert.deepEqual(
    geometry.dxfPoints(rotatedL, 10, 20, 200, 100),
    [[10, 120], [210, 120], [210, 40], [170, 40], [170, 20], [10, 20]]
);

let printed = null;
global.frappe.msgprint = (payload) => {
    printed = payload;
};
global.frappe.ui = {
    Dialog: function Dialog() {
        throw new Error("Corner editor must not open before piece dimensions exist");
    },
};

window.AlmdinaClippedCornerEditor.open({}, {
    piece_type: "Clipped Corner",
    width_cm: 0,
    length_cm: 0,
});
assert.ok(printed, "Missing dimensions should show a guidance message instead of an error");
assert.match(printed.message, /أدخل عرض الدرفة وطولها أولًا، ثم افتح إعداد الزاوية/);

window.AlmdinaClippedCornerEditor.open({}, {
    piece_type: "L-Shaped Corner",
});
assert.match(printed.message, /أدخل عرض الدرفة وطولها أولًا، ثم افتح إعداد الزاوية/);

console.log("Clipped-corner and L-shaped geometry, rotation, DXF, defaults, and labels passed");
