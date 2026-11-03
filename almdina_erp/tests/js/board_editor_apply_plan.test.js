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
const workspace = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"),
    "utf8"
);
const arCsv = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");

assert.match(canvas, /Apply to cutting plan/);
assert.match(canvas, /Apply this layout as an unapproved edited cutting plan copy\./);
assert.match(controller, /rememberApplyReturnContext/);
assert.match(controller, /almdina\.dco\.planTab\./);
assert.match(controller, /almdina\.dco\.planApplyReturn\./);
assert.match(controller, /response\.order_name/);
assert.match(controller, /response\.plan_name/);
assert.match(controller, /backToOrder\(orderName\)/);
assert.match(controller, /The edited layout was applied as cutting plan/);
assert.match(controller, /Applying the layout to a cutting plan failed\. The saved draft is unchanged\./);
assert.doesNotMatch(controller, /planWorkspaceReload/);
assert.match(tabs, /consumePreferredPlanTab/);
assert.match(tabs, /almdina\.dco\.planTab\./);
assert.match(tabs, /BoardEditor/);
assert.match(tabs, /dco-plan-apply-return-retry/);
assert.match(tabs, /Retry loading the plan/);
assert.match(page, /controller\.js\?v=23/);
assert.match(page, /transform_geometry\.js\?v=1/);
assert.match(page, /measure_geometry\.js\?v=1/);
assert.match(page, /canvas_renderer\.js\?v=23/);
assert.match(workspace, /planApplyReturn/);
assert.match(workspace, /settleApplyReturn/);
assert.match(workspace, /retryApplyReturnRead/);
assert.match(workspace, /board_editor_plan_applied/);
assert.match(arCsv, /Retry loading the plan/);
assert.match(arCsv, /Waiting for the edited cutting plan to appear\.\.\./);
assert.match(arCsv, /A newer edited cutting plan \(\{0\}\) is shown/);

console.log("board_editor_apply_plan.test.js: ok");
