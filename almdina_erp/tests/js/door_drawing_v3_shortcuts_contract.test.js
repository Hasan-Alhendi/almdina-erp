"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "../../..");
const read = relative => fs.readFileSync(path.join(repoRoot, relative), "utf8");

const activeFacade = read("almdina_erp/public/js/door_cutting_order/drawing/special_shape_facade.js");
const v4Bootstrap = read("almdina_erp/public/js/door_drawing_v4/bootstrap.js");
const shortcuts = read("almdina_erp/public/js/door_drawing_v3/application/editor_shortcuts.js");
const nodePolicy = read("almdina_erp/public/js/door_drawing_v3/application/node_selection_policy.js");

assert.match(activeFacade, /door_drawing_v4\/bootstrap\.js/);
assert.match(v4Bootstrap, /door_drawing_v4\/domain\/geometry\.js/);
assert.match(v4Bootstrap, /door_drawing_v4\/presentation\/editor_controller\.js/);
assert.match(activeFacade, /__doorDrawingV4:\s*true/);
assert.doesNotMatch(activeFacade, /door_drawing_v3\//);
assert.doesNotMatch(v4Bootstrap, /door_drawing_v3\//);
assert.doesNotMatch(activeFacade, /__doorDrawingV3ProfessionalShortcuts|__doorDrawingV3MultiClipboard|__doorDrawingV3SelectionNodeDrag/);

assert.match(shortcuts, /KeyA:\s*"a"/, "Select-all must use the physical KeyA location");
assert.match(shortcuts, /KeyC:\s*"c"/, "Copy must be keyboard-layout independent");
assert.match(shortcuts, /KeyD:\s*"d"/, "Duplicate must be keyboard-layout independent");
assert.match(shortcuts, /KeyV:\s*"v"/, "Paste must be keyboard-layout independent");
assert.match(shortcuts, /KeyX:\s*"x"/, "Cut must be keyboard-layout independent");
assert.match(shortcuts, /KeyY:\s*"y"/, "Redo must be keyboard-layout independent");
assert.match(shortcuts, /KeyZ:\s*"z"/, "Undo must be keyboard-layout independent");
assert.match(shortcuts, /function shortcutKey\(event\)/, "One shortcut normalizer must own keyboard-layout handling");
assert.match(shortcuts, /key === "c"/);
assert.match(shortcuts, /key === "x"/);
assert.match(shortcuts, /key === "v"/);
assert.match(shortcuts, /key === "z"/);
assert.match(shortcuts, /key === "y"/);
assert.match(shortcuts, /event\.shiftKey \? redo\(c\) : undo\(c\)/, "Ctrl/Cmd+Shift+Z must redo");
assert.match(shortcuts, /Array\.isArray\(c\s*&&\s*c\.selectedIds\)/, "Clipboard must understand multi-selection");
assert.match(shortcuts, /function cutSelection\(c\)/, "Cut must be a first-class editor command");
assert.match(shortcuts, /D\.removeObject\(document, id\)/, "Cut must remove selected geometry from the document model");
assert.match(shortcuts, /Paste \$\{ids\.length\} objects/, "Multi-object paste must be one history command");
assert.match(shortcuts, /Cut \$\{ids\.length\} objects/, "Multi-object cut must be one history command");
assert.match(shortcuts, /G\.cloneObject\(source, nextId\(source\.type\)\)/, "Paste must clone geometry rather than share object identity");

assert.match(nodePolicy, /data-ddv3-tool=\\?"select\\?"/, "Selection tool intent must be recognized");
assert.match(nodePolicy, /__selectionToolNodeEditSnapshot/, "Node edit state must be preserved while choosing V/select");
assert.match(nodePolicy, /event\.key !== "Enter"/, "Enter must be a supported vector-edit entry gesture");
assert.match(nodePolicy, /c\.nodeEditId = String\(object\.id\)/, "Selected path must enter node edit mode");

console.log("Door Drawing V3 layout-independent shortcut legacy contracts passed; active facade remains V4");
