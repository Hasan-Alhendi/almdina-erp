"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(file) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js/door_cutting_order", file), "utf8");
}

class Control {
    constructor() {
        this.disabled = true;
        this.attributes = {};
        this.length = 1;
    }
    attr(name, value) {
        if (value === undefined) return this.attributes[name];
        this.attributes[name] = value;
        return this;
    }
    removeAttr(name) { delete this.attributes[name]; return this; }
    prop(name, value) {
        if (value === undefined) return this[name];
        this[name] = value;
        return this;
    }
    on() { return this; }
    off() { return this; }
    is() { return false; }
    addClass() { return this; }
    parent() { return { is: () => true }; }
}

class Group {
    constructor(items) { this.items = items; this.length = items.length; }
    each(callback) { this.items.forEach((item, index) => callback(index, item)); return this; }
    first() { return this.items[0] || this; }
    find() { return new Group([]); }
    on() { return this; }
    off() { return this; }
    remove() { return this; }
    toggleClass() { return this; }
}

function environment({ canCalculate, busy = false }) {
    const handlers = [];
    const recalculate = new Control();
    const host = {
        length: 1,
        editor: false,
        children(selector) {
            if (selector !== ".dco-plan-settings-editor" || !this.editor) return new Group([]);
            return new Group([{
                length: 1,
                find: () => new Group([]),
                toggleClass() {},
            }]);
        },
        append() { return this; },
        prepend() { this.editor = true; return this; },
        find(selector) {
            if (String(selector).includes(".dco-recalculate-plan")) return new Group([recalculate]);
            return new Group([]);
        },
    };
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-1",
            docstatus: 0,
            status: "Draft",
            revision_state: "Current",
        },
        __generation: 1,
        fields_dict: { plan_control_actions: { $wrapper: host } },
        is_new() { return false; },
        is_dirty() { return false; },
        trigger(event) { handlers.forEach(map => map[event] && map[event](this)); },
    };
    const window = {
        cur_frm: frm,
        AlmdinaDocumentContext: {
            formIdentity(form) { return `Door Cutting Order::${form.doc.name}`; },
            capture(form) { return { identity: this.formIdentity(form), generation: form.__generation }; },
            isSameDocument(form, token) { return this.formIdentity(form) === token.identity; },
            isCurrent(form, token) {
                return window.cur_frm === form
                    && this.isSameDocument(form, token)
                    && form.__generation === token.generation;
            },
        },
        addEventListener() {},
        dispatchEvent() {},
        requestAnimationFrame(callback) { callback(); },
        AlmdinaPermissions: { canDocument: () => true },
        AlmdinaPlanFieldAccessAdapter: { apply() {} },
        AlmdinaPlanWorkspacePresenterAdapter: {
            activeSettings: () => ({ deduct_edge_thickness: 0, kerf_mm: 3 }),
            project() {},
        },
        AlmdinaPlanControlsUX: {
            canCalculate,
            refresh(form) {
                const allowed = canCalculate(form);
                recalculate.prop("disabled", !allowed);
                recalculate.attr("aria-disabled", allowed ? "false" : "true");
                recalculate.attr("title", allowed ? "preview" : "blocked");
            },
        },
        AlmdinaPlanPreviewSession: { isBusy: () => busy, preview() { return Promise.resolve(true); } },
    };
    const frappe = {
        ui: { form: { on(_doctype, mapping) { handlers.push(mapping); } } },
        utils: { escape_html: String },
        msgprint() {},
        show_alert() {},
    };
    const document = {
        getElementById() { return null; },
        createElement() { return {}; },
        head: { appendChild() {} },
        body: { classList: { toggle() {} } },
    };
    const context = vm.createContext({
        window, document, frappe, $: item => item, __: String, console,
        CustomEvent: class {
            constructor(name, options) { this.name = name; this.detail = options && options.detail; }
        },
        structuredClone, Promise, Set, WeakMap, Map,
    });
    for (const file of [
        "core/door_cutting_order_workspace_store.js",
        "core/door_cutting_order_edit_session_coordinator.js",
        "cutting_plan/door_cutting_order_plan_edit_session_ux.js",
    ]) vm.runInContext(source(file), context, { filename: file });
    const store = window.AlmdinaWorkspaceStore.create("plan");
    const requestId = store.beginLoad("Door Cutting Order::DCO-1");
    store.resolveLoad("Door Cutting Order::DCO-1", requestId, {
        approved_plan: "",
        order_name: "DCO-1",
        plans: { system_draft: { name: "CP-1", status: "Draft", revision: 1 } },
    });
    window.AlmdinaPlanWorkspaceState = {
        storeFor: () => store,
        snapshot: () => store.snapshot(),
        load: () => Promise.resolve(store.snapshot()),
    };
    return { frm, recalculate, coordinator: window.AlmdinaDcoEditSessionCoordinator, session: window.AlmdinaPlanEditSessionUX };
}

