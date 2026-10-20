"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const core = path.resolve(__dirname, "../../public/js/door_cutting_order/core");

function deferred() {
    let resolve;
    const promise = new Promise(complete => { resolve = complete; });
    return { promise, resolve };
}

function runtime() {
    const handlers = {};
    const scheduledUiWork = [];
    const document = {};
    const window = {
        addEventListener() {},
        setTimeout(callback) { scheduledUiWork.push(callback); },
        clearTimeout() {},
        requestAnimationFrame(callback) { scheduledUiWork.push(callback); },
        cancelAnimationFrame() {},
        AlmdinaPermissions: { canDocument: () => true, version: () => 1 },
    };
    const frappe = {
        almdina: {},
        provide() {},
        get_route: () => ["Form", "Door Cutting Order", window.cur_frm.doc.name],
        router: { on() {} },
        model: { new_names: {} },
        ui: { form: { on(doctype, events) {
            assert.equal(doctype, "Door Cutting Order");
            Object.entries(events).forEach(([event, handler]) => {
                handlers[event] = handlers[event] || [];
                handlers[event].push(handler);
            });
        } } },
        show_alert() {},
        msgprint() {},
    };
    window.frappe = frappe;
    const context = vm.createContext({
        window, document, frappe, console,
        $: () => ({ on() {} }),
    });
    for (const file of [
        "door_cutting_order_document_context.js",
        "door_cutting_order_edit_session_coordinator.js",
        "door_cutting_order_revision_ux.js",
    ]) {
        vm.runInContext(fs.readFileSync(path.join(core, file), "utf8"), context, { filename: file });
    }
    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-CHECKPOINT", status: "Draft", docstatus: 0, modified: "M1" },
        dirty: true,
        fields_dict: {},
        is_new() { return Boolean(this.newState); },
        is_dirty() { return this.dirty; },
        has_perm: () => true,
        toggle_enable(fields, enabled) { this.inputsEnabled = enabled; },
        remove_custom_button() {},
        trigger() {},
        reload_doc() { this.dirty = false; return Promise.resolve(); },
    };
    window.cur_frm = frm;
    window.AlmdinaDocumentContext.synchronize(frm);
    const ux = window.AlmdinaOrderRevisionUX;
    let saveNumber = 0;

    async function deliverEvent(event) {
        for (const handler of handlers[event] || []) await handler(frm);
    }

    function nextNativeSave(outcome = "success", options = {}) {
        const earlierAfterSaveHandler = deferred();
        const requestStarted = deferred();
        const requestSettled = deferred();
        let afterSave;
        let savedSource;
        let saveIndex;
        let nativeCallback;
        let callbackDelivered = false;
        function deliverCallback() {
            if (callbackDelivered || !nativeCallback) return;
            callbackDelivered = true;
            const response = options.missingDocs ? {}
                : { docs: options.wrongDocs
                    ? [{ ...savedSource, name: "DCO-UNRELATED" }]
                    : [savedSource] };
            nativeCallback(response);
        }
        function deliverResponse() {
            // The actual saved document is the request's source, even if the
            // live Form is reused for another document before this response.
            savedSource = {
                ...savedSource,
                modified: options.unchangedModified ? savedSource.modified : `${savedSource.name}-M${saveIndex + 1}`,
            };
            if (options.promoteTo) {
                const localname = savedSource.name;
                savedSource = { ...savedSource, localname, name: options.promoteTo };
                frappe.model.new_names[localname] = options.promoteTo;
                frm.doc.name = options.promoteTo;
                frm.doc.localname = localname;
                frm.newState = false;
            }
            if (frm.doc.name === savedSource.name) {
                frm.dirty = false;
                frm.doc.modified = savedSource.modified;
            }
            // Pinned Frappe queues trigger('after_save'), then invokes callback
            // with r.docs, then resolves frm.save(). ScriptManager may still be
            // awaiting an earlier handler when that native promise settles.
            afterSave = earlierAfterSaveHandler.promise.then(() => deliverEvent("after_save"));
            deliverCallback();
            requestSettled.resolve();
        }
        frm.save = async (action, callback) => {
            await deliverEvent("before_save");
            saveNumber += 1;
            saveIndex = saveNumber;
            savedSource = { ...frm.doc };
            nativeCallback = callback;
            requestStarted.resolve();
            if (outcome === "reject") return Promise.reject(new Error("native Save rejected"));
            if (outcome === "validation") return Promise.resolve();
            if (!options.holdResponse) deliverResponse();
            return requestSettled.promise;
        };
        return {
            started: requestStarted.promise,
            deliverResponse,
            async deliverAfterSave() {
                assert.ok(afterSave, "a successful native Save scheduled after_save");
                earlierAfterSaveHandler.resolve();
                await afterSave;
            },
        };
    }

    function visit(name, { isNew = false } = {}) {
        ux.abandonStoredEditSession(frm.doc.name, frm);
        frm.doc = { doctype: frm.doctype, name, status: "Draft", docstatus: 0, modified: `${name}-M1` };
        frm.docname = name;
        frm.dirty = true;
        frm.newState = isNew;
        window.AlmdinaDocumentContext.synchronize(frm);
    }

    return {
        frm, ux, coordinator: window.AlmdinaDcoEditSessionCoordinator,
        documentContext: window.AlmdinaDocumentContext, nextNativeSave, visit,
        setCapabilities(canDocument) { window.AlmdinaPermissions.canDocument = canDocument; },
    };
}

