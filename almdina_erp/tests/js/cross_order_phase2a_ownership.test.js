"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");
function deferred() {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
}

function makeHarness() {
    const handlers = {};
    const listeners = new Map();
    const flights = { plan: [], cost: [], preview: [] };
    const calls = { plan: [], cost: [], preview: [] };
    const paints = { plan: 0, cost: 0 };
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order", name: "A", modified: "v-A",
            customer: "A Customer", board_description: "A White", board_length_cm: 244,
            status: "Draft", pieces: [{ name: "a8f23b6710", width_cm: 42, qty: 2 }],
        },
        fields_dict: {}, is_new() { return false; }, is_dirty() { return false; },
    };
    const window = {
        cur_frm: frm,
        addEventListener(name, callback) {
            if (!listeners.has(name)) listeners.set(name, []);
            listeners.get(name).push(callback);
        },
        dispatchEvent(event) {
            (listeners.get(event.type) || []).forEach(callback => callback(event));
        },
        clearTimeout() {}, setTimeout() { return 1; },
        requestAnimationFrame(callback) { callback(); return 1; },
        AlmdinaPermissions: { canDocument() { return true; } },
        AlmdinaWorkspaceFieldEditor: { project() {} },
        AlmdinaPlanTabsUX: {
            shouldShowPlanTabs() { return true; },
            renderDualTabs() { paints.plan += 1; return true; },
            printActivePlan() { return true; },
            afterRender() { return true; },
        },
        AlmdinaOrderCostUX: {
            render() { paints.cost += 1; return true; },
            refreshInvoiceSection() { return true; },
            invoiceLines() { return []; }, invoiceTotal() { return 0; }, quoteTotal() { return 0; },
        },
    };
    for (const kind of ["plan", "cost"]) {
        window[kind === "plan" ? "AlmdinaPlanWorkspaceAPI" : "AlmdinaCostWorkspaceAPI"] = {
            load(name) {
                calls[kind].push(name);
                const flight = deferred();
                flights[kind].push(flight);
                return flight.promise;
            },
            preview(name) {
                calls.preview.push(name);
                const flight = deferred();
                flights.preview.push(flight);
                return flight.promise;
            },
        };
    }
    const frappe = {
        model: { new_names: {} },
        ui: { form: { on(_doctype, hooks) { Object.assign(handlers, hooks); } } },
        utils: { escape_html: String }, msgprint() {},
    };
    const context = vm.createContext({
        window, frappe, console, structuredClone, Promise, Set, Map,
        Object, Array, String, Number, Boolean, Date, Error, JSON,
        CustomEvent: class CustomEvent {
            constructor(type, init) { this.type = type; this.detail = init.detail; }
        },
        __: value => value,
    });
    function load(file) {
        vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), context, { filename: file });
    }
    load("core/door_cutting_order_document_context.js");
    load("core/door_cutting_order_workspace_store.js");
    load("core/door_cutting_order_workspace_keep_paint.js");
    load("cutting_plan/door_cutting_order_plan_workspace_state.js");
    load("costing/door_cutting_order_cost_workspace_state.js");
    load("cutting_plan/door_cutting_order_plan_preview_session.js");
    load("cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js");
    load("costing/door_cutting_order_cost_workspace_presenter_adapter.js");
    handlers.before_load(frm);
    const plan = window.AlmdinaPlanWorkspaceState;
    const cost = window.AlmdinaCostWorkspaceState;
    function navigate(name) {
        frm.doc = {
            doctype: "Door Cutting Order", name, modified: `v-${name}`,
            customer: `${name} Customer`, board_description: `${name} Black`,
            board_length_cm: 280, status: "At Drawing",
            pieces: [{ name: "b91d4c7e20", width_cm: 57, qty: 3 }],
        };
        handlers.before_load(frm);
    }
    return { frm, window, handlers, flights, calls, paints, plan, cost, navigate };
}

