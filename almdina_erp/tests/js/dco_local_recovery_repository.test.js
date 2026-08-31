"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const relativeSources = [
    "../../public/js/door_cutting_order/recovery/application/door_cutting_order_recovery_projection.js",
    "../../public/js/door_cutting_order/recovery/infrastructure/door_cutting_order_recovery_indexeddb.js",
    "../../public/js/door_cutting_order/recovery/infrastructure/door_cutting_order_local_draft_repository.js",
    "../../public/js/door_cutting_order/recovery/infrastructure/door_cutting_order_local_asset_repository.js",
];
const fakeWindow = {
    TextEncoder,
    crypto: crypto.webcrypto,
    navigator: {},
    structuredClone,
};
const context = vm.createContext({
    window: fakeWindow,
    console,
    Object,
    Array,
    Set,
    Map,
    String,
    Number,
    Date,
    JSON,
    Promise,
    Uint8Array,
    Blob,
    TextEncoder,
    structuredClone,
    encodeURIComponent,
});
relativeSources.forEach((relative) => {
    const source = fs.readFileSync(path.resolve(__dirname, relative), "utf8");
    vm.runInContext(source, context, { filename: path.basename(relative) });
});

const Recovery = fakeWindow.AlmdinaDcoRecovery;

function domNames() {
    const values = [];
    return {
        values,
        contains(name) { return values.includes(name); },
        add(name) { if (!values.includes(name)) values.push(name); },
    };
}

async function verifiesDatabaseInitialization() {
    const stores = new Map();
    const databaseNames = domNames();
    const database = {
        objectStoreNames: databaseNames,
        createObjectStore(name, options) {
            databaseNames.add(name);
            const indexes = domNames();
            const store = {
                name,
                options,
                indexNames: indexes,
                createIndex(indexName, keyPath) {
                    indexes.add(indexName);
                    return { indexName, keyPath };
                },
            };
            stores.set(name, store);
            return store;
        },
        close() {},
    };
    const indexedDB = {
        open(name, version) {
            assert.equal(name, "almdina_erp_dco_recovery");
            assert.equal(version, 1);
            const request = {
                result: database,
                transaction: {
                    abort() {},
                    objectStore(storeName) { return stores.get(storeName); },
                },
            };
            queueMicrotask(() => {
                request.onupgradeneeded();
                request.onsuccess();
            });
            return request;
        },
    };
    const gateway = Recovery.IndexedDb.createGateway({ indexedDB, crypto: crypto.webcrypto, TextEncoder });
    assert.equal(await gateway.open(), database);
    assert.deepEqual(databaseNames.values.sort(), ["dco_recovery_assets", "dco_recovery_drafts"]);
    assert.deepEqual(
        stores.get("dco_recovery_drafts").indexNames.values.sort(),
        ["captured_at", "namespace_key", "target_key"]
    );
    assert.deepEqual(
        stores.get("dco_recovery_assets").indexNames.values.sort(),
        ["draft_key", "namespace_key"]
    );
}

async function verifiesDatabaseOpenFailuresAreExplicit() {
    const indexedDB = {
        open() {
            const request = { error: { name: "VersionError" } };
            queueMicrotask(() => request.onerror());
            return request;
        },
    };
    const gateway = Recovery.IndexedDb.createGateway({ indexedDB, crypto: crypto.webcrypto, TextEncoder });
    await assert.rejects(
        gateway.open(),
        (error) => error.code === "unknown_schema"
    );
}

async function verifiesCodedOperationFailuresRemainExplicit() {
    const transaction = {
        objectStore() { return {}; },
        abort() { queueMicrotask(() => this.onabort()); },
    };
    const database = {
        objectStoreNames: { contains: () => true },
        transaction() { return transaction; },
        close() {},
    };
    const indexedDB = {
        open() {
            const request = { result: database };
            queueMicrotask(() => request.onsuccess());
            return request;
        },
    };
    const gateway = Recovery.IndexedDb.createGateway({ indexedDB, crypto: crypto.webcrypto, TextEncoder });
    const conflict = Object.assign(new Error("same revision differs"), { code: "revision_conflict" });
    await assert.rejects(
        gateway.transaction(["dco_recovery_drafts"], "readwrite", () => { throw conflict; }),
        (error) => error === conflict && error.code === "revision_conflict"
    );
}

