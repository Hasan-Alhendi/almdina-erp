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
        style: {},
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
            if (name === "hidden") node.hidden = true;
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
    if (selector === "option") return node.tag === "option";
    if (selector.startsWith(".")) {
        return String(node.className || "").split(/\s+/).includes(selector.slice(1));
    }
    if (selector.startsWith("[") && selector.endsWith("]")) {
        const body = selector.slice(1, -1);
        if (body.includes("=")) {
            const [name, raw] = body.split("=");
            const expected = raw.replace(/^"|"$/g, "");
            return String(node.attrs[name] || "") === expected;
        }
        return Object.prototype.hasOwnProperty.call(node.attrs, body);
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

function jq(node) {
    const api = {
        0: node,
        length: node ? 1 : 0,
        get() { return node; },
        first() { return api; },
        text(value) {
            if (!node) return "";
            if (arguments.length) {
                node.textContent = String(value);
                return api;
            }
            return node.textContent || "";
        },
        find(selector) {
            if (!node) return jq(null);
            if (selector === ".control-input-wrapper, .control-input") return jq(null);
            if (selector === "label" || selector === ".control-label") return jq(null);
            // Support attribute selector with value used by collectOverrides.
            if (selector.includes("data-profile-tool=")) {
                const name = selector.match(/data-profile-tool="([^"]+)"/);
                const match = (node.querySelectorAll("[data-profile-tool]") || []).find(
                    input => input.getAttribute("data-profile-tool") === (name && name[1])
                );
                return jq(match || null);
            }
            const found = node.querySelectorAll ? node.querySelectorAll(selector) : [];
            return jq(found[0] || null);
        },
        children(selector) {
            if (!node) return Object.assign(jq(null), { length: 0 });
            const matchesFound = (node.children || []).filter(child => {
                if (selector === "[data-tool-picker-host]") {
                    return Object.prototype.hasOwnProperty.call(child.attrs || {}, "data-tool-picker-host");
                }
                return false;
            });
            if (!matchesFound.length) return Object.assign(jq(null), { length: 0 });
            return jq(matchesFound[0]);
        },
        append(child) {
            const el = child && child.get ? child.get(0) : child;
            if (node && el) node.appendChild(el);
            return api;
        },
        addClass() { return api; },
        empty() {
            if (node) node.children = [];
            return api;
        },
        data(key, value) {
            if (!node) return undefined;
            node.__data = node.__data || {};
            if (arguments.length === 1) return node.__data[key];
            node.__data[key] = value;
            return api;
        },
        removeData(key) {
            if (node && node.__data) delete node.__data[key];
            return api;
        },
        val(value) {
            if (!node) return "";
            if (arguments.length === 0) return node.value;
            node.value = String(value);
            return api;
        },
    };
    return api;
}

