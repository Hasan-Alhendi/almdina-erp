"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const loader = fs.readFileSync(path.join(root, "public/js/door_cutting_order/drawing/special_shape_facade.js"), "utf8");
const app = fs.readFileSync(path.join(root, "public/js/door_drawing_v3/application/vector_editing.js"), "utf8");
const view = fs.readFileSync(path.join(root, "public/js/door_drawing_v3/presentation/vector_editing_view.js"), "utf8");
const css = fs.readFileSync(path.join(root, "public/css/door_drawing_v3_vector_editing.css"), "utf8");

const domainIndex = loader.indexOf("domain/vector_selection.js");
const viewIndex = loader.indexOf("presentation/vector_editing_view.js");
const smartPenIndex = loader.indexOf("application/smart_pen.js");
const appIndex = loader.indexOf("application/vector_editing.js");
assert.ok(domainIndex > -1, "Vector selection domain must be bootstrapped");
assert.ok(viewIndex > domainIndex, "Vector view must load after its domain");
assert.ok(appIndex > smartPenIndex, "Vector interactions must wrap the final Smart Pen editor, not an earlier editor instance");
assert.ok(loader.includes("door_drawing_v3_vector_editing.css"));
assert.ok(loader.includes("__doorDrawingV3MultiSelect: true"));
assert.ok(loader.includes("__doorDrawingV3VectorPathPen: true"));
assert.ok(app.includes('type: "marquee"'));
assert.ok(app.includes('type: "group-move"'));
assert.ok(app.includes('type: "nodes-move"'));
assert.ok(app.includes('"segment-midpoints"'));
assert.ok(app.includes('const PATH_TOOL = "path"'));
assert.ok(view.includes("data-ddv3-vector-action"));
assert.ok(view.includes("data-ddv3-vector-tool"));
assert.ok(css.includes(".ddv3-vector-actionbar"));
assert.ok(css.includes(".ddv3-vector-marquee"));

console.log("Door Drawing V3 vector editing contract tests passed");