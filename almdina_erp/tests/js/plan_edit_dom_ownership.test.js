"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

function read(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, relativePath), "utf8");
}

function functionBlock(source, startMarker, endMarker) {
    const start = source.indexOf(startMarker);
    const end = source.indexOf(endMarker, start);
    assert.notEqual(start, -1, `missing ${startMarker}`);
    assert.notEqual(end, -1, `missing ${endMarker}`);
    return source.slice(start, end);
}

const planSource = read("../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js");
const editSource = read("../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js");
const controlsSource = read("../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js");
const contextSource = read("../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_context_actions_ux.js");

const renderActions = functionBlock(planSource, "function renderActions(frm)", "async function recalculate");
assert.match(renderActions, /wrapper\.children\("\.dco-plan-actions-shell"\)\.remove\(\)/);
assert.match(renderActions, /controls\.syncRecalculateButton\(frm\)/);
assert.doesNotMatch(renderActions, /Cutting plan commands/);
assert.doesNotMatch(renderActions, /\.on\("click"/);
assert.doesNotMatch(renderActions, /field\.\$wrapper\.(?:html|empty)\(/);

const mount = functionBlock(editSource, "function mountDraftControls(frm)", "function syncEditorChrome");
assert.match(mount, /data-role="recalc"/);
assert.doesNotMatch(mount, /preserveRecalculateButton/);
assert.doesNotMatch(mount, /\.dco-recalculate-plan/);
assert.match(editSource, /controls\.syncRecalculateButton\(frm\)/);
assert.doesNotMatch(editSource, /recalcSlot\.append\(button\)/);

const delegation = functionBlock(controlsSource, "function bindRecalculateDelegation", "function buttonHost");
assert.match(delegation, /click\.almdinaRecalculate/);
assert.match(delegation, /__almdinaRecalculateDelegated/);
assert.match(controlsSource, /function syncRecalculateButton/);
assert.match(contextSource, /dco-plan-context-approve/);
assert.match(contextSource, /dco-print-cutting-plan/);
assert.match(contextSource, /dco-export-dxf/);
assert.match(contextSource, /dco-upload-dxf-plan/);
assert.doesNotMatch(planSource, /Cutting plan commands/);

console.log("plan edit DOM ownership contract passed");
