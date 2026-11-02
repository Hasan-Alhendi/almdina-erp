"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const canvas = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const tabs = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js"),
    "utf8"
);
const page = fs.readFileSync(
    path.join(root, "almdina_erp/page/board_editor/board_editor.js"),
    "utf8"
);

assert.match(canvas, /Apply to cutting plan/);
assert.match(canvas, /Apply this layout as an unapproved edited cutting plan copy\./);
assert.match(controller, /rememberPreferEditedPlanTab/);
assert.match(controller, /almdina\.dco\.planTab\./);
assert.match(controller, /almdina\.dco\.planWorkspaceReload\./);
assert.match(controller, /backToOrder\(orderName\)/);
assert.match(controller, /The edited layout was applied as cutting plan/);
assert.match(controller, /Applying the layout to a cutting plan failed\. The saved draft is unchanged\./);
assert.match(tabs, /consumePreferredPlanTab/);
assert.match(tabs, /almdina\.dco\.planTab\./);
assert.match(tabs, /BoardEditor/);
assert.match(page, /controller\.js\?v=18/);
const workspace = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"),
    "utf8"
);
assert.match(workspace, /consumeWorkspaceReloadFlag/);
assert.match(workspace, /almdina\.dco\.planWorkspaceReload\./);

console.log("board_editor_apply_plan.test.js: ok");
