"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(relativePath, context) {
    vm.runInContext(fs.readFileSync(path.resolve(__dirname, relativePath), "utf8"), context);
}

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    document: { documentElement: { lang: "ar" } },
    frappe: { utils: { escape_html(value) { return String(value ?? ""); } } },
    __(value) { return Array.isArray(value) ? value[0] : value; },
    Object,
    Array,
    Boolean,
    Number,
    String,
    Math,
    Set,
    console,
});
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js", context);
load("../../public/js/door_cutting_order/drawing/door_cutting_order_machining_overlay.js", context);
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_ux.js", context);
load("../../public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_extra_addons_ux.js", context);
load("../../public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_addons_dialog.js", context);

const dialog = fakeWindow.AlmdinaDoorAddonsDialog;
const row = {
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    piece_no: "P-001",
    qty: 2,
    edge_width_top: 1,
    edge_long_right: 1,
    extra_double: 1,
    extra_full_door_double: 0,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
    liner_start_cm: 0,
    liner_length_cm: 40,
    extra_back_groove: 1,
    back_groove_reference_side: "edge_long_right",
    back_groove_offset_cm: 1,
    back_groove_width_cm: 0.8,
    back_groove_start_cm: 5,
    back_groove_length_cm: 20,
    extra_recessed_handle_cutout: 0,
};
const session = dialog.createSession({ doc: {} }, row);
assert.equal(session.activeField, "extra_double");
assert.equal(session.flags.extra_double, 1);
assert.equal(session.drafts.extra_liner.enabled, true);
assert.equal(session.drafts.extra_back_groove.side, "edge_long_right");
assert.equal(session.drafts.extra_recessed_handle_cutout.enabled, false);

assert.equal(dialog.machiningDirty(session, "extra_liner"), false);
dialog.selectTab(session, "extra_back_groove");
assert.equal(dialog.machiningDirty(session, "extra_liner"), false);
assert.equal(session.activeField, "extra_back_groove");
assert.equal(session.flags.extra_double, 1);
assert.equal(row.extra_back_groove, 1);
assert.equal(session.drafts.extra_recessed_handle_cutout.enabled, false);

dialog.setEnabled(session, "extra_full_door_double", true);
assert.equal(session.flags.extra_full_door_double, 1);
assert.equal(session.flags.extra_double, 0);
assert.equal(row.extra_double, 1);
assert.equal(row.extra_full_door_double, 0);

dialog.setEnabled(session, "extra_recessed_handle_cutout", true);
assert.equal(session.drafts.extra_recessed_handle_cutout.enabled, true);
assert.equal(row.extra_recessed_handle_cutout, 0);

const shown = JSON.parse(JSON.stringify(dialog.enabledPreviewDrafts(session).map(item => item.kind)));
assert.deepEqual(shown, ["liner", "back_groove", "recessed_handle_cutout"]);
const preview = dialog.previewMarkup(session);
assert.match(preview, /data-machining-kind="liner"/);
assert.match(preview, /data-machining-kind="back_groove"/);
assert.match(preview, /data-machining-kind="recessed_handle_cutout"/);
assert.match(preview, /data-liner-edge="1"/);

dialog.setEnabled(session, "extra_liner", false);
assert.equal(dialog.machiningDirty(session, "extra_liner"), true);
assert.equal(dialog.machiningDirty(session, "extra_back_groove"), false);
const afterRemove = JSON.parse(JSON.stringify(dialog.enabledPreviewDrafts(session).map(item => item.kind)));
assert.deepEqual(afterRemove, ["back_groove", "recessed_handle_cutout"]);
assert.equal(row.extra_liner, 1);

const clipped = dialog.createSession({ doc: {} }, {
    piece_type: "L-Shaped Corner",
    width_cm: 50,
    length_cm: 70,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 10,
    clipped_corner_length_cm: 12,
    edge_break: 1,
    edge_width_top: 1,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
    liner_start_cm: 0,
    liner_length_cm: 20,
});
dialog.selectTab(clipped, "extra_liner");
const clippedPreview = dialog.previewMarkup(clipped);
assert.match(clippedPreview, /data-machining-kind="liner"/);
assert.match(clippedPreview, /data-liner-edge="1"/);
const polygon = clippedPreview.match(/<polygon points="([^"]+)"/);
assert.ok(polygon && polygon[1].split(" ").length >= 5);

const special = dialog.createSession({ doc: {} }, {
    piece_type: "Special",
    width_cm: 30,
    length_cm: 40,
    extra_double: 1,
});
assert.equal(special.supported, false);
assert.equal(special.flags.extra_double, 1);
assert.equal(Object.keys(special.drafts).length, 0);

console.log("Unified add-ons dialog session passed");
