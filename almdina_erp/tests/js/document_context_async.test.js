"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(filename) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", filename), "utf8");
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

const handlers = {};
const calls = [];
const databaseCalls = [];
const setValues = [];

const fakeWindow = {
    cur_frm: null,
    clearTimeout() {},
};
const fakeDocument = {
    documentElement: { lang: "en" },
};
const fakeFrappe = {
    boot: { lang: "en" },
    user_roles: [],
    utils: {
        escape_html(value) {
            return String(value);
        },
    },
    ui: {
        form: {
            on(doctype, events) {
                handlers[doctype] = handlers[doctype] || {};
                Object.entries(events).forEach(([event, handler]) => {
                    handlers[doctype][event] = handlers[doctype][event] || [];
                    handlers[doctype][event].push(handler);
                });
            },
        },
    },
    call() {
        const pending = deferred();
        calls.push(pending);
        return pending.promise;
    },
    db: {
        get_value() {
            const pending = deferred();
            databaseCalls.push(pending);
            return pending.promise;
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    document: fakeDocument,
    frappe: fakeFrappe,
    console,
    Promise,
    Object,
    Set,
    String,
    Number,
    __: value => value,
});
vm.runInContext(source("door_cutting_order_document_context.js"), context);
vm.runInContext(source("door_cutting_order_defaults.js"), context);
vm.runInContext(source("door_cutting_order_drawing_plan_ux.js"), context);

function trigger(event, frm) {
    const eventHandlers = handlers["Door Cutting Order"][event] || [];
    eventHandlers.forEach(handler => handler(frm));
}

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
}

(async () => {
    const frm = {
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-2026-00001",
            board_length_cm: 244,
            board_width_cm: 122,
        },
        doctype: "Door Cutting Order",
        fields_dict: {},
        is_new() {
            return true;
        },
        set_df_property() {},
        set_value(...args) {
            setValues.push(args);
            return Promise.resolve();
        },
    };
    fakeWindow.cur_frm = frm;

    // The defaults response belongs to the first order and must not update the
    // same Form instance after navigation changes its document identity.
    trigger("onload", frm);
    assert.equal(calls.length, 1);
    frm.doc.name = "DCO-2026-00002";
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    calls[0].resolve({ message: { kerf_mm: 9 } });
    await flushPromises();
    assert.equal(setValues.length, 0);

    // The same rule applies to edge-color defaults.
    frm.doc.default_edge_type = "EDGE-22";
    frm.doc.edge_color = "";
    trigger("default_edge_type", frm);
    assert.equal(databaseCalls.length, 1);
    frm.doc.name = "DCO-2026-00003";
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    databaseCalls[0].resolve({ message: { edge_color: "White" } });
    await flushPromises();
    assert.equal(setValues.length, 0);

    // A stage lookup started for one order cannot activate drawing controls in
    // the order opened while that lookup was in flight.
    frm.doc.current_production_stage = "STAGE-DRAWING";
    const stageLookup = fakeWindow.AlmdinaDrawingPlanUX.ensureStageType(frm);
    assert.equal(calls.length, 2);
    assert.equal(databaseCalls.length, 1);
    frm.doc.name = "DCO-2026-00004";
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    calls[1].resolve({ message: { active_stage_type: "Drawing" } });
    assert.equal(await stageLookup, false);
    assert.equal(frm.__almdina_stage_type, null);

    console.log("Door cutting order asynchronous identity guards passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
