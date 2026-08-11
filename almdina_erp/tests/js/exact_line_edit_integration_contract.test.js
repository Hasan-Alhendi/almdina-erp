"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const hooks = fs.readFileSync(path.resolve(__dirname, "../../hooks.py"), "utf8");
const baseModel = hooks.indexOf("door_cutting_order_exact_line_model.js");
const editModel = hooks.indexOf("door_cutting_order_exact_line_edit_model.js");
const baseUx = hooks.indexOf("door_cutting_order_exact_line_ux.js");
const inspectorUx = hooks.indexOf("door_cutting_order_exact_line_inspector_ux.js");
const closeGuard = hooks.indexOf("door_cutting_order_special_shape_close_ux.js");

assert.ok(baseModel >= 0 && editModel > baseModel);
assert.ok(baseUx >= 0 && inspectorUx > baseUx);
assert.ok(closeGuard > inspectorUx);

console.log("Exact line edit module integration passed");