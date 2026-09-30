"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

function jqueryish(options = {}) {
    const state = {
        html: String(options.html || ""),
        readHtml: options.readHtml,
        writeHtml: options.writeHtml,
    };
    const getHtml = () => (state.readHtml ? state.readHtml() : state.html);
    const setHtml = (value) => {
        if (state.writeHtml) state.writeHtml(value);
        else state.html = String(value);
    };
    const api = {
        length: options.length === undefined ? 1 : options.length,
        jquery: true,
        attributes: {},
        attr(name, value) {
            if (value === undefined) return this.attributes[name];
            this.attributes[name] = value;
            return this;
        },
        html(value) {
            if (value !== undefined) {
                setHtml(value);
                return this;
            }
            return getHtml();
        },
        empty() {
            setHtml("");
            return this;
        },
        find(selector) {
            const source = getHtml();
            const raw = String(selector || "");
            const token = raw
                .replace(/^\./, "")
                .replace(/\[data-almdina-context-tools\]/g, "data-almdina-context-tools")
                .replace(/\[|\]|"|=/g, "");
            const hit = Boolean(api.length) && (
                source.includes(token)
                || source.includes(raw.replace(/^\./, ""))
            );
            return jqueryish({
                length: hit ? 1 : 0,
                readHtml: getHtml,
                writeHtml: setHtml,
            });
        },
        first() { return this; },
        children() { return { length: getHtml() ? 1 : 0 }; },
        on() { return this; },
        off() { return this; },
        toggle() { return this; },
        show() { return this; },
        hide() { return this; },
        get() { return { setAttribute() {}, removeAttribute() {} }; },
        0: { setAttribute() {}, removeAttribute() {} },
    };
    return api;
}

async function run() {
    let planHtml = `
        <div class="dco-plan-tabs"></div>
        <div class="dco-plan-context-actions-host"></div>
        <div class="dco-plan-tab-content"><geometry id="canonical"></geometry></div>
    `;
    let hostInner = "";
    const planWrapper = jqueryish({
        readHtml: () => planHtml,
        writeHtml: (value) => { planHtml = String(value); },
    });
    const originalFind = planWrapper.find.bind(planWrapper);
    planWrapper.find = (selector) => {
        const raw = String(selector || "");
        if (raw.includes("dco-plan-context-actions-host")) {
            return jqueryish({
                length: planHtml.includes("dco-plan-context-actions-host") ? 1 : 0,
                readHtml: () => hostInner,
                writeHtml: (value) => { hostInner = String(value); },
            });
        }
        return originalFind(selector);
    };

    const payload = {
        order_name: "DCO-1",
        approved_plan: "",
        plans: {
            system_draft: {
                name: "PLAN-1",
                source_type: "System",
                snapshot_json: { sheets: [{ id: "canonical" }] },
                settings: {
                    packing_mode: "Auto Pro",
                    cutting_machine_type: "Panel Saw",
                    kerf_mm: 4,
                    trim_margin_mm: 5,
                    optimization_time_limit_sec: 20,
                },
                validation: { status: "Valid", needs_recalculation: false },
                totals: { required_boards: 2 },
                status: "Draft",
            },
            uploaded_draft: null,
            approved: null,
        },
        capabilities: {
            print: true,
            export_dxf: true,
            upload_dxf: true,
            replace_dxf: true,
            approve: true,
            view_system: true,
            view_uploaded: true,
            view_approved: true,
        },
    };

    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-1", doctype: "Door Cutting Order" },
        fields_dict: {
            cutting_plan_html: { $wrapper: planWrapper, df: {} },
            plan_control_actions: {
                $wrapper: jqueryish({ html: '<div class="dco-plan-actions-shell"></div>' }),
                df: {},
            },
        },
        layout: { current_tab: { df: { fieldname: "results_tab" } } },
        is_new() { return false; },
        trigger() {},
    };

    const listeners = {};
    const fakeWindow = {
        cur_frm: frm,
        addEventListener(name, handler) {
            listeners[name] = listeners[name] || [];
            listeners[name].push(handler);
        },
        dispatchEvent(event) {
            (listeners[event.type] || []).forEach((handler) => handler(event));
            return true;
        },
        AlmdinaDocumentContext: {
            formIdentity(form) { return `Door Cutting Order::${form.doc.name}`; },
        },
        AlmdinaPermissions: {
            canDocument() { return true; },
            can() { return true; },
        },
        AlmdinaPlanWorkspaceAPI: {
            load() { return Promise.resolve(payload); },
        },
        AlmdinaCuttingPlanRender: {
            build(_frm, plan) {
                return `<geometry id="${plan.sheets[0].id}"></geometry>`;
            },
        },
        AlmdinaUi: {
            button({ label, className, disabled }) {
                return `<button type="button" class="btn ${className || ""}"${disabled ? " disabled" : ""}>${label}</button>`;
            },
        },
        requestAnimationFrame(cb) { cb(); },
    };

    const fakeDocument = {
        getElementById() { return null; },
        createElement() {
            return { id: "", textContent: "", style: {} };
        },
        head: { appendChild() {} },
    };
    fakeWindow.document = fakeDocument;

    const context = vm.createContext({
        window: fakeWindow,
        document: fakeDocument,
        frappe: {
            ui: { form: { on() {} } },
            utils: { escape_html: String },
            msgprint() {},
        },
        __: String,
        console,
        Object,
        String,
        Number,
        Boolean,
        Promise,
        Set,
        Map,
        CustomEvent: class {
            constructor(type, init = {}) {
                this.type = type;
                this.detail = init.detail;
            }
        },
        structuredClone: (value) => JSON.parse(JSON.stringify(value)),
        $: (value) => {
            if (value && value.jquery) return value;
            return jqueryish({ html: typeof value === "string" ? value : "" });
        },
    });
    fakeWindow.window = fakeWindow;

    vm.runInContext(read("core/door_cutting_order_workspace_store.js"), context);
    vm.runInContext(read("core/door_cutting_order_workspace_keep_paint.js"), context);
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_workspace_state.js"), context);
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_context_actions_ux.js"), context);
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_tabs_ux.js"), context);
    vm.runInContext(read("cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js"), context);

    const keep = fakeWindow.AlmdinaWorkspaceKeepPaint;
    assert.equal(keep.shouldRetain({ status: "loading", data: { ok: 1 } }), true);
    assert.equal(keep.shouldRetain({ status: "idle", data: null }), false);
    assert.equal(keep.presentationData({ status: "loading", data: { ok: 1 } }).ok, 1);

    const workspace = fakeWindow.AlmdinaPlanWorkspaceState;
    await workspace.load(frm);
    assert.equal(workspace.snapshot(frm).status, "ready");

    fakeWindow.AlmdinaPlanTabsUX.renderDualTabs(frm);
    assert.match(planHtml, /geometry id="canonical"/);
    assert.match(hostInner, /dco-plan-context-bar/);

    const store = workspace.storeFor(frm);
    store.beginLoad(`Door Cutting Order::${frm.doc.name}`);
    assert.equal(workspace.snapshot(frm).status, "loading");
    assert.ok(workspace.snapshot(frm).data);

    fakeWindow.AlmdinaPlanTabsUX.renderDualTabs(frm);
    assert.match(planHtml, /geometry id="canonical"/);
    assert.match(hostInner, /dco-plan-context-bar/);
    assert.doesNotMatch(planHtml, /جاري تحميل خطة القص/);

    assert.equal(fakeWindow.AlmdinaPlanContextActionsUX.refresh(frm), true);
    assert.match(hostInner, /dco-plan-context-bar/);
    assert.match(hostInner, /dco-print-cutting-plan|dco-export-dxf|dco-upload-dxf-plan/);

    console.log("workspace keep-paint contract passed");
}

run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
