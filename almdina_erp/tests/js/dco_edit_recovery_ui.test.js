"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const handlers = {};
const windowListeners = new Map();
const cleanups = new WeakMap();
const dialogs = [];
const writes = [];
const scriptEvents = [];
const checkpointFrames = new WeakMap();
let selectedRecord = null;
let permission = true;
let officialSaves = 0;
let deletes = 0;
let coordinatorStarts = 0;
let coordinatorCancels = 0;
let confirmCallbacks = null;
let latestServerDocument = null;
let clipboardCopy = null;
let pauseRemovalHook = null;
let pauseDerivedRebuild = null;
let recoveryDiscoveries = 0;
let serverDocumentReads = 0;
let capabilityRefreshes = 0;
const recoveryAlerts = [];

function makeDialog(options) {
    const buttonNames = ["continue", "delete", "dismiss"];
    const markup = String(options.fields && options.fields[0] && options.fields[0].options || "");
    const wrapper = {
        clickHandler: null,
        buttons: buttonNames.map((action) => ({
            disabled: action === "continue"
                && /data-edit-recovery-action="continue"[^>]*disabled="true"/.test(markup),
            dataset: { editRecoveryAction: action },
            closest(selector) {
                if (selector === "[data-draft-id]") return this.card;
                return null;
            },
            card: {
                dataset: { draftId: "draft-edit-1" },
                panel: null,
                querySelectorAll() { return []; },
                querySelector(selector) {
                    if (selector === '[data-edit-recovery-action="continue"]') {
                        return wrapper.buttons.find((item) => item.dataset.editRecoveryAction === "continue");
                    }
                    if (selector === "[data-edit-recovery-conflict]") return this.panel;
                    return null;
                },
                appendChild(panel) {
                    this.panel = panel;
                    wrapper.buttons.push({
                        disabled: false,
                        dataset: { editRecoveryAction: "copy" },
                        closest(selector) { return selector === "[data-draft-id]" ? this.card : null; },
                        card: this,
                    });
                },
                remove() { this.removed = true; },
            },
        })),
        addEventListener(name, callback) { if (name === "click") this.clickHandler = callback; },
        querySelectorAll() { return this.buttons; },
        querySelector() { return null; },
        fire(action) {
            const button = this.buttons.find((item) => item.dataset.editRecoveryAction === action);
            assert.ok(button, `missing ${action} button`);
            if (this.clickHandler) {
                this.clickHandler({ target: { closest: () => button } });
            }
        },
    };
    const dialog = {
        options,
        $wrapper: { get() { return wrapper; } },
        wrapper,
        hidden: false,
        show() { this.shown = true; },
        hide() { this.hidden = true; },
    };
    dialogs.push(dialog);
    return dialog;
}

const fakeWindow = {
    location: { host: "erp.example.test" },
    structuredClone,
    cur_frm: null,
    AlmdinaDoorCuttingFastEntry: {
        async render() {
            if (pauseDerivedRebuild) {
                pauseDerivedRebuild.started();
                await pauseDerivedRebuild.wait;
            }
        },
    },
    addEventListener(name, callback) { windowListeners.set(name, callback); },
    AlmdinaPermissions: {
        canDocument() { return permission; },
        async refresh() {
            capabilityRefreshes += 1;
            return { capabilities: { edit_order: permission } };
        },
    },
    AlmdinaOrderRevisionUX: {
        canOfferEditSession(frm) {
            return permission && !String(frm.doc.current_production_stage || "").trim();
        },
        isEditSessionActive(frm) { return Boolean(frm.coordinatorEditing); },
    },
};
const fakeDocument = {
    addEventListener() {},
    createElement() {
        return {
            attributes: {},
            setAttribute(name, value) { this.attributes[name] = value; },
            innerHTML: "",
        };
    },
};
const repository = {
    createIdentity() { return `local-id-${writes.length + 1}`; },
    async discover(scope) {
        recoveryDiscoveries += 1;
        repository.lastDiscovery = scope;
        return { ok: true, value: { records: selectedRecord ? [selectedRecord] : [], rejected: [] } };
    },
    async read() { return { ok: true, value: selectedRecord }; },
    async write(value) { writes.push(value); return { ok: true, value }; },
    async delete(identity, revision, attemptedAt) {
        repository.lastDelete = { identity, revision, attemptedAt };
        deletes += 1;
        return { ok: true, value: true };
    },
    async requestPersistence() { return false; },
    async hashCanonical(value) { return JSON.stringify(value); },
};

const documentTokens = new WeakMap();
const DocumentContext = {
    capture(frm) {
        let token = documentTokens.get(frm);
        if (!token) {
            token = { identity: `Door Cutting Order::${frm.doc.name}`, generation: 1 };
            documentTokens.set(frm, token);
        }
        return token;
    },
    isCurrent(frm, token) {
        const current = this.capture(frm);
        return current.identity === token.identity && current.generation === token.generation
            && fakeWindow.cur_frm === frm;
    },
    isSameDocument(frm, token) { return this.isCurrent(frm, token); },
    formIdentity(frm) { return `Door Cutting Order::${frm.doc.name}`; },
    registerCleanup(frm, key, cleanup) { cleanups.set(frm, { key, cleanup }); return true; },
    scheduleFrame(frm, key, callback) { checkpointFrames.set(frm, callback); },
};
fakeWindow.AlmdinaDocumentContext = DocumentContext;

const coordinatorStates = new WeakMap();
fakeWindow.AlmdinaDcoEditSessionCoordinator = {
    canStart(frm, kind) { return kind === "order" && !frm.coordinatorEditing && permission; },
    async start(frm, kind) {
        if (!this.canStart(frm, kind)) return false;
        frm.coordinatorEditing = true;
        frm.coordinatorGeneration = (frm.coordinatorGeneration || 0) + 1;
        coordinatorStarts += 1;
        coordinatorStates.set(frm, true);
        return true;
    },
    async cancel(frm, kind) {
        assert.equal(kind, "order");
        frm.coordinatorEditing = false;
        coordinatorCancels += 1;
        return true;
    },
        snapshot(frm) {
        return {
            sessionGeneration: frm.coordinatorGeneration || 0,
            phase: frm.coordinatorEditing ? "editing" : "idle",
            activeKind: frm.coordinatorEditing ? "order" : null,
        };
    },
    isSessionCurrent(frm, session) {
        return session.kind === "order"
            && frm.coordinatorEditing
            && session.sessionGeneration === frm.coordinatorGeneration
            && DocumentContext.isCurrent(frm, session.document);
    },
};

