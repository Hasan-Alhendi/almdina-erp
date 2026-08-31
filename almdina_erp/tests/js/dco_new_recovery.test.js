"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const fakeWindow = { structuredClone };
let addedRows = 0;
let userMutationEvents = 0;
const fakeFrappe = {
    model: {
        clear_table(doc, fieldname) { doc[fieldname] = []; },
        add_child(doc, doctype, fieldname) {
            addedRows += 1;
            const row = {
                doctype,
                name: `new-door-cutting-order-detail-${addedRows}`,
                __islocal: 1,
            };
            doc[fieldname].push(row);
            return row;
        },
    },
};
const context = vm.createContext({
    window: fakeWindow,
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
});

function run(relative) {
    const source = fs.readFileSync(path.resolve(__dirname, relative), "utf8");
    vm.runInContext(source, context, { filename: path.basename(relative) });
}

run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_recovery_projection.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_checkpoint_session.js");
run("../../public/js/door_cutting_order/recovery/application/door_cutting_order_new_recovery.js");

const Recovery = fakeWindow.AlmdinaDcoRecovery;

function payload(pieceKeys = ["piece-a", "piece-b"]) {
    return Recovery.Projection.createPayload({
        dirtyScope: "DCO",
        dco: Recovery.Projection.createDcoInput({
            customer: "CUST-RECOVERED",
            order_date: "2026-08-29",
            board_description: "MDF أبيض",
            edge_color: "أبيض",
            pieces: [
                { name: "temporary-a", width_cm: 40, length_cm: 70, qty: 2, edge_long_right: 1 },
                {
                    name: "temporary-b",
                    piece_type: "Special",
                    width_cm: 55,
                    length_cm: 80,
                    qty: 1,
                    special_shape_geometry_json: '{"type":"polygon"}',
                },
            ],
        }, { pieceKey: (row, index) => pieceKeys[index] }),
    });
}

function record(draftId, capturedAt, overrides = {}) {
    return {
        schema_version: 2,
        draft_id: draftId,
        mode: "NEW",
        dirty_scope: "DCO",
        target_doctype: "Door Cutting Order",
        target_name: null,
        session_origin_modified: null,
        expected_server_modified: null,
        tab_session_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        recovery_revision: 4,
        created_at: "2026-08-29T09:00:00.000Z",
        captured_at: capturedAt,
        official_save_state: "ACTIVE",
        official_save_attempted_at: null,
        payload_hash: "hash",
        payload: payload(),
        asset_refs: ["local-scan-asset"],
        ...overrides,
    };
}

