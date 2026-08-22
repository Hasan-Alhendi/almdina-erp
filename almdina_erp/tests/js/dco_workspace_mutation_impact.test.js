"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/order_entry/door_cutting_order_mutation_impact_policy.js"
    ),
    "utf8"
);

const handlers = new Map();
const invalidations = [];
const refreshes = [];

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-1",
        plan_needs_recalculation: 0,
        pieces: [
            {
                name: "ROW-1",
                piece_type: "Special",
                width_cm: 80,
                length_cm: 200,
                qty: 2,
                special_shape_price_status: "Approved",
                special_shape_custom_unit_price_usd: 125,
            },
        ],
    },
};

const fakeCoordinator = {
    invalidate(_frm, resources, reason) {
        invalidations.push({ resources: Array.from(resources), reason });
        return resources;
    },
    async refresh(_frm, resources, options) {
        refreshes.push({ resources: Array.from(resources), options: { ...options } });
        return resources;
    },
};

const fakeFrappe = {
    ui: {
        form: {
            on(doctype, mapping) {
                handlers.set(doctype, mapping);
            },
        },
    },
};

const context = vm.createContext({
    window: {
        AlmdinaWorkspaceSyncCoordinator: fakeCoordinator,
    },
    frappe: fakeFrappe,
    console,
    Set,
    Object,
    String,
    Boolean,
    Array,
    locals: {
        "Door Cutting Order Detail": {
            "ROW-1": frm.doc.pieces[0],
        },
    },
});
context.window.window = context.window;

vm.runInContext(source, context, {
    filename: "door_cutting_order_mutation_impact_policy.js",
});

const policy = context.window.AlmdinaOrderMutationImpactPolicy;
assert.ok(policy);
assert.deepEqual(
    Array.from(policy.SPECIAL_PRICE_BASIS_FIELDS),
    ["width_cm", "length_cm", "qty", "piece_type"]
);

const detailHandlers = handlers.get("Door Cutting Order Detail");
assert.ok(detailHandlers && typeof detailHandlers.qty === "function");
detailHandlers.qty(frm, "Door Cutting Order Detail", "ROW-1");

const piece = frm.doc.pieces[0];
assert.equal(piece.__almdina_special_price_basis_stale, true);
assert.equal(piece.__almdina_special_price_basis_stale_field, "qty");
assert.deepEqual(invalidations[0], {
    resources: ["plan", "cost"],
    reason: "special_price_basis_changed",
});

(async () => {
    frm.doc.plan_needs_recalculation = 1;
    assert.equal(await policy.reconcileAfterSave(frm), true);
    assert.equal(piece.__almdina_special_price_basis_stale, undefined);
    assert.equal(piece.__almdina_special_price_basis_stale_field, undefined);
    assert.deepEqual(refreshes, [
        {
            resources: ["plan", "cost"],
            options: { force: false, reason: "order_saved" },
        },
    ]);
    assert.deepEqual(invalidations.at(-1), {
        resources: ["cost"],
        reason: "plan_recalculation_required",
    });

    invalidations.length = 0;
    frm.doc.plan_needs_recalculation = 0;
    detailHandlers.allow_rotation(frm, "Door Cutting Order Detail", "ROW-1");
    assert.equal(piece.__almdina_special_price_basis_stale, undefined,
        "non-pricing-basis geometry must not invalidate the approved special price");
    assert.deepEqual(invalidations[0], {
        resources: ["plan", "cost"],
        reason: "order_inputs_changed",
    });

    console.log("DCO workspace mutation impact simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
