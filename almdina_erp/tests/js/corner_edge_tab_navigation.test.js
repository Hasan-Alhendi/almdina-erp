"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");

function read(relativePath) {
    return fs.readFileSync(path.join(root, relativePath), "utf8");
}

const CLIPPED = "Clipped Corner";
const L_SHAPED = "L-Shaped Corner";
const DETAIL = "Door Cutting Order Detail";

function piece(name, fields) {
    return {
        doctype: DETAIL,
        name,
        piece_type: "Regular",
        piece_instance_id: `piece:${name}`,
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 20,
        clipped_corner_length_cm: 40,
        width_cm: 100,
        length_cm: 200,
        edge_break: 0,
        edge_break_only: 0,
        edge_width_top: 1,
        edge_width_bottom: 0,
        edge_long_right: 1,
        edge_long_left: 0,
        edge_break_cost_usd: 0,
        edge_break_meters: 0,
        ...fields,
    };
}

const clipped = piece("PIECE-CLIP", {
    piece_type: CLIPPED,
    edge_break: 1,
    edge_break_only: 0,
});
const clippedAgain = piece("PIECE-CLIP-2", {
    piece_type: CLIPPED,
    edge_break: 0,
    edge_break_only: 0,
    edge_width_top: 0,
    edge_long_right: 0,
});
const lShaped = piece("PIECE-L", {
    piece_type: L_SHAPED,
    edge_break: 0,
    edge_break_only: 0,
    edge_width_top: 1,
    edge_long_right: 1,
});
const regular = piece("PIECE-REGULAR", {
    edge_break: 0,
    edge_break_only: 0,
    edge_width_top: 1,
    edge_long_right: 1,
});

const pieces = [clipped, clippedAgain, lShaped, regular];
const locals = {
    [DETAIL]: Object.fromEntries(pieces.map((row) => [row.name, row])),
};

const formHandlers = { parent: {}, child: {} };
let activeTab = "order_tab";
let costResponses = [];

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        doctype: "Door Cutting Order",
        name: "DCO-CORNER-TAB",
        pieces,
        board_rate_usd: 0,
    },
    is_new() { return false; },
    is_dirty() { return true; },
    dirty() { this.dirtyCalls = (this.dirtyCalls || 0) + 1; },
    get_active_tab() {
        return { df: { fieldname: activeTab } };
    },
};

function costSnapshot(cost = 7.25) {
    return {
        order: { board_rate_usd: 12 },
        pieces: pieces.map((row) => ({
            name: row.name,
            edge_break: row === clipped ? 1 : 0,
            edge_break_only: 0,
            edge_break_cost_usd: cost,
            edge_break_meters: 1.5,
            special_shape_price_status: "Not Applicable",
        })),
    };
}

class WindowTarget extends EventTarget {}

const fakeWindow = new WindowTarget();
fakeWindow.cur_frm = frm;
fakeWindow.AlmdinaPermissions = {
    can() { return true; },
    canDocument() { return true; },
};
fakeWindow.AlmdinaCostWorkspaceAPI = {
    load() {
        const next = costResponses.shift();
        return next || Promise.resolve(costSnapshot());
    },
};
fakeWindow.AlmdinaOrderCostUX = {
    render() { return true; },
    refreshInvoiceSection() { return true; },
    invoiceLines() { return []; },
    invoiceTotal() { return 0; },
    quoteTotal() { return 0; },
};

const frappe = {
    boot: { lang: "ar" },
    model: {
        new_names: {},
        async set_value(doctype, name, values) {
            const row = locals[doctype] && locals[doctype][name];
            assert.ok(row, "Apply must write the live child row");
            assert.equal(frm.doc.pieces.includes(row), true);
            Object.assign(row, values);
            for (const fieldname of Object.keys(values)) {
                const handler = formHandlers.child[fieldname];
                if (typeof handler === "function") await handler(frm, doctype, name);
            }
            return row;
        },
    },
    ui: {
        form: {
            on(doctype, handlers) {
                const bucket = doctype === "Door Cutting Order"
                    ? formHandlers.parent
                    : formHandlers.child;
                Object.assign(bucket, handlers || {});
            },
        },
    },
    utils: {
        escape_html(value) { return String(value ?? ""); },
    },
};

