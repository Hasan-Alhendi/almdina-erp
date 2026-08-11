"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicRoot = path.resolve(__dirname, "../../public");
const read = relative => fs.readFileSync(path.join(publicRoot, relative), "utf8");

const bootstrap = read("js/door_drawing_v2/bootstrap.js");
const closeUx = read("js/door_cutting_order_special_shape_close_ux.js");
const workspace = read("js/door_drawing_v2/interaction/workspace_policy.js");
const selection = read("js/door_drawing_v2/application/selection_manager.js");
const transforms = read("js/door_drawing_v2/application/transform_manager.js");
const bridge = read("js/door_drawing_v2/infrastructure/legacy_runtime_bridge.js");
const overlay = read("js/door_drawing_v2/presentation/selection_overlay_ux.js");
const shell = read("js/door_drawing_v2/presentation/editor_shell_ux.js");
const selectionCss = read("css/door_drawing_v2_selection.css");

const order = [
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
order.forEach(filename => {
    const index = bootstrap.indexOf(filename);
    assert.ok(index > cursor, `${filename} must load after its dependencies`);
    cursor = index;
});

assert.match(closeUx, /door_drawing_v2\/bootstrap\.js/);
assert.doesNotMatch(closeUx, /precision_policy\.js/, "Modal close UX must no longer own V2 module ordering");
assert.match(workspace, /MODE = "free"/);
assert.match(shell, /createFree/);
assert.match(shell, /ارسم في أي مكان/);
assert.match(overlay, /setLineEndpoint/);
assert.match(overlay, /translateSelection/);
assert.match(overlay, /EXACT · mm/);
assert.match(bridge, /applyLineObjectToLegacy/);

[workspace, selection, transforms, bridge, overlay, shell].forEach(source => {
    assert.doesNotMatch(source, /frappe\.ui\.form\.on/, "Stage 4 modules must stay isolated to the custom-door editor");
});
assert.doesNotMatch(overlay, /special_shape_(drawing|geometry)_json\s*=/, "Selection presentation must not write persistence fields directly");
assert.doesNotMatch(selectionCss, /^body\s*\{/m);
assert.doesNotMatch(selectionCss, /^\.form-layout\s*\{/m);
assert.match(selectionCss, /\.dco-v2-editor-shell \.dco-exact-frame/);
assert.match(selectionCss, /\.dco-v2-selection-overlay/);

console.log("Door Drawing V2 Stage 4 isolation contract passed");
