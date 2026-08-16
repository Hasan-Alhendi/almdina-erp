"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("domain/constraint.js");
load("application/geometry_commands.js");
load("application/constraint_commands.js");
load("application/constraint_solver.js");
load("application/manufacturing_projection.js");
load("infrastructure/persistence_adapter.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const D = V4.DocumentModel;
const C = V4.ConstraintCommands;
const Constraints = V4.ConstraintDomain;
const Solver = V4.ConstraintSolver;
const Manufacturing = V4.ManufacturingProjection;
const Persistence = V4.PersistenceAdapter;

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
        paths: [{ id: "p1", startNodeId: "n1", segmentIds: ["s1", "s2", "s3", "s4"], closed: true }],
    });
}

let document = rectangle();
assert.deepEqual(document.constraints, [], "V4 drawings without constraints remain valid");

document = C.ensureHorizontal(document, "s1", { id: "c-h-top" }).document;
document = C.ensureVertical(document, "s2", { id: "c-v-right" }).document;
document = C.ensureHorizontal(document, "s3", { id: "c-h-bottom" }).document;
document = C.ensureVertical(document, "s4", { id: "c-v-left" }).document;
assert.equal(document.constraints.length, 4);
assert.equal(Constraints.isSatisfied(document), true, "the original rectangle must satisfy its orthogonal constraints");

const driven = Solver.driveSegmentLength(document, "s1", 750, {
    id: "c-width",
    anchorNodeId: "n1",
});
assert.equal(driven.ok, true, "a constrained rectangle width must be solvable");
assert.equal(driven.constraintCreated, true);
assert.equal(driven.document.constraints.length, 5);
assert.deepEqual(driven.document.nodes.map(node => [node.id, node.xMm, node.yMm]), [
    ["n1", 0, 0],
    ["n2", 750, 0],
    ["n3", 750, 1200],
    ["n4", 0, 1200],
]);
assert.equal(Constraints.isSatisfied(driven.document), true, "all geometric constraints must remain satisfied after driving width");
const widthConstraint = D.constraintById(driven.document, driven.constraintId);
assert.deepEqual(widthConstraint, {
    id: "c-width",
    type: D.CONSTRAINT_TYPES.FIXED_LENGTH,
    segmentId: "s1",
    valueMm: 750,
    anchorNodeId: "n1",
});

const projected = Manufacturing.project(driven.document);
assert.equal(projected.ok, true);
assert.deepEqual(projected.geometry.points, [
    [0, 0],
    [75, 0],
    [75, 120],
    [0, 120],
], "manufacturing projection must use the solved geometry and ignore constraint metadata");

const stored = Persistence.toStored(driven.document);
const restored = Persistence.fromStored(stored, { width_cm: 60, length_cm: 120 });
assert.deepEqual(restored.constraints, driven.document.constraints, "constraints must survive persistence round-trip");
assert.deepEqual(restored.nodes, driven.document.nodes);

// A failed solve is transactional: neither the new requested value nor partial geometry is committed.
const beforeConflict = driven.document;
const conflict = Solver.driveSegmentLength(beforeConflict, "s1", 900, {
    pinnedNodeIds: ["n2"],
});
assert.equal(conflict.ok, false);
assert.equal(conflict.code, "constraint-conflict");
assert.equal(conflict.document, beforeConflict, "failed constraint solves must return the exact original document");
assert.equal(D.constraintById(conflict.document, "c-width").valueMm, 750);
assert.deepEqual(conflict.document.nodes, beforeConflict.nodes);

// Editing only the value preserves the explicitly chosen anchor.
let isolated = D.create({
    widthMm: 1000,
    heightMm: 1000,
    nodes: [
        { id: "a", xMm: 0, yMm: 0 },
        { id: "b", xMm: 300, yMm: 400 },
    ],
    segments: [{ id: "ab", startNodeId: "a", endNodeId: "b" }],
    paths: [{ id: "path-ab", startNodeId: "a", segmentIds: ["ab"], closed: false }],
});
isolated = C.ensureFixedLength(isolated, "ab", 500, { id: "c-ab", anchorNodeId: "b" }).document;
const edited = C.ensureFixedLength(isolated, "ab", 600);
assert.equal(D.constraintById(edited.document, "c-ab").anchorNodeId, "b");
assert.equal(D.constraintById(edited.document, "c-ab").valueMm, 600);

console.log("Door Drawing V4 constraint foundation tests passed");
