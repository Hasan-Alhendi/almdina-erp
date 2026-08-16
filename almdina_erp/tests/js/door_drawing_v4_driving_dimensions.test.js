"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("domain/dimension.js");
load("domain/constraint.js");
load("application/geometry_commands.js");
load("application/dimension_commands.js");
load("application/constraint_commands.js");
load("application/constraint_solver.js");
load("application/constraint_inference.js");
load("application/driving_dimension_commands.js");
load("application/snap_resolver.js");
load("application/hit_test.js");
load("application/command_history.js");
load("application/tool_state_machine.js");
load("application/interaction_engine.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const D = V4.DocumentModel;
const DimensionDomain = V4.DimensionDomain;
const Driving = V4.DrivingDimensionCommands;
const T = V4.ToolStateMachine;

function rectangleWithDimension() {
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
        paths: [{ id: "p1", startNodeId: "n1", segmentIds: ["s1", "s2", "s3", "s4"], closed: true }],
        dimensions: [{ id: "d1", type: D.DIMENSION_TYPES.SEGMENT_LENGTH, segmentId: "s1" }],
    });
}

const reference = rectangleWithDimension();
assert.equal(reference.constraints.length, 0);
assert.equal(DimensionDomain.resolve(reference, "d1").driving, false);
assert.equal(DimensionDomain.resolve(reference, "d1").valueMm, 600);

const driven = Driving.drive(reference, "d1", 750, {
    idFactory: (() => {
        let index = 0;
        return kind => `auto-${kind}-${++index}`;
    })(),
});
assert.equal(driven.ok, true);
assert.equal(driven.measurement.driving, true);
assert.equal(driven.measurement.valueMm, 750);
assert.equal(driven.document.constraints.length, 5, "four inferred axis constraints plus one fixed length are expected");
assert.deepEqual(driven.document.constraints.map(constraint => constraint.type).sort(), [
    D.CONSTRAINT_TYPES.FIXED_LENGTH,
    D.CONSTRAINT_TYPES.HORIZONTAL,
    D.CONSTRAINT_TYPES.HORIZONTAL,
    D.CONSTRAINT_TYPES.VERTICAL,
    D.CONSTRAINT_TYPES.VERTICAL,
].sort());
assert.deepEqual(driven.document.nodes.map(node => [node.id, node.xMm, node.yMm]), [
    ["n1", 0, 0],
    ["n2", 750, 0],
    ["n3", 750, 1200],
    ["n4", 0, 1200],
]);

const released = Driving.release(driven.document, "d1");
assert.equal(released.ok, true);
assert.equal(released.changed, true);
assert.equal(DimensionDomain.resolve(released.document, "d1").driving, false);
assert.equal(released.document.constraints.filter(constraint => constraint.type === D.CONSTRAINT_TYPES.FIXED_LENGTH).length, 0);
assert.equal(released.document.constraints.length, 4, "releasing a dimension removes only its fixed-length driver");

const engine = V4.InteractionEngine.create({ document: reference });
engine.keyDown("d");
assert.equal(engine.state().toolState.activeTool, T.TOOLS.DIMENSION);
let action = engine.pointerDown({ xMm: 300, yMm: 0 }, { hitToleranceMm: 4 });
assert.equal(action.kind, "dimension-selected");
assert.deepEqual(engine.state().selection, { kind: "dimension", id: "d1" });
assert.equal(engine.state().history.undoCount, 0);

action = engine.inputDimensionValue(800);
assert.equal(action.kind, "dimension-driven");
assert.equal(action.measurement.valueMm, 800);
assert.equal(action.measurement.driving, true);
assert.equal(engine.state().history.undoCount, 1, "driving a dimension must be one semantic undo step");
assert.deepEqual(engine.state().document.nodes.map(node => [node.id, node.xMm, node.yMm]), [
    ["n1", 0, 0],
    ["n2", 800, 0],
    ["n3", 800, 1200],
    ["n4", 0, 1200],
]);

engine.undo();
assert.deepEqual(engine.state().document.nodes, reference.nodes);
assert.deepEqual(engine.state().document.constraints, [], "undo must remove inferred and fixed constraints together");
assert.equal(DimensionDomain.resolve(engine.state().document, "d1").driving, false);
assert.equal(engine.state().history.redoCount, 1);

engine.redo();
assert.equal(DimensionDomain.resolve(engine.state().document, "d1").valueMm, 800);
assert.equal(DimensionDomain.resolve(engine.state().document, "d1").driving, true);
assert.equal(engine.state().constraints, undefined, "constraints stay inside the canonical document, not interaction side state");

const constrainedDocument = engine.state().document;
const undoCountBeforeProtectedDrag = engine.state().history.undoCount;
engine.keyDown("a");
assert.equal(engine.state().toolState.activeTool, T.TOOLS.NODE);
action = engine.pointerDown({ xMm: 800, yMm: 0 }, { hitToleranceMm: 4 });
assert.equal(action.kind, "constraint-protected-node", "constrained nodes must not enter free-drag mode");
assert.equal(action.nodeId, "n2");
assert.ok(action.constraintIds.length >= 2, "the protected node must report its attached constraints");
assert.equal(engine.state().drag, null);
engine.pointerMove({ xMm: 900, yMm: 100 });
engine.pointerUp();
assert.equal(engine.state().document, constrainedDocument, "protected drag attempts must not mutate constrained geometry");
assert.equal(engine.state().history.undoCount, undoCountBeforeProtectedDrag, "protected drag attempts must not create history");

console.log("Door Drawing V4 driving dimension tests passed");
