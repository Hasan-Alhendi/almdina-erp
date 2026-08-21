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
};

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-TEST-PRICE-1",
        docstatus: 0,
        status: "Draft",
        revision_state: "Current",
        pieces: [],
    },
    fields_dict: {},
    is_new() {
        return false;
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

console.log("Special price Cost-session authorization simulation passed");