function planPayload(name) {
    return { order_name: name, plans: {
        system_draft: { name: `PLAN-${name}`, revision: 1,
            snapshot_json: JSON.stringify({ sheets: [{ sheet_no: name }] }) },
    } };
}
function costPayload(name, pieceName) {
    return { order_name: name, order_modified: `v-${name}`,
        order: { customer: "Stale Customer", board_description: "Stale White", board_length_cm: 200,
            status: "Rejected", board_rate_usd: 12 },
        pieces: [{ name: pieceName, width_cm: 22, qty: 9,
            special_shape_price_status: "Approved", special_shape_final_unit_price_usd: 18 }],
    };
}

test("A Plan, Cost, preview and global events lose ownership synchronously at B", async () => {
    const h = makeHarness();
    const tokenA = h.window.AlmdinaDocumentContext.capture(h.frm);
    const planA = h.plan.load(h.frm);
    const costA = h.cost.load(h.frm);
    const previewA = h.window.AlmdinaPlanPreviewSession.preview(h.frm, {
        packing_mode: "auto", cutting_machine_type: "saw", kerf_mm: 3,
        trim_margin_mm: 5, optimization_time_limit_sec: 30,
    });
    h.navigate("B");
    assert.equal(h.window.AlmdinaDocumentContext.isSameDocument(h.frm, tokenA), false);
    assert.equal(h.plan.snapshot(h.frm).status, "idle");
    assert.equal(h.cost.snapshot(h.frm).status, "idle");
    assert.equal(h.window.AlmdinaPlanPreviewSession.snapshot(h.frm).status, "idle");
    const before = { ...h.paints };
    h.window.dispatchEvent({ type: "almdina:plan-workspace-updated", detail: { identity: tokenA.identity } });
    h.window.dispatchEvent({ type: "almdina:cost-workspace-updated", detail: { identity: tokenA.identity } });
    assert.deepEqual(h.paints, before, "A events may not repaint B");

    const planB = h.plan.load(h.frm);
    const costB = h.cost.load(h.frm);
    assert.deepEqual(h.calls.plan, ["A", "B"]);
    assert.deepEqual(h.calls.cost, ["A", "B"]);
    h.flights.plan[1].resolve(planPayload("B"));
    h.flights.cost[1].resolve(costPayload("B", "b91d4c7e20"));
    await Promise.all([planB, costB]);
    h.flights.plan[0].resolve(planPayload("A"));
    h.flights.cost[0].resolve(costPayload("A", "a8f23b6710"));
    h.flights.preview[0].resolve({ preview_id: "A-PREVIEW", plan: { sheets: [] } });
    await Promise.all([planA, costA, previewA]);
    assert.equal(h.plan.snapshot(h.frm).data.order_name, "B");
    assert.equal(h.cost.snapshot(h.frm).data.order_name, "B");
    assert.equal(h.window.AlmdinaPlanPreviewSession.snapshot(h.frm).status, "idle");
    assert.equal(h.frm.doc.customer, "B Customer");
    assert.equal(h.frm.doc.board_description, "B Black");
    assert.equal(h.frm.doc.board_length_cm, 280);
    assert.equal(h.frm.doc.status, "At Drawing");
    assert.equal(h.frm.doc.pieces[0].width_cm, 57);
    assert.equal(h.frm.doc.pieces[0].qty, 3);
});

test("Cost read may reconcile financial fields only, never order inputs or piece geometry", async () => {
    const h = makeHarness();
    const loading = h.cost.load(h.frm);
    h.flights.cost[0].resolve(costPayload("A", "a8f23b6710"));
    await loading;
    assert.equal(h.window.AlmdinaCostWorkspacePresenterAdapter.project(h.frm), true);
    assert.equal(h.frm.doc.customer, "A Customer");
    assert.equal(h.frm.doc.board_description, "A White");
    assert.equal(h.frm.doc.board_length_cm, 244);
    assert.equal(h.frm.doc.pieces[0].width_cm, 42);
    assert.equal(h.frm.doc.pieces[0].qty, 2);
    assert.equal(h.frm.doc.pieces[0].special_shape_price_status, "Approved");

    h.navigate("B");
    // Even an injected same child name cannot lend A's cost read ownership of B.
    h.frm.doc.pieces[0].name = "a8f23b6710";
    const store = h.cost.storeFor(h.frm);
    const idA = "Door Cutting Order::A";
    store.reset(idA);
    store.resolveLoad(idA, store.beginLoad(idA), costPayload("A", "a8f23b6710"));
    assert.equal(h.window.AlmdinaCostWorkspacePresenterAdapter.project(h.frm), false);
    assert.equal(h.frm.doc.pieces[0].width_cm, 57);
    assert.equal(h.frm.doc.pieces[0].special_shape_price_status, undefined);
});

