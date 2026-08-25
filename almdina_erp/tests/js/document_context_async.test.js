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
const edgeTypeCalls = [];
const setValues = [];

const fakeWindow = {
    cur_frm: null,
    clearTimeout() {},
    addEventListener() {},
    dispatchEvent() {},
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
    call(options = {}) {
        const pending = deferred();
        pending.options = options;
        calls.push(pending);
        return pending.promise;
    },
    db: {
        get_value() {
            const pending = deferred();
            databaseCalls.push(pending);
            return pending.promise;
        },
        get_list() {
            const pending = deferred();
            edgeTypeCalls.push(pending);
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
    CustomEvent: class CustomEvent {
        constructor(type, options = {}) {
            this.type = type;
            this.detail = options.detail;
        }
    },
    __: value => value,
});
vm.runInContext(source("door_cutting_order/core/door_cutting_order_document_context.js"), context);
vm.runInContext(source("door_cutting_order/order_entry/door_cutting_order_defaults.js"), context);
vm.runInContext(source("door_cutting_order/order_entry/door_cutting_order_operator_ux.js"), context);
vm.runInContext(source("door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js"), context);

function trigger(event, frm) {
    const eventHandlers = handlers["Door Cutting Order"][event] || [];
    eventHandlers.forEach(handler => handler(frm));
}

function callFor(method, fromIndex = 0) {
    return calls.slice(fromIndex).find(call => call.options && call.options.method === method) || null;
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

    // Both factory defaults and the safe edge-profile lookup belong to the first
    // visit. Neither may update the same Form instance after an A -> B -> A
    // navigation cycle. Identify requests by endpoint instead of relying on call
    // count/order as more document-scoped reads are introduced.
    trigger("onload", frm);
    const defaultsCall = callFor(
        "almdina_erp.almdina_erp.services.order_defaults_service.get_order_defaults"
    );
    const initialEdgeLookup = callFor(
        "almdina_erp.almdina_erp.services.edge_banding_lookup_service.get_order_edge_banding_options"
    );
    assert.ok(defaultsCall);
    assert.ok(initialEdgeLookup);
    assert.equal(databaseCalls.length, 0);

    frm.doc.name = "DCO-2026-00002";
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    frm.doc.name = "DCO-2026-00001";
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    defaultsCall.resolve({ message: { kerf_mm: 9 } });
    initialEdgeLookup.resolve({
        message: {
            options: [{ name: "EDGE-OLD" }],
            include_financial: false,
        },
    });
    await flushPromises();
    assert.equal(setValues.length, 0);
    assert.equal(frm._almdina_safe_edge_options_loaded, undefined);

    // Edge color is order-owned manual input. Changing the default profile must
    // not start another lookup and must never overwrite what the operator typed.
    frm.doc.default_edge_type = "EDGE-22";
    frm.doc.edge_color = "Manual White";
    const beforeProfileChangeCalls = calls.length;
    trigger("default_edge_type", frm);
    await flushPromises();
    assert.equal(calls.length, beforeProfileChangeCalls);
    assert.equal(databaseCalls.length, 0);
    assert.equal(setValues.length, 0);
    assert.equal(frm.doc.edge_color, "Manual White");

    // A stage lookup started for one order cannot activate drawing controls in
    // the order opened while that lookup was in flight.
    frm.doc.current_production_stage = "STAGE-DRAWING";
    const stageLookup = fakeWindow.AlmdinaDrawingPlanUX.ensureStageType(frm);
    const stageCall = calls[calls.length - 1];
    frm.doc.name = "DCO-2026-00004";
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    stageCall.resolve({ message: { active_stage_type: "Drawing" } });
    assert.equal(await stageLookup, false);
    assert.equal(frm.__almdina_stage_type, null);

    // A late edge-type lookup may populate only the document generation that
    // started it. The next order starts its own request and remains authoritative.
    delete frm._dco_edge_types;
    delete frm._dco_edge_types_loaded;
    frm.doc.name = "DCO-EDGE-A";
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    const edgeTypesA = fakeWindow.AlmdinaDoorCuttingFastEntry.loadEdgeTypes(frm);
    assert.equal(edgeTypeCalls.length, 1);

    frm.doc.name = "DCO-EDGE-B";
    fakeWindow.AlmdinaDocumentContext.synchronize(frm);
    const edgeTypesB = fakeWindow.AlmdinaDoorCuttingFastEntry.loadEdgeTypes(frm);
    assert.equal(edgeTypeCalls.length, 2);

    edgeTypeCalls[0].resolve([{ name: "EDGE-A", edge_type_name: "Edge A" }]);
    assert.equal(await edgeTypesA, false);
    assert.equal(frm._dco_edge_types, undefined);

    edgeTypeCalls[1].resolve([{ name: "EDGE-B", edge_type_name: "Edge B" }]);
    assert.equal(await edgeTypesB, true);
    assert.deepEqual(
        frm._dco_edge_types.map(row => row.name),
        ["EDGE-B"]
    );

    console.log("Door cutting order asynchronous identity guards passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
