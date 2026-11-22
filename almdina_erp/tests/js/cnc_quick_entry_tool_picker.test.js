"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");

function load(relative, sandbox) {
    const file = path.join(root, relative);
    vm.runInNewContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
}

function element(tag) {
    const node = {
        tag,
        children: [],
        attrs: {},
        hidden: false,
        value: "",
        textContent: "",
        className: "",
        parent: null,
        ownerDocument: null,
        dataset: {},
        listeners: {},
        options: [],
        appendChild(child) {
            child.parent = node;
            child.ownerDocument = node.ownerDocument;
            node.children.push(child);
            if (child.tag === "option") node.options.push(child);
            if (child.tag === "text") node.textContent += child.textContent;
            return child;
        },
        setAttribute(name, value) {
            node.attrs[name] = String(value);
            if (name === "value") node.value = String(value);
            if (name === "class") node.className = String(value);
        },
        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(node.attrs, name) ? node.attrs[name] : null;
        },
        addEventListener(type, fn) {
            node.listeners[type] = node.listeners[type] || [];
            node.listeners[type].push(fn);
        },
        dispatch(type, event) {
            (node.listeners[type] || []).forEach(fn => fn(event));
        },
        querySelector(selector) {
            return walk(node, selector)[0] || null;
        },
        querySelectorAll(selector) {
            return walk(node, selector);
        },
        contains(other) {
            let current = other;
            while (current) {
                if (current === node) return true;
                current = current.parent;
            }
            return false;
        },
        closest(selector) {
            let current = node;
            while (current) {
                if (matches(current, selector)) return current;
                current = current.parent;
            }
            return null;
        },
    };
    return node;
}

function matches(node, selector) {
    if (!node || node.tag === "fragment") return false;
    if (selector === "input") return node.tag === "input";
    if (selector.startsWith(".")) {
        return String(node.className || "").split(/\s+/).includes(selector.slice(1));
    }
    if (selector.startsWith("[") && selector.endsWith("]")) {
        return Object.prototype.hasOwnProperty.call(node.attrs, selector.slice(1, -1));
    }
    if (selector.includes(" ")) {
        return false;
    }
    return false;
}

function walk(node, selector) {
    const parts = String(selector || "").trim().split(/\s+/);
    if (parts.length > 1) {
        const found = [];
        walk(node, parts[0]).forEach(parent => {
            parent.children.forEach(child => {
                walk(child, parts.slice(1).join(" ")).forEach(item => {
                    if (!found.includes(item)) found.push(item);
                });
            });
        });
        return found;
    }
    const found = [];
    if (matches(node, selector)) found.push(node);
    (node.children || []).forEach(child => {
        if (child.children) walk(child, selector).forEach(item => found.push(item));
    });
    return found;
}

function parseAttrs(source, node) {
    const attrRe = /([^\s=]+)(?:="([^"]*)")?/g;
    let match = attrRe.exec(source || "");
    while (match) {
        if (match[2] == null) {
            node.attrs[match[1]] = "";
            if (match[1] === "hidden") node.hidden = true;
        } else {
            node.setAttribute(match[1], match[2]);
        }
        match = attrRe.exec(source);
    }
}

function parseHTML(html, doc) {
    const root = element("fragment");
    root.ownerDocument = doc;
    const stack = [root];
    const re = /<\/?([a-zA-Z0-9-]+)([^>]*)>|([^<]+)/g;
    const voidTags = new Set(["input", "br", "img"]);
    let match = re.exec(html);
    while (match) {
        if (match[3]) {
            const text = element("text");
            text.textContent = match[3];
            text.ownerDocument = doc;
            stack[stack.length - 1].appendChild(text);
        } else if (match[0].startsWith("</")) {
            stack.pop();
        } else {
            const node = element(match[1].toLowerCase());
            node.ownerDocument = doc;
            parseAttrs(match[2], node);
            stack[stack.length - 1].appendChild(node);
            if (!voidTags.has(node.tag) && !match[0].endsWith("/>")) stack.push(node);
        }
        match = re.exec(html);
    }
    return root;
}

