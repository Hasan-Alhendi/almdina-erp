"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("infrastructure/persistence_adapter.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const D = V4.DocumentModel;
const P = V4.PersistenceAdapter;

const row = { width_cm: 60, length_cm: 120 };
assert.deepEqual(P.rowBlankMm(row), { widthMm: 600, heightMm: 1200 });

const document = D.create({
    widthMm: 600,
    heightMm: 1200,
    nodes: [
        { id: "n1", xMm: 0, yMm: 0 },
        { id: "n2", xMm: 600, yMm: 0 },
    ],
    segments: [
        { id: "s1", startNodeId: "n1", endNodeId: "n2" },
    ],
    paths: [
        { id: "p1", startNodeId: "n1", segmentIds: ["s1"], closed: false },
    ],
    dimensions: [
        { id: "d1", type: D.DIMENSION_TYPES.SEGMENT_LENGTH, segmentId: "s1" },
    ],
});

const stored = P.toStored(document);
const parsed = JSON.parse(stored);
assert.equal(parsed.schema, "almdina.door-drawing");
assert.equal(parsed.version, 4);
assert.equal(parsed.units, "mm");
assert.equal(parsed.meta, undefined, "V4 storage must not create a legacy compatibility envelope");
assert.equal(parsed.nodes.length, 2);
assert.equal(parsed.segments.length, 1);
assert.deepEqual(parsed.dimensions, [
    { id: "d1", type: "segment-length", segmentId: "s1" },
]);

const restored = P.fromStored(stored, row);
assert.equal(restored.schema, D.SCHEMA);
assert.equal(restored.version, D.VERSION);
assert.deepEqual(restored.blank, { widthMm: 600, heightMm: 1200 });
assert.equal(restored.nodes.length, 2);
assert.equal(restored.segments.length, 1);
assert.equal(restored.paths.length, 1);
assert.deepEqual(restored.dimensions, [
    { id: "d1", type: "segment-length", segmentId: "s1" },
]);

const withoutDimensions = P.fromStored(JSON.stringify({
    schema: D.SCHEMA,
    version: D.VERSION,
    units: D.UNITS,
    blank: { widthMm: 600, heightMm: 1200 },
    nodes: [],
    segments: [],
    paths: [],
}), row);
assert.deepEqual(withoutDimensions.dimensions, [], "pre-dimension V4 documents must remain valid");

const legacyPayload = JSON.stringify({ version: 1, meta: { door_drawing_v3: { schema: "almdina.door-drawing", version: 3 } } });
const ignoredLegacy = P.fromStored(legacyPayload, row);
assert.equal(ignoredLegacy.nodes.length, 0, "legacy drawings are intentionally ignored in the clean V4 development reset");
assert.equal(ignoredLegacy.segments.length, 0);
assert.equal(ignoredLegacy.dimensions.length, 0);
assert.deepEqual(ignoredLegacy.blank, { widthMm: 600, heightMm: 1200 });

console.log("Door Drawing V4 persistence tests passed");