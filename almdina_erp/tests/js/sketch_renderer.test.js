"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_engine.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_renderer.js"
));

const renderer = global.window.AlmdinaSketchRenderer;

assert.equal(Object.isFrozen(renderer), true, "The renderer API should be immutable");

const note = {
    id: 'note-"unsafe"',
    type: "note",
    x: 320,
    y: 180,
    text: "<b>ملاحظة آمنة</b>",
    font_size: 24,
    text_anchor: "end",
    color: "#172033",
};
const noteMarkup = renderer.elementMarkup(note, { selected: true });
assert.ok(noteMarkup.includes("is-selected"), "Selected elements should retain their visual state");
assert.ok(noteMarkup.includes('font-size="24"'), "Notes should retain their chosen font size");
assert.ok(noteMarkup.includes('text-anchor="end"'), "Notes should retain their text anchor");
assert.ok(noteMarkup.includes("&lt;b&gt;"), "User note text must be HTML escaped");
assert.ok(!noteMarkup.includes("<b>ملاحظة"), "User note text must never become SVG markup");
assert.ok(!noteMarkup.includes("dco-sketch-note-bg"), "Canvas notes should remain text-only");

const dimension = {
    id: "dimension-1",
    type: "dimension",
    x1: 120,
    y1: 200,
    x2: 420,
    y2: 200,
    text: "85 < 90 سم",
    color: "#1769aa",
};
const dimensionMarkup = renderer.elementMarkup(dimension);
assert.ok(dimensionMarkup.includes("marker-start"), "Dimensions should retain both arrow markers");
assert.ok(dimensionMarkup.includes("85 &lt; 90"), "Dimension labels must be escaped");

const state = {
    elements: [
        { id: "line-1", type: "line", x1: 50, y1: 60, x2: 400, y2: 60 },
        dimension,
        note,
    ],
    selectedId: "line-1",
    tool: "select",
    gridVisible: true,
    snapPoint: { x: 400, y: 60 },
    viewBox: { x: 100, y: 50, width: 500, height: 325 },
};
const canvas = renderer.canvasView(state);
assert.equal(canvas.viewBox, "100 50 500 325");
assert.ok(canvas.markup.includes('fill="url(#dco-grid)"'), "The drawing grid should remain visible");
assert.ok(canvas.markup.includes("dco-sketch-selection-overlay"), "Selection handles should render");
assert.ok(canvas.markup.includes("dco-sketch-snap-indicator"), "Endpoint snapping should render");
assert.ok(canvas.markup.includes("dco-sketch-cursor-preview"), "The interactive cursor layer should remain");

const withoutGrid = renderer.canvasView({ elements: [], gridVisible: false });
assert.ok(
    !withoutGrid.markup.includes('fill="url(#dco-grid)"'),
    "Read-only or configured views should be able to hide the grid"
);

const sidebar = renderer.sidebarView(state.elements);
assert.ok(sidebar.dimensions.includes("85 &lt; 90"), "Sidebar dimensions must be escaped");
assert.ok(sidebar.notes.includes("&lt;b&gt;"), "Sidebar notes must be escaped");
assert.ok(sidebar.progress.includes("إضافة القياسات (1)"));
assert.ok(sidebar.progress.includes("ملاحظات المصمم (1)"));

console.log("Pure special-shape SVG and sidebar renderer checks passed");
