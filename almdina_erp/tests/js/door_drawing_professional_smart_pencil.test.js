"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
global.window = { AlmdinaDoorDrawingV4: Object.create(null), AlmdinaDoorDrawingProfessional: Object.create(null) };

[
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
].forEach(file => require(path.join(root, file)));

const v4 = global.window.AlmdinaDoorDrawingV4;
const professional = global.window.AlmdinaDoorDrawingProfessional;
const documentModel = v4.DocumentModel;
const commands = v4.GeometryCommands;
const tools = v4.ToolStateMachine;

assert.equal(tools.TOOLS.PEN, "pen");
assert.equal(tools.TOOLS.SMART_PENCIL, "smart-pencil");
assert.notEqual(tools.TOOLS.PEN, tools.TOOLS.SMART_PENCIL, "path tool and smart pencil must remain separate tools");
assert.equal(tools.toolForShortcut("p"), tools.TOOLS.PEN);
assert.equal(tools.toolForShortcut("p", { shiftKey: true }), tools.TOOLS.SMART_PENCIL);

// Alignment must suggest starting/ending another line at the same X/Y level as an existing endpoint.
let alignmentDoc = documentModel.create({ widthMm: 500, heightMm: 500 });
const ids = commands.createIdFactory("align");
let started = commands.startPath(alignmentDoc, { point: { xMm: 10, yMm: 10 }, nodeId: null }, { idFactory: ids });
alignmentDoc = started.document;
let appended = commands.appendLine(alignmentDoc, started.pathId, { point: { xMm: 100, yMm: 10 }, nodeId: null }, { idFactory: ids });
alignmentDoc = appended.document;

let aligned = v4.SnapResolver.resolve(alignmentDoc, {
    rawPoint: { xMm: 102, yMm: 70 },
    toleranceMm: 4,
    releaseToleranceMm: 6,
    gridStepMm: 0,
});
assert.equal(aligned.semantic, "align-x");
assert.equal(aligned.point.xMm, 100);
assert.equal(aligned.point.yMm, 70);
assert.ok(aligned.guides.length, "point alignment must expose a visible guide");

aligned = v4.SnapResolver.resolve(alignmentDoc, {
    rawPoint: { xMm: 160, yMm: 12 },
    toleranceMm: 4,
    releaseToleranceMm: 6,
    gridStepMm: 0,
});
assert.equal(aligned.semantic, "align-y");
assert.equal(aligned.point.yMm, 10);
assert.equal(aligned.point.xMm, 160);

// A noisy freehand stroke should simplify to clean geometric segments.
const interpretedLine = v4.StrokeInterpreter.interpret([
    { xMm: 10, yMm: 10 },
    { xMm: 25, yMm: 10.4 },
    { xMm: 40, yMm: 9.7 },
    { xMm: 60, yMm: 10.2 },
    { xMm: 80, yMm: 9.8 },
    { xMm: 100, yMm: 10 },
], {
    minSampleDistanceMm: 0.2,
    simplificationToleranceMm: 2,
    closeToleranceMm: 4,
    angleToleranceDeg: 7,
});
assert.equal(interpretedLine.ok, true);
assert.equal(interpretedLine.closed, false);
assert.equal(interpretedLine.points.length, 2, "nearly straight freehand movement should become one clean segment");
assert.equal(interpretedLine.points[0].yMm, interpretedLine.points[1].yMm, "near-horizontal hand movement should straighten exactly");

const session = professional.EditorSession.create({
    document: documentModel.create({ widthMm: 500, heightMm: 500 }),
});
session.setTool(tools.TOOLS.SMART_PENCIL);
const committed = session.commitSmartStroke([
    { xMm: 20, yMm: 20 },
    { xMm: 50, yMm: 20.7 },
    { xMm: 80, yMm: 19.5 },
    { xMm: 120, yMm: 20 },
], {
    minSampleDistanceMm: 0.2,
    simplificationToleranceMm: 2,
    closeToleranceMm: 5,
    snapToleranceMm: 0,
    angleToleranceDeg: 7,
});
assert.equal(committed.kind, "smart-stroke-added");
assert.equal(committed.segmentIds.length, 1);
assert.equal(session.state().document.paths.length, 1);
assert.ok(session.state().document.constraints.some(item => item.type === "horizontal"), "smart stroke must persist inferred geometry constraints");

const afterSmartStroke = session.state().document;
assert.equal(session.undo().kind, "undo");
assert.equal(session.state().document.paths.length, 0, "one undo must remove the whole interpreted stroke");
assert.equal(session.redo().kind, "redo");
assert.deepEqual(session.state().document.paths, afterSmartStroke.paths);

session.setTool(tools.TOOLS.SMART_PENCIL);
const closed = session.commitSmartStroke([
    { xMm: 160, yMm: 80 },
    { xMm: 240, yMm: 81 },
    { xMm: 241, yMm: 160 },
    { xMm: 160, yMm: 159 },
    { xMm: 162, yMm: 82 },
], {
    minSampleDistanceMm: 0.2,
    simplificationToleranceMm: 3,
    closeToleranceMm: 8,
    snapToleranceMm: 0,
    angleToleranceDeg: 8,
});
assert.equal(closed.kind, "smart-stroke-added");
assert.equal(closed.closed, true);
const closedPath = documentModel.pathById(session.state().document, closed.pathId);
assert.equal(closedPath.closed, true, "a hand stroke returning near its start must close topologically");
assert.ok(closedPath.segmentIds.length >= 3);

console.log("Professional path alignment and smart pencil behavior passed");