function installDom(sandbox) {
    const doc = element("document");
    doc.ownerDocument = doc;
    doc.addEventListener = element("document").addEventListener;
    const documentNode = element("document");
    documentNode.ownerDocument = documentNode;
    sandbox.document = documentNode;
    sandbox.Node = { prototype: {} };
    return documentNode;
}

function hostFor(markup, doc) {
    const host = element("div");
    host.ownerDocument = doc;
    Object.defineProperty(host, "innerHTML", {
        configurable: true,
        set(html) {
            host.children = [];
            const parsed = parseHTML(html, doc);
            parsed.children.forEach(child => host.appendChild(child));
        },
    });
    host.innerHTML = markup;
    return host;
}

const english = {
    window: {},
    document: { documentElement: { lang: "en", getAttribute() { return "ltr"; } } },
    frappe: { boot: { lang: "en" }, ui: { form: {} } },
};
english.window = english;
english.frappe.ready = fn => fn();
load("public/js/almdina_locale.js", english);
load("public/js/cnc/cnc_field_labels.js", english);
load("public/js/cnc/cnc_tool_picker.js", english);

class QuickEntryForm {
    constructor(doctype, afterInsert, initCallback, doc) {
        this.doctype = doctype;
        this.doc = doc || {};
        this.docfields = [];
        this.fields_dict = {};
        this.intros = [];
    }

    render_dialog() {
        this.fields_dict = {};
        this.docfields.forEach(df => {
            const control = {
                df: Object.assign({}, df),
                labelText: df.label,
                _value: this.doc[df.fieldname] == null ? "" : this.doc[df.fieldname],
                set_label(text) {
                    this.labelText = text;
                    this.df.label = text;
                },
                get_value() {
                    return this._value;
                },
                refresh() {},
                $input: null,
            };
            if (df.fieldname === "post_processor") {
                const option = { value: "ima_wh_ncstudio", textContent: "ima_wh_ncstudio" };
                control.$input = { get() { return { options: [option] }; } };
                control.option = option;
            }
            this.fields_dict[df.fieldname] = control;
        });
    }

    set_df_property(name, prop, value) {
        const field = this.fields_dict[name];
        if (field) field.df[prop] = value;
    }

    toggle_display(name, show) {
        const field = this.fields_dict[name];
        if (field) field.df.hidden = show ? 0 : 1;
    }

    toggle_reqd(name, mandatory) {
        const field = this.fields_dict[name];
        if (field) field.df.reqd = mandatory ? 1 : 0;
    }

    set_intro(text) {
        this.intros.push(text);
    }

    get_field(name) {
        return this.fields_dict[name];
    }
}

english.frappe.ui.form.QuickEntryForm = QuickEntryForm;
assert.strictEqual(english.AlmdinaCncLabels.installQuickEntryForms(), true);
assert.ok(english.frappe.ui.form.CNCToolPresetQuickEntryForm);
assert.ok(english.frappe.ui.form.CNCMachineQuickEntryForm);
assert.strictEqual(english.frappe.ui.form.OtherDocTypeQuickEntryForm, undefined);

const toolFields = [
    ["tool_name", "Tool Name"],
    ["tool_number", "Tool Number"],
    ["tool_diameter_mm", "Tool Diameter (mm)"],
    ["spindle_speed_rpm", "Spindle Speed (RPM)"],
    ["stepdown_mm", "Stepdown"],
    ["final_tool_offset_mm", "Final Tool Offset"],
    ["stepover_size_mm", "Stepover Size"],
    ["stepover_percent", "Stepover Percent of D"],
    ["feed_rate_mm_sec", "Feed Rate (mm/sec)"],
    ["plunge_rate_mm_sec", "Plunge Rate (mm/sec)"],
    ["notes", "Notes"],
    ["enabled", "Enabled"],
].map(([fieldname, label]) => ({ fieldname, label, reqd: fieldname === "notes" ? 0 : 1 }));