function memoryGateway() {
    const records = {
        dco_recovery_drafts: new Map(),
        dco_recovery_assets: new Map(),
    };
    let failure = null;

    function storeFor(name) {
        const values = records[name];
        return {
            get(key) { return values.get(key); },
            put(value) { values.set(value.storage_key, value); return value.storage_key; },
            delete(key) { values.delete(key); },
            index(indexName) {
                return {
                    getAll(expected) {
                        return [...values.values()].filter((item) => item[indexName] === expected);
                    },
                    getAllKeys(expected) {
                        return [...values.values()]
                            .filter((item) => item[indexName] === expected)
                            .map((item) => item.storage_key);
                    },
                };
            },
        };
    }

    return {
        records,
        failNext(code) { failure = code; },
        async open() { return {}; },
        async transaction(storeNames, mode, operation) {
            if (failure) {
                const error = Object.assign(new Error(`forced ${failure}`), { code: failure });
                failure = null;
                throw error;
            }
            const stores = Object.fromEntries(storeNames.map((name) => [name, storeFor(name)]));
            return operation(stores, async (value) => value, { mode });
        },
        async sha256(value) {
            return crypto.createHash("sha256").update(String(value)).digest("hex");
        },
        async sha256Bytes(value) {
            return crypto.createHash("sha256").update(Buffer.from(value)).digest("hex");
        },
        async requestPersistence() { return false; },
    };
}

function dcoProjection(pieceKey = "piece-local-1") {
    return Recovery.Projection.createDcoInput({
        customer: "CUST-001",
        board_description: "MDF",
        pieces: [{ name: "new-piece-1", width_cm: 40, length_cm: 60, qty: 2 }],
    }, { pieceKey: () => pieceKey });
}

function dcoPayload(pieceKey = "piece-local-1") {
    return Recovery.Projection.createPayload({
        dco: dcoProjection(pieceKey),
        dirtyScope: "DCO",
    });
}

