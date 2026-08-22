"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js"
    ),
    "utf8"
);

const grants = new Set(["view_costs", "approve_special_price"]);
const pricingCalls = [];
const syncCalls = [];
let pricingMode = "success";
let successfulCallIndex = 0;

const fakeFrappe = {
    almdina: {
        orderCanEdit() {
            throw new Error("Pricing must never depend on orderCanEdit");
        },
    },
    session: { user: "pricing@example.com" },
    datetime: {
        now_datetime() {
            return "2026-08-21 04:30:00";
        },
    },
    ui: {
        form: {
            on() {},
        },
    },
    async call(options) {
        pricingCalls.push({
            method: options.method,
            expectedModified: options.args.expected_modified,
            pieceName: options.args.piece_name,
        });

        if (pricingMode === "partial" && pricingCalls.length === 2) {
            throw new Error("simulated second-command failure");
        }

        successfulCallIndex += 1;
        return {
            message: {
                order_modified: `server-${successfulCallIndex}`,
            },
        };
    },
};

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-TEST-PRICE-1",
        docstatus: 0,
        status: "Draft",
        revision_state: "Current",
        modified: "client-0",
        __unsaved: 0,
        pieces: [],
    },
    fields_dict: {},
    is_new() {
        return false;
    },
    is_dirty() {
        return Boolean(this.doc.__unsaved);
    },
};