function openToolEntry(sandbox) {
    const Entry = sandbox.frappe.ui.form.CNCToolPresetQuickEntryForm;
    const entry = new Entry("CNC Tool Preset", null, null, { doctype: "CNC Tool Preset" });
    entry.docfields = toolFields.map(df => Object.assign({}, df));
    entry.render_dialog();
    return entry;
}

const englishEntry = openToolEntry(english);
const englishForm = { fields_dict: {}, set_df_property(name, prop, value) { this.fields_dict[name].df[prop] = value; } };
toolFields.forEach(df => {
    englishForm.fields_dict[df.fieldname] = {
        df: Object.assign({}, df),
        labelText: df.label,
        set_label(text) { this.labelText = text; this.df.label = text; },
    };
});
english.AlmdinaCncLabels.applyToolFieldLabels(englishForm);
toolFields.forEach(df => {
    assert.strictEqual(englishEntry.fields_dict[df.fieldname].labelText, df.label);
    assert.strictEqual(
        englishEntry.fields_dict[df.fieldname].labelText,
        englishForm.fields_dict[df.fieldname].labelText
    );
});

const arabic = {
    window: {},
    document: { documentElement: { lang: "ar", getAttribute() { return "rtl"; } } },
    frappe: { boot: { lang: "ar" }, ui: { form: { QuickEntryForm } }, ready(fn) { fn(); } },
    __: message => ({
        "Tool Name": "اسم الريشة",
        "Tool Number": "رقم الريشة",
        "Tool Diameter (mm)": "قطر الريشة (مم)",
        "Spindle Speed (RPM)": "سرعة الدوران (دورة/دقيقة)",
        Stepdown: "عمق التمريرة",
        "Final Tool Offset": "الإزاحة النهائية للريشة",
        "Stepover Size": "مقدار التداخل",
        "Stepover Percent of D": "نسبة التداخل",
        "Feed Rate": "سرعة التغذية",
        "Plunge Rate": "سرعة الغطس",
        "Feed Rate (mm/sec)": "سرعة التغذية (مم/ث)",
        "Plunge Rate (mm/sec)": "سرعة الغطس (مم/ث)",
        "Positive whole number, for example 9. One board file uses one tool number.": "عدد صحيح موجب، مثلاً 9. ملف اللوح الواحد يستخدم رقم ريشة واحداً.",
        Notes: "الملاحظات",
        Enabled: "مفعّل",
        "Post Processor": "معالج المخرجات",
        "IMA-WH (*.nc)": "IMA-WH (*.nc)",
        "Left Stop (cm)": "المصادم الأيسر (سم)",
        "Right Stop (cm)": "المصادم الأيمن (سم)",
        "Bottom Stop (cm)": "المصادم السفلي (سم)",
        "Top Stop (cm)": "المصادم العلوي (سم)",
        "Work Zero Position": "نقطة صفر العمل",
    }[message] || message),
};
arabic.window = arabic;
load("public/js/almdina_locale.js", arabic);
load("public/js/cnc/cnc_field_labels.js", arabic);
assert.strictEqual(arabic.AlmdinaCncLabels.installQuickEntryForms(), true);
const arabicEntry = openToolEntry(arabic);
const arabicForm = { fields_dict: {} };
toolFields.forEach(df => {
    arabicForm.fields_dict[df.fieldname] = {
        df: Object.assign({}, df),
        labelText: df.label,
        set_label(text) { this.labelText = text; this.df.label = text; },
    };
});
arabicForm.set_df_property = function setDf(name, prop, value) {
    this.fields_dict[name].df[prop] = value;
};
arabic.AlmdinaCncLabels.applyToolFieldLabels(arabicForm);
assert.strictEqual(arabicEntry.fields_dict.tool_name.labelText, "اسم الريشة");
assert.strictEqual(arabicEntry.fields_dict.tool_number.labelText, "رقم الريشة");
assert.strictEqual(arabicEntry.fields_dict.tool_diameter_mm.labelText, "قطر الريشة (مم)");
assert.strictEqual(arabicEntry.fields_dict.spindle_speed_rpm.labelText, "سرعة الدوران (دورة/دقيقة)");
assert.strictEqual(arabicEntry.fields_dict.stepdown_mm.labelText, "عمق التمريرة (Stepdown)");
assert.strictEqual(arabicEntry.fields_dict.final_tool_offset_mm.labelText, "الإزاحة النهائية للريشة (Final Tool Offset)");
assert.strictEqual(arabicEntry.fields_dict.stepover_size_mm.labelText, "مقدار التداخل (Stepover - mm)");
assert.strictEqual(arabicEntry.fields_dict.stepover_percent.labelText, "نسبة التداخل (Stepover - %)");
assert.strictEqual(arabicEntry.fields_dict.feed_rate_mm_sec.labelText, "سرعة التغذية (Feed Rate)");
assert.strictEqual(arabicEntry.fields_dict.plunge_rate_mm_sec.labelText, "سرعة الغطس (Plunge Rate)");
assert.strictEqual(arabicEntry.fields_dict.notes.labelText, "الملاحظات (Notes)");
assert.strictEqual(
    arabicEntry.fields_dict.tool_number.helpText,
    "عدد صحيح موجب، مثلاً 9. ملف اللوح الواحد يستخدم رقم ريشة واحداً."
);
const stepdown = arabicEntry.fields_dict.stepdown_mm;
stepdown.df.label = "Stepdown";
stepdown.labelText = "عمق التمريرة";
stepdown.set_label();
assert.strictEqual(stepdown.labelText, "عمق التمريرة (Stepdown)");
assert.strictEqual(stepdown.df.label, "عمق التمريرة (Stepdown)");
toolFields.forEach(df => {
    assert.strictEqual(
        arabicEntry.fields_dict[df.fieldname].labelText,
        arabicForm.fields_dict[df.fieldname].labelText
    );
});

