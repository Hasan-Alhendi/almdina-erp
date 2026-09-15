"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

function source(filename) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", filename), "utf8");
}

const planUx = source("door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js");
const costOffcut = source(
    "door_cutting_order/costing/door_cutting_order_cost_offcut_assignment_ux.js"
);
const costLayout = source(
    "door_cutting_order/costing/door_cutting_order_cost_page_layout_ux.js"
);
const registry = source(
    "door_cutting_order/core/door_cutting_order_workspace_asset_registry.js"
);
const api = source("door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js");
const dependencyPolicy = source(
    "door_cutting_order/order_entry/door_cutting_order_mutation_impact_policy.js"
);

assert.doesNotMatch(planUx, /dco-open-offcut-editor/);
assert.doesNotMatch(planUx, /new frappe\.ui\.Dialog/);
assert.doesNotMatch(planUx, /saveOffcutAssignments\(/);

assert.match(costOffcut, /function projection\(frm\)/);
assert.match(costOffcut, /state\.data/);
assert.match(costOffcut, /piece_instance_id/);
assert.match(costOffcut, /type="radio"/);
assert.match(costOffcut, /CUSTOMER_FACTORY/);
assert.match(costOffcut, /FACTORY_FACTORY/);
assert.match(costOffcut, /CUSTOMER_CUSTOMER/);
assert.match(costOffcut, /dco-cost-offcut-table/);
assert.doesNotMatch(costOffcut, /dco-cost-offcut-summary/);
assert.match(costOffcut, /saveOffcutAssignments\(offcut\.plan_name, assignments\(root\)\)/);
assert.match(costOffcut, /savePending/);
assert.doesNotMatch(costOffcut, /dco-cost-offcut-save/);
assert.match(costOffcut, /policy\.reconcileOffcutMutation\(frm, result\)/);
assert.match(costOffcut, /captureDocument\(frm\)/);
assert.match(costOffcut, /documentStillCurrent\(frm, token\)/);
assert.doesNotMatch(costOffcut, /frappe\.call\(/);
assert.doesNotMatch(costOffcut, /setTimeout\s*\(/);
assert.doesNotMatch(costOffcut, /location\.reload\s*\(/);

assert.match(costLayout, /AlmdinaCostOffcutAssignmentUX/);
assert.match(registry, /door_cutting_order_cost_offcut_assignment_ux\.js/);

assert.match(api, /function saveOffcutAssignments/);
assert.doesNotMatch(api, /AlmdinaWorkspaceSyncCoordinator/);
assert.doesNotMatch(api, /cur_frm/);
assert.doesNotMatch(api, /setTimeout\s*\(/);
assert.doesNotMatch(api, /location\.reload\s*\(/);

assert.match(dependencyPolicy, /OFFCUT_CLASSIFICATION_REASON/);
assert.match(dependencyPolicy, /reconcileOffcutMutation/);
assert.match(dependencyPolicy, /coordinator\.reconcile\(/);
assert.doesNotMatch(dependencyPolicy, /setTimeout\s*\(/);
assert.doesNotMatch(dependencyPolicy, /location\.reload\s*\(/);

console.log("OFFCUT Cost-tab ownership simulation passed");
