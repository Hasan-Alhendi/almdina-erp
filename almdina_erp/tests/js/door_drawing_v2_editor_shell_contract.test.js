"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const shellPath = path.resolve(
    __dirname,
    "../../public/js/door_drawing_v2/presentation/editor_shell_ux.js"
);
const cssPath = path.resolve(
    __dirname,
    "../../public/css/door_drawing_v2_editor.css"
);
const bootstrapPath = path.resolve(
    __dirname,
    "../../public/js/door_drawing_v2/bootstrap.js"
);
const closeUxPath = path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_special_shape_close_ux.js"
);

const shell = fs.readFileSync(shellPath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");
const bootstrap = fs.readFileSync(bootstrapPath, "utf8");
const closeUx = fs.readFileSync(closeUxPath, "utf8");

assert.match(shell, /AlmdinaDoorDrawingV2/);
assert.match(shell, /ViewportModel/);
assert.match(shell, /rowDimensionsMm/);
assert.match(shell, /dco-v2-editor-shell/);
assert.match(shell, /dco-v2-reference-popover/);
assert.match(shell, /Space \+ سحب/);
assert.doesNotMatch(shell, /special_shape_(drawing|geometry)_json\s*=/, "Stage 3 presentation must not write manufacturing/drawing persistence");
assert.doesNotMatch(shell, /frappe\.ui\.form\.on/, "Stage 3 shell must stay scoped to the custom-door editor instead of changing the order form globally");

assert.match(css, /\.dco-special-shape-modal\.dco-v2-modal/);
assert.match(css, /\.dco-v2-editor-shell \.dco-figma-properties/);
assert.match(css, /\.dco-v2-editor-shell \.dco-figma-dock/);
assert.doesNotMatch(css, /^body\s*\{/m, "Editor styling must not leak into the rest of ERPNext");
assert.doesNotMatch(css, /^\.form-layout\s*\{/m, "Editor styling must not alter ordinary Frappe forms");

const scriptOrder = [
    "precision_policy.js",
    "geometry_engine.js",
    "document_model.js",
    "workspace_policy.js",
    "selection_manager.js",
    "transform_manager.js",
    "legacy_adapter.js",
    "legacy_runtime_bridge.js",
    "viewport_model.js",
    "editor_shell_ux.js",
    "selection_overlay_ux.js",
];
let cursor = -1;
scriptOrder.forEach(filename => {
    const index = bootstrap.indexOf(filename);
    assert.ok(index > cursor, `${filename} must load after its Door Drawing V2 dependencies`);
    cursor = index;
});
assert.match(closeUx, /door_drawing_v2\/bootstrap\.js/, "The special-shape entry point should delegate V2 module ordering to one focused bootstrap");
assert.doesNotMatch(closeUx, /geometry_engine\.js/, "The modal-close module must not own V2 dependency ordering");

console.log("Door Drawing V2 editor-shell isolation contract passed");