function visibleStops(entry) {
    return ["left_stop_cm", "right_stop_cm", "bottom_stop_cm", "top_stop_cm"].filter(name => {
        return Number(entry.fields_dict[name].df.hidden || 0) === 0;
    });
}

const machineFields = [
    "machine_name",
    "width_cm",
    "length_cm",
    "work_zero_position",
    "post_processor",
    "left_stop_cm",
    "right_stop_cm",
    "bottom_stop_cm",
    "top_stop_cm",
    "enabled",
].map(fieldname => ({ fieldname, label: fieldname, reqd: 1 }));

function openMachine(position) {
    const Entry = english.frappe.ui.form.CNCMachineQuickEntryForm;
    const entry = new Entry("CNC Machine", null, null, {
        doctype: "CNC Machine",
        work_zero_position: position,
        post_processor: "ima_wh_ncstudio",
        left_stop_cm: 0,
        right_stop_cm: 0,
        bottom_stop_cm: 0,
        top_stop_cm: 0,
    });
    entry.docfields = machineFields.map(df => Object.assign({}, df));
    entry.render_dialog();
    return entry;
}

const corners = {
    "Bottom Left": ["left_stop_cm", "bottom_stop_cm"],
    "Bottom Right": ["right_stop_cm", "bottom_stop_cm"],
    "Top Left": ["left_stop_cm", "top_stop_cm"],
    "Top Right": ["right_stop_cm", "top_stop_cm"],
};
Object.keys(corners).forEach(position => {
    const entry = openMachine(position);
    assert.deepStrictEqual(visibleStops(entry), []);
    ["left_stop_cm", "right_stop_cm", "bottom_stop_cm", "top_stop_cm"].forEach(name => {
        assert.strictEqual(Number(entry.fields_dict[name].df.reqd), 0);
        assert.strictEqual(Number(entry.fields_dict[name].df.hidden || 0), 1);
    });
    assert.strictEqual(entry.fields_dict.post_processor.option.textContent, "IMA-WH (*.nc)");
    assert.strictEqual(entry.fields_dict.post_processor._value, "ima_wh_ncstudio");
});

