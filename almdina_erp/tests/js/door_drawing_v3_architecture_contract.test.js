"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const entry = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_cutting_order_special_shape_ux.js"), "utf8");
const editor = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/presentation/editor.js"), "utf8");
const css = fs.readFileSync(path.resolve(__dirname, "../../public/css/door_drawing_v3.css"), "utf8");

assert.match(entry, /door_drawing_v3\/domain\/geometry\.js/);
assert.match(entry, /door_drawing_v3\/presentation\/editor\.js/);
assert.match(entry, /__doorDrawingV3:\s*true/);
assert.doesNotMatch(entry, /AlmdinaSketchEngine|AlmdinaExactLineModel|AlmdinaSketchHistory/, "V3 entry point must not depend on the retired sketch engine");

assert.match(editor, /data-ddv3-tool="line"/);
assert.match(editor, /data-ddv3-prop="length"/);
assert.match(editor, /data-ddv3-prop="angle"/);
assert.match(editor, /measurementMarkup/);
assert.match(editor, /worldToScreen/);
assert.match(editor, /screenToWorld/);
assert.match(editor, /Ctrl\+Shift\+Z/);
assert.doesNotMatch(editor, /canvas:\s*\{\s*width:\s*1000/, "The editor must not use legacy canvas coordinates as its geometry model");
assert.doesNotMatch(editor, /special_shape_geometry_json\s*=/, "Stage 1 must not fabricate manufacturing geometry from screen output");

assert.match(css, /\.ddv3-app/);
assert.match(css, /\.ddv3-inspector/);
assert.match(css, /\.ddv3-toolbar/);
assert.match(css, /\.ddv3-measure/);
assert.doesNotMatch(css, /^body\s*\{/m, "Drawing V3 styles must stay scoped to the custom-door editor");
assert.doesNotMatch(css, /^\.form-layout\s*\{/m, "Drawing V3 styles must not leak into ERPNext forms");

console.log("Door Drawing V3 clean architecture contract passed");
