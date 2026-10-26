"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"),
    "utf8",
);

function functionSource(sourceText, name) {
    const start = sourceText.indexOf(`function ${name}(`);
    assert.notEqual(start, -1, `${name} remains in the workspace state owner`);
    const open = sourceText.indexOf("{", start);
    let depth = 0;
    for (let index = open; index < sourceText.length; index += 1) {
        if (sourceText[index] === "{") depth += 1;
        if (sourceText[index] === "}") depth -= 1;
        if (depth === 0) return sourceText.slice(start, index + 1);
    }
    throw new Error(`Unclosed function ${name}`);
}

const isCurrentDraftRow = new Function(`return (${functionSource(source, "isCurrentDraftRow")})`)();
const state = { data: { plans: {} } };
const snapshot = () => state;
const activePlan = new Function(
    "snapshot", "isCurrentDraftRow",
    `return (${functionSource(source, "activePlan")})`,
)(snapshot, isCurrentDraftRow);
const planForTab = new Function(
    "snapshot",
    `return (${functionSource(source, "planForTab")})`,
)(snapshot);

const historical = {
    name: "CP-HISTORY",
    status: "Cancelled",
    display_context: "historical",
};
state.data.plans.system_draft = historical;
assert.equal(planForTab({ doc: { name: "DCO-1" } }, "System"), historical);
assert.equal(activePlan({ doc: { name: "DCO-1" } }), null);
assert.equal(isCurrentDraftRow(historical), false);

const draft = { name: "CP-DRAFT", status: "Draft", display_context: "current_draft" };
state.data.plans.system_draft = draft;
assert.equal(activePlan({ doc: { name: "DCO-1" } }), draft);
assert.equal(isCurrentDraftRow(draft), true);

const approved = { name: "CP-APPROVED", status: "Approved", display_context: "current_approved" };
state.data.plans.system_draft = historical;
state.data.plans.approved = approved;
assert.equal(activePlan({ doc: { name: "DCO-1" } }), approved);

const controlsSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js"),
    "utf8",
);
const hasSystemDraft = new Function(
    "plans", "stateOwner",
    `return (${functionSource(controlsSource, "hasSystemDraft")})`,
)(() => ({ system_draft: historical }), () => ({ isCurrentDraftRow }));
assert.equal(hasSystemDraft({}), false, "historical System row does not block first-plan setup");
const hasCurrentSystemDraft = new Function(
    "plans", "stateOwner",
    `return (${functionSource(controlsSource, "hasSystemDraft")})`,
)(() => ({ system_draft: draft }), () => ({ isCurrentDraftRow }));
assert.equal(hasCurrentSystemDraft({}), true);

console.log("Historical plan display and active-plan selection passed");
