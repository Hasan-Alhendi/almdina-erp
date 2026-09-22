"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/almdina_ui.js"),
    "utf8"
);

function createParent() {
    const classes = new Set();
    return {
        jquery: true,
        length: 1,
        empty() {
            return this;
        },
        addClass(name) {
            String(name || "").split(/\s+/).filter(Boolean).forEach((entry) => classes.add(entry));
            return this;
        },
        removeClass(name) {
            String(name || "").split(/\s+/).filter(Boolean).forEach((entry) => classes.delete(entry));
            return this;
        },
        hasClass(name) {
            return classes.has(name);
        },
    };
}

const fakeControls = [];
const fakeFieldGroups = [];
const fakeUploaders = [];
const frappeOwnedHandlers = [];
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
        ui: {
            FieldGroup: class {
                constructor(opts) {
                    this.opts = opts;
                    this.fields_dict = {};
                    this.fields_list = (opts.fields || []).map(df => {
                        const field = {
                            df,
                            value: df.default || "",
                            get_value() {
                                return this.value;
                            },
                            set_value(value) {
                                this.value = value;
                                return Promise.resolve().then(() => {
                                    if (typeof this.df.change === "function") {
                                        return this.df.change.call(this, {type: "change"});
                                    }
                                });
                            },
                            userChange(value) {
                                this.value = value;
                                return Promise.resolve().then(() => {
                                    if (typeof this.df.change === "function") {
                                        return this.df.change.call(this, {type: "change", user: true});
                                    }
                                });
                            },
                            set_focus() {},
                        };
                        this.fields_dict[df.fieldname] = field;
                        return field;
                    });
                    fakeFieldGroups.push(this);
                }
                make() {}
                get_values() {
                    const values = {};
                    this.fields_list.forEach(field => {
                        values[field.df.fieldname] = field.get_value();
                    });
                    return values;
                }
                set_value(fieldname, value) {
                    if (this.fields_dict[fieldname]) return this.fields_dict[fieldname].set_value(value);
                    return Promise.resolve();
                }
            },
            form: {
                make_control(opts) {
                    const handlers = new Map();
                    const control = {
                        df: opts.df,
                        value: opts.df.default || "",
                        $input: {
                            handlers,
                            on(event, handler) {
                                String(event).split(/\s+/).filter(Boolean).forEach((name) => {
                                    const current = this.handlers.get(name) || [];
                                    current.push(handler);
                                    this.handlers.set(name, current);
                                });
                            },
                            focus() {},
                        },
                        refresh() {},
                        get_value() {
                            return this.value;
                        },
                        set_value(next) {
                            this.value = next;
                            return Promise.resolve().then(() => {
                                if (typeof this.df.change === "function") {
                                    return this.df.change.call(this, {type: "change"});
                                }
                            });
                        },
                        userChange(next) {
                            this.value = next;
                            return Promise.resolve().then(() => {
                                if (typeof this.df.change === "function") {
                                    return this.df.change.call(this, {type: "change", user: true});
                                }
                            });
                        },
                    };
                    const nativeHandler = () => {};
                    control.$input.on("change", nativeHandler);
                    frappeOwnedHandlers.push({control, nativeHandler});
                    fakeControls.push({ opts, control });
                    return control;
                },
            },
            FileUploader: class {
                constructor(options) {
                    this.options = options;
                    fakeUploaders.push(options);
                }
            },
        },
    },
};

function $(value) {
    if (value && value.jquery) return value;
    return createParent();
}

vm.runInContext(source, vm.createContext({
    window: fakeWindow,
    console,
    Object,
    String,
    $,
}), { filename: "almdina_ui.js" });

const ui = fakeWindow.AlmdinaUi;
assert.ok(ui);
assert.equal(Object.isFrozen(ui), true);