async function delayedCheckpointAfterSaveKeepsEditing() {
    const { frm, ux, coordinator, nextNativeSave } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    const checkpoint = nextNativeSave();
    assert.equal(await ux.persistOrderEditCheckpoint(frm), true);
    assert.equal(frm.is_dirty(), false);
    assert.equal(ux.isEditSessionActive(frm), true);
    await checkpoint.deliverAfterSave();
    assert.equal(ux.isEditableDraft(frm), true,
        "a delayed native after_save must preserve the acknowledged pre-plan Edit Session");
    assert.equal(frm.inputsEnabled, true);
    assert.equal(coordinator.snapshot(frm).phase, "editing");

    // Checkpoint intent is one-shot. The next explicit Save must finish editing
    // even when its after_save also runs after frm.save has already resolved.
    frm.dirty = true;
    const explicit = nextNativeSave();
    assert.equal(await ux.commitEditSession(frm), true);
    await explicit.deliverAfterSave();
    assert.equal(ux.isEditSessionActive(frm), false);
    assert.equal(frm.inputsEnabled, false);
    assert.equal(coordinator.snapshot(frm).phase, "idle");
}

async function failedCheckpointClearsIntent(outcome) {
    const { frm, ux, nextNativeSave } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    nextNativeSave(outcome);
    if (outcome === "reject") {
        await assert.rejects(ux.persistOrderEditCheckpoint(frm), /native Save rejected/);
    } else {
        assert.equal(await ux.persistOrderEditCheckpoint(frm), false);
    }
    assert.equal(frm.is_dirty(), true);
    assert.equal(ux.isEditSessionActive(frm), true);
    assert.equal(frm.__almdina_preserve_edit_session_after_save, false,
        "a failed Save with no after_save must not retain checkpoint preserve intent");
    const explicit = nextNativeSave();
    assert.equal(await ux.commitEditSession(frm), true);
    await explicit.deliverAfterSave();
    assert.equal(ux.isEditSessionActive(frm), false,
        "an explicit Save after checkpoint failure must still finish editing");
}

async function checkpointIntentCannotPreserveAnotherDocumentsNativeSave() {
    const { frm, ux, nextNativeSave, visit } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    const oldCheckpoint = nextNativeSave();
    assert.equal(await ux.persistOrderEditCheckpoint(frm), true);
    // A's after_save chain has not reached the revision handler. Frappe reuses
    // the same Form object for B before that old serial task is delivered.
    visit("DCO-B");
    assert.equal(await ux.enterEditSession(frm), true);
    const nativeSaveB = nextNativeSave();
    await frm.save();
    await nativeSaveB.deliverAfterSave();
    assert.equal(ux.isEditSessionActive(frm), false,
        "A's checkpoint intent must not keep B editable after B's native Save");
    await oldCheckpoint.deliverAfterSave();
    assert.equal(ux.isEditSessionActive(frm), false,
        "the late A after_save must not reopen B editing");
}

