"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = relative => fs.readFileSync(path.resolve(__dirname, `../../public/js/${relative}`), "utf8");
const controller = read("door_drawing_v4/presentation/editor_controller.js");
const shell = read("door_drawing_v4/presentation/editor_shell.js");

assert.match(controller, /NUMERIC_ENTRY_MODES\.DIMENSION_VALUE/, "dimension numeric entry must have an explicit interaction mode");
assert.match(controller, /engine\.inputDimensionValue\(valueMm\)/, "numeric dimension values must go through the interaction engine");
assert.match(controller, /قياس مرجعي/, "reference dimensions need clear Arabic feedback");
assert.match(controller, /بُعد ثابت/, "driving dimensions need clear Arabic feedback");
assert.match(controller, /لا يمكن تطبيق هذا القياس دون كسر قيود الشكل/, "constraint conflicts need a clear Arabic message");
assert.match(controller, /constraint-protected-node/, "the controller must surface protected constrained-node interactions");
assert.match(shell, /aria-label="القيمة بالميليمتر"/, "the shared numeric entry must have a generic accessible label");
assert.doesNotMatch(controller, /frappe\.ui\.Dialog|frappe\.prompt\s*\(/, "driving dimension editing must stay inline and modal-free");
assert.doesNotMatch(shell, /<dialog\b/i, "the V4 shell must not introduce a modal for dimension entry");

console.log("Door Drawing V4 driving dimension UX contract tests passed");