async function run() {
async function flush() {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}
const primary = ui.button({ label: "حفظ", variant: "primary", className: "apc-save" });
assert.match(primary, /class="btn alm-btn-primary apc-save"/);
assert.match(primary, />حفظ</);

const secondary = ui.button({
    label: "تراجع",
    variant: "secondary",
    className: "apc-reset",
    disabled: true,
});
assert.match(secondary, /class="btn alm-btn-secondary apc-reset"/);
assert.match(secondary, /disabled/);

const empty = ui.empty({ title: "لا توجد بيانات", message: "اختر دورًا للمتابعة." });
assert.match(empty, /class="alm-empty"/);
assert.match(empty, /لا توجد بيانات/);

const parent = createParent();
let changed = 0;
const mounted = ui.control({
    parent,
    fieldname: "search",
    fieldtype: "Data",
    placeholder: "ابحث...",
    default: "abc",
    className: "apa-search-control",
    onChange: () => {
        changed += 1;
    },
});
assert.equal(fakeControls.length, 1);
assert.equal(fakeControls[0].opts.df.fieldtype, "Data");
assert.equal(fakeControls[0].opts.only_input, true);
assert.equal(parent.hasClass("alm-control"), true);
assert.equal(parent.hasClass("apa-search-control"), true);
assert.equal(mounted.getValue(), "abc");
await flush();
assert.equal(changed, 0, "initial async value must not trigger Almdina");
await mounted.setValue("xyz");
assert.equal(mounted.getValue(), "xyz");
assert.equal(changed, 0, "programmatic sync must not bounce into Almdina state");
changed = 0;
for (const handler of fakeControls[0].control.$input.handlers.get("input") || []) {
    handler({target: {value: "typed"}});
}
assert.equal(changed, 0, "Almdina must not subscribe to the Frappe-owned input event");
await fakeControls[0].control.userChange("new-value");
assert.equal(changed, 1, "Data changes must use the native control contract exactly once");
const dataOwnedHandler = frappeOwnedHandlers[0];
mounted.dispose();
assert.equal(dataOwnedHandler.control.$input.handlers.get("change").includes(dataOwnedHandler.nativeHandler), true);
assert.equal(mounted.dispose(), false, "dispose must be idempotent");
assert.equal(parent.hasClass("alm-control"), false);
assert.equal(parent.hasClass("apa-search-control"), false);

const linkParent = createParent();
let linkChanged = 0;
const linkMounted = ui.control({
    parent: linkParent,
    fieldname: "operational_role",
    fieldtype: "Link",
    options: "Role",
    value: "Order Entry",
    onChange: () => {
        linkChanged += 1;
    },
});
assert.equal(fakeControls.length, 2);
assert.equal(fakeControls[1].opts.df.fieldtype, "Link");
await flush();
assert.equal(linkChanged, 0, "initial Link value must not trigger Almdina");
await fakeControls[1].control.userChange("Order Entry");
assert.equal(linkChanged, 1);
fakeControls[1].control.$input.handlers.set("input", [() => {}]);
for (const handler of fakeControls[1].control.$input.handlers.get("input")) handler({target: {value: "Ord"}});
assert.equal(linkChanged, 1, "Link typing must not be treated as final selection");
linkMounted.dispose();

const selectParent = createParent();
let selectChanged = 0;
const selectMounted = ui.control({
    parent: selectParent,
    fieldname: "status",
    fieldtype: "Select",
    options: "A\nB",
    value: "A",
    onChange: () => { selectChanged += 1; },
});
await flush();
await fakeControls[2].control.userChange("B");
assert.equal(selectChanged, 1, "Select changes must use the native control contract exactly once");
selectMounted.dispose();

const remountParent = createParent();
let remountChanged = 0;
const firstMount = ui.control({
    parent: remountParent,
    fieldname: "remount",
    fieldtype: "Data",
    onChange: () => { remountChanged += 1; },
});
firstMount.dispose();
const secondMount = ui.control({
    parent: remountParent,
    fieldname: "remount",
    fieldtype: "Data",
    onChange: () => { remountChanged += 1; },
});
await fakeControls[4].control.userChange("one");
assert.equal(remountChanged, 1, "remount must leave one Almdina callback owner");
secondMount.dispose();

const nativeOrder = [];
const nativeContractMount = ui.control({
    parent: createParent(),
    fieldname: "native_contract",
    fieldtype: "Data",
    df: {
        change() {
            nativeOrder.push("frappe");
            return {then: resolve => resolve("native-result")};
        },
    },
    onChange: () => nativeOrder.push("almdina"),
});
await fakeControls[5].control.userChange("validated");
assert.deepEqual(nativeOrder, ["frappe", "almdina"], "native async change contract must remain ordered");
nativeContractMount.dispose();

let lateChanged = 0;
const pendingMount = ui.control({
    parent: createParent(),
    fieldname: "pending",
    fieldtype: "Data",
    onChange: () => { lateChanged += 1; },
});
const pendingChange = fakeControls[6].control.userChange("late");
pendingMount.dispose();
await pendingChange;
assert.equal(lateChanged, 0, "dispose must suppress a pending native callback");

const filterParent = createParent();
let filterChanged = 0;
const filterMounted = ui.filterGroup({
    parent: filterParent,
    className: "prw-filter-group",
    fields: [
        { fieldname: "search", fieldtype: "Data", label: "بحث" },
        { fieldname: "status", fieldtype: "Select", label: "الحالة", options: "A\nB" },
    ],
    values: { search: "needle", status: "A" },
    onChange: (fieldname) => {
        if (fieldname === "search") filterChanged += 1;
    },
});
assert.equal(fakeFieldGroups.length, 1);
assert.equal(filterParent.hasClass("alm-filter-group"), true);
assert.equal(filterParent.hasClass("prw-filter-group"), true);
assert.equal(filterMounted.getValue("search"), "needle");
await flush();
assert.equal(filterChanged, 0, "initial FieldGroup values must not trigger domain callbacks");
await filterMounted.setValue("search", "updated");
assert.equal(filterMounted.getValue("search"), "updated");
assert.equal(filterChanged, 0, "FieldGroup UI sync must not bounce into domain state");
filterChanged = 0;
await fakeFieldGroups[0].fields_list[0].userChange("changed");
assert.equal(filterChanged, 1);
await filterMounted.setValues({search: "changed"});
assert.equal(filterChanged, 1, "setValues must remain silent after native change");
filterMounted.dispose();
assert.equal(filterParent.hasClass("alm-filter-group"), false);
assert.equal(filterMounted.dispose(), false, "filterGroup dispose must be idempotent");

assert.doesNotMatch(source, /\.off\(\s*["'](?:input|change|input change)/);
assert.doesNotMatch(source, /frappeControl\.change\s*=/);

const uploader = ui.fileUploader({
    preset: "securePrivate",
    restrictions: { allowed_file_types: [".dxf"] },
    on_success() {},
});
assert.equal(fakeUploaders.length, 1);
assert.equal(uploader.options.folder, "Home/Attachments");
assert.equal(uploader.options.make_attachments_public, false);
assert.equal(uploader.options.allow_toggle_private, false);
assert.equal(uploader.options.disable_file_browser, true);
assert.equal(uploader.options.restrictions.allowed_file_types[0], ".dxf");
assert.equal(uploader.options.preset, undefined);

console.log("Almdina design system UI builder tests passed");
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
