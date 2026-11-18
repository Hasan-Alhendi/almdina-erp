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
    return context;
}

const editor = load([
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
    "public/js/board_editor/editor_mode.js",
]).AlmdinaBoardEditor;

const drawing = editor.DrawingModel.createSession();
drawing.activate({ pieceInstanceId: "piece:door-1", widthMm: 600, lengthMm: 2100 });
drawing.markReady();
assert.equal(Object.prototype.hasOwnProperty.call(drawing.current().document, "texts"), false);

const outlines = [[
    { x_mm: 40, y_mm: 40 },
    { x_mm: 80, y_mm: 40 },
    { x_mm: 80, y_mm: 70 },
    { x_mm: 40, y_mm: 70 },
]];
const id = drawing.applyText({
    text: "باب",
    font_size_mm: 20,
    font_weight: "regular",
    direction: "auto",
    align: "right",
    outlines,
});
assert.equal(typeof id, "string");
const text = drawing.current().document.texts[0];
assert.equal(text.text, "باب");
assert.equal(text.role, "manufacturing_text");
assert.equal(text.state, "editable");
assert.equal(text.export_approved, false);
assert.equal(text.outlines.length, 1);
assert.equal(text.outlines[0].points.length, 4);

assert.equal(drawing.selectHit({ x: 50, y: 50 }, 2), true);
const placed = JSON.parse(JSON.stringify(drawing.current().document.texts[0]));
const placedX = placed.outlines[0].points[0].x_mm;
drawing.moveText(id, 30, 0, { base: placed, history: false });
drawing.moveText(id, 30, 0, { base: placed, history: false });
assert.equal(drawing.current().document.texts[0].outlines[0].points[0].x_mm, placedX + 30);
assert.equal(drawing.current().document.texts[0].x_mm, placed.x_mm + 30);
drawing.moveText(id, 0, 0, { base: placed, history: false });
assert.equal(drawing.moveText(id, 15, 5), true);
assert.equal(drawing.current().document.texts[0].x_mm, 55);
assert.equal(drawing.undo(), true);
assert.equal(drawing.current().document.texts[0].x_mm, 40);
assert.equal(drawing.redo(), true);
assert.equal(drawing.current().document.texts[0].x_mm, 55);

drawing.current().selection = { textId: id };
assert.equal(drawing.convertText(id), true);
assert.equal(drawing.setTextExport(id, true), true);
drawing.applyText({
    id,
    text: "مدينة",
    font_size_mm: 20,
    font_weight: "regular",
    direction: "rtl",
    align: "right",
    outlines,
    state: "vector",
});
const edited = drawing.current().document.texts[0];
assert.equal(edited.state, "editable");
assert.equal(edited.export_approved, false);
assert.equal(edited.text, "مدينة");

drawing.convertText(edited.id);
drawing.setTextExport(edited.id, true);
assert.equal(drawing.duplicateSelection(), true);
const copy = drawing.current().document.texts[1];
assert.equal(copy.export_approved, false);
assert.equal(copy.text, "مدينة");
assert.notEqual(copy.id, edited.id);
assert.equal(drawing.deleteSelection(), true);
assert.equal(drawing.current().document.texts.length, 1);

assert.equal(drawing.rotateText(edited.id, 90), true);
assert.equal(drawing.scaleText(edited.id, 2), true);
const scaled = drawing.textBounds(edited.id);
assert.ok(scaled.width > 50);
drawing.scaleText(edited.id, 2, { anchor: { x: scaled.minX, y: scaled.minY }, history: false });
const grown = drawing.textBounds(edited.id);
assert.equal(grown.minX, scaled.minX);
assert.equal(grown.minY, scaled.minY);
assert.ok(grown.width > scaled.width);

const tools = editor.EditorMode.futureTools.map((tool) => tool.id);
assert.equal(tools.includes("text"), true);
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const renderer = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
assert.match(renderer, /text:\s*"type"/);
assert.match(page, /editor_mode\.js\?v=2/);
assert.match(page, /drawing_model\.js\?v=10/);
