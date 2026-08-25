"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

let frameSequence = 0;
const frames = new Map();
const handlers = {};

global.window = {
    cur_frm: null,
    setTimeout,
    clearTimeout,
    requestAnimationFrame(callback) {
        frameSequence += 1;
        frames.set(frameSequence, callback);
        return frameSequence;
    },
    cancelAnimationFrame(id) {
        frames.delete(id);
    },
    addEventListener() {},
    dispatchEvent() {},
};
global.frappe = {
    model: { new_names: {} },
    ui: {
        form: {
            on(doctype, events) {
                assert.equal(doctype, "Door Cutting Order");
                Object.entries(events).forEach(([event, handler]) => {
                    handlers[event] = handlers[event] || [];
                    handlers[event].push(handler);
                });
            },
        },
    },
};
global.CustomEvent = class CustomEvent {
    constructor(type, options = {}) {
        this.type = type;
        this.detail = options.detail;
    }
};

function trigger(event, frm) {
    (handlers[event] || []).forEach(handler => handler(frm));
}

function runSerially(tasks) {
    return tasks.reduce(
        (promise, task) => promise.then(() => task()),
        Promise.resolve()
    );
}

function flushFrames() {
    const pending = [...frames.entries()];
    frames.clear();
    pending.forEach(([, callback]) => callback());
}

function sleep(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

require(path.resolve(__dirname, "../../public/js/frontend_foundation.js"));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/core/door_cutting_order_document_context.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_lifecycle.js"
));

const lifecycle = window.AlmdinaMeasurementLifecycle;
assert.ok(lifecycle, "Measurement lifecycle API must be installed");
assert.equal(Object.isFrozen(lifecycle), true, "Measurement lifecycle API must be immutable");

function form(name, { isLocal = false } = {}) {
    return {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name,
            __islocal: isLocal ? 1 : 0,
            pieces: [],
        },
        fields_dict: {},
        is_new() {
            return Boolean(this.doc.__islocal);
        },
    };
}

function activate(frm) {
    window.cur_frm = frm;
    trigger("before_load", frm);
}

function measurementDom(rowNames = ["ROW-1"]) {
    return {
        tableShells: 1,
        tableClasses: new Set(),
        hiddenCalcColumns: new Set(),
        headerSelectors: new Set(),
        rowSelectors: new Set(),
        virtualRows: new Set(),
        noteEnhancements: new Set(),
        toolbarEnhancements: new Set(),
        performanceObservers: new Set(),
        listenerOwners: new Set(),
        rowNames: [...rowNames],
        modelValues: { "ROW-1:width_cm": "48.5" },
        activeInput: "ROW-1:width_cm",
        scrollTop: 175,
        scrollLeft: 42,
        effectiveReconciliations: 0,
    };
}

function reconcileMeasurementDom(dom) {
    const alreadyReady = dom.tableClasses.has("dco-compact-measurements");
    dom.tableClasses.add("dco-compact-measurements");
    dom.hiddenCalcColumns.add("area_m2");
    dom.hiddenCalcColumns.add("edge_meters");
    dom.headerSelectors.add(".dco-select-all");
    dom.rowNames.forEach(name => {
        dom.rowSelectors.add(`.dco-row-selector:${name}`);
        dom.noteEnhancements.add(`.dco-notes-editor:${name}`);
    });
    dom.virtualRows.add(".dco-virtual-row");
    dom.toolbarEnhancements.add(".dco-measurement-table-actions");
    dom.performanceObservers.add("_dcoTablePerformanceObserver");
    dom.listenerOwners.add("measurement-delegated-events");
    if (!alreadyReady) dom.effectiveReconciliations += 1;
}

function scheduleDomReconciliation(frm, dom) {
    return lifecycle.schedule(
        frm,
        "measurement-final-reconciliation",
        () => reconcileMeasurementDom(dom),
        { immediate: false }
    );
}

function domSnapshot(dom) {
    return {
        tableShells: dom.tableShells,
        tableClasses: [...dom.tableClasses].sort(),
        hiddenCalcColumns: [...dom.hiddenCalcColumns].sort(),
        headerSelectors: [...dom.headerSelectors].sort(),
        rowSelectors: [...dom.rowSelectors].sort(),
        virtualRows: [...dom.virtualRows].sort(),
        noteEnhancements: [...dom.noteEnhancements].sort(),
        toolbarEnhancements: [...dom.toolbarEnhancements].sort(),
        performanceObservers: [...dom.performanceObservers].sort(),
        listenerOwners: [...dom.listenerOwners].sort(),
    };
}