function createSandbox() {
    const doc = element("document");
    doc.ownerDocument = doc;
    doc.createElement = tag => {
        const node = element(tag);
        node.ownerDocument = doc;
        return node;
    };
    doc.addEventListener = element("document").addEventListener;
    const presets = {
        tool_a: {
            name: "tool_a",
            tool_name: "Ball Nose A",
            tool_type: "Ball Nose",
            tool_number: "9",
            tool_units: "mm",
            rate_units: "mm/sec",
            notes: "",
            tool_diameter_mm: 5,
            stepdown_mm: 1.5,
            final_tool_offset_mm: 0,
            stepover_size_mm: 1,
            stepover_percent: 20,
            spindle_speed_rpm: 12000,
            feed_rate_mm_sec: 40,
            plunge_rate_mm_sec: 20,
            enabled: 1,
        },
        tool_b: {
            name: "tool_b",
            tool_name: "Ball Nose B",
            tool_type: "Ball Nose",
            tool_number: "11",
            tool_units: "mm",
            rate_units: "mm/sec",
            notes: "",
            tool_diameter_mm: 8,
            stepdown_mm: 2,
            final_tool_offset_mm: 0,
            stepover_size_mm: 1.5,
            stepover_percent: 20,
            spindle_speed_rpm: 10000,
            feed_rate_mm_sec: 35,
            plunge_rate_mm_sec: 18,
            enabled: 1,
        },
    };
    const sandbox = {
        window: {},
        document: doc,
        jQuery: jq,
        $: jq,
        console,
        setTimeout: fn => fn(),
        Promise,
        frappe: {
            boot: { lang: "en" },
            ui: { form: {} },
            ready(fn) { fn(); },
            db: {
                get_list() {
                    return Promise.resolve(Object.values(presets).map(row => ({
                        name: row.name,
                        tool_name: row.tool_name,
                    })));
                },
                get_doc(_doctype, name) {
                    return Promise.resolve(Object.assign({}, presets[name]));
                },
            },
        },
        __: message => message,
    };
    sandbox.window = sandbox;
    sandbox.frappe.ui.form.QuickEntryForm = class QuickEntryForm {
        constructor(doctype, afterInsert, initCallback, doc) {
            this.doctype = doctype;
            this.doc = doc || { doctype, name: "new-profile-1" };
            this.docfields = [];
            this.fields_dict = {};
        }
        render_dialog() {
            this.fields_dict = {};
            this.docfields.forEach(df => {
                const wrapperNode = element("div");
                wrapperNode.ownerDocument = doc;
                const controlInput = element("div");
                controlInput.className = "control-input";
                controlInput.ownerDocument = doc;
                wrapperNode.appendChild(controlInput);
                const $wrapper = jq(wrapperNode);
                $wrapper.find = selector => {
                    if (selector === ".control-input-wrapper, .control-input") return jq(controlInput);
                    return jq(wrapperNode).children(selector);
                };
                $wrapper.children = selector => jq(wrapperNode).children(selector);
                $wrapper.append = child => {
                    const el = child && child.get ? child.get(0) : child;
                    if (el && !el.ownerDocument) el.ownerDocument = doc;
                    if (el && Object.prototype.hasOwnProperty.call(el.attrs || {}, "data-tool-picker-host") === false
                        && child && child.attrs) {
                        /* noop */
                    }
                    wrapperNode.appendChild(el);
                    return $wrapper;
                };
                this.fields_dict[df.fieldname] = {
                    df: Object.assign({}, df),
                    $wrapper,
                    $input: {
                        val(value) {
                            if (arguments.length) {
                                this._value = value;
                                return this;
                            }
                            return this._value;
                        },
                        _value: this.doc[df.fieldname] == null ? "" : this.doc[df.fieldname],
                    },
                    set_value(value) {
                        this.$input.val(value);
                        this._value = value;
                    },
                    set_label(text) {
                        this.df.label = text;
                        this.labelText = text;
                    },
                    refresh() {},
                };
            });
        }
        get_values() {
            return Object.assign({}, this.doc);
        }
        update_doc(data) {
            Object.assign(this.doc, data || {});
            return this.doc;
        }
        get_field(name) {
            return this.fields_dict[name];
        }
    };

    // Patch jQuery factory used by binding for creating hosts.
    sandbox.jQuery = function jQueryFactory(input) {
        if (typeof input === "string" && input.indexOf("data-tool-picker-host") !== -1) {
            const host = element("div");
            host.ownerDocument = doc;
            host.setAttribute("data-tool-picker-host", "");
            return jq(host);
        }
        return jq(input && input.tag ? input : null);
    };
    sandbox.$ = sandbox.jQuery;

    // InnerHTML support for picker mount hosts.
    const originalMountReady = () => {};
    void originalMountReady;

    load("public/js/almdina_locale.js", sandbox);
    load("public/js/cnc/cnc_field_labels.js", sandbox);
    load("public/js/cnc/cnc_tool_picker.js", sandbox);
    load("public/js/cnc/cnc_profile_tool_binding.js", sandbox);

    // Upgrade mount host nodes with innerHTML setter and honor selected options
    // the way a real DOM would after parsing markup.
    const NativeMount = sandbox.AlmdinaCncToolPicker.mount;
    sandbox.AlmdinaCncToolPicker = Object.assign({}, sandbox.AlmdinaCncToolPicker, {
        mount(container, spec) {
            if (container && !Object.getOwnPropertyDescriptor(container, "innerHTML")) {
                Object.defineProperty(container, "innerHTML", {
                    configurable: true,
                    set(html) {
                        container.children = [];
                        const parsed = parseHTML(html, doc);
                        parsed.children.forEach(child => container.appendChild(child));
                    },
                });
            }
            const controller = NativeMount(container, spec);
            const select = container.querySelector("[data-tool-picker-select]");
            if (select) {
                select.value = String((spec && spec.selected) || "");
                select.options.forEach(option => {
                    if (Object.prototype.hasOwnProperty.call(option.attrs, "selected")) {
                        select.value = option.value;
                    }
                });
            }
            return controller;
        },
        markup: sandbox.AlmdinaCncToolPicker.markup,
        bind: sandbox.AlmdinaCncToolPicker.bind,
    });
    Object.freeze(sandbox.AlmdinaCncToolPicker);

    return { sandbox, presets, doc };
}

