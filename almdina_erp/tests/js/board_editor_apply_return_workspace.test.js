"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
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

async function flushPromises() {
    for (let index = 0; index < 8; index += 1) {
        await Promise.resolve();
    }
}

function pieceOnSheet(snapshotJson, pieceInstanceId) {
    const plan = typeof snapshotJson === "string" ? JSON.parse(snapshotJson) : snapshotJson;
    for (const sheet of plan.sheets || []) {
        for (const piece of sheet.pieces || []) {
            if (String(piece.piece_instance_id || "") === String(pieceInstanceId)) {
                return Number(sheet.sheet_no);
            }
        }
    }
    return null;
}

function makeFormRoot() {
    const listeners = new Map();
    return {
        nodeType: 1,
        addEventListener(name, handler) {
            if (!listeners.has(name)) listeners.set(name, new Set());
            listeners.get(name).add(handler);
        },
        removeEventListener(name, handler) {
            if (listeners.has(name)) listeners.get(name).delete(handler);
        },
    };
}

function makePayload({ orderName, planName, pieceSheet }) {
    const snapshot = {
        sheets: [
            {
                sheet_no: 1,
                full_width_cm: 280,
                full_length_cm: 210,
                pieces: pieceSheet === 1
                    ? [{ piece_instance_id: "PIECE-A", x_cm: 10, y_cm: 10, width_cm: 40, length_cm: 60 }]
                    : [],
            },
            {
                sheet_no: 2,
                full_width_cm: 280,
                full_length_cm: 210,
                pieces: pieceSheet === 2
                    ? [{ piece_instance_id: "PIECE-A", x_cm: 20, y_cm: 30, width_cm: 40, length_cm: 60 }]
                    : [],
            },
        ],
    };
    return {
        order_name: orderName,
        approved_plan: "",
        plans: {
            system_draft: {
                name: "CP-SYSTEM",
                status: "Draft",
                display_context: "current_draft",
                snapshot_json: JSON.stringify({ sheets: [] }),
            },
            uploaded_draft: null,
            approved: null,
            board_editor_draft: planName
                ? {
                    name: planName,
                    status: "Draft",
                    display_context: "current_draft",
                    source_type: "Board Editor",
                    snapshot_json: JSON.stringify(snapshot),
                    can_approve: true,
                }
                : null,
        },
    };
}

