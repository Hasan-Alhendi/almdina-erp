"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_plan_cost_workspace_visual_ux.js"
    ),
    "utf8"
);

function makeNode() {
    const attributes = new Map();
    const classes = new Set();
    return {
        attributes,
        classList: {
            add(value) {
                classes.add(value);
            },
            contains(value) {
                return classes.has(value);
            },
        },
        setAttribute(name, value) {
            attributes.set(name, String(value));
        },
        removeAttribute(name) {
            attributes.delete(name);
        },
        getAttribute(name) {
            return attributes.has(name) ? attributes.get(name) : null;
        },
    };
}

function wrapper(node) {
    return { 0: node, length: 1 };
}

const root = makeNode();
const pageRoot = makeNode();
const planActions = makeNode();
const planHtml = makeNode();
const planIntro = makeNode();
const costHtml = makeNode();
const optimizer = makeNode();
const boardRate = makeNode();

const fields = {
    plan_controls_intro: { $wrapper: wrapper(planIntro) },
    plan_control_actions: { $wrapper: wrapper(planActions) },
    cutting_plan_html: { $wrapper: wrapper(planHtml) },
    packing_mode: { $wrapper: wrapper(optimizer) },
    cutting_machine_type: { $wrapper: wrapper(makeNode()) },
    kerf_mm: { $wrapper: wrapper(makeNode()) },
    trim_margin_mm: { $wrapper: wrapper(makeNode()) },
    optimization_time_limit_sec: { $wrapper: wrapper(makeNode()) },
    order_cost_invoice_html: { $wrapper: wrapper(costHtml) },
    board_rate_usd: { $wrapper: wrapper(boardRate) },
    cutting_cost_per_board_usd: { $wrapper: wrapper(makeNode()) },
};

const frm = {
    doctype: "Door Cutting Order",
    wrapper: root,
    page: { wrapper: pageRoot },
    fields_dict: fields,
};

let planSnapshot = { status: "loading", editing: false, data: null };
let costSnapshot = {
    status: "ready",
    editing: true,
    data: { order: { board_rate_usd: 10, cutting_cost_per_board_usd: 2 } },
};

const listeners = new Map();
const appendedStyles = [];
const fakeDocument = {
    head: {
        appendChild(node) {
            appendedStyles.push(node);
        },
    },
    getElementById(id) {
        return appendedStyles.find(node => node.id === id) || null;
    },
    createElement(tag) {
        return { tagName: tag.toUpperCase(), id: "", textContent: "" };
    },
};

const fakeWindow = {
    cur_frm: frm,
    AlmdinaPlanWorkspaceState: {
        snapshot() {
            return planSnapshot;
        },
    },
    AlmdinaCostWorkspaceState: {
        snapshot() {
            return costSnapshot;
        },
    },
    AlmdinaDocumentContext: {
        scheduleFrame(_frm, _key, callback) {
            callback();
        },
    },
    addEventListener(name, handler) {
        listeners.set(name, handler);
    },
    requestAnimationFrame(callback) {
        callback();
    },
};

const fakeFrappe = {
    ui: {
        form: {
            on() {},
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    document: fakeDocument,
    frappe: fakeFrappe,
    console,
    Object,
    String,
    Boolean,
    Array,
});

vm.runInContext(source, context, {
    filename: "door_cutting_order_plan_cost_workspace_visual_ux.js",
});

const visual = fakeWindow.AlmdinaPlanCostWorkspaceVisualUX;
assert.ok(visual);
assert.equal(visual.refresh(frm), true);
assert.equal(appendedStyles.length, 1);
assert.equal(root.classList.contains("dco-a53-workspace-polish"), true);
assert.equal(pageRoot.classList.contains("dco-a53-workspace-polish"), true);

assert.equal(planActions.getAttribute("data-almdina-workspace-status"), "loading");
assert.equal(planActions.getAttribute("aria-busy"), "true");
assert.equal(planHtml.getAttribute("aria-live"), "polite");
assert.equal(costHtml.getAttribute("data-almdina-workspace-status"), "ready");
assert.equal(costHtml.getAttribute("data-almdina-workspace-editing"), "1");
assert.equal(costHtml.getAttribute("aria-live"), "polite");
assert.equal(boardRate.getAttribute("data-almdina-workspace-editing"), "1");

planSnapshot = {
    status: "ready",
    editing: false,
    data: {
        plans: {
            system_draft: {
                validation: { needs_recalculation: true },
            },
        },
    },
};
costSnapshot = { status: "error", editing: false, data: null };

listeners.get("almdina:plan-workspace-updated")();
assert.equal(planActions.getAttribute("data-almdina-workspace-status"), "ready");
assert.equal(planActions.getAttribute("aria-busy"), null);
assert.equal(planActions.getAttribute("data-almdina-workspace-stale"), "1");
assert.equal(costHtml.getAttribute("data-almdina-workspace-status"), "error");
assert.equal(costHtml.getAttribute("data-almdina-workspace-editing"), "0");

visual.refresh(frm);
assert.equal(appendedStyles.length, 1, "style installation must be idempotent");

console.log("Plan/Cost workspace visual simulation passed");