test("mismatched payload and permissions fail closed; same-document edits keep drafts", async () => {
    const h = makeHarness();
    const a = h.plan.load(h.frm);
    h.flights.plan[0].resolve(planPayload("B"));
    await a;
    assert.equal(h.plan.planForTab(h.frm, "System"), null);
    assert.equal(h.window.AlmdinaPlanWorkspacePresenterAdapter.ready(h.frm), false);
    const c = h.cost.load(h.frm);
    h.flights.cost[0].resolve(costPayload("B", "b91d4c7e20"));
    await c;
    assert.equal(h.window.AlmdinaCostWorkspacePresenterAdapter.project(h.frm), false);
    assert.equal(h.frm.doc.board_description, "A White");

    const p = h.plan.load(h.frm, { force: true });
    h.flights.plan[1].resolve(planPayload("A"));
    await p;
    const q = h.cost.load(h.frm, { force: true });
    h.flights.cost[1].resolve(costPayload("A", "a8f23b6710"));
    await q;
    h.plan.storeFor(h.frm).beginEdit({ kerf_mm: 3 });
    h.plan.storeFor(h.frm).patchDraft({ kerf_mm: 4 });
    h.cost.storeFor(h.frm).beginEdit({ board_rate_usd: 12 });
    h.cost.storeFor(h.frm).patchDraft({ board_rate_usd: 13 });
    await Promise.all([h.plan.load(h.frm, { force: true }), h.cost.load(h.frm, { force: true })]);
    assert.equal(h.plan.snapshot(h.frm).draft.kerf_mm, 4);
    assert.equal(h.cost.snapshot(h.frm).draft.board_rate_usd, 13);
    h.navigate("B");
    assert.equal(h.plan.snapshot(h.frm).editing, false);
    assert.equal(h.cost.snapshot(h.frm).editing, false);
    h.window.AlmdinaPermissions.canDocument = () => false;
    await Promise.all([h.plan.load(h.frm), h.cost.load(h.frm)]);
    assert.equal(h.plan.snapshot(h.frm).status, "idle");
    assert.equal(h.cost.snapshot(h.frm).status, "idle");
});

test("a second visit to A has a new generation and rejects the first visit's replies", async () => {
    const h = makeHarness();
    const first = h.window.AlmdinaDocumentContext.capture(h.frm);
    const oldPlan = h.plan.load(h.frm);
    const oldCost = h.cost.load(h.frm);
    h.navigate("B");
    h.navigate("A");
    const second = h.window.AlmdinaDocumentContext.capture(h.frm);
    assert.equal(second.identity, first.identity);
    assert.notEqual(second.generation, first.generation);
    const newPlan = h.plan.load(h.frm);
    const newCost = h.cost.load(h.frm);
    assert.deepEqual(h.calls.plan, ["A", "A"]);
    assert.deepEqual(h.calls.cost, ["A", "A"]);
    h.flights.plan[1].resolve(planPayload("A"));
    h.flights.cost[1].resolve(costPayload("A", "a8f23b6710"));
    await Promise.all([newPlan, newCost]);
    const planRequest = h.plan.snapshot(h.frm).requestId;
    const costRequest = h.cost.snapshot(h.frm).requestId;
    h.flights.plan[0].resolve(planPayload("A"));
    h.flights.cost[0].resolve(costPayload("A", "a8f23b6710"));
    await Promise.all([oldPlan, oldCost]);
    assert.equal(h.plan.snapshot(h.frm).requestId, planRequest);
    assert.equal(h.cost.snapshot(h.frm).requestId, costRequest);
    assert.equal(h.plan.snapshot(h.frm).status, "ready");
    assert.equal(h.cost.snapshot(h.frm).status, "ready");
});