const fakeFrappe = {
    boot: { sitename: "erp.example.test" },
    session: { user: "operator@example.test" },
    utils: { copy_to_clipboard(value) { clipboardCopy = value; } },
    datetime: {},
    model: {
        clear_doc(doctype, name) {
            const doc = fakeWindow.cur_frm.doc;
            doc.pieces = doc.pieces.filter((row) => !(row.doctype === doctype && row.name === name));
            doc.pieces.forEach((row, index) => { row.idx = index + 1; });
            if (this.locals[doctype]) delete this.locals[doctype][name];
        },
        add_child(doc, doctype, fieldname) {
            doc[fieldname].push({ doctype, name: `new-row-${doc[fieldname].length + 1}`, __islocal: 1 });
            this.locals[doctype] = this.locals[doctype] || {};
            this.locals[doctype][doc[fieldname].at(-1).name] = doc[fieldname].at(-1);
            return doc[fieldname].at(-1);
        },
        locals: {},
    },
    ui: {
        Dialog: makeDialog,
        form: { on(doctype, events) { handlers[doctype] = { ...(handlers[doctype] || {}), ...events }; } },
    },
    meta: {
        get_docfield(doctype, fieldname) {
            return {
                doctype,
                fieldname,
                read_only: false,
                ...(fieldname === "notes" ? { get_status() { return "Write"; } } : {}),
            };
        },
    },
    perm: {
        get_field_display_status(df) { return df.fieldname === "edge_break" ? "Read" : "Write"; },
    },
    async call(options) {
        serverDocumentReads += 1;
        assert.equal(options.method, "frappe.client.get");
        assert.equal(options.args.doctype, "Door Cutting Order");
        assert.equal(options.args.name, fakeWindow.cur_frm.doc.name);
        return { message: latestServerDocument || fakeWindow.cur_frm.doc };
    },
    confirm(message, yes, no) { confirmCallbacks = { message, yes, no }; },
    show_alert(payload) { recoveryAlerts.push(payload); },
    msgprint(message) { fakeFrappe.lastMessage = message; },
};
fakeWindow.AlmdinaUi = {
    button(options = {}) {
        const attributes = Object.entries(options.attrs || {})
            .filter(([, value]) => value !== undefined && value !== null && value !== false)
            .map(([key, value]) => `${key}="${String(value)}"`)
            .join(" ");
        return `<button ${attributes}>${String(options.label || "")}</button>`;
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
    locals: {},
    __(message) {
        // This harness asserts an Arabic notice; exercise its actual catalog entry.
        const prefix = `${message},`;
        const entry = fs.readFileSync(path.resolve(__dirname, "../../translations/ar.csv"), "utf8")
            .split(/\r?\n/).find((line) => line.startsWith(prefix));
        return entry ? entry.slice(prefix.length) : message;
    },
});

function run(relative) {
    vm.runInContext(fs.readFileSync(path.resolve(__dirname, relative), "utf8"), context, {
        filename: path.basename(relative),
    });
}

run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_recovery_projection.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_checkpoint_session.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_new_recovery.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_edit_recovery.js");
fakeWindow.AlmdinaDcoRecovery.LocalDraftRepository = Object.freeze({ create: () => repository });
fakeWindow.AlmdinaDcoRecovery.LocalAssetRepository = Object.freeze({ create: () => ({}) });
run("../../public/js/door_cutting_order/recovery/presentation/door_cutting_order_local_checkpoint.js");

function makeRecord(overrides = {}) {
    const dco = fakeWindow.AlmdinaDcoRecovery.Projection.createDcoInput({
        customer: "LOCAL-CUSTOMER",
        order_notes: "restored notes",
        status: "not-restored",
        pieces: [
            { name: "EDIT-ROW-1", idx: 90, width_cm: 44, length_cm: 60, qty: 2, edge_break: 1, notes: "local notes", owner: "not-restored" },
            { name: "EDIT-ROW-2", idx: 91, width_cm: 82, length_cm: 90, qty: 1 },
        ],
    });
    return {
        schema_version: 2,
        draft_id: "draft-edit-1",
        mode: "EDIT",
        dirty_scope: "DCO",
        target_doctype: "Door Cutting Order",
        target_name: "DCO-EDIT-001",
        session_origin_modified: "2026-09-12 09:30:00.000000",
        expected_server_modified: "2026-09-12 09:30:00.000000",
        tab_session_id: "tab-edit-1",
        recovery_revision: 3,
        created_at: "2026-09-12T09:00:00.000Z",
        captured_at: "2026-09-12T09:20:00.000Z",
        official_save_state: "ACTIVE",
        official_save_attempted_at: null,
        payload_hash: "hash",
        payload: fakeWindow.AlmdinaDcoRecovery.Projection.createPayload({ dco, dirtyScope: "DCO" }),
        asset_refs: [],
        ...overrides,
    };
}