const documentStub = {
    documentElement: { lang: "ar" },
    getElementById() { return null; },
    createElement() { return { id: "", textContent: "" }; },
    head: { appendChild() {} },
};

const context = vm.createContext({
    window: fakeWindow,
    frappe,
    document: documentStub,
    locals,
    console,
    Object,
    Array,
    Map,
    Set,
    WeakMap,
    Promise,
    Number,
    String,
    Boolean,
    Error,
    Date,
    JSON,
    Math,
    CustomEvent,
    structuredClone,
    __: (value) => value,
});

[
    "core/door_cutting_order_workspace_store.js",
    "core/door_cutting_order_workspace_keep_paint.js",
    "core/door_cutting_order_workspace_sync_coordinator.js",
    "costing/door_cutting_order_cost_workspace_state.js",
    "costing/door_cutting_order_cost_workspace_presenter_adapter.js",
    "order_entry/door_cutting_order_mutation_impact_policy.js",
    "drawing/door_cutting_order_clipped_corner_ux.js",
].forEach((relativePath) => {
    vm.runInContext(read(relativePath), context, { filename: relativePath });
});

function flags(row) {
    return {
        edge_break: row.edge_break,
        edge_break_only: row.edge_break_only,
        edge_width_top: row.edge_width_top,
        edge_width_bottom: row.edge_width_bottom,
        edge_long_right: row.edge_long_right,
        edge_long_left: row.edge_long_left,
    };
}

function assertFlags(row, expected, message) {
    const actual = {};
    Object.keys(expected).forEach((key) => {
        actual[key] = row[key];
    });
    assert.deepEqual(actual, expected, message);
}

async function applyCorner(row, edgeDraft) {
    const values = Object.fromEntries(
        fakeWindow.AlmdinaClippedCornerEditor.cornerValueUpdates(
            {
                position: row.clipped_corner_position,
                cutWidth: row.clipped_corner_width_cm,
                cutLength: row.clipped_corner_length_cm,
            },
            {
                piece_type: row.piece_type,
                clipped_corner_position: row.clipped_corner_position,
                edge_width_top: row.edge_width_top,
                edge_width_bottom: row.edge_width_bottom,
                edge_long_right: row.edge_long_right,
                edge_long_left: row.edge_long_left,
                ...edgeDraft,
            }
        )
    );
    row.edge_break_cost_usd = 0;
    await frappe.model.set_value(row.doctype, row.name, values);
    return row;
}

