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
assert.equal(api.renderControl({ piece_type: "Regular" }, { editable: true }), "");

const emptyExtra = api.renderControl({ piece_type: "Extra" }, { editable: true });
assert.match(emptyExtra, /aria-haspopup="dialog"/);
assert.match(emptyExtra, /اختر إضافة واحدة على الأقل/);

const selectedExtra = api.renderControl(
    { piece_type: "Extra", extra_liner: 1 },
    { editable: true }
);
assert.match(selectedExtra, /Liner/);
assert.match(selectedExtra, /<b>1<\/b>/);
assert.match(api.notesCueHtml({ piece_type: "Extra", notes: "" }), /اكتب تفاصيل التنفيذ/);
assert.equal(api.notesCueHtml({ piece_type: "Extra", notes: "تم" }), "");

console.log("Extra door add-ons UX simulation passed");
