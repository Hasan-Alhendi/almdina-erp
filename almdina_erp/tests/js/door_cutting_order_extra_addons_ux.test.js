"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_extra_addons_ux.js"
    ),
    "utf8"
);

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    document: { documentElement: { lang: "ar" } },
    frappe: {
        boot: { lang: "ar" },
        utils: { escape_html(value) { return String(value); } },
    },
    Object,
    Array,
    Boolean,
    Number,
    String,
    Set,
    console,
});
vm.runInContext(source, context);

const api = fakeWindow.AlmdinaExtraDoorAddonsUX;
assert.ok(api);
assert.deepEqual(
    JSON.parse(JSON.stringify(api.PIECE_TYPES.map(item => item.value))),
    ["Regular", "Special", "Clipped Corner", "L-Shaped Corner"]
);
assert.deepEqual(
    JSON.parse(JSON.stringify(api.FIELDS.map(item => item.buttonAr))),
    ["دبل قشاط", "دبل كامل", "لاينر", "فرزة ظهر", "مسكة غطس"]
);
assert.deepEqual(
    JSON.parse(JSON.stringify(api.FIELDS.map(item => item.buttonEn))),
    ["Double Banding", "Full Double", "Liner", "Back Groove", "Recessed Handle"]
);

for (const pieceType of api.PIECE_TYPES.map(item => item.value)) {
    assert.deepEqual(
        JSON.parse(JSON.stringify(api.selectedFields({
            piece_type: pieceType,
            extra_double: 1,
            extra_liner: 1,
        }).map(item => item.fieldname))),
        ["extra_double", "extra_liner"]
    );
}

assert.equal(api.physicalCutQuantity({ qty: 3, extra_full_door_double: 1 }), 6);
assert.equal(api.physicalCutQuantity({ qty: 3, extra_liner: 1 }), 3);

const picker = api.renderTypePicker({ piece_type: "Regular" }, { editable: true });
assert.match(picker, /<select class="dco-fast-select dco-piece-type-select"/);
assert.match(picker, /data-field="piece_type"/);
assert.match(picker, />عادية<\/option>/);
assert.match(picker, />خاصة<\/option>/);
assert.match(picker, />الزاوية الكسر<\/option>/);
assert.match(picker, />زاوية L<\/option>/);
assert.doesNotMatch(picker, /value="Extra"/);

const cell = api.renderAddonCell({ extra_liner: 1 }, "extra_liner", { editable: true });
assert.match(cell, /dco-col-addon|dco-addon-toggle/);
assert.match(cell, /data-check-field="extra_liner"/);
assert.match(cell, /aria-pressed="true"/);
assert.match(cell, /لاينر/);
assert.doesNotMatch(cell, /✓|dco-check-mark/);

const arabicFullLabelCell = api.renderAddonCell(
    { extra_full_door_double: 1 },
    "extra_full_door_double",
    { editable: true }
);
assert.match(arabicFullLabelCell, /دبل كامل الدرفة/);
assert.match(arabicFullLabelCell, />دبل<\/span>\s*<span class="dco-addon-label-line">كامل<\/span>/);
assert.doesNotMatch(arabicFullLabelCell, /✓|dco-check-mark/);

context.document.documentElement.lang = "en";
const englishFullLabelCell = api.renderAddonCell(
    { extra_recessed_handle_cutout: 1 },
    "extra_recessed_handle_cutout",
    { editable: true }
);
assert.match(englishFullLabelCell, /Recessed Handle Cutout/);
assert.match(englishFullLabelCell, />Recessed<\/span>\s*<span class="dco-addon-label-line">Handle<\/span>/);
assert.doesNotMatch(englishFullLabelCell, /✓|dco-check-mark/);
context.document.documentElement.lang = "ar";

const row = { extra_double: 1, extra_full_door_double: 0 };
assert.deepEqual(
    JSON.parse(JSON.stringify(api.enforceMutualExclusivity(row, "extra_full_door_double", true))),
    ["extra_full_door_double", "extra_double"]
);
assert.equal(row.extra_double, 0);
assert.equal(row.extra_full_door_double, 1);
assert.deepEqual(
    JSON.parse(JSON.stringify(api.enforceMutualExclusivity(row, "extra_liner", true))),
    ["extra_liner"]
);
assert.equal(row.extra_full_door_double, 1);

const legacy = { piece_type: "Extra", extra_liner: 1 };
let dirtyCalls = 0;
assert.equal(api.reconcilePieceType({ dirty() { dirtyCalls += 1; } }, legacy), true);
assert.equal(legacy.piece_type, "Regular");
assert.equal(legacy.extra_liner, 1);
assert.equal(dirtyCalls, 1);

console.log("Independent door add-ons UX simulation passed");
