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

const interaction = window.AlmdinaSketchInteraction;

assert.equal(interaction.SMART_ENDPOINT_SNAP_RADIUS, 24);

let resolved = interaction.resolveLineEndpoint(
    { x: 100, y: 100 },
    { x: 190, y: 155 },
    [],
    true,
    18
);
assert.deepEqual(
    resolved.endpoint,
    { x: 190, y: 100 },
    "Shift must hard-lock a mostly horizontal drag to the horizontal axis"
);
assert.equal(resolved.axis, "horizontal");

resolved = interaction.resolveLineEndpoint(
    { x: 100, y: 100 },
    { x: 125, y: 210 },
    [],
    true,
    18
);
assert.deepEqual(
    resolved.endpoint,
    { x: 100, y: 210 },
    "Shift must hard-lock a mostly vertical drag to the vertical axis"
);
assert.equal(resolved.axis, "vertical");

const firstLine = {
    id: "line-1",
    type: "line",
    x1: 100,
    y1: 100,
    x2: 220,
    y2: 100,
    color: "#172033",
};

const started = interaction.beginDraft({
    tool: "line",
    point: { x: 228, y: 106 },
    elements: [firstLine],
    snapRadius: 18,
    id: "line-2",
});
assert.deepEqual(
    started.start,
    { x: 220, y: 100 },
    "A new line must magnetically start from a nearby existing endpoint"
);
assert.deepEqual(started.snapPoint, { x: 220, y: 100 });

resolved = interaction.resolveLineEndpoint(
    { x: 100, y: 100 },
    { x: 214, y: 103 },
    [firstLine],
    true,
    18
);
assert.deepEqual(
    resolved.endpoint,
    { x: 220, y: 100 },
    "A Shift-locked line should still snap to an endpoint that lies on the locked axis"
);
assert.deepEqual(resolved.snapPoint, { x: 220, y: 100 });

const offAxisLine = {
    id: "line-off-axis",
    type: "line",
    x1: 180,
    y1: 120,
    x2: 220,
    y2: 120,
    color: "#172033",
};
resolved = interaction.resolveLineEndpoint(
    { x: 100, y: 100 },
    { x: 218, y: 119 },
    [offAxisLine],
    true,
    18
);
assert.equal(
    resolved.endpoint.y,
    100,
    "Endpoint magnetism must never break the Shift axis lock"
);
assert.equal(
    resolved.snapPoint,
    null,
    "Off-axis anchors should be ignored while Shift is held"
);

resolved = interaction.resolveLineEndpoint(
    { x: 100, y: 100 },
    { x: 200, y: 108 },
    [],
    false,
    18
);
assert.equal(
    resolved.endpoint.y,
    100,
    "Near-horizontal lines should still receive the existing soft automatic alignment"
);

console.log("Smart line axis locking and endpoint magnetism passed");
