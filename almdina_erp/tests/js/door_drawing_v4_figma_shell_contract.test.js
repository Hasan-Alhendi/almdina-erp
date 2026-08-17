"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../../");
const shell = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/presentation/editor_shell.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/presentation/editor_controller.js"), "utf8");
const bootstrap = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/bootstrap.js"), "utf8");
const css = fs.readFileSync(path.join(root, "public/css/door_drawing_v4.css"), "utf8");

assert.match(shell, /ald-v4-layers-panel/, "Figma shell must expose a physical left Layers panel");
assert.match(shell, /ald-v4-properties-panel/, "Figma shell must expose a physical right Properties panel");
assert.match(shell, /ald-v4-canvas-region/, "Canvas must remain the independent center region");
assert.match(shell, /ald-v4-toolbar/, "Editor must keep a compact floating toolbar");
assert.match(shell, /renderViewModel/, "Shell must render a view model rather than inspect geometry itself");
assert.match(shell, /data-position-properties/);
assert.match(shell, /data-size-properties/);
assert.doesNotMatch(shell, /frappe\./, "Presentation shell must not depend on Frappe APIs");

assert.match(controller, /root\.EditorViewModel/, "Controller must derive panels from the canonical editor state");
assert.match(controller, /shell\.renderViewModel\(viewModel\.build\(state\.document, state\)\)/);
assert.doesNotMatch(controller, /querySelector\([^\n]*special_shape/, "Controller must not infer domain state from legacy DOM fields");

assert.match(bootstrap, /presentation\/editor_view_model\.js/);
assert.ok(
    bootstrap.indexOf("presentation/editor_view_model.js") < bootstrap.indexOf("presentation/editor_shell.js"),
    "View model must load before the Figma shell"
);

assert.match(css, /grid-template-areas:\s*"layers canvas properties"/);
assert.match(css, /\.ald-v4-toolbar[\s\S]*bottom:\s*18px/);
assert.match(css, /\.ald-v4-layers-panel\s*\{\s*grid-area:\s*layers/);
assert.match(css, /\.ald-v4-properties-panel\s*\{\s*grid-area:\s*properties/);

console.log("Door Drawing V4 Figma-like shell contract passed");
