"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(filename) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", filename), "utf8");
}

function assignment(id) {
    return {
        piece_instance_id: id,
        piece_label: id,
        business_state: "UNASSIGNED",
        business_state_label: "غير محدد",
    };
}

function planRow(name, geometryIdentity, assignments) {
    return {
        name,
        snapshot_json: JSON.stringify({
            identity: geometryIdentity,
            sheets: [{ sheet_no: 1, pieces: [] }],
        }),
        offcut: {
            assignments,
            summary: [{ label: "غير محدد", count: assignments.length }],
            state_options: [{ value: "UNASSIGNED", label: "غير محدد" }],
        },
    };
}

const system = planRow("CP-SYSTEM", "SYSTEM", []);
const uploaded = planRow("CP-UPLOADED", "UPLOADED", [assignment("DXF:1"), assignment("DXF:2")]);
const approved = planRow("CP-APPROVED", "APPROVED-UPLOADED", [assignment("DXF:1"), assignment("DXF:2")]);
const workspaceSnapshot = {
    status: "ready",
    data: {
        approved_plan: approved.name,
        plans: {
            system_draft: system,
            uploaded_draft: uploaded,
            approved,
        },
    },
};

const listeners = new Map();
const fakeWindow = {
    AlmdinaPermissions: {
        canDocument() {
            return true;
        },
        can() {
            return true;
        },
    },
    AlmdinaWorkspaceStore: {
        create() {
            return { snapshot: () => workspaceSnapshot };
        },
    },
    addEventListener(name, handler) {
        listeners.set(name, handler);
    },
    dispatchEvent() {
        return true;
    },
};
const fakeFrappe = {
    ui: { form: { on() {} } },
    utils: { escape_html: value => String(value) },
};
const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    document: {},
    console,
    CustomEvent: class CustomEvent {
        constructor(type, options) {
            this.type = type;
            this.detail = options && options.detail;
        }
    },
    $: value => value,
    __: value => value,
    Promise,
    Object,
    Array,
    String,
    Number,
    Boolean,
    JSON,
    Set,
});

vm.runInContext(
    source("door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js"),
    context
);
vm.runInContext(
    source("door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"),
    context
);
vm.runInContext(
    source("door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js"),
    context
);

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-VISIBLE-PLAN",
        approved_plan: approved.name,
        system_plan_json: JSON.parse(system.snapshot_json),
        cutting_plan_json: JSON.parse(system.snapshot_json),
        custom_plan_json: JSON.parse(uploaded.snapshot_json),
    },
    __almdina_approved_plan_order: "DCO-VISIBLE-PLAN",
    __almdina_approved_plan_snapshot: JSON.parse(approved.snapshot_json),
};
fakeWindow.cur_frm = frm;

const state = fakeWindow.AlmdinaPlanWorkspaceState;
const planUx = fakeWindow.AlmdinaDoorCuttingPlanUX;
const tabs = fakeWindow.AlmdinaPlanTabsUX;

function assertVisiblePlan(tab, expectedRow, expectedGeometry, expectedOffcutCount) {
    frm.__almdina_active_plan_tab = tab;
    const displayed = state.displayedPlan(frm);
    const geometry = tabs.getPlanForTab(frm, tabs.activeTab(frm));
    const offcut = planUx.offcutContext(frm);

    assert.equal(displayed.name, expectedRow.name);
    assert.equal(JSON.parse(displayed.snapshot_json).identity, expectedGeometry);
    assert.equal(geometry.identity, expectedGeometry);
    assert.equal(offcut.plan.name, expectedRow.name);
    assert.equal(offcut.assignments.length, expectedOffcutCount);
}

assertVisiblePlan("System", system, "SYSTEM", 0);
assert.equal(planUx.offcutPanelHtml(frm), "", "System without OFFCUT must hide the panel");

assertVisiblePlan("Custom", uploaded, "UPLOADED", 2);
assert.match(planUx.offcutPanelHtml(frm), /2 قطع/);
assert.match(planUx.offcutPanelHtml(frm), /تحديد مصدر وتنفيذ قطع النقص/);

assertVisiblePlan("System", system, "SYSTEM", 0);
assert.equal(planUx.offcutPanelHtml(frm), "", "returning to System must clear Uploaded OFFCUT UI");

assertVisiblePlan("Approved", approved, "APPROVED-UPLOADED", 2);
assert.match(planUx.offcutPanelHtml(frm), /2 قطع/);

const planUxSource = source("door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js");
assert.match(planUxSource, /saveOffcutAssignments\(plan\.name, rows\)/);
assert.doesNotMatch(planUxSource, /activePlan\(frm,\s*["']System["']\)/);
assert.match(planUxSource, /almdina:plan-selection-changed/);

fakeWindow.AlmdinaPlanPreviewSession = {
    isReady() {
        return true;
    },
    previewRow() {
        return planRow("preview:1", "PREVIEW", []);
    },
};
frm.__almdina_active_plan_tab = "System";
assert.equal(state.displayedPlan(frm).name, "preview:1");
assert.equal(planUx.offcutPanelHtml(frm), "", "preview geometry must not leak persisted OFFCUT state");

console.log("OFFCUT visible-plan binding simulation passed");
