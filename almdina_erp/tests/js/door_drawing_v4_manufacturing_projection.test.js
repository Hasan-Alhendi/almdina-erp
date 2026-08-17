"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("application/manufacturing_projection.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const D = V4.DocumentModel;
const P = V4.ManufacturingProjection;

function rectangle(overrides = {}) {
    return D.create({
        widthMm: 600,
        heightMm: 1200,
        nodes: [
            { id: "n1", xMm: 0, yMm: 0 },
            { id: "n2", xMm: 600, yMm: 0 },
            { id: "n3", xMm: 600, yMm: 1200 },
            { id: "n4", xMm: 0, yMm: 1200 },
        ],
        segments: [
            { id: "s1", startNodeId: "n1", endNodeId: "n2" },
            { id: "s2", startNodeId: "n2", endNodeId: "n3" },
            { id: "s3", startNodeId: "n3", endNodeId: "n4" },
            { id: "s4", startNodeId: "n4", endNodeId: "n1" },
        ],
        paths: [{
            id: "p1",
            startNodeId: "n1",
            segmentIds: ["s1", "s2", "s3", "s4"],
            closed: true,
        }],
        ...overrides,
    });
}

let result = P.project(rectangle());
assert.equal(result.ok, true);
assert.deepEqual(result.geometry, {
    version: 1,
    kind: "polygon",
    units: "cm",
    template: "custom",
    blank_width_cm: 60,
    blank_length_cm: 120,
    points: [
        [0, 0],
        [60, 0],
        [60, 120],
        [0, 120],
    ],
    exact: true,
});
assert.equal(result.geometry.points.length, 4, "closing node must not be duplicated in manufacturing polygon");

result = P.project(rectangle({
    paths: [{ id: "p1", startNodeId: "n1", segmentIds: ["s1", "s2", "s3"], closed: false }],
}));
assert.equal(result.ok, false);
assert.equal(result.code, "open-boundary");

result = P.project(rectangle({
    paths: [
        { id: "p1", startNodeId: "n1", segmentIds: ["s1", "s2", "s3", "s4"], closed: true },
        { id: "cancelled", startNodeId: "n1", segmentIds: [], closed: false },
    ],
}));
assert.equal(result.ok, true, "a cancelled click-only path must not block a valid manufacturing boundary");

result = P.project(rectangle({
    paths: [
        { id: "p1", startNodeId: "n1", segmentIds: ["s1", "s2", "s3", "s4"], closed: true },
        { id: "p2", startNodeId: "n1", segmentIds: ["s1"], closed: false },
    ],
}));
assert.equal(result.ok, false);
assert.equal(result.code, "ambiguous-boundary");

const broken = rectangle();
const brokenSerialized = JSON.parse(JSON.stringify(broken));
brokenSerialized.paths[0].segmentIds[1] = "missing";
result = P.project(brokenSerialized);
assert.equal(result.ok, false);
assert.equal(result.code, "missing-segment");

const disconnected = rectangle();
const disconnectedSerialized = JSON.parse(JSON.stringify(disconnected));
disconnectedSerialized.segments[1].startNodeId = "n1";
result = P.project(disconnectedSerialized);
assert.equal(result.ok, false);
assert.equal(result.code, "disconnected-boundary");

console.log("Door Drawing V4 manufacturing projection tests passed");
