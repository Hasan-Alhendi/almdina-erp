"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const handlers = {};
const records = new Map();
const saveStates = [];
const deleted = [];
const routes = [];
const cleanupCallbacks = new WeakMap();
let uuidSequence = 0;
let reconciliationResult = { status: "NOT_FOUND" };
let reconciliationFailure = null;
let nativeSaveCalls = 0;
let nativeFailure = null;
let discoveredRecords = [];
let lastDialog = null;
let documentGeneration = 1;
let reconciliationDeferred = null;
let saveAttemptSequence = 0;
let writeDeferred = null;
let writeFailure = null;
let saveStateDeferred = null;
let saveStateEntered = null;
let pendingStateFailure = null;
let advanceRevisionOnRead = false;
let advanceRevisionBeforeActiveCas = false;
let nativeSaveDeferred = null;
let deleteDeferred = null;
let deleteEntered = null;

const repository = {
    createIdentity() {
        uuidSequence += 1;
        return `99999999-9999-4999-8999-${String(uuidSequence).padStart(12, "0")}`;
    },
    async discover() { return { ok: true, value: { records: discoveredRecords, rejected: [] } }; },
    async read(identity) {
        const current = records.get(identity.draft_id) || null;
        if (current && advanceRevisionOnRead) {
            advanceRevisionOnRead = false;
            const advanced = { ...current, recovery_revision: current.recovery_revision + 1 };
            records.set(identity.draft_id, advanced);
            return { ok: true, value: structuredClone(advanced) };
        }
        return { ok: true, value: current ? structuredClone(current) : null };
    },
    async write(input) {
        if (writeDeferred) await writeDeferred.promise;
        if (writeFailure) return { ok: false, error: structuredClone(writeFailure) };
        const current = records.get(input.draft_id) || null;
        const revision = Number(input.recovery_revision);
        const expectedRevision = Number(input.expected_recovery_revision);
        if (current && Number(current.recovery_revision) > revision) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        if (current && Number(current.recovery_revision) === revision) {
            const comparableFields = [
                "mode",
                "dirty_scope",
                "target_name",
                "session_origin_modified",
                "expected_server_modified",
                "tab_session_id",
                "recovery_revision",
                "payload",
                "asset_refs",
            ];
            const sameContent = comparableFields.every(
                (fieldname) => JSON.stringify(current[fieldname] ?? null)
                    === JSON.stringify(input[fieldname] ?? null)
            );
            return sameContent
                ? { ok: true, value: structuredClone(current) }
                : { ok: false, error: { code: "revision_conflict" } };
        }
        if (current && current.official_save_state === "PENDING_RECONCILIATION") {
            return { ok: false, error: { code: "save_attempt_conflict" } };
        }
        if (!current && expectedRevision !== 0) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        if (current && Number(current.recovery_revision) !== expectedRevision) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        const recordInput = structuredClone(input);
        delete recordInput.expected_recovery_revision;
        const next = {
            ...(current || {}),
            ...recordInput,
            official_save_state: input.official_save_state || (current && current.official_save_state) || "ACTIVE",
            created_at: (current && current.created_at) || "2026-08-29T09:00:00.000Z",
            captured_at: "2026-08-29T10:00:00.000Z",
        };
        records.set(input.draft_id, next);
        return { ok: true, value: next };
    },
    async setOfficialSaveState(identity, state, revision, expectedAttemptedAt) {
        let current = records.get(identity.draft_id);
        if (pendingStateFailure && state === "PENDING_RECONCILIATION") {
            const error = pendingStateFailure;
            pendingStateFailure = null;
            return { ok: false, error };
        }
        if (saveStateDeferred && state === "PENDING_RECONCILIATION") {
            if (saveStateEntered) saveStateEntered.resolve();
            await saveStateDeferred.promise;
        }
        if (!current) return { ok: false, error: { code: "draft_not_found" } };
        if (advanceRevisionBeforeActiveCas && state === "ACTIVE") {
            advanceRevisionBeforeActiveCas = false;
            current = { ...current, recovery_revision: current.recovery_revision + 1 };
            records.set(identity.draft_id, current);
        }
        if (Number(current.recovery_revision) !== Number(revision)) {
            return { ok: false, error: { code: "stale_revision" } };
        }
        const currentState = current.official_save_state || "ACTIVE";
        const currentAttempt = current.official_save_attempted_at || null;
        const requiredState = state === "PENDING_RECONCILIATION"
            ? "ACTIVE"
            : "PENDING_RECONCILIATION";
        if (currentState !== requiredState || currentAttempt !== expectedAttemptedAt) {
            return { ok: false, error: { code: "save_attempt_conflict" } };
        }
        saveAttemptSequence += state === "PENDING_RECONCILIATION" ? 1 : 0;
        const attemptedAt = state === "PENDING_RECONCILIATION"
            ? `2026-08-29T10:${String(saveAttemptSequence + 1).padStart(2, "0")}:00.000Z`
            : currentAttempt;
        const next = {
            ...current,
            official_save_state: state,
            official_save_attempted_at: attemptedAt,
        };
        records.set(identity.draft_id, next);
        saveStates.push({ draft_id: identity.draft_id, state, attempted_at: attemptedAt });
        return { ok: true, value: structuredClone(next) };
    },
    async delete(identity, expectedRevision = null, expectedAttemptedAt = undefined) {
        if (deleteDeferred) {
            if (deleteEntered) deleteEntered.resolve();
            await deleteDeferred.promise;
        }
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
                this.visible = false;
                this.$wrapper = {
                    get: () => ({ addEventListener: (name, callback) => { this.listener = callback; } }),
                };
                lastDialog = this;
            }
            show() { this.visible = true; }
            hide() { this.visible = false; }
        },
        form: {
            on(doctype, events) { handlers[doctype] = { ...(handlers[doctype] || {}), ...events }; },
        },
    },
    set_route(...args) { routes.push(args); },
    msgprint() {},
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
    Blob,
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
        if (reconciliationDeferred) return reconciliationDeferred.promise;
        if (reconciliationFailure) throw reconciliationFailure;
        return reconciliationResult;
    },
});
run("../../public/js/door_cutting_order/recovery/presentation/door_cutting_order_local_checkpoint.js");

