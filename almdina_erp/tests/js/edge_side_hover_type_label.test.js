"use strict";

/**
 * Proves selected-side hover survives the real render order:
 * AlmdinaEdgeProfileControls sets the type-name title, then
 * compact_measurements decorateControls used to overwrite it with the
 * direction label ("Left long edge" → "قشاط الطول الأيسر").
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const scripts = [
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_compact_measurements_ux.js",
].map((relative) => path.join(root, relative));

function classSet(node) {
    return new Set(String(node.className || "").split(/\s+/).filter(Boolean));
}

function matches(node, selector) {
    let raw = String(selector || "").trim();
    if (!raw || !node || node.nodeType !== 1) return false;
    if (raw.includes(",")) return raw.split(",").some((part) => matches(node, part.trim()));
    const attribute = raw.match(/\[([^\]=]+)(?:=['"]([^'"]*)['"])?\]/);
    if (attribute) {
        const actual = node.getAttribute(attribute[1]);
        if (attribute[2] === undefined) {
            if (actual === null) return false;
        } else if (actual !== attribute[2]) {
            return false;
        }
        raw = raw.replace(attribute[0], "").trim();
        if (!raw) return true;
    }
    const [tag, ...classNames] = raw.split(".");
    if (tag && node.tagName !== tag.toUpperCase()) return false;
    const owned = classSet(node);
    return classNames.every((name) => owned.has(name));
}

function descendants(node) {
    const found = [];
    for (const child of node.children || []) {
        found.push(child, ...descendants(child));
    }
    return found;
}

function createNode(tagName = "div") {
    const attrs = Object.create(null);
    const node = {
        nodeType: 1,
        tagName: String(tagName).toUpperCase(),
        className: "",
        textContent: "",
        title: "",
        children: [],
        dataset: {},
        parentNode: null,
        style: {},
        classList: {
            add(...names) {
                const owned = classSet(node);
                names.forEach((name) => owned.add(name));
                node.className = [...owned].join(" ");
            },
            remove(...names) {
                const owned = classSet(node);
                names.forEach((name) => owned.delete(name));
                node.className = [...owned].join(" ");
            },
            toggle(name, force) {
                const owned = classSet(node);
                const should = force === undefined ? !owned.has(name) : Boolean(force);
                if (should) owned.add(name);
                else owned.delete(name);
                node.className = [...owned].join(" ");
            },
            contains(name) {
                return classSet(node).has(name);
            },
        },
        getAttribute(name) {
            if (name === "class") return node.className;
            if (name === "title") return node.title;
            if (name.startsWith("data-")) {
                const key = name
                    .slice(5)
                    .replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
                return Object.prototype.hasOwnProperty.call(node.dataset, key)
                    ? node.dataset[key]
                    : null;
            }
            return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
        },
        setAttribute(name, value) {
            if (name === "class") {
                node.className = String(value);
                return;
            }
            if (name === "title") {
                node.title = String(value);
                return;
            }
            if (name.startsWith("data-")) {
                const key = name
                    .slice(5)
                    .replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
                node.dataset[key] = String(value);
                return;
            }
            attrs[name] = String(value);
        },
        appendChild(child) {
            child.parentNode = node;
            node.children.push(child);
            return child;
        },
        replaceChildren(...kids) {
            node.children.forEach((child) => {
                child.parentNode = null;
            });
            node.children = [];
            kids.forEach((child) => node.appendChild(child));
        },
        querySelector(selector) {
            return node.querySelectorAll(selector)[0] || null;
        },
        querySelectorAll(selector) {
            const raw = String(selector || "").trim();
            if (!raw) return [];
            if (raw.includes(",")) {
                const seen = new Set();
                const found = [];
                raw.split(",").forEach((part) => {
                    node.querySelectorAll(part.trim()).forEach((match) => {
                        if (seen.has(match)) return;
                        seen.add(match);
                        found.push(match);
                    });
                });
                return found;
            }
            if (raw.startsWith(":scope")) {
                const rest = raw.replace(/^:scope\s*>\s*/, "").trim();
                if (raw.includes(">")) {
                    return (node.children || []).filter((child) => matches(child, rest));
                }
                return [node, ...descendants(node)].filter((child) =>
                    matches(child, rest || raw)
                );
            }
            if (/\s+/.test(raw) || raw.includes(">")) {
                const parts = raw.split(/\s*>\s*|\s+/).filter(Boolean);
                let current = [node];
                parts.forEach((part) => {
                    const next = [];
                    current.forEach((item) => {
                        descendants(item).forEach((child) => {
                            if (matches(child, part)) next.push(child);
                        });
                    });
                    current = next;
                });
                return current;
            }
            return descendants(node).filter((child) => matches(child, selector));
        },
        closest(selector) {
            let current = node;
            while (current) {
                if (matches(current, selector)) return current;
                current = current.parentNode;
            }
            return null;
        },
        addEventListener() {},
        removeEventListener() {},
        contains(other) {
            return other === node || descendants(node).includes(other);
        },
        focus() {},
        dispatchEvent() {
            return true;
        },
    };
    return node;
}

class MutationObserver {
    observe() {}
    disconnect() {}
}

const document = {
    styles: new Map(),
    body: createNode("body"),
    documentElement: createNode("html"),
    getElementById(id) {
        return this.styles.get(id) || null;
    },
    createElement(tag) {
        return createNode(tag);
    },
    head: {
        appendChild(element) {
            if (element && element.id) document.styles.set(element.id, element);
            return element;
        },
    },
    addEventListener() {},
};

function __(message, replacements) {
    let text = String(message == null ? "" : message);
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.split(`{${index}}`).join(String(value));
        });
    }
    return text;
}

