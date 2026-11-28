"use strict";

/**
 * ALMADINA-129 offline / transport-failure regressions.
 *
 * These cases intentionally mirror Frappe Desk semantics:
 * - frm.save() returns a Promise that resolves even when the network fails
 * - after_save may run when the XHR has no `exc`
 * - the document stays __islocal until savedocs actually syncs a permanent name
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const handlers = {};
const records = new Map();
const deleted = [];
const alerts = [];
const routes = [];
const cleanupCallbacks = new WeakMap();
let uuidSequence = 0;
let reconciliationResult = { status: "NOT_FOUND" };
let reconciliationFailure = null;
let saveAttemptSequence = 0;
let writeFailure = null;
let documentGeneration = 1;
let nativeSaveImpl = null;
let lastDialog = null;

const repository = {
    createIdentity() {
        uuidSequence += 1;
        return `aaaaaaaa-aaaa-4aaa-8aaa-${String(uuidSequence).padStart(12, "0")}`;
    },
    async discover() {
        return {
            ok: true,
            value: {
                records: [...records.values()].filter((record) => record.mode === "NEW"),
                rejected: [],
            },
        };
    },
    async read(identity) {
        const current = records.get(identity.draft_id) || null;
        return { ok: true, value: current ? structuredClone(current) : null };
    },
    async write(input) {
        if (writeFailure) return { ok: false, error: structuredClone(writeFailure) };
        const current = records.get(input.draft_id) || null;
        const revision = Number(input.recovery_revision);
        const expectedRevision = Number(input.expected_recovery_revision);
        if (current && Number(current.recovery_revision) > revision) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        if (current && Number(current.recovery_revision) === revision) {
            return { ok: true, value: structuredClone(current) };
        }
        if (!current && expectedRevision !== 0) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        if (current && Number(current.recovery_revision) !== expectedRevision) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        const next = {
            ...(current || {}),
            ...structuredClone(input),
            official_save_state: (current && current.official_save_state) || "ACTIVE",
            official_save_attempted_at: current ? current.official_save_attempted_at || null : null,
            official_save_attempt_revision: current
                ? (
                    current.official_save_attempt_revision == null
                        ? (
                            current.official_save_state === "PENDING_RECONCILIATION"
                                ? Number(current.recovery_revision)
                                : null
                        )
                        : Number(current.official_save_attempt_revision)
                )
                : null,
            created_at: (current && current.created_at) || "2026-11-28T09:00:00.000Z",
            captured_at: "2026-11-28T10:00:00.000Z",
        };
        delete next.expected_recovery_revision;
        records.set(input.draft_id, next);
        return { ok: true, value: structuredClone(next) };
    },
    async setOfficialSaveState(identity, state, revision, expectedAttemptedAt) {
        const current = records.get(identity.draft_id);
        if (!current) return { ok: false, error: { code: "draft_not_found" } };
        if (Number(current.recovery_revision) !== Number(revision)) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        const currentState = current.official_save_state || "ACTIVE";
        const currentAttempt = current.official_save_attempted_at || null;
        const requiredState = state === "PENDING_RECONCILIATION" ? "ACTIVE" : "PENDING_RECONCILIATION";
        if (currentState !== requiredState || currentAttempt !== expectedAttemptedAt) {
            return { ok: false, error: { code: "save_attempt_conflict" } };
        }
        saveAttemptSequence += state === "PENDING_RECONCILIATION" ? 1 : 0;
        const attemptedAt = state === "PENDING_RECONCILIATION"
            ? `2026-11-28T10:${String(saveAttemptSequence + 1).padStart(2, "0")}:00.000Z`
            : currentAttempt;
        const next = {
            ...current,
            official_save_state: state,
            official_save_attempted_at: attemptedAt,
            official_save_attempt_revision: state === "PENDING_RECONCILIATION"
                ? Number(current.recovery_revision)
                : (
                    current.official_save_attempt_revision == null
                        ? null
                        : Number(current.official_save_attempt_revision)
                ),
        };
        records.set(identity.draft_id, next);
        return { ok: true, value: structuredClone(next) };
    },
    async delete(identity, expectedRevision = null, expectedAttemptedAt = undefined) {
        const current = records.get(identity.draft_id) || null;
        if (
            current
            && expectedRevision !== null
            && Number(current.recovery_revision) !== Number(expectedRevision)
        ) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        if (
            current
            && expectedAttemptedAt !== undefined
            && (current.official_save_attempted_at || null) !== expectedAttemptedAt
        ) {
            return { ok: false, error: { code: "save_attempt_conflict" } };
        }
        deleted.push(identity.draft_id);
        records.delete(identity.draft_id);
        return { ok: true, value: true };
    },
    async hashCanonical(value) { return JSON.stringify(value); },
    async requestPersistence() { return true; },
};

const DocumentContext = {
    capture(frm) { return Object.freeze({ frm, generation: documentGeneration }); },
    isSameDocument(frm, token) {
        return token && token.frm === frm && token.generation === documentGeneration;
    },
    isCurrent(frm, token) {
        return this.isSameDocument(frm, token)
            && (!fakeWindow.cur_frm || fakeWindow.cur_frm === frm);
    },
    formIdentity(frm) { return `Door Cutting Order::${frm.doc.name}`; },
    registerCleanup(frm, key, callback) {
        const callbacks = cleanupCallbacks.get(frm) || new Map();
        callbacks.set(key, callback);
        cleanupCallbacks.set(frm, callbacks);
        return true;
    },
    scheduleFrame(frm, key, callback) { queueMicrotask(callback); return key; },
};

const fakeWindow = {
    location: { host: "erp.example.test" },
    structuredClone,
    AlmdinaDocumentContext: DocumentContext,
    AlmdinaUi: {
        button(options = {}) {
            return `<button type="${options.type || "button"}">${options.label || ""}</button>`;
        },
    },
    AlmdinaOrderRevisionUX: { isEditSessionActive: () => false },
    AlmdinaDoorCuttingFastEntry: { render() {} },
    AlmdinaFastEntryKeyboardUX: { install() {} },
    AlmdinaTablePerformanceUX: { refreshAll() {} },
    AlmdinaMeasurementToolbarUX: { polish() {} },
    addEventListener() {},
    cur_frm: null,
};
const fakeDocument = { visibilityState: "visible", addEventListener() {} };
const fakeFrappe = {
    boot: { sitename: "erp.example.test" },
    session: { user: "operator@example.test" },
    validated: true,
    utils: {},
    datetime: {},
    model: {
        clear_table(doc, fieldname) { doc[fieldname] = []; },
        add_child(doc, doctype, fieldname) {
            const row = { doctype, name: `new-detail-${doc[fieldname].length + 1}`, __islocal: 1 };
            doc[fieldname].push(row);
            return row;
        },
    },
    ui: {
        Dialog: class FakeDialog {
            constructor(options) {
                this.options = options;
                this.listener = null;
                lastDialog = this;
            }
            show() {}
            hide() {}
            get $wrapper() {
                return {
                    get: () => ({
                        addEventListener: (name, callback) => { this.listener = callback; },
                        querySelector: () => null,
                        querySelectorAll: () => [],
                    }),
                    attr() {},
                };
            }
        },
        form: {
            on(doctype, events) { handlers[doctype] = { ...(handlers[doctype] || {}), ...events }; },
        },
    },
    set_route(...args) { routes.push(args); },
    msgprint() {},
    show_alert(payload) { alerts.push(payload); },
    confirm(message, callback) { callback(); },
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
    structuredClone,
    queueMicrotask,
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
fakeWindow.AlmdinaDcoRecovery.ServerReconciliation = Object.freeze({
    async reconcileNewCreation() {
        if (reconciliationFailure) throw reconciliationFailure;
        return reconciliationResult;
    },
});
run("../../public/js/door_cutting_order/recovery/presentation/door_cutting_order_local_checkpoint.js");

const Recovery = fakeWindow.AlmdinaDcoRecovery;

function form(name) {
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name,
            __islocal: 1,
            customer: "",
            pieces: [],
        },
        is_new() { return Boolean(this.doc.__islocal); },
        refresh_fields() {},
        refresh_field() {},
        dirty() {},
        // Frappe-realistic default: Promise resolves even when nothing was created.
        save() {
            if (typeof nativeSaveImpl === "function") return nativeSaveImpl(this);
            return Promise.resolve(undefined);
        },
    };
    return frm;
}

function seedDraft(frm, values = {}) {
    frm.doc.customer = values.customer || "CUST-OFFLINE";
    frm.doc.board_description = values.board || "MDF";
    frm.doc.pieces = values.pieces || [
        {
            doctype: "Door Cutting Order Detail",
            name: "new-detail-1",
            __islocal: 1,
            width_cm: 90,
            length_cm: 210,
            qty: 1,
        },
    ];
}

async function startNewOrder(frm, values) {
    fakeWindow.cur_frm = frm;
    lastDialog = null;
    await Recovery.LocalCheckpoint.initializeNewForm(frm);
    if (lastDialog && typeof lastDialog.listener === "function") {
        const newButton = { disabled: false, dataset: { recoveryAction: "new" } };
        lastDialog.listener({ target: { closest: () => newButton } });
    }
    seedDraft(frm, values);
    assert.equal(Recovery.LocalCheckpoint.markDirty(frm, "DCO"), true);
    await Recovery.LocalCheckpoint.flush(frm);
    return Recovery.LocalCheckpoint.snapshot(frm);
}

function acknowledgeNativeInsert(frm, permanentName) {
    const draftId = String(frm.doc.recovery_creation_token || "").trim();
    frm.doc.name = permanentName;
    frm.doc.__islocal = 0;
    frm.doc.recovery_creation_token = draftId;
    frm.doc.modified = "2026-11-28 11:00:00.000000";
}

(async () => {
    alerts.length = 0;
    deleted.length = 0;
    records.clear();
    routes.length = 0;

    // T01 — offline typing keeps local checkpoints
    const typingForm = form("new-door-cutting-order-t01");
    const typingSnapshot = await startNewOrder(typingForm, { customer: "CUST-T01" });
    assert.equal(typingSnapshot.state, "LOCAL_SAVED");
    assert.equal(records.has(typingSnapshot.draft_id), true, "T01 local draft remains");

    // T02 / T07 — offline Save Promise resolves without creation proof; draft retained
    nativeSaveImpl = async (frm) => {
        // Mirror Frappe network failure: after_save may fire with no exc, Promise resolves,
        // and the document stays new.
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    await handlers["Door Cutting Order"].before_save(typingForm);
    await typingForm.save();
    assert.equal(records.has(typingSnapshot.draft_id), true, "T02 draft survives offline Save");
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(typingForm).state,
        "PENDING_RECONCILIATION",
        "T07 unresolved Promise success stays pending"
    );
    assert.ok(
        alerts.some((item) => String(item.message || "").includes("saved locally")),
        "T02 shows the local-only official-save message"
    );

    // T03 — reconnect Save retries without refresh
    nativeSaveImpl = null;
    reconciliationResult = { status: "NOT_FOUND" };
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(typingForm);
    assert.equal(fakeFrappe.validated, true, "T03 reconcile NOT_FOUND allows retry");
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(typingForm).official_save_state,
        "PENDING_RECONCILIATION",
        "T03 second attempt creates a fresh pending marker with the same draft id"
    );
    assert.equal(
        typingForm.doc.recovery_creation_token,
        typingSnapshot.draft_id,
        "T03 keeps the same creation token"
    );
    acknowledgeNativeInsert(typingForm, "DCO-2026-T03");
    await handlers["Door Cutting Order"].after_save(typingForm);
    await typingForm.save();
    assert.equal(records.has(typingSnapshot.draft_id), false, "T12 acknowledged success deletes draft");

    // T04 — offline Save then refresh restores the draft
    const refreshForm = form("new-door-cutting-order-t04");
    const refreshSnapshot = await startNewOrder(refreshForm, { customer: "CUST-T04" });
    nativeSaveImpl = async (frm) => {
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    await handlers["Door Cutting Order"].before_save(refreshForm);
    await refreshForm.save();
    assert.equal(records.has(refreshSnapshot.draft_id), true, "T04 draft retained after offline Save");
    const reopenForm = form("new-door-cutting-order-t04-reopen");
    fakeWindow.cur_frm = reopenForm;
    documentGeneration += 1;
    await Recovery.LocalCheckpoint.initializeNewForm(reopenForm);
    // Discovery dialog path: continue the retained pending draft through continueDraft.
    const retained = records.get(refreshSnapshot.draft_id);
    assert.equal(retained.official_save_state, "PENDING_RECONCILIATION");
    reconciliationResult = { status: "NOT_FOUND" };
    await Recovery.LocalCheckpoint.continueDraft(reopenForm, retained);
    assert.equal(reopenForm.doc.customer, "CUST-T04", "T04 restored customer");
    assert.equal(reopenForm.doc.pieces.length, 1, "T04 restored pieces");

    // T05 — additional edits after offline Save survive refresh
    const extraForm = form("new-door-cutting-order-t05");
    const extraSnapshot = await startNewOrder(extraForm, { customer: "CUST-T05" });
    nativeSaveImpl = async (frm) => {
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    await handlers["Door Cutting Order"].before_save(extraForm);
    await extraForm.save();
    extraForm.doc.pieces.push({
        doctype: "Door Cutting Order Detail",
        name: "new-detail-2",
        __islocal: 1,
        width_cm: 40,
        length_cm: 80,
        qty: 2,
    });
    extraForm.doc.customer = "CUST-T05-EXTRA";
    assert.equal(Recovery.LocalCheckpoint.markDirty(extraForm, "DCO"), true);
    await Recovery.LocalCheckpoint.flush(extraForm);
    const advanced = records.get(extraSnapshot.draft_id);
    assert.equal(advanced.official_save_state, "PENDING_RECONCILIATION");
    assert.equal(advanced.official_save_attempt_revision, extraSnapshot.recovery_revision);
    assert.ok(advanced.recovery_revision > extraSnapshot.recovery_revision);
    const reopenExtra = form("new-door-cutting-order-t05-reopen");
    fakeWindow.cur_frm = reopenExtra;
    documentGeneration += 1;
    reconciliationResult = { status: "NOT_FOUND" };
    await Recovery.LocalCheckpoint.continueDraft(reopenExtra, advanced);
    assert.equal(reopenExtra.doc.customer, "CUST-T05-EXTRA", "T05 restored later edits");
    assert.equal(reopenExtra.doc.pieces.length, 2, "T05 restored additional pieces");

    // T06 — validation failure keeps draft and returns ACTIVE
    const validationForm = form("new-door-cutting-order-t06");
    const validationSnapshot = await startNewOrder(validationForm, { customer: "CUST-T06" });
    nativeSaveImpl = async () => {
        const error = {
            status: 417,
            responseJSON: { exc_type: "ValidationError", exc: "ValidationError" },
            message: "validation failed",
        };
        throw error;
    };
    await handlers["Door Cutting Order"].before_save(validationForm);
    await assert.rejects(validationForm.save());
    assert.equal(records.has(validationSnapshot.draft_id), true, "T06 draft retained");
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(validationForm).official_save_state,
        "ACTIVE",
        "T06 definite validation returns ACTIVE"
    );

    // T08 — Promise rejection from network keeps draft and frees save state
    const rejectForm = form("new-door-cutting-order-t08");
    const rejectSnapshot = await startNewOrder(rejectForm, { customer: "CUST-T08" });
    nativeSaveImpl = async () => {
        throw { status: 0, message: "network lost" };
    };
    await handlers["Door Cutting Order"].before_save(rejectForm);
    await assert.rejects(rejectForm.save());
    assert.equal(records.has(rejectSnapshot.draft_id), true, "T08 draft retained");
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(rejectForm).state,
        "PENDING_RECONCILIATION",
        "T08 unknown transport stays pending"
    );

    // T09 — hung native Promise leaves draft durable; a later Save can reconcile
    const hangForm = form("new-door-cutting-order-t09");
    const hangSnapshot = await startNewOrder(hangForm, { customer: "CUST-T09" });
    let resolveHang;
    nativeSaveImpl = () => new Promise((resolve) => { resolveHang = resolve; });
    await handlers["Door Cutting Order"].before_save(hangForm);
    const hungSave = hangForm.save();
    assert.equal(records.get(hangSnapshot.draft_id).official_save_state, "PENDING_RECONCILIATION");
    reconciliationResult = { status: "NOT_FOUND" };
    fakeFrappe.validated = true;
    // Second explicit Save can still reconcile the pending marker without waiting forever.
    nativeSaveImpl = async (frm) => {
        acknowledgeNativeInsert(frm, "DCO-2026-T09");
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    await hangForm.save();
    assert.equal(records.has(hangSnapshot.draft_id), false, "T09 later acknowledged Save cleans draft");
    resolveHang(undefined);
    await hungSave;

    // T10 — lost HTTP response but server created the order
    const lostForm = form("new-door-cutting-order-t10");
    const lostSnapshot = await startNewOrder(lostForm, { customer: "CUST-T10" });
    nativeSaveImpl = async (frm) => {
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    await handlers["Door Cutting Order"].before_save(lostForm);
    await lostForm.save();
    assert.equal(records.has(lostSnapshot.draft_id), true);
    reconciliationResult = {
        status: "CREATED",
        door_cutting_order: "DCO-2026-T10",
        modified: "2026-11-28 11:10:00.000000",
    };
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(lostForm);
    assert.equal(fakeFrappe.validated, false, "T10 cancels duplicate insert");
    assert.equal(records.has(lostSnapshot.draft_id), false, "T10 CREATED cleans draft");
    assert.deepEqual(routes.at(-1), ["Form", "Door Cutting Order", "DCO-2026-T10"]);

    // T11 — first attempt still pending while retrying: NOT_FOUND is required before retry insert
    const concurrentForm = form("new-door-cutting-order-t11");
    const concurrentSnapshot = await startNewOrder(concurrentForm, { customer: "CUST-T11" });
    nativeSaveImpl = async (frm) => {
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    await handlers["Door Cutting Order"].before_save(concurrentForm);
    await concurrentForm.save();
    reconciliationFailure = new Error("still checking");
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(concurrentForm);
    assert.equal(fakeFrappe.validated, false, "T11 failed reconcile blocks unsafe retry");
    assert.equal(records.has(concurrentSnapshot.draft_id), true, "T11 draft retained");
    reconciliationFailure = null;

    // T13 — failed reconciliation retains draft on continue
    const failedRecord = structuredClone(records.get(concurrentSnapshot.draft_id));
    const failedForm = form("new-door-cutting-order-t13");
    failedForm.doc.customer = "UNCHANGED";
    reconciliationFailure = new Error("endpoint offline");
    await assert.rejects(Recovery.LocalCheckpoint.continueDraft(failedForm, failedRecord));
    assert.equal(failedForm.doc.customer, "UNCHANGED", "T13 no partial hydrate");
    assert.equal(records.has(concurrentSnapshot.draft_id), true, "T13 draft retained");
    reconciliationFailure = null;

    // T14 — newer local revision is not deleted by older attempt success
    const newerForm = form("new-door-cutting-order-t14");
    const newerSnapshot = await startNewOrder(newerForm, { customer: "CUST-T14" });
    nativeSaveImpl = async (frm) => {
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    await handlers["Door Cutting Order"].before_save(newerForm);
    await newerForm.save();
    newerForm.doc.customer = "CUST-T14-NEWER";
    assert.equal(Recovery.LocalCheckpoint.markDirty(newerForm, "DCO"), true);
    await Recovery.LocalCheckpoint.flush(newerForm);
    const attemptRevision = records.get(newerSnapshot.draft_id).official_save_attempt_revision;
    acknowledgeNativeInsert(newerForm, "DCO-2026-T14");
    await handlers["Door Cutting Order"].after_save(newerForm);
    assert.equal(records.has(newerSnapshot.draft_id), true, "T14 newer local revision retained");
    assert.ok(
        records.get(newerSnapshot.draft_id).recovery_revision > attemptRevision,
        "T14 keeps the advanced local revision"
    );

    // T15 — IndexedDB failure does not claim local protection
    alerts.length = 0;
    const storageForm = form("new-door-cutting-order-t15");
    writeFailure = { code: "quota_exceeded", message: "IndexedDB full" };
    fakeWindow.cur_frm = storageForm;
    lastDialog = null;
    await Recovery.LocalCheckpoint.initializeNewForm(storageForm);
    if (lastDialog && typeof lastDialog.listener === "function") {
        const newButton = { disabled: false, dataset: { recoveryAction: "new" } };
        lastDialog.listener({ target: { closest: () => newButton } });
    }
    seedDraft(storageForm, { customer: "CUST-T15" });
    assert.equal(Recovery.LocalCheckpoint.markDirty(storageForm, "DCO"), true);
    await Recovery.LocalCheckpoint.flush(storageForm);
    nativeSaveImpl = async (frm) => {
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    // Force an official-save attempt without a durable checkpoint marker when possible.
    await handlers["Door Cutting Order"].before_save(storageForm);
    await storageForm.save();
    writeFailure = null;
    assert.ok(
        alerts.some((item) => String(item.message || "").includes("could not be confirmed"))
            || Recovery.LocalCheckpoint.snapshot(storageForm) === null
            || Number(Recovery.LocalCheckpoint.snapshot(storageForm).saved_revision || 0) === 0,
        "T15 does not claim durable local protection after storage failure"
    );

    // T16 — navigating away does not mutate the replacement form
    const oldForm = form("new-door-cutting-order-t16-old");
    const oldSnapshot = await startNewOrder(oldForm, { customer: "CUST-T16" });
    nativeSaveImpl = () => new Promise(() => {});
    await handlers["Door Cutting Order"].before_save(oldForm);
    oldForm.save();
    const replacementForm = form("new-door-cutting-order-t16-new");
    documentGeneration += 1;
    const replacementSnapshot = await startNewOrder(replacementForm, { customer: "CUST-T16-OTHER" });
    const replacementId = replacementSnapshot.draft_id;
    assert.notEqual(replacementId, oldSnapshot.draft_id);
    assert.equal(records.has(oldSnapshot.draft_id), true, "T16 old draft untouched");
    assert.equal(records.has(replacementId), true, "T16 replacement draft independent");

    // T17 — two tabs: newer revision wins; unsafe overwrite blocked by CAS
    const tabA = form("new-door-cutting-order-t17-a");
    const tabSnapshot = await startNewOrder(tabA, { customer: "CUST-T17" });
    const tabB = form("new-door-cutting-order-t17-b");
    fakeWindow.cur_frm = tabB;
    await Recovery.LocalCheckpoint.continueDraft(tabB, records.get(tabSnapshot.draft_id));
    fakeWindow.cur_frm = tabA;
    tabA.doc.customer = "CUST-T17-A";
    assert.equal(Recovery.LocalCheckpoint.markDirty(tabA, "DCO"), true);
    await Recovery.LocalCheckpoint.flush(tabA);
    fakeWindow.cur_frm = tabB;
    tabB.doc.customer = "CUST-T17-B";
    assert.equal(Recovery.LocalCheckpoint.markDirty(tabB, "DCO"), true);
    await Recovery.LocalCheckpoint.flush(tabB);
    assert.equal(
        records.get(tabSnapshot.draft_id).payload.dco.customer,
        "CUST-T17-A",
        "T17 first writer keeps the durable revision when the second tab is stale"
    );

    // T18 — cleanup of one draft does not delete unrelated drafts
    const keepForm = form("new-door-cutting-order-t18-keep");
    const keepSnapshot = await startNewOrder(keepForm, { customer: "CUST-KEEP" });
    const cleanForm = form("new-door-cutting-order-t18-clean");
    documentGeneration += 1;
    const cleanSnapshot = await startNewOrder(cleanForm, { customer: "CUST-CLEAN" });
    nativeSaveImpl = async (frm) => {
        acknowledgeNativeInsert(frm, "DCO-2026-T18");
        await handlers["Door Cutting Order"].after_save(frm);
        return undefined;
    };
    await handlers["Door Cutting Order"].before_save(cleanForm);
    await cleanForm.save();
    assert.equal(records.has(cleanSnapshot.draft_id), false, "T18 related draft cleaned");
    assert.equal(records.has(keepSnapshot.draft_id), true, "T18 unrelated draft retained");

    console.log("DCO NEW offline Save regressions passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