const fakeWindow = {
    frappe: fakeFrappe,
    AlmdinaPermissions: {
        canDocument(receivedFrm, capability) {
            assert.equal(receivedFrm, frm);
            return grants.has(capability);
        },
        can(capability) {
            return grants.has(capability);
        },
    },
    AlmdinaCostEditSessionUX: {
        isEditing(receivedFrm) {
            return receivedFrm === frm;
        },
    },
    AlmdinaOrderRevisionUX: {
        captureEditSessionPresence() {
            return false;
        },
    },
    AlmdinaWorkspaceSyncCoordinator: {
        syncDocumentModified(receivedFrm, modified) {
            assert.equal(receivedFrm, frm);
            assert.equal(receivedFrm.doc.__unsaved, 0,
                "the form token may advance only after local pricing dirty state is cleared");
            syncCalls.push(modified);
            receivedFrm.doc.modified = modified;
            return true;
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
    Boolean,
    Number,
    String,
    Math,
    Promise,
    Error,
    MutationObserver: class MutationObserver {
        observe() {}
        disconnect() {}
    },
    setTimeout(callback) {
        callback();
        return 1;
    },
    __: value => value,
});

vm.runInContext(source, context, {
    filename: "door_cutting_order_cost_permissions_ux.js",
});

const api = fakeWindow.AlmdinaCostPermissionsUX;
assert.ok(api, "Cost permission API must be installed");

const unpricedSpecial = {
    name: "ROW-1",
    piece_type: "Special",
    special_shape_price_status: "Estimated",
};
frm.doc.pieces = [unpricedSpecial];

assert.equal(
    api.canEditInlinePiecePrice(frm, unpricedSpecial),
    true,
    "Draft + Cost edit session + approve_special_price must open an unpriced Special input without edit_order"
);

const locallyPricedSpecial = {
    ...unpricedSpecial,
    special_shape_price_status: "Approved",
    special_shape_custom_unit_price_usd: 150,
    __almdina_pending_price_edit: "special",
    __almdina_pending_price_capability: "approve_special_price",
};
frm.doc.pieces = [locallyPricedSpecial];
assert.equal(
    api.canEditInlinePiecePrice(frm, locallyPricedSpecial),
    true,
    "A first-price local draft must keep its original approve capability until Save/Cancel"
);

const alreadyApprovedSpecial = {
    name: "ROW-2",
    piece_type: "Special",
    special_shape_price_status: "Approved",
    special_shape_custom_unit_price_usd: 150,
};
frm.doc.pieces = [alreadyApprovedSpecial];
assert.equal(
    api.canEditInlinePiecePrice(frm, alreadyApprovedSpecial),
    false,
    "Editing an already-approved Special price must still require edit_special_price"
);

grants.add("edit_special_price");
assert.equal(api.canEditInlinePiecePrice(frm, alreadyApprovedSpecial), true);

frm.doc.status = "Pending Review";
assert.equal(
    api.canEditInlinePiecePrice(frm, unpricedSpecial),
    false,
    "Frontend lifecycle must match the server Draft-only pricing boundary"
);
frm.doc.status = "Draft";

frm.doc.revision_state = "Superseded";
assert.equal(api.canEditInlinePiecePrice(frm, unpricedSpecial), false);
frm.doc.revision_state = "Current";

fakeWindow.AlmdinaCostEditSessionUX.isEditing = () => false;
assert.equal(
    api.canEditInlinePiecePrice(frm, unpricedSpecial),
    false,
    "Pricing stays locked outside an explicit edit session"
);

function specialPending(name, price) {
    return {
        name,
        piece_type: "Special",
        special_shape_price_status: "Approved",
        special_shape_custom_unit_price_usd: price,
        special_shape_price_note: "",
        __almdina_pending_price_edit: "special",
        __almdina_pending_price_capability: "approve_special_price",
    };
}

function clippedPending(name, price) {
    return {
        name,
        piece_type: "Clipped Corner",
        clipped_corner_edge_price_status: "Priced",
        clipped_corner_edge_price_usd: price,
        clipped_corner_edge_price_note: "",
        __almdina_pending_price_edit: "clipped",
        __almdina_pending_price_capability: "approve_special_price",
    };
}

(async () => {
    fakeWindow.AlmdinaCostEditSessionUX.isEditing = () => true;

    pricingCalls.length = 0;
    syncCalls.length = 0;
    successfulCallIndex = 0;
    pricingMode = "success";
    frm.doc.modified = "client-0";
    frm.doc.__unsaved = 1;
    frm.__almdina_pricing_command_modified = null;
    frm.doc.pieces = [
        specialPending("ROW-A", 120),
        clippedPending("ROW-B", 30),
    ];

    await api.flushPendingPriceEdits(frm, { refresh: false });
    assert.deepEqual(
        pricingCalls.map(call => call.expectedModified),
        ["client-0", "server-1"],
        "each pricing command must consume the version returned by the previous successful command"
    );
    assert.deepEqual(syncCalls, ["server-2"],
        "frm.doc.modified must advance once, after all local pricing commands finish");
    assert.equal(frm.doc.modified, "server-2");
    assert.equal(frm.doc.__unsaved, 0);
    assert.equal(frm.__almdina_pricing_command_modified, null);
    assert.equal(api.pendingPricePieces(frm).length, 0);

    pricingCalls.length = 0;
    syncCalls.length = 0;
    successfulCallIndex = 2;
    pricingMode = "partial";
    frm.doc.modified = "server-2";
    frm.doc.__unsaved = 1;
    frm.__almdina_pricing_command_modified = null;
    frm.doc.pieces = [
        specialPending("ROW-C", 140),
        clippedPending("ROW-D", 35),
    ];

    await assert.rejects(
        api.flushPendingPriceEdits(frm, { refresh: false }),
        /simulated second-command failure/
    );
    assert.equal(frm.doc.modified, "server-2",
        "partial success must not advance the form write token while another local price remains pending");
    assert.equal(frm.__almdina_pricing_command_modified, "server-3",
        "the successful command version must be retained for a safe retry");
    assert.equal(api.pendingPricePieces(frm).length, 1);
    assert.equal(api.pendingPricePieces(frm)[0].name, "ROW-D");

    pricingMode = "success";
    pricingCalls.length = 0;
    await api.flushPendingPriceEdits(frm, { refresh: false });
    assert.equal(pricingCalls[0].expectedModified, "server-3",
        "retry must continue from the last successful pricing command version");
    assert.equal(frm.doc.modified, "server-4");
    assert.deepEqual(syncCalls, ["server-4"]);
    assert.equal(api.pendingPricePieces(frm).length, 0);

    console.log("Special price Cost-session authorization and concurrency simulation passed");
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
