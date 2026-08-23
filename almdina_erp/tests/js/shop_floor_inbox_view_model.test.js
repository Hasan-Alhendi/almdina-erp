"use strict";

const assert = require("node:assert/strict");
global.window = global;
const viewModel = require("../../public/js/shop_floor_inbox/view_model.js");

const context = {
    personal_inbox: true,
    production_routes: [{
        name: "route-a",
        label: "المسار أ",
        stages: [
            { sequence: 1, stage_type: "Cutting", department: "القص" },
            { sequence: 2, stage_type: "Edge", department: "القشاط" },
        ],
    }],
};

const active = [
    {
        name: "stage-1",
        door_cutting_order: "DCO-1",
        production_path: "route-a",
        stage_type: "Cutting",
        department_label: "القص",
        actor_holds_current_stage_role: true,
        can_start_stage: true,
        can_handoff_stage: false,
        status: "Pending",
        customer: "أحمد",
    },
    {
        name: "stage-2",
        door_cutting_order: "DCO-2",
        production_path: "route-a",
        stage_type: "Edge",
        department_label: "القشاط",
        actor_holds_current_stage_role: false,
        can_start_stage: false,
        can_handoff_stage: true,
        status: "In Progress",
        customer: "محمد",
    },
];

const archive = [
    { door_cutting_order: "DCO-1", production_path: "route-a", stage_type: "Edge", order_status: "Ready for Delivery" },
    { door_cutting_order: "DCO-3", production_path: "route-a", stage_type: "Edge", order_status: "Ready for Delivery" },
];

assert.deepEqual(
    viewModel.workerBoardRows(active, context).map(row => row.door_cutting_order),
    ["DCO-1"]
);

const merged = viewModel.mergeVisibleList(active, archive, context);
assert.deepEqual(merged.assigned.map(row => row.door_cutting_order), ["DCO-1"]);
assert.deepEqual(merged.completed.map(row => row.door_cutting_order), ["DCO-3"]);

const board = viewModel.board({
    mode: "board",
    sessionContext: context,
    boardRows: active,
    archiveRows: archive,
    routeFilter: "",
    search: "",
});
assert.equal(board.routes.length, 1);
assert.equal(board.routeModels.length, 1);
assert.equal(board.routeModels[0].routeRows.length, 1);
assert.equal(board.routeModels[0].readyRows.length, 2);
assert.deepEqual(board.counts, { pending: 1, progress: 0, paused: 0, ready: 2 });

const searched = viewModel.board({
    mode: "board",
    sessionContext: { ...context, personal_inbox: false },
    boardRows: active,
    archiveRows: archive,
    routeFilter: "route-a",
    search: "محمد",
});
assert.equal(searched.routeModels[0].routeRows.length, 1);
assert.equal(searched.routeModels[0].routeRows[0].door_cutting_order, "DCO-2");

const action = viewModel.quickActionContext(active[0], "board");
assert.equal(action.canStart, true);
assert.equal(action.canHandoff, false);
assert.equal(viewModel.quickActionContext(active[0], "account").canStart, false);

const account = viewModel.account({
    identity: { user: "worker@example.com", full_name: "عامل", departments: ["القص"] },
    navigation: { sections: { orders: true, production: true, costing: false } },
});
assert.deepEqual(account.enabledSections.sort(), ["orders", "production"]);

console.log("shop_floor_inbox view-model simulation: ok");
