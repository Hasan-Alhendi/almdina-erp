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

const ARABIC = {
    Regular: "عادية",
    Special: "خاصة",
    "Clipped corner": "الزاوية الكسر",
    "L-shaped corner": "زاوية L",
    Glass: "درفة بلور",
    "Piece type": "نوع الدرفة",
    "Double Banding": "دبل قشاط",
    "Full Double": "دبل كامل",
    Liner: "لاينر",
    "Back Groove": "فرزة ظهر",
    "Recessed Handle": "مسكة غطس",
    "Recessed Handle Cutout": "حفر مسكة غطس",
    "Double Edge Banding": "دبل قشاط",
    "Full Door Double": "دبل كامل الدرفة",
    "Add-ons": "الإضافات",
};
let useArabic = true;
function __(value) {
    const text = Array.isArray(value) ? value[0] : value;
    return useArabic ? (ARABIC[text] || text) : text;
}

const fakeWindow = {};
const documentStub = { documentElement: { lang: "ar" } };
const csv = fs.readFileSync(path.resolve(__dirname, "../../translations/ar.csv"), "utf8");
const translations = new Map(csv.split(/\r?\n/).map(line => {
    const delimiter = line.indexOf(",");
    return delimiter < 0 ? ["", ""] : [line.slice(0, delimiter), line.slice(delimiter + 1).split(",")[0]];
}));
function translate(message) {
    return documentStub.documentElement.lang === "ar"
        ? (translations.get(String(message)) || String(message))
        : String(message);
}
const context = vm.createContext({
    window: fakeWindow,
    document: documentStub,
    __: translate,
    frappe: {
        boot: { lang: "ar" },
        utils: { escape_html(value) { return String(value); } },
    },
    __,
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
    ["Regular", "Special", "Clipped Corner", "L-Shaped Corner", "Glass"]
);
assert.deepEqual(
    JSON.parse(JSON.stringify(api.FIELDS.map(item => item.button))),
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
assert.match(picker, /value="Glass"/);
assert.match(picker, />درفة بلور<\/option>/);
assert.doesNotMatch(picker, /value="Extra"/);

const emptySummary = api.addonSummary({});
assert.equal(emptySummary.label, "الإضافات");
assert.equal(emptySummary.hidden, 0);
assert.deepEqual(JSON.parse(JSON.stringify(emptySummary.names)), []);
const emptyButton = api.renderAddonSummary({}, { editable: true });
assert.match(emptyButton, /data-open-addons="1"/);
assert.match(emptyButton, /الإضافات/);
const readOnlySummary = api.renderAddonSummary({ extra_liner: 1 }, { editable: false, virtual: false });
assert.match(readOnlySummary, /data-open-addons="1"/);
assert.doesNotMatch(readOnlySummary, /disabled/);
assert.match(api.renderAddonSummary({}, { editable: false, virtual: true }), /disabled/);
assert.doesNotMatch(emptyButton, />0<|>\+0</);

const one = api.addonSummary({ extra_liner: 1 });
assert.deepEqual(JSON.parse(JSON.stringify(one.names)), ["لاينر"]);
assert.equal(one.label, "لاينر");
assert.match(api.renderAddonSummary({ extra_liner: 1 }, { editable: true }), /لاينر/);

const two = api.addonSummary({ extra_liner: 1, extra_back_groove: 1, extra_double: 0 });
assert.equal(two.label, "لاينر · فرزة ظهر");
assert.equal(two.hidden, 0);
assert.equal(two.tooltip, "لاينر · فرزة ظهر");

const many = api.addonSummary({
    extra_double: 1,
    extra_liner: 1,
    extra_back_groove: 1,
    extra_recessed_handle_cutout: 1,
});
assert.deepEqual(JSON.parse(JSON.stringify(many.names)), ["دبل قشاط", "لاينر", "فرزة ظهر", "مسكة غطس"]);
assert.equal(many.label, "دبل قشاط · لاينر");
assert.equal(many.hidden, 2);
assert.equal(many.tooltip, "دبل قشاط · لاينر · فرزة ظهر · مسكة غطس");
const manyButton = api.renderAddonSummary({
    extra_double: 1,
    extra_liner: 1,
    extra_back_groove: 1,
    extra_recessed_handle_cutout: 1,
}, { editable: true });
assert.match(manyButton, /دبل قشاط · لاينر/);
assert.match(manyButton, /\+2/);
assert.match(manyButton, /title="دبل قشاط · لاينر · فرزة ظهر · مسكة غطس"/);
assert.doesNotMatch(manyButton, /✓|dco-check-mark/);

useArabic = false;
const english = api.addonSummary({ extra_recessed_handle_cutout: 1 });
assert.equal(english.label, "Recessed Handle");
useArabic = true;

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

const glass = { piece_type: "Glass", glass_margin_mm: 65 };
assert.equal(api.reconcilePieceType({ dirty() {} }, glass), false);
assert.equal(glass.piece_type, "Glass");
assert.equal(glass.glass_margin_mm, 65);

const legacy = { piece_type: "Extra", extra_liner: 1 };
let dirtyCalls = 0;
assert.equal(api.reconcilePieceType({ dirty() { dirtyCalls += 1; } }, legacy), true);
assert.equal(legacy.piece_type, "Regular");
assert.equal(legacy.extra_liner, 1);
assert.equal(dirtyCalls, 1);

console.log("Independent door add-ons UX simulation passed");
