"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const editSource = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js"),
    "utf8",
);
const summarySource = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_settings_summary_ux.js"),
    "utf8",
);
const previewSource = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_edit_ux.js"),
    "utf8",
);
const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");

assert.ok(catalog.includes("Tool diameters,قياسات الريش"));
const diameterBlock = previewSource.slice(
    previewSource.indexOf("const DIAMETER_FIELDS"),
    previewSource.indexOf("const DIAMETER_FIELDS") + 280,
);
assert.match(diameterBlock, /liner_tool_diameter_mm/);
assert.match(diameterBlock, /handle_recess_tool_diameter_mm/);
assert.match(diameterBlock, /rear_groove_tool_diameter_mm/);
assert.doesNotMatch(diameterBlock, /kerf_mm/);

function element(tag) {
    const children = [];
    const attributes = {};
    const node = {
        nodeType: 1,
        tagName: String(tag || "div").toUpperCase(),
        children,
        parentElement: null,
        className: "",
        innerHTML: "",
        setAttribute(name, value) { attributes[name] = String(value); },
        getAttribute(name) { return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null; },
        appendChild(child) {
            child.parentElement = node;
            child.parentNode = node;
            children.push(child);
            return child;
        },
        insertBefore(child) { return node.appendChild(child); },
        querySelector(selector) {
            const match = String(selector).match(/\[([\w-]+)="([^"]+)"\]/);
            const visit = (current) => {
                if (match && current.getAttribute && current.getAttribute(match[1]) === match[2]) return current;
                for (const child of current.children || []) {
                    const found = visit(child);
                    if (found) return found;
                }
                return null;
            };
            return visit(node);
        },
    };
    node.parentNode = null;
    return node;
}

function chain() {
    const api = {
        length: 0,
        find() { return chain(); },
        children() { return chain(); },
        first() { return chain(); },
        remove() { return api; },
        off() { return api; },
        on() { return api; },
        each() { return api; },
        attr() { return undefined; },
        prop() { return api; },
        toggleClass() { return api; },
        append() { return api; },
    };
    return api;
}

function load(layers) {
    const document = {
        documentElement: element("html"),
        head: element("head"),
        body: element("body"),
        getElementById() { return null; },
        createElement: element,
    };
    const captured = [];
    const wrapper = {
        length: 1,
        find() { return chain(); },
        children() { return chain(); },
        prepend(html) { captured.push(String(html)); },
    };
    const window = {
        document,
        addEventListener() {},
        requestAnimationFrame(callback) { callback(); return 0; },
        AlmdinaLocale: { translate(message) { return message; }, direction() { return "rtl"; } },
        AlmdinaPermissions: { canDocument() { return true; } },
        AlmdinaMachiningOverlay: { layersInPlan() { return layers; } },
    };
    const frappe = {
        ui: { form: { on() {} } },
        utils: { escape_html(value) { return String(value ?? ""); } },
        msgprint() {},
    };
    const context = vm.createContext({
        window, document, frappe,
        __: (message) => message,
        $: () => chain(),
        Object, Boolean, String, Number, Array, Map, Promise, Math, Date, Set, console,
    });
    vm.runInContext(editSource, context);
    vm.runInContext(summarySource, context);
    return { window, document, captured, wrapper };
}

function splitGroups(html) {
    const planAt = html.indexOf('data-settings-group="plan"');
    const toolsAt = html.indexOf('data-settings-group="tools"');
    assert.ok(planAt >= 0 && toolsAt > planAt);
    return { plan: html.slice(planAt, toolsAt), tools: html.slice(toolsAt) };
}

const settings = {
    kerf_mm: 3.2,
    liner_tool_diameter_mm: 8,
    handle_recess_tool_diameter_mm: 10,
    rear_groove_tool_diameter_mm: 6,
    trim_margin_mm: 5,
    cutting_machine_type: "Panel Saw",
    optimization_time_limit_sec: 10,
    deduct_edge_thickness: 0,
};

function renderSummary(env) {
    const anchor = element("div");
    const form = element("div");
    form.appendChild(anchor);
    env.window.AlmdinaPlanWorkspaceState = {
        snapshot() { return { status: "ready", editing: false, data: { approved_plan: "" } }; },
        displayedPlan() { return { settings, layers: {} }; },
        planForTab() { return { settings }; },
        storeFor() { return { snapshot() { return { status: "ready", editing: false, data: { approved_plan: "" } }; } }; },
    };
    env.window.AlmdinaPlanWorkspacePresenterAdapter = { activeSettings() { return settings; } };
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-1", status: "Draft", docstatus: 0 },
        wrapper: form,
        fields_dict: { plan_actions_section: { wrapper: anchor } },
    };
    assert.equal(env.window.AlmdinaPlanSettingsSummaryUX.render(frm), true);
    return form.querySelector('[data-almdina-plan-settings-summary-owner="stable"]').innerHTML;
}

