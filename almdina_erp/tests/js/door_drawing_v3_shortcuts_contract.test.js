"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "../../..");
const read = relative => fs.readFileSync(path.join(repoRoot, relative), "utf8");

const bootstrap = read("almdina_erp/public/js/door_cutting_order_special_shape_ux.js");
const shortcuts = read("almdina_erp/public/js/door_drawing_v3/application/editor_shortcuts.js");
const nodePolicy = read("almdina_erp/public/js/door_drawing_v3/application/node_selection_policy.js");

const vectorIndex = bootstrap.indexOf("application/vector_editing.js");
const nodePolicyIndex = bootstrap.indexOf("application/node_selection_policy.js");
const shortcutsIndex = bootstrap.indexOf("application/editor_shortcuts.js");
assert.ok(vectorIndex >= 0, "Vector editing must be bootstrapped");
assert.ok(nodePolicyIndex > vectorIndex, "Node selection policy must load after vector editing");
assert.ok(shortcutsIndex > nodePolicyIndex, "Shortcut manager must load after selection policies");

assert.match(bootstrap, /__doorDrawingV3SelectionNodeDrag:\s*true/);
assert.match(bootstrap, /__doorDrawingV3ProfessionalShortcuts:\s*true/);
assert.match(bootstrap, /__doorDrawingV3MultiClipboard:\s*true/);

assert.match(shortcuts, /key === "c"/);
assert.match(shortcuts, /key === "v"/);
assert.match(shortcuts, /key === "z"/);
assert.match(shortcuts, /key === "y"/);
assert.match(shortcuts, /event\.shiftKey \? redo\(c\) : undo\(c\)/, "Ctrl/Cmd+Shift+Z must redo");
assert.match(shortcuts, /Array\.isArray\(c\.selectedIds\)/, "Clipboard must understand multi-selection");
assert.match(shortcuts, /Paste \$\{ids\.length\} objects/, "Multi-object paste must be one history command");
assert.match(shortcuts, /G\.cloneObject\(source, nextId\(source\.type\)\)/, "Paste must clone geometry rather than share object identity");

assert.match(nodePolicy, /data-ddv3-tool=\\?"select\\?"/, "Selection tool intent must be recognized");
assert.match(nodePolicy, /__selectionToolNodeEditSnapshot/, "Node edit state must be preserved while choosing V/select");
assert.match(nodePolicy, /event\.key !== "Enter"/, "Enter must be a supported vector-edit entry gesture");
assert.match(nodePolicy, /c\.nodeEditId = String\(object\.id\)/, "Selected path must enter node edit mode");

console.log("Door Drawing V3 shortcut and node-selection contract tests passed");
