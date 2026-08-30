"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const handlers = {};
const windowListeners = new Map();
const documentListeners = new Map();
const scheduledFrames = new Map();
const cleanups = new WeakMap();
const writes = [];
let failWrites = false;
let uuidSequence = 0;
let officialSaveCalls = 0;
let planSnapshot = null;
let costSnapshot = null;

function workspaceStore(readSnapshot) {
    const listeners = new Set();
    return {
        subscribe(listener) {
            listeners.add(listener);
            return () => listeners.delete(listener);
        },
        emit(snapshot) {
            listeners.forEach((listener) => listener(snapshot));
        },
        snapshot: readSnapshot,
    };
}

const planStore = workspaceStore(() => planSnapshot);
const costStore = workspaceStore(() => costSnapshot);

const repository = {
    createIdentity() {
        uuidSequence += 1;
        return `00000000-0000-4000-8000-${String(uuidSequence).padStart(12, "0")}`;
    },
    async write(record) {
        writes.push(structuredClone(record));
        if (failWrites) {
            return { ok: false, error: { code: "quota_exceeded", message: "quota full" } };
        }
        return { ok: true, value: record };
    },
    async discover() { return { ok: true, value: { records: [], rejected: [] } }; },
    async setOfficialSaveState(identityValue, state) {
        return { ok: true, value: { ...identityValue, official_save_state: state } };
    },
    async delete() { return { ok: true, value: true }; },
    async hashCanonical(value) { return `hash:${JSON.stringify(value)}`; },
    async requestPersistence() { return false; },
};

function identity(frm) {
    return `Door Cutting Order::${frm.doc.name}`;
}

const DocumentContext = {
    capture(frm) { return Object.freeze({ form: frm, generation: 1 }); },
    isSameDocument(frm, token) { return token && token.form === frm; },
    formIdentity(frm) { return identity(frm); },
    registerCleanup(frm, key, cleanup) {
        cleanups.set(frm, { key, cleanup });
        return true;
    },
    scheduleFrame(frm, key, callback) {
        scheduledFrames.set(`${identity(frm)}::${key}`, callback);
        return scheduledFrames.size;
    },
};

const fakeDocument = {
    visibilityState: "visible",
    addEventListener(name, callback) { documentListeners.set(name, callback); },
};
const fakeWindow = {
    location: { host: "erp.example.test" },
    structuredClone,
    AlmdinaDocumentContext: DocumentContext,
    AlmdinaOrderRevisionUX: {
        isEditSessionActive(frm) { return !frm.is_new() && frm.editSessionActive !== false; },
    },
    AlmdinaPlanWorkspaceState: {
        storeFor() { return planStore; },
        snapshot() { return planSnapshot; },
        activePlan() { return { name: "PLAN-001", modified: "2026-08-29 07:30:00.000000" }; },
    },
    AlmdinaCostWorkspaceState: {
        storeFor() { return costStore; },
        snapshot() { return costSnapshot; },
    },
    addEventListener(name, callback) { windowListeners.set(name, callback); },
    dispatchEvent() {},
    cur_frm: null,
};
const fakeFrappe = {
    boot: { sitename: "erp.example.test" },
    session: { user: "operator@example.test" },
    utils: {},
    datetime: {},
    model: {
        clear_table(doc, fieldname) { doc[fieldname] = []; },
        add_child(doc, doctype, fieldname) {
            const row = { doctype, name: `new-row-${(doc[fieldname] || []).length + 1}`, __islocal: 1 };
            doc[fieldname] = doc[fieldname] || [];
            doc[fieldname].push(row);
            return row;
        },
    },
    ui: {
        form: {
            on(doctype, events) {
                handlers[doctype] = { ...(handlers[doctype] || {}), ...events };
            },
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    document: fakeDocument,
    frappe: fakeFrappe,
    console,
    Object,
    Array,
    Set,
    Map,
    WeakMap,
    String,
    Number,
    Date,
    JSON,
    Promise,
    Blob,
    structuredClone,
});

function run(relative) {
    const source = fs.readFileSync(path.resolve(__dirname, relative), "utf8");
    vm.runInContext(source, context, { filename: path.basename(relative) });
}

run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_recovery_projection.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_checkpoint_session.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_new_recovery.js");
fakeWindow.AlmdinaDcoRecovery.LocalDraftRepository = Object.freeze({ create: () => repository });
fakeWindow.AlmdinaDcoRecovery.LocalAssetRepository = Object.freeze({ create: () => ({}) });
run("../../public/js/door_cutting_order/recovery/presentation/door_cutting_order_local_checkpoint.js");

function form(name, isLocal = false) {
    return {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name,
            __islocal: isLocal ? 1 : 0,
            modified: isLocal ? null : "2026-08-29 08:00:00.000000",
            customer: "CUST-001",
            board_description: "MDF",
            pieces: [{
                name: isLocal ? "new-door-cutting-order-detail-1" : "DCO-DETAIL-001",
                __islocal: isLocal ? 1 : 0,
                width_cm: 40,
                length_cm: 60,
                qty: 1,
            }],
        },
        is_new() { return Boolean(this.doc.__islocal); },
        save() { officialSaveCalls += 1; return Promise.resolve(); },
        editSessionActive: true,
    };
}

