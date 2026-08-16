"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("domain/dimension.js");
load("application/geometry_commands.js");
load("application/dimension_commands.js");
load("application/manufacturing_projection.js");
load("application/snap_resolver.js");
load("application/hit_test.js");
load("application/command_history.js");
load("application/tool_state_machine.js");
load("application/interaction_engine.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const G = V4.Geometry;
const D = V4.DocumentModel;
const Dimensions = V4.DimensionDomain;
const DimensionCommands = V4.DimensionCommands;
const Manufacturing = V4.ManufacturingProjection;
const T = V4.ToolStateMachine;

function rectangle() {
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
        paths: [
            { id: "p1", startNodeId: "n1", segmentIds: ["s1", "s2", "s3", "s4"], closed: true },
        ],
    });
}

let document = rectangle();
assert.deepEqual(document.dimensions, []);
assert.equal(T.toolForShortcut("d"), T.TOOLS.DIMENSION);

let result = DimensionCommands.ensureSegmentLength(document, "s1", { id: "d1" });
assert.equal(result.created, true);
document = result.document;
assert.equal(document.dimensions.length, 1);
assert.deepEqual(document.dimensions[0], {
    id: "d1",
    type: D.DIMENSION_TYPES.SEGMENT_LENGTH,
    segmentId: "s1",
});
assert.equal(result.measurement.valueMm, 600);
assert.equal(Dimensions.resolve(document, "d1").valueMm, 600);

// Dimensions are references to geometry, never cached numeric copies.
const movedDocument = D.moveNode(document, "n2", G.point(750, 0));
assert.equal(Dimensions.resolve(movedDocument, "d1").valueMm, 750);
assert.equal(Object.hasOwn(movedDocument.dimensions[0], "valueMm"), false);

// Adding the same semantic dimension twice is idempotent.
result = DimensionCommands.ensureSegmentLength(document, "s1", { id: "ignored" });
assert.equal(result.created, false);
assert.equal(result.dimensionId, "d1");
assert.equal(result.document, document);
assert.equal(result.document.dimensions.length, 1);

// Manufacturing projection is geometry-only and unaffected by annotations.
const projected = Manufacturing.project(document);
assert.equal(projected.ok, true);
assert.deepEqual(projected.geometry.points, [
    [0, 0],
    [60, 0],
    [60, 120],
    [0, 120],
]);

// Interaction: D + click on a segment creates one persistent annotation and one history step.
const engine = V4.InteractionEngine.create({ document: rectangle() });
engine.keyDown("d");
assert.equal(engine.state().toolState.activeTool, T.TOOLS.DIMENSION);
let action = engine.pointerDown(G.point(300, 2), { hitToleranceMm: 5 });
assert.equal(action.kind, "dimension-added");
assert.equal(action.segmentId, "s1");
assert.equal(action.measurement.valueMm, 600);
assert.equal(engine.state().document.dimensions.length, 1);
assert.equal(engine.state().history.undoCount, 1);
assert.equal(engine.state().selection.kind, "dimension");
const createdDimensionId = action.dimensionId;

// Re-click selects the same dimension and does not create another history entry.
action = engine.pointerDown(G.point(300, 1), { hitToleranceMm: 5 });
assert.equal(action.kind, "dimension-selected");
assert.equal(action.dimensionId, createdDimensionId);
assert.equal(engine.state().document.dimensions.length, 1);
assert.equal(engine.state().history.undoCount, 1);

engine.undo();
assert.equal(engine.state().document.dimensions.length, 0, "undo must remove the annotation without changing geometry");
assert.equal(engine.state().document.segments.length, 4);
assert.equal(engine.state().history.redoCount, 1);
engine.redo();
assert.equal(engine.state().document.dimensions.length, 1, "redo must restore the same semantic annotation");
assert.equal(engine.state().document.dimensions[0].id, createdDimensionId);
assert.equal(Dimensions.resolve(engine.state().document, createdDimensionId).valueMm, 600);

console.log("Door Drawing V4 dimension foundation tests passed");