const switching = openMachine("Bottom Left");
["Bottom Right", "Top Left", "Top Right", "Bottom Left"].forEach(position => {
    switching.fields_dict.work_zero_position._value = position;
    switching.fields_dict.work_zero_position.df.change.call(switching.fields_dict.work_zero_position);
    assert.deepStrictEqual(visibleStops(switching), []);
    assert.strictEqual(switching.doc.work_zero_position, position);
});
const reopened = openMachine("Top Right");
reopened.fields_dict.right_stop_cm._value = 0;
reopened.fields_dict.top_stop_cm._value = 0;
assert.deepStrictEqual(visibleStops(reopened), []);
assert.strictEqual(reopened.fields_dict.right_stop_cm._value, 0);
const refreshed = openMachine("Bottom Left");
refreshed.fields_dict.right_stop_cm.df.hidden = 0;
refreshed.fields_dict.right_stop_cm.df.reqd = 1;
refreshed.fields_dict.top_stop_cm.df.hidden = 0;
refreshed.fields_dict.right_stop_cm.refresh();
refreshed.fields_dict.top_stop_cm.refresh();
assert.deepStrictEqual(visibleStops(refreshed), []);
assert.strictEqual(Number(refreshed.fields_dict.right_stop_cm.df.reqd), 0);
assert.strictEqual(Number(refreshed.fields_dict.top_stop_cm.df.reqd), 0);
const translatedZero = openMachine("Bottom Left");
translatedZero.doc.work_zero_position = "Top Right";
translatedZero.fields_dict.work_zero_position.get_value = () => "أعلى اليمين";
translatedZero.fields_dict.work_zero_position.df.change.call(translatedZero.fields_dict.work_zero_position);
assert.strictEqual(translatedZero.doc.work_zero_position, "Top Right");
assert.deepStrictEqual(visibleStops(translatedZero), []);
english.frappe.ui.form.make_quick_entry = function makeBaseQuickEntry(doctype) {
    const entry = new english.frappe.ui.form.QuickEntryForm(doctype, null, null, {
        doctype,
        work_zero_position: "Top Left",
        post_processor: "ima_wh_ncstudio",
    });
    entry.docfields = machineFields.map(df => Object.assign({}, df));
    english.frappe.quick_entry = entry;
    entry.render_dialog();
    return entry;
};
assert.strictEqual(english.AlmdinaCncLabels.installQuickEntryForms(), true);
const baseDialog = english.frappe.ui.form.make_quick_entry("CNC Machine");
assert.strictEqual(baseDialog.constructor, english.frappe.ui.form.QuickEntryForm);
assert.deepStrictEqual(visibleStops(baseDialog), []);
const css = fs.readFileSync(path.join(root, "public/css/door_cutting_order_operational_files.css"), "utf8");
const panelRule = css.slice(css.indexOf(".dco-tool-picker__panel {"), css.indexOf(".dco-tool-picker__change"));
assert.ok(panelRule.includes("position: static"));
assert.equal(panelRule.includes("position: absolute"), false);
const groupRule = css.slice(
    css.indexOf(".dco-operational-sheet .dco-sheet-group {"),
    css.indexOf(".dco-operational-sheet .dco-sheet-group__title")
);
assert.ok(groupRule.includes("box-shadow: none"));
assert.equal(groupRule.includes("overflow: hidden"), false);

