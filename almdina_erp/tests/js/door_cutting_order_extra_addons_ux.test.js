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
        extra_recessed_handle_cutout: 1,
    }).map(item => item.fieldname))),
    ["extra_double", "extra_recessed_handle_cutout"]
);

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
assert.match(selectedExtra, /لاينر، دبل/);
assert.match(selectedExtra, /dco-extra-open-count">2<\/b>/);

const submenu = api.renderSubmenu({ piece_type: "Extra" });
assert.match(submenu, /إضافات Extra/);
assert.match(submenu, /لاينر/);
assert.match(submenu, /دبل/);
assert.match(submenu, /مسكة غطس/);
assert.match(submenu, /يمكن اختيار أكثر من خيار/);
assert.doesNotMatch(submenu, /data-piece-type-option/);
assert.doesNotMatch(submenu, /تطبيق/);
assert.doesNotMatch(submenu, /إلغاء/);

assert.match(api.notesCueHtml({ piece_type: "Extra", notes: "" }), /اكتب تفاصيل التنفيذ/);
assert.equal(api.notesCueHtml({ piece_type: "Extra", notes: "تم" }), "");

console.log("Extra door add-ons native-select UX simulation passed");