(async () => {
    await verifiesDatabaseInitialization();
    await verifiesDatabaseOpenFailuresAreExplicit();
    await verifiesCodedOperationFailuresRemainExplicit();

    const gateway = memoryGateway();
    const clockValues = [
        "2026-08-29T10:00:00.000Z",
        "2026-08-29T10:01:00.000Z",
        "2026-08-29T10:02:00.000Z",
    ];
    const repository = Recovery.LocalDraftRepository.create({
        gateway,
        clock: () => clockValues.shift() || "2026-08-29T10:03:00.000Z",
        TextEncoder,
    });
    const newIdentity = {
        site: "erp.example.test",
        user: "operator@example.test",
        target_doctype: "Door Cutting Order",
        draft_id: "11111111-1111-4111-8111-111111111111",
    };
    const firstWrite = await repository.write({
        ...newIdentity,
        mode: "NEW",
        dirty_scope: "DCO",
        target_name: null,
        session_origin_modified: null,
        expected_server_modified: null,
        tab_session_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        recovery_revision: 1,
        payload: dcoPayload(),
        asset_refs: [],
    });
    assert.equal(firstWrite.ok, true);
    assert.equal(firstWrite.value.schema_version, 1);
    assert.equal(firstWrite.value.mode, "NEW");
    assert.equal(firstWrite.value.draft_id, newIdentity.draft_id);
    assert.equal(firstWrite.value.target_name, null);
    assert.equal(firstWrite.value.session_origin_modified, null);
    assert.equal(firstWrite.value.expected_server_modified, null);
    assert.equal(firstWrite.value.recovery_revision, 1);
    assert.match(firstWrite.value.payload_hash, /^[a-f0-9]{64}$/);

    const readFirst = await repository.read(newIdentity);
    assert.equal(readFirst.ok, true);
    assert.equal(readFirst.value.payload.dco.pieces[0].piece_key, "piece-local-1");
    const createdAt = readFirst.value.created_at;

    const secondWrite = await repository.write({
        ...newIdentity,
        mode: "NEW",
        dirty_scope: "DCO",
        target_name: null,
        session_origin_modified: null,
        expected_server_modified: null,
        tab_session_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        recovery_revision: 2,
        payload: dcoPayload("piece-local-2"),
        asset_refs: [],
    });
    assert.equal(secondWrite.ok, true);
    assert.equal(secondWrite.value.recovery_revision, 2);
    assert.equal(secondWrite.value.created_at, createdAt);
    assert.equal((await repository.read(newIdentity)).value.payload.dco.pieces[0].piece_key, "piece-local-2");

    const idempotent = await repository.write({
        ...newIdentity,
        mode: "NEW",
        dirty_scope: "DCO",
        target_name: null,
        session_origin_modified: null,
        expected_server_modified: null,
        tab_session_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        recovery_revision: 2,
        payload: dcoPayload("piece-local-2"),
        asset_refs: [],
    });
    assert.equal(idempotent.ok, true);
    assert.equal(idempotent.value.recovery_revision, 2);

    const revisionConflict = await repository.write({
        ...newIdentity,
        mode: "NEW",
        dirty_scope: "DCO",
        target_name: null,
        session_origin_modified: null,
        expected_server_modified: null,
        tab_session_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        recovery_revision: 2,
        payload: dcoPayload("different-at-same-revision"),
        asset_refs: [],
    });
    assert.equal(revisionConflict.ok, false);
    assert.equal(revisionConflict.error.code, "revision_conflict");

    const stale = await repository.write({
        ...newIdentity,
        mode: "NEW",
        dirty_scope: "DCO",
        target_name: null,
        session_origin_modified: null,
        expected_server_modified: null,
        tab_session_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        recovery_revision: 1,
        payload: dcoPayload(),
        asset_refs: [],
    });
    assert.equal(stale.ok, false);
    assert.equal(stale.error.code, "stale_revision");

    const editIdentity = {
        site: newIdentity.site,
        user: newIdentity.user,
        target_doctype: "Door Cutting Order",
        draft_id: "22222222-2222-4222-8222-222222222222",
    };
    const editWrite = await repository.write({
        ...editIdentity,
        mode: "EDIT",
        dirty_scope: "DCO",
        target_name: "DCO-2026-00001",
        session_origin_modified: "2026-08-29 08:00:00.000000",
        expected_server_modified: "2026-08-29 09:00:00.000000",
        tab_session_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        recovery_revision: 1,
        payload: dcoPayload("ROW-EXISTING"),
        asset_refs: [],
    });
    assert.equal(editWrite.ok, true);
    assert.equal(editWrite.value.target_name, "DCO-2026-00001");
    assert.equal(editWrite.value.session_origin_modified, "2026-08-29 08:00:00.000000");
    assert.equal(editWrite.value.expected_server_modified, "2026-08-29 09:00:00.000000");

    const discovered = await repository.discover({
        site: newIdentity.site,
        user: newIdentity.user,
        target_doctype: "Door Cutting Order",
    });
    assert.equal(discovered.ok, true);
    assert.equal(discovered.value.records.length, 2);
    assert.deepEqual(Array.from(discovered.value.rejected), []);
    const editDiscovery = await repository.discover({
        site: newIdentity.site,
        user: newIdentity.user,
        mode: "EDIT",
        target_name: "DCO-2026-00001",
    });
    assert.equal(editDiscovery.value.records.length, 1);
    assert.equal(editDiscovery.value.records[0].draft_id, editIdentity.draft_id);

    const specialPayload = Recovery.Projection.createPayload({
        dco: dcoProjection(),
        dirtyScope: "SPECIAL_SHAPE",
        specialShapeDrafts: [Recovery.Projection.createSpecialShapeDraft({
            order_name: "DCO-2026-00001",
            piece_name: "ROW-EXISTING",
            document: { schema: "almdina.special-shape-documentation", version: 1, reference: null },
            asset_refs: ["asset-scan-1"],
        })],
    });
    const assetEnvelopeWrite = await repository.write({
        ...newIdentity,
        mode: "NEW",
        dirty_scope: "SPECIAL_SHAPE",
        target_name: null,
        session_origin_modified: null,
        expected_server_modified: null,
        tab_session_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        recovery_revision: 3,
        payload: specialPayload,
        asset_refs: ["asset-scan-1"],
    });
    assert.equal(assetEnvelopeWrite.ok, true);
    assert.deepEqual(Array.from(assetEnvelopeWrite.value.asset_refs), ["asset-scan-1"]);
    assert.equal(JSON.stringify(assetEnvelopeWrite.value.payload).includes("blob:"), false);
    assert.equal(JSON.stringify(assetEnvelopeWrite.value.payload).includes("data:image"), false);

    const assetRepository = Recovery.LocalAssetRepository.create({ gateway });
    const sourceBlob = new Blob(["scanner bytes"], { type: "image/jpeg" });
    const assetWrite = await assetRepository.write(newIdentity, "asset-scan-1", sourceBlob, {
        file_name: "scan.jpg",
    });
    assert.equal(assetWrite.ok, true);
    assert.equal(assetWrite.value.byte_length, sourceBlob.size);
    const assetRead = await assetRepository.read(newIdentity, "asset-scan-1");
    assert.equal(assetRead.ok, true);
    assert.equal(await assetRead.value.blob.text(), "scanner bytes");
    assert.equal(assetRead.value.mime_type, "image/jpeg");
    const assetStorageKey = [...gateway.records.dco_recovery_assets.keys()][0];
    const validAssetRecord = gateway.records.dco_recovery_assets.get(assetStorageKey);
    gateway.records.dco_recovery_assets.set(assetStorageKey, {
        ...validAssetRecord,
        content_hash: "0".repeat(64),
    });
    const corruptAsset = await assetRepository.read(newIdentity, "asset-scan-1");
    assert.equal(corruptAsset.ok, false);
    assert.equal(corruptAsset.error.code, "integrity_mismatch");
    gateway.records.dco_recovery_assets.set(assetStorageKey, validAssetRecord);
    assert.equal((await assetRepository.delete(newIdentity, "asset-scan-1")).value, true);
    assert.equal((await assetRepository.read(newIdentity, "asset-scan-1")).value, null);

    await assetRepository.write(newIdentity, "asset-cascade", sourceBlob);
    assert.equal(gateway.records.dco_recovery_assets.size, 1);
    assert.equal((await repository.delete(newIdentity)).value, true);
    assert.equal(gateway.records.dco_recovery_assets.size, 0);
    assert.equal((await repository.read(newIdentity)).value, null);

    const editKey = repository.storageKey(editIdentity);
    const validEditRecord = gateway.records.dco_recovery_drafts.get(editKey);
    gateway.records.dco_recovery_drafts.set(editKey, { ...validEditRecord, payload_hash: "0".repeat(64) });
    const corruptRead = await repository.read(editIdentity);
    assert.equal(corruptRead.ok, false);
    assert.equal(corruptRead.error.code, "integrity_mismatch");
    gateway.records.dco_recovery_drafts.set(editKey, { ...validEditRecord, schema_version: 999 });
    const unknownRead = await repository.read(editIdentity);
    assert.equal(unknownRead.ok, false);
    assert.equal(unknownRead.error.code, "unknown_schema");
    gateway.records.dco_recovery_drafts.set(editKey, { ...validEditRecord, schema_version: 0 });
    const oldRead = await repository.read(editIdentity);
    assert.equal(oldRead.ok, false);
    assert.equal(oldRead.error.code, "incompatible_schema");

    gateway.failNext("api_unavailable");
    const unavailable = await repository.read(editIdentity);
    assert.equal(unavailable.ok, false);
    assert.equal(unavailable.error.code, "api_unavailable");
    gateway.failNext("quota_exceeded");
    const quota = await repository.write({
        ...editIdentity,
        mode: "EDIT",
        dirty_scope: "DCO",
        target_name: "DCO-2026-00001",
        session_origin_modified: "2026-08-29 08:00:00.000000",
        expected_server_modified: "2026-08-29 09:00:00.000000",
        tab_session_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        recovery_revision: 2,
        payload: dcoPayload("ROW-EXISTING"),
        asset_refs: [],
    });
    assert.equal(quota.ok, false);
    assert.equal(quota.error.code, "quota_exceeded");

    const missingDraftAsset = await assetRepository.write(
        { ...newIdentity, draft_id: "missing-draft" },
        "asset-orphan",
        sourceBlob
    );
    assert.equal(missingDraftAsset.ok, false);
    assert.equal(missingDraftAsset.error.code, "draft_not_found");

    const smallRepository = Recovery.LocalDraftRepository.create({
        gateway,
        maxPayloadBytes: 1024,
        TextEncoder,
    });
    const oversizedDco = dcoProjection("oversized-piece");
    oversizedDco.order_notes = "x".repeat(2048);
    const oversizedPayload = Recovery.Projection.createPayload({
        dco: oversizedDco,
        dirtyScope: "DCO",
    });
    const oversizedWrite = await smallRepository.write({
        ...editIdentity,
        mode: "EDIT",
        dirty_scope: "DCO",
        target_name: "DCO-2026-00001",
        session_origin_modified: "2026-08-29 08:00:00.000000",
        expected_server_modified: "2026-08-29 09:00:00.000000",
        tab_session_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        recovery_revision: 3,
        payload: oversizedPayload,
        asset_refs: [],
    });
    assert.equal(oversizedWrite.ok, false);
    assert.equal(oversizedWrite.error.code, "payload_too_large");

    const smallAssetRepository = Recovery.LocalAssetRepository.create({
        gateway,
        maxAssetBytes: 1024,
    });
    const oversizedAsset = await smallAssetRepository.write(
        editIdentity,
        "asset-too-large",
        new Blob(["x".repeat(1025)], { type: "image/jpeg" })
    );
    assert.equal(oversizedAsset.ok, false);
    assert.equal(oversizedAsset.error.code, "asset_too_large");

    console.log("DCO local recovery repository simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
