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
const H = V4.HitTest;
const T = V4.ToolStateMachine;

const rectangle = D.create({
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
});

assert.equal(H.node(rectangle, G.point(598, 3), 5).id, "n2");
assert.equal(H.segment(rectangle, G.point(300, 2), 5).id, "s1");
assert.equal(H.selectPath(rectangle, G.point(300, 2), 5).id, "p1");
assert.equal(H.selectPath(rectangle, G.point(300, 30), 5), null);

const engine = V4.InteractionEngine.create({ document: rectangle });
let action = engine.pointerDown(G.point(300, 2), { hitToleranceMm: 5 });
assert.equal(action.kind, "path-selected");
assert.deepEqual(engine.state().selection, { kind: "path", id: "p1" });

engine.keyDown("a");
assert.equal(engine.state().toolState.activeTool, T.TOOLS.NODE);
action = engine.pointerDown(G.point(598, 3), { hitToleranceMm: 6 });
assert.equal(action.kind, "node-drag-started");
assert.deepEqual(engine.state().selection, { kind: "node", id: "n2" });
assert.equal(engine.state().history.undoCount, 0, "starting a drag must not create history");

for (let index = 1; index <= 20; index += 1) {
    engine.pointerMove(G.point(600 + index, index * 2));
}
assert.deepEqual(D.nodeById(engine.state().document, "n2"), { id: "n2", xMm: 620, yMm: 40 });
assert.equal(engine.state().history.undoCount, 0, "live pointer moves must not create micro-history entries");
assert.deepEqual(engine.state().drag.delta, { xMm: 20, yMm: 40 });

const movedDocument = engine.state().document;
action = engine.pointerUp();
assert.equal(action.kind, "node-drag-committed");
assert.equal(engine.state().history.undoCount, 1, "the whole drag must be exactly one undo step");
assert.equal(engine.state().history.redoCount, 0);

const connectedS1 = D.segmentById(engine.state().document, "s1");
const connectedS2 = D.segmentById(engine.state().document, "s2");
assert.equal(connectedS1.endNodeId, "n2");
assert.equal(connectedS2.startNodeId, "n2");
assert.deepEqual(D.nodeById(engine.state().document, connectedS1.endNodeId), { id: "n2", xMm: 620, yMm: 40 });
assert.deepEqual(D.nodeById(engine.state().document, connectedS2.startNodeId), { id: "n2", xMm: 620, yMm: 40 });

engine.undo();
assert.deepEqual(D.nodeById(engine.state().document, "n2"), { id: "n2", xMm: 600, yMm: 0 });
assert.equal(engine.state().history.undoCount, 0);
assert.equal(engine.state().history.redoCount, 1);
engine.redo();
assert.deepEqual(D.nodeById(engine.state().document, "n2"), { id: "n2", xMm: 620, yMm: 40 });
assert.equal(engine.state().history.undoCount, 1);
assert.equal(engine.state().history.redoCount, 0);
assert.deepEqual(engine.state().document, movedDocument);

engine.keyDown("a");
engine.pointerDown(G.point(620, 40), { hitToleranceMm: 5 });
for (let index = 0; index < 10; index += 1) engine.pointerMove(G.point(700 + index, 100 + index));
assert.notDeepEqual(D.nodeById(engine.state().document, "n2"), { id: "n2", xMm: 620, yMm: 40 });
action = engine.keyDown("Escape");
assert.equal(action.kind, "node-drag-cancelled");
assert.deepEqual(D.nodeById(engine.state().document, "n2"), { id: "n2", xMm: 620, yMm: 40 });
assert.equal(engine.state().history.undoCount, 1, "cancelled drag must not alter history");

engine.keyDown("v");
engine.pointerDown(G.point(300, 30), { hitToleranceMm: 5 });
assert.equal(engine.state().selection, null, "clicking empty canvas clears selection");

console.log("Door Drawing V4 selection and semantic history tests passed");