async function staleCheckpointFailureCannotClearNewDocumentsIntent() {
    const { frm, ux, nextNativeSave, visit } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    const saveStarted = deferred();
    let rejectOldSave;
    frm.save = () => {
        saveStarted.resolve();
        return new Promise((resolve, reject) => { rejectOldSave = reject; });
    };
    const oldCheckpoint = ux.persistOrderEditCheckpoint(frm);
    // Observe rejection immediately so this deliberate network failure never
    // produces an unhandled rejected promise while the test operates B.
    const observedOldFailure = oldCheckpoint.then(() => null, error => error);
    await saveStarted.promise;
    visit("DCO-B");
    assert.equal(await ux.enterEditSession(frm), true);
    const newCheckpoint = nextNativeSave();
    assert.equal(await ux.persistOrderEditCheckpoint(frm), true);
    rejectOldSave(new Error("old A Save transport failure"));
    const oldFailure = await observedOldFailure;
    assert.match(String(oldFailure), /old A Save transport failure/);
    await newCheckpoint.deliverAfterSave();
    assert.equal(ux.isEditableDraft(frm), true,
        "A's late checkpoint failure must not clear B's pending successful checkpoint intent");
    assert.equal(frm.inputsEnabled, true);
}

async function staleAfterSaveCannotConsumeNewCheckpoint(ordering) {
    const { frm, ux, nextNativeSave, visit } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    const oldCheckpoint = nextNativeSave();
    assert.equal(await ux.persistOrderEditCheckpoint(frm), true);
    visit("DCO-B");
    assert.equal(await ux.enterEditSession(frm), true);
    const newCheckpoint = nextNativeSave("success", { holdResponse: true });
    const savingB = ux.persistOrderEditCheckpoint(frm);
    await newCheckpoint.started;
    if (ordering === "before") {
        await oldCheckpoint.deliverAfterSave();
        assert.equal(ux.isEditSessionActive(frm), true,
            "late A after_save cannot consume or close B's still-pending checkpoint");
    }
    newCheckpoint.deliverResponse();
    assert.equal(await savingB, true);
    await newCheckpoint.deliverAfterSave();
    if (ordering === "after") await oldCheckpoint.deliverAfterSave();
    assert.equal(ux.isEditableDraft(frm), true,
        "late A after_save cannot close B after B's acknowledged checkpoint handler");
    assert.equal(frm.inputsEnabled, true);
    frm.dirty = true;
    const nativeSave = nextNativeSave();
    await frm.save();
    await nativeSave.deliverAfterSave();
    assert.equal(ux.isEditSessionActive(frm), false,
        "a later native B Save with a new official revision still finishes editing");
}

async function callbackCannotAcknowledgeARevisitedDocument() {
    const { frm, ux, documentContext, nextNativeSave, visit } = runtime();
    const nameA = frm.doc.name;
    assert.equal(await ux.enterEditSession(frm), true);
    const tokenA = documentContext.capture(frm);
    const oldSave = nextNativeSave("success", { holdResponse: true });
    const oldCheckpoint = ux.persistOrderEditCheckpoint(frm);
    await oldSave.started;
    visit("DCO-B");
    visit(nameA);
    assert.equal(await ux.enterEditSession(frm), true);
    assert.notEqual(documentContext.capture(frm).generation, tokenA.generation);
    oldSave.deliverResponse();
    assert.equal(await oldCheckpoint, false,
        "a genuine callback for the old A visit cannot acknowledge checkpoint success in a new A visit");
    assert.equal(Boolean(frm.__almdina_preserve_edit_session_after_save), false);
}

async function unprovenCallbackCannotAcknowledgeCheckpoint(options) {
    const { frm, ux, nextNativeSave } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    const checkpoint = nextNativeSave("success", options);
    assert.equal(await ux.persistOrderEditCheckpoint(frm), false,
        "checkpoint acknowledgement requires this exact document and a positively returned newer modified token");
    assert.equal(Boolean(frm.__almdina_preserve_edit_session_after_save), false);
    await checkpoint.deliverAfterSave();
    assert.equal(ux.isEditSessionActive(frm), Boolean(options.unchangedModified),
        "an unchanged official revision does not acknowledge completion; a changed native Save still locks normally");
}

