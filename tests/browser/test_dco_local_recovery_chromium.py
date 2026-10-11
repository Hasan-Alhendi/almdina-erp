from __future__ import annotations

import os
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


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
def chromium() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
        args = ["--no-sandbox"] if os.geteuid() == 0 else []
        browser = playwright.chromium.launch(
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


def test_chromium_new_recovery_discovery_hydration_and_pending_reconciliation_ui(
    chromium: Browser, local_origin: str
) -> None:
    """Exercise real browser storage/presentation; the Frappe port is a test double."""
    context = chromium.new_context()
    page = recovery_page(context, local_origin)
    try:
        seeded = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const repo = recovery.LocalDraftRepository.create();
                const assets = recovery.LocalAssetRepository.create();
                const identity = { site: location.host, user: "new-flow-user" };
                const makePieces = (count, prefix) => Array.from({ length: count }, (_, index) => ({
                    piece_type: index === count - 1 ? "Special" : "Liner",
                    qty: index === 0 ? 2 : 1,
                    width_cm: 60,
                    length_cm: 200,
                    notes: index === 0 ? "ملاحظة طويلة ".repeat(300) : "",
                    extra_liner: index === 0 ? 1 : 0,
                    edge_long_left: index === 0 ? 1 : 0,
                    special_shape_drawing_json: index === count - 1
                        ? JSON.stringify({ elements: [{ id: prefix + "-drawing" }] }) : "",
                    special_shape_geometry_json: index === count - 1
                        ? JSON.stringify({ path: "M0 0 L1200 400 Z" }) : "",
                }));
                const result = {};
                for (const [draftId, customer, count] of [
                    ["90000000-0000-4000-8000-000000000001", "مسودة للحذف", 2],
                    ["90000000-0000-4000-8000-000000000002", "مسودة للاستكمال", 200],
                ]) {
                    const dco = recovery.Projection.createDcoInput({
                        customer,
                        board_description: "MDF 18mm",
                        edge_color: "أبيض",
                        order_notes: "ملاحظة رأس طويلة ".repeat(500),
                        pieces: makePieces(count, draftId),
                    }, { pieceKey: (_, index) => draftId + "-piece-" + index });
                    const payload = recovery.Projection.createPayload({ dco, dirtyScope: "DCO" });
                    const stored = await repo.write({
                        ...identity,
                        target_doctype: "Door Cutting Order",
                        draft_id: draftId,
                        tab_session_id: "seed-tab",
                        mode: "NEW",
                        dirty_scope: "DCO",
                        recovery_revision: 1,
                        expected_recovery_revision: 0,
                        payload,
                        asset_refs: [draftId + "-asset"],
                    });
                    if (!stored.ok) throw new Error("seed draft: " + stored.error.code);
                    const asset = await assets.write(
                        { ...identity, draft_id: draftId },
                        draftId + "-asset",
                        new Blob([draftId + " drawing bytes"], { type: "application/json" }),
                        { file_name: draftId + ".json" },
                    );
                    if (!asset.ok) throw new Error("seed asset: " + asset.error.code);
                    result[draftId] = { bytes: new TextEncoder().encode(
                        recovery.Projection.serialize(payload)
                    ).byteLength, rows: count };
                }
                return result;
            }"""
        )
        assert seeded["90000000-0000-4000-8000-000000000002"]["rows"] == 200
        assert seeded["90000000-0000-4000-8000-000000000002"]["bytes"] > 60_000

        page.evaluate(
            """() => {
                window.__formHandlers = {};
                window.__confirmAction = null;
                window.__routes = [];
                window.AlmdinaUi = {
                    button({ label, className = "", attrs = {} }) {
                        const attributes = Object.entries(attrs)
                            .map(([key, value]) => `${key}="${String(value)}"`).join(" ");
                        return `<button type="button" class="${className}" ${attributes}>${label}</button>`;
                    },
                };
                window.AlmdinaDocumentContext = {
                    capture: (frm) => ({ identity: frm.doctype + "::" + frm.doc.name, generation: frm.generation }),
                    isCurrent: (frm, token) => window.cur_frm === frm
                        && token.generation === frm.generation
                        && token.identity === frm.doctype + "::" + frm.doc.name,
                    isSameDocument: (frm, token) => token.identity === frm.doctype + "::" + frm.doc.name,
                    formIdentity: (frm) => frm.doctype + "::" + frm.doc.name,
                    registerCleanup: () => true,
                    scheduleFrame: (_frm, _key, callback) => callback(),
                };
                window.AlmdinaOrderRevisionUX = { isEditSessionActive: () => true };
                window.frappe = {
                    boot: { sitename: location.host },
                    session: { user: "new-flow-user" },
                    utils: { escape_html: (value) => String(value) },
                    datetime: { str_to_user: (value) => value },
                    validated: true,
                    model: {
                        clear_table: (doc, field) => { doc[field] = []; },
                        add_child: (doc, _doctype, field) => {
                            const row = { __islocal: 1 };
                            (doc[field] ||= []).push(row);
                            return row;
                        },
                    },
                    ui: {
                        form: { on: (doctype, handlers) => {
                            window.__formHandlers[doctype] = {
                                ...(window.__formHandlers[doctype] || {}), ...handlers,
                            };
                        } },
                        Dialog: class {
                            constructor(options) {
                                this.wrapper = document.createElement("div");
                                this.wrapper.className = "modal";
                                this.wrapper.innerHTML = options.fields[0].options;
                                this.$wrapper = { get: () => this.wrapper };
                            }
                            show() { document.body.appendChild(this.wrapper); }
                            hide() { this.wrapper.remove(); }
                        },
                    },
                    confirm: (_message, yes, no) => { window.__confirmAction = { yes, no }; },
                    msgprint: (value) => { window.__lastMessage = value; },
                    show_alert: () => {},
                    set_route: (...route) => { window.__routes.push(route); },
                };
            }"""
        )
        page.add_script_tag(path=str(RECOVERY / "application/door_cutting_order_new_recovery.js"))
        page.add_script_tag(path=str(RECOVERY / "infrastructure/door_cutting_order_recovery_api.js"))
        page.add_script_tag(path=str(RECOVERY / "presentation/door_cutting_order_local_checkpoint.js"))
        page.evaluate(
            """async () => {
                const wrapper = document.createElement("div");
                wrapper.className = "form-layout";
                document.body.appendChild(wrapper);
                const frm = {
                    doctype: "Door Cutting Order",
                    generation: 1,
                    doc: { doctype: "Door Cutting Order", name: "__new__", pieces: [] },
                    wrapper,
                    is_new: () => frm.doc.name === "__new__",
                    save: async () => {},
                    refresh_fields: () => {},
                    refresh_field: () => {},
                    dirty: () => { frm.isDirty = true; },
                };
                window.cur_frm = frm;
                window.__newForm = frm;
                await window.__formHandlers["Door Cutting Order"].onload(frm);
            }"""
        )
        assert page.locator(".dco-recovery-card").count() == 2
        assert page.get_by_text("مسودة للاستكمال").count() == 1
        page.evaluate(
            """async () => {
                window.frappe.validated = true;
                await window.__formHandlers["Door Cutting Order"].before_save(window.__newForm);
            }"""
        )
        assert page.evaluate("window.frappe.validated") is False
        assert page.locator(".dco-recovery-card").count() == 2
        page.evaluate("window.frappe.validated = true")

        page.locator('[data-draft-id="90000000-0000-4000-8000-000000000001"] [data-recovery-action="delete"]').click()
        page.evaluate("window.__confirmAction.no()")
        assert page.locator('[data-draft-id="90000000-0000-4000-8000-000000000001"]').count() == 1
        assert page.locator(".dco-recovery-card").count() == 2

        page.locator('[data-draft-id="90000000-0000-4000-8000-000000000001"] [data-recovery-action="delete"]').click()
        page.evaluate("window.__confirmAction.yes()")
        page.wait_for_function("document.querySelectorAll('.dco-recovery-card').length === 1", timeout=5000)
        deleted = page.evaluate(
            """async () => {
                const recovery = window.AlmdinaDcoRecovery;
                const drafts = recovery.LocalDraftRepository.create();
                const assets = recovery.LocalAssetRepository.create();
                const identity = { site: location.host, user: "new-flow-user" };
                const removedDraft = await drafts.read({ ...identity, draft_id: "90000000-0000-4000-8000-000000000001" });
                const removedAsset = await assets.read(
                    { ...identity, draft_id: "90000000-0000-4000-8000-000000000001" }, "90000000-0000-4000-8000-000000000001-asset"
                );
                const keptDraft = await drafts.read({ ...identity, draft_id: "90000000-0000-4000-8000-000000000002" });
                const keptAsset = await assets.read(
                    { ...identity, draft_id: "90000000-0000-4000-8000-000000000002" }, "90000000-0000-4000-8000-000000000002-asset"
                );
                return {
                    removed: removedDraft.ok && removedDraft.value === null
                        && removedAsset.ok && removedAsset.value === null,
                    kept: keptDraft.ok && Boolean(keptDraft.value)
                        && keptAsset.ok && Boolean(keptAsset.value),
                };
            }"""
        )
        assert deleted == {"removed": True, "kept": True}

        page.locator('[data-draft-id="90000000-0000-4000-8000-000000000002"] [data-recovery-action="continue"]').click()
        page.wait_for_function("!document.querySelector('.dco-recovery-card')", timeout=5000)
        restored = page.evaluate(
            """() => ({
                name: window.__newForm.doc.name,
                customer: window.__newForm.doc.customer,
                count: window.__newForm.doc.pieces.length,
                first: window.__newForm.doc.pieces[0],
                last: window.__newForm.doc.pieces.at(-1),
                dirty: window.__newForm.isDirty === true,
            })"""
        )
        assert restored["name"] == "__new__"
        assert restored["customer"] == "مسودة للاستكمال"
        assert restored["count"] == 200
        assert restored["first"]["piece_type"] == "Liner"
        assert restored["first"]["extra_liner"] == 1
        assert restored["last"]["piece_type"] == "Special"
        assert restored["last"]["special_shape_geometry_json"] == '{"path":"M0 0 L1200 400 Z"}'
        assert restored["dirty"] is True

        checkpointed = page.evaluate(
            """async () => {
                const frm = window.__newForm;
                frm.doc.pieces[0].qty = 3;
                window.__formHandlers["Door Cutting Order Detail"].qty(frm);
                const flushed = await window.AlmdinaDcoRecovery.LocalCheckpoint.flush(frm);
                if (!flushed.ok) throw new Error("restored edit checkpoint failed");
                const result = await window.AlmdinaDcoRecovery.LocalCheckpoint.repository().read({
                    site: location.host,
                    user: "new-flow-user",
                    draft_id: "90000000-0000-4000-8000-000000000002",
                });
                return result.value.payload.dco.pieces[0];
            }"""
        )
        assert checkpointed["piece_key"] == "90000000-0000-4000-8000-000000000002-piece-0"
        assert checkpointed["qty"] == 3

        # The explicit native Save gate persists the exact selected UUID before insert.
        page.evaluate("window.frappe.validated = true")
        page.evaluate(
            """async () => window.__formHandlers["Door Cutting Order"].before_save(window.__newForm)"""
        )
        pending = page.evaluate(
            """async () => {
                const repo = window.AlmdinaDcoRecovery.LocalDraftRepository.create();
                const record = await repo.read({
                    site: location.host,
                    user: "new-flow-user",
                    draft_id: "90000000-0000-4000-8000-000000000002",
                });
                return {
                    valid: window.frappe.validated,
                    token: window.__newForm.doc.recovery_creation_token,
                    state: window.__newForm.wrapper.querySelector(".dco-recovery-status")
                        ?.dataset.recoveryState,
                    recordState: record.value.official_save_state,
                };
            }"""
        )
        assert pending == {
            "valid": True,
            "token": "90000000-0000-4000-8000-000000000002",
            "state": "OFFICIAL_SAVING",
            "recordState": "PENDING_RECONCILIATION",
        }
        page.close()

        # Reopen with a durable pending marker; only the reconciliation result
        # can authorize local cleanup/navigation.
        reopened = recovery_page(context, local_origin)
        reopened.evaluate(
            """() => {
                window.__formHandlers = {};
                window.__confirmAction = null;
                window.__routes = [];
                window.AlmdinaUi = { button: ({ label, attrs = {} }) => {
                    const attributes = Object.entries(attrs).map(([key, value]) => `${key}="${value}"`).join(" ");
                    return `<button type="button" ${attributes}>${label}</button>`;
                } };
                window.AlmdinaDocumentContext = {
                    capture: (frm) => ({ identity: frm.doctype + "::" + frm.doc.name, generation: frm.generation }),
                    isCurrent: (frm, token) => window.cur_frm === frm
                        && token.generation === frm.generation
                        && token.identity === frm.doctype + "::" + frm.doc.name,
                    isSameDocument: (frm, token) => token.identity === frm.doctype + "::" + frm.doc.name,
                    formIdentity: (frm) => frm.doctype + "::" + frm.doc.name,
                    registerCleanup: () => true,
                    scheduleFrame: (_frm, _key, callback) => callback(),
                };
                window.AlmdinaOrderRevisionUX = { isEditSessionActive: () => true };
                window.frappe = {
                    boot: { sitename: location.host }, session: { user: "new-flow-user" },
                    utils: { escape_html: (value) => String(value) }, datetime: { str_to_user: (value) => value },
                    validated: true, model: {
                        clear_table: (doc, field) => { doc[field] = []; },
                        add_child: (doc, _doctype, field) => { const row = {}; (doc[field] ||= []).push(row); return row; },
                    }, ui: {
                        form: { on: (doctype, handlers) => { window.__formHandlers[doctype] = {
                            ...(window.__formHandlers[doctype] || {}), ...handlers,
                        }; } },
                        Dialog: class {
                            constructor(options) { this.wrapper = document.createElement("div");
                                this.wrapper.className = "modal"; this.wrapper.innerHTML = options.fields[0].options;
                                this.$wrapper = { get: () => this.wrapper }; }
                            show() { document.body.appendChild(this.wrapper); }
                            hide() { this.wrapper.remove(); }
                        },
                    },
                    confirm: (_message, yes, no) => { window.__confirmAction = { yes, no }; },
                    msgprint: (value) => { window.__lastMessage = value; },
                    show_alert: () => {}, set_route: (...route) => window.__routes.push(route),
                };
                window.__reconcileCalls = [];
                window.AlmdinaDcoRecovery.ServerReconciliation = {
                    reconcileNewCreation: async (token) => {
                        window.__reconcileCalls.push(token);
                        if (window.__recoveryOffline) throw new Error("reconciliation offline");
                        return {
                            status: token === "90000000-0000-4000-8000-000000000002" ? "CREATED" : "NOT_FOUND",
                            door_cutting_order: "DCO-RECOVERED-1",
                        };
                    },
                };
            }"""
        )
        reopened.add_script_tag(path=str(RECOVERY / "application/door_cutting_order_new_recovery.js"))
        reopened.add_script_tag(path=str(RECOVERY / "presentation/door_cutting_order_local_checkpoint.js"))
        reopened.evaluate(
            """async () => {
                const wrapper = document.createElement("div"); wrapper.className = "form-layout";
                document.body.appendChild(wrapper);
                const frm = { doctype: "Door Cutting Order", generation: 2,
                    doc: { doctype: "Door Cutting Order", name: "__new__", pieces: [] }, wrapper,
                    is_new: () => frm.doc.name === "__new__", save: async () => {},
                    refresh_fields: () => {}, refresh_field: () => {}, dirty: () => {}, };
                window.cur_frm = frm; window.__newForm = frm;
                await window.__formHandlers["Door Cutting Order"].onload(frm);
            }"""
        )
        reopened.wait_for_function("document.querySelectorAll('.dco-recovery-card').length === 1", timeout=5000)
        reopened.evaluate("window.__recoveryOffline = true")
        reopened.locator('[data-recovery-action="continue"]').click()
        reopened.wait_for_function("window.__lastMessage && document.querySelector('.dco-recovery-card button:not([disabled])')", timeout=5000)
        unavailable = reopened.evaluate(
            """async () => ({
                routeCount: window.__routes.length,
                dialogVisible: Boolean(document.querySelector('.dco-recovery-card')),
                record: await window.AlmdinaDcoRecovery.LocalCheckpoint.repository().read({
                    site: location.host,
                    user: "new-flow-user",
                    draft_id: "90000000-0000-4000-8000-000000000002",
                }),
            })"""
        )
        assert unavailable["routeCount"] == 0
        assert unavailable["dialogVisible"] is True
        assert unavailable["record"]["value"]["official_save_state"] == "PENDING_RECONCILIATION"
        reopened.evaluate("window.__recoveryOffline = false")
        reopened.locator('[data-recovery-action="continue"]').click()
        reopened.wait_for_function("window.__routes.length === 1", timeout=5000)
        assert reopened.evaluate("window.__routes[0]") == ["Form", "Door Cutting Order", "DCO-RECOVERED-1"]
        final = reopened.evaluate(
            """async () => {
                const repo = window.AlmdinaDcoRecovery.LocalDraftRepository.create();
                const assets = window.AlmdinaDcoRecovery.LocalAssetRepository.create();
                return {
                    draft: await repo.read({ site: location.host, user: "new-flow-user", draft_id: "90000000-0000-4000-8000-000000000002" }),
                    asset: await assets.read({ site: location.host, user: "new-flow-user", draft_id: "90000000-0000-4000-8000-000000000002" }, "90000000-0000-4000-8000-000000000002-asset"),
                };
            }"""
        )
        assert final["draft"]["value"] is None
        assert final["asset"]["value"] is None
    finally:
        context.close()
