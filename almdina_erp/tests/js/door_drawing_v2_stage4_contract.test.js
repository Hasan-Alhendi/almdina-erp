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
const lineLabel = read("js/door_drawing_v2/presentation/line_label_geometry.js");
const lineUx = read("js/door_drawing_v2/presentation/line_tool_ux.js");
const selectionCss = read("css/door_drawing_v2_selection.css");
const lineCss = read("css/door_drawing_v2_line.css");

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
    "line_label_geometry.js",
    "editor_shell_ux.js",
    "selection_overlay_ux.js",
    "line_tool_ux.js",
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

assert.match(lineUx, /data-v2-draft-length/);
assert.match(lineUx, /data-v2-draft-angle/);
assert.match(lineUx, /gesture\.moved \|\| gesture\.hadPreviewBeforeDown/);
assert.match(lineUx, /suppressLegacySuccessAlert/);
assert.match(lineUx, /data-v2-apply/);
assert.match(lineCss, /\.dco-v2-editor-shell \.dco-exact-line-hud/);
assert.match(lineCss, /\.dco-v2-editor-shell\.is-v2-line-drawing \.dco-exact-shape-card/);
assert.match(lineCss, /\.dco-v2-line-draft-measurement/);
assert.match(lineCss, /\.dco-v2-inspector-apply/);

[workspace, selection, transforms, bridge, overlay, shell, lineLabel, lineUx].forEach(source => {
    assert.doesNotMatch(source, /frappe\.ui\.form\.on/, "Stage 4 modules must stay isolated to the custom-door editor");
});
assert.doesNotMatch(overlay, /special_shape_(drawing|geometry)_json\s*=/, "Selection presentation must not write persistence fields directly");
assert.doesNotMatch(lineUx, /special_shape_(drawing|geometry)_json\s*=/, "Line presentation must not write persistence fields directly");
assert.doesNotMatch(selectionCss, /^body\s*\{/m);
assert.doesNotMatch(selectionCss, /^\.form-layout\s*\{/m);
assert.doesNotMatch(lineCss, /^body\s*\{/m);
assert.doesNotMatch(lineCss, /^\.form-layout\s*\{/m);
assert.match(selectionCss, /\.dco-v2-editor-shell \.dco-exact-frame/);
assert.match(selectionCss, /\.dco-v2-selection-overlay/);

// The measurement badge follows Figma's spatial rule: it stays below a
// horizontal line regardless of draw direction, and moves to screen-right
// for vertical lines. The displayed text remains upright.
global.window = {};
require(path.join(publicRoot, "js/door_drawing_v2/presentation/line_label_geometry.js"));
const labelGeometry = global.window.AlmdinaDoorDrawingV2.LineLabelGeometry;
const leftToRight = labelGeometry.placement([10, 20], [110, 20]);
const rightToLeft = labelGeometry.placement([110, 20], [10, 20]);
const vertical = labelGeometry.placement([40, 10], [40, 110]);
const reversedVertical = labelGeometry.placement([40, 110], [40, 10]);
const diagonal = labelGeometry.placement([0, 0], [-100, -100]);
assert.ok(leftToRight.y > 20, "horizontal measurement must sit below the segment");
assert.ok(rightToLeft.y > 20, "reversed horizontal measurement must still sit below the segment");
assert.ok(vertical.x > 40, "vertical measurement must sit on screen-right");
assert.ok(reversedVertical.x > 40, "reversed vertical measurement must stay on screen-right");
assert.ok(diagonal.angleDeg >= -90 && diagonal.angleDeg <= 90, "measurement text must remain upright");

console.log("Door Drawing V2 Stage 4 isolation and Figma-like line UX contract passed");
