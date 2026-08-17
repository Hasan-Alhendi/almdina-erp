"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("domain/dimension.js");
load("application/dimension_commands.js");
load("presentation/editor_view_model.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const D = V4.DocumentModel;
const Dimensions = V4.DimensionCommands;
const VM = V4.EditorViewModel;

let document = D.create({
    widthMm: 1220,
    heightMm: 2440,
    nodes: [
        { id: "n1", xMm: 100, yMm: 200 },
        { id: "n2", xMm: 700, yMm: 200 },
        { id: "n3", xMm: 700, yMm: 1400 },
        { id: "n4", xMm: 100, yMm: 1400 },
    ],
    segments: [
        { id: "s1", startNodeId: "n1", endNodeId: "n2" },
        { id: "s2", startNodeId: "n2", endNodeId: "n3" },
        { id: "s3", startNodeId: "n3", endNodeId: "n4" },
        { id: "s4", startNodeId: "n4", endNodeId: "n1" },
    ],
    paths: [{ id: "p1", startNodeId: "n1", segmentIds: ["s1", "s2", "s3", "s4"], closed: true }],
});

document = Dimensions.ensureSegmentLength(document, "s1", { id: "d1" }).document;

let vm = VM.build(document, { toolState: { activeTool: "select", effectiveTool: "select" }, selection: null });
assert.equal(vm.properties.kind, "document");
assert.equal(vm.properties.widthMm, 1220);
assert.equal(vm.properties.heightMm, 2440);
assert.equal(vm.layers.paths.length, 1);
assert.equal(vm.layers.dimensions.length, 1);
assert.equal(vm.layers.dimensions[0].valueMm, 600);
assert.equal(vm.summary.nodes, 4);

vm = VM.build(document, { toolState: { activeTool: "select" }, selection: { kind: "path", id: "p1" } });
assert.equal(vm.properties.kind, "path");
assert.equal(vm.properties.xMm, 100);
assert.equal(vm.properties.yMm, 200);
assert.equal(vm.properties.widthMm, 600);
assert.equal(vm.properties.heightMm, 1200);
assert.equal(vm.properties.closed, true);
assert.equal(vm.layers.paths[0].selected, true);

vm = VM.build(document, { toolState: { activeTool: "node" }, selection: { kind: "node", id: "n2" } });
assert.equal(vm.properties.kind, "node");
assert.equal(vm.properties.xMm, 700);
assert.equal(vm.properties.yMm, 200);

vm = VM.build(document, { toolState: { activeTool: "dimension" }, selection: { kind: "dimension", id: "d1" } });
assert.equal(vm.properties.kind, "dimension");
assert.equal(vm.properties.valueMm, 600);
assert.equal(vm.layers.dimensions[0].selected, true);

console.log("Door Drawing V4 editor view-model tests passed");
