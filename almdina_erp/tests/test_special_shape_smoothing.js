"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
global.frappe = {
    utils: {
        escape_html(value) {
            return String(value);
        },
    },
};

require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_special_shape_ux.js"
));

const normalize = global.window.AlmdinaSpecialShapeEditor.normalizePenStroke;
const erasePenStroke = global.window.AlmdinaSpecialShapeEditor.erasePenStroke;
const clientPointToCanvas = global.window.AlmdinaSpecialShapeEditor.clientPointToCanvas;

function almostEqual(first, second, tolerance = 0.001) {
    return Math.abs(first - second) <= tolerance;
}

const tremblingHorizontal = Array.from({ length: 101 }, (_, index) => [
    index * 5,
    120 + Math.sin(index * 1.7) * 4 + (index % 2 ? 1.2 : -1.2),
]);
const horizontal = normalize(tremblingHorizontal);
assert.equal(horizontal.length, 2, "A trembling straight stroke should become one line");
assert.ok(almostEqual(horizontal[0][1], horizontal[1][1]), "A slight tilt should snap horizontally");

const sparseHorizontal = normalize([[20, 50], [280, 62]]);
assert.ok(
    almostEqual(sparseHorizontal[0][1], sparseHorizontal[1][1]),
    "A sparse, slightly tilted stroke should also snap horizontally"
);

const tremblingDiagonal = Array.from({ length: 81 }, (_, index) => [
    index * 5,
    index * 2 + Math.sin(index * 1.9) * 2.5,
]);
const diagonal = normalize(tremblingDiagonal);
assert.equal(diagonal.length, 2, "A trembling diagonal should become one clean diagonal");
assert.ok(
    Math.abs(diagonal[1][1] - diagonal[0][1]) > 100,
    "An intentional diagonal must not snap to a horizontal line"
);

const arc = Array.from({ length: 61 }, (_, index) => {
    const angle = Math.PI * index / 120;
    return [300 + Math.cos(angle) * 180, 300 + Math.sin(angle) * 180];
});
const curved = normalize(arc);
assert.ok(curved.length > 2, "An intentional curve must remain curved");

const corner = normalize([
    [40, 40], [80, 41], [120, 39], [160, 40],
    [161, 80], [159, 120], [160, 160],
]);
assert.ok(corner.length >= 3, "A deliberate corner must not become one straight line");
assert.ok(
    corner.some(point => Math.abs(point[0] - 160) < 8 && Math.abs(point[1] - 40) < 8),
    "The deliberate corner should remain near its original position"
);

const straightPen = {
    id: "pen-1",
    type: "pen",
    color: "#172033",
    points: [[40, 200], [360, 200]],
};
const erasedMiddle = erasePenStroke(straightPen, [200, 200], [200, 200], 14);
assert.equal(erasedMiddle.changed, true, "The eraser should detect a pen stroke");
assert.equal(erasedMiddle.fragments.length, 2, "Erasing the middle should split the stroke");
assert.ok(
    erasedMiddle.fragments[0].points.at(-1)[0] < 190,
    "The first fragment must stop before the erased circle"
);
assert.ok(
    erasedMiddle.fragments[1].points[0][0] > 210,
    "The second fragment must start after the erased circle"
);
assert.equal(
    erasedMiddle.fragments[0].color,
    straightPen.color,
    "Partial erasing must retain pen styling"
);

const untouchedPen = erasePenStroke(straightPen, [500, 500], [540, 540], 14);
assert.equal(untouchedPen.changed, false, "A distant eraser pass must leave the stroke untouched");
assert.equal(untouchedPen.fragments[0], straightPen, "Untouched strokes should retain identity");

const erasedBand = erasePenStroke(straightPen, [145, 200], [255, 200], 10);
assert.equal(erasedBand.fragments.length, 2, "Dragging the eraser should clear a continuous band");
assert.ok(
    erasedBand.fragments[0].points.at(-1)[0] < 140
    && erasedBand.fragments[1].points[0][0] > 260,
    "The erased band must follow the complete pointer path"
);

const svgWithTransform = {
    getScreenCTM() {
        return {
            inverse() {
                return { marker: "inverse" };
            },
        };
    },
    createSVGPoint() {
        return {
            x: 0,
            y: 0,
            matrixTransform(matrix) {
                assert.equal(matrix.marker, "inverse");
                return {
                    x: (this.x - 100) / 0.8,
                    y: (this.y - 50) / 0.8,
                };
            },
        };
    },
    getBoundingClientRect() {
        throw new Error("The bounding-box approximation must not be used when CTM is available");
    },
};
const mapped = clientPointToCanvas(svgWithTransform, 500, 310);
assert.ok(almostEqual(mapped.x, 500), "Pointer X must follow the real SVG transform");
assert.ok(almostEqual(mapped.y, 325), "Pointer Y must follow the real SVG transform");

console.log("Special-shape drawing precision, smoothing, and eraser checks passed");