(async () => {
    const controllerSource = source("public/js/board_editor/controller.js");
    assert.match(controllerSource, /rememberApplyReturnContext/);
    assert.match(controllerSource, /almdina\.dco\.planApplyReturn\./);
    assert.match(controllerSource, /order_name/);
    assert.match(controllerSource, /plan_name/);
    assert.doesNotMatch(controllerSource, /planWorkspaceReload/);

    const storage = new Map();
    const listeners = new Map();
    const formHooks = [];
    let activeFieldname = "results_tab";
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-APPLY-1",
            approved_plan: "",
        },
        get_active_tab() {
            return { df: { fieldname: activeFieldname } };
        },
        layout: {
            current_tab: { df: { fieldname: "results_tab" } },
        },
        wrapper: makeFormRoot(),
        is_new() {
            return false;
        },
    };

    const planFlights = [];
    let planCalls = 0;

    const fakeWindow = {
        cur_frm: frm,
        sessionStorage: {
            getItem(key) {
                return storage.has(key) ? storage.get(key) : null;
            },
            setItem(key, value) {
                storage.set(String(key), String(value));
            },
            removeItem(key) {
                storage.delete(String(key));
            },
        },
        addEventListener(name, handler) {
            if (!listeners.has(name)) listeners.set(name, []);
            listeners.get(name).push(handler);
        },
        dispatchEvent(event) {
            for (const handler of listeners.get(event.type) || []) handler(event);
            return true;
        },
        requestAnimationFrame(callback) {
            callback();
            return 1;
        },
        setTimeout(callback) {
            callback();
            return 1;
        },
        clearTimeout() {},
        AlmdinaPermissions: {
            canDocument() { return true; },
            can() { return true; },
        },
        AlmdinaDocumentContext: {
            formIdentity(currentForm) {
                return `${currentForm.doctype}::${currentForm.doc.name}`;
            },
            capture(currentForm) {
                return Object.freeze({
                    identity: `${currentForm.doctype}::${currentForm.doc.name}`,
                    generation: 0,
                });
            },
            isCurrent(currentForm, token) {
                return token.identity === `${currentForm.doctype}::${currentForm.doc.name}`;
            },
            isSameDocument(currentForm, token) {
                return token.identity === `${currentForm.doctype}::${currentForm.doc.name}`;
            },
            scheduleFrame(_frm, _key, callback) {
                callback();
                return 1;
            },
            registerCleanup() {
                return true;
            },
        },
        AlmdinaPlanWorkspaceAPI: {
            load() {
                const flight = deferred();
                planFlights.push(flight);
                planCalls += 1;
                return flight.promise;
            },
        },
    };

    const fakeFrappe = {
        boot: {},
        utils: { escape_html: (value) => String(value || "") },
        ui: {
            form: {
                on(doctype, handlers) {
                    formHooks.push({ doctype, handlers });
                },
            },
        },
        msgprint() {},
    };
    fakeWindow.frappe = fakeFrappe;

    class CustomEvent {
        constructor(type, options = {}) {
            this.type = type;
            this.detail = options.detail;
        }
    }

    const context = vm.createContext({
        window: fakeWindow,
        document: { documentElement: { lang: "ar", getAttribute: () => "rtl" } },
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Array,
        Map,
        Set,
        String,
        Number,
        Boolean,
        JSON,
        Date,
        CustomEvent,
        structuredClone: global.structuredClone,
        __: (value) => String(value),
    });

    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"),
        context,
        { filename: "door_cutting_order_workspace_store.js" }
    );
    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_workspace_sync_coordinator.js"),
        context,
        { filename: "door_cutting_order_workspace_sync_coordinator.js" }
    );
    vm.runInContext(
        source("public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"),
        context,
        { filename: "door_cutting_order_plan_workspace_state.js" }
    );
    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_workspace_activation_lifecycle.js"),
        context,
        { filename: "door_cutting_order_workspace_activation_lifecycle.js" }
    );

    const planState = fakeWindow.AlmdinaPlanWorkspaceState;
    const coordinator = fakeWindow.AlmdinaWorkspaceSyncCoordinator;
    const lifecycle = fakeWindow.AlmdinaDcoWorkspaceActivationLifecycle;
    assert.ok(planState && coordinator && lifecycle);

    // Seed an older Edited plan already painted in memory.
    const oldPayload = makePayload({
        orderName: "DCO-APPLY-1",
        planName: "CP-EDIT-OLD",
        pieceSheet: 1,
    });
    const seedId = planState.storeFor(frm).beginLoad("Door Cutting Order::DCO-APPLY-1");
    assert.equal(
        planState.storeFor(frm).resolveLoad("Door Cutting Order::DCO-APPLY-1", seedId, oldPayload),
        true
    );
    frm.__almdinaPlanWorkspaceLoadedIdentity = "Door Cutting Order::DCO-APPLY-1";
    assert.equal(planState.planForTab(frm, "BoardEditor").name, "CP-EDIT-OLD");
    assert.equal(
        pieceOnSheet(planState.planForTab(frm, "BoardEditor").snapshot_json, "PIECE-A"),
        1
    );

    // Start a read that begins before apply return exists (stale generation).
    const staleFlight = planState.load(frm, { force: true });
    await flushPromises();
    assert.equal(planCalls, 1);

    // Apply moved the piece to sheet 2 and created CP-EDIT-NEW. Persist return context
    // exactly as board_editor/controller.js does after a successful createPlanCopy.
    storage.set("almdina.dco.planTab.DCO-APPLY-1", "BoardEditor");
    storage.set(
        "almdina.dco.planApplyReturn.DCO-APPLY-1",
        JSON.stringify({
            order_name: "DCO-APPLY-1",
            plan_name: "CP-EDIT-NEW",
            prefer_tab: "BoardEditor",
        })
    );

    // Lifecycle activation (WorkspaceSyncCoordinator path) must invalidate the
    // pre-apply generation and coalesce into one fresh follow-up read.
    const activated = lifecycle.activate(frm, { fieldname: "results_tab" });
    await flushPromises();
    assert.equal(planCalls, 1, "forced activation joins the current flight before follow-up");

    planFlights[0].resolve(oldPayload);
    await staleFlight.catch(() => null);
    await flushPromises();
    assert.equal(planCalls, 2, "invalidated stale flight must be followed by one apply-return read");

    const newPayload = makePayload({
        orderName: "DCO-APPLY-1",
        planName: "CP-EDIT-NEW",
        pieceSheet: 2,
    });
    planFlights[1].resolve(newPayload);
    await activated;
    await flushPromises();

    const edited = planState.planForTab(frm, "BoardEditor");
    assert.equal(edited.name, "CP-EDIT-NEW", "tab data must expose the applied plan_name");
    assert.equal(
        pieceOnSheet(edited.snapshot_json, "PIECE-A"),
        2,
        "moved piece_instance_id must land on sheet 2 in BoardEditor snapshot_json"
    );
    assert.equal(frm.__almdina_active_plan_tab, "BoardEditor");
    assert.equal(storage.has("almdina.dco.planApplyReturn.DCO-APPLY-1"), false);
    assert.equal(planState.applyReturnState(frm), null);

    // First apply: no BoardEditor row yet, then the authorized row appears on retry.
    frm.doc.name = "DCO-APPLY-2";
    fakeWindow.cur_frm = frm;
    planState.reset(frm);
    storage.set(
        "almdina.dco.planApplyReturn.DCO-APPLY-2",
        JSON.stringify({
            order_name: "DCO-APPLY-2",
            plan_name: "CP-EDIT-FIRST",
            prefer_tab: "BoardEditor",
        })
    );
    activeFieldname = "results_tab";
    const firstApply = lifecycle.activate(frm, { fieldname: "results_tab", force: true });
    await flushPromises();
    const firstIndex = planCalls - 1;
    planFlights[firstIndex].resolve(makePayload({
        orderName: "DCO-APPLY-2",
        planName: null,
        pieceSheet: 1,
    }));
    await firstApply;
    await flushPromises();
    assert.equal(planState.applyReturnState(frm).status, "waiting_row");
    assert.equal(planState.planForTab(frm, "BoardEditor"), null);
    assert.ok(planCalls >= firstIndex + 2, "waiting_row auto-retries the read only");
    const retryIndex = planCalls - 1;
    planFlights[retryIndex].resolve(makePayload({
        orderName: "DCO-APPLY-2",
        planName: "CP-EDIT-FIRST",
        pieceSheet: 2,
    }));
    await flushPromises();
    assert.equal(planState.planForTab(frm, "BoardEditor").name, "CP-EDIT-FIRST");
    assert.equal(frm.__almdina_active_plan_tab, "BoardEditor");
    assert.equal(planState.applyReturnState(frm), null);

    // Read failure then retryApplyReturnRead must not invent a second plan create.
    frm.doc.name = "DCO-APPLY-3";
    planState.reset(frm);
    storage.set(
        "almdina.dco.planApplyReturn.DCO-APPLY-3",
        JSON.stringify({
            order_name: "DCO-APPLY-3",
            plan_name: "CP-EDIT-RETRY",
            prefer_tab: "BoardEditor",
        })
    );
    const failedActivate = lifecycle.activate(frm, { fieldname: "results_tab", force: true });
    await flushPromises();
    const failIndex = planCalls - 1;
    planFlights[failIndex].reject(new Error("network down"));
    await failedActivate.catch(() => null);
    await flushPromises();
    assert.equal(planState.applyReturnState(frm).status, "failed");
    const beforeRetry = planCalls;
    const retried = planState.retryApplyReturnRead(frm);
    await flushPromises();
    assert.equal(planCalls, beforeRetry + 1, "retry is a single workspace read");
    planFlights[planCalls - 1].resolve(makePayload({
        orderName: "DCO-APPLY-3",
        planName: "CP-EDIT-RETRY",
        pieceSheet: 2,
    }));
    await retried;
    await flushPromises();
    assert.equal(planState.planForTab(frm, "BoardEditor").name, "CP-EDIT-RETRY");
    assert.equal(planState.applyReturnState(frm), null);

    // Switching to another order must not inherit the previous apply-return visit.
    storage.set(
        "almdina.dco.planApplyReturn.DCO-APPLY-1",
        JSON.stringify({
            order_name: "DCO-APPLY-1",
            plan_name: "CP-SHOULD-NOT-MOVE",
            prefer_tab: "BoardEditor",
        })
    );
    frm.doc.name = "DCO-OTHER";
    planState.reset(frm);
    assert.equal(planState.applyReturnState(frm), null);
    assert.equal(planState.ensureApplyReturnState(frm), null);
    assert.equal(
        storage.get("almdina.dco.planApplyReturn.DCO-APPLY-1"),
        JSON.stringify({
            order_name: "DCO-APPLY-1",
            plan_name: "CP-SHOULD-NOT-MOVE",
            prefer_tab: "BoardEditor",
        })
    );

    // Concurrent newer plan: distinguish actual row from the requested plan_name.
    frm.doc.name = "DCO-APPLY-4";
    planState.reset(frm);
    storage.set(
        "almdina.dco.planApplyReturn.DCO-APPLY-4",
        JSON.stringify({
            order_name: "DCO-APPLY-4",
            plan_name: "CP-EDIT-EXPECTED",
            prefer_tab: "BoardEditor",
        })
    );
    const newerActivate = lifecycle.activate(frm, { fieldname: "results_tab", force: true });
    await flushPromises();
    planFlights[planCalls - 1].resolve(makePayload({
        orderName: "DCO-APPLY-4",
        planName: "CP-EDIT-NEWER",
        pieceSheet: 2,
    }));
    await newerActivate;
    await flushPromises();
    const newerState = planState.applyReturnState(frm);
    assert.equal(newerState.status, "newer");
    assert.equal(newerState.actual_plan_name, "CP-EDIT-NEWER");
    assert.equal(newerState.plan_name, "CP-EDIT-EXPECTED");
    assert.equal(planState.planForTab(frm, "BoardEditor").name, "CP-EDIT-NEWER");
    assert.equal(frm.__almdina_active_plan_tab, "BoardEditor");

    // Deferred while plan-settings editing: keep apply-return context and invalidate.
    frm.doc.name = "DCO-APPLY-5";
    planState.reset(frm);
    storage.set(
        "almdina.dco.planApplyReturn.DCO-APPLY-5",
        JSON.stringify({
            order_name: "DCO-APPLY-5",
            plan_name: "CP-EDIT-DEFER",
            prefer_tab: "BoardEditor",
        })
    );
    const deferSeed = planState.storeFor(frm).beginLoad("Door Cutting Order::DCO-APPLY-5");
    planState.storeFor(frm).resolveLoad(
        "Door Cutting Order::DCO-APPLY-5",
        deferSeed,
        makePayload({ orderName: "DCO-APPLY-5", planName: "CP-OLD", pieceSheet: 1 })
    );
    frm.__almdinaPlanWorkspaceLoadedIdentity = "Door Cutting Order::DCO-APPLY-5";
    planState.storeFor(frm).beginEdit({});
    const beforeDeferCalls = planCalls;
    const deferredSnap = await planState.load(frm, { force: true });
    assert.equal(deferredSnap.editing, true);
    assert.equal(planCalls, beforeDeferCalls, "editing defers the canonical apply-return read");
    assert.equal(planState.applyReturnState(frm).plan_name, "CP-EDIT-DEFER");
    assert.equal(planState.snapshot(frm).freshness, "stale");
    planState.storeFor(frm).cancelEdit();
    const afterEdit = planState.load(frm, { force: true });
    await flushPromises();
    planFlights[planCalls - 1].resolve(makePayload({
        orderName: "DCO-APPLY-5",
        planName: "CP-EDIT-DEFER",
        pieceSheet: 2,
    }));
    await afterEdit;
    await flushPromises();
    assert.equal(planState.planForTab(frm, "BoardEditor").name, "CP-EDIT-DEFER");

    console.log("board_editor_apply_return_workspace.test.js: ok");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
