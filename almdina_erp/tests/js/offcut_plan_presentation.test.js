"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_source_presentation.js"
    ),
    "utf8"
);

function piece(id, extra = {}) {
    return {
        piece_instance_id: id,
        label: id,
        geometry: {
            schema_version: 1,
            outer: [[0, 0], [100, 0], [100, 200], [0, 200]],
            holes: [],
        },
        ...extra,
    };
}

function assignment(id, state, label) {
    return {
        piece_instance_id: id,
        business_state: state,
        business_state_label: label,
    };
}

function renderRaw(plan) {
    return `<div class="dco-cutting-plan">${plan.sheets.map(sheet => `
        <div class="dco-sheet-card" data-resource-kind="${sheet.resource_kind || "FULL_BOARD"}">
            <div class="dco-sheet-title" style="display:flex"><div>لوح ${sheet.sheet_no}</div><div>عدد القطع: ${(sheet.pieces || []).length}</div></div>
            <div class="dco-sheet-board"><span>${sheet.sheet_no}</span></div>
        </div>
    `).join("")}</div>`;
}

const printCalls = [];
const fakeWindow = {
    AlmdinaCuttingPlanRender: {
        build(_frm, plan) {
            return renderRaw(plan);
        },
        parse() {
            return null;
        },
        print(_frm, planOverride) {
            printCalls.push(planOverride);
            return planOverride;
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    console,
    Object,
    Array,
    String,
    Number,
    Set,
    Map,
});
vm.runInContext(source, context, {
    filename: "door_cutting_order_plan_source_presentation.js",
});

const presentation = fakeWindow.AlmdinaPlanSourcePresentation;
assert.ok(presentation);
assert.ok(fakeWindow.AlmdinaCuttingPlanRender.__almadina179SourcePresentation);

function labels(plan) {
    return Array.from(presentation.project(plan), sourceRow => sourceRow.primary_label);
}

const fullOnly = {
    sheets: [
        { sheet_no: 7, full_board_no: 1, resource_kind: "FULL_BOARD", pieces: [piece("1:1")] },
        { sheet_no: 8, full_board_no: 2, resource_kind: "FULL_BOARD", pieces: [piece("2:1")] },
        { sheet_no: 9, full_board_no: 3, resource_kind: "FULL_BOARD", pieces: [piece("3:1")] },
    ],
};
assert.deepEqual(labels(fullOnly), ["لوح 1", "لوح 2", "لوح 3"]);

const mixed = {
    sheets: [
        { sheet_no: 1, full_board_no: 1, resource_kind: "FULL_BOARD", pieces: [piece("1:1")] },
        { sheet_no: 2, full_board_no: null, resource_kind: "OFFCUT", pieces: [piece("2:1")] },
        { sheet_no: 3, full_board_no: 2, resource_kind: "FULL_BOARD", pieces: [piece("3:1")] },
        { sheet_no: 4, full_board_no: null, resource_kind: "OFFCUT", pieces: [piece("4:1")] },
        { sheet_no: 5, full_board_no: 3, resource_kind: "FULL_BOARD", pieces: [piece("5:1")] },
    ],
    __offcut_assignments: [
        assignment("2:1", "CUSTOMER_FACTORY", "فضلة من الزبون — تنفيذ في المعمل"),
        assignment("4:1", "FACTORY_FACTORY", "فضلة من المعمل — تنفيذ في المعمل"),
    ],
};
assert.deepEqual(labels(mixed), ["لوح 1", "نقص", "لوح 2", "نقص", "لوح 3"]);

const legacy = {
    sheets: [
        { sheet_no: 11, resource_kind: "OFFCUT", pieces: [piece("L:1")] },
        { sheet_no: 12, resource_kind: "FULL_BOARD", pieces: [piece("L:2")] },
        { sheet_no: 13, resource_kind: "OFFCUT", pieces: [piece("L:3")] },
        { sheet_no: 14, resource_kind: "FULL_BOARD", pieces: [piece("L:4")] },
    ],
};
assert.deepEqual(labels(legacy), ["نقص", "لوح 1", "نقص", "لوح 2"]);

const allOffcut = {
    sheets: [
        { sheet_no: 21, resource_kind: "OFFCUT", pieces: [piece("O:1")] },
        { sheet_no: 22, resource_kind: "OFFCUT", pieces: [piece("O:2")] },
    ],
};
assert.deepEqual(labels(allOffcut), ["نقص", "نقص"]);
assert.equal(labels(allOffcut).some(label => label.startsWith("لوح")), false);
assert.equal(labels(allOffcut).some(label => /نقص\s+\d/.test(label)), false);

const statePlan = {
    sheets: [
        {
            sheet_no: 31,
            resource_kind: "OFFCUT",
            pieces: [piece("S:1"), piece("S:2"), piece("S:3"), piece("S:4")],
        },
    ],
    __offcut_assignments: [
        assignment("S:1", "CUSTOMER_FACTORY", "فضلة من الزبون — تنفيذ في المعمل"),
        assignment("S:2", "CUSTOMER_CUSTOMER", "فضلة من الزبون — تنفيذ عند الزبون"),
        assignment("S:3", "FACTORY_FACTORY", "فضلة من المعمل — تنفيذ في المعمل"),
        assignment("S:4", "UNASSIGNED", "غير محدد"),
    ],
};
const stateProjection = presentation.project(statePlan)[0];
assert.equal(stateProjection.primary_label, "نقص");
assert.deepEqual(Array.from(stateProjection.business_context_labels), [
    "فضلة من الزبون — تنفيذ في المعمل",
    "فضلة من الزبون — تنفيذ عند الزبون",
    "فضلة من المعمل — تنفيذ في المعمل",
    "غير محدد",
]);
assert.deepEqual(Array.from(stateProjection.piece_instance_ids), ["S:1", "S:2", "S:3", "S:4"]);

const invalidStatePlan = {
    sheets: [
        { sheet_no: 41, resource_kind: "OFFCUT", pieces: [piece("I:1")] },
    ],
    __offcut_assignments: [
        assignment("I:1", "FACTORY_CUSTOMER", "فضلة من المعمل — تنفيذ عند الزبون"),
    ],
};
const invalidProjection = presentation.project(invalidStatePlan)[0];
assert.deepEqual(Array.from(invalidProjection.business_context_labels), ["غير محدد"]);
assert.doesNotMatch(
    presentation.decorateHtml(renderRaw(invalidStatePlan), invalidStatePlan),
    /فضلة من المعمل — تنفيذ عند الزبون/
);

const immutablePlan = JSON.parse(JSON.stringify(mixed));
const before = JSON.stringify(immutablePlan);
presentation.project(immutablePlan);
assert.equal(JSON.stringify(immutablePlan), before, "presentation projection must not mutate canonical plan data");
assert.equal(immutablePlan.sheets[1].sheet_no, 2);
assert.equal(immutablePlan.sheets[1].pieces[0].piece_instance_id, "2:1");
assert.deepEqual(immutablePlan.sheets[1].pieces[0].geometry.outer, [[0, 0], [100, 0], [100, 200], [0, 200]]);

const decoratedHtml = fakeWindow.AlmdinaCuttingPlanRender.build({}, mixed);
const primaryHeadings = [...decoratedHtml.matchAll(/dco-sheet-title[^>]*>\s*<div>([^<]+)<\/div>/g)]
    .map(match => match[1]);
assert.deepEqual(primaryHeadings, ["لوح 1", "نقص", "لوح 2", "نقص", "لوح 3"]);
assert.match(decoratedHtml, /فضلة من الزبون — تنفيذ في المعمل/);
assert.match(decoratedHtml, /فضلة من المعمل — تنفيذ في المعمل/);
assert.equal((decoratedHtml.match(/dco-offcut-business-context"/g) || []).length, 2);
assert.match(decoratedHtml, /dco-sheet-board/);

const visibleRoot = { querySelector: selector => selector === ".dco-cutting-plan" ? {} : null };
const visibleFrm = {
    fields_dict: {
        cutting_plan_html: {
            $wrapper: { get: () => visibleRoot },
        },
    },
};
fakeWindow.AlmdinaCuttingPlanRender.print(visibleFrm, mixed);
assert.equal(printCalls.at(-1), null, "print must clone the already projected visible plan for screen/print parity");

const hiddenFrm = {
    fields_dict: {
        cutting_plan_html: {
            $wrapper: { get: () => ({ querySelector: () => null }) },
        },
    },
};
fakeWindow.AlmdinaCuttingPlanRender.print(hiddenFrm, mixed);
assert.strictEqual(printCalls.at(-1), mixed, "legacy print fallback must preserve the explicit plan override");

console.log("ALMADINA-179 OFFCUT plan presentation simulation passed");