const registeredFeatures = Object.create(null);
const window = {
    AlmdinaMultiEdgeBanding: null,
    AlmdinaEdgeProfileControls: null,
    AlmdinaMeasurementLifecycle: {
        registerFeature(name, feature) {
            registeredFeatures[name] = feature;
        },
        schedule(_frm, _name, work) {
            work();
        },
    },
    MutationObserver,
    addEventListener() {},
    removeEventListener() {},
};
const frappe = {
    utils: { escape_html: (value) => String(value ?? "") },
    ui: { form: { on() {} } },
    show_alert() {},
};

const sandboxGlobals = {
    window,
    document,
    frappe,
    __,
    Promise,
    Map,
    Set,
    String,
    Number,
    Boolean,
    Object,
    Array,
    Math,
    console,
    MutationObserver,
    setTimeout(callback) {
        callback();
        return 1;
    },
    clearTimeout() {},
    requestAnimationFrame(callback) {
        callback();
        return 1;
    },
};

scripts.forEach((filePath) => {
    vm.runInNewContext(fs.readFileSync(filePath, "utf8"), sandboxGlobals);
});

const defaultType = "قشاط 2سم عادي";
const customType = "قشاط 4سم لميع";
const row = {
    name: "piece-1",
    edge_width_top: 1,
    edge_width_bottom: 0,
    edge_long_right: 1,
    edge_long_left: 0,
    edge_width_top_type_override: "",
    edge_width_bottom_type_override: "",
    edge_long_right_type_override: customType,
    edge_long_left_type_override: "",
};

const wrapper = createNode("div");
wrapper.className = "dco-fast-entry";
const help = createNode("div");
help.className = "dco-fast-help";
wrapper.appendChild(help);
const toolbar = createNode("div");
toolbar.className = "dco-fast-entry-toolbar";
wrapper.appendChild(toolbar);
const table = createNode("table");
table.className = "dco-fast-table";
const tbody = createNode("tbody");
const tr = createNode("tr");
tr.dataset.rowName = "piece-1";
tr.setAttribute("data-row-name", "piece-1");
const td = createNode("td");
td.className = "dco-col-edges";
const buttons = createNode("div");
buttons.className = "dco-edge-buttons";

function makeToggle(field, checked) {
    const toggle = createNode("button");
    toggle.className = checked ? "dco-check-toggle is-checked" : "dco-check-toggle";
    toggle.dataset.checkField = field;
    toggle.setAttribute("data-check-field", field);
    const mark = createNode("span");
    mark.className = "dco-check-mark";
    toggle.appendChild(mark);
    return toggle;
}

const top = makeToggle("edge_width_top", true);
const bottom = makeToggle("edge_width_bottom", false);
const right = makeToggle("edge_long_right", true);
const left = makeToggle("edge_long_left", false);
[top, bottom, right, left].forEach((toggle) => buttons.appendChild(toggle));
td.appendChild(buttons);
tr.appendChild(td);
tbody.appendChild(tr);
table.appendChild(tbody);
wrapper.appendChild(table);
document.body.appendChild(wrapper);

const frm = {
    doc: {
        default_edge_type: defaultType,
        pieces: [row],
        docstatus: 0,
    },
    fields_dict: {
        pieces_fast_entry: {
            $wrapper: {
                get() {
                    return wrapper;
                },
            },
        },
    },
    _dco_side_edge_profiles: new Map([
        [
            defaultType,
            {
                name: defaultType,
                label: defaultType,
                thickness_mm: 2,
                rate_usd_per_meter: 0.5,
            },
        ],
        [
            customType,
            {
                name: customType,
                label: customType,
                thickness_mm: 4,
                rate_usd_per_meter: 2,
            },
        ],
    ]),
    _dco_side_edge_profiles_loaded: true,
};

window.AlmdinaEdgeProfileControls.apply(frm);
assert.equal(top.title, defaultType);
assert.equal(right.title, customType);

// Real competing owner: compact measurements used to overwrite selected titles.
assert.equal(typeof registeredFeatures["compact-measurements"], "function");
registeredFeatures["compact-measurements"](frm);

assert.equal(
    top.title,
    defaultType,
    "compact must not overwrite selected default-side title with direction"
);
assert.equal(
    right.title,
    customType,
    "compact must not overwrite selected custom-side title with direction"
);
assert.equal(bottom.title, "Bottom width edge", "unselected side keeps compact direction title");
assert.equal(left.title, "Left long edge", "unselected side keeps compact direction title");
assert.equal(top.getAttribute("aria-label"), "Top width edge");
assert.equal(right.getAttribute("aria-label"), "Right long edge");
assert.doesNotMatch(String(top.title), /Top width|long edge|Click to toggle/i);
assert.doesNotMatch(String(right.title), /Right long|Click to toggle/i);

frm.doc.default_edge_type = "قشاط 2سم ذهبي";
frm._dco_side_edge_profiles.set("قشاط 2سم ذهبي", {
    name: "قشاط 2سم ذهبي",
    label: "قشاط 2سم ذهبي",
    thickness_mm: 2,
    rate_usd_per_meter: 1.25,
});
row.edge_long_right_type_override = "قشاط 2سم عادي يدوي";
frm._dco_side_edge_profiles.set("قشاط 2سم عادي يدوي", {
    name: "قشاط 2سم عادي يدوي",
    label: "قشاط 2سم عادي يدوي",
    thickness_mm: 2,
    rate_usd_per_meter: 1,
});
window.AlmdinaEdgeProfileControls.apply(frm);
registeredFeatures["compact-measurements"](frm);
assert.equal(top.title, "قشاط 2سم ذهبي");
assert.equal(right.title, "قشاط 2سم عادي يدوي");
assert.equal(bottom.title, "Bottom width edge");

console.log("edge_side_hover_type_label.test.js: ok");