function form() {
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-EDIT-001",
            modified: "2026-09-12 09:30:00.000000",
            docstatus: 0,
            status: "Draft",
            revision_state: "Current",
            production_path: "ROUTE-ONLY-BEFORE-DISPATCH",
            current_production_stage: null,
            customer: "SERVER-CUSTOMER",
            order_notes: "SERVER-NOTE",
            pieces: [
                { doctype: "Door Cutting Order Detail", name: "EDIT-ROW-1", idx: 1, width_cm: 10, edge_break: 0, notes: "server notes", owner: "server-1" },
                { doctype: "Door Cutting Order Detail", name: "EDIT-ROW-2", idx: 2, width_cm: 20, edge_break: 0, owner: "server-2" },
            ],
        },
        coordinatorEditing: false,
        dirtyState: false,
        is_new() { return false; },
        is_dirty() { return this.dirtyState; },
        get_field(fieldname) {
            return { get_status() { return fieldname === "order_notes" ? "Read" : "Write"; } };
        },
        add_child(fieldname) {
            return fakeFrappe.model.add_child(this.doc, "Door Cutting Order Detail", fieldname);
        },
        dirty() { this.dirtyState = true; },
        save() { officialSaves += 1; return Promise.resolve(); },
        refresh_fields() {},
        refresh_field() {},
        script_manager: { async trigger(event, doctype, name) {
            scriptEvents.push({ event, doctype, name });
            if (["pieces_add", "pieces_remove"].includes(event) && handlers["Door Cutting Order Detail"]
                && typeof handlers["Door Cutting Order Detail"][event] === "function") {
                handlers["Door Cutting Order Detail"][event](frm);
            }
            if (event === "pieces_remove" && pauseRemovalHook) {
                fakeFrappe.model.locals[doctype].UNRELATED_LOADED_DURING_HOOK = {
                    doctype,
                    name: "UNRELATED_LOADED_DURING_HOOK",
                    title: "must survive rollback",
                };
            }
            if (pauseRemovalHook && event === pauseRemovalHook.event) {
                pauseRemovalHook.started();
                await pauseRemovalHook.wait;
            }
        } },
    };
    fakeFrappe.model.locals["Door Cutting Order Detail"] = Object.fromEntries(
        frm.doc.pieces.map((row) => [row.name, row]),
    );
    frm.fields_dict = {
        pieces: {
            grid: {
                df: { fieldname: "pieces", options: "Door Cutting Order Detail" },
                is_editable() { return false; },
                refresh() {},
            },
        },
    };
    return frm;
}

function currentToken(frm) {
    const old = DocumentContext.capture(frm);
    const next = { ...old, generation: old.generation + 1 };
    documentTokens.set(frm, next);
}

async function settle() {
    for (let i = 0; i < 50; i += 1) await Promise.resolve();
}

