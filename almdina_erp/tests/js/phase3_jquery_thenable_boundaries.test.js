"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => {
        resolve = yes;
        reject = no;
    });
    return { promise, resolve, reject };
}

function frappeThenable(promise) {
    return {
        then(fulfilled, rejected) {
            return frappeThenable(promise.then(fulfilled, rejected));
        },
        catch(rejected) {
            return frappeThenable(promise.catch(rejected));
        },
        // Frappe v16 may return a jqXHR-like thenable without native finally.
    };
}

function environment(file) {
    const calls = [];
    const handlers = {};
    const events = [];
    const window = {
        cur_frm: null,
        addEventListener() {},
        dispatchEvent(event) { events.push(event.type); },
        clearTimeout() {},
        setTimeout() { return 1; },
    };
    const frappe = {
        almdina: {},
        provide() {},
        ui: {
            form: {
                on(name, callbacks) {
                    handlers[name] = callbacks;
                },
            },
        },
        call(options) {
            const call = { options, ...deferred() };
            calls.push(call);
            return frappeThenable(call.promise);
        },
    };
    window.frappe = frappe;
    const globals = vm.createContext({
        window, frappe, Promise, Set, Map, String, Object, Number, Boolean,
        console, document: { addEventListener() {} },
        CustomEvent: class CustomEvent {
            constructor(type) { this.type = type; }
        },
        __: value => value,
    });
    vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), globals, {
        filename: file,
    });
    return { window, frappe, calls, handlers, events };
}

function form(name, stage = "") {
    const button = {
        nodeType: 1, isConnected: true, textContent: "", dataset: {},
        classList: { add() {}, toggle() {} },
        setAttribute() {},
    };
    return {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order", name, current_production_stage: stage,
            status: stage ? "At Drawing" : "Draft",
        },
        fields_dict: {},
        is_new() { return this.doc.name.startsWith("new-"); },
        add_custom_button() { return button; },
        remove_custom_button() {},
    };
}

test("a saved order's Notes refresh accepts the Frappe thenable and ignores a late A reply at B", async () => {
    const { window, calls, handlers } = environment("notes/door_cutting_order_notes_ux.js");
    const frm = form("DCO-A");
    window.cur_frm = frm;

    handlers["Door Cutting Order"].refresh(frm);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].options.args.order_name, "DCO-A");

    frm.doc.name = "DCO-B";
    handlers["Door Cutting Order"].refresh(frm);
    assert.equal(calls.length, 2);
    assert.equal(calls[1].options.args.order_name, "DCO-B");

    calls[0].resolve({ message: {
        order: "DCO-A", counts: { order: 99 }, important_note_preview: "A only",
    } });
    calls[1].resolve({ message: {
        order: "DCO-B", counts: { order: 2 }, important_note_preview: "B only",
    } });
    await Promise.all([calls[0].promise, calls[1].promise]);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(frm._almdinaNotesCount, 2);
    assert.equal(frm.doc.important_note_preview, "B only");
    assert.equal(frm._almdinaNotesSummaryPromise, null);
});

test("active stage context accepts the Frappe thenable and keeps its document visit", async () => {
    const { window, calls, events } = environment("core/door_cutting_order_document_context.js");
    const frm = form("DCO-A", "DRAWING-A");
    window.cur_frm = frm;
    const owner = window.AlmdinaDocumentContext;
    owner.synchronize(frm);

    const pendingA = owner.ensureStageContext(frm);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].options.args.order_name, "DCO-A");

    frm.doc.name = "DCO-B";
    frm.doc.current_production_stage = "DRAWING-B";
    owner.synchronize(frm);
    const pendingB = owner.ensureStageContext(frm);
    assert.equal(calls.length, 2);
    assert.equal(calls[1].options.args.order_name, "DCO-B");

    calls[0].resolve({ message: {
        active_stage_type: "A", actor_is_current_assignee: true,
    } });
    assert.equal(await pendingA, false);
    assert.equal(frm.__almdina_stage_type, null);
    assert.equal(frm.__almdina_stage_context_ready, false);

    calls[1].resolve({ message: {
        active_stage_type: "Drawing", actor_is_current_assignee: true,
    } });
    assert.equal(await pendingB, true);
    assert.equal(frm.__almdina_stage_type, "Drawing");
    assert.equal(frm.__almdina_actor_is_current_assignee, true);
    assert.equal(frm.__almdina_actor_can_operate_current_stage, true);
    assert.equal(frm.__almdina_stage_context_ready, true);
    assert.equal(frm.__almdinaStageContextPromise, null);
    assert.equal(events.includes("almdina:stage-context-ready"), true);

    frm.doc.name = "new-DCO-1";
    owner.synchronize(frm);
    const beforeNew = calls.length;
    assert.equal(await owner.ensureStageContext(frm), false);
    assert.equal(calls.length, beforeNew);
});

test("stage operation context allows Administrator without changing assignee identity", async () => {
    const { window, calls } = environment("core/door_cutting_order_document_context.js");
    const frm = form("DCO-ADMIN", "DRAWING-ADMIN");
    window.cur_frm = frm;
    const owner = window.AlmdinaDocumentContext;
    owner.synchronize(frm);
    const pending = owner.ensureStageContext(frm);
    calls[0].resolve({ message: {
        active_stage_type: "Drawing",
        active_stage_assigned_to: "designer@example.com",
        actor_is_current_assignee: false,
        actor_can_operate_current_stage: true,
    } });
    assert.equal(await pending, true);
    assert.equal(frm.__almdina_actor_is_current_assignee, false);
    assert.equal(owner.isCurrentStageAssignee(frm), false);
    assert.equal(owner.canMutateCurrentStage(frm), true);
});

test("production revert targets accept the native Frappe thenable and release their request", async () => {
    const { window, calls } = environment("production/shop_floor_order_ux.js");
    window.AlmdinaPermissions = { canDocument: (_frm, capability) => capability === "revert_department" };
    const frm = form("DCO-REVERT", "DYNAMIC-STAGE");
    frm.doc.production_path = "DYNAMIC-ROUTE";
    window.cur_frm = frm;
    assert.doesNotThrow(() => window.AlmdinaShopFloorOrderUX.reconcileProductionActions(frm));
    assert.equal(calls.length, 1);
    assert.match(calls[0].options.method, /get_revert_targets$/);
    const pending = frm.__almdinaRevertTargetsPromise;
    calls[0].resolve({ message: [{ stage_type: "Earlier dynamic stage" }] });
    await pending;
    assert.equal(frm.__almdinaRevertTargets.length, 1);
    assert.equal(frm.__almdinaRevertTargetsPromise, null);
});
