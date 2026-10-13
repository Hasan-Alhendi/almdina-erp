from __future__ import annotations

import json
import os
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


REPOSITORY = Path(__file__).resolve().parents[2]
RECOVERY = REPOSITORY / "almdina_erp/public/js/door_cutting_order/recovery"
SCRIPTS = (
    RECOVERY / "application/door_cutting_order_recovery_projection.js",
    RECOVERY / "infrastructure/door_cutting_order_recovery_indexeddb.js",
    RECOVERY / "infrastructure/door_cutting_order_local_draft_repository.js",
    RECOVERY / "infrastructure/door_cutting_order_local_asset_repository.js",
    RECOVERY / "application/door_cutting_order_checkpoint_session.js",
)


class QuietRepositoryHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(REPOSITORY), **kwargs)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture(scope="session")
def local_origin() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietRepositoryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.fixture(scope="session")
def playwright_instance() -> Iterator[Playwright]:
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def chromium(playwright_instance: Playwright) -> Iterator[Browser]:
    executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
    args = ["--no-sandbox"] if os.geteuid() == 0 else []
    browser = playwright_instance.chromium.launch(
        headless=True,
        executable_path=executable,
        args=args,
    )
    try:
        yield browser
    finally:
        browser.close()


def recovery_page(context: BrowserContext, local_origin: str) -> Page:
    page = context.new_page()
    page.goto(local_origin, wait_until="domcontentloaded")
    for script in SCRIPTS:
        page.add_script_tag(path=str(script))
    return page


