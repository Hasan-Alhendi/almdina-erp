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
    "../public/js/door_cutting_order_sketch_engine.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_sketch_interaction.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_sketch_history.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_sketch_renderer.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_inline_note_editor.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_special_shape_geometry.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_shape_output_contract.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_special_shape_ux.js"
));

const sketchEngine = global.window.AlmdinaSketchEngine;
const normalize = sketchEngine.normalizePenStroke;
const erasePenStroke = sketchEngine.erasePenStroke;
const clientPointToCanvas = global.window.AlmdinaSpecialShapeEditor.clientPointToCanvas;
const snapLineEnd = sketchEngine.snapLineEnd;
const snapPenEndpoints = sketchEngine.snapPenEndpoints;
const translateElement = sketchEngine.translateElement;
const elementBounds = sketchEngine.elementBounds;
const templatePoints = sketchEngine.templatePoints;
const clampViewBox = sketchEngine.clampViewBox;

assert.equal(Object.isFrozen(sketchEngine), true, "The pure sketch API should be immutable");

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
assert.equal(
    erasedMiddle.fragments[1].id,
    "pen-1-fragment-1",
    "Standalone erasing should produce a deterministic fragment identity"
);
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

const almostHorizontal = snapLineEnd(
    { x: 100, y: 100 },
    { x: 420, y: 125 }
);
assert.ok(
    almostEqual(almostHorizontal.y, 100),
    "A nearly horizontal line-tool stroke should align itself"
);
const intentionalDiagonal = snapLineEnd(
    { x: 100, y: 100 },
    { x: 300, y: 230 }
);
assert.ok(
    almostEqual(intentionalDiagonal.x, 300) && almostEqual(intentionalDiagonal.y, 230),
    "An intentional line-tool diagonal must remain unchanged"
);
const forcedAngle = snapLineEnd(
    { x: 0, y: 0 },
    { x: 200, y: 80 },
    true
);
const forcedDegrees = Math.atan2(forcedAngle.y, forcedAngle.x) * 180 / Math.PI;
assert.ok(
    almostEqual(forcedDegrees, 15, 0.01),
    "Holding Shift should constrain a line to 15-degree increments"
);

const closedOutline = snapPenEndpoints(
    [[100, 100], [500, 100], [500, 400], [100, 400], [108, 105]],
    []
);
assert.deepEqual(
    closedOutline.at(-1),
    closedOutline[0],
    "A long outline ending near its start should close automatically"
);
const existingLine = {
    id: "line-anchor",
    type: "line",
    x1: 40,
    y1: 60,
    x2: 400,
    y2: 60,
};
const joinedStroke = snapPenEndpoints(
    [[395, 65], [520, 180]],
    [existingLine]
);
assert.deepEqual(
    joinedStroke[0],
    [400, 60],
    "A new stroke should join a nearby existing endpoint without a visible gap"
);

const movedDimension = translateElement({
    id: "dimension-1",
    type: "dimension",
    x1: 120,
    y1: 180,
    x2: 360,
    y2: 180,
    text: "85 سم",
}, 25, -20);
assert.deepEqual(
    [movedDimension.x1, movedDimension.y1, movedDimension.x2, movedDimension.y2],
    [145, 160, 385, 160],
    "Moving a selected dimension should preserve its geometry"
);
assert.equal(movedDimension.text, "85 سم", "Moving must retain the dimension text");
assert.deepEqual(
    elementBounds(movedDimension),
    { x: 145, y: 125, width: 240, height: 35 },
    "The selection box should cover both the dimension line and its label"
);

for (const template of ["single-slope", "double-clipped", "clipped-corner", "arch", "lshape", "trapezoid"]) {
    const points = templatePoints(template);
    assert.ok(points.length >= 5, `${template} should produce a usable outline`);
    assert.deepEqual(points.at(-1), points[0], `${template} should be a closed outline`);
}

assert.equal(
    templatePoints("single-slope").length,
    5,
    "The single-slope preset should be a closed four-sided outline"
);
assert.equal(
    templatePoints("double-clipped").length,
    7,
    "The double-clipped preset should include both upper cuts"
);

const clippedCorner = templatePoints("clipped-corner");
assert.equal(clippedCorner.length, 6, "A clipped corner should have five sides and a closing point");
assert.deepEqual(
    clippedCorner.slice(3, 5),
    [[430, 500], [250, 320]],
    "The clipped-corner preset should include a visible diagonal cut"
);

assert.deepEqual(
    clampViewBox({ x: 950, y: 620, width: 250, height: 162.5 }),
    { x: 750, y: 487.5, width: 250, height: 162.5 },
    "Zoomed view boxes must stay within the paper"
);

const denseStroke = Array.from({ length: 12000 }, (_, index) => [
    index * 0.08,
    260 + Math.sin(index * 0.07) * 3,
]);
const performanceStart = Date.now();
const denseResult = normalize(denseStroke);
const performanceElapsed = Date.now() - performanceStart;
assert.ok(denseResult.length >= 2, "A dense pen stream must remain a valid stroke");
assert.ok(
    performanceElapsed < 250,
    `Live smoothing must stay responsive; received ${performanceElapsed} ms`
);

console.log("Special-shape drawing precision, editing, templates, zoom, smoothing, and eraser checks passed");
