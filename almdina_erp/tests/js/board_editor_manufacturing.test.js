"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(files) {
    const context = { console, __: (message) => message };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context.AlmdinaBoardEditor;
}

const editor = load([
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
    "public/js/board_editor/drawing_compile.js",
]);

function ring(points) {
    return {
        schema: "almdina.board-editor-drawing",
        version: 1,
        units: "mm",
        coordinate_space: "door_local",
        piece_instance_id: "piece:a",
        blank: { width_mm: 500, length_mm: 300 },
        shapes: [],
        references: [{ id: "ref-1", opacity: 0.2 }],
        paths: [{
            id: "path-1",
            role: "manufacturing_outer",
            closed: true,
            nodes: points.map((point, index) => ({ id: "n" + index, x_mm: point[0], y_mm: point[1] })),
            segments: points.map((point, index) => ({
                id: "s" + index,
                kind: "line",
                from_node: "n" + index,
                to_node: "n" + ((index + 1) % points.length),
            })),
        }],
    };
}

const compiled = editor.DrawingCompile.compile(ring([[0, 0], [500, 0], [500, 300], [0, 300]]), 500, 300);
assert.equal(compiled.status, "ready");
assert.equal(JSON.stringify(compiled.geometry.points), JSON.stringify([[0, 0], [50, 0], [50, 30], [0, 30]]));
assert.equal(JSON.stringify(compiled.geometry).includes("opacity"), false);

const guide = ring([[0, 0], [500, 0], [500, 300], [0, 300]]);
guide.paths[0].role = "construction";
assert.equal(editor.DrawingCompile.compile(guide, 500, 300).status, "absent");

const open = ring([[0, 0], [500, 0], [500, 300], [0, 300]]);
open.paths[0].closed = false;
assert.equal(editor.DrawingCompile.compile(open, 500, 300).code, "path_open");

const hole = ring([[0, 0], [500, 0], [500, 300], [0, 300]]);
hole.paths[0].role = "manufacturing_hole";
assert.equal(editor.DrawingCompile.compile(hole, 500, 300).code, "holes_unsupported");

const drawing = editor.DrawingModel.createSession();
drawing.activate({ pieceInstanceId: "piece:special", widthMm: 500, lengthMm: 300 });
drawing.markReady();
assert.equal(drawing.createShape("rectangle", {
    x_mm: 0, y_mm: 0, width_mm: 500, height_mm: 300, rotation_deg: 0,
}), true);
const shape = drawing.current().document.shapes[0];
assert.equal(drawing.convertShape(shape.id), true);
const created = drawing.current().document.paths[0];
assert.equal(created.role, "construction");
assert.equal(drawing.setPathRole(created.id, "manufacturing_hole"), false);
assert.equal(drawing.current().document.paths[0].role, "construction");
assert.equal(drawing.setPathRole(created.id, "manufacturing_outer"), true);
const before = drawing.current().document.paths[0].nodes.map((node) => [node.x_mm, node.y_mm]);
assert.equal(drawing.translatePath(created.id, 10, -5), true);
const after = drawing.current().document.paths[0].nodes.map((node) => [node.x_mm, node.y_mm]);
assert.equal(after.length, before.length);
after.forEach((point, index) => {
    assert.equal(point[0], before[index][0] + 10);
    assert.equal(point[1], before[index][1] - 5);
});
assert.equal(drawing.current().document.paths[0].segments.every((segment) => segment.kind === "line"), true);

const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
assert.match(page, /drawing_compile\.js\?v=4/);
assert.match(page, /controller\.js\?v=53/);
const renderer = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
assert.match(renderer, /Cut outline/);
assert.match(renderer, /Clear cut outline/);
assert.match(renderer, /Proposed cut/);
assert.match(renderer, /#0b5fff/);
assert.match(renderer, /reservation_mm/);
assert.match(renderer, /stroke-dasharray="4 3"/);

const inset = editor.DrawingCompile.compile(
    ring([[50, 100], [250, 100], [250, 400], [50, 400]]),
    330,
    550
);
assert.equal(inset.status, "ready");
assert.equal(inset.geometry.reservation, "blank");
assert.equal(inset.geometry.points[0][0], 5);
assert.equal(inset.geometry.points[0][1], 10);
assert.equal(inset.geometry.blank_width_cm, 33);
assert.equal(inset.geometry.blank_length_cm, 55);
assert.equal(inset.messageKey, "The cut outline is valid for manufacturing.");

console.log("manufacturing geometry UI contract passed");
