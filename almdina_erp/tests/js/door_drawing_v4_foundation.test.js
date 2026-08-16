"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("application/geometry_commands.js");
load("application/snap_resolver.js");
load("application/hit_test.js");
load("application/command_history.js");
load("application/tool_state_machine.js");
load("application/interaction_engine.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const G = V4.Geometry;
const D = V4.DocumentModel;
const T = V4.ToolStateMachine;

const engine = V4.InteractionEngine.create({ document: D.create({ widthMm: 1220, heightMm: 2440 }) });
assert.equal(engine.state().toolState.activeTool, T.TOOLS.SELECT);
engine.keyDown("p");
assert.equal(engine.state().toolState.activeTool, T.TOOLS.PEN, "P must activate the geometric smart pen");

let action = engine.pointerDown(G.point(0, 0), { toleranceMm: 6 });
assert.equal(action.kind, "path-started");
const pathId = action.activePathId;
const startNodeId = action.nodeId;

let preview = engine.pointerMove(G.point(600, 1), { toleranceMm: 6 }).preview;
assert.equal(preview.type, "angle");
assert.equal(preview.semantic, "horizontal");
action = engine.inputLength(600);
assert.equal(action.kind, "segment-added");

preview = engine.pointerMove(G.point(602, 1200), { toleranceMm: 6 }).preview;
assert.equal(preview.type, "angle");
assert.equal(preview.semantic, "vertical");
engine.inputLength(1200);

preview = engine.pointerMove(G.point(0, 1198), { toleranceMm: 6 }).preview;
assert.equal(preview.type, "angle");
assert.equal(preview.semantic, "horizontal");
engine.inputLength(600);

preview = engine.pointerMove(G.point(2, 3), { toleranceMm: 6 }).preview;
assert.equal(preview.type, "endpoint");
assert.equal(preview.semantic, "endpoint");
assert.equal(preview.nodeId, startNodeId, "near-start preview must target the original shared node");
action = engine.pointerDown(G.point(2, 3), { toleranceMm: 6 });
assert.equal(action.kind, "path-closed");
assert.equal(action.activePathId, null);

const document = engine.state().document;
const rectangle = D.pathById(document, pathId);
assert.equal(rectangle.closed, true);
assert.equal(rectangle.segmentIds.length, 4, "rectangle must have four manufacturing edges");
assert.equal(document.nodes.length, 4, "closing must reuse the first node instead of creating a duplicate point");
assert.equal(document.segments.length, 4);
const lastSegment = D.segmentById(document, rectangle.segmentIds.at(-1));
assert.equal(lastSegment.endNodeId, startNodeId, "closing edge must reference the exact first node id");
assert.deepEqual(document.nodes.map(node => [node.xMm, node.yMm]), [[0, 0], [600, 0], [600, 1200], [0, 1200]]);

engine.pointerDown(G.point(600, 2), { toleranceMm: 6 });
assert.equal(engine.state().document.nodes.length, 4, "a new path started on an endpoint must share the existing node");
assert.equal(engine.state().document.paths.length, 2);
assert.equal(D.pathById(engine.state().document, engine.state().activePathId).startNodeId, document.nodes[1].id);

engine.spaceDown();
assert.equal(engine.state().toolState.activeTool, T.TOOLS.HAND);
engine.spaceUp();
assert.equal(engine.state().toolState.activeTool, T.TOOLS.PEN, "Space hand tool must restore the previous tool");
engine.keyDown("v");
assert.equal(engine.state().toolState.activeTool, T.TOOLS.SELECT);
assert.equal(engine.state().activePathId, null, "leaving the pen must end only the interaction session, not corrupt geometry");

console.log("Door Drawing V4 foundation tests passed");