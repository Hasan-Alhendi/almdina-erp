"use strict";

// Intentional RED baseline. Run with: node --test almdina_erp/tests/js/cross_order_p0_baseline.test.js
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const js = "../../public/js/door_cutting_order/";
function deferred() {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
}

function harness(kind, { pending = false } = {}) {
    const calls = [];
    const replies = [];
    const handlers = {};
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order", name: "A", modified: "v-A",
            board_description: "أبيض", pieces: [{ name: "PIECE-1", width_cm: 10 }],
        },
        fields_dict: {},
        is_new() { return false; },
        is_dirty() { return false; },
    };
    const window = {
        cur_frm: frm,
        dispatchEvent() {}, addEventListener() {},
        clearTimeout() {}, setTimeout() { return 1; },
        requestAnimationFrame(callback) { callback(); return 1; },
        AlmdinaPermissions: { canDocument() { return true; } },
        AlmdinaWorkspaceFieldEditor: { project() {} },
    };
    const apiName = kind === "plan" ? "AlmdinaPlanWorkspaceAPI" : "AlmdinaCostWorkspaceAPI";
    window[apiName] = {
        load(name) {
            calls.push(name);
            if (!pending) return Promise.resolve(payload(kind, name));
            const reply = deferred();
            replies.push(reply);
            return reply.promise;
        },
    };
    const frappe = {
        model: { new_names: {} },
        ui: { form: { on(_doctype, events) { Object.assign(handlers, events); } } },
        utils: { escape_html(value) { return String(value); } },
        msgprint() {},
    };
    const context = vm.createContext({
        window, frappe, console, structuredClone, Promise, Set, Map,
        Object, Array, String, Number, Boolean, Date, Error, JSON,
        CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init.detail; } },
        __: value => value,
    });
    function load(relative) {
        const file = path.resolve(__dirname, js, relative);
        vm.runInContext(fs.readFileSync(file, "utf8"), context, { filename: file });
    }
    load("core/door_cutting_order_document_context.js");
    load("core/door_cutting_order_workspace_store.js");
    load("core/door_cutting_order_workspace_keep_paint.js");
    load(kind === "plan"
        ? "cutting_plan/door_cutting_order_plan_workspace_state.js"
        : "costing/door_cutting_order_cost_workspace_state.js");
    const owner = kind === "plan" ? window.AlmdinaPlanWorkspaceState : window.AlmdinaCostWorkspaceState;
    const presenterPath = kind === "plan"
        ? "cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js"
        : "costing/door_cutting_order_cost_workspace_presenter_adapter.js";
    load(presenterPath);
    const presenter = kind === "plan"
        ? window.AlmdinaPlanWorkspacePresenterAdapter
        : window.AlmdinaCostWorkspacePresenterAdapter;
    handlers.before_load(frm);
    function navigate(name) {
        // Frappe reuses the same Form object. Exercise the real context hook.
        frm.doc = {
            doctype: "Door Cutting Order", name, modified: `v-${name}`,
            board_description: "أسود", pieces: [{ name: "PIECE-1", width_cm: 99 }],
        };
        handlers.before_load(frm);
    }
    return { frm, owner, presenter, window, frappe, handlers, calls, replies, navigate, load };
}

function payload(kind, name) {
    if (kind === "cost") return {
        order_name: name, order_modified: `v-${name}`,
        order: { board_description: name === "A" ? "أبيض" : "أسود" },
        pieces: [{ name: "PIECE-1", width_cm: name === "A" ? 10 : 99 }],
    };
    return {
        order_name: name,
        approved_plan: null,
        plans: { system_draft: {
            name: `PLAN-${name}`, snapshot_json: JSON.stringify({ sheets: [{ sheet_no: name }] }),
        } },
    };
}

for (const kind of ["plan", "cost"]) {
    test(`${kind}: A snapshot cannot be presented or projected on B after Frappe before_load`, async () => {
        const h = harness(kind);
        await h.owner.load(h.frm);
        h.navigate("B");
        assert.equal(h.presenter.canPresent(h.frm), false);
        assert.equal(h.presenter.project(h.frm), false);
        if (kind === "cost") {
            assert.equal(h.frm.doc.board_description, "أسود");
            assert.equal(h.frm.doc.pieces[0].width_cm, 99);
        } else {
            assert.equal(h.frm.doc.cutting_plan_json, undefined);
            assert.equal(h.owner.planForTab(h.frm, "System"), null);
        }
    });

    test(`${kind}: B starts its own GET while A is pending`, async () => {
        const h = harness(kind, { pending: true });
        const a = h.owner.load(h.frm);
        h.navigate("B");
        const b = h.owner.load(h.frm);
        assert.deepEqual(h.calls, ["A", "B"]);
        h.replies.forEach((reply, index) => reply.resolve(payload(kind, index ? "B" : "A")));
        await Promise.all([a, b]);
    });

    test(`${kind}: late A cannot clear a ready B`, async () => {
        const h = harness(kind, { pending: true });
        const a = h.owner.load(h.frm);
        h.navigate("B");
        // This explicitly exercises the route activation that must own B.
        h.owner.reset(h.frm);
        const b = h.owner.load(h.frm);
        assert.deepEqual(h.calls, ["A", "B"]);
        h.replies[1].resolve(payload(kind, "B"));
        await b;
        h.replies[0].resolve(payload(kind, "A"));
        await a;
        const state = h.owner.snapshot(h.frm);
        assert.equal(state.identity, "Door Cutting Order::B");
        assert.equal(state.status, "ready");
        assert.equal(state.data.order_name, "B");
    });
}

