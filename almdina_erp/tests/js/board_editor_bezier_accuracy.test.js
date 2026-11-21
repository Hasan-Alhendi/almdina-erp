"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const context = { console, __: (message) => message };
context.window = context;
vm.createContext(context);
vm.runInContext(
    fs.readFileSync(path.join(root, "public/js/board_editor/drawing_compile.js"), "utf8"),
    context,
    { filename: "drawing_compile.js" }
);
const compile = context.AlmdinaBoardEditor.DrawingCompile.compile;

function bezier(p0, c1, c2, p3, t) {
    const u = 1 - t;
    return [
        u ** 3 * p0[0] + 3 * u ** 2 * t * c1[0] + 3 * u * t ** 2 * c2[0] + t ** 3 * p3[0],
        u ** 3 * p0[1] + 3 * u ** 2 * t * c1[1] + 3 * u * t ** 2 * c2[1] + t ** 3 * p3[1],
    ];
}

function distanceToSegment(point, start, end) {
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];
    const length2 = dx * dx + dy * dy;
    if (length2 <= 1e-18) return Math.hypot(point[0] - start[0], point[1] - start[1]);
    const ratio = Math.min(1, Math.max(0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2));
    return Math.hypot(point[0] - (start[0] + ratio * dx), point[1] - (start[1] + ratio * dy));
}

function deviation(curve, polygonCm) {
    const polygon = polygonCm.map((point) => [point[0] * 10, point[1] * 10]);
    let worst = 0;
    for (let index = 0; index <= 4000; index += 1) {
        const point = bezier(curve[0], curve[1], curve[2], curve[3], index / 4000);
        let nearest = Infinity;
        for (let edge = 0; edge < polygon.length - 1; edge += 1) {
            nearest = Math.min(nearest, distanceToSegment(point, polygon[edge], polygon[edge + 1]));
        }
        worst = Math.max(worst, nearest);
    }
    return worst;
}

function document(nodes, segments, width, length) {
    return {
        schema: "almdina.board-editor-drawing",
        version: 1,
        units: "mm",
        coordinate_space: "door_local",
        piece_instance_id: "piece:a",
        blank: { width_mm: width, length_mm: length },
        shapes: [],
        references: [],
        paths: [{
            id: "path-1",
            role: "manufacturing_outer",
            closed: true,
            nodes: nodes.map((node) => ({ id: node[0], x_mm: node[1], y_mm: node[2] })),
            segments,
        }],
    };
}

function line(id, from, to) {
    return { id, kind: "line", from_node: from, to_node: to };
}

function cubic(id, from, to, c1, c2) {
    return {
        id,
        kind: "bezier",
        from_node: from,
        to_node: to,
        controls: [{ x_mm: c1[0], y_mm: c1[1] }, { x_mm: c2[0], y_mm: c2[1] }],
    };
}

function ready(nodes, segments, curve, width, length) {
    const source = document(nodes, segments, width, length);
    const before = JSON.stringify(source.paths[0].segments[0]);
    const result = compile(source, width, length);
    assert.equal(result.status, "ready", result.code);
    assert.equal(JSON.stringify(source.paths[0].segments[0]), before);
    assert.equal(source.paths[0].segments[0].kind, "bezier");
    assert.ok(result.geometry.points.length > 2);
    assert.ok(result.geometry.points.length <= 64);
    assert.ok(deviation(curve, result.geometry.points) < 0.05);
    return result;
}

const sCurve = [[0, 0], [30, 0], [70, 100], [100, 100]];
const midpoint = bezier(sCurve[0], sCurve[1], sCurve[2], sCurve[3], 0.5);
assert.ok(distanceToSegment(midpoint, sCurve[0], sCurve[3]) < 1e-9);
assert.ok(distanceToSegment(bezier(sCurve[0], sCurve[1], sCurve[2], sCurve[3], 0.25), sCurve[0], sCurve[3]) > 5.9);

const s = ready(
    [["n1", 20, 20], ["n2", 120, 120], ["n3", 180, 20]],
    [cubic("s1", "n1", "n2", [50, 20], [90, 120]), line("s2", "n2", "n3"), line("s3", "n3", "n1")],
    [[20, 20], [50, 20], [90, 120], [120, 120]],
    220,
    180
);
assert.equal(JSON.stringify(s.geometry.points[0]), JSON.stringify([2, 2]));
assert.ok(s.geometry.points.some((point) => point[0] === 12 && point[1] === 12));