def test_chromium_checkpoint_payload_size_persistence_cas_and_assets(
    chromium: Browser, local_origin: str
) -> None:
    context = chromium.new_context()
    page = recovery_page(context, local_origin)
    try:
        measured = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const repo = recovery.LocalDraftRepository.create();
                const scenarios = [];
                for (const count of [200, 500]) {
                    const longNotes = count === 500 ? 2048 : 512;
                    const pieces = Array.from({ length: count }, (_, index) => ({
                        piece_type: index === 0 ? "Special" : "Liner",
                        width_cm: 60,
                        length_cm: 200,
                        qty: 1,
                        notes: "N".repeat(longNotes),
                        special_shape_drawing_json: index === 0
                            ? JSON.stringify({ elements: [{ path: "D".repeat(280000) }] })
                            : "",
                        special_shape_geometry_json: index === 0
                            ? JSON.stringify({ geometry: "G".repeat(45000) })
                            : "",
                    }));
                    const dco = recovery.Projection.createDcoInput({
                        customer: "Synthetic capacity test",
                        order_notes: "O".repeat(20000),
                        pieces,
                    }, { pieceKey: (_, index) => "piece-" + index });
                    const payload = recovery.Projection.createPayload({
                        dco,
                        dirtyScope: "DCO",
                    });
                    const bytes = new TextEncoder().encode(
                        recovery.Projection.serialize(payload)
                    ).byteLength;
                    const input = {
                        site: location.host,
                        user: "chromium-size-test",
                        draft_id: "payload-" + count,
                        tab_session_id: "tab-size-test",
                        mode: "NEW",
                        dirty_scope: "DCO",
                        recovery_revision: 1,
                        expected_recovery_revision: 0,
                        payload,
                    };
                    const timings = [];
                    let result;
                    for (let sample = 0; sample < 7; sample += 1) {
                        const started = performance.now();
                        result = await repo.write({
                            ...input,
                            draft_id: input.draft_id + "-" + sample,
                        });
                        timings.push(performance.now() - started);
                    }
                    scenarios.push({
                        rows: count,
                        bytes,
                        accepted: result.ok,
                        error: result.error && result.error.code || null,
                        p95WriteMs: timings.sort((a, b) => a - b)[Math.ceil(timings.length * .95) - 1],
                    });
                }
                const cap = recovery.LocalDraftRepository.DEFAULT_MAX_PAYLOAD_BYTES;
                const configurable = recovery.LocalDraftRepository.create({
                    maxPayloadBytes: 1024 * 1024,
                });
                return { scenarios, cap, configurableCap: configurable.maxPayloadBytes };
            }"""
        )
        assert measured["scenarios"][0]["bytes"] == 479745
        assert measured["scenarios"][1]["bytes"] == 1449645
        assert all(case["accepted"] for case in measured["scenarios"])
        assert all(case["p95WriteMs"] <= 2000 for case in measured["scenarios"])
        assert measured["cap"] == 1792 * 1024
        assert measured["configurableCap"] == 1024 * 1024
        print(f"RECOVERY_CHROMIUM_MEASUREMENTS {measured}")

        page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const repo = recovery.LocalDraftRepository.create();
                const identity = {
                    site: location.host,
                    user: "chromium-durable-test",
                    draft_id: "refresh-close-reopen",
                    tab_session_id: "tab-one",
                    mode: "NEW",
                    dirty_scope: "DCO",
                    recovery_revision: 1,
                    expected_recovery_revision: 0,
                };
                const dco = recovery.Projection.createDcoInput({
                    customer: "Persistent customer",
                    pieces: [{ piece_type: "Liner", qty: 4, notes: "persisted" }],
                }, { pieceKey: () => "piece-1" });
                const payload = recovery.Projection.createPayload({ dco, dirtyScope: "DCO" });
                const first = await repo.write({ ...identity, payload });
                if (!first.ok) throw new Error(first.error.code);
                const asset = await recovery.LocalAssetRepository.create().write(
                    identity,
                    "drawing-1",
                    new Blob(["durable drawing bytes"], { type: "application/json" }),
                    { file_name: "drawing.json" }
                );
                if (!asset.ok) throw new Error(asset.error.code);
                return { first: first.ok, asset: asset.value };
            }"""
        )
        page.close()
        page = context.new_page()
        page.goto(local_origin, wait_until="domcontentloaded")
        for script in SCRIPTS[:4]:
            page.add_script_tag(path=str(script))
        persisted = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const identity = {
                    site: location.host,
                    user: "chromium-durable-test",
                    draft_id: "refresh-close-reopen",
                };
                const draft = await recovery.LocalDraftRepository.create().read(identity);
                const asset = await recovery.LocalAssetRepository.create().read(identity, "drawing-1");
                return {
                    draftOk: draft.ok,
                    customer: draft.value && draft.value.payload.dco.customer,
                    pieceQty: draft.value && draft.value.payload.dco.pieces[0].qty,
                    assetOk: asset.ok,
                    assetText: asset.value && await asset.value.blob.text(),
                };
            }"""
        )
        assert persisted == {
            "draftOk": True,
            "customer": "Persistent customer",
            "pieceQty": 4,
            "assetOk": True,
            "assetText": "durable drawing bytes",
        }

        second_tab = recovery_page(context, local_origin)
        cas = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const repo = recovery.LocalDraftRepository.create();
                const base = {
                    site: location.host,
                    user: "chromium-durable-test",
                    draft_id: "refresh-close-reopen",
                    tab_session_id: "tab-one",
                    mode: "NEW",
                    dirty_scope: "DCO",
                    recovery_revision: 2,
                    expected_recovery_revision: 1,
                };
                const payload = (customer) => recovery.Projection.createPayload({
                    dco: recovery.Projection.createDcoInput(
                        { customer, pieces: [] },
                        { pieceKey: () => "unused" }
                    ),
                    dirtyScope: "DCO",
                });
                const left = { ...base, payload: payload("left") };
                const right = { ...base, payload: payload("right"), tab_session_id: "tab-two" };
                const results = await Promise.all([repo.write(left), repo.write(right)]);
                const accepted = results.filter((result) => result.ok);
                const rejected = results.filter((result) => !result.ok);
                return {
                    accepted: accepted.length,
                    rejected: rejected.length,
                    rejectCode: rejected[0] && rejected[0].error.code,
                    winner: (await repo.read(base)).value.payload.dco.customer,
                };
            }"""
        )
        assert cas["accepted"] == 1
        assert cas["rejected"] == 1
        assert cas["rejectCode"] in {"revision_conflict", "stale_revision"}
        assert cas["winner"] in {"left", "right"}
        second_tab.close()

        injected = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const repo = recovery.LocalDraftRepository.create();
                const identity = {
                    site: location.host,
                    user: "chromium-durable-test",
                    draft_id: "quota-rejected",
                    tab_session_id: "quota-tab",
                    mode: "NEW",
                    dirty_scope: "DCO",
                    recovery_revision: 1,
                    expected_recovery_revision: 0,
                    payload: recovery.Projection.createPayload({
                        dco: recovery.Projection.createDcoInput(
                            { customer: "quota", pieces: [] },
                            { pieceKey: () => "unused" }
                        ),
                        dirtyScope: "DCO",
                    }),
                };
                const acknowledged = await repo.write(identity);
                if (!acknowledged.ok) throw new Error("baseline checkpoint was not acknowledged");
                const originalPut = IDBObjectStore.prototype.put;
                IDBObjectStore.prototype.put = function (...args) {
                    if (this.name === recovery.IndexedDb.DRAFT_STORE) {
                        throw new DOMException("Injected Chromium quota exhaustion", "QuotaExceededError");
                    }
                    return originalPut.apply(this, args);
                };
                const quota = await repo.write({
                    ...identity,
                    recovery_revision: 2,
                    expected_recovery_revision: 1,
                });
                IDBObjectStore.prototype.put = originalPut;
                const rejected = await repo.read(identity);
                const gateway = recovery.IndexedDb.createGateway();
                let abortCode = "";
                try {
                    await gateway.transaction(
                        [recovery.IndexedDb.DRAFT_STORE],
                        "readwrite",
                        (stores) => {
                            stores[recovery.IndexedDb.DRAFT_STORE].put({
                                storage_key: "failed-atomic-write",
                                partial: true,
                            });
                            throw new Error("Injected transaction failure");
                        }
                    );
                } catch (error) {
                    abortCode = error.code;
                }
                const noPartial = await gateway.transaction(
                    [recovery.IndexedDb.DRAFT_STORE],
                    "readonly",
                    (stores, request) => request(
                        stores[recovery.IndexedDb.DRAFT_STORE].get("failed-atomic-write")
                    )
                );
                const corruptId = { ...identity, draft_id: "corrupt-preserved" };
                const valid = await repo.write(corruptId);
                const database = await gateway.open();
                await new Promise((resolve, reject) => {
                    const tx = database.transaction(recovery.IndexedDb.DRAFT_STORE, "readwrite");
                    const store = tx.objectStore(recovery.IndexedDb.DRAFT_STORE);
                    const key = repo.storageKey(corruptId);
                    const get = store.get(key);
                    get.onsuccess = () => {
                        const record = get.result;
                        record.payload_hash = "0".repeat(64);
                        store.put(record);
                    };
                    tx.oncomplete = resolve;
                    tx.onerror = () => reject(tx.error);
                });
                const corrupt = await repo.read(corruptId);
                const raw = await gateway.transaction(
                    [recovery.IndexedDb.DRAFT_STORE],
                    "readonly",
                    (stores, request) => request(
                        stores[recovery.IndexedDb.DRAFT_STORE].get(repo.storageKey(corruptId))
                    )
                );
                return {
                    quota: quota.error && quota.error.code,
                    acknowledgedCheckpointPreserved: rejected.ok
                        && rejected.value.recovery_revision === 1,
                    validWrite: valid.ok,
                    abortCode,
                    partialWriteAbsent: noPartial === undefined,
                    corruptionCode: corrupt.error && corrupt.error.code,
                    corruptRecordPreserved: raw.payload_hash === "0".repeat(64),
                };
            }"""
        )
        assert injected == {
            "quota": "quota_exceeded",
            "acknowledgedCheckpointPreserved": True,
            "validWrite": True,
            "abortCode": "transaction_failure",
            "partialWriteAbsent": True,
            "corruptionCode": "integrity_mismatch",
            "corruptRecordPreserved": True,
        }
    finally:
        context.close()


def test_chromium_draft_reads_and_discovery_are_scoped_by_site_and_user(
    chromium: Browser, local_origin: str
) -> None:
    context = chromium.new_context()
    page = recovery_page(context, local_origin)
    try:
        scoped = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const repo = recovery.LocalDraftRepository.create();
                const owners = [
                    { site: "tenant-a.example", user: "operator-a", label: "A at tenant A" },
                    { site: "tenant-a.example", user: "operator-b", label: "B at tenant A" },
                    { site: "tenant-b.example", user: "operator-a", label: "A at tenant B" },
                ];
                const draftId = "shared-draft-id";
                const writes = [];
                for (const [index, owner] of owners.entries()) {
                    const dco = recovery.Projection.createDcoInput(
                        { customer: owner.label, pieces: [] },
                        { pieceKey: () => "unused" }
                    );
                    const payload = recovery.Projection.createPayload({ dco, dirtyScope: "DCO" });
                    writes.push(await repo.write({
                        ...owner,
                        draft_id: draftId,
                        tab_session_id: "tab-" + index,
                        mode: "NEW",
                        dirty_scope: "DCO",
                        recovery_revision: 1,
                        expected_recovery_revision: 0,
                        payload,
                    }));
                }
                const checks = [];
                for (const owner of owners) {
                    const identity = { ...owner, draft_id: draftId };
                    const [read, discovery] = await Promise.all([
                        repo.read(identity),
                        repo.discover({ ...identity, mode: "NEW" }),
                    ]);
                    checks.push({
                        label: owner.label,
                        readLabel: read.value && read.value.payload.dco.customer,
                        records: discovery.value.records.map(record => record.payload.dco.customer),
                        rejected: discovery.value.rejected.length,
                    });
                }
                return {
                    writes: writes.map(result => result.ok),
                    keys: owners.map(owner => repo.storageKey({ ...owner, draft_id: draftId })),
                    checks,
                };
            }"""
        )
        assert scoped["writes"] == [True, True, True]
        assert len(set(scoped["keys"])) == 3
        assert scoped["checks"] == [
            {"label": "A at tenant A", "readLabel": "A at tenant A", "records": ["A at tenant A"], "rejected": 0},
            {"label": "B at tenant A", "readLabel": "B at tenant A", "records": ["B at tenant A"], "rejected": 0},
            {"label": "A at tenant B", "readLabel": "A at tenant B", "records": ["A at tenant B"], "rejected": 0},
        ]
    finally:
        context.close()


