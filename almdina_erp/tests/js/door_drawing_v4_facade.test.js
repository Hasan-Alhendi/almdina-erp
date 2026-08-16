"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/special_shape_facade.js"));

const facade = global.window.AlmdinaSpecialShapeEditor;
const bootstrap = global.window.AlmdinaDoorDrawingV4Bootstrap;

assert.ok(facade, "active special-shape facade must be registered");
assert.equal(facade.__doorDrawingV4, true);
assert.equal(facade.__canonicalMmGeometry, true);
assert.equal(facade.__sharedNodeTopology, true);
assert.equal(facade.__singleInteractionOwner, true);
assert.equal(facade.__highDpiCanvas, true);

assert.ok(bootstrap, "V4 bootstrap must be registered");
assert.ok(bootstrap.SCRIPTS.length > 0);
assert.ok(bootstrap.SCRIPTS.every(src => src.includes("/door_drawing_v4/")), "active facade must load V4 modules only");
assert.ok(bootstrap.SCRIPTS.every(src => !src.includes("door_drawing_v3")), "active facade must never load V3 modules");
assert.equal(global.window.AlmdinaDoorDrawingV3Bootstrap, undefined, "legacy bootstrap must not be exposed by the active facade");

const raw = JSON.stringify({
    schema: "almdina.door-drawing",
    version: 4,
    units: "mm",
    blank: { widthMm: 600, heightMm: 1200 },
    nodes: [
        { id: "n1", xMm: 0, yMm: 0 },
        { id: "n2", xMm: 600, yMm: 0 },
    ],
    segments: [
        { id: "s1", type: "line", startNodeId: "n1", endNodeId: "n2" },
    ],
    paths: [
        { id: "p1", startNodeId: "n1", segmentIds: ["s1"], closed: false },
    ],
});
const drawing = facade.parseDrawing(raw);
assert.equal(drawing.length, 1);
assert.deepEqual(drawing[0], {
    id: "s1",
    type: "line",
    start: { xMm: 0, yMm: 0 },
    end: { xMm: 600, yMm: 0 },
});
assert.deepEqual(facade.parseDrawing(JSON.stringify({ version: 1 })), []);

console.log("Door Drawing V4 facade tests passed");