ready(
    [["n1", 120, 120], ["n2", 20, 20], ["n3", 180, 20]],
    [cubic("s1", "n1", "n2", [90, 120], [50, 20]), line("s2", "n2", "n3"), line("s3", "n3", "n1")],
    [[120, 120], [90, 120], [50, 20], [20, 20]],
    220,
    180
);

ready(
    [["n1", 10, 20], ["n2", 110, 20], ["n3", 110, 140], ["n4", 10, 140]],
    [cubic("s1", "n1", "n2", [40, 100], [80, 100]), line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n1")],
    [[10, 20], [40, 100], [80, 100], [110, 20]],
    160,
    160
);

ready(
    [["n1", 10, 20], ["n2", 110, 20], ["n3", 110, 80], ["n4", 10, 80]],
    [cubic("s1", "n1", "n2", [10, 60], [30, 60]), line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n1")],
    [[10, 20], [10, 60], [30, 60], [110, 20]],
    160,
    120
);

const shallow = ready(
    [["n1", 0, 0], ["n2", 100, 0], ["n3", 100, 40], ["n4", 0, 40]],
    [cubic("s1", "n1", "n2", [40, 0.01], [60, 0.01]), line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n1")],
    [[0, 0], [40, 0.01], [60, 0.01], [100, 0]],
    120,
    60
);
assert.equal(shallow.geometry.points.length, 4);

const straight = ready(
    [["n1", 0, 0], ["n2", 100, 0], ["n3", 100, 40], ["n4", 0, 40]],
    [cubic("s1", "n1", "n2", [30, 0], [70, 0]), line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n1")],
    [[0, 0], [30, 0], [70, 0], [100, 0]],
    120,
    60
);
assert.equal(straight.geometry.points.length, 4);
assert.ok(deviation([[0, 0], [30, 0], [70, 0], [100, 0]], straight.geometry.points) < 1e-9);

ready(
    [["n1", 60, 50], ["n2", 100, 50], ["n3", 150, 80], ["n4", 150, 120], ["n5", 10, 120], ["n6", 10, 80]],
    [
        cubic("s1", "n1", "n2", [30, 48], [130, 48]),
        line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n5"), line("s5", "n5", "n6"), line("s6", "n6", "n1"),
    ],
    [[60, 50], [30, 48], [130, 48], [100, 50]],
    180,
    140
);

const two = document(
    [["n1", 20, 40], ["n2", 140, 40], ["n3", 140, 100], ["n4", 20, 100]],
    [
        cubic("s1", "n1", "n2", [50, 48], [110, 48]),
        line("s2", "n2", "n3"),
        cubic("s3", "n3", "n4", [110, 92], [50, 92]),
        line("s4", "n4", "n1"),
    ],
    180,
    140
);
const twoResult = compile(two, 180, 140);
assert.equal(twoResult.status, "ready", twoResult.code);
assert.ok(twoResult.geometry.points.length <= 64);
assert.ok(deviation([[20, 40], [50, 48], [110, 48], [140, 40]], twoResult.geometry.points) < 0.05);
assert.ok(deviation([[140, 100], [110, 92], [50, 92], [20, 100]], twoResult.geometry.points) < 0.05);

const outside = compile(document(
    [["n1", 10, 30], ["n2", 90, 30], ["n3", 90, 10], ["n4", 10, 10]],
    [cubic("s1", "n1", "n2", [30, 180], [70, 180]), line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n1")],
    100,
    80
), 100, 80);
assert.equal(outside.code, "outside_blank");

const crossing = compile(document(
    [["n1", 20, 20], ["n2", 80, 20], ["n3", 80, 60], ["n4", 20, 60]],
    [cubic("s1", "n1", "n2", [90, 90], [10, 90]), line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n1")],
    200,
    200
), 200, 200);
assert.equal(crossing.code, "self_intersection");

const huge = compile(document(
    [["n1", 0, 0], ["n2", 8000, 0], ["n3", 8000, 8000], ["n4", 0, 8000]],
    [cubic("s1", "n1", "n2", [0, 8000], [8000, 8000]), line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n1")],
    9000,
    9000
), 9000, 9000);
assert.equal(huge.code, "curve_unrepresentable");

const tiny = ready(
    [["n1", 10, 10], ["n2", 80, 10], ["n3", 80, 40], ["n4", 10, 40]],
    [cubic("s1", "n1", "n2", [30, 10.004], [50, 10.003]), line("s2", "n2", "n3"), line("s3", "n3", "n4"), line("s4", "n4", "n1")],
    [[10, 10], [30, 10.004], [50, 10.003], [80, 10]],
    100,
    60
);
assert.ok(tiny.geometry.points.length < 8);
