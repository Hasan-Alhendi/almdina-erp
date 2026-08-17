"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
global.window = { AlmdinaDoorDrawingV4: Object.create(null), AlmdinaDoorDrawingProfessional: Object.create(null) };

const modules = [
    "public/js/door_drawing_v4/domain/geometry.js",
    "public/js/door_drawing_v4/domain/document.js",
    "public/js/door_drawing_v4/domain/dimension.js",
    "public/js/door_drawing_v4/domain/constraint.js",
    "public/js/door_drawing_v4/application/geometry_commands.js",
    "public/js/door_drawing_v4/application/dimension_commands.js",
    "public/js/door_drawing_v4/application/constraint_commands.js",
    "public/js/door_drawing_v4/application/constraint_solver.js",
    "public/js/door_drawing_v4/application/constraint_inference.js",
    "public/js/door_drawing_v4/application/driving_dimension_commands.js",
    "public/js/door_drawing_v4/application/snap_resolver.js",
    "public/js/door_drawing_v4/application/point_alignment_snap.js",
    "public/js/door_drawing_v4/application/stroke_interpreter.js",
    "public/js/door_drawing_v4/application/hit_test.js",
    "public/js/door_drawing_v4/application/command_history.js",
    "public/js/door_drawing_v4/application/tool_state_machine.js",
    "public/js/door_drawing_v4/professional/editor_session.js",
];
modules.forEach(file => require(path.join(root, file)));

const v4 = global.window.AlmdinaDoorDrawingV4;
const professional = global.window.AlmdinaDoorDrawingProfessional;
const documentModel = v4.DocumentModel;
const tools = v4.ToolStateMachine;
const geometry = v4.Geometry;

const session = professional.EditorSession.create({
    document: documentModel.create({ widthMm: 500, heightMm: 500 }),
});
const interaction = { toleranceMm: 4, releaseToleranceMm: 6, hitToleranceMm: 4, gridStepMm: 0 };

session.setTool(tools.TOOLS.PEN);
assert.equal(session.state().toolState.activeTool, "pen");
assert.equal(session.pointerDown({ xMm: 10, yMm: 10 }, interaction).kind, "path-started");

let moved = session.pointerMove({ xMm: 100, yMm: 11 }, interaction);
assert.equal(moved.preview.semantic, "horizontal", "Path tool must infer horizontal intent near the axis");
let added = session.pointerDown({ xMm: 100, yMm: 11 }, interaction);
assert.equal(added.kind, "segment-added");
let firstSegment = documentModel.segmentById(session.state().document, added.segmentId);
let firstStart = documentModel.nodeById(session.state().document, firstSegment.startNodeId);
let firstEnd = documentModel.nodeById(session.state().document, firstSegment.endNodeId);
assert.equal(firstStart.yMm, firstEnd.yMm, "horizontal snap must become exact geometry");
assert.ok(session.state().document.constraints.some(item => item.segmentId === added.segmentId && item.type === "horizontal"), "horizontal intent must persist as a constraint");

moved = session.pointerMove({ xMm: 101, yMm: 100 }, interaction);
assert.equal(moved.preview.semantic, "vertical", "Path tool must infer vertical intent near the axis");
added = session.pointerDown({ xMm: 101, yMm: 100 }, interaction);
assert.ok(session.state().document.constraints.some(item => item.segmentId === added.segmentId && item.type === "vertical"), "vertical intent must persist as a constraint");

moved = session.pointerMove({ xMm: 11, yMm: 11 }, interaction);
assert.equal(moved.preview.semantic, "close", "approaching the first node must offer smart close");
const closed = session.pointerDown({ xMm: 11, yMm: 11 }, interaction);
assert.equal(closed.kind, "path-closed");
const closedPath = documentModel.pathById(session.state().document, closed.pathId);
assert.equal(closedPath.closed, true);
assert.equal(documentModel.pathEndNodeId(session.state().document, closed.pathId), closedPath.startNodeId, "smart close must be topological, not visual overlap");

// Auto inferred H/V constraints must remain editable with A. Moving the shared corner
// pins the dragged node and lets the solver move adjacent endpoints to preserve relations.
session.setTool(tools.TOOLS.NODE);
const horizontalConstraint = session.state().document.constraints.find(item => item.type === "horizontal");
const horizontalSegment = documentModel.segmentById(session.state().document, horizontalConstraint.segmentId);
const cornerId = horizontalSegment.endNodeId;
const cornerBefore = documentModel.nodeById(session.state().document, cornerId);
const dragStart = session.pointerDown({ xMm: cornerBefore.xMm, yMm: cornerBefore.yMm }, { ...interaction, hitToleranceMm: 2 });
assert.equal(dragStart.kind, "node-drag-started", "A must allow dragging nodes with inferred axis constraints");
session.pointerMove({ xMm: cornerBefore.xMm + 20, yMm: cornerBefore.yMm + 10 }, { ...interaction, toleranceMm: 1, releaseToleranceMm: 1 });
const dragEnd = session.pointerUp();
assert.equal(dragEnd.kind, "node-drag-finished");
const cornerAfter = documentModel.nodeById(session.state().document, cornerId);
assert.ok(geometry.distance(cornerBefore, cornerAfter) > 1, "the constrained node must actually move");
for (const constraint of session.state().document.constraints.filter(item => ["horizontal", "vertical"].includes(item.type))) {
    const segment = documentModel.segmentById(session.state().document, constraint.segmentId);
    const start = documentModel.nodeById(session.state().document, segment.startNodeId);
    const end = documentModel.nodeById(session.state().document, segment.endNodeId);
    if (constraint.type === "horizontal") assert.equal(start.yMm, end.yMm);
    if (constraint.type === "vertical") assert.equal(start.xMm, end.xMm);
}

const afterDrag = session.state().document;
assert.equal(session.undo().kind, "undo");
assert.notDeepEqual(session.state().document.nodes, afterDrag.nodes, "node drag must be one undoable semantic command");
assert.equal(session.redo().kind, "redo");
assert.deepEqual(session.state().document.nodes, afterDrag.nodes);

console.log("Professional path tool and node editing behavior passed");