function faceText(host) {
    const root = host.get(0);
    const face = root.querySelector(".dco-tool-picker__value");
    return face ? face.textContent : "";
}

function selectValue(host) {
    const root = host.get(0);
    const select = root.querySelector("[data-tool-picker-select]");
    return select ? select.value : "";
}

function settingsOpen(host) {
    const root = host.get(0);
    const settings = root.querySelector("[data-tool-picker-settings]");
    return Boolean(settings && !settings.hidden && settings.querySelector("input"));
}

function panelOpen(host) {
    const root = host.get(0);
    const panel = root.querySelector("[data-tool-picker-panel]");
    return Boolean(panel && !panel.hidden);
}

function stepdownValue(host) {
    const root = host.get(0);
    const input = root.querySelector('[data-profile-tool="stepdown_mm"]');
    return input ? input.value : "";
}

async function syncFormLike(sandbox, doc, docname, state, host, force) {
    const binding = sandbox.AlmdinaCncProfileToolBinding;
    return binding.sync(host, state, doc, {
        docname,
        force: Boolean(force),
        loadTools: () => sandbox.frappe.db.get_list(),
        handlers: {
            onToolChange(value) {
                doc.tool_preset = value || null;
            },
        },
    });
}

async function selectTool(sandbox, doc, state, host, toolName) {
    const binding = sandbox.AlmdinaCncProfileToolBinding;
    doc.tool_preset = toolName;
    const generation = binding.beginToolLoad(state);
    const preset = await sandbox.frappe.db.get_doc("CNC Tool Preset", toolName);
    assert.ok(binding.isCurrentToolLoad(state, generation, doc, toolName));
    state.tool = binding.toolPayloadFromPreset(preset);
    state.toolName = toolName;
    await syncFormLike(sandbox, doc, doc.name, state, host, true);
}

