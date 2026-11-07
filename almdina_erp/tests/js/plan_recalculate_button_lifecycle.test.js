"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Node {
    constructor(className = "") {
        this.className = className;
        this.children = [];
        this.parent = null;
        this.attrs = {};
        this.textValue = "";
        this.disabled = false;
        this.listeners = [];
    }

    matches(selector) {
        const value = String(selector || "");
        if (value.startsWith(".")) {
            return this.className.split(/\s+/).includes(value.slice(1));
        }
        const attribute = value.match(/^\[([^=]+)="([^"]+)"\]$/);
        return Boolean(attribute && this.attrs[attribute[1]] === attribute[2]);
    }
}

function collect(node, selector, deep) {
    const found = [];
    for (const child of node.children) {
        if (!selector || child.matches(selector)) found.push(child);
        if (deep) found.push(...collect(child, selector, true));
    }
    return found;
}

function wrap(nodes) {
    const api = {
        length: nodes.length,
        0: nodes[0],
        nodes,
        get(index) { return nodes[index]; },
        first() { return wrap(nodes.slice(0, 1)); },
        children(selector) {
            return wrap(nodes.flatMap((node) => collect(node, selector, false)));
        },
        find(selector) {
            return wrap(nodes.flatMap((node) => collect(node, selector, true)));
        },
        append(value) {
            const parent = nodes[0];
            if (!parent) return api;
            if (typeof value === "string") {
                const markup = String(value);
                if (markup.includes("dco-plan-calculate-host")) {
                    const host = new Node("dco-plan-calculate-host");
                    host.parent = parent;
                    parent.children.push(host);
                }
                return api;
            }
            const child = value.get ? value.get(0) : value;
            if (!child) return api;
            if (child.parent) {
                child.parent.children = child.parent.children.filter((item) => item !== child);
            }
            child.parent = parent;
            parent.children.push(child);
            return api;
        },
        remove() {
            nodes.forEach((node) => {
                if (!node.parent) return;
                node.parent.children = node.parent.children.filter((item) => item !== node);
                node.parent = null;
            });
            return api;
        },
        each(callback) {
            nodes.forEach((node, index) => callback(index, node));
            return api;
        },
        on(event, selector, handler) {
            if (nodes[0]) nodes[0].listeners.push({ event, selector, handler });
            return api;
        },
        attr(name, value) {
            const node = nodes[0];
            if (!node) return undefined;
            if (value === undefined) return node.attrs[name];
            node.attrs[name] = value;
            return api;
        },
        prop(name, value) {
            const node = nodes[0];
            if (!node) return undefined;
            if (value === undefined) return node[name];
            node[name] = value;
            return api;
        },
        text(value) {
            const node = nodes[0];
            if (!node) return "";
            if (value === undefined) return node.textValue;
            node.textValue = String(value);
            return api;
        },
        toggleClass(name, enabled) {
            const node = nodes[0];
            if (!node) return api;
            const names = new Set(node.className.split(/\s+/).filter(Boolean));
            if (enabled) names.add(name);
            else names.delete(name);
            node.className = [...names].join(" ");
            return api;
        },
    };
    return api;
}

function $(input) {
    if (typeof input === "string") {
        if (input === "head") return wrap([head]);
        const className = (String(input).match(/class="([^"]+)"/) || [])[1] || "";
        return wrap([new Node(className)]);
    }
    if (input instanceof Node) return wrap([input]);
    return wrap([]);
}

function click(node) {
    if (!node || node.disabled) return;
    let current = node;
    while (current) {
        for (const listener of current.listeners) {
            if (listener.selector && node.matches(listener.selector)) {
                listener.handler({ preventDefault() {}, stopPropagation() {} });
            }
        }
        current = current.parent;
    }
}

const head = new Node();
const root = new Node("plan-control-actions");
const slot = new Node("");
slot.attrs["data-role"] = "recalc";

const previewCalls = [];
const commits = [];
let permissions = { recalculate: true };
let busy = false;
let failPreview = false;

function state() {
    return root.state;
}

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-1",
        docstatus: 0,
        status: "Draft",
        revision_state: "Current",
    },
    fields_dict: { plan_control_actions: { $wrapper: wrap([root]) } },
    is_new() { return false; },
    is_dirty() { return false; },
    set_df_property() {},
};

const window = {
    cur_frm: frm,
    addEventListener() {},
    AlmdinaPermissions: {
        canDocument(_frm, capability) {
            return capability !== "recalculate_plan" || permissions.recalculate;
        },
    },
    AlmdinaPlanWorkspaceState: { snapshot: state },
    AlmdinaPlanPreviewSession: {
        isBusy: () => busy,
        preview(_frm, settings) {
            previewCalls.push({ ...settings });
            if (failPreview) return Promise.reject(new Error("preview failed"));
            return Promise.resolve(true);
        },
        commit() { commits.push("commit"); return Promise.resolve(true); },
    },
    AlmdinaPlanWorkspaceAPI: { preview() { return Promise.resolve(true); } },
    AlmdinaPlanEditSessionUX: { startEditing: () => Promise.resolve(true) },
    AlmdinaUi: {
        button(options) {
            return `<button type="button" class="alm-button ${options.className || ""}"></button>`;
        },
    },
    AlmdinaTextBoardPlanUX: { preparePlanInputs: () => Promise.resolve(true) },
};

