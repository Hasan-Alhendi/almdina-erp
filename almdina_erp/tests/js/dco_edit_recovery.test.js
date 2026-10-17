"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const fakeWindow = { structuredClone };
const context = vm.createContext({
    window: fakeWindow,
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
});

function run(relative) {
    vm.runInContext(
        fs.readFileSync(path.resolve(__dirname, relative), "utf8"),
        context,
        { filename: path.basename(relative) }
    );
}

run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_recovery_projection.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_checkpoint_session.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_edit_recovery.js");

const Recovery = fakeWindow.AlmdinaDcoRecovery;
const identity = {
    site: "erp.example.test",
    user: "operator@example.test",
    target_doctype: "Door Cutting Order",
    target_name: "DCO-2026-00001",
    draft_id: "draft-001",
};
const modified = "2026-09-12 09:30:00.000000";

function makePayload(overrides = {}) {
    const dco = Recovery.Projection.createDcoInput({
        customer: "CUST-LOCAL",
        order_notes: "Local note",
        name: "SHOULD_NOT_APPLY",
        docstatus: 0,
        status: "Draft",
        pieces: [
            { name: "ROW-1", idx: 1, width_cm: 40, length_cm: 60, qty: 2, status: "Locked" },
            { name: "ROW-2", idx: 2, width_cm: 80, length_cm: 90, qty: 1, owner: "locked" },
        ],
    });
    return Recovery.Projection.createPayload({
        dco,
        dirtyScope: "DCO",
        ...overrides,
    });
}

function record(overrides = {}) {
    return {
        schema_version: 2,
        draft_id: identity.draft_id,
        mode: "EDIT",
        dirty_scope: "DCO",
        target_doctype: "Door Cutting Order",
        target_name: identity.target_name,
        session_origin_modified: modified,
        expected_server_modified: modified,
        tab_session_id: "tab-001",
        recovery_revision: 3,
        created_at: "2026-09-12T09:00:00.000Z",
        captured_at: "2026-09-12T09:20:00.000Z",
        official_save_state: "ACTIVE",
        official_save_attempted_at: null,
        payload_hash: "hash",
        payload: makePayload(),
        asset_refs: [],
        ...overrides,
    };
}

function document() {
    return {
        doctype: "Door Cutting Order",
        name: identity.target_name,
        modified,
        status: "Draft",
        docstatus: 0,
        customer: "CUST-SERVER",
        pieces: [
            { doctype: "Door Cutting Order Detail", name: "ROW-1", idx: 1, width_cm: 10, owner: "server-1" },
            { doctype: "Door Cutting Order Detail", name: "ROW-2", idx: 2, width_cm: 20, owner: "server-2" },
        ],
    };
}

function fakeRepository(selected) {
    const calls = { discover: [], reads: 0, readIdentity: null, deletes: 0 };
    return {
        calls,
        async discover(scope) {
            calls.discover.push(scope);
            return { ok: true, value: { records: [selected], rejected: [] } };
        },
        async read(scope) {
            calls.reads += 1;
            calls.readIdentity = scope;
            return { ok: true, value: selected };
        },
        async delete() { calls.deletes += 1; return { ok: true, value: true }; },
    };
}

