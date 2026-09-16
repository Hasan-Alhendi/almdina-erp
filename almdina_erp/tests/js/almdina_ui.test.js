"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/almdina_ui.js"),
    "utf8"
);

const fakeWindow = {
    frappe: {
        utils: {
            escape_html(value) {
                return String(value ?? "")
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&#039;");
            },
        },
    },
};

vm.runInContext(source, vm.createContext({
    window: fakeWindow,
    console,
    Object,
    String,
}), { filename: "almdina_ui.js" });

const ui = fakeWindow.AlmdinaUi;
assert.ok(ui);
assert.equal(Object.isFrozen(ui), true);

const primary = ui.button({ label: "حفظ", variant: "primary", className: "apc-save" });
assert.match(primary, /class="btn alm-btn-primary apc-save"/);
assert.match(primary, />حفظ</);

const secondary = ui.button({
    label: "تراجع",
    variant: "secondary",
    className: "apc-reset",
    disabled: true,
});
assert.match(secondary, /class="btn btn-default apc-reset"/);
assert.match(secondary, /disabled/);

const empty = ui.empty({ title: "لا توجد بيانات", message: "اختر دورًا للمتابعة." });
assert.match(empty, /class="alm-empty"/);
assert.match(empty, /لا توجد بيانات/);

console.log("Almdina design system UI builder tests passed");