async function cancelledSessionCannotAcknowledgeItsReplacement() {
    const { frm, ux, coordinator, nextNativeSave } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    const originalGeneration = coordinator.snapshot(frm).sessionGeneration;
    const oldSave = nextNativeSave("success", { holdResponse: true });
    const checkpoint = ux.persistOrderEditCheckpoint(frm);
    await oldSave.started;
    assert.equal(await ux.cancelEditSession(frm), true);
    assert.equal(await ux.enterEditSession(frm), true);
    assert.ok(coordinator.snapshot(frm).sessionGeneration > originalGeneration);
    oldSave.deliverResponse();
    assert.equal(await checkpoint, false,
        "a callback from the cancelled Edit Session cannot acknowledge its replacement session");
    assert.equal(Boolean(frm.__almdina_preserve_edit_session_after_save), false);
}

async function newPromotionClearsCreateOnlyProjection() {
    const { frm, ux, documentContext, nextNativeSave, visit, setCapabilities } = runtime();
    visit("new-door-cutting-order-test", { isNew: true });
    setCapabilities((form, capability) => capability === "create_order");
    const originalPermissions = [{ read: true, create: true, write: false }];
    frm.perm = originalPermissions;
    frm.has_perm = permission => Boolean(frm.perm[0][permission]);
    let permissionRefreshes = 0;
    frm.fields_dict.customer = {
        df: { fieldname: "customer", permlevel: 0 },
        refresh() { permissionRefreshes += 1; },
    };
    ux.applyImmutableFields(frm);
    assert.equal(frm.perm[0].write, true,
        "CREATE-only NEW input uses its existing temporary native-control projection");
    assert.notEqual(frm.perm, originalPermissions);
    assert.equal(originalPermissions[0].write, false);
    const localToken = documentContext.capture(frm);
    const nativeInsert = nextNativeSave("success", { promoteTo: "26-NEW-PERMANENT" });
    await frm.save();
    await nativeInsert.deliverAfterSave();
    assert.equal(documentContext.capture(frm).generation, localToken.generation,
        "DocumentContext promotes NEW identity in the same generation");
    assert.equal(documentContext.isSameDocument(frm, localToken), true);
    assert.equal(frm.perm, originalPermissions,
        "NEW promotion must restore the original CREATE-only permission projection after native Save");
    assert.equal(frm.perm[0].write, false);
    assert.equal(frm.__almdina_new_create_field_projection, undefined);
    assert.equal(ux.isEditableDraft(frm), false,
        "CREATE authority must not leave the officially saved DCO editable");
    assert.equal(frm.inputsEnabled, false);
    assert.ok(permissionRefreshes >= 2, "controls refresh both while projecting and after cleanup");
}

async function run() {
    const tests = [
        ["delayed after_save preserves checkpoint and later explicit Save locks", delayedCheckpointAfterSaveKeepsEditing],
        ["validation failure clears checkpoint intent", () => failedCheckpointClearsIntent("validation")],
        ["rejected Save clears checkpoint intent", () => failedCheckpointClearsIntent("reject")],
        ["checkpoint intent cannot preserve another document's native Save", checkpointIntentCannotPreserveAnotherDocumentsNativeSave],
        ["old checkpoint failure cannot clear new document intent", staleCheckpointFailureCannotClearNewDocumentsIntent],
        ["late A after_save cannot consume B's pending checkpoint", () => staleAfterSaveCannotConsumeNewCheckpoint("before")],
        ["late A after_save after B acknowledgement remains idempotent", () => staleAfterSaveCannotConsumeNewCheckpoint("after")],
        ["old A callback cannot acknowledge a revisited A document", callbackCannotAcknowledgeARevisitedDocument],
        ["missing response.docs cannot acknowledge checkpoint", () => unprovenCallbackCannotAcknowledgeCheckpoint({ missingDocs: true })],
        ["unrelated response.docs cannot acknowledge checkpoint", () => unprovenCallbackCannotAcknowledgeCheckpoint({ wrongDocs: true })],
        ["unchanged callback modified cannot acknowledge checkpoint", () => unprovenCallbackCannotAcknowledgeCheckpoint({ unchangedModified: true })],
        ["cancelled session callback cannot acknowledge its replacement", cancelledSessionCannotAcknowledgeItsReplacement],
        ["native NEW promotion clears CREATE-only input projection", newPromotionClearsCreateOnlyProjection],
    ];
    for (const [name, test] of tests) {
        try {
            await test();
            console.log(`PASS ${name}`);
        } catch (error) {
            process.exitCode = 1;
            console.error(`FAIL ${name}`);
            console.error(error);
        }
    }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
