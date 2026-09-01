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
        utils: {
            escape_html(value) {
                return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;");
            },
        },
        ui: { form: { on() {} } },
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
assert.equal(api.TYPE, "Extra");
assert.deepEqual(
    JSON.parse(JSON.stringify(api.selectedFields({
        piece_type: "Extra",
        extra_double: 1,
        extra_liner: 0,
        extra_back_groove: 0,
        extra_recessed_handle_cutout: 1,
    }).map(item => item.fieldname))),
    ["extra_double", "extra_recessed_handle_cutout"]
);
assert.deepEqual(
    JSON.parse(JSON.stringify(api.selectedFields({
        piece_type: "Extra",
        extra_back_groove: 1,
    }).map(item => item.fieldname))),
    ["extra_back_groove"]
);

assert.equal(api.physicalCutQuantity({ qty: 3, extra_full_door_double: 1 }), 6);
assert.equal(api.physicalCutQuantity({ qty: 3 }), 3);

const regularPicker = api.renderTypePicker({ piece_type: "Regular" }, { editable: true });
assert.match(regularPicker, /<select class="dco-fast-select dco-piece-type-select"/);
assert.match(regularPicker, /data-field="piece_type"/);
assert.match(regularPicker, />عادية<\/option>/);
assert.doesNotMatch(regularPicker, /dco-piece-type-trigger/);
assert.doesNotMatch(regularPicker, /dco-extra-open-button/);

const specialIndex = regularPicker.indexOf(">خاصة</option>");
const cornerIndex = regularPicker.indexOf(">زاوية</option>");
const extraIndex = regularPicker.indexOf(">Extra</option>");
assert.ok(specialIndex > regularPicker.indexOf(">عادية</option>"));
assert.ok(cornerIndex > specialIndex);
assert.ok(extraIndex > cornerIndex);

const emptyExtra = api.renderTypePicker({ piece_type: "Extra" }, { editable: true });
assert.match(emptyExtra, /dco-piece-type-select/);
assert.match(emptyExtra, /dco-extra-open-button/);
assert.match(emptyExtra, /اختر إضافة واحدة على الأقل/);

const selectedExtra = api.renderTypePicker(
    { piece_type: "Extra", extra_liner: 1, extra_double: 1 },
    { editable: true }
);
assert.match(selectedExtra, /دبل قشاط، لاينر/);
assert.match(selectedExtra, /dco-extra-open-count">2<\/b>/);

const submenu = api.renderSubmenu({ piece_type: "Extra" });
assert.match(submenu, /إضافات Extra/);
assert.match(submenu, /لاينر/);
assert.match(submenu, /فرزة ظهر/);
assert.match(submenu, /دبل قشاط/);
assert.match(submenu, /دبل كامل الدرفة/);
assert.match(submenu, /حفر مسكة غطس/);
assert.match(submenu, /يمكن اختيار أكثر من خيار/);
assert.doesNotMatch(submenu, /data-piece-type-option/);
assert.doesNotMatch(submenu, /تطبيق/);
assert.doesNotMatch(submenu, /إلغاء/);

// In-place type refresh must preserve the actual native select node so the
// table-performance owner can restore keyboard focus after changing the type.
const nativeSelect = { value: "Regular", disabled: false };
const nativeShell = {
    dataset: {},
    querySelector(selector) {
        return selector === "select.dco-piece-type-select[data-field='piece_type']"
            ? nativeSelect
            : null;
    },
    querySelectorAll() { return []; },
};
const typeCell = {
    querySelector(selector) {
        return selector === ".dco-piece-type-native" ? nativeShell : null;
    },
};
const tableRow = {
    classList: { toggle() {} },
    querySelector(selector) {
        if (selector === ".dco-col-type") return typeCell;
        if (selector === ".dco-col-notes") return null;
        return null;
    },
};
api.syncRowPresentation({}, tableRow, { piece_type: "Special" }, { editable: true });
assert.strictEqual(
    nativeShell.querySelector("select.dco-piece-type-select[data-field='piece_type']"),
    nativeSelect
);
assert.equal(nativeSelect.value, "Special");
assert.equal(nativeSelect.disabled, false);

assert.match(api.notesCueHtml({ piece_type: "Extra", notes: "" }), /اكتب تفاصيل التنفيذ/);
assert.equal(api.notesCueHtml({ piece_type: "Extra", notes: "تم" }), "");

console.log("Extra door add-ons native-select UX simulation passed");
