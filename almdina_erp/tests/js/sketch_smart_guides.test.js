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
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_smart_guides.js"
));

const renderer = window.AlmdinaSketchRenderer;

assert.equal(renderer.inferredAxis({
    draft: { type: "line", x1: 100, y1: 120, x2: 300, y2: 120 },
}), "horizontal");
assert.equal(renderer.inferredAxis({
    draft: { type: "line", x1: 100, y1: 120, x2: 100, y2: 350 },
}), "vertical");
assert.equal(renderer.inferredAxis({
    draft: { type: "line", x1: 100, y1: 120, x2: 220, y2: 260 },
}), "");

let markup = renderer.smartGuideMarkup({
    draft: { type: "line", x1: 100, y1: 120, x2: 300, y2: 120 },
}, { width: 1000, height: 650 });
assert.match(markup, /dco-smart-axis-guide/);
assert.match(markup, />أفقي</);

markup = renderer.smartGuideMarkup({
    draft: { type: "dimension", x1: 100, y1: 120, x2: 100, y2: 350 },
}, { width: 1000, height: 650 });
assert.match(markup, />عمودي</);

const view = renderer.canvasView({
    elements: [],
    tool: "line",
    draft: { id: "line-1", type: "line", x1: 100, y1: 120, x2: 300, y2: 120, color: "#172033" },
    viewBox: { x: 0, y: 0, width: 1000, height: 650 },
}, { width: 1000, height: 650 });
assert.match(view.markup, /dco-smart-axis-guide/);
assert.ok(
    view.markup.indexOf("dco-smart-axis-guide") < view.markup.indexOf("dco-sketch-cursor-preview"),
    "Smart guides should render behind the cursor overlay"
);

console.log("Smart axis guide inference and rendering passed");