def test_chromium_recovery_survives_full_browser_restart(
    playwright_instance: Playwright, local_origin: str, tmp_path: Path
) -> None:
    executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
    args = ["--no-sandbox"] if os.geteuid() == 0 else []
    profile = str(tmp_path / "chromium-profile")
    context = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=profile,
        headless=True,
        executable_path=executable,
        args=args,
    )
    try:
        page = context.new_page()
        page.goto(local_origin, wait_until="domcontentloaded")
        for script in SCRIPTS:
            page.add_script_tag(path=str(script))
        saved = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const identity = {
                    site: location.host,
                    user: "chromium-restart-test",
                    draft_id: "full-browser-restart",
                    tab_session_id: "persistent-profile-tab",
                    mode: "NEW",
                    dirty_scope: "DCO",
                    recovery_revision: 1,
                    expected_recovery_revision: 0,
                };
                const payload = recovery.Projection.createPayload({
                    dco: recovery.Projection.createDcoInput(
                        { customer: "Persisted across browser close", pieces: [] },
                        { pieceKey: () => "unused" }
                    ),
                    dirtyScope: "DCO",
                });
                const draft = await recovery.LocalDraftRepository.create().write({
                    ...identity,
                    payload,
                });
                const asset = await recovery.LocalAssetRepository.create().write(
                    identity,
                    "restart-drawing",
                    new Blob(["persisted blob bytes"], { type: "application/json" }),
                    { file_name: "drawing.json" }
                );
                return { draftAcknowledged: draft.ok, assetAcknowledged: asset.ok };
            }"""
        )
    finally:
        context.close()

    reopened = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=profile,
        headless=True,
        executable_path=executable,
        args=args,
    )
    try:
        page = reopened.new_page()
        page.goto(local_origin, wait_until="domcontentloaded")
        for script in SCRIPTS:
            page.add_script_tag(path=str(script))
        persisted = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const identity = {
                    site: location.host,
                    user: "chromium-restart-test",
                    draft_id: "full-browser-restart",
                };
                const draft = await recovery.LocalDraftRepository.create().read(identity);
                const asset = await recovery.LocalAssetRepository.create().read(
                    identity,
                    "restart-drawing"
                );
                return {
                    draftOk: draft.ok,
                    customer: draft.value && draft.value.payload.dco.customer,
                    assetOk: asset.ok,
                    assetText: asset.value && await asset.value.blob.text(),
                };
            }"""
        )
    finally:
        reopened.close()

    assert saved == {"draftAcknowledged": True, "assetAcknowledged": True}
    assert persisted == {
        "draftOk": True,
        "customer": "Persisted across browser close",
        "assetOk": True,
        "assetText": "persisted blob bytes",
    }