(async () => {
    const selected = record();
    const repository = fakeRepository(selected);
    await Recovery.EditRecovery.discover(repository, identity);
    assert.deepEqual(JSON.parse(JSON.stringify(repository.calls.discover[0])), {
        site: identity.site,
        user: identity.user,
        target_doctype: "Door Cutting Order",
        target_name: identity.target_name,
        mode: "EDIT",
    }, "discovery is scoped to the current user and exact DCO");

    const dco = Recovery.EditRecovery.validateRecord(selected, identity, modified);
    const patch = Recovery.EditRecovery.buildAllowlistedPatch(document(), dco);
    assert.deepEqual(Object.keys(patch.headers), ["customer", "order_notes"]);
    assert.deepEqual(patch.pieces.map((item) => item.existing_name), ["ROW-1", "ROW-2"]);
    assert.deepEqual(patch.pieces.map((item) => item.values.width_cm), [40, 80]);
    assert.equal(Object.hasOwn(patch.pieces[0].values, "name"), false);
    assert.equal(Object.hasOwn(patch.pieces[0].values, "idx"), false);
    assert.equal(Object.hasOwn(patch.pieces[0].values, "owner"), false);
    assert.equal(Object.hasOwn(patch.headers, "status"), false);

    let current = true;
    let clean = true;
    let canEditCalls = 0;
    let canStartCalls = 0;
    let starts = 0;
    let applies = 0;
    let saves = 0;
    const restored = await Recovery.EditRecovery.restore(selected, {
        repository,
        identity,
        modified,
        doc: document(),
        isSessionGenerationCurrent: () => true,
        async fetchServerDocument() { return document(); },
        isCurrent: () => current,
        isClean: () => clean,
        canEdit: () => { canEditCalls += 1; return true; },
        canStart: () => { canStartCalls += 1; return true; },
        async startEdit() { starts += 1; return true; },
        isSessionCurrent: () => true,
        apply(value) { applies += 1; assert.deepEqual(value.pieces.map((item) => item.existing_name), ["ROW-1", "ROW-2"]); },
        save() { saves += 1; },
    });
    assert.equal(restored.draft_id, identity.draft_id);
    assert.equal(starts, 1);
    assert.equal(applies, 1);
    assert.equal(canStartCalls, 1);
    assert.equal(canEditCalls, 2, "permission is checked before session start and immediately before apply");
    assert.equal(saves, 0, "restore never invokes official Save");
    assert.equal(repository.calls.deletes, 0, "successful restore retains the recovery record");
    assert.deepEqual(JSON.parse(JSON.stringify(repository.calls.readIdentity)), identity);

    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository,
            identity,
            modified: "2026-09-12 10:00:00.000000",
            doc: document(),
            isSessionGenerationCurrent: () => true,
            async fetchServerDocument() { return document(); },
            isCurrent: () => true,
            isClean: () => true,
            canEdit: () => true,
            canStart: () => { throw new Error("must not start on version conflict"); },
        }),
        (error) => error.code === "version_conflict"
    );
    assert.equal(repository.calls.deletes, 0, "version conflict retains the draft");

    let conflictDetails = null;
    const latestServer = { ...document(), modified: "2026-09-12 10:00:00.000000", customer: "SERVER-CHANGED" };
    let conflictStarts = 0;
    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository: fakeRepository(selected),
            identity,
            modified,
            doc: document(),
            isCurrent: () => true,
            isSessionGenerationCurrent: () => true,
            async fetchServerDocument() { return latestServer; },
            isClean: () => true,
            canEdit: () => true,
            canStart: () => { conflictStarts += 1; return true; },
            async startEdit() { conflictStarts += 1; return true; },
            isSessionCurrent: () => true,
            apply() { throw new Error("freshness conflict must not apply"); },
        }),
        (error) => {
            conflictDetails = error.details;
            return error.code === "version_conflict";
        }
    );
    assert.equal(conflictStarts, 0, "external server updates after form load never start EDIT restore");
    assert.equal(conflictDetails.versions.loaded_form, modified);
    assert.equal(conflictDetails.versions.draft_expected, modified);
    assert.equal(conflictDetails.versions.current_server, latestServer.modified);
    assert.ok(conflictDetails.differences.some((item) => item.section === "header" && item.identity === "customer"));

    let fetchFailureStarts = 0;
    let fetchFailureDeletes = 0;
    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository: {
                async read() { return { ok: true, value: selected }; },
                async delete() { fetchFailureDeletes += 1; },
            },
            identity,
            modified,
            doc: document(),
            isCurrent: () => true,
            isSessionGenerationCurrent: () => true,
            async fetchServerDocument() { throw new Error("network unavailable"); },
            isClean: () => true,
            canEdit: () => true,
            canStart() { fetchFailureStarts += 1; return true; },
            async startEdit() { fetchFailureStarts += 1; return true; },
        }),
        (error) => error.code === "version_check_unavailable"
    );
    assert.equal(fetchFailureStarts, 0, "server version lookup failure never starts or applies EDIT recovery");
    assert.equal(fetchFailureDeletes, 0, "server version lookup failure retains the local draft");

    let staleDocument = true;
    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository: fakeRepository(selected),
            identity,
            modified,
            doc: document(),
            isCurrent: () => staleDocument,
            isSessionGenerationCurrent: () => true,
            async fetchServerDocument() {
                staleDocument = false;
                return document();
            },
            isClean: () => true,
        }),
        (error) => error.code === "stale_document"
    );

    let currentGeneration = true;
    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository: fakeRepository(selected),
            identity,
            modified,
            doc: document(),
            isCurrent: () => true,
            isSessionGenerationCurrent: () => currentGeneration,
            async fetchServerDocument() {
                currentGeneration = false;
                return document();
            },
            isClean: () => true,
        }),
        (error) => error.code === "stale_session"
    );

    let permissionChecks = 0;
    let deniedApply = 0;
    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository: fakeRepository(selected),
            identity,
            modified,
            doc: document(),
            isSessionGenerationCurrent: () => true,
            async fetchServerDocument() { return document(); },
            isCurrent: () => true,
            isClean: () => true,
            canEdit: () => { permissionChecks += 1; return permissionChecks === 1; },
            canStart: () => true,
            async startEdit() { return true; },
            isSessionCurrent: () => true,
            apply() { deniedApply += 1; },
        }),
        (error) => error.code === "permission_denied"
    );
    assert.equal(permissionChecks, 2);
    assert.equal(deniedApply, 0, "capability revocation is checked immediately before apply");

    let failedReadDeletes = 0;
    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository: {
                async read() { return { ok: false, error: { code: "storage_failure" } }; },
                async delete() { failedReadDeletes += 1; },
            },
            identity,
            modified,
            doc: document(),
            isSessionGenerationCurrent: () => true,
            async fetchServerDocument() { return document(); },
            isCurrent: () => true,
            isClean: () => true,
        }),
        (error) => error.code === "storage_unavailable"
    );
    assert.equal(failedReadDeletes, 0, "unknown local read outcome never discards the selected draft");

    let staleNow = true;
    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository: fakeRepository(selected),
            identity,
            modified,
            doc: document(),
            isSessionGenerationCurrent: () => true,
            async fetchServerDocument() { return document(); },
            isCurrent: () => staleNow,
            isClean: () => true,
            canEdit: () => true,
            canStart: () => true,
            async startEdit() { staleNow = false; return true; },
            isSessionCurrent: () => true,
            apply() { throw new Error("stale callback must not mutate the form"); },
        }),
        (error) => error.code === "stale_document"
    );

    await assert.rejects(
        Recovery.EditRecovery.restore(selected, {
            repository: fakeRepository(selected),
            identity,
            modified,
            doc: document(),
            isSessionGenerationCurrent: () => true,
            async fetchServerDocument() { return document(); },
            isCurrent: () => true,
            isClean: () => false,
        }),
        (error) => error.code === "dirty_document"
    );

    assert.throws(
        () => Recovery.EditRecovery.validateRecord(
            record({ target_name: "DCO-OTHER" }), identity, modified
        ),
        (error) => error.code === "invalid_edit_draft"
    );
    assert.throws(
        () => Recovery.EditRecovery.validateRecord(
            record({ dirty_scope: "PLAN" }), identity, modified
        ),
        (error) => error.code === "invalid_edit_draft"
    );
    assert.throws(
        () => Recovery.EditRecovery.validateRecord(
            record({ mode: "NEW" }), identity, modified
        ),
        (error) => error.code === "invalid_edit_draft"
    );
    const reorderedDco = {
        ...dco,
        pieces: [...dco.pieces].reverse(),
    };
    const reorderedPatch = Recovery.EditRecovery.buildAllowlistedPatch(document(), reorderedDco);
    assert.deepEqual(
        reorderedPatch.pieces.map((item) => item.existing_name),
        ["ROW-2", "ROW-1"],
        "saved row order is recoverable while child identities remain the persisted names"
    );
    const addedKey = "e4c16a0d-6149-4d3c-9b70-1c0aadd12345";
    const structurallyChangedPatch = Recovery.EditRecovery.buildAllowlistedPatch(document(), {
        ...dco,
        pieces: [
            { ...dco.pieces[1], piece_key: "ROW-2" },
            { piece_key: addedKey, width_cm: 35, length_cm: 40, qty: 1 },
        ],
    });
    assert.deepEqual(structurallyChangedPatch.pieces.map((item) => item.existing_name), ["ROW-2", null]);
    assert.equal(structurallyChangedPatch.pieces[1].piece_key, addedKey);

    const writes = [];
    const session = Recovery.CheckpointSession.create({
        repository: {
            async write(value) { writes.push(value); return { ok: true, value }; },
        },
        site: identity.site,
        user: identity.user,
        mode: "EDIT",
        draftId: identity.draft_id,
        targetName: identity.target_name,
        sessionOriginModified: modified,
        expectedServerModified: modified,
        tabSessionId: "tab-002",
        recoveryRevision: 3,
        savedRevision: 3,
        dirtyScope: "DCO",
        capture: () => ({ payload: makePayload(), asset_refs: [] }),
    });
    assert.equal(session.advanceExpectedServerModified("2026-09-12 10:15:00.000000"), true);
    await session.flush();
    assert.equal(session.snapshot().session_origin_modified, modified);
    assert.equal(session.snapshot().expected_server_modified, "2026-09-12 10:15:00.000000");
    assert.equal(writes[0].session_origin_modified, modified);
    assert.equal(writes[0].expected_server_modified, "2026-09-12 10:15:00.000000");

    console.log("DCO EDIT recovery contract simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