(async () => {
    selectedRecord = makeRecord();
    const frm = form();
    fakeWindow.cur_frm = frm;
    await handlers["Door Cutting Order"].onload(frm);
    assert.equal(repository.lastDiscovery.site, "erp.example.test");
    assert.equal(repository.lastDiscovery.user, "operator@example.test");
    assert.equal(repository.lastDiscovery.target_name, "DCO-EDIT-001");
    assert.equal(repository.lastDiscovery.mode, "EDIT");
    assert.equal(dialogs.at(-1).shown, true);

    dialogs.at(-1).wrapper.fire("continue");
    await settle();
    assert.equal(coordinatorStarts, 1);
    assert.equal(frm.doc.customer, "LOCAL-CUSTOMER", JSON.stringify(fakeFrappe.lastMessage));
    assert.equal(frm.doc.order_notes, "SERVER-NOTE", "locked header fields stay at the current form value");
    assert.equal(frm.doc.pieces.map((row) => row.name).join(","), "EDIT-ROW-1,EDIT-ROW-2");
    assert.equal(frm.doc.pieces.map((row) => row.width_cm).join(","), "44,82");
    assert.equal(frm.doc.pieces[0].idx, 1, "restore preserves Frappe row identity and order metadata");
    assert.equal(frm.doc.pieces[0].owner, "server-1", "locked fields are not hydrated");
    assert.equal(frm.doc.pieces[0].edge_break, 0, "Frappe's current field permission status preserves locked allowlisted values");
    assert.equal(frm.doc.pieces[0].notes, "server notes", "unknown dynamic field status without a live control fails closed");
    assert.equal(frm.doc.status, "Draft", "workflow fields are not hydrated");
    assert.equal(frm.dirtyState, true, "recovered values remain unsaved in the current form");
    assert.equal(officialSaves, 0, "restore never invokes the official Save action");
    assert.equal(deletes, 0, "restore retains the draft until an explicit user discard");
    assert.equal(fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(frm).mode, "EDIT");
    frm.save();
    assert.equal(officialSaves, 1, "official persistence remains available through an explicit Save action");

    const stickyForm = form();
    stickyForm.coordinatorEditing = true;
    stickyForm.coordinatorGeneration = 17;
    fakeWindow.cur_frm = stickyForm;
    selectedRecord = makeRecord();
    const startsBeforeSticky = coordinatorStarts;
    await handlers["Door Cutting Order"].onload(stickyForm);
    assert.equal(dialogs.at(-1).shown, true, "a hydrated active order session still discovers its persisted EDIT draft");
    dialogs.at(-1).wrapper.fire("continue");
    await settle();
    assert.equal(coordinatorStarts, startsBeforeSticky, "sticky order recovery reuses the existing session");
    assert.equal(stickyForm.coordinatorGeneration, 17, "sticky restore remains bound to its captured session generation");
    assert.equal(stickyForm.doc.customer, "LOCAL-CUSTOMER", JSON.stringify(fakeFrappe.lastMessage));

    const structuralForm = form();
    const originalRow1 = structuralForm.doc.pieces[0];
    const originalRow2 = structuralForm.doc.pieces[1];
    const removedRow = { doctype: "Door Cutting Order Detail", name: "EDIT-ROW-3", idx: 3, width_cm: 30 };
    structuralForm.doc.pieces.push(removedRow);
    const addedPieceKey = "e4c16a0d-6149-4d3c-9b70-1c0aadd12345";
    const structuralDco = fakeWindow.AlmdinaDcoRecovery.Projection.createDcoInput({
        customer: "STRUCTURAL-CUSTOMER",
        pieces: [
            { name: "EDIT-ROW-2", width_cm: 82, length_cm: 90, qty: 1 },
            { name: addedPieceKey, width_cm: 35, length_cm: 40, qty: 1 },
            { name: "EDIT-ROW-1", width_cm: 44, length_cm: 60, qty: 2 },
        ],
    });
    selectedRecord = makeRecord({
        payload: fakeWindow.AlmdinaDcoRecovery.Projection.createPayload({
            dco: structuralDco,
            dirtyScope: "DCO",
        }),
    });
    fakeWindow.cur_frm = structuralForm;
    await handlers["Door Cutting Order"].onload(structuralForm);
    dialogs.at(-1).wrapper.fire("continue");
    await settle();
    assert.deepEqual(structuralForm.doc.pieces.map((row) => row.name), [
        "EDIT-ROW-2", "new-row-3", "EDIT-ROW-1",
    ], "EDIT restore applies saved row removal, local addition and order through Frappe model seams");
    assert.equal(structuralForm.doc.pieces[0], originalRow2, "persisted child object identity survives reorder");
    assert.equal(structuralForm.doc.pieces[2], originalRow1, "persisted child object identity survives reorder");
    assert.equal(structuralForm.doc.pieces[1].width_cm, 35, "local addition is materialized with saved fields");
    assert.ok(structuralForm.doc.pieces[1].__unedited, "model-created row remains eligible for the existing Frappe row lifecycle");
    assert.equal(structuralForm.doc.pieces[1].idx, 2);
    assert.ok(scriptEvents.some((event) => event.event === "pieces_add" && event.name === "new-row-3"),
        "restore awaits the existing child-row add lifecycle hook");
    assert.ok(!structuralForm.doc.pieces.includes(removedRow), "rows removed by the saved draft leave the live child model");
    assert.ok(scriptEvents.some((event) => event.event === "before_pieces_remove" && event.name === "EDIT-ROW-3"));
    assert.ok(scriptEvents.some((event) => event.event === "pieces_remove" && event.name === "EDIT-ROW-3"));

    const successfulRestoreWrites = writes.length;
    assert.equal(typeof checkpointFrames.get(structuralForm), "function",
        "successful restore schedules the completed DCO projection");
    checkpointFrames.get(structuralForm)();
    await settle();
    assert.equal(writes.length, successfulRestoreWrites + 1,
        "successful hydration checkpoints once through the existing owner");
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(structuralForm);
    assert.equal(fakeFrappe.validated, true,
        "completed hydration keeps the next explicit native Save available");
    const completedProjection = writes.at(-1).payload.dco;
    assert.equal(completedProjection.customer, "STRUCTURAL-CUSTOMER");
    assert.deepEqual(completedProjection.pieces.map((piece) => piece.piece_key), [
        "EDIT-ROW-2", addedPieceKey, "EDIT-ROW-1",
    ], "only the completed row set and stable recovery identities are persisted");
    assert.equal(completedProjection.pieces[1].width_cm, 35);

    const interruptedStructuralForm = form();
    interruptedStructuralForm.doc.pieces.push({
        doctype: "Door Cutting Order Detail", name: "EDIT-ROW-3", idx: 3, width_cm: 30,
    });
    fakeWindow.cur_frm = interruptedStructuralForm;
    selectedRecord = makeRecord({ payload: fakeWindow.AlmdinaDcoRecovery.Projection.createPayload({
        dco: structuralDco, dirtyScope: "DCO",
    }) });
    const retainedRecord = JSON.stringify(selectedRecord);
    const retainedRevision = selectedRecord.recovery_revision;
    await handlers["Door Cutting Order"].onload(interruptedStructuralForm);
    let signalStructuralRebuild;
    const structuralRebuildStarted = new Promise((resolve) => { signalStructuralRebuild = resolve; });
    let resumeStructuralRebuild;
    const structuralRebuildWait = new Promise((resolve) => { resumeStructuralRebuild = resolve; });
    pauseDerivedRebuild = { started: signalStructuralRebuild, wait: structuralRebuildWait };
    const writesBeforeInterruptedStructure = writes.length;
    dialogs.at(-1).wrapper.fire("continue");
    await structuralRebuildStarted;
    assert.equal(fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(interruptedStructuralForm)
        .recovery_revision, retainedRevision,
    "native child lifecycle callbacks must not advance the checkpoint during hydration");
    // Also emulate a previously queued visibility/pagehide/frame flush while the
    // same model is being restored; it must not persist even fully applied data
    // until the final authoritative ownership check acknowledges the operation.
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(interruptedStructuralForm);
    assert.equal(writes.length, writesBeforeInterruptedStructure,
        "flushes during hydration cannot overwrite the acknowledged source checkpoint");
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(interruptedStructuralForm);
    assert.equal(fakeFrappe.validated, false,
        "native Save must not publish a model while hydration still awaits its final ownership check");
    assert.ok(recoveryAlerts.at(-1).message.includes("استعادة المسودة المحلية"),
        "the active operator is told that local restoration is still in progress");
    assert.equal(writes.length, writesBeforeInterruptedStructure);
    const alertsBeforeDepartedSave = recoveryAlerts.length;
    fakeWindow.cur_frm = form();
    fakeFrappe.validated = true;
    await assert.rejects(
        handlers["Door Cutting Order"].before_save(interruptedStructuralForm),
        (error) => error.code === "recovery_document_inactive",
        "a departed hydration owner rejects only its originating Save",
    );
    assert.equal(fakeFrappe.validated, true,
        "departed recovery must not alter the replacement form's process-global validation flag");
    assert.equal(recoveryAlerts.length, alertsBeforeDepartedSave,
        "departed recovery must not show its Save notice on the replacement document");
    fakeWindow.cur_frm = interruptedStructuralForm;
    latestServerDocument = {
        ...interruptedStructuralForm.doc,
        current_production_stage: "DYNAMIC-DISPATCH-DURING-STRUCTURAL-RESTORE",
    };
    resumeStructuralRebuild();
    pauseDerivedRebuild = null;
    await settle();
    assert.equal(interruptedStructuralForm.doc.customer, "SERVER-CUSTOMER");
    assert.deepEqual(interruptedStructuralForm.doc.pieces.map((row) => row.name), [
        "EDIT-ROW-1", "EDIT-ROW-2", "EDIT-ROW-3",
    ], "a failed final ownership check rolls back additions, removals and order");
    assert.equal(writes.length, writesBeforeInterruptedStructure);
    assert.equal(JSON.stringify(selectedRecord), retainedRecord,
        "failed hydration retains the exact acknowledged source checkpoint");
    latestServerDocument = null;

    const reusedRestoreForm = form();
    fakeWindow.cur_frm = reusedRestoreForm;
    selectedRecord = makeRecord();
    await handlers["Door Cutting Order"].onload(reusedRestoreForm);
    let signalOldRestore;
    const oldRestoreStarted = new Promise((resolve) => { signalOldRestore = resolve; });
    let resumeOldRestore;
    const oldRestoreWait = new Promise((resolve) => { resumeOldRestore = resolve; });
    pauseDerivedRebuild = { started: signalOldRestore, wait: oldRestoreWait };
    dialogs.at(-1).wrapper.fire("continue");
    await oldRestoreStarted;
    const oldRestoreCleanup = cleanups.get(reusedRestoreForm);
    const oldVisit = DocumentContext.capture(reusedRestoreForm);
    reusedRestoreForm.doc = { ...form().doc, name: "DCO-REUSED-B" };
    documentTokens.set(reusedRestoreForm, {
        identity: "Door Cutting Order::DCO-REUSED-B", generation: oldVisit.generation + 1,
    });
    oldRestoreCleanup.cleanup();
    reusedRestoreForm.doc.customer = "CURRENT-B-INPUT";
    assert.equal(fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.markDirty(reusedRestoreForm), true,
        "unfinished A hydration must not suppress mutations on B reusing the same Form object");
    const writesBeforeReusedB = writes.length;
    await fakeWindow.AlmdinaDcoRecovery.LocalCheckpoint.flush(reusedRestoreForm);
    assert.equal(writes.length, writesBeforeReusedB + 1);
    assert.equal(writes.at(-1).target_name, "DCO-REUSED-B");
    assert.equal(writes.at(-1).payload.dco.customer, "CURRENT-B-INPUT");
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(reusedRestoreForm);
    assert.equal(fakeFrappe.validated, true, "unfinished A hydration cannot block B's explicit Save");

    cleanups.get(reusedRestoreForm).cleanup();
    reusedRestoreForm.coordinatorEditing = false;
    reusedRestoreForm.dirtyState = false;
    selectedRecord = makeRecord({ target_name: "DCO-REUSED-B" });
    await handlers["Door Cutting Order"].onload(reusedRestoreForm);
    let signalNewRestore;
    const newRestoreStarted = new Promise((resolve) => { signalNewRestore = resolve; });
    let resumeNewRestore;
    const newRestoreWait = new Promise((resolve) => { resumeNewRestore = resolve; });
    pauseDerivedRebuild = { started: signalNewRestore, wait: newRestoreWait };
    dialogs.at(-1).wrapper.fire("continue");
    await newRestoreStarted;
    resumeOldRestore();
    await settle();
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(reusedRestoreForm);
    assert.equal(fakeFrappe.validated, false,
        "stale A finalization must not clear B's own unfinished restore guard");
    resumeNewRestore();
    pauseDerivedRebuild = null;
    await settle();
    fakeFrappe.validated = true;
    await handlers["Door Cutting Order"].before_save(reusedRestoreForm);
    assert.equal(fakeFrappe.validated, true, "B's own completed restore releases only B's Save guard");

    // 10/50/100 local piece additions must use bounded server calls.
    // Keep the actual Frappe Desk timings as a separate required gate.
    for (const count of [10, 50, 100]) {
        selectedRecord = makeRecord({
            payload: fakeWindow.AlmdinaDcoRecovery.Projection.createPayload({
                dco: fakeWindow.AlmdinaDcoRecovery.Projection.createDcoInput({
                    customer: "BULK-RESTORE",
                    pieces: Array.from({ length: count }, (_, index) => ({
                        name: `e4c16a0d-6149-4d3c-9b70-${index.toString(16).padStart(12, "0")}`,
                        width_cm: 20 + index,
                        length_cm: 40,
                        qty: 1,
                    })),
                }),
                dirtyScope: "DCO",
            }),
        });
        const batchForm = form();
        fakeWindow.cur_frm = batchForm;
        await handlers["Door Cutting Order"].onload(batchForm);
        const beforeReads = serverDocumentReads;
        const beforeCapabilities = capabilityRefreshes;
        dialogs.at(-1).wrapper.fire("continue");
        for (let attempt = 0; attempt < 200 && !batchForm.dirtyState; attempt += 1) {
            await new Promise((resolve) => setImmediate(resolve));
        }
        assert.equal(batchForm.dirtyState, true, `restore ${count} pieces reached a dirty, explicit-Save form`);
        assert.equal(batchForm.doc.pieces.length, count);
        assert.equal(serverDocumentReads - beforeReads, 3,
            `restore ${count} pieces uses initial version read plus two operation-boundary reads`);
        assert.equal(capabilityRefreshes - beforeCapabilities, 2,
            `restore ${count} pieces refreshes capabilities at operation boundaries only`);
        assert.equal(officialSaves, 1, "bulk recovery cannot trigger an extra official Save");
    }

    const interruptedForm = form();
    const interruptedRemovedRow = { doctype: "Door Cutting Order Detail", name: "EDIT-ROW-3", idx: 3, width_cm: 30 };
    interruptedForm.doc.pieces.push(interruptedRemovedRow);
    fakeWindow.cur_frm = interruptedForm;
    selectedRecord = makeRecord({ payload: fakeWindow.AlmdinaDcoRecovery.Projection.createPayload({
        dco: fakeWindow.AlmdinaDcoRecovery.Projection.createDcoInput({
            customer: "LOCAL-CUSTOMER",
            pieces: [
                { name: "EDIT-ROW-1", width_cm: 44, length_cm: 60, qty: 2 },
                { name: "EDIT-ROW-2", width_cm: 82, length_cm: 90, qty: 1 },
            ],
        }),
        dirtyScope: "DCO",
    }) });
    await handlers["Door Cutting Order"].onload(interruptedForm);
    let signalRemovalStarted;
    const removalStarted = new Promise((resolve) => { signalRemovalStarted = resolve; });
    let resumeRemoval;
    const removalWait = new Promise((resolve) => { resumeRemoval = resolve; });
    pauseRemovalHook = { event: "before_pieces_remove", started: signalRemovalStarted, wait: removalWait };
    const deletesBeforeInterruptedRestore = deletes;
    dialogs.at(-1).wrapper.fire("continue");
    await removalStarted;
    const capturedGeneration = interruptedForm.coordinatorGeneration;
    await fakeWindow.AlmdinaDcoEditSessionCoordinator.cancel(interruptedForm, "order");
    assert.equal(await fakeWindow.AlmdinaDcoEditSessionCoordinator.start(interruptedForm, "order"), true);
    assert.notEqual(interruptedForm.coordinatorGeneration, capturedGeneration);
    resumeRemoval();
    pauseRemovalHook = null;
    await settle();
    assert.equal(interruptedForm.coordinatorEditing, true, "a replacement order session is not canceled by the stale restore");
    assert.deepEqual(interruptedForm.doc.pieces.map((row) => row.name), ["EDIT-ROW-1", "EDIT-ROW-2", "EDIT-ROW-3"],
        "the restore stops before removing a row when its captured session ends during an awaited hook");
    assert.equal(interruptedForm.doc.customer, "SERVER-CUSTOMER", "stale restore does not apply header values after the hook");
    assert.equal(interruptedForm.dirtyState, false, "stale restore does not mark the replacement session dirty");
    assert.equal(deletes, deletesBeforeInterruptedRestore, "stale restore keeps the local checkpoint");

    const discoveriesBeforeActiveStageChecks = recoveryDiscoveries;
    const dialogsBeforeActiveStageChecks = dialogs.length;
    const alertsBeforeActiveStageChecks = recoveryAlerts.length;
    const deletesBeforeActiveStageChecks = deletes;
    for (const stageId of ["DYNAMIC-CUTTING-STAGE-7", "DYNAMIC-FINISHING-STAGE-19"]) {
        const activeStageForm = form();
        activeStageForm.doc.current_production_stage = stageId;
        fakeWindow.cur_frm = activeStageForm;
        selectedRecord = makeRecord();
        await handlers["Door Cutting Order"].onload(activeStageForm);
        await settle();
        assert.equal(activeStageForm.doc.current_production_stage, stageId);
    }
    assert.equal(recoveryDiscoveries, discoveriesBeforeActiveStageChecks + 2,
        "active dynamic production stages inspect only the existing local draft to explain retention");
    assert.equal(dialogs.length, dialogsBeforeActiveStageChecks,
        "active dynamic production stages never offer EDIT recovery");
    assert.equal(recoveryAlerts.length, alertsBeforeActiveStageChecks + 2);
    assert.ok(recoveryAlerts.at(-1).message.includes("لا يمكن استعادتها بعد بدء مرحلة الإنتاج"),
        "an ineligible local draft remains stored and receives a non-actionable Arabic explanation");
    assert.equal(deletes, deletesBeforeActiveStageChecks, "an ineligible draft is never silently deleted");

    const dispatchedDuringRestore = form();
    const pendingRemovedRow = {
        doctype: "Door Cutting Order Detail",
        name: "EDIT-ROW-3",
        idx: 3,
        width_cm: 30,
    };
    dispatchedDuringRestore.doc.pieces.push(pendingRemovedRow);
    fakeWindow.cur_frm = dispatchedDuringRestore;
    selectedRecord = makeRecord({ payload: fakeWindow.AlmdinaDcoRecovery.Projection.createPayload({
        dco: fakeWindow.AlmdinaDcoRecovery.Projection.createDcoInput({
            customer: "LOCAL-CUSTOMER",
            pieces: [
                { name: "EDIT-ROW-1", width_cm: 44, length_cm: 60, qty: 2 },
                { name: "EDIT-ROW-2", width_cm: 82, length_cm: 90, qty: 1 },
            ],
        }),
        dirtyScope: "DCO",
    }) });
    await handlers["Door Cutting Order"].onload(dispatchedDuringRestore);
    let signalDispatchPause;
    const dispatchPause = new Promise((resolve) => { signalDispatchPause = resolve; });
    let resumeDispatchPause;
    const dispatchWait = new Promise((resolve) => { resumeDispatchPause = resolve; });
    pauseRemovalHook = { event: "before_pieces_remove", started: signalDispatchPause, wait: dispatchWait };
    const originalDispatchRows = [...dispatchedDuringRestore.doc.pieces];
    const originalDispatchCustomer = dispatchedDuringRestore.doc.customer;
    const deletesBeforeDispatch = deletes;
    dialogs.at(-1).wrapper.fire("continue");
    await dispatchPause;
    latestServerDocument = {
        ...dispatchedDuringRestore.doc,
        current_production_stage: "DYNAMIC-STAGE-ACTIVATED-DURING-RESTORE",
    };
    resumeDispatchPause();
    pauseRemovalHook = null;
    await settle();
    assert.deepEqual(dispatchedDuringRestore.doc.pieces, originalDispatchRows,
        "a newly active server stage stops restore before any row mutation");
    assert.equal(dispatchedDuringRestore.doc.customer, originalDispatchCustomer,
        "a newly active server stage stops restore before any header mutation");
    assert.equal(dispatchedDuringRestore.dirtyState, false);
    assert.equal(deletes, deletesBeforeDispatch, "dispatch conflict retains the EDIT draft");
    latestServerDocument = null;

    const changedDuringRebuild = form();
    const changedRow = { doctype: "Door Cutting Order Detail", name: "EDIT-ROW-3", idx: 3, width_cm: 30 };
    changedDuringRebuild.doc.pieces.push(changedRow);
    fakeFrappe.model.locals["Door Cutting Order Detail"][changedRow.name] = changedRow;
    const originalRebuildRows = [...changedDuringRebuild.doc.pieces];
    fakeWindow.cur_frm = changedDuringRebuild;
    selectedRecord = makeRecord({ payload: fakeWindow.AlmdinaDcoRecovery.Projection.createPayload({
        dco: fakeWindow.AlmdinaDcoRecovery.Projection.createDcoInput({
            customer: "LOCAL-CUSTOMER",
            pieces: [
                { name: "EDIT-ROW-1", width_cm: 44, length_cm: 60, qty: 2 },
                { name: "EDIT-ROW-2", width_cm: 82, length_cm: 90, qty: 1 },
            ],
        }),
        dirtyScope: "DCO",
    }) });
    await handlers["Door Cutting Order"].onload(changedDuringRebuild);
    let signalRebuildStarted;
    const rebuildStarted = new Promise((resolve) => { signalRebuildStarted = resolve; });
    let resumeRebuild;
    const rebuildWait = new Promise((resolve) => { resumeRebuild = resolve; });
    pauseDerivedRebuild = { started: signalRebuildStarted, wait: rebuildWait };
    const writesBeforeRebuildConflict = writes.length;
    const deletesBeforeRebuildConflict = deletes;
    dialogs.at(-1).wrapper.fire("continue");
    await rebuildStarted;
    assert.equal(changedDuringRebuild.doc.customer, "LOCAL-CUSTOMER",
        "the race test pauses after model application and before dirty/checkpoint");
    latestServerDocument = {
        ...changedDuringRebuild.doc,
        current_production_stage: "DYNAMIC-STAGE-ACTIVATED-DURING-UI-REBUILD",
    };
    resumeRebuild();
    pauseDerivedRebuild = null;
    await settle();
    assert.equal(changedDuringRebuild.doc.customer, "SERVER-CUSTOMER",
        "a lifecycle change during derived UI rebuild rolls the recovery back");
    assert.deepEqual(changedDuringRebuild.doc.pieces, originalRebuildRows,
        "rollback restores the original row set and object identities");
    assert.equal(changedDuringRebuild.dirtyState, false,
        "a post-rebuild ownership conflict cannot dirty the live form");
    assert.equal(writes.length, writesBeforeRebuildConflict,
        "a post-rebuild ownership conflict cannot checkpoint partial recovery state");
    assert.equal(deletes, deletesBeforeRebuildConflict,
        "the EDIT draft remains retained after a post-rebuild conflict");
    latestServerDocument = null;

    const postHookForm = form();
    const postHookRemovedRow = { doctype: "Door Cutting Order Detail", name: "EDIT-ROW-3", idx: 3, width_cm: 30, notes: "keep me" };
    postHookForm.doc.pieces.push(postHookRemovedRow);
    fakeFrappe.model.locals["Door Cutting Order Detail"][postHookRemovedRow.name] = postHookRemovedRow;
    const originalPiecesList = postHookForm.doc.pieces;
    const originalRows = [...postHookForm.doc.pieces];
    const originalRowValues = originalRows.map((row) => ({ ...row }));
    const originalCustomer = postHookForm.doc.customer;
    const originalOrderNotes = postHookForm.doc.order_notes;
    const originalLocalRow = fakeFrappe.model.locals["Door Cutting Order Detail"][postHookRemovedRow.name];
    fakeWindow.cur_frm = postHookForm;
    selectedRecord = makeRecord({ payload: fakeWindow.AlmdinaDcoRecovery.Projection.createPayload({
        dco: fakeWindow.AlmdinaDcoRecovery.Projection.createDcoInput({
            customer: "LOCAL-CUSTOMER",
            pieces: [
                { name: "EDIT-ROW-1", width_cm: 44, length_cm: 60, qty: 2 },
                { name: "EDIT-ROW-2", width_cm: 82, length_cm: 90, qty: 1 },
            ],
        }),
        dirtyScope: "DCO",
    }) });
    await handlers["Door Cutting Order"].onload(postHookForm);
    let signalPostHookStarted;
    const postHookStarted = new Promise((resolve) => { signalPostHookStarted = resolve; });
    let resumePostHook;
    const postHookWait = new Promise((resolve) => { resumePostHook = resolve; });
    pauseRemovalHook = { event: "pieces_remove", started: signalPostHookStarted, wait: postHookWait };
    const writesBeforePostHook = writes.length;
    const deletesBeforePostHook = deletes;
    dialogs.at(-1).wrapper.fire("continue");
    await postHookStarted;
    assert.equal(postHookForm.doc.customer, "LOCAL-CUSTOMER", "the post-hook test reaches the applied-but-uncommitted projection");
    assert.ok(!postHookForm.doc.pieces.includes(postHookRemovedRow), "the Frappe removal path has run before the post-hook");
    const postHookGeneration = postHookForm.coordinatorGeneration;
    await fakeWindow.AlmdinaDcoEditSessionCoordinator.cancel(postHookForm, "order");
    assert.equal(await fakeWindow.AlmdinaDcoEditSessionCoordinator.start(postHookForm, "order"), true);
    assert.notEqual(postHookForm.coordinatorGeneration, postHookGeneration);
    resumePostHook();
    pauseRemovalHook = null;
    await settle();
    assert.equal(postHookForm.coordinatorEditing, true, "post-hook rollback leaves the replacement session untouched");
    assert.equal(postHookForm.doc.pieces, originalPiecesList, "rollback restores the exact Frappe child table object");
    assert.deepEqual(postHookForm.doc.pieces, originalRows, "rollback restores the exact row order and identity set");
    postHookForm.doc.pieces.forEach((row, index) => {
        assert.equal(row, originalRows[index], "rollback preserves each persisted child object reference");
        assert.deepEqual(row, originalRowValues[index], "rollback restores every original child value");
    });
    assert.equal(postHookForm.doc.customer, originalCustomer, "rollback restores header values");
    assert.equal(postHookForm.doc.order_notes, originalOrderNotes);
    assert.equal(fakeFrappe.model.locals["Door Cutting Order Detail"][postHookRemovedRow.name], originalLocalRow,
        "rollback restores Frappe's local child registration");
    assert.equal(fakeFrappe.model.locals["Door Cutting Order Detail"].UNRELATED_LOADED_DURING_HOOK.title,
        "must survive rollback", "rollback preserves unrelated local documents added during the awaited hook");
    assert.equal(postHookForm.dirtyState, false, "partial restore does not leave the form dirty");
    assert.equal(postHookForm.doc.__unsaved, undefined, "partial restore does not set Frappe's unsaved marker");
    assert.equal(writes.length, writesBeforePostHook, "hook callbacks cannot checkpoint a partial projection");
    assert.equal(deletes, deletesBeforePostHook, "the draft remains available after rollback");

    const conflictForm = form();
    fakeWindow.cur_frm = conflictForm;
    selectedRecord = makeRecord();
    const beforeConflictStarts = coordinatorStarts;
    await handlers["Door Cutting Order"].onload(conflictForm);
    const conflictDialog = dialogs.at(-1);
    latestServerDocument = {
        ...conflictForm.doc,
        modified: "2026-09-12 10:00:00.000000",
        customer: "SERVER-UPDATED-AFTER-LOAD",
    };
    const continueButton = conflictDialog.wrapper.buttons.find((button) => button.dataset.editRecoveryAction === "continue");
    conflictDialog.wrapper.fire("continue");
    await settle();
    assert.equal(coordinatorStarts, beforeConflictStarts, "server version conflict never enters edit mode");
    assert.equal(deletes, 0, "server version conflict retains the local draft");
    assert.equal(continueButton.disabled, true, "conflicting draft cannot be applied");
    assert.ok(continueButton.card.panel.innerHTML.includes("2026-09-12 10:00:00.000000"));
    assert.ok(continueButton.card.panel.innerHTML.includes("SERVER-UPDATED-AFTER-LOAD"));
    conflictDialog.wrapper.fire("copy");
    assert.ok(clipboardCopy.includes("LOCAL-CUSTOMER"), "conflict review can copy the allowlisted local draft");
    assert.equal(conflictForm.doc.customer, "SERVER-CUSTOMER", "conflict review leaves the live form untouched");
    latestServerDocument = null;

    const staleForm = form();
    fakeWindow.cur_frm = staleForm;
    selectedRecord = makeRecord();
    const oldRead = repository.read;
    repository.read = async () => {
        currentToken(staleForm);
        return { ok: true, value: selectedRecord };
    };
    const startsBeforeStale = coordinatorStarts;
    await handlers["Door Cutting Order"].onload(staleForm);
    dialogs.at(-1).wrapper.fire("continue");
    await settle();
    assert.equal(coordinatorStarts, startsBeforeStale, "stale document callback cannot start a session");
    assert.equal(staleForm.doc.customer, "SERVER-CUSTOMER", "stale response cannot mutate the replacement DCO");
    repository.read = oldRead;

    const staleServerForm = form();
    fakeWindow.cur_frm = staleServerForm;
    selectedRecord = makeRecord();
    await handlers["Door Cutting Order"].onload(staleServerForm);
    const staleServerDialog = dialogs.at(-1);
    const originalCall = fakeFrappe.call;
    fakeFrappe.call = async (options) => {
        currentToken(staleServerForm);
        return originalCall(options);
    };
    const startsBeforeStaleServer = coordinatorStarts;
    staleServerDialog.wrapper.fire("continue");
    await settle();
    assert.equal(coordinatorStarts, startsBeforeStaleServer, "stale canonical response cannot start or apply recovery");
    assert.equal(staleServerForm.doc.customer, "SERVER-CUSTOMER");
    fakeFrappe.call = originalCall;

    const revokedDuringFetchForm = form();
    fakeWindow.cur_frm = revokedDuringFetchForm;
    selectedRecord = makeRecord();
    permission = true;
    await handlers["Door Cutting Order"].onload(revokedDuringFetchForm);
    const revokedDuringFetchDialog = dialogs.at(-1);
    const writesBeforeRevocation = writes.length;
    const deletesBeforeRevocation = deletes;
    fakeFrappe.call = async (options) => {
        const response = await originalCall(options);
        permission = false;
        return response;
    };
    revokedDuringFetchDialog.wrapper.fire("continue");
    await settle();
    assert.equal(revokedDuringFetchForm.doc.customer, "SERVER-CUSTOMER",
        "capability revoked during canonical GET prevents applying the recovery projection");
    assert.equal(revokedDuringFetchForm.dirtyState, false,
        "capability revocation during the GET does not dirty the form");
    assert.equal(writes.length, writesBeforeRevocation,
        "capability revocation during the GET does not checkpoint recovery");
    assert.equal(deletes, deletesBeforeRevocation,
        "capability revocation during the GET retains the recovery draft");
    fakeFrappe.call = originalCall;
    permission = true;

    const discardForm = form();
    fakeWindow.cur_frm = discardForm;
    selectedRecord = makeRecord();
    await handlers["Door Cutting Order"].onload(discardForm);
    dialogs.at(-1).wrapper.fire("delete");
    assert.ok(confirmCallbacks, "deleting a draft requires an explicit user confirmation");
    await confirmCallbacks.yes();
    assert.equal(deletes, 1);
    assert.equal(repository.lastDelete.revision, selectedRecord.recovery_revision);

    const forcedForm = form();
    fakeWindow.cur_frm = forcedForm;
    permission = true;
    selectedRecord = makeRecord();
    const startsBeforeForcedDismiss = coordinatorStarts;
    const cancelsBeforeForcedDismiss = coordinatorCancels;
    await handlers["Door Cutting Order"].onload(forcedForm);
    const forcedDialog = dialogs.at(-1);
    permission = false;
    windowListeners.get("almdina:permissions-updated")();
    assert.equal(forcedDialog.hidden, true, "permission revocation dismisses discovery");
    assert.equal(deletes, 1, "forced capability cancellation never discards the user's recovery data");
    assert.equal(coordinatorStarts, startsBeforeForcedDismiss, "permission revocation does not open an edit session");
    assert.equal(coordinatorCancels, cancelsBeforeForcedDismiss, "permission revocation does not cancel an unrelated edit session");

    const dismissedVisitForm = form();
    fakeWindow.cur_frm = dismissedVisitForm;
    permission = true;
    selectedRecord = makeRecord();
    await handlers["Door Cutting Order"].onload(dismissedVisitForm);
    const dismissedDialog = dialogs.at(-1);
    dismissedDialog.wrapper.fire("dismiss");
    assert.equal(dismissedDialog.hidden, true);
    const discoveriesAfterDismiss = recoveryDiscoveries;
    const dialogsAfterDismiss = dialogs.length;
    await handlers["Door Cutting Order"].refresh(dismissedVisitForm);
    await handlers["Door Cutting Order"].onload(dismissedVisitForm);
    assert.equal(recoveryDiscoveries, discoveriesAfterDismiss,
        "ordinary refresh in the same visit must respect an explicit dismissal");
    assert.equal(dialogs.length, dialogsAfterDismiss,
        "an explicitly dismissed recovery choice must not reopen in the same visit");

    const dismissedVisit = DocumentContext.capture(dismissedVisitForm);
    cleanups.get(dismissedVisitForm).cleanup();
    dismissedVisitForm.doc = { ...form().doc, name: "DCO-DISMISS-REUSED-B" };
    documentTokens.set(dismissedVisitForm, {
        identity: "Door Cutting Order::DCO-DISMISS-REUSED-B",
        generation: dismissedVisit.generation + 1,
    });
    selectedRecord = makeRecord({ target_name: "DCO-DISMISS-REUSED-B" });
    await handlers["Door Cutting Order"].onload(dismissedVisitForm);
    assert.equal(recoveryDiscoveries, discoveriesAfterDismiss + 1,
        "dismissing A must not suppress B's valid draft discovery when Frappe reuses its Form");
    assert.equal(dialogs.length, dialogsAfterDismiss + 1,
        "B receives its own explicit recovery choice after A's visit cleanup");
    assert.equal(dialogs.at(-1).shown, true);

    console.log("DCO EDIT recovery presentation simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