const Recovery = fakeWindow.AlmdinaDcoRecovery;

function payload() {
    return Recovery.Projection.createPayload({
        dirtyScope: "DCO",
        dco: Recovery.Projection.createDcoInput({
            customer: "CUST-RECOVERED",
            board_description: "MDF",
            pieces: [{ name: "temp", width_cm: 40, length_cm: 70, qty: 2 }],
        }, { pieceKey: () => "piece-key-1" }),
    });
}

function draft(draftId, state = "ACTIVE") {
    const value = {
        schema_version: 2,
        site: "erp.example.test",
        user: "operator@example.test",
        target_doctype: "Door Cutting Order",
        draft_id: draftId,
        mode: "NEW",
        dirty_scope: "DCO",
        target_name: null,
        session_origin_modified: null,
        expected_server_modified: null,
        tab_session_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        recovery_revision: 2,
        created_at: "2026-08-29T09:00:00.000Z",
        captured_at: "2026-08-29T10:00:00.000Z",
        official_save_state: state,
        official_save_attempted_at: state === "PENDING_RECONCILIATION" ? "2026-08-29T10:01:00.000Z" : null,
        payload_hash: "hash",
        payload: payload(),
        asset_refs: [],
    };
    records.set(draftId, structuredClone(value));
    return value;
}

function form(name) {
    return {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name, __islocal: 1, pieces: [] },
        is_new() { return Boolean(this.doc.__islocal); },
        refresh_fields() {},
        refresh_field() {},
        dirty() {},
        save() {
            nativeSaveCalls += 1;
            if (nativeSaveDeferred) return nativeSaveDeferred.promise;
            return nativeFailure ? Promise.reject(nativeFailure) : Promise.resolve();
        },
    };
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

function runCleanups(frm) {
    const callbacks = cleanupCallbacks.get(frm) || new Map();
    callbacks.forEach((callback) => callback());
    cleanupCallbacks.delete(frm);
}