const pickerDoc = element("document");
pickerDoc.ownerDocument = pickerDoc;
const emptyMarkup = english.AlmdinaCncToolPicker.markup({
    label: "Tool",
    emptyLabel: "Choose a tool",
    selected: "",
    tools: [{ value: "finish", label: "Ball Nose 5 mm" }],
    fields: [],
});
assert.ok(emptyMarkup.includes("Choose a tool"));
assert.ok(emptyMarkup.includes("data-tool-picker-settings hidden"));
const emptyHost = hostFor(emptyMarkup, pickerDoc);
english.AlmdinaCncToolPicker.bind(emptyHost);
assert.strictEqual(emptyHost.querySelector("[data-tool-picker-panel]").hidden, true);
emptyHost.dispatch("click", {
    target: emptyHost.querySelector(".dco-tool-picker__value"),
    preventDefault() {},
});
assert.strictEqual(emptyHost.querySelector("[data-tool-picker-panel]").hidden, false);
assert.ok(emptyHost.querySelector("[data-tool-picker-select]"));
assert.strictEqual(emptyHost.querySelector("[data-tool-picker-settings] input"), null);

const selectedMarkup = english.AlmdinaCncToolPicker.markup({
    label: "Tool",
    changeLabel: "Tool",
    emptyLabel: "Choose a tool",
    selected: "finish",
    selectedLabel: "Ball Nose 5 mm",
    tools: [
        { value: "finish", label: "Ball Nose 5 mm" },
        { value: "rough", label: "Flat 8 mm" },
    ],
    fields: [{ name: "stepdown_mm", label: "Stepdown", value: "3.5" }],
});
const selectedHost = hostFor(selectedMarkup, pickerDoc);
let changedTo = "";
const mounted = english.AlmdinaCncToolPicker.mount(selectedHost, {
    label: "Tool",
    changeLabel: "Tool",
    emptyLabel: "Choose a tool",
    selected: "finish",
    selectedLabel: "Ball Nose 5 mm",
    tools: [
        { value: "finish", label: "Ball Nose 5 mm" },
        { value: "rough", label: "Flat 8 mm" },
    ],
    fields: [{ name: "stepdown_mm", label: "Stepdown", value: "3.5" }],
    onToolChange(value) { changedTo = value; },
    onFieldInput() {},
});
assert.strictEqual(mounted.isOpen(), false);
assert.strictEqual(selectedHost.querySelector(".dco-tool-picker__value").textContent, "Ball Nose 5 mm");
const panel = selectedHost.querySelector("[data-tool-picker-panel]");
const select = selectedHost.querySelector("[data-tool-picker-select]");
const settings = selectedHost.querySelector("[data-tool-picker-settings]");
assert.ok(panel.children.indexOf(select.parent) < panel.children.indexOf(settings));
selectedHost.dispatch("click", {
    target: selectedHost.querySelector(".dco-tool-picker__value"),
    preventDefault() {},
});
assert.strictEqual(mounted.isOpen(), true);
const input = selectedHost.querySelector("[data-tool-picker-settings] input");
input.value = "4.25";
input.dispatch("input", { target: input });
selectedHost.dispatch("keydown", { key: "Escape", target: input });
assert.strictEqual(mounted.isOpen(), false);
assert.strictEqual(input.value, "4.25");
selectedHost.dispatch("click", {
    target: selectedHost.querySelector("[data-tool-picker-toggle]"),
    preventDefault() {},
});
assert.strictEqual(selectedHost.querySelector("[data-tool-picker-settings] input").value, "4.25");
input.dispatch("mousedown", { target: input });
assert.strictEqual(mounted.isOpen(), true);
pickerDoc.dispatch("mousedown", { target: pickerDoc });
assert.strictEqual(mounted.isOpen(), false);
assert.strictEqual(selectedHost.querySelector("[data-tool-picker-settings] input").value, "4.25");
select.value = "finish";
select.dispatch("change", { target: select });
assert.strictEqual(changedTo, "");
select.value = "rough";
select.dispatch("change", { target: select });
assert.strictEqual(changedTo, "rough");

console.log("cnc_quick_entry_tool_picker.test.js passed");