async function testSameFeatureCancelsStaleFrameAndTimer() {
    const frm = form("DCO-LIFECYCLE-1");
    activate(frm);
    const calls = [];

    lifecycle.schedule(frm, "feature", () => calls.push("stale"), {
        immediate: false,
        delays: [5],
    });
    lifecycle.schedule(frm, "feature", () => calls.push("current"), {
        immediate: false,
        delays: [5],
    });

    flushFrames();
    await sleep(15);

    assert.deepEqual(
        calls,
        ["current", "current"],
        "Replacing one feature schedule must cancel its stale frame and timeout"
    );
}

async function testDocumentIdentityInvalidatesQueuedWork() {
    const frm = form("DCO-LIFECYCLE-A");
    activate(frm);
    const calls = [];
    const documentBDom = measurementDom();
    let sharedDom = measurementDom();

    lifecycle.schedule(frm, "document-bound", () => calls.push("ran"), {
        immediate: false,
        delays: [5],
    });
    lifecycle.schedule(
        frm,
        "document-bound-dom",
        () => reconcileMeasurementDom(sharedDom),
        { immediate: false, delays: [5] }
    );
    frm.doc.name = "DCO-LIFECYCLE-B";
    trigger("onload", frm);
    sharedDom = documentBDom;

    flushFrames();
    await sleep(15);

    assert.deepEqual(calls, [], "Queued work must not render a different document");
    assert.equal(documentBDom.tableClasses.size, 0, "A must not compact B");
    assert.equal(documentBDom.headerSelectors.size, 0, "A must not decorate B headers");
    assert.equal(documentBDom.noteEnhancements.size, 0, "A must not decorate B notes");
    assert.equal(documentBDom.performanceObservers.size, 0, "A must not observe B");
    assert.equal(documentBDom.listenerOwners.size, 0, "A must not bind listeners to B");
    assert.equal(documentBDom.activeInput, "ROW-1:width_cm", "A must not restore focus into B");
    assert.equal(documentBDom.scrollTop, 175, "A must not restore scroll into B");
}

async function testRetryStopsAfterSuccessAndCanBeCancelled() {
    const frm = form("DCO-LIFECYCLE-RETRY");
    activate(frm);
    let attempts = 0;

    lifecycle.retry(
        frm,
        "retry",
        () => {
            attempts += 1;
            return attempts >= 3;
        },
        { maxAttempts: 11, delay: 2 }
    );

    flushFrames();
    await sleep(4);
    flushFrames();
    await sleep(4);
    flushFrames();
    await sleep(4);

    assert.equal(attempts, 3, "Retry must stop immediately after the callback succeeds");

    let cancelledCalls = 0;
    lifecycle.schedule(frm, "cancelled", () => { cancelledCalls += 1; }, {
        immediate: false,
        delays: [5],
    });
    assert.equal(lifecycle.cancel(frm, "cancelled"), true);
    flushFrames();
    await sleep(15);
    assert.equal(cancelledCalls, 0, "Explicit cancellation must dispose queued work");
}

async function testNewDocumentPromotionKeepsQueuedWorkCurrent() {
    const temporaryName = "new-door-cutting-order-1";
    const permanentName = "DCO-2026-00999";
    const frm = form(temporaryName, { isLocal: true });
    const calls = [];
    activate(frm);

    lifecycle.schedule(frm, "promotion", () => calls.push(frm.doc.name), {
        immediate: false,
        delays: [5],
    });

    trigger("before_save", frm);
    frappe.model.new_names[temporaryName] = permanentName;
    frm.doc = { ...frm.doc, name: permanentName, __islocal: 0, localname: temporaryName };
    trigger("after_save", frm);

    flushFrames();
    await sleep(15);

    assert.deepEqual(
        calls,
        [permanentName, permanentName],
        "First-insert promotion must keep same-Form measurement work current"
    );
}