(async function main() {
    const { sandbox, presets } = createSandbox();
    const binding = sandbox.AlmdinaCncProfileToolBinding;
    assert.ok(binding);
    assert.strictEqual(sandbox.AlmdinaCncLabels.installQuickEntryForms(), true);
    assert.ok(sandbox.frappe.ui.form.CNCToolPresetQuickEntryForm);
    assert.ok(sandbox.frappe.ui.form.CNCMachineQuickEntryForm);
    assert.ok(sandbox.frappe.ui.form.CNCMachiningProfileQuickEntryForm);

    // 1) Profile A with tool A, then profile B with same tool A without page reload.
    const hostNode = element("div");
    hostNode.ownerDocument = sandbox.document;
    const host = jq(hostNode);
    const state = binding.createRuntimeState();
    const docA = { name: "new-profile-1", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, docA, docA.name, state, host);
    assert.strictEqual(faceText(host), "Choose a tool");
    assert.strictEqual(selectValue(host), "");
    await selectTool(sandbox, docA, state, host, "tool_a");
    assert.strictEqual(selectValue(host), "tool_a");
    assert.strictEqual(faceText(host), "Ball Nose A");
    assert.ok(settingsOpen(host));
    assert.strictEqual(panelOpen(host), false);
    state.tool.stepdown_mm = 9.9;
    await syncFormLike(sandbox, docA, docA.name, state, host, true);
    const inputA = host.get(0).querySelector('[data-profile-tool="stepdown_mm"]');
    inputA.value = "9.9";
    inputA.dispatch("input", { target: inputA });
    assert.strictEqual(stepdownValue(host), "9.9");
    const overridesA = binding.collectOverrides(host);
    assert.strictEqual(overridesA.stepdown_mm, 9.9);

    const docB = { name: "new-profile-2", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, docB, docB.name, state, host);
    assert.strictEqual(faceText(host), "Choose a tool");
    assert.strictEqual(selectValue(host), "");
    assert.strictEqual(settingsOpen(host), false);
    assert.notStrictEqual(state.tool && state.tool.stepdown_mm, 9.9);
    await selectTool(sandbox, docB, state, host, "tool_a");
    assert.strictEqual(selectValue(host), "tool_a");
    assert.strictEqual(stepdownValue(host), "1.5");

    // 2) Profile with tool A then another with tool B.
    const docC = { name: "new-profile-3", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, docC, docC.name, state, host);
    await selectTool(sandbox, docC, state, host, "tool_a");
    const docD = { name: "new-profile-4", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, docD, docD.name, state, host);
    await selectTool(sandbox, docD, state, host, "tool_b");
    assert.strictEqual(selectValue(host), "tool_b");
    assert.strictEqual(faceText(host), "Ball Nose B");
    assert.strictEqual(stepdownValue(host), "2");

    // 3) After save-equivalent switch to a blank new doc, previous tool must not linger.
    const blank = { name: "new-profile-5", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, blank, blank.name, state, host);
    assert.strictEqual(selectValue(host), "");
    assert.strictEqual(faceText(host), "Choose a tool");
    assert.strictEqual(host.get(0).querySelector("[data-tool-picker-settings] input"), null);

    // 5) Saved profile -> new profile isolation.
    const saved = {
        name: "PROFILE-SAVED",
        tool_preset: "tool_a",
        tool_values_json: {
            tool_name: "Ball Nose A",
            stepdown_mm: 3.3,
            tool_number: "9",
        },
    };
    await syncFormLike(sandbox, saved, saved.name, state, host);
    assert.strictEqual(selectValue(host), "tool_a");
    assert.strictEqual(stepdownValue(host), "3.3");
    const fresh = { name: "new-profile-6", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, fresh, fresh.name, state, host);
    assert.strictEqual(selectValue(host), "");
    assert.strictEqual(faceText(host), "Choose a tool");

    // 6) Edits on one profile do not transfer.
    const editOne = { name: "edit-1", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, editOne, editOne.name, state, host);
    await selectTool(sandbox, editOne, state, host, "tool_a");
    const editInput = host.get(0).querySelector('[data-profile-tool="feed_rate_mm_sec"]');
    editInput.value = "77";
    editInput.dispatch("input", { target: editInput });
    assert.strictEqual(state.tool.feed_rate_mm_sec, 77);
    const editTwo = { name: "edit-2", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, editTwo, editTwo.name, state, host);
    await selectTool(sandbox, editTwo, state, host, "tool_a");
    assert.strictEqual(stepdownValue(host), String(presets.tool_a.stepdown_mm));
    assert.strictEqual(
        host.get(0).querySelector('[data-profile-tool="feed_rate_mm_sec"]').value,
        String(presets.tool_a.feed_rate_mm_sec)
    );

    // 7) Stale tool-load response must not mutate the current document.
    const staleDoc = { name: "stale-1", tool_preset: "tool_a", tool_values_json: {} };
    await syncFormLike(sandbox, staleDoc, staleDoc.name, state, host);
    const genA = binding.beginToolLoad(state);
    staleDoc.tool_preset = "tool_b";
    state.toolName = "tool_b";
    const genB = binding.beginToolLoad(state);
    assert.strictEqual(binding.isCurrentToolLoad(state, genA, staleDoc, "tool_a"), false);
    assert.strictEqual(binding.isCurrentToolLoad(state, genB, staleDoc, "tool_b"), true);
    const late = await sandbox.frappe.db.get_doc("CNC Tool Preset", "tool_a");
    if (binding.isCurrentToolLoad(state, genA, staleDoc, "tool_a")) {
        state.tool = binding.toolPayloadFromPreset(late);
    }
    assert.notStrictEqual(state.tool && state.tool.tool_preset, "tool_a");

    // 9) Clear selection syncs UI and document truth.
    const clearDoc = { name: "clear-1", tool_preset: "", tool_values_json: {} };
    await syncFormLike(sandbox, clearDoc, clearDoc.name, state, host);
    await selectTool(sandbox, clearDoc, state, host, "tool_a");
    clearDoc.tool_preset = "";
    state.tool = null;
    state.toolName = "";
    await syncFormLike(sandbox, clearDoc, clearDoc.name, state, host, true);
    assert.strictEqual(selectValue(host), "");
    assert.strictEqual(faceText(host), "Choose a tool");

    // 4 + 8) Quick Entry modal isolation and full/quick controllers.
    const profileFields = [
        "profile_name",
        "tool_preset",
        "final_depth_mm",
        "safe_z_mm",
        "home_x_mm",
        "home_y_mm",
        "home_z_mm",
        "enabled",
    ].map(fieldname => ({ fieldname, label: fieldname, reqd: 1 }));

    async function openProfileModal(name) {
        const Entry = sandbox.frappe.ui.form.CNCMachiningProfileQuickEntryForm;
        const entry = new Entry("CNC Machining Profile", null, null, {
            doctype: "CNC Machining Profile",
            name,
            tool_preset: "",
            enabled: 1,
        });
        entry.docfields = profileFields.map(df => Object.assign({}, df));
        entry.render_dialog();
        sandbox.AlmdinaCncLabels.applyProfileFieldLabels(entry);
        await sandbox.AlmdinaCncLabels.bindProfileToolPicker(entry);
        return entry;
    }

    const modalOne = await openProfileModal("qe-1");
    assert.strictEqual(modalOne.fields_dict.profile_name.labelText, "Profile Name");
    const modalHost = binding.toolHost(modalOne.fields_dict.tool_preset);
    assert.ok(modalHost && modalHost.data("picker"));
    assert.strictEqual(faceText(modalHost), "Choose a tool");
    modalOne.doc.tool_preset = "tool_a";
    const modalState = modalOne._profile_tool_runtime;
    await selectTool(sandbox, modalOne.doc, modalState, modalHost, "tool_a");
    assert.strictEqual(selectValue(modalHost), "tool_a");

    // Cancel/close semantics: open a brand new modal with a fresh runtime.
    const modalTwo = await openProfileModal("qe-2");
    assert.notStrictEqual(modalTwo._profile_tool_runtime, modalOne._profile_tool_runtime);
    const modalHostTwo = binding.toolHost(modalTwo.fields_dict.tool_preset);
    assert.strictEqual(faceText(modalHostTwo), "Choose a tool");
    assert.strictEqual(selectValue(modalHostTwo), "");
    modalTwo.doc.tool_preset = "tool_a";
    await selectTool(sandbox, modalTwo.doc, modalTwo._profile_tool_runtime, modalHostTwo, "tool_a");
    modalTwo.update_doc(modalTwo.get_values());
    assert.ok(modalTwo.doc.tool_values_json);
    assert.strictEqual(modalTwo.doc.tool_preset, "tool_a");

    // Same-document refresh must not wipe in-progress edits.
    const stable = { name: "stable-1", tool_preset: "tool_a", tool_values_json: { stepdown_mm: 1.5 } };
    const stableHostNode = element("div");
    stableHostNode.ownerDocument = sandbox.document;
    const stableHost = jq(stableHostNode);
    const stableState = binding.createRuntimeState();
    await syncFormLike(sandbox, stable, stable.name, stableState, stableHost);
    const stableInput = stableHost.get(0).querySelector('[data-profile-tool="stepdown_mm"]');
    stableInput.value = "4.4";
    stableInput.dispatch("input", { target: stableInput });
    await syncFormLike(sandbox, stable, stable.name, stableState, stableHost, false);
    assert.strictEqual(
        stableHost.get(0).querySelector('[data-profile-tool="stepdown_mm"]').value,
        "4.4"
    );

    // setTools must honor explicit empty selection (previous bug).
    const sticky = sandbox.AlmdinaCncToolPicker.mount(stableHost.get(0), {
        selected: "tool_a",
        selectedLabel: "Ball Nose A",
        emptyLabel: "Choose a tool",
        tools: [{ value: "tool_a", label: "Ball Nose A" }],
        fields: [],
        onToolChange() {},
    });
    sticky.setTools([{ value: "tool_a", label: "Ball Nose A" }], "");
    assert.strictEqual(stableHost.get(0).querySelector("[data-tool-picker-select]").value, "");
    assert.strictEqual(stableHost.get(0).querySelector(".dco-tool-picker__value").textContent, "Choose a tool");

    console.log("cnc_machining_profile_tool_state.test.js passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