test("cost: stale A projection must not mutate B board or pieces", async () => {
    const h = harness("cost");
    await h.owner.load(h.frm);
    h.navigate("B");
    h.presenter.project(h.frm);
    assert.deepEqual({
        board: h.frm.doc.board_description,
        pieceWidth: h.frm.doc.pieces[0].width_cm,
    }, { board: "أسود", pieceWidth: 99 });
});

test("plan: stale A projection must not write B's cutting_plan_json", async () => {
    const h = harness("plan");
    await h.owner.load(h.frm);
    h.navigate("B");
    h.presenter.project(h.frm);
    assert.equal(h.frm.doc.cutting_plan_json, undefined);
});

test("cost: server payload identity must match current order before model projection", async () => {
    const h = harness("cost", { pending: true });
    const load = h.owner.load(h.frm);
    h.replies[0].resolve(payload("cost", "B"));
    await load;
    assert.equal(h.presenter.project(h.frm), false);
    assert.equal(h.frm.doc.board_description, "أبيض");
});

test("plan: mismatched server payload cannot become current plan", async () => {
    const h = harness("plan", { pending: true });
    const load = h.owner.load(h.frm);
    h.replies[0].resolve(payload("plan", "B"));
    await load;
    assert.equal(h.owner.planForTab(h.frm, "System"), null);
    assert.equal(h.presenter.ready(h.frm), false);
});

test("plan: print command must reject geometry owned by A while current form is B", async () => {
    const h = harness("plan");
    let printed = null;
    h.window.AlmdinaPlanTabsUX = {
        printActivePlan(frm) { printed = h.window.AlmdinaPlanWorkspaceState.planForTab(frm, "System"); return true; },
    };
    h.presenter.install();
    await h.owner.load(h.frm);
    h.navigate("B");
    assert.equal(h.window.AlmdinaPlanTabsUX.printActivePlan(h.frm), false);
    assert.equal(printed, null);
});

test("control: reload of same order retains an active Plan edit draft", async () => {
    const h = harness("plan");
    await h.owner.load(h.frm);
    const store = h.owner.storeFor(h.frm);
    assert.equal(store.beginEdit({ kerf_mm: 5 }), true);
    store.patchDraft({ kerf_mm: 6 });
    await h.owner.load(h.frm, { force: true });
    assert.equal(h.owner.snapshot(h.frm).editing, true);
    assert.equal(h.owner.snapshot(h.frm).draft.kerf_mm, 6);
});

test("control: separate Form instances have separate workspace stores", async () => {
    const one = harness("cost");
    await one.owner.load(one.frm);
    const otherFrm = {
        doctype: "Door Cutting Order", doc: { doctype: "Door Cutting Order", name: "B" },
        is_new() { return false; },
    };
    await one.owner.load(otherFrm);
    assert.equal(one.owner.snapshot(one.frm).data.order_name, "A");
    assert.equal(one.owner.snapshot(otherFrm).data.order_name, "B");
});

test("control: NEW first insert promotes Document Context without a new generation", () => {
    const h = harness("plan");
    h.navigate("new-door-cutting-order-1");
    h.frm.doc.__islocal = 1;
    h.frm.is_new = () => Boolean(h.frm.doc.__islocal);
    const first = h.window.AlmdinaDocumentContext.capture(h.frm);
    h.handlers.before_save(h.frm);
    h.frappe.model.new_names[h.frm.doc.name] = "26-99999";
    h.frm.doc.name = "26-99999";
    h.frm.doc.localname = "new-door-cutting-order-1";
    h.frm.doc.__islocal = 0;
    h.handlers.refresh(h.frm);
    h.handlers.after_save(h.frm);
    assert.equal(h.window.AlmdinaDocumentContext.capture(h.frm).generation, first.generation);
    assert.equal(h.window.AlmdinaDocumentContext.isSameDocument(h.frm, first), true);
});

test("board DOM: stale input from A cannot become B's next save payload", async () => {
    const h = harness("cost");
    let submitted;
    h.frm.fields_dict.board_description = { $input: { length: 1, val() { return "أبيض"; } } };
    h.frm.fields_dict.board_length_cm = { get_value() { return 244; } };
    h.frm.fields_dict.board_width_cm = { get_value() { return 122; } };
    h.frm.doc.board_length_cm = 244;
    h.frm.doc.board_width_cm = 122;
    h.frm.set_value = async values => Object.assign(h.frm.doc, values);
    h.load("order_entry/door_cutting_order_board_text_ux.js");
    h.navigate("B");
    h.frm.doc.board_length_cm = 244;
    h.frm.doc.board_width_cm = 122;
    // Captures what native Frappe Save would serialize after before_save.
    await h.window.AlmdinaBoardTextUX.syncInputs(h.frm);
    submitted = { name: h.frm.doc.name, board_description: h.frm.doc.board_description };
    assert.deepEqual(submitted, { name: "B", board_description: "أسود" });
});