def test_chromium_schema_upgrade_preserves_legacy_scope_records(
    local_origin: str, chromium: Browser
) -> None:
    context = chromium.new_context()
    page = recovery_page(context, local_origin)
    try:
        results = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const dbName = recovery.IndexedDb.DATABASE_NAME;
                const openV1 = () => new Promise((resolve, reject) => {
                    const request = indexedDB.open(dbName, 1);
                    request.onupgradeneeded = () => {
                        request.result.createObjectStore(recovery.IndexedDb.DRAFT_STORE, { keyPath: "storage_key" });
                        request.result.createObjectStore(recovery.IndexedDb.ASSET_STORE, { keyPath: "storage_key" });
                    };
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                });
                const initial = await openV1();
                initial.close();
                const connections = new Set();
                const legacyIndexedDb = {
                    open(name) {
                        const request = indexedDB.open(name, 1);
                        request.addEventListener("success", () => connections.add(request.result));
                        return request;
                    },
                };
                const legacyRepo = recovery.LocalDraftRepository.create({ indexedDB: legacyIndexedDb });
                for (const scope of ["DCO", "PLAN", "COST", "SPECIAL_SHAPE"]) {
                    const dco = recovery.Projection.createDcoInput(
                        { customer: scope, pieces: [] },
                        { pieceKey: () => "unused" }
                    );
                    const plan = scope === "PLAN"
                        ? recovery.Projection.createPlanWorkspaceDraft({
                            editing: true, dirty: true, baseline: {}, draft: { kerf_mm: 4 },
                        }, { normalized_settings_hash: "baseline-plan" })
                        : null;
                    const cost = scope === "COST"
                        ? recovery.Projection.createCostWorkspaceDraft({
                            editing: true, dirty: true, baseline: {}, draft: { board_rate_usd: 9 },
                        }, { normalized_settings_hash: "baseline-cost" })
                        : null;
                    const special = scope === "SPECIAL_SHAPE"
                        ? [recovery.Projection.createSpecialShapeDraft({
                            order_name: "DCO-LEGACY", piece_name: "DCO-LEGACY-ROW",
                            document: { schema: "special-shape", version: 1, elements: [] },
                        })]
                        : [];
                    const payload = recovery.Projection.createPayload({
                        dco, dirtyScope: scope, planWorkspaceDraft: plan,
                        costWorkspaceDraft: cost, specialShapeDrafts: special,
                    });
                    const written = await legacyRepo.write({
                        site: location.host, user: "legacy-user", draft_id: "legacy-" + scope,
                        tab_session_id: "legacy-tab", mode: "NEW", dirty_scope: scope,
                        recovery_revision: 1, expected_recovery_revision: 0, payload,
                    });
                    if (!written.ok) throw new Error(scope + ":" + written.error.code);
                    const database = [...connections].at(-1);
                    const key = legacyRepo.storageKey({
                        site: location.host, user: "legacy-user", draft_id: "legacy-" + scope,
                    });
                    await new Promise((resolve, reject) => {
                        const tx = database.transaction(recovery.IndexedDb.DRAFT_STORE, "readwrite");
                        const store = tx.objectStore(recovery.IndexedDb.DRAFT_STORE);
                        const get = store.get(key);
                        get.onsuccess = () => {
                            const record = get.result;
                            record.schema_version = 1;
                            delete record.official_save_state;
                            delete record.official_save_attempted_at;
                            store.put(record);
                        };
                        tx.oncomplete = resolve;
                        tx.onerror = () => reject(tx.error);
                    });
                }
                const legacyAssetIdentity = {
                    site: location.host, user: "legacy-user", draft_id: "legacy-PLAN",
                };
                const legacyAsset = await recovery.LocalAssetRepository.create({
                    indexedDB: legacyIndexedDb,
                }).write(
                    legacyAssetIdentity,
                    "legacy-drawing",
                    new Blob(["legacy drawing bytes"], { type: "application/json" }),
                    { file_name: "legacy-drawing.json" }
                );
                if (!legacyAsset.ok) throw new Error("legacy asset:" + legacyAsset.error.code);
                const current = recovery.LocalDraftRepository.create();
                const blocker = await openV1();
                const blocked = await current.read({
                    site: location.host, user: "legacy-user", draft_id: "legacy-PLAN",
                });
                blocker.close();
                [...connections].forEach((database) => database.close());
                await new Promise((resolve) => setTimeout(resolve, 0));
                const planRecord = await current.read({
                    site: location.host, user: "legacy-user", draft_id: "legacy-PLAN",
                });
                const rawDb = await new Promise((resolve, reject) => {
                    const request = indexedDB.open(dbName);
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                });
                const names = Array.from(rawDb.objectStoreNames);
                const indexes = await new Promise((resolve, reject) => {
                    const tx = rawDb.transaction(recovery.IndexedDb.DRAFT_STORE, "readonly");
                    const store = tx.objectStore(recovery.IndexedDb.DRAFT_STORE);
                    tx.oncomplete = () => resolve(Array.from(store.indexNames));
                    tx.onerror = () => reject(tx.error);
                });
                rawDb.close();
                const otherScopes = [];
                for (const scope of ["DCO", "COST", "SPECIAL_SHAPE"]) {
                    const result = await current.read({
                        site: location.host, user: "legacy-user", draft_id: "legacy-" + scope,
                    });
                    otherScopes.push({
                        scope,
                        ok: result.ok,
                        schema: result.value && result.value.schema_version,
                        dirtyScope: result.value && result.value.dirty_scope,
                    });
                }
                const upgradedAsset = await recovery.LocalAssetRepository.create().read(
                    legacyAssetIdentity,
                    "legacy-drawing"
                );
                return {
                    version: recovery.IndexedDb.DATABASE_VERSION,
                    blockedCode: blocked.error && blocked.error.code,
                    names: names.sort(),
                    indexes: indexes.sort(),
                    planRead: planRecord.ok,
                    planSchema: planRecord.value && planRecord.value.schema_version,
                    planScope: planRecord.value && planRecord.value.dirty_scope,
                    assetOk: upgradedAsset.ok,
                    assetText: upgradedAsset.value && await upgradedAsset.value.blob.text(),
                    otherScopes,
                };
            }"""
        )
        assert results["version"] == 2
        assert results["blockedCode"] == "open_blocked"
        assert results["names"] == ["dco_recovery_assets", "dco_recovery_drafts"]
        assert results["indexes"] == ["captured_at", "namespace_key", "target_key"]
        assert results["planRead"] is True
        assert results["planSchema"] == 1
        assert results["planScope"] == "PLAN"
        assert results["assetOk"] is True
        assert results["assetText"] == "legacy drawing bytes"
        assert results["otherScopes"] == [
            {"scope": "DCO", "ok": True, "schema": 1, "dirtyScope": "DCO"},
            {"scope": "COST", "ok": True, "schema": 1, "dirtyScope": "COST"},
            {"scope": "SPECIAL_SHAPE", "ok": True, "schema": 1, "dirtyScope": "SPECIAL_SHAPE"},
        ]
    finally:
        context.close()


def test_chromium_presentation_checkpoints_direct_dco_mutations_and_reports_statuses(
    chromium: Browser, local_origin: str
) -> None:
    context = chromium.new_context()
    page = recovery_page(context, local_origin)
    try:
        page.set_content('<div id="form" class="form-layout"></div>')
        page.evaluate(
            """() => {
                window.__formHandlers = {};
                window.__pendingRecoveryFrame = null;
                window.AlmdinaDocumentContext = {
                    capture: (frm) => ({ identity: frm.doctype + "::" + frm.doc.name, generation: 1 }),
                    isSameDocument: (frm, token) => token.identity === frm.doctype + "::" + frm.doc.name,
                    formIdentity: (frm) => frm.doctype + "::" + frm.doc.name,
                    registerCleanup: () => true,
                    scheduleFrame: (_frm, _key, callback) => { window.__pendingRecoveryFrame = callback; },
                };
                window.AlmdinaOrderRevisionUX = { isEditSessionActive: () => true };
                window.frappe = {
                    boot: { sitename: location.host },
                    session: { user: "browser-operator" },
                    utils: { escape_html: (value) => String(value) },
                    datetime: {},
                    model: {
                        clear_table: (doc, field) => { doc[field] = []; },
                        add_child: (doc, _doctype, field) => {
                            const row = { name: "new-row", __islocal: 1 };
                            (doc[field] ||= []).push(row);
                            return row;
                        },
                    },
                    ui: { form: { on: (doctype, handlers) => {
                        window.__formHandlers[doctype] = { ...(window.__formHandlers[doctype] || {}), ...handlers };
                    } } },
                    show_alert: () => {},
                    msgprint: () => {},
                };
            }"""
        )
        page.add_script_tag(
            path=str(RECOVERY / "presentation/door_cutting_order_local_checkpoint.js")
        )
        page.evaluate(
            """() => {
                const wrapper = document.querySelector("#form");
                const frm = {
                    doctype: "Door Cutting Order",
                    doc: {
                        doctype: "Door Cutting Order",
                        name: "__new__",
                        pieces: [{
                            name: "new-row-1", __islocal: 1,
                            piece_type: "Liner", qty: 1, extra_liner: 0,
                            edge_long_left: 0, special_shape_geometry_json: "",
                        }],
                    },
                    wrapper,
                    is_new: () => true,
                };
                window.cur_frm = frm;
                window.__recoveryForm = frm;
                window.AlmdinaDcoRecovery.LocalCheckpoint.ensureState(frm);
            }"""
        )
        captured = page.evaluate(
            """async () => {
                const frm = window.__recoveryForm;
                const handlers = window.__formHandlers["Door Cutting Order Detail"];
                const cases = [
                    ["qty", 3, "fast measurement"],
                    ["edge_long_left", 1, "bulk edge"],
                    ["extra_liner", 1, "extra addon"],
                    ["special_shape_geometry_json", JSON.stringify({ points: [1, 2] }), "special geometry"],
                ];
                const results = [];
                for (const [index, [field, value, label]] of cases.entries()) {
                    frm.doc.pieces[0][field] = value;
                    handlers[field](frm);
                    if (index === cases.length - 1) {
                        window.dispatchEvent(new Event("pagehide"));
                        await new Promise((resolve) => setTimeout(resolve, 0));
                    }
                    const flushed = index === cases.length - 1
                        ? { ok: true }
                        : await window.AlmdinaDcoRecovery.LocalCheckpoint.flush(frm);
                    const current = await window.AlmdinaDcoRecovery.LocalCheckpoint.repository().read({
                        site: location.host,
                        user: "browser-operator",
                        draft_id: window.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(frm).draft_id,
                    });
                    if (!flushed.ok || !current.ok) throw new Error(label + ": checkpoint failed");
                    results.push({
                        label,
                        revision: current.value.recovery_revision,
                        value: current.value.payload.dco.pieces[0][field],
                    });
                }
                return {
                    results,
                    snapshot: window.AlmdinaDcoRecovery.LocalCheckpoint.snapshot(frm),
                    statusText: document.querySelector(".dco-recovery-status")?.textContent || "",
                    statusState: document.querySelector(".dco-recovery-status")?.dataset.recoveryState || "",
                };
            }"""
        )
        assert [entry["label"] for entry in captured["results"]] == [
            "fast measurement", "bulk edge", "extra addon", "special geometry",
        ]
        assert [entry["revision"] for entry in captured["results"]] == [1, 2, 3, 4]
        assert [entry["value"] for entry in captured["results"]] == [
            3, 1, 1, '{"points":[1,2]}',
        ]
        assert captured["snapshot"]["state"] == "LOCAL_SAVED"
        assert "تم تأكيد حفظ نسخة محلية" in captured["statusText"]
        assert "لم يُحفظ الطلب رسميًا" in captured["statusText"]

        official = page.evaluate(
            """async () => {
                await window.__formHandlers["Door Cutting Order"].before_save(window.__recoveryForm);
                const status = document.querySelector(".dco-recovery-status");
                return { state: status.dataset.recoveryState, text: status.textContent };
            }"""
        )
        assert official["state"] == "OFFICIAL_SAVING"
        assert "رسميًا على الخادم" in official["text"]

        failure = page.evaluate(
            """async () => {
                const wrapper = document.createElement("div");
                wrapper.id = "edit-form";
                wrapper.className = "form-layout";
                document.body.appendChild(wrapper);
                const frm = {
                    doctype: "Door Cutting Order",
                    doc: {
                        doctype: "Door Cutting Order",
                        name: "DCO-EDIT-1",
                        modified: "2026-10-11 07:00:00",
                        pieces: [{ name: "piece-1", piece_type: "Liner", qty: 1 }],
                    },
                    wrapper,
                    is_new: () => false,
                };
                window.cur_frm = frm;
                window.AlmdinaDcoRecovery.LocalCheckpoint.ensureState(frm);
                frm.doc.pieces[0].qty = 2;
                window.__formHandlers["Door Cutting Order Detail"].qty(frm);
                const originalPut = IDBObjectStore.prototype.put;
                IDBObjectStore.prototype.put = function (...args) {
                    if (this.name === window.AlmdinaDcoRecovery.IndexedDb.DRAFT_STORE) {
                        throw new DOMException("Injected quota exhaustion", "QuotaExceededError");
                    }
                    return originalPut.apply(this, args);
                };
                const flushed = await window.AlmdinaDcoRecovery.LocalCheckpoint.flush(frm);
                IDBObjectStore.prototype.put = originalPut;
                const status = wrapper.querySelector(".dco-recovery-status");
                return {
                    result: flushed.error && flushed.error.code,
                    state: status && status.dataset.recoveryState,
                    role: status && status.getAttribute("role"),
                    text: status && status.textContent,
                };
            }"""
        )
        assert failure["result"] == "quota_exceeded"
        assert failure["state"] == "ERROR"
        assert failure["role"] == "alert"
        assert "تعذر حفظ نسخة الاسترداد محليًا" in failure["text"]
    finally:
        context.close()


def test_chromium_repository_unavailable_status_is_removed_on_document_cleanup(
    chromium: Browser, local_origin: str
) -> None:
    context = chromium.new_context()
    page = recovery_page(context, local_origin)
    try:
        page.set_content('<div id="form" class="form-layout"></div>')
        page.evaluate(
            """() => {
                window.__documentCleanups = new Map();
                window.AlmdinaDocumentContext = {
                    capture: (frm) => ({ identity: frm.doctype + "::" + frm.doc.name, generation: 1 }),
                    isSameDocument: () => false,
                    formIdentity: (frm) => frm.doctype + "::" + frm.doc.name,
                    registerCleanup: (_frm, key, cleanup) => {
                        window.__documentCleanups.set(key, cleanup);
                        return true;
                    },
                    scheduleFrame: () => null,
                };
                window.AlmdinaOrderRevisionUX = { isEditSessionActive: () => true };
                window.AlmdinaDcoRecovery.LocalDraftRepository = null;
                window.frappe = {
                    boot: { sitename: location.host },
                    session: { user: "browser-operator" },
                    utils: { escape_html: (value) => String(value) },
                    datetime: {},
                    ui: { form: { on: () => {} } },
                    show_alert: () => {},
                    msgprint: () => {},
                };
            }"""
        )
        page.add_script_tag(
            path=str(RECOVERY / "presentation/door_cutting_order_local_checkpoint.js")
        )
        result = page.evaluate(
            """() => {
                const wrapper = document.querySelector("#form");
                const frm = {
                    doctype: "Door Cutting Order",
                    doc: {
                        doctype: "Door Cutting Order",
                        name: "DCO-EDIT-UNAVAILABLE",
                        modified: "2026-10-11 07:00:00",
                        pieces: [],
                    },
                    wrapper,
                    is_new: () => false,
                };
                window.AlmdinaDcoRecovery.LocalCheckpoint.ensureState(frm);
                const status = wrapper.querySelector(".dco-recovery-status");
                const cleanup = window.__documentCleanups.get("dco-local-recovery-error-status-cleanup");
                if (cleanup) cleanup();
                return {
                    errorState: status && status.dataset.recoveryState,
                    cleanupRegistered: Boolean(cleanup),
                    remainsAfterGenerationCleanup: Boolean(wrapper.querySelector(".dco-recovery-status")),
                };
            }"""
        )
        assert result["errorState"] == "ERROR"
        assert result["cleanupRegistered"] is True
        assert result["remainsAfterGenerationCleanup"] is False
    finally:
        context.close()


def test_chromium_native_origin_quota_preserves_acknowledged_checkpoint(
    playwright_instance: Playwright,
    local_origin: str,
    tmp_path: Path,
) -> None:
    """Exercise Chromium's real per-origin quota without patching IndexedDB."""
    profile = tmp_path / "al128-native-quota-profile"
    executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
    args = ["--no-sandbox"] if os.geteuid() == 0 else []
    context = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=True,
        executable_path=executable,
        args=args,
    )
    page: Page | None = None
    cdp = None
    override_removed = False
    quota_evidence: dict[str, object] | None = {
        "result": "NOT_TESTED",
        "profile_isolated": True,
        "origin": local_origin,
        "requested_quota_bytes": 1024 * 1024,
    }
    quota_assertions_passed = False
    try:
        page = recovery_page(context, local_origin)
        origin = local_origin
        cdp = context.new_cdp_session(page)
        cdp.send("Storage.enable")
        cdp.send("Storage.clearDataForOrigin", {"origin": origin, "storageTypes": "all"})
        cdp.send(
            "Storage.overrideQuotaForOrigin",
            {"origin": origin, "quotaSize": 1024 * 1024},
        )
        applied_quota = cdp.send("Storage.getUsageAndQuota", {"origin": origin})
        assert applied_quota["quota"] == 1024 * 1024
        assert applied_quota["overrideActive"] is True
        quota_evidence.update(
            {
                "applied_quota_bytes": applied_quota["quota"],
                "storage_usage_bytes_at_application": applied_quota["usage"],
                "override_active": applied_quota["overrideActive"],
            }
        )

        page.set_content('<div id="form" class="form-layout"></div>')
        page.evaluate(
            """() => {
                window.__formHandlers = {};
                window.AlmdinaDocumentContext = {
                    capture: frm => ({ identity: frm.doctype + "::" + frm.doc.name, generation: 1 }),
                    isSameDocument: (frm, token) => token.identity === frm.doctype + "::" + frm.doc.name,
                    formIdentity: frm => frm.doctype + "::" + frm.doc.name,
                    registerCleanup: () => true,
                    scheduleFrame: (_frm, _key, callback) => requestAnimationFrame(callback),
                };
                window.AlmdinaOrderRevisionUX = { isEditSessionActive: () => true };
                window.frappe = {
                    boot: { sitename: location.host },
                    session: { user: "al128-quota-operator" },
                    utils: { escape_html: value => String(value) },
                    datetime: {},
                    model: {
                        clear_table: (doc, field) => { doc[field] = []; },
                        add_child: (doc, _doctype, field) => {
                            const row = { name: "quota-row", __islocal: 1 };
                            (doc[field] ||= []).push(row);
                            return row;
                        },
                    },
                    ui: { form: { on: (doctype, handlers) => {
                        window.__formHandlers[doctype] = {
                            ...(window.__formHandlers[doctype] || {}),
                            ...handlers,
                        };
                    } } },
                    show_alert: () => {},
                    msgprint: () => {},
                };
            }"""
        )
        page.add_script_tag(
            path=str(RECOVERY / "presentation/door_cutting_order_local_checkpoint.js")
        )
        checkpoint = page.evaluate(
            """async () => {
                const wrapper = document.querySelector("#form");
                const row = {
                    name: "quota-row-1",
                    piece_type: "Regular",
                    width_cm: 60,
                    length_cm: 100,
                    qty: 1,
                    notes: "",
                };
                const frm = {
                    doctype: "Door Cutting Order",
                    doc: {
                        doctype: "Door Cutting Order",
                        name: "DCO-AL128-QUOTA",
                        modified: "2026-10-13 00:00:00",
                        customer: "Quota Test Customer",
                        pieces: [row],
                    },
                    wrapper,
                    is_new: () => false,
                };
                window.cur_frm = frm;
                window.__quotaForm = frm;
                const owner = window.AlmdinaDcoRecovery.LocalCheckpoint;
                owner.ensureState(frm);
                const handlers = window.__formHandlers["Door Cutting Order Detail"];
                const randomText = length => {
                    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
                    const output = new Array(length);
                    const bytes = new Uint8Array(65536);
                    for (let offset = 0; offset < length; offset += bytes.length) {
                        const count = Math.min(bytes.length, length - offset);
                        crypto.getRandomValues(bytes.subarray(0, count));
                        for (let index = 0; index < count; index += 1) {
                            output[offset + index] = alphabet[bytes[index] % alphabet.length];
                        }
                    }
                    return output.join("");
                };
                row.notes = randomText(120000);
                handlers.notes(frm);
                const acknowledged = await owner.flush(frm);
                const firstSnapshot = owner.snapshot(frm);
                const identity = {
                    site: location.host,
                    user: frappe.session.user,
                    target_doctype: "Door Cutting Order",
                    draft_id: firstSnapshot.draft_id,
                };
                const firstRecord = await owner.repository().read(identity);
                if (!acknowledged.ok || !firstRecord.ok) {
                    throw new Error("Initial native-quota checkpoint was not acknowledged");
                }

                row.notes = randomText(1450000);
                handlers.notes(frm);
                const failedWrite = await owner.flush(frm);
                const failedSnapshot = owner.snapshot(frm);
                const preserved = await owner.repository().read(identity);
                const failedStatus = wrapper.querySelector(".dco-recovery-status");
                let nativeFailure = { name: "", code: "" };
                try {
                    const gateway = window.AlmdinaDcoRecovery.IndexedDb.createGateway();
                    await gateway.transaction(
                        [window.AlmdinaDcoRecovery.IndexedDb.DRAFT_STORE],
                        "readwrite",
                        stores => stores[window.AlmdinaDcoRecovery.IndexedDb.DRAFT_STORE].put({
                            storage_key: "native-quota-evidence-only",
                            namespace_key: "native-quota-evidence-only",
                            payload: randomText(1450000),
                        })
                    );
                } catch (error) {
                    nativeFailure = {
                        name: String(error && error.cause && error.cause.name || error.name || ""),
                        code: String(error && error.code || ""),
                    };
                }
                return {
                    initialAcknowledged: acknowledged.ok,
                    firstRevision: firstSnapshot.saved_revision,
                    firstRecordRevision: firstRecord.value.recovery_revision,
                    firstNotesLength: firstRecord.value.payload.dco.pieces[0].notes.length,
                    failedCode: failedWrite.error && failedWrite.error.code,
                    failedState: failedSnapshot.state,
                    failedRevision: failedSnapshot.recovery_revision,
                    savedRevisionAfterFailure: failedSnapshot.saved_revision,
                    preservedRevision: preserved.value && preserved.value.recovery_revision,
                    preservedNotesLength: preserved.value && preserved.value.payload.dco.pieces[0].notes.length,
                    statusState: failedStatus && failedStatus.dataset.recoveryState,
                    statusRole: failedStatus && failedStatus.getAttribute("role"),
                    statusText: failedStatus && failedStatus.textContent,
                    nativeFailure,
                    failedCheckpointPayloadBytes: new TextEncoder().encode(
                        window.AlmdinaDcoRecovery.Projection.serialize(
                            window.AlmdinaDcoRecovery.Projection.createPayload({
                                dco: window.AlmdinaDcoRecovery.Projection.createDcoInput(
                                    { customer: "Quota Test Customer", pieces: [row] },
                                    { pieceKey: () => row.name }
                                ),
                                dirtyScope: "DCO",
                            })
                        )
                    ).byteLength,
                };
            }"""
        )
        quota_evidence["checkpoint"] = {
            "initial_acknowledged": checkpoint["initialAcknowledged"],
            "acknowledged_revision": checkpoint["firstRevision"],
            "failed_code": checkpoint["failedCode"],
            "failed_state": checkpoint["failedState"],
            "failed_revision": checkpoint["failedRevision"],
            "saved_revision_after_failure": checkpoint["savedRevisionAfterFailure"],
            "preserved_revision": checkpoint["preservedRevision"],
            "preserved_data_length": checkpoint["preservedNotesLength"],
            "failed_payload_bytes": checkpoint["failedCheckpointPayloadBytes"],
            "native_error_name": checkpoint["nativeFailure"]["name"],
            "native_error_code": checkpoint["nativeFailure"]["code"],
            "user_status": checkpoint["statusState"],
            "user_status_role": checkpoint["statusRole"],
            "user_status_text": checkpoint["statusText"],
        }
        assert checkpoint["initialAcknowledged"] is True
        assert checkpoint["firstRevision"] == checkpoint["firstRecordRevision"] == 1
        assert checkpoint["firstNotesLength"] == 120000
        assert checkpoint["failedCode"] == "quota_exceeded"
        assert checkpoint["failedState"] == "ERROR"
        assert checkpoint["failedRevision"] == 2
        assert checkpoint["savedRevisionAfterFailure"] == 1
        assert checkpoint["preservedRevision"] == 1
        assert checkpoint["preservedNotesLength"] == 120000
        assert checkpoint["statusState"] == "ERROR"
        assert checkpoint["statusRole"] == "alert"
        assert "تعذر حفظ نسخة الاسترداد محليًا" in checkpoint["statusText"]
        assert checkpoint["nativeFailure"] == {
            "name": "QuotaExceededError",
            "code": "quota_exceeded",
        }
        assert checkpoint["failedCheckpointPayloadBytes"] < 1792 * 1024
        assert applied_quota["usage"] < applied_quota["quota"]

        cdp.send("Storage.clearDataForOrigin", {"origin": origin, "storageTypes": "all"})
        cdp.send("Storage.overrideQuotaForOrigin", {"origin": origin})
        removed_quota = cdp.send("Storage.getUsageAndQuota", {"origin": origin})
        override_removed = removed_quota["overrideActive"] is False
        assert override_removed is True
        quota_evidence["override_removed"] = override_removed
        quota_assertions_passed = True
    finally:
        if cdp is not None and not override_removed:
            try:
                cdp.send("Storage.overrideQuotaForOrigin", {"origin": local_origin})
                removed_quota = cdp.send("Storage.getUsageAndQuota", {"origin": local_origin})
                override_removed = removed_quota["overrideActive"] is False
            except Exception:
                pass
        cleanup_errors: list[str] = []
        try:
            context.close()
        except Exception as error:
            cleanup_errors.append(f"browser_context_close: {error}")
        if profile.exists():
            try:
                shutil.rmtree(profile)
            except OSError as error:
                cleanup_errors.append(f"profile_removal: {error}")
        if quota_evidence is not None:
            quota_evidence["override_removed"] = override_removed
            quota_evidence["profile_removed_after_close"] = not profile.exists()
            quota_evidence["cleanup_errors"] = cleanup_errors
            quota_evidence["test_assertions_passed"] = quota_assertions_passed
            has_applied_override = "applied_quota_bytes" in quota_evidence
            quota_evidence["result"] = (
                "PASS"
                if quota_assertions_passed
                and override_removed
                and quota_evidence["profile_removed_after_close"]
                and not cleanup_errors
                else "NOT_CONFIRMED" if has_applied_override else "NOT_TESTED"
            )
            evidence_path = Path(os.environ.get("RUNNER_TEMP", str(tmp_path))) / "al128-native-quota-evidence.json"
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(
                json.dumps(quota_evidence, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"AL128_NATIVE_QUOTA_EVIDENCE {quota_evidence}")
            if cleanup_errors or not quota_evidence["profile_removed_after_close"] or not override_removed:
                raise AssertionError("The native-quota override or isolated profile was not cleaned up.")
