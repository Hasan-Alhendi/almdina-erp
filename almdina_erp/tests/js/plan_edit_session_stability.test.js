"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const rootDir = path.resolve(__dirname, "../../public/js/door_cutting_order");

function source(relativePath) {
    return fs.readFileSync(path.join(rootDir, relativePath), "utf8");
}

class Node {
    constructor(className = "") {
        this.className = className;
        this.children = [];
        this.parent = null;
        this.attrs = {};
        this.value = "";
        this.checked = false;
        this.id = "";
        this.listeners = {};
        this.selectionStart = 1;
        this.selectionEnd = 1;
        this.disabled = false;
    }

    matches(selector) {
        const value = String(selector || "");
        if (value.startsWith(".")) return this.className.split(/\s+/).includes(value.slice(1));
        const attribute = value.match(/^\[([^=]+)="([^"]+)"\]$/);
        if (attribute) return this.attrs[attribute[1]] === attribute[2] || (attribute[1] === "id" && this.id === attribute[2]);
        if (value === "[data-almdina-plan-setting]") return Boolean(this.attrs["data-almdina-plan-setting"]);
        return false;
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
        get(index) { return nodes[index]; },
        first() { return wrap(nodes.slice(0, 1)); },
        children(selector) { return wrap(nodes.flatMap((node) => collect(node, selector, false))); },
        find(selector) { return wrap(nodes.flatMap((node) => collect(node, selector, true))); },
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
        val(value) {
            const node = nodes[0];
            if (!node) return "";
            if (value === undefined) return node.value;
            node.value = value;
            return api;
        },
        text(value) {
            const node = nodes[0];
            if (!node) return "";
            if (value === undefined) return node.textValue || "";
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
        on(event, selector, handler) {
            const callback = typeof handler === "function" ? handler : selector;
            const match = typeof handler === "function" ? selector : "";
            nodes.forEach((node) => { node.listeners[event] = { match, callback }; });
            return api;
        },
        off() { return api; },
        removeAttr(name) {
            nodes.forEach((node) => { delete node.attrs[name]; });
            return api;
        },
        each(callback) {
            nodes.forEach((node, index) => callback(index, node));
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
        prepend(html) {
            const parent = nodes[0];
            const section = new Node("dco-plan-settings-editor");
            const structure = String(html).match(/data-editor-structure="([^"]*)"/);
            section.attrs["data-editor-structure"] = structure ? structure[1] : "";
            const slot = new Node("");
            slot.attrs["data-role"] = "recalc";
            slot.parent = section;
            section.children.push(slot);
            const ids = [...String(html).matchAll(/id="(dco-plan-setting-[^"]+)"/g)].map((match) => match[1]);
            const fields = [...String(html).matchAll(/data-almdina-plan-setting="([^"]+)"/g)].map((match) => match[1]);
            ids.forEach((id, index) => {
                const input = new Node("form-control");
                input.id = id;
                input.attrs.id = id;
                input.attrs["data-almdina-plan-setting"] = fields[index] || "";
                input.parent = section;
                section.children.push(input);
            });
            section.parent = parent;
            parent.children.unshift(section);
            parent.prepends += 1;
            return api;
        },
        append(value) {
            const parent = nodes[0];
            const child = value && value.get ? value.get(0) : value;
            if (!parent || !child) return api;
            if (child.parent) child.parent.children = child.parent.children.filter((item) => item !== child);
            child.parent = parent;
            parent.children.push(child);
            return api;
        },
    };
    return api;
}

function $(input) {
    if (input instanceof Node) return wrap([input]);
    if (typeof input === "string" && input !== "head") {
        const className = (input.match(/class="([^"]+)"/) || [])[1] || "";
        return wrap([new Node(className)]);
    }
    return wrap([]);
}

const host = new Node("plan-control-actions");
host.prepends = 0;
const previewCalls = [];
const commits = [];
const messages = [];
let allowRecalculate = true;

const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-1", docstatus: 0, status: "Draft", revision_state: "Current", modified: "2026-11-07" },
    fields_dict: { plan_control_actions: { $wrapper: wrap([host]) } },
    is_new() { return false; },
    is_dirty() { return false; },
    set_df_property() {},
    trigger() {},
};

const document = {
    activeElement: null,
    head: { appendChild() {} },
    createElement() { return { remove() {} }; },
    getElementById() { return null; },
    documentElement: { getAttribute() { return "rtl"; } },
    addEventListener() {},
};

const window = {
    cur_frm: frm,
    addEventListener() {},
    AlmdinaPermissions: {
        canDocument(_frm, capability) {
            return capability !== "recalculate_plan" || allowRecalculate;
        },
    },
    AlmdinaUi: {
        button(options) {
            return `<button type="button" class="alm-button ${options.className || ""}"></button>`;
        },
    },
    AlmdinaPlanPreviewSession: {
        isBusy: () => false,
        preview(_frm, settings) {
            previewCalls.push({ ...settings });
            return Promise.resolve(true);
        },
        commit() { commits.push("commit"); },
        snapshot() { return { error: "" }; },
    },
    AlmdinaPlanWorkspaceAPI: { preview() { return Promise.resolve(true); } },
    AlmdinaTextBoardPlanUX: { preparePlanInputs: () => Promise.resolve(true) },
};

const frappe = {
    ui: { form: { on() {} } },
    utils: { escape_html: (value) => String(value) },
    msgprint(message) { messages.push(String(message)); },
    show_alert() {},
};

const context = vm.createContext({
    window, document, frappe, $, __: String, console,
    Promise, Set, Map, WeakMap,
});
vm.runInContext(source("core/door_cutting_order_workspace_store.js"), context, { filename: "store.js" });
vm.runInContext(source("cutting_plan/door_cutting_order_plan_controls_ux.js"), context, { filename: "controls.js" });