function runFrame(frm) {
    const key = [...scheduledFrames.keys()].find((candidate) => candidate.startsWith(`${identity(frm)}::`));
    assert.ok(key, `expected a scheduled checkpoint frame for ${identity(frm)}`);
    const callback = scheduledFrames.get(key);
    scheduledFrames.delete(key);
    callback();
}

(async () => {
    const editForm = form("DCO-2026-00001");
    fakeWindow.cur_frm = editForm;
    handlers["Door Cutting Order"].onload(editForm);
    const initial = fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(editForm);
    assert.equal(initial.mode, "EDIT");
    assert.equal(initial.session_origin_modified, "2026-08-29 08:00:00.000000");
    assert.equal(initial.expected_server_modified, "2026-08-29 08:00:00.000000");

    handlers["Door Cutting Order"].customer(editForm);
    handlers["Door Cutting Order"].board_description(editForm);
    assert.equal(writes.length, 0, "mutations batch until the DocumentContext frame");
    runFrame(editForm);
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(editForm);
    assert.equal(writes.length, 1);
    assert.equal(writes[0].recovery_revision, 2);
    assert.equal(writes[0].expected_recovery_revision, 0);
    assert.equal(writes[0].mode, "EDIT");
    assert.equal(writes[0].target_name, "DCO-2026-00001");
    assert.equal(writes[0].session_origin_modified, "2026-08-29 08:00:00.000000");
    assert.equal(writes[0].expected_server_modified, "2026-08-29 08:00:00.000000");
    assert.equal(writes[0].payload.dco.modified, undefined);
    assert.equal(writes[0].payload.dco.pieces[0].piece_key, "DCO-DETAIL-001");
    assert.equal(officialSaveCalls, 0);

    editForm.__almdina_preserve_edit_session_after_save = true;
    await handlers["Door Cutting Order"].before_save(editForm);
    editForm.doc.modified = "2026-08-29 09:00:00.000000";
    await handlers["Door Cutting Order"].after_save(editForm);
    runFrame(editForm);
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(editForm);
    assert.equal(writes.length, 2);
    assert.equal(writes[1].expected_recovery_revision, writes[0].recovery_revision);
    assert.equal(writes[1].session_origin_modified, "2026-08-29 08:00:00.000000");
    assert.equal(writes[1].expected_server_modified, "2026-08-29 09:00:00.000000");
    assert.equal(officialSaveCalls, 0, "local checkpoint integration never invokes frm.save()");

    const newForm = form("new-door-cutting-order-1", true);
    fakeWindow.cur_frm = newForm;
    await handlers["Door Cutting Order"].onload(newForm);
    handlers["Door Cutting Order Detail"].width_cm(newForm);
    runFrame(newForm);
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(newForm);
    const firstNew = writes.at(-1);
    assert.equal(firstNew.mode, "NEW");
    assert.equal(firstNew.target_name, null);
    assert.equal(firstNew.session_origin_modified, null);
    assert.equal(firstNew.expected_server_modified, null);
    assert.equal(firstNew.expected_recovery_revision, 0);
    assert.equal(Object.hasOwn(firstNew, "official_save_state"), false);
    assert.match(firstNew.draft_id, /^00000000-0000-4000-8000-/);
    assert.match(firstNew.payload.dco.pieces[0].piece_key, /^00000000-0000-4000-8000-/);
    const stableDraftId = firstNew.draft_id;
    const stablePieceKey = firstNew.payload.dco.pieces[0].piece_key;

    handlers["Door Cutting Order Detail"].qty(newForm);
    runFrame(newForm);
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(newForm);
    const secondNew = writes.at(-1);
    assert.equal(secondNew.draft_id, stableDraftId);
    assert.equal(secondNew.payload.dco.pieces[0].piece_key, stablePieceKey);
    assert.equal(secondNew.recovery_revision, firstNew.recovery_revision + 1);
    assert.equal(secondNew.expected_recovery_revision, firstNew.recovery_revision);

    const writesBeforePromotion = writes.length;
    await handlers["Door Cutting Order"].before_save(newForm);
    newForm.doc.name = "DCO-2026-00999";
    newForm.doc.__islocal = 0;
    newForm.doc.modified = "2026-08-29 10:00:00.000000";
    await handlers["Door Cutting Order"].after_save(newForm);
    assert.equal(writes.length, writesBeforePromotion);
    assert.equal(
        fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(newForm),
        null,
        "acknowledged first insert completes and removes the local session"
    );

    fakeWindow.cur_frm = editForm;
    failWrites = true;
    handlers["Door Cutting Order"].order_notes(editForm);
    runFrame(editForm);
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(editForm);
    const failed = fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(editForm);
    assert.equal(failed.state, "ERROR");
    assert.equal(failed.error.code, "quota_exceeded");
    assert.equal(officialSaveCalls, 0);
    assert.equal(typeof editForm.save, "function", "normal DCO behavior remains available after storage failure");

    failWrites = false;
    handlers["Door Cutting Order"].order_notes(editForm);
    fakeDocument.visibilityState = "hidden";
    documentListeners.get("visibilitychange")();
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(editForm);
    assert.equal(fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(editForm).state, "LOCAL_SAVED");

    handlers["Door Cutting Order"].edge_color(editForm);
    windowListeners.get("pagehide")();
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(editForm);
    assert.equal(fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(editForm).state, "LOCAL_SAVED");
    assert.equal(officialSaveCalls, 0);

    const workspaceForm = form("DCO-2026-00002");
    workspaceForm.editSessionActive = false;
    fakeWindow.cur_frm = workspaceForm;
    handlers["Door Cutting Order"].onload(workspaceForm);
    assert.equal(fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(workspaceForm), null);
    planSnapshot = { editing: true, dirty: false };
    costSnapshot = null;
    handlers["Door Cutting Order"].almdina_edit_session_changed(workspaceForm);
    planSnapshot = {
        editing: true,
        dirty: true,
        baseline: {
            packing_mode: "Auto",
            cutting_machine_type: "Panel Saw",
            optimization_time_limit_sec: 20,
            kerf_mm: 3,
            trim_margin_mm: 5,
        },
        draft: {
            packing_mode: "Deep Search",
            cutting_machine_type: "Panel Saw",
            optimization_time_limit_sec: 30,
            kerf_mm: 4,
            trim_margin_mm: 6,
        },
    };
    planStore.emit(planSnapshot);
    runFrame(workspaceForm);
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(workspaceForm);
    const planWrite = writes.at(-1);
    assert.equal(planWrite.dirty_scope, "PLAN");
    assert.equal(planWrite.payload.plan_workspace_draft.baseline.plan_name, "PLAN-001");
    assert.equal(
        planWrite.payload.plan_workspace_draft.baseline.plan_modified,
        "2026-08-29 07:30:00.000000"
    );
    assert.equal(planWrite.payload.plan_workspace_draft.draft.packing_mode, "Deep Search");

    planSnapshot = { editing: false, dirty: false };
    costSnapshot = {
        editing: true,
        dirty: false,
    };
    handlers["Door Cutting Order"].almdina_edit_session_changed(workspaceForm);
    costSnapshot = {
        editing: true,
        dirty: true,
        data: { cutting_plan: "PLAN-001" },
        baseline: { board_rate_usd: 20, cutting_cost_per_board_usd: 3 },
        draft: { board_rate_usd: 22, cutting_cost_per_board_usd: 4 },
    };
    costStore.emit(costSnapshot);
    runFrame(workspaceForm);
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(workspaceForm);
    const costWrite = writes.at(-1);
    assert.equal(costWrite.dirty_scope, "COST");
    assert.equal(costWrite.payload.cost_workspace_draft.baseline.cutting_plan, "PLAN-001");
    assert.equal(costWrite.payload.cost_workspace_draft.draft.board_rate_usd, 22);
    assert.equal(officialSaveCalls, 0);

    console.log("DCO local checkpoint lifecycle simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