async function testRapidFirstSaveMatchesFreshSavedDomWithoutDestroyingInputState() {
    const temporaryName = "new-door-cutting-order-rapid";
    const permanentName = "DCO-2026-01000";
    const frm = form(temporaryName, { isLocal: true });
    const promotedDom = measurementDom();
    activate(frm);

    // Initial render queued work, then the operator saves before RAF executes.
    scheduleDomReconciliation(frm, promotedDom);
    trigger("before_save", frm);
    frappe.model.new_names[temporaryName] = permanentName;
    frm.doc = { ...frm.doc, name: permanentName, __islocal: 0, localname: temporaryName };
    trigger("after_save", frm);

    // Frappe refresh follows after_save. Keyed replacement leaves exactly one
    // effective current reconciliation for the promoted generation.
    trigger("refresh", frm);
    scheduleDomReconciliation(frm, promotedDom);
    flushFrames();

    const fresh = form(permanentName);
    const freshDom = measurementDom();
    activate(fresh);
    scheduleDomReconciliation(fresh, freshDom);
    flushFrames();

    assert.deepEqual(domSnapshot(promotedDom), domSnapshot(freshDom));
    assert.equal(promotedDom.tableShells, 1, ".dco-fast-table shell must exist exactly once");
    assert.deepEqual([...promotedDom.tableClasses], ["dco-compact-measurements"]);
    assert.equal(promotedDom.hiddenCalcColumns.size, 2);
    assert.equal(promotedDom.headerSelectors.size, 1);
    assert.equal(promotedDom.rowSelectors.size, 1);
    assert.equal(promotedDom.virtualRows.size, 1);
    assert.equal(promotedDom.noteEnhancements.size, 1);
    assert.equal(promotedDom.toolbarEnhancements.size, 1);
    assert.equal(promotedDom.performanceObservers.size, 1);
    assert.equal(promotedDom.listenerOwners.size, 1);
    assert.equal(promotedDom.effectiveReconciliations, 1);

    // Reconciliation enhances the existing shell; it does not rebuild model or
    // steal the active input/scroll owned by the operator.
    assert.equal(promotedDom.modelValues["ROW-1:width_cm"], "48.5");
    assert.equal(promotedDom.activeInput, "ROW-1:width_cm");
    assert.equal(promotedDom.scrollTop, 175);
    assert.equal(promotedDom.scrollLeft, 42);
}

async function testFrappeV16FirstSaveDispatchOrdering() {
    const temporaryName = "new-door-cutting-order-ordering";
    const permanentName = "DCO-2026-01001";
    const frm = form(temporaryName, { isLocal: true });
    const order = [];
    activate(frm);

    await runSerially([
        () => { order.push("validate"); },
        () => {
            order.push("before_save");
            trigger("before_save", frm);
        },
        () => {
            order.push("save/insert response");
            frappe.model.new_names[temporaryName] = permanentName;
            frm.doc = {
                ...frm.doc,
                name: permanentName,
                __islocal: 0,
                localname: temporaryName,
            };
            order.push("local name mapped to permanent name");

            // Frappe v16 dispatches after_save without awaiting it, then calls
            // frm.refresh(). Both serial queues start in this exact order.
            const afterSave = runSerially([
                () => {
                    order.push("after_save handler");
                    trigger("after_save", frm);
                },
            ]);
            order.push("after_save dispatched");
            const refresh = runSerially([
                () => {
                    order.push("refresh handler");
                    trigger("refresh", frm);
                },
            ]);
            order.push("refresh dispatched");
            return Promise.all([afterSave, refresh]);
        },
    ]);

    assert.deepEqual(order, [
        "validate",
        "before_save",
        "save/insert response",
        "local name mapped to permanent name",
        "after_save dispatched",
        "refresh dispatched",
        "after_save handler",
        "refresh handler",
    ]);
    assert.equal(
        order.includes("onload_post_render"),
        false,
        "A post-save refresh is not a new onload cycle in Frappe v16"
    );
}

(async () => {
    await testSameFeatureCancelsStaleFrameAndTimer();
    await testDocumentIdentityInvalidatesQueuedWork();
    await testRetryStopsAfterSuccessAndCanBeCancelled();
    await testNewDocumentPromotionKeepsQueuedWorkCurrent();
    await testRapidFirstSaveMatchesFreshSavedDomWithoutDestroyingInputState();
    await testFrappeV16FirstSaveDispatchOrdering();
    console.log("DCO measurement lifecycle checks passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
