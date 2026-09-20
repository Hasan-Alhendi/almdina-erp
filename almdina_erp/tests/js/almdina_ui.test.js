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
                            change() {},
                            get_value() {
                                return this.value;
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
                    if (this.fields_dict[fieldname]) this.fields_dict[fieldname].value = value;
                }
            },
            form: {
                make_control(opts) {
                    const control = {
                        df: opts.df,
                        value: opts.df.default || "",
                        $input: {
                            handlers: {},
                            on(event, handler) {
                                String(event).split(/\s+/).filter(Boolean).forEach((name) => {
                                    this.handlers[name] = handler;
                                });
                            },
                            off(event) {
                                String(event).split(/\s+/).filter(Boolean).forEach((name) => {
                                    delete this.handlers[name];
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
                        },
                        change() {},
                    };
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
mounted.setValue("xyz");
assert.equal(mounted.getValue(), "xyz");
fakeControls[0].control.$input.handlers.input();
assert.equal(changed, 1);
mounted.dispose();
assert.equal(parent.hasClass("alm-control"), false);
assert.equal(parent.hasClass("apa-search-control"), false);

const linkParent = createParent();
let linkChanged = 0;
const linkMounted = ui.control({
    parent: linkParent,
    fieldname: "operational_role",
    fieldtype: "Link",
    options: "Role",
    onChange: () => {
        linkChanged += 1;
    },
});
assert.equal(fakeControls.length, 2);
assert.equal(fakeControls[1].opts.df.fieldtype, "Link");
fakeControls[1].control.change();
assert.equal(linkChanged, 1);
linkMounted.dispose();

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
filterMounted.setValue("search", "updated");
assert.equal(filterMounted.getValue("search"), "updated");
fakeFieldGroups[0].fields_list[0].change();
assert.equal(filterChanged, 1);
filterMounted.dispose();
assert.equal(filterParent.hasClass("alm-filter-group"), false);

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
