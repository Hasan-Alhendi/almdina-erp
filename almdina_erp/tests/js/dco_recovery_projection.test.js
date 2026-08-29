"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/recovery/application/door_cutting_order_recovery_projection.js"),
    "utf8"
);
const fakeWindow = { structuredClone };
const context = vm.createContext({
    window: fakeWindow,
    console,
    Object,
    Array,
    Set,
    String,
    Number,
    JSON,
    Blob,
    structuredClone,
});
vm.runInContext(source, context, { filename: "door_cutting_order_recovery_projection.js" });

const Projection = fakeWindow.AlmdinaDcoRecovery.Projection;
const doc = {
    doctype: "Door Cutting Order",
    name: "new-door-cutting-order-1",
    owner: "administrator@example.com",
    modified: "2026-08-29 10:00:00.000000",
    status: "Draft",
    customer: "CUST-001",
    order_date: "2026-08-29",
    order_notes: "Keep grain aligned",
    board_description: "MDF white",
    board_length_cm: 280,
    board_width_cm: 207,
    default_edge_type: "EDGE-1",
    edge_color: "White",
    total_cost_usd: 999,
    pieces: [{
        name: "new-door-cutting-order-detail-1",
        piece_type: "Regular",
        width_cm: 60,
        length_cm: 80,
        qty: 2,
        allow_rotation: 1,
        edge_long_right: 1,
        edge_long_left: 0,
        edge_width_top: 1,
        edge_width_bottom: 0,
        notes: "Piece note",
        special_shape_drawing_json: JSON.stringify({ reference: { fileUrl: "/private/files/ref.jpg" } }),
        special_shape_geometry_json: JSON.stringify({ kind: "rectangle" }),
        cut_width_cm: 59.8,
        edge_cost_usd: 50,
        __controller_cache: { selected: true },
    }],
    __dialog: { open: true },
};

const dco = Projection.createDcoInput(doc, { pieceKey: () => "piece-recovery-uuid" });
assert.equal(dco.projection_version, 1);
assert.deepEqual(
    Object.keys(dco).sort(),
    [...Projection.HEADER_FIELDS, "pieces", "projection_version"].sort()
);
assert.equal(dco.pieces[0].piece_key, "piece-recovery-uuid");
assert.equal(dco.pieces[0].width_cm, 60);
assert.equal("name" in dco.pieces[0], false);
assert.equal("cut_width_cm" in dco.pieces[0], false);
assert.equal("edge_cost_usd" in dco.pieces[0], false);
assert.equal("__controller_cache" in dco.pieces[0], false);
assert.equal("modified" in dco, false);
assert.equal("total_cost_usd" in dco, false);
assert.equal("__dialog" in dco, false);

const dcoPayload = Projection.createPayload({ dco, dirtyScope: "DCO" });
assert.equal(dcoPayload.plan_workspace_draft, null);
assert.equal(dcoPayload.cost_workspace_draft, null);
assert.deepEqual(Array.from(dcoPayload.special_shape_drafts), []);
const serialized = Projection.serialize(dcoPayload);
assert.equal(Projection.serialize(Projection.deserialize(serialized)), Projection.serialize(dcoPayload));
assert.equal(serialized, Projection.serialize(JSON.parse(serialized)));

const plan = Projection.createPlanWorkspaceDraft({
    editing: true,
    dirty: true,
    baseline: {
        name: "PLAN-001",
        modified: "2026-08-29 09:00:00.000000",
        packing_mode: "Guillotine",
        cutting_machine_type: "Panel Saw",
    },
    draft: {
        packing_mode: "Non-Guillotine",
        cutting_machine_type: "CNC",
        optimization_time_limit_sec: 30,
        kerf_mm: 4,
        trim_margin_mm: 8,
        preview_id: "PREVIEW-TRANSIENT",
    },
}, { normalized_settings_hash: "plan-baseline-hash" });
assert.deepEqual(Object.keys(plan.draft).sort(), [...Projection.PLAN_DRAFT_FIELDS].sort());
assert.equal("preview_id" in plan.draft, false);
const planPayload = Projection.createPayload({
    dco,
    dirtyScope: "PLAN",
    planWorkspaceDraft: plan,
});
assert.equal(planPayload.plan_workspace_draft.baseline.plan_name, "PLAN-001");

const cost = Projection.createCostWorkspaceDraft({
    editing: true,
    dirty: true,
    baseline: { cutting_plan: "PLAN-001", board_rate_usd: 20, cutting_cost_per_board_usd: 3 },
    draft: { board_rate_usd: 21, cutting_cost_per_board_usd: 4, invoice_html: "<div>transient</div>" },
}, { normalized_settings_hash: "cost-baseline-hash" });
assert.deepEqual(Object.keys(cost.draft).sort(), [...Projection.COST_DRAFT_FIELDS].sort());
assert.equal("invoice_html" in cost.draft, false);

assert.throws(
    () => Projection.createDcoInput({ pieces: [{}] }),
    (error) => error.code === "missing_piece_key"
);
assert.throws(
    () => Projection.createDcoInput({ pieces: [{
        name: "ROW-1",
        special_shape_drawing_json: JSON.stringify({ reference: { fileUrl: "blob:temporary" } }),
    }] }),
    (error) => error.code === "transient_asset"
);
assert.throws(
    () => Projection.createDcoInput({ pieces: [{
        name: "ROW-1",
        special_shape_drawing_json: JSON.stringify({ reference: { fileUrl: "data:image/png;base64,AAAA" } }),
    }] }),
    (error) => error.code === "transient_asset"
);
assert.throws(
    () => Projection.createPlanWorkspaceDraft({ editing: false, dirty: false }),
    (error) => error.code === "workspace_not_dirty"
);
assert.throws(
    () => Projection.createPayload({ dco, dirtyScope: "PLAN" }),
    (error) => error.code === "missing_scope_projection"
);
assert.throws(
    () => Projection.deserialize(JSON.stringify({ ...dcoPayload, dialog_state: { open: true } })),
    (error) => error.code === "unexpected_projection_field"
);
assert.throws(
    () => Projection.deserialize(JSON.stringify({
        ...dcoPayload,
        plan_workspace_draft: plan,
    }), "DCO"),
    (error) => error.code === "multiple_dirty_owners"
);

console.log("DCO recovery projection contract simulation passed");