const hidden = load({ readable: true });
const hiddenGroups = splitGroups(renderSummary(hidden));
assert.match(hiddenGroups.plan, /trim_margin_mm/);
assert.match(hiddenGroups.plan, /deduct_edge_thickness/);
assert.doesNotMatch(hiddenGroups.plan, /kerf_mm/);
assert.match(hiddenGroups.tools, /data-fieldname="kerf_mm"/);
assert.doesNotMatch(hiddenGroups.tools, /liner_tool_diameter_mm/);
assert.doesNotMatch(hiddenGroups.tools, /handle_recess_tool_diameter_mm/);
assert.doesNotMatch(hiddenGroups.tools, /rear_groove_tool_diameter_mm/);

const visible = load({
    readable: true,
    liner: true,
    recessed_handle_cutout: true,
    back_groove: true,
});
const view = splitGroups(renderSummary(visible));
assert.match(view.tools, /kerf_mm/);
assert.match(view.tools, /liner_tool_diameter_mm/);
assert.match(view.tools, /handle_recess_tool_diameter_mm/);
assert.match(view.tools, /rear_groove_tool_diameter_mm/);
assert.match(view.tools, /data-tool-diameter="1"/);
assert.doesNotMatch(view.plan, /kerf_mm|liner_tool_diameter_mm|handle_recess_tool_diameter_mm|rear_groove_tool_diameter_mm/);
assert.match(view.plan, /trim_margin_mm[\s\S]*cutting_machine_type[\s\S]*optimization_time_limit_sec[\s\S]*deduct_edge_thickness/);

const editor = visible.window.AlmdinaPlanEditSessionUX;
const grouped = editor.groupPlanSettingSpecs(editor.planSettingSpecs({}, settings));
assert.equal(grouped.plan.map((spec) => spec.fieldname).join(","), [
    "trim_margin_mm",
    "cutting_machine_type",
    "optimization_time_limit_sec",
    "deduct_edge_thickness",
].join(","));
assert.equal(grouped.tools.map((spec) => spec.fieldname).join(","), [
    "kerf_mm",
    "liner_tool_diameter_mm",
    "handle_recess_tool_diameter_mm",
    "rear_groove_tool_diameter_mm",
].join(","));

const editEnv = load({
    readable: true,
    liner: true,
    recessed_handle_cutout: true,
    back_groove: true,
});
const draft = { ...settings };
const store = {
    snapshot() {
        return { status: "ready", editing: true, dirty: false, draft, data: { approved_plan: "" } };
    },
    beginEdit() {},
};
editEnv.window.cur_frm = null;
editEnv.window.AlmdinaPlanWorkspaceState = {
    snapshot() { return store.snapshot(); },
    displayedPlan() { return { settings }; },
    storeFor() { return store; },
};
editEnv.window.AlmdinaPlanWorkspacePresenterAdapter = { activeSettings() { return settings; } };
const editForm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-1", status: "Draft", docstatus: 0, revision_state: "Current" },
    is_dirty() { return false; },
    is_new() { return false; },
    trigger() {},
    fields_dict: { plan_control_actions: { $wrapper: editEnv.wrapper } },
};
editEnv.window.cur_frm = editForm;
editEnv.window.AlmdinaPlanEditSessionUX.startEditing(editForm).then((started) => {
    assert.equal(started, true);
    const edit = splitGroups(editEnv.captured.at(-1));
    assert.match(edit.plan, /trim_margin_mm/);
    assert.match(edit.plan, /deduct_edge_thickness/);
    assert.doesNotMatch(edit.plan, /data-fieldname="kerf_mm"/);
    assert.match(edit.tools, /data-fieldname="kerf_mm"/);
    assert.match(edit.tools, /liner_tool_diameter_mm/);
    assert.match(edit.tools, /handle_recess_tool_diameter_mm/);
    assert.match(edit.tools, /rear_groove_tool_diameter_mm/);
    assert.match(edit.tools, /data-tool-diameter="1"/);
    assert.match(editSource, /flex-direction:\s*column/);
    assert.match(summarySource, /flex-direction:\s*column/);
    console.log("plan tool row layout ok");
}).catch((error) => {
    console.error(error);
    process.exit(1);
});