const document = {
    getElementById() { return null; },
    createElement() { return {}; },
    head: { appendChild() {} },
    documentElement: { getAttribute() { return "rtl"; } },
};

const frappe = {
    ui: { form: { on() {} } },
    msgprint() {},
    show_alert() {},
};

const context = vm.createContext({
    window,
    document,
    frappe,
    $,
    __: String,
    console,
    MutationObserver: class { observe() {} disconnect() {} },
    Promise,
    Set,
    Map,
    WeakMap,
});
vm.runInContext(
    fs.readFileSync(
        path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js"),
        "utf8"
    ),
    context,
    { filename: "door_cutting_order_plan_controls_ux.js" }
);

const controls = window.AlmdinaPlanControlsUX;

function readyState({ editing = false, systemDraft = null, draft = null, deduct = 0 }) {
    root.state = {
        status: "ready",
        editing,
        draft,
        data: {
            approved_plan: "",
            calculation_settings: { deduct_edge_thickness: deduct, kerf_mm: 3 },
            plans: { system_draft: systemDraft },
        },
    };
}

function buttons() {
    return wrap([root]).find(".dco-recalculate-plan").nodes;
}

function sync() {
    controls.syncRecalculateButton(frm);
}

async function flush() {
    await new Promise((resolve) => setTimeout(resolve, 0));
}

async function main() {
readyState({ deduct: 0 });
sync();
assert.equal(buttons().length, 1);
assert.equal(buttons()[0].textValue, "Calculate the cutting plan");
assert.equal(buttons()[0].disabled, false);
click(buttons()[0]);
click(buttons()[0]);
await flush();
assert.equal(previewCalls.length, 1);
assert.equal(previewCalls[0].deduct_edge_thickness, 0);
assert.equal(commits.length, 0);
assert.equal(root.state.data.approved_plan, "");

previewCalls.length = 0;
readyState({ deduct: 1 });
sync();
assert.equal(buttons()[0].disabled, false);
click(buttons()[0]);
await flush();
assert.equal(previewCalls.length, 1);
assert.equal(previewCalls[0].deduct_edge_thickness, 1);

previewCalls.length = 0;
const systemDraft = { name: "CP-1", status: "Draft" };
root.children = [slot];
slot.parent = root;
slot.children = [];
readyState({
    editing: true,
    systemDraft,
    draft: { deduct_edge_thickness: 0, kerf_mm: 3 },
});
sync();
assert.equal(buttons().length, 1);
assert.equal(buttons()[0].parent, slot);
assert.equal(buttons()[0].textValue, "Recalculate with the current settings");
click(buttons()[0]);
await flush();
assert.equal(previewCalls.length, 1);
assert.equal(previewCalls[0].deduct_edge_thickness, 0);
assert.equal(previewCalls[0].kerf_mm, 3);

previewCalls.length = 0;
root.state.draft = { deduct_edge_thickness: 1, kerf_mm: 4 };
sync();
click(buttons()[0]);
await flush();
assert.equal(previewCalls.length, 1);
assert.equal(previewCalls[0].deduct_edge_thickness, 1);
assert.equal(previewCalls[0].kerf_mm, 4);

const previous = buttons()[0];
previous.parent.children = previous.parent.children.filter((item) => item !== previous);
frm.__almdina_active_plan_tab = "Custom";
sync();
frm.__almdina_active_plan_tab = "Approved";
sync();
frm.__almdina_active_plan_tab = "System";
sync();
assert.equal(buttons().length, 1);
assert.notEqual(buttons()[0], previous);
previewCalls.length = 0;
click(buttons()[0]);
await flush();
assert.equal(previewCalls.length, 1);

failPreview = true;
previewCalls.length = 0;
click(buttons()[0]);
await flush();
assert.equal(previewCalls.length, 1);
failPreview = false;
sync();
assert.equal(buttons()[0].disabled, false);
previewCalls.length = 0;
click(buttons()[0]);
await flush();
assert.equal(previewCalls.length, 1);

permissions.recalculate = false;
sync();
assert.equal(buttons()[0].disabled, true);
assert.match(String(buttons()[0].attrs.title || ""), /Recalculate plan/);
previewCalls.length = 0;
click(buttons()[0]);
await controls.runRecalculation(frm);
assert.equal(previewCalls.length, 0);

permissions.recalculate = true;
frm.doc.status = "At CNC";
frm.doc.current_production_stage = "CNC";
root.state.data.approved_plan = "CP-APPROVED";
sync();
assert.equal(buttons()[0].disabled, true);
previewCalls.length = 0;
click(buttons()[0]);
await controls.runRecalculation(frm);
assert.equal(previewCalls.length, 0);
assert.equal(commits.length, 0);
assert.equal(root.state.data.approved_plan, "CP-APPROVED");

frm.doc.status = "Draft";
frm.doc.current_production_stage = "";
root.state.data.approved_plan = "";
readyState({ editing: false, systemDraft });
sync();
assert.equal(buttons().length, 0);

const rendered = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js"),
    "utf8"
);
assert.equal(rendered.includes("Cutting plan commands"), false);
assert.equal(rendered.includes("أوامر خطة القص"), false);
assert.equal(commits.length, 0);

console.log("plan recalculate button lifecycle passed");
}

main();