function loadControls() {
    let permissions = { recalculate: true };
    let busy = false;
    const handlers = [];
    const window = {
        cur_frm: null,
        addEventListener() {},
        AlmdinaPermissions: {
            canDocument(_frm, capability) {
                return capability !== "recalculate_plan" || permissions.recalculate;
            },
        },
        AlmdinaPlanWorkspaceState: {
            snapshot(frm) { return frm.__planState; },
        },
        AlmdinaPlanPreviewSession: {
            isBusy: () => busy,
            preview() { return Promise.resolve(true); },
        },
        AlmdinaPlanWorkspaceAPI: { preview() { return Promise.resolve(true); } },
    };
    const document = {
        getElementById() { return null; },
        createElement() { return {}; },
        head: { appendChild() {} },
    };
    const frappe = { ui: { form: { on(_doctype, mapping) { handlers.push(mapping); } } } };
    const context = vm.createContext({
        window, document, frappe, $() { return { append() {}, length: 0 }; }, __: String, console,
        MutationObserver: class { observe() {} disconnect() {} },
        requestAnimationFrame(callback) { callback(); },
    });
    vm.runInContext(source("cutting_plan/door_cutting_order_plan_controls_ux.js"), context);
    const controls = context.window.AlmdinaPlanControlsUX;
    return {
        canCalculate: controls.canCalculate,
        reason: controls.recalculationDisabledReason,
        form(options) {
            permissions = { recalculate: options.recalculate !== false };
            busy = Boolean(options.busy);
            const planning = options.planning !== false;
            const frm = {
                doc: {
                    name: "DCO-1",
                    docstatus: 0,
                    status: options.status || "Draft",
                    revision_state: "Current",
                    current_production_stage: options.stage || "",
                    production_path: options.stage ? "Route" : "",
                },
                is_new() { return false; },
                __almdina_stage_context: {
                    actor_can_operate_current_stage: options.assignee !== false,
                    route_stages: [{
                        stage_type: "Drawing",
                        is_planning_stage: true,
                    }],
                },
                __almdina_stage_type: planning ? "Drawing" : "CNC",
                __planState: {
                    status: "ready",
                    editing: Boolean(options.editing),
                    data: {
                        order_name: "DCO-1",
                        approved_plan: options.approved || "",
                        plans: {
                            system_draft: options.systemDraft === null
                                ? null
                                : { name: "CP-1", status: "Draft" },
                        },
                    },
                },
            };
            return frm;
        },
    };
}

async function run() {
    const allowed = environment({ canCalculate: () => true });
    assert.equal(allowed.recalculate.disabled, true);
    assert.equal(await allowed.coordinator.start(allowed.frm, "plan"), true);
    assert.equal(allowed.coordinator.snapshot(allowed.frm).phase, "editing");
    assert.equal(allowed.recalculate.disabled, false);
    assert.equal(allowed.recalculate.attr("aria-disabled"), "false");

    const denied = environment({ canCalculate: () => false });
    assert.equal(await denied.coordinator.start(denied.frm, "plan"), true);
    assert.equal(denied.coordinator.snapshot(denied.frm).phase, "editing");
    assert.equal(denied.recalculate.disabled, true);
    assert.equal(denied.recalculate.attr("aria-disabled"), "true");

    const resumed = environment({ canCalculate: () => true });
    assert.equal(await resumed.coordinator.start(resumed.frm, "plan"), true);
    resumed.recalculate.prop("disabled", true);
    resumed.session.syncPhaseLocks(resumed.frm);
    assert.equal(resumed.recalculate.disabled, false);

    const controlsSource = source("cutting_plan/door_cutting_order_plan_controls_ux.js");
    assert.match(controlsSource, /firstPlan \|\| workspaceEditing\(frm\)/);
    assert.match(controlsSource, /previews\.isBusy\(frm\)/);
    assert.doesNotMatch(
        controlsSource.slice(controlsSource.indexOf("function canCalculate"), controlsSource.indexOf("function recalculationDisabledReason")),
        /dirty/,
    );

    const decisions = loadControls();
    const editable = decisions.form({ editing: true });
    assert.equal(decisions.canCalculate(editable), true);
    assert.equal(decisions.reason(editable), "");
    editable.__planState.editing = false;
    assert.equal(decisions.canCalculate(editable), false);
    assert.match(decisions.reason(editable), /Press “Edit”/);

    const first = decisions.form({ editing: false, systemDraft: null });
    assert.equal(decisions.canCalculate(first), true);

    const noPermission = decisions.form({ editing: true, recalculate: false });
    assert.equal(decisions.canCalculate(noPermission), false);
    assert.match(decisions.reason(noPermission), /Recalculate plan/);

    const busy = decisions.form({ editing: true, busy: true });
    assert.equal(decisions.canCalculate(busy), false);
    assert.match(decisions.reason(busy), /current preview or save/);

    const assignedLaterStage = decisions.form({
        editing: true,
        status: "At CNC",
        stage: "STAGE-1",
        planning: false,
        assignee: true,
    });
    assert.equal(decisions.canCalculate(assignedLaterStage), true);

    const unassigned = decisions.form({
        editing: true,
        status: "At CNC",
        stage: "STAGE-1",
        planning: false,
        assignee: false,
    });
    unassigned.__almdina_stage_context.active_stage_assigned_to = "other-user";
    assert.equal(decisions.canCalculate(unassigned), false);
    assert.match(decisions.reason(unassigned), /assigned to another user/);

    const approvedLater = decisions.form({
        editing: true,
        status: "At CNC",
        stage: "STAGE-1",
        planning: false,
        approved: "CP-APPROVED",
    });
    assert.equal(decisions.canCalculate(approvedLater), false);
    assert.match(decisions.reason(approvedLater), /approved plan cannot be recalculated/);
}

run().then(() => console.log("recalculate button after edit tests passed"))
    .catch((error) => {
        console.error(error);
        process.exitCode = 1;
    });