(async () => {
    const drafts = [
        record("11111111-1111-4111-8111-111111111111", "2026-08-29T10:00:00.000Z"),
        record("22222222-2222-4222-8222-222222222222", "2026-08-29T11:00:00.000Z"),
    ];
    const requested = [];
    const discoveryRepository = {
        async discover(identity) {
            requested.push(identity);
            return { ok: true, value: { records: drafts, rejected: [] } };
        },
    };
    const discovered = await Recovery.NewRecovery.discover(discoveryRepository, {
        site: "erp.example.test",
        user: "operator@example.test",
    });
    assert.equal(discovered.value.records.length, 2, "multiple NEW drafts coexist");
    assert.deepEqual(JSON.parse(JSON.stringify(requested[0])), {
        site: "erp.example.test",
        user: "operator@example.test",
        target_doctype: "Door Cutting Order",
        mode: "NEW",
    });
    assert.equal(
        (await Recovery.NewRecovery.discover({ discover: async () => ({ ok: true, value: { records: [], rejected: [] } }) }, {
            site: "erp.example.test", user: "operator@example.test",
        })).value.records.length,
        0,
        "zero-draft discovery is explicit"
    );

    const summary = Recovery.NewRecovery.summarize(drafts[0]);
    assert.equal(summary.customer, "CUST-RECOVERED");
    assert.equal(summary.piece_count, 2);
    assert.equal(summary.board_description, "MDF أبيض");
    assert.equal(summary.edge_color, "أبيض");
    assert.equal(summary.has_special_piece, true);

    const writes = [];
    let storedOfficialSaveState = null;
    const repository = {
        async write(value) {
            writes.push(structuredClone(value));
            return {
                ok: true,
                value: storedOfficialSaveState
                    ? { ...value, official_save_state: storedOfficialSaveState }
                    : value,
            };
        },
        async setOfficialSaveState() { return { ok: true, value: null }; },
    };
    let activeForm = null;
    const session = Recovery.CheckpointSession.create({
        repository,
        site: "erp.example.test",
        user: "operator@example.test",
        mode: "NEW",
        draftId: drafts[0].draft_id,
        tabSessionId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        recoveryRevision: 4,
        savedRevision: 4,
        dirtyScope: "DCO",
        officialSaveState: "ACTIVE",
        capture: () => ({ payload: Recovery.Projection.createPayload({
            dirtyScope: "DCO",
            dco: Recovery.Projection.createDcoInput(activeForm.doc, {
                pieceKey: (row) => row.recoveryPieceKey,
            }),
        }), asset_refs: ["local-scan-asset"] }),
    });
    const form = activeForm = {
        doc: {
            customer: "BASE-CUSTOMER",
            pieces: [{ name: "base-row", width_cm: 1, length_cm: 1, qty: 1 }],
        },
        refreshFields: 0,
        refreshPieces: 0,
        dirtyCalls: 0,
        officialSaveCalls: 0,
        refresh_fields() { this.refreshFields += 1; },
        refresh_field(fieldname) { if (fieldname === "pieces") this.refreshPieces += 1; },
        dirty() { this.dirtyCalls += 1; },
        save() { this.officialSaveCalls += 1; },
    };
    const recoveredKeys = [];
    let derivedRebuilds = 0;
    let keyboardInstalls = 0;
    const result = await Recovery.NewRecovery.hydrate(drafts[0], {
        session,
        async hydrationPort(dco) {
            Recovery.Projection.HEADER_FIELDS.forEach((fieldname) => {
                if (Object.prototype.hasOwnProperty.call(dco, fieldname)) {
                    form.doc[fieldname] = dco[fieldname];
                }
            });
            form.doc.pieces = dco.pieces.map((piece, index) => {
                addedRows += 1;
                const row = { ...piece, idx: index + 1, piece_no: index + 1 };
                row.recoveryPieceKey = piece.piece_key;
                recoveredKeys.push(piece.piece_key);
                return row;
            });
            form.refresh_fields();
            form.refresh_field("pieces");
            derivedRebuilds += 1;
            keyboardInstalls += 1;
            // Hydration-time mutation notifications must be ignored by RESTORING.
            userMutationEvents += 1;
            session.markDirty("DCO");
            form.dirty();
        },
    });
    assert.equal(result.draft_id, drafts[0].draft_id, "stable draft_id survives restore");
    assert.equal(result.restored, true);
    assert.deepEqual(Array.from(result.asset_refs), ["local-scan-asset"]);
    assert.equal(form.doc.customer, "CUST-RECOVERED");
    assert.deepEqual(form.doc.pieces.map((row) => row.width_cm), [40, 55]);
    assert.deepEqual(form.doc.pieces.map((row) => row.qty), [2, 1]);
    assert.deepEqual(recoveredKeys, ["piece-a", "piece-b"]);
    assert.equal(form.doc.pieces.length, 2, "base rows are replaced, never duplicated");
    assert.equal(form.refreshFields, 1);
    assert.equal(form.refreshPieces, 1);
    assert.equal(form.dirtyCalls, 1);
    assert.equal(derivedRebuilds, 1, "derived UI rebuilds once after hydration");
    assert.equal(keyboardInstalls, 1, "keyboard owner is reinstalled once");
    assert.equal(form.officialSaveCalls, 0, "restore never invokes official Save");
    assert.equal(writes.length, 0, "RESTORING suppresses checkpoint storms");
    assert.equal(session.snapshot().recovery_revision, 4);
    assert.equal(session.snapshot().state, "READY_CLEAN");
    assert.equal(userMutationEvents, 1);

    storedOfficialSaveState = "PENDING_RECONCILIATION";
    session.markDirty("DCO");
    await session.flush();
    assert.equal(writes.length, 1);
    assert.equal(writes[0].draft_id, drafts[0].draft_id);
    assert.equal(writes[0].recovery_revision, 5);
    assert.deepEqual(writes[0].payload.dco.pieces.map((piece) => piece.piece_key), ["piece-a", "piece-b"]);
    assert.equal(session.snapshot().official_save_state, "PENDING_RECONCILIATION");
    assert.equal(session.snapshot().state, "PENDING_RECONCILIATION");

    const invalid = record("33333333-3333-4333-8333-333333333333", "2026-08-29T12:00:00.000Z", {
        dirty_scope: "PLAN",
        payload: Recovery.Projection.createPayload({
            dirtyScope: "PLAN",
            dco: Recovery.Projection.createDcoInput({ pieces: [] }),
            planWorkspaceDraft: Recovery.Projection.createPlanWorkspaceDraft({
                editing: true,
                dirty: true,
                draft: { packing_mode: "Auto" },
            }, { normalized_settings_hash: "hash" }),
        }),
    });
    const untouched = { doc: { customer: "UNCHANGED", pieces: [{ name: "keep" }] } };
    await assert.rejects(
        Recovery.NewRecovery.hydrate(invalid, { session, hydrationPort: () => {} }),
        (error) => error.code === "invalid_new_draft"
    );
    assert.equal(untouched.doc.customer, "UNCHANGED");
    assert.equal(untouched.doc.pieces.length, 1, "invalid drafts fail before partial hydration");

    console.log("DCO NEW recovery discovery and hydration simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