(async () => {
    const choiceA = draft("44444444-4444-4444-8444-444444444444");
    const choiceB = draft("55555555-5555-4555-8555-555555555555");
    discoveredRecords = [choiceA, choiceB];
    const startNewForm = form("new-door-cutting-order-discovery");
    await Recovery.LocalCheckpoint.initializeNewForm(startNewForm);
    const html = lastDialog.options.fields[0].options;
    assert.match(html, /مسودة محلية غير محفوظة رسميًا/);
    assert.match(html, /متابعة الطلب/);
    assert.match(html, /بدء طلب جديد/);
    assert.match(html, /حذف المسودة/);
    assert.match(html, /44444444-4444-4444-8444-444444444444/);
    assert.match(html, /55555555-5555-4555-8555-555555555555/);
    const newButton = { disabled: false, dataset: { recoveryAction: "new" } };
    lastDialog.listener({ target: { closest: () => newButton } });
    assert.equal(records.has(choiceA.draft_id), true);
    assert.equal(records.has(choiceB.draft_id), true, "Start New never deletes unfinished drafts");
    assert.notEqual(Recovery.LocalCheckpoint.snapshot(startNewForm).draft_id, choiceA.draft_id);

    discoveredRecords = [];
    const pristineForm = form("new-door-cutting-order-pristine-save");
    await Recovery.LocalCheckpoint.initializeNewForm(pristineForm);
    const pristineId = Recovery.LocalCheckpoint.snapshot(pristineForm).draft_id;
    await handlers["Door Cutting Order"].before_save(pristineForm);
    assert.equal(
        records.get(pristineId).official_save_state,
        "PENDING_RECONCILIATION",
        "first Save durably records its creation identity even before the first field mutation"
    );

    const deleteId = "66666666-6666-4666-8666-666666666666";
    const deleteRecord = draft(deleteId);
    discoveredRecords = [deleteRecord];
    const deleteForm = form("new-door-cutting-order-delete");
    await Recovery.LocalCheckpoint.initializeNewForm(deleteForm);
    let cardRemoved = false;
    let deleteCardActions = [];
    const card = {
        dataset: { draftId: deleteId },
        querySelectorAll: () => deleteCardActions,
        remove() { cardRemoved = true; },
    };
    const deleteButton = {
        disabled: false,
        dataset: { recoveryAction: "delete" },
        closest: () => card,
    };
    const deleteSiblingButton = { disabled: false };
    deleteCardActions = [deleteButton, deleteSiblingButton];
    lastDialog.listener({ target: { closest: () => deleteButton } });
    assert.equal(deleteSiblingButton.disabled, true, "Delete locks every action on its card");
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(cardRemoved, true);
    assert.equal(records.has(deleteId), false, "explicit deletion removes only the selected draft");

    const staleDeleteId = "67676767-6767-4767-8767-676767676767";
    const staleDeleteRecord = draft(staleDeleteId);
    discoveredRecords = [staleDeleteRecord];
    const staleDeleteForm = form("new-door-cutting-order-stale-delete");
    await Recovery.LocalCheckpoint.initializeNewForm(staleDeleteForm);
    records.set(staleDeleteId, {
        ...records.get(staleDeleteId),
        recovery_revision: staleDeleteRecord.recovery_revision + 1,
        official_save_state: "PENDING_RECONCILIATION",
        official_save_attempted_at: "2026-08-29T10:47:00.000Z",
    });
    let staleCardRemoved = false;
    const staleCard = {
        dataset: { draftId: staleDeleteId },
        remove() { staleCardRemoved = true; },
    };
    const staleDeleteButton = {
        disabled: false,
        dataset: { recoveryAction: "delete" },
        closest: () => staleCard,
    };
    lastDialog.listener({ target: { closest: () => staleDeleteButton } });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(staleCardRemoved, false);
    assert.equal(
        records.get(staleDeleteId).official_save_state,
        "PENDING_RECONCILIATION",
        "a stale discovery dialog cannot delete a newer pending attempt"
    );
    assert.equal(staleDeleteButton.disabled, true, "stale Delete stays disabled until reopen");
    staleDeleteButton.disabled = false;
    lastDialog.listener({ target: { closest: () => staleDeleteButton } });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(
        records.get(staleDeleteId).official_save_state,
        "PENDING_RECONCILIATION",
        "even a forced second click cannot adopt and delete the unseen revision"
    );

    const staleContinueId = "68686868-6868-4868-8868-686868686868";
    const staleContinueRecord = draft(staleContinueId);
    discoveredRecords = [staleContinueRecord];
    const staleContinueForm = form("new-door-cutting-order-stale-continue");
    fakeWindow.cur_frm = staleContinueForm;
    await Recovery.LocalCheckpoint.initializeNewForm(staleContinueForm);
    records.set(staleContinueId, {
        ...records.get(staleContinueId),
        recovery_revision: staleContinueRecord.recovery_revision + 1,
        official_save_state: "PENDING_RECONCILIATION",
        official_save_attempted_at: "2026-08-29T10:48:00.000Z",
    });
    let staleContinueActions = [];
    const staleContinueCard = {
        dataset: { draftId: staleContinueId },
        querySelectorAll: () => staleContinueActions,
    };
    const staleContinueButton = {
        disabled: false,
        dataset: { recoveryAction: "continue" },
        closest: () => staleContinueCard,
    };
    const staleContinueDelete = { disabled: false };
    staleContinueActions = [staleContinueButton, staleContinueDelete];
    lastDialog.listener({ target: { closest: () => staleContinueButton } });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(Recovery.LocalCheckpoint.snapshot(staleContinueForm), null);
    assert.equal(staleContinueButton.disabled, true);
    assert.equal(staleContinueDelete.disabled, true);
    assert.equal(
        records.get(staleContinueId).official_save_attempted_at,
        "2026-08-29T10:48:00.000Z",
        "Continue never hydrates the stale displayed revision"
    );

    const lockedContinueId = "69696969-6969-4969-8969-696969696969";
    const lockedContinueRecord = draft(lockedContinueId, "PENDING_RECONCILIATION");
    discoveredRecords = [lockedContinueRecord];
    const lockedContinueForm = form("new-door-cutting-order-locked-continue");
    fakeWindow.cur_frm = lockedContinueForm;
    await Recovery.LocalCheckpoint.initializeNewForm(lockedContinueForm);
    reconciliationDeferred = deferred();
    let lockedActions = [];
    const lockedCard = {
        dataset: { draftId: lockedContinueId },
        querySelectorAll: () => lockedActions,
    };
    const lockedContinueButton = {
        disabled: false,
        dataset: { recoveryAction: "continue" },
        closest: () => lockedCard,
    };
    const lockedDeleteButton = {
        disabled: false,
        dataset: { recoveryAction: "delete" },
        closest: () => lockedCard,
    };
    lockedActions = [lockedContinueButton, lockedDeleteButton];
    lastDialog.listener({ target: { closest: () => lockedContinueButton } });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(lockedContinueButton.disabled, true);
    assert.equal(lockedDeleteButton.disabled, true, "Continue locks Delete while reconciliation is in flight");
    lastDialog.listener({ target: { closest: () => lockedDeleteButton } });
    assert.equal(records.has(lockedContinueId), true);
    reconciliationDeferred.resolve({ status: "NOT_FOUND" });
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
    reconciliationDeferred = null;

    discoveredRecords = [];
    const activeId = "11111111-1111-4111-8111-111111111111";
    const activeRecord = draft(activeId);
    const validationForm = form("new-door-cutting-order-validation");
    fakeWindow.cur_frm = validationForm;
    await Recovery.LocalCheckpoint.continueDraft(validationForm, activeRecord);
    assert.equal(Recovery.LocalCheckpoint.snapshot(validationForm).draft_id, activeId);
    assert.equal(validationForm.doc.recovery_creation_token, activeId);

    await handlers["Door Cutting Order"].before_save(validationForm);
    assert.equal(saveStates.at(-1).state, "PENDING_RECONCILIATION");
    assert.equal(Recovery.LocalCheckpoint.snapshot(validationForm).state, "OFFICIAL_SAVING");
    const firstAttempt = Recovery.LocalCheckpoint.snapshot(validationForm).official_save_attempted_at;
    assert.match(firstAttempt, /^2026-08-29T/);
    nativeFailure = { status: 417, responseJSON: { exc_type: "ValidationError" }, message: "validation failed" };
    await assert.rejects(validationForm.save());
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(validationForm).official_save_state,
        "ACTIVE",
        "a definite server validation failure returns the draft to ACTIVE"
    );
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(validationForm).official_save_attempted_at,
        firstAttempt,
        "server-proven failure retains the reconciled attempt fence"
    );
    assert.equal(records.has(activeId), true, "validation failure never deletes the draft");

    nativeFailure = null;
    await handlers["Door Cutting Order"].before_save(validationForm);
    nativeFailure = { status: 0, message: "network lost" };
    await assert.rejects(validationForm.save());
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(validationForm).state,
        "PENDING_RECONCILIATION",
        "unknown transport outcome remains pending"
    );
    assert.equal(records.has(activeId), true, "unknown outcome never deletes the draft");

    reconciliationResult = {
        status: "CREATED",
        door_cutting_order: "DCO-2026-00421",
        modified: "2026-08-29 11:00:00.000000",
    };
    fakeFrappe.validated = true;
    const callsBeforeReconcile = nativeSaveCalls;
    await handlers["Door Cutting Order"].before_save(validationForm);
    assert.equal(fakeFrappe.validated, false, "reconciled success cancels a duplicate native insert");
    assert.equal(nativeSaveCalls, callsBeforeReconcile);
    assert.equal(records.has(activeId), false);
    assert.deepEqual(routes.at(-1), ["Form", "Door Cutting Order", "DCO-2026-00421"]);

    const pendingId = "22222222-2222-4222-8222-222222222222";
    const pendingRecord = draft(pendingId, "PENDING_RECONCILIATION");
    const retryForm = form("new-door-cutting-order-retry");
    reconciliationResult = { status: "NOT_FOUND" };
    fakeWindow.cur_frm = retryForm;
    await Recovery.LocalCheckpoint.continueDraft(retryForm, pendingRecord);
    assert.equal(records.get(pendingId).official_save_state, "ACTIVE");
    assert.equal(retryForm.doc.customer, "CUST-RECOVERED");
    assert.equal(retryForm.doc.pieces.length, 1);
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(retryForm).draft_id,
        pendingId,
        "server-proven absence resumes with the same creation identity"
    );

    await handlers["Door Cutting Order"].before_save(retryForm);
    retryForm.doc.name = "DCO-2026-00422";
    retryForm.doc.__islocal = 0;
    retryForm.doc.modified = "2026-08-29 11:05:00.000000";
    await handlers["Door Cutting Order"].after_save(retryForm);
    assert.equal(records.has(pendingId), false, "acknowledged success cleans up after binding");
    assert.equal(Recovery.LocalCheckpoint.snapshot(retryForm), null);

    const failOpenId = "23232323-2323-4232-8232-232323232323";
    const failOpenRecord = draft(failOpenId);
    failOpenRecord.official_save_attempted_at = "2026-08-29T10:44:00.000Z";
    records.set(failOpenId, structuredClone(failOpenRecord));
    const failOpenForm = form("new-door-cutting-order-marker-failure");
    failOpenForm.save = async function saveAfterRecoveryHook() {
        await handlers["Door Cutting Order"].before_save(this);
        nativeSaveCalls += 1;
    };
    fakeWindow.cur_frm = failOpenForm;
    await Recovery.LocalCheckpoint.continueDraft(failOpenForm, failOpenRecord);
    pendingStateFailure = { code: "quota_exceeded", message: "marker storage failed" };
    await failOpenForm.save();
    assert.equal(
        records.has(failOpenId),
        false,
        "fail-open acknowledged insert cleans against the retained pre-attempt fence"
    );

    const validationFailOpenId = "25252525-2525-4252-8252-252525252525";
    const validationFailOpenRecord = draft(validationFailOpenId);
    validationFailOpenRecord.official_save_attempted_at = "2026-08-29T10:46:00.000Z";
    records.set(validationFailOpenId, structuredClone(validationFailOpenRecord));
    const validationFailOpenForm = form("new-door-cutting-order-marker-validation-failure");
    validationFailOpenForm.save = async function saveAfterRecoveryHook() {
        await handlers["Door Cutting Order"].before_save(this);
        nativeSaveCalls += 1;
        if (nativeFailure) throw nativeFailure;
    };
    fakeWindow.cur_frm = validationFailOpenForm;
    await Recovery.LocalCheckpoint.continueDraft(
        validationFailOpenForm,
        validationFailOpenRecord
    );
    pendingStateFailure = { code: "quota_exceeded", message: "marker storage failed" };
    nativeFailure = {
        status: 417,
        responseJSON: { exc_type: "ValidationError" },
        message: "validation failed after marker storage failure",
    };
    await assert.rejects(validationFailOpenForm.save());
    assert.equal(records.get(validationFailOpenId).official_save_state, "ACTIVE");
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(validationFailOpenForm).official_save_state,
        "ACTIVE",
        "a retained cleanup fence does not claim durable pending-attempt ownership"
    );
    nativeFailure = null;
    await validationFailOpenForm.save();
    assert.equal(
        records.has(validationFailOpenId),
        false,
        "the next explicit Save can create its own marker and clean up"
    );

    const checkpointFailOpenId = "24242424-2424-4242-8242-242424242424";
    const checkpointFailOpenRecord = draft(checkpointFailOpenId);
    checkpointFailOpenRecord.official_save_attempted_at = "2026-08-29T10:45:00.000Z";
    records.set(checkpointFailOpenId, structuredClone(checkpointFailOpenRecord));
    const checkpointFailOpenForm = form("new-door-cutting-order-checkpoint-failure");
    checkpointFailOpenForm.save = async function saveAfterRecoveryHook() {
        await handlers["Door Cutting Order"].before_save(this);
        nativeSaveCalls += 1;
    };
    fakeWindow.cur_frm = checkpointFailOpenForm;
    await Recovery.LocalCheckpoint.continueDraft(
        checkpointFailOpenForm,
        checkpointFailOpenRecord
    );
    writeFailure = { code: "quota_exceeded", message: "checkpoint storage failed" };
    Recovery.LocalCheckpoint.markDirty(checkpointFailOpenForm, "DCO");
    await checkpointFailOpenForm.save();
    writeFailure = null;
    assert.equal(
        records.has(checkpointFailOpenId),
        false,
        "fail-open cleanup uses saved_revision when the in-memory revision was not persisted"
    );

    const failedReconcileId = "33333333-3333-4333-8333-333333333333";
    const failedRecord = draft(failedReconcileId, "PENDING_RECONCILIATION");
    const untouchedForm = form("new-door-cutting-order-offline");
    untouchedForm.doc.customer = "UNCHANGED";
    reconciliationFailure = new Error("endpoint offline");
    await assert.rejects(Recovery.LocalCheckpoint.continueDraft(untouchedForm, failedRecord));
    assert.equal(untouchedForm.doc.customer, "UNCHANGED");
    assert.equal(untouchedForm.doc.pieces.length, 0, "failed reconciliation never partially hydrates");
    assert.equal(records.has(failedReconcileId), true);

    const lateCreatedId = "88888888-8888-4888-8888-888888888888";
    const lateCreatedRecord = draft(lateCreatedId, "PENDING_RECONCILIATION");
    const departedCreatedForm = form("new-door-cutting-order-departed-created");
    fakeWindow.cur_frm = departedCreatedForm;
    const routesBeforeDeparture = routes.length;
    reconciliationDeferred = deferred();
    const lateCreatedContinuation = Recovery.LocalCheckpoint.continueDraft(
        departedCreatedForm,
        lateCreatedRecord
    );
    fakeWindow.cur_frm = form("new-door-cutting-order-other-route");
    reconciliationDeferred.resolve({
        status: "CREATED",
        door_cutting_order: "DCO-2026-00901",
        modified: "2026-08-29 12:00:00.000000",
    });
    assert.equal((await lateCreatedContinuation).cancelled, true);
    assert.equal(routes.length, routesBeforeDeparture, "late CREATED cannot route a departed form");
    assert.equal(records.has(lateCreatedId), true, "navigation retains pending recovery state");

    const lateMissingId = "99999999-9999-4999-8999-999999999999";
    const lateMissingRecord = draft(lateMissingId, "PENDING_RECONCILIATION");
    const departedMissingForm = form("new-door-cutting-order-departed-missing");
    fakeWindow.cur_frm = departedMissingForm;
    departedMissingForm.doc.customer = "UNCHANGED-AFTER-NAVIGATION";
    reconciliationDeferred = deferred();
    const lateMissingContinuation = Recovery.LocalCheckpoint.continueDraft(
        departedMissingForm,
        lateMissingRecord
    );
    fakeWindow.cur_frm = form("new-door-cutting-order-another-route");
    reconciliationDeferred.resolve({ status: "NOT_FOUND" });
    assert.equal((await lateMissingContinuation).cancelled, true);
    assert.equal(departedMissingForm.doc.customer, "UNCHANGED-AFTER-NAVIGATION");
    assert.equal(departedMissingForm.doc.pieces.length, 0, "late NOT_FOUND cannot hydrate a departed form");
    assert.equal(records.get(lateMissingId).official_save_state, "PENDING_RECONCILIATION");
    reconciliationDeferred = null;

    const saveDepartureId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const saveDepartureRecord = draft(saveDepartureId);
    const departedSaveForm = form("new-door-cutting-order-departed-save");
    fakeWindow.cur_frm = departedSaveForm;
    await Recovery.LocalCheckpoint.continueDraft(departedSaveForm, saveDepartureRecord);
    await handlers["Door Cutting Order"].before_save(departedSaveForm);
    reconciliationDeferred = deferred();
    fakeFrappe.validated = true;
    const routesBeforeSaveDeparture = routes.length;
    const deletesBeforeSaveDeparture = deleted.length;
    const lateSaveReconciliation = handlers["Door Cutting Order"].before_save(departedSaveForm);
    fakeWindow.cur_frm = form("new-door-cutting-order-save-other-route");
    reconciliationDeferred.resolve({
        status: "CREATED",
        door_cutting_order: "DCO-2026-00902",
        modified: "2026-08-29 12:05:00.000000",
    });
    await assert.rejects(
        lateSaveReconciliation,
        (error) => error.code === "recovery_document_inactive"
    );
    assert.equal(fakeFrappe.validated, true, "late Save reconciliation cannot change global validation");
    assert.equal(routes.length, routesBeforeSaveDeparture, "late Save reconciliation cannot route");
    assert.equal(deleted.length, deletesBeforeSaveDeparture, "late Save reconciliation cannot clean a departed form");
    assert.equal(records.has(saveDepartureId), true);
    reconciliationDeferred = null;

    const flushDepartureId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
    const flushDepartureRecord = draft(flushDepartureId);
    const departedFlushForm = form("new-door-cutting-order-departed-flush");
    departedFlushForm.save = async function saveAfterRecoveryHook() {
        await handlers["Door Cutting Order"].before_save(this);
        nativeSaveCalls += 1;
    };
    fakeWindow.cur_frm = departedFlushForm;
    await Recovery.LocalCheckpoint.continueDraft(departedFlushForm, flushDepartureRecord);
    writeDeferred = deferred();
    Recovery.LocalCheckpoint.markDirty(departedFlushForm, "DCO");
    const lateFlushSave = departedFlushForm.save();
    fakeWindow.cur_frm = form("new-door-cutting-order-flush-other-route");
    records.set(flushDepartureId, {
        ...records.get(flushDepartureId),
        official_save_state: "PENDING_RECONCILIATION",
        official_save_attempted_at: "2026-08-29T10:58:00.000Z",
    });
    writeDeferred.resolve();
    await assert.rejects(
        lateFlushSave,
        (error) => error.code === "recovery_document_inactive"
    );
    assert.equal(
        records.get(flushDepartureId).official_save_state,
        "PENDING_RECONCILIATION",
        "cancelling this tab cannot clear a pending attempt adopted from another tab"
    );
    assert.equal(records.get(flushDepartureId).official_save_attempted_at, "2026-08-29T10:58:00.000Z");
    writeDeferred = null;

    const disposedSaveId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
    const disposedSaveRecord = draft(disposedSaveId);
    const disposedSaveForm = form("new-door-cutting-order-disposed-save");
    disposedSaveForm.save = async function saveAfterRecoveryHook() {
        await handlers["Door Cutting Order"].before_save(this);
        nativeSaveCalls += 1;
    };
    fakeWindow.cur_frm = disposedSaveForm;
    await Recovery.LocalCheckpoint.continueDraft(disposedSaveForm, disposedSaveRecord);
    saveStateDeferred = deferred();
    saveStateEntered = deferred();
    const disposedSave = disposedSaveForm.save();
    await saveStateEntered.promise;
    fakeWindow.cur_frm = form("new-door-cutting-order-disposed-other-route");
    runCleanups(disposedSaveForm);
    advanceRevisionOnRead = true;
    advanceRevisionBeforeActiveCas = true;
    saveStateDeferred.resolve();
    await assert.rejects(
        disposedSave,
        (error) => error.code === "recovery_document_inactive"
    );
    assert.equal(
        records.get(disposedSaveId).official_save_state,
        "ACTIVE",
        "the originating attempt is cleared even after its session is disposed"
    );
    assert.equal(
        records.get(disposedSaveId).recovery_revision,
        disposedSaveRecord.recovery_revision + 2,
        "cancellation CAS re-reads and retries when a later checkpoint wins after the first read"
    );
    assert.equal(Recovery.LocalCheckpoint.snapshot(disposedSaveForm), null);
    saveStateDeferred = null;
    saveStateEntered = null;

    const reusedFormId = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
    const reusedFormRecord = draft(reusedFormId);
    const reusedForm = form("new-door-cutting-order-reused-old");
    fakeWindow.cur_frm = reusedForm;
    await Recovery.LocalCheckpoint.continueDraft(reusedForm, reusedFormRecord);
    await handlers["Door Cutting Order"].before_save(reusedForm);
    const oldAttempt = records.get(reusedFormId).official_save_attempted_at;
    nativeSaveDeferred = deferred();
    const oldNativeSave = reusedForm.save();
    runCleanups(reusedForm);
    documentGeneration += 1;
    reusedForm.doc = {
        doctype: "Door Cutting Order",
        name: "new-door-cutting-order-reused-new",
        __islocal: 1,
        pieces: [],
    };
    discoveredRecords = [];
    await Recovery.LocalCheckpoint.initializeNewForm(reusedForm);
    const replacementId = Recovery.LocalCheckpoint.snapshot(reusedForm).draft_id;
    await handlers["Door Cutting Order"].before_save(reusedForm);
    const replacementAttempt = records.get(replacementId).official_save_attempted_at;
    nativeSaveDeferred.reject({
        status: 417,
        responseJSON: { exc_type: "ValidationError" },
        message: "old validation failed",
    });
    await assert.rejects(oldNativeSave);
    assert.equal(records.get(reusedFormId).official_save_state, "ACTIVE");
    assert.equal(records.get(reusedFormId).official_save_attempted_at, oldAttempt);
    assert.equal(records.get(replacementId).official_save_state, "PENDING_RECONCILIATION");
    assert.equal(
        records.get(replacementId).official_save_attempted_at,
        replacementAttempt,
        "a late native failure can clear only its originating document and attempt"
    );
    nativeSaveDeferred = null;

    const liveSyncId = "12121212-1212-4212-8212-121212121212";
    const liveSyncRecord = draft(liveSyncId);
    const liveSyncForm = form("new-door-cutting-order-live-sync");
    fakeWindow.cur_frm = liveSyncForm;
    await Recovery.LocalCheckpoint.continueDraft(liveSyncForm, liveSyncRecord);
    await handlers["Door Cutting Order"].before_save(liveSyncForm);
    records.set(liveSyncId, {
        ...records.get(liveSyncId),
        recovery_revision: liveSyncRecord.recovery_revision + 1,
    });
    nativeFailure = {
        status: 417,
        responseJSON: { exc_type: "ValidationError" },
        message: "validation failed after another checkpoint",
    };
    await assert.rejects(liveSyncForm.save());
    assert.equal(records.get(liveSyncId).official_save_state, "ACTIVE");
    assert.equal(Recovery.LocalCheckpoint.snapshot(liveSyncForm).recovery_revision, liveSyncRecord.recovery_revision);
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(liveSyncForm);
    assert.equal(
        fakeFrappe.validated,
        false,
        "a divergent higher-revision payload is quarantined until the draft is reopened and hydrated"
    );
    assert.equal(records.get(liveSyncId).recovery_revision, liveSyncRecord.recovery_revision + 1);
    nativeFailure = null;

    const reusedSuccessId = "13131313-1313-4313-8313-131313131313";
    const reusedSuccessRecord = draft(reusedSuccessId);
    const reusedSuccessForm = form("new-door-cutting-order-reused-success-old");
    fakeWindow.cur_frm = reusedSuccessForm;
    await Recovery.LocalCheckpoint.continueDraft(reusedSuccessForm, reusedSuccessRecord);
    await handlers["Door Cutting Order"].before_save(reusedSuccessForm);
    nativeSaveDeferred = deferred();
    const oldSuccessfulSave = reusedSuccessForm.save();
    runCleanups(reusedSuccessForm);
    documentGeneration += 1;
    reusedSuccessForm.doc = {
        doctype: "Door Cutting Order",
        name: "new-door-cutting-order-reused-success-new",
        __islocal: 1,
        pieces: [],
    };
    await Recovery.LocalCheckpoint.initializeNewForm(reusedSuccessForm);
    const replacementSuccessId = Recovery.LocalCheckpoint.snapshot(reusedSuccessForm).draft_id;
    await handlers["Door Cutting Order"].before_save(reusedSuccessForm);
    const replacementSuccessAttempt = records.get(replacementSuccessId).official_save_attempted_at;
    await handlers["Door Cutting Order"].after_save(reusedSuccessForm);
    nativeSaveDeferred.resolve();
    await oldSuccessfulSave;
    assert.equal(records.has(reusedSuccessId), false, "old success cleans only its originating draft");
    assert.equal(records.get(replacementSuccessId).official_save_state, "PENDING_RECONCILIATION");
    assert.equal(records.get(replacementSuccessId).official_save_attempted_at, replacementSuccessAttempt);
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(reusedSuccessForm).draft_id,
        replacementSuccessId,
        "old success cannot dispose the replacement document session"
    );
    nativeSaveDeferred = null;

    const cleanupRaceId = "14141414-1414-4414-8414-141414141414";
    const cleanupRaceRecord = draft(cleanupRaceId);
    const cleanupRaceForm = form("new-door-cutting-order-cleanup-race-old");
    fakeWindow.cur_frm = cleanupRaceForm;
    await Recovery.LocalCheckpoint.continueDraft(cleanupRaceForm, cleanupRaceRecord);
    await handlers["Door Cutting Order"].before_save(cleanupRaceForm);
    nativeSaveDeferred = deferred();
    const cleanupRaceSave = cleanupRaceForm.save();
    deleteDeferred = deferred();
    deleteEntered = deferred();
    nativeSaveDeferred.resolve();
    await deleteEntered.promise;
    runCleanups(cleanupRaceForm);
    documentGeneration += 1;
    cleanupRaceForm.doc = {
        doctype: "Door Cutting Order",
        name: "new-door-cutting-order-cleanup-race-new",
        __islocal: 1,
        pieces: [],
    };
    cleanupRaceForm.save = async function saveWithRecoveryLifecycle() {
        await handlers["Door Cutting Order"].before_save(this);
        nativeSaveCalls += 1;
        if (nativeFailure) throw nativeFailure;
    };
    await Recovery.LocalCheckpoint.initializeNewForm(cleanupRaceForm);
    const cleanupReplacementId = Recovery.LocalCheckpoint.snapshot(cleanupRaceForm).draft_id;
    deleteDeferred.resolve();
    await cleanupRaceSave;
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(cleanupRaceForm).draft_id,
        cleanupReplacementId,
        "cleanup rechecks ownership after asynchronous deletion"
    );
    nativeSaveDeferred = null;
    deleteDeferred = null;
    deleteEntered = null;
    nativeFailure = {
        status: 417,
        responseJSON: { exc_type: "ValidationError" },
        message: "replacement validation failed",
    };
    await assert.rejects(cleanupRaceForm.save());
    assert.equal(
        records.get(cleanupReplacementId).official_save_state,
        "ACTIVE",
        "the replacement observer retains its operation registry after the old operation settles"
    );
    nativeFailure = null;

    const staleRevisionId = "ffffffff-ffff-4fff-8fff-ffffffffffff";
    const staleRevisionRecord = draft(staleRevisionId);
    const staleRevisionForm = form("new-door-cutting-order-stale-revision");
    fakeWindow.cur_frm = staleRevisionForm;
    await Recovery.LocalCheckpoint.continueDraft(staleRevisionForm, staleRevisionRecord);
    records.set(staleRevisionId, {
        ...records.get(staleRevisionId),
        recovery_revision: staleRevisionRecord.recovery_revision + 1,
    });
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(staleRevisionForm);
    assert.equal(fakeFrappe.validated, false, "a stale-revision tab cannot start native insert");
    assert.equal(records.get(staleRevisionId).official_save_state, "ACTIVE");
    assert.equal(records.get(staleRevisionId).recovery_revision, staleRevisionRecord.recovery_revision + 1);
    assert.equal(
        Recovery.LocalCheckpoint.markDirty(staleRevisionForm, "DCO"),
        false,
        "the stale tab remains quarantined after the rejected Save"
    );
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(staleRevisionForm);
    assert.equal(fakeFrappe.validated, false);
    assert.equal(records.get(staleRevisionId).recovery_revision, staleRevisionRecord.recovery_revision + 1);

    const backgroundConflictId = "abababab-abab-4bab-8bab-abababababab";
    const backgroundConflictRecord = draft(backgroundConflictId);
    const backgroundConflictForm = form("new-door-cutting-order-background-conflict");
    fakeWindow.cur_frm = backgroundConflictForm;
    await Recovery.LocalCheckpoint.continueDraft(backgroundConflictForm, backgroundConflictRecord);
    records.set(backgroundConflictId, {
        ...records.get(backgroundConflictId),
        recovery_revision: backgroundConflictRecord.recovery_revision + 1,
    });
    assert.equal(Recovery.LocalCheckpoint.markDirty(backgroundConflictForm, "DCO"), true);
    assert.equal(Recovery.LocalCheckpoint.markDirty(backgroundConflictForm, "DCO"), true);
    assert.equal(Recovery.LocalCheckpoint.markDirty(backgroundConflictForm, "DCO"), true);
    await Recovery.LocalCheckpoint.flush(backgroundConflictForm);
    assert.equal(
        records.get(backgroundConflictId).recovery_revision,
        backgroundConflictRecord.recovery_revision + 1,
        "a stale tab cannot leapfrog a newer persisted base by batching local mutations"
    );
    assert.equal(
        Recovery.LocalCheckpoint.markDirty(backgroundConflictForm, "DCO"),
        false,
        "a background flush conflict quarantines later local mutations"
    );
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(backgroundConflictForm);
    assert.equal(fakeFrappe.validated, false, "a background-conflicted tab cannot start native insert");
    assert.equal(
        records.get(backgroundConflictId).recovery_revision,
        backgroundConflictRecord.recovery_revision + 1
    );

    const cleanupFenceId = "acacacac-acac-4cac-8cac-acacacacacac";
    const cleanupFenceRecord = draft(cleanupFenceId);
    const cleanupOwnerForm = form("new-door-cutting-order-cleanup-owner");
    const cleanupStaleForm = form("new-door-cutting-order-cleanup-stale-tab");
    fakeWindow.cur_frm = cleanupOwnerForm;
    await Recovery.LocalCheckpoint.continueDraft(cleanupOwnerForm, cleanupFenceRecord);
    fakeWindow.cur_frm = cleanupStaleForm;
    await Recovery.LocalCheckpoint.continueDraft(cleanupStaleForm, cleanupFenceRecord);
    fakeWindow.cur_frm = cleanupOwnerForm;
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(cleanupOwnerForm);
    const cleanupAttempt = records.get(cleanupFenceId).official_save_attempted_at;
    assert.equal(records.get(cleanupFenceId).recovery_revision, cleanupFenceRecord.recovery_revision);
    fakeWindow.cur_frm = cleanupStaleForm;
    assert.equal(Recovery.LocalCheckpoint.markDirty(cleanupStaleForm, "DCO"), true);
    await Recovery.LocalCheckpoint.flush(cleanupStaleForm);
    assert.equal(
        records.get(cleanupFenceId).recovery_revision,
        cleanupFenceRecord.recovery_revision,
        "a pending insert fences out a stale tab's higher checkpoint"
    );
    assert.equal(
        Recovery.LocalCheckpoint.markDirty(cleanupStaleForm, "DCO"),
        false,
        "the rejected post-attempt checkpoint quarantines the stale tab"
    );
    records.set(cleanupFenceId, {
        ...records.get(cleanupFenceId),
        recovery_revision: cleanupFenceRecord.recovery_revision + 1,
        official_save_attempted_at: cleanupAttempt,
    });
    fakeWindow.cur_frm = cleanupOwnerForm;
    await cleanupOwnerForm.save();
    assert.equal(records.has(cleanupFenceId), true);
    assert.equal(
        records.get(cleanupFenceId).recovery_revision,
        cleanupFenceRecord.recovery_revision + 1,
        "acknowledged revision-R success cannot delete a raced revision R+1 checkpoint"
    );

    const staleTabId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    const staleTabRecord = draft(staleTabId);
    const staleTabForm = form("new-door-cutting-order-stale-tab");
    fakeWindow.cur_frm = staleTabForm;
    await Recovery.LocalCheckpoint.continueDraft(staleTabForm, staleTabRecord);
    records.set(staleTabId, {
        ...records.get(staleTabId),
        official_save_state: "PENDING_RECONCILIATION",
        official_save_attempted_at: "2026-08-29T10:59:00.000Z",
    });
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(staleTabForm);
    assert.equal(fakeFrappe.validated, false, "a stale tab cannot start over a newer pending attempt");
    assert.equal(
        records.get(staleTabId).official_save_attempted_at,
        "2026-08-29T10:59:00.000Z",
        "save-attempt conflict preserves the newer tab's marker"
    );
    assert.equal(
        Recovery.LocalCheckpoint.markDirty(staleTabForm, "DCO"),
        false,
        "a begin-attempt ownership conflict quarantines the stale form"
    );
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(staleTabForm);
    assert.equal(fakeFrappe.validated, false, "the quarantined form stays blocked");
    assert.equal(
        records.get(staleTabId).official_save_attempted_at,
        "2026-08-29T10:59:00.000Z"
    );

    const raceId = "77777777-7777-4777-8777-777777777777";
    const raceRecord = draft(raceId);
    const raceForm = form("new-door-cutting-order-race");
    reconciliationFailure = null;
    reconciliationResult = { status: "NOT_FOUND" };
    fakeWindow.cur_frm = raceForm;
    await Recovery.LocalCheckpoint.continueDraft(raceForm, raceRecord);
    await handlers["Door Cutting Order"].before_save(raceForm);
    nativeFailure = {
        status: 417,
        responseJSON: { exc_type: "UniqueValidationError" },
        message: "same creation token already committed",
    };
    await assert.rejects(raceForm.save());
    assert.equal(
        Recovery.LocalCheckpoint.snapshot(raceForm).state,
        "PENDING_RECONCILIATION",
        "a unique-key race must reconcile rather than assume no insert"
    );

    console.log("DCO NEW first-save and reconciliation simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
