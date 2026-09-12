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

const renderActions = functionBlock(planSource, "function renderActions(frm)", "async function recalculate");
assert.match(renderActions, /const wrapper = field\.\$wrapper;/);
assert.match(renderActions, /wrapper\.children\("\.dco-plan-actions-shell"\)\.remove\(\)/);
assert.match(renderActions, /wrapper\.append\(`/);
assert.match(renderActions, /const shell = wrapper\.children\("\.dco-plan-actions-shell"\)\.last\(\)/);
assert.doesNotMatch(renderActions, /field\.\$wrapper\.(?:html|empty)\(/);
assert.doesNotMatch(renderActions, /field\.\$wrapper\.find\(/);

const pending = functionBlock(planSource, "function renderWorkspacePending(frm)", "function refreshPlanUX(frm)");
assert.match(pending, /actions\.\$wrapper\.children\("\.dco-plan-actions-shell"\)\.remove\(\)/);
assert.doesNotMatch(pending, /actions\.\$wrapper\.empty\(\)/);

const editorHost = functionBlock(editSource, "function editorHost(frm)", "function markEditorDirty");
assert.match(editorHost, /return actionSurface\(frm\);/);
assert.doesNotMatch(editorHost, /dco-plan-actions-shell/);
const mount = functionBlock(editSource, "function mountDraftControls(frm)", "function unmountDraftControls(frm)");
assert.match(mount, /host\.children\(EDITOR_SELECTOR\)\.remove\(\)/);
assert.match(mount, /host\.prepend\(`/);
assert.match(mount, /const editor = host\.children\(EDITOR_SELECTOR\)\.first\(\)/);
const unmount = functionBlock(editSource, "function unmountDraftControls(frm)", "function focusDraftControl(frm");
assert.match(unmount, /wrapper\.children\(EDITOR_SELECTOR\)\.remove\(\)/);

const simplify = functionBlock(controlsSource, "function simplifyActions(frm)", "function apply(frm)");
assert.doesNotMatch(simplify, /field\.\$wrapper\.empty\(\)/);
assert.match(simplify, /field\.\$wrapper\.children\("\.dco-plan-actions-shell"\)\.first\(\)/);
assert.match(simplify, /shell\.find\(DUPLICATED_ACTIONS\)/);
assert.match(simplify, /installApprovalAction\(frm, shell\)/);

function rerenderActions(root) {
    return root.filter(name => name !== "dco-plan-actions-shell").concat("dco-plan-actions-shell");
}
function unmountEditor(root) {
    return root.filter(name => name !== "dco-plan-settings-editor");
}

let root = ["dco-plan-settings-editor", "dco-plan-actions-shell"];
for (let i = 0; i < 5; i += 1) root = rerenderActions(root);
assert.deepEqual(root, ["dco-plan-settings-editor", "dco-plan-actions-shell"]);
root = unmountEditor(root);
assert.deepEqual(root, ["dco-plan-actions-shell"], "Cancel/Save cleanup must leave PlanUX actions intact");

let reverse = ["dco-plan-actions-shell"];
reverse.unshift("dco-plan-settings-editor");
reverse = rerenderActions(reverse);
assert.deepEqual(reverse, ["dco-plan-settings-editor", "dco-plan-actions-shell"]);

console.log("plan edit DOM ownership contract passed");