async function main() {
    const cost = fakeWindow.AlmdinaCostWorkspaceState;
    const coordinator = fakeWindow.AlmdinaWorkspaceSyncCoordinator;
    assert.equal(typeof cost.load, "function");
    assert.equal(typeof formHandlers.child.edge_break, "function");
    assert.equal(typeof formHandlers.child.edge_break_only, "function");
    assert.equal(typeof formHandlers.child.edge_width_top, "function");

    activeTab = "order_tab";
    activeTab = "cost_tab";
    costResponses.push(Promise.resolve(costSnapshot(7.25)));
    await cost.load(frm);
    assert.equal(clipped.edge_break, 1, "Opening Cost must not change the saved full path");
    assert.equal(clipped.edge_break_only, 0);
    assert.equal(clipped.edge_break_cost_usd, 7.25, "Cost projection must still copy calculated fields");

    activeTab = "results_tab";
    coordinator.invalidate(frm, ["cost"], "plan_settings_changed");
    assert.equal(clipped.edge_break, 1, "A plan edit must not rewrite the corner selection");
    assert.equal(regular.edge_width_top, 1, "A plan edit must not rewrite an ordinary side");

    activeTab = "order_tab";

    await applyCorner(clipped, {
        edge_break: 0,
        edge_break_only: 1,
        edge_width_top: 1,
        edge_long_right: 0,
    });
    assertFlags(clipped, {
        edge_break: 0,
        edge_break_only: 1,
        edge_width_top: 1,
        edge_long_right: 0,
    }, "Break-only Apply must remain on the order row after the cost snapshot projects");
    assert.equal(clipped.edge_break_cost_usd, 7.25, "The stale cost refresh still runs during Apply");

    await applyCorner(clipped, {
        edge_break: 1,
        edge_break_only: 0,
        edge_width_top: 0,
        edge_long_right: 0,
    });
    assertFlags(clipped, {
        edge_break: 1,
        edge_break_only: 0,
        edge_width_top: 0,
        edge_long_right: 0,
    }, "Switching back to the full path must replace break-only");

    await applyCorner(clipped, {
        edge_break: 0,
        edge_break_only: 0,
        edge_width_top: 1,
        edge_long_right: 1,
    });
    assertFlags(clipped, {
        edge_break: 0,
        edge_break_only: 0,
        edge_width_top: 1,
        edge_long_right: 1,
    }, "Clearing both corner modes must not restore the cost snapshot");

    await applyCorner(clippedAgain, {
        edge_break: 1,
        edge_break_only: 0,
        edge_width_top: 0,
        edge_long_right: 0,
    });
    assert.equal(clippedAgain.edge_break, 1, "A second corner piece keeps its own Apply");
    assert.equal(clippedAgain.edge_break_only, 0);
    assert.equal(clipped.edge_break, 0, "Applying one piece must not rewrite another");

    await applyCorner(lShaped, {
        edge_break: 1,
        edge_break_only: 0,
        edge_width_top: 1,
        edge_long_right: 1,
        edge_width_bottom: 0,
        edge_long_left: 0,
    });
    assertFlags(lShaped, {
        edge_break: 1,
        edge_break_only: 0,
        edge_width_top: 1,
        edge_long_right: 1,
    }, "L-shaped corner strap Apply must survive the cost projection and keep outer sides");

    await applyCorner(lShaped, {
        edge_break: 0,
        edge_break_only: 0,
        edge_width_top: 1,
        edge_long_right: 1,
    });
    assert.equal(lShaped.edge_break, 0, "Turning the L strap off must not restore a previous value");
    assert.equal(lShaped.edge_width_top, 1);

    regular.edge_width_top = 0;
    await formHandlers.child.edge_width_top(frm, regular.doctype, regular.name);
    assert.equal(regular.edge_width_top, 0, "The same cost refresh must leave an ordinary side edit in place");
    assert.equal(regular.edge_break, 0);
    assert.equal(regular.edge_break_only, 0);

    clipped.edge_break_cost_usd = 0;
    costResponses.push(Promise.resolve(costSnapshot(8.5)));
    await cost.load(frm, { force: true });
    assert.equal(clipped.edge_break, 0, "A late cost response must not restore the old full path");
    assert.equal(clipped.edge_break_only, 0, "A late cost response must not restore break-only either");
    assert.equal(lShaped.edge_break, 0);
    assert.equal(clippedAgain.edge_break, 1, "A late cost response must not clear a newer full path on another piece");
    assert.equal(regular.edge_width_top, 0);
    assert.equal(clipped.edge_break_cost_usd, 8.5, "A late cost response may still refresh calculated cost fields");

    const saved = JSON.parse(JSON.stringify(pieces.map(flags)));
    if (typeof formHandlers.parent.before_save === "function") {
        await formHandlers.parent.before_save(frm);
    }
    const reloaded = JSON.parse(JSON.stringify(saved));
    assert.deepEqual(reloaded, saved, "Save must persist the same corner selections shown on the order");
    assert.deepEqual(reloaded[0], {
        edge_break: 0,
        edge_break_only: 0,
        edge_width_top: 1,
        edge_width_bottom: 0,
        edge_long_right: 1,
        edge_long_left: 0,
    });
    assert.equal(reloaded[1].edge_break, 1);
    assert.equal(reloaded[2].edge_break, 0);
    assert.equal(reloaded[2].edge_width_top, 1);
    assert.equal(reloaded[3].edge_width_top, 0);

    console.log("Corner edge tab navigation regression passed");
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