const store = window.AlmdinaWorkspaceStore.create("plan");
store.beginLoad("Door Cutting Order::DCO-1");
store.resolveLoad("Door Cutting Order::DCO-1", store.snapshot().requestId, {
    order_name: "DCO-1",
    approved_plan: "",
    machine_type_catalog: [{ id: "panel_saw", label: "Panel Saw", available: true }],
    plans: { system_draft: { name: "CP-1", status: "Draft" } },
});
window.AlmdinaPlanWorkspaceState = {
    storeFor: () => store,
    snapshot: () => store.snapshot(),
};
vm.runInContext(source("cutting_plan/door_cutting_order_plan_edit_session_ux.js"), context, { filename: "edit.js" });

async function main() {
store.beginEdit({
    kerf_mm: 3,
    trim_margin_mm: 0,
    cutting_machine_type: "panel_saw",
    optimization_time_limit_sec: 20,
    deduct_edge_thickness: 0,
});
window.AlmdinaPlanEditSessionUX.schedule(frm);
const editor = host.children.find((child) => child.className.includes("dco-plan-settings-editor"));
const kerf = editor.children.find((child) => child.attrs["data-almdina-plan-setting"] === "kerf_mm");
assert.ok(editor);
assert.ok(kerf);
kerf.value = "3.5";
document.activeElement = kerf;
kerf.listeners["input.almdinaPlanEdit change.almdinaPlanEdit"].callback.call(kerf);
window.AlmdinaPlanEditSessionUX.schedule(frm);
window.AlmdinaPlanEditSessionUX.schedule(frm);

const editorAfter = host.children.find((child) => child.className.includes("dco-plan-settings-editor"));
const kerfAfter = editorAfter.children.find((child) => child.attrs["data-almdina-plan-setting"] === "kerf_mm");
assert.equal(editorAfter, editor);
assert.equal(kerfAfter, kerf);
assert.equal(kerf.value, "3.5");
assert.equal(document.activeElement, kerf);
assert.equal(host.prepends, 1);
assert.equal(store.snapshot().draft.kerf_mm, 3.5);
assert.equal(store.snapshot().draft.deduct_edge_thickness, 0);
assert.equal(source("cutting_plan/door_cutting_order_plan_controls_ux.js").includes("new MutationObserver"), false);

const buttons = () => host.children.flatMap((child) => {
    const found = [];
    const visit = (node) => {
        if (node.className.split(/\s+/).includes("dco-recalculate-plan")) found.push(node);
        node.children.forEach(visit);
    };
    visit(child);
    return found;
});
assert.equal(buttons().length, 1);

function click(node) {
    if (!node || node.disabled) return 0;
    let fired = 0;
    let current = node;
    while (current) {
        for (const [event, listener] of Object.entries(current.listeners)) {
            if (!event.startsWith("click") || typeof listener.callback !== "function") continue;
            if (listener.match && !node.matches(listener.match)) continue;
            fired += 1;
            listener.callback({ preventDefault() {}, stopPropagation() {} });
        }
        current = current.parent;
    }
    return fired;
}

assert.equal(click(buttons()[0]), 1);
click(buttons()[0]);
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(previewCalls.length, 1);
assert.equal(previewCalls[0].deduct_edge_thickness, 0);
assert.equal(previewCalls[0].kerf_mm, 3.5);
assert.equal(commits.length, 0);

store.patchDraft({ deduct_edge_thickness: 1, kerf_mm: 4 });
window.AlmdinaPlanEditSessionUX.schedule(frm);
assert.equal(host.children.find((child) => child.className.includes("dco-plan-settings-editor")), editor);
previewCalls.length = 0;
click(buttons()[0]);
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(previewCalls.length, 1);
assert.equal(previewCalls[0].deduct_edge_thickness, 1);
assert.equal(previewCalls[0].kerf_mm, 4);

allowRecalculate = false;
window.AlmdinaPlanControlsUX.syncRecalculateButton(frm);
assert.equal(buttons()[0].disabled, true);
previewCalls.length = 0;
click(buttons()[0]);
await window.AlmdinaPlanControlsUX.runRecalculation(frm);
assert.equal(previewCalls.length, 0);
assert.equal(store.snapshot().data.approved_plan, "");

const recovery = vm.createContext({
    window: { addEventListener() {}, AlmdinaDcoRecovery: { Projection: { HEADER_FIELDS: [], PIECE_FIELDS: [], DIRTY_SCOPES: ["PLAN"] } } },
    document: { addEventListener() {} },
    frappe: { ui: { form: { on() {} } } },
    __: String,
    console,
});
vm.runInContext(source("recovery/presentation/door_cutting_order_local_checkpoint.js"), recovery, { filename: "checkpoint.js" });
const paint = recovery.window.AlmdinaDcoRecovery.LocalCheckpoint.shouldPaintRecoveryStatus;
assert.equal(paint("LOCAL_SAVED", { state: "DIRTY", dirty_scope: "PLAN" }), false);
assert.equal(paint("LOCAL_SAVED", { state: "LOCAL_SAVING", dirty_scope: "PLAN" }), false);
assert.equal(paint("LOCAL_SAVED", { state: "LOCAL_SAVED", dirty_scope: "PLAN" }), true);
assert.equal(paint("LOCAL_SAVED", { state: "ERROR", dirty_scope: "PLAN" }), true);
assert.equal(paint("READY_CLEAN", { state: "DIRTY", dirty_scope: "PLAN" }), true);
assert.equal(paint("LOCAL_SAVED", { state: "DIRTY", dirty_scope: "DCO" }), true);

console.log("plan edit session stability passed");
}

main();
