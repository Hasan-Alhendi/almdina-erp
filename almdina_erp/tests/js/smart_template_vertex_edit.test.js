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
    "../../public/js/door_cutting_order_sketch_history.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_renderer.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_smart_guides.js"
));

const history = window.AlmdinaSketchHistory;
const guides = window.AlmdinaSketchSmartGuides;

const state = history.createState([]);
assert.equal(history.getActiveState(), state, "Extensions must receive the live editor state");
history.clearActiveState(state);
assert.equal(history.getActiveState(), null, "Closed editors must be able to release active state");

const rectangle = [
    [100, 100],
    [500, 100],
    [500, 400],
    [100, 400],
    [100, 100],
];

let resolved = guides.snapTemplateVertex(
    rectangle,
    2,
    [493, 394],
    { threshold: 14, width: 1000, height: 650 }
);
assert.deepEqual(
    resolved.point,
    [500, 400],
    "Template vertices should magnetically align to existing template axes"
);
assert.equal(resolved.guides.x, 500);
assert.equal(resolved.guides.y, 400);

resolved = guides.snapTemplateVertex(
    rectangle,
    1,
    [610, 135],
    {
        originalPoint: [500, 100],
        shiftKey: true,
        threshold: 5,
        width: 1000,
        height: 650,
    }
);
assert.equal(
    resolved.point[1],
    100,
    "Shift while moving a template point must constrain movement to one axis"
);

resolved = guides.snapTemplateVertex(
    rectangle,
    1,
    [702, 206],
    {
        threshold: 10,
        width: 1000,
        height: 650,
        externalAnchors: [[700, 210]],
    }
);
assert.deepEqual(
    resolved.point,
    [700, 210],
    "Template points should also align with anchors from nearby drawing elements"
);

const moved = guides.applyClosedVertex(rectangle, 0, [120, 130]);
assert.deepEqual(moved[0], [120, 130]);
assert.deepEqual(
    moved[moved.length - 1],
    [120, 130],
    "Moving the first vertex must preserve the closed contour"
);

assert.equal(guides.uniqueClosedPoints(rectangle).length, 4);

console.log("Smart template magnetic vertex editing passed");
