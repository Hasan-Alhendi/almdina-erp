"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_engine.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_interaction.js"
));

const interaction = global.window.AlmdinaSketchInteraction;

assert.equal(Object.isFrozen(interaction), true, "The interaction API should be immutable");
assert.equal(
    Object.isFrozen(interaction.DRAWING_TOOLS),
    true,
    "The supported drawing tools should be immutable"
);
assert.deepEqual(
    interaction.DRAWING_TOOLS,
    ["pen", "line", "rectangle", "ellipse", "dimension"]
);

const existingElements = [{
    id: "line-existing",
    type: "line",
    x1: 100,
    y1: 100,
    x2: 300,
    y2: 100,
}];
const snappedStart = interaction.beginDraft({
    tool: "line",
    point: { x: 111, y: 106 },
    elements: existingElements,
    id: "line-1",
    color: "#1769aa",
});
assert.deepEqual(snappedStart.start, { x: 100, y: 100 });
assert.deepEqual(snappedStart.snapPoint, { x: 100, y: 100 });
assert.deepEqual(snappedStart.draft, {
    id: "line-1",
    type: "line",
    color: "#1769aa",
    x1: 100,
    y1: 100,
    x2: 100,
    y2: 100,
});

const rectangle = interaction.beginDraft({
    tool: "rectangle",
    point: { x: 240, y: 180 },
    id: "rectangle-1",
});
assert.deepEqual(rectangle.draft, {
    id: "rectangle-1",
    type: "rectangle",
    color: "#172033",
    x: 240,
    y: 180,
    width: 0,
    height: 0,
});
assert.equal(rectangle.snapPoint, null);

const ellipse = interaction.beginDraft({
    tool: "ellipse",
    point: { x: 200, y: 160 },
    id: "ellipse-1",
});
assert.deepEqual(ellipse.draft, {
    id: "ellipse-1",
    type: "ellipse",
    color: "#172033",
    cx: 200,
    cy: 160,
    rx: 0,
    ry: 0,
});
assert.equal(interaction.beginDraft({ tool: "select", point: { x: 1, y: 2 } }).draft, null);
assert.equal(interaction.beginDraft({ tool: "line", point: { x: "bad", y: 2 } }).draft, null);

const lineInput = {
    id: "line-2",
    type: "line",
    color: "#172033",
    x1: 0,
    y1: 0,
    x2: 0,
    y2: 0,
};
const lineBefore = JSON.stringify(lineInput);
const updatedLine = interaction.updateDraft({
    draft: lineInput,
    start: { x: 0, y: 0 },
    point: { x: 92, y: 4 },
    elements: [{
        id: "line-anchor",
        type: "line",
        x1: 100,
        y1: 0,
        x2: 200,
        y2: 0,
    }],
});
assert.equal(JSON.stringify(lineInput), lineBefore, "Draft transitions must not mutate their input");
assert.equal(updatedLine.draft.x2, 100);
assert.equal(updatedLine.draft.y2, 0);
assert.deepEqual(updatedLine.snapPoint, { x: 100, y: 0 });

const angledLine = interaction.updateDraft({
    draft: lineInput,
    start: { x: 0, y: 0 },
    point: { x: 90, y: 40 },
    forceAngle: true,
});
const angle = Math.atan2(angledLine.draft.y2, angledLine.draft.x2);
assert.ok(
    Math.abs(angle - Math.PI / 6) < 0.001,
    "Shift-constrained lines should snap to 15-degree intervals"
);

const reversedRectangle = interaction.updateDraft({
    draft: rectangle.draft,
    start: rectangle.start,
    point: { x: 120, y: 80 },
});
assert.deepEqual(
    {
        x: reversedRectangle.draft.x,
        y: reversedRectangle.draft.y,
        width: reversedRectangle.draft.width,
        height: reversedRectangle.draft.height,
    },
    { x: 120, y: 80, width: 120, height: 100 }
);

const updatedEllipse = interaction.updateDraft({
    draft: ellipse.draft,
    start: ellipse.start,
    point: { x: 320, y: 240 },
});
assert.deepEqual(
    {
        cx: updatedEllipse.draft.cx,
        cy: updatedEllipse.draft.cy,
        rx: updatedEllipse.draft.rx,
        ry: updatedEllipse.draft.ry,
    },
    { cx: 260, cy: 200, rx: 60, ry: 40 }
);

const pen = interaction.beginDraft({
    tool: "pen",
    point: { x: 0, y: 0 },
    id: "pen-1",
});
const updatedPen = interaction.updateDraft({
    draft: pen.draft,
    start: pen.start,
    penPoints: [[0.5, 0], [2, 0], [3, 0]],
    finalPenPoint: [2.4, 0],
});
assert.deepEqual(
    updatedPen.draft.points,
    [[0, 0], [2, 0], [2.4, 0]],
    "Coalesced points should be filtered without dropping the precise final point"
);
assert.deepEqual(interaction.appendPenPoints(null, []), null);

const closingPen = {
    id: "pen-closing",
    type: "pen",
    points: [
        [0, 0], [20, 0], [40, 0], [40, 20], [40, 40],
        [20, 40], [0, 40], [0, 20], [0, 10], [2, 1],
    ],
};
assert.deepEqual(
    interaction.penSnapPoint(closingPen, []),
    { x: 0, y: 0 },
    "A sufficiently long outline should advertise closure at its starting point"
);
assert.deepEqual(
    interaction.penSnapPoint({
        id: "pen-anchor",
        type: "pen",
        points: [[20, 20], [108, 104]],
    }, existingElements),
    { x: 100, y: 100 },
    "A pen endpoint should advertise a nearby existing anchor"
);

const acceptedPen = interaction.finalizeDraft({
    draft: {
        id: "pen-final",
        type: "pen",
        points: [[0, 0], [50, 2], [100, 0]],
    },
    elements: [],
});
assert.equal(acceptedPen.accepted, true);
assert.equal(acceptedPen.needsText, false);
assert.ok(acceptedPen.element.points.length >= 2);

for (const draft of [
    { id: "tiny-line", type: "line", x1: 0, y1: 0, x2: 3, y2: 0 },
    { id: "tiny-rect", type: "rectangle", x: 0, y: 0, width: 3, height: 9 },
    { id: "tiny-ellipse", type: "ellipse", cx: 5, cy: 5, rx: 1, ry: 4 },
]) {
    const result = interaction.finalizeDraft({ draft });
    assert.equal(result.accepted, false);
    assert.equal(result.reason, "too-small");
}

const dimension = interaction.finalizeDraft({
    draft: {
        id: "dimension-1",
        type: "dimension",
        x1: 10,
        y1: 20,
        x2: 210,
        y2: 20,
    },
});
assert.equal(dimension.accepted, true);
assert.equal(dimension.needsText, true);

const cancelled = interaction.finalizeDraft({
    draft: lineInput,
    cancelled: true,
});
assert.equal(cancelled.accepted, false);
assert.equal(cancelled.reason, "cancelled");

console.log("Pure special-shape draft interaction checks passed");
