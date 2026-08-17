"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const activeFacade = fs.readFileSync(path.join(root, "public/js/door_cutting_order/drawing/special_shape_facade.js"), "utf8");
const v4Bootstrap = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/bootstrap.js"), "utf8");
const app = fs.readFileSync(path.join(root, "public/js/door_drawing_v3/application/vector_editing.js"), "utf8");
const view = fs.readFileSync(path.join(root, "public/js/door_drawing_v3/presentation/vector_editing_view.js"), "utf8");
const css = fs.readFileSync(path.join(root, "public/css/door_drawing_v3_vector_editing.css"), "utf8");

assert.match(activeFacade, /door_drawing_v4\/bootstrap\.js/);
assert.match(v4Bootstrap, /door_drawing_v4\/domain\/geometry\.js/);
assert.match(v4Bootstrap, /door_drawing_v4\/presentation\/editor_controller\.js/);
assert.match(activeFacade, /__doorDrawingV4:\s*true/);
assert.doesNotMatch(activeFacade, /door_drawing_v3\//);
assert.doesNotMatch(v4Bootstrap, /door_drawing_v3\//);
assert.doesNotMatch(activeFacade, /__doorDrawingV3MultiSelect|__doorDrawingV3VectorPathPen/);

assert.ok(app.includes('type: "marquee"'));
assert.ok(app.includes('type: "group-move"'));
assert.ok(app.includes('type: "nodes-move"'));
assert.ok(app.includes('"segment-midpoints"'));
assert.ok(app.includes('const PATH_TOOL = "path"'));
assert.ok(view.includes("data-ddv3-vector-action"));
assert.ok(view.includes("data-ddv3-vector-tool"));
assert.ok(css.includes(".ddv3-vector-actionbar"));
assert.ok(css.includes(".ddv3-vector-marquee"));

console.log("Door Drawing V3 vector editing legacy contracts passed; active facade remains V4");
