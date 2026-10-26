"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const files = [
    "public/js/door_cutting_order/order_entry/door_cutting_order_order_tab_layout_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_cutting_machine_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_piece_mirroring_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_whatsapp_delivery_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_toolbar_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_color_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_double_click_guard.js",
];

for (const relative of files) {
    const source = fs.readFileSync(path.join(root, relative), "utf8");
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*__\(/m, relative);
    assert.doesNotMatch(source, /direction:\s*rtl/, relative);
    assert.doesNotMatch(source, /isArabic|labelAr|labelEn/, relative);
}

const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
for (const row of [
    "Order details,بيانات الطلب",
    "Edit order,تعديل",
    "{0} pieces,{0} قطعة",
    "Send measurements via WhatsApp,إرسال القياسات عبر واتساب",
    "Edge color: {0},لون القشاط: {0}",
]) {
    assert.ok(catalog.includes(row), row);
}
assert.ok(catalog.includes("Panel Saw,منشار ألواح"));
assert.ok(catalog.startsWith("Almdina ERP,") || catalog.includes("\nEdit,إعداد\n"));
assert.match(catalog, /^Edit,إعداد$/m);

function element(tag) {
    const children = [];
    const attributes = {};
    const classes = new Set();
    const node = {
        tagName: String(tag || "div").toUpperCase(),
        nodeType: 1,
        children,
        parentElement: null,
        style: {},
        hidden: false,
        classList: {
            add(...names) { names.filter(Boolean).forEach(name => classes.add(name)); },
            remove(...names) { names.forEach(name => classes.delete(name)); },
            contains(name) { return classes.has(name); },
            toggle(name, force) {
                const next = force === undefined ? !classes.has(name) : Boolean(force);
                if (next) classes.add(name);
                else classes.delete(name);
            },
        },
        appendChild(child) {
            if (child.parentElement) child.remove();
            child.parentElement = node;
            children.push(child);
            return child;
        },
        insertBefore(child, reference) {
            if (child.parentElement) child.remove();
            child.parentElement = node;
            const index = children.indexOf(reference);
            if (index < 0) children.push(child);
            else children.splice(index, 0, child);
            return child;
        },
        remove() {
            if (!node.parentElement) return;
            const list = node.parentElement.children;
            const index = list.indexOf(node);
            if (index >= 0) list.splice(index, 1);
            node.parentElement = null;
        },
        setAttribute(name, value) { attributes[name] = String(value); },
        getAttribute(name) { return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null; },
        removeAttribute(name) { delete attributes[name]; },
        closest(selector) {
            let current = node;
            while (current) {
                if (matches(current, selector)) return current;
                current = current.parentElement;
            }
            return null;
        },
        querySelector(selector) {
            let rest = String(selector || "").trim();
            if (rest.startsWith(":scope")) rest = rest.replace(/^:scope\s*>?\s*/, "");
            if (!rest) return node;
            if (rest.includes(" ")) {
                let current = node;
                for (const part of rest.split(/\s+/)) {
                    current = current.querySelector(part);
                    if (!current) return null;
                }
                return current;
            }
            const found = walk(node, rest);
            if (found.length) return rest.includes(":last-child") ? found[found.length - 1] : found[0];
            const classMatch = rest.match(/^\.([A-Za-z0-9_-]+)$/);
            if (classMatch && String(node._html || "").includes(classMatch[1])) {
                const host = element("div");
                host.className = classMatch[1];
                node.appendChild(host);
                return host;
            }
            return null;
        },
        querySelectorAll(selector) { return walk(node, selector); },
        _listeners: {},
        addEventListener(type, fn) {
            node._listeners[type] = node._listeners[type] || [];
            node._listeners[type].push(fn);
        },
        click() {
            const event = { target: node, preventDefault() {}, stopPropagation() {} };
            let current = node;
            while (current) {
                (current._listeners.click || []).forEach(fn => fn(event));
                current = current.parentElement;
            }
        },
        getBoundingClientRect() { return { top: 0, left: 0, right: 40, bottom: 20, width: 40, height: 20 }; },
        focus() {},
        contains(child) {
            let current = child;
            while (current) {
                if (current === node) return true;
                current = current.parentElement;
            }
            return false;
        },
        dataset: {},
    };
    Object.defineProperty(node, "parentNode", {
        get() { return node.parentElement; },
    });
    Object.defineProperty(node, "isConnected", {
        get() { return Boolean(node.parentElement); },
    });
    Object.defineProperty(node, "className", {
        get() { return [...classes].join(" "); },
        set(value) {
            classes.clear();
            String(value || "").split(/\s+/).filter(Boolean).forEach(name => classes.add(name));
        },
    });
    Object.defineProperty(node, "id", {
        get() { return node.getAttribute("id"); },
        set(value) { node.setAttribute("id", value); },
    });
    Object.defineProperty(node, "innerHTML", {
        get() { return node._html || ""; },
        set(value) {
            node._html = String(value);
            children.length = 0;
            parseHTML(node._html, node);
        },
    });
    Object.defineProperty(node, "textContent", {
        get() { return node._text == null ? node._html || "" : node._text; },
        set(value) { node._text = String(value); node._html = ""; },
    });
    Object.defineProperty(node, "value", {
        get() { return node._value == null ? "" : node._value; },
        set(value) { node._value = String(value); },
    });
    return node;
}

function parseHTML(html, parent) {
    const pattern = /<([a-zA-Z0-9]+)([^>]*)>([\s\S]*?)<\/\1>/g;
    let match;
    while ((match = pattern.exec(html))) {
        const child = element(match[1]);
        const classMatch = match[2].match(/class="([^"]*)"/);
        if (classMatch) child.className = classMatch[1];
        if (match[3].includes("<")) parseHTML(match[3], child);
        else if (match[3]) child.textContent = match[3];
        parent.appendChild(child);
    }
}

function matches(node, selector) {
    if (selector.startsWith("#")) return node.getAttribute("id") === selector.slice(1);
    const classMatch = selector.match(/\.([A-Za-z0-9_-]+)/);
    if (classMatch) return node.classList.contains(classMatch[1]);
    const tag = selector.match(/^([a-zA-Z0-9]+)/);
    if (tag) return node.tagName === tag[1].toUpperCase();
    return false;
}

function walk(node, selector) {
    const found = [];
    for (const child of node.children || []) {
        if (matches(child, selector)) found.push(child);
        found.push(...walk(child, selector));
    }
    return found;
}

function documentStub() {
    const body = element("body");
    const head = element("head");
    const documentElement = element("html");
    documentElement.setAttribute("dir", "rtl");
    documentElement.appendChild(head);
    documentElement.appendChild(body);
    const document = {
        body,
        head,
        documentElement,
        createElement: element,
        createComment() { return element("comment"); },
        getElementById(id) {
            const found = walk(body, `#${id}`);
            return found[0] || null;
        },
        addEventListener() {},
    };
    return document;
}

const french = {
    "Order details": "Détails de la commande",
    "Customer and basic order information.": "Informations client.",
    "{0} pieces": "{0} pièces",
    "Panel Saw": "Scie à panneaux",
    "Cutting machine type": "Type de machine",
    "Select the cutting machine type": "Choisissez la machine",
    "Send the measurements file to the customer?": "Envoyer le fichier ?",
    "Send measurements via WhatsApp": "Envoyer les mesures",
    "Send measurement changes via WhatsApp": "Envoyer les modifications",
    "Send the measurement changes to the customer?": "Envoyer les modifications ?",
    "The measurements table was sent to the customer via WhatsApp.": "Mesures envoyées",
    "WhatsApp": "WhatsApp",
    "Door entry table": "Table de saisie",
    "Door measurement entry table": "Saisie des mesures",
    "{0} · {1}": "{0} · {1}",
    "Draft": "Brouillon",
    "No customer": "Sans client",
    "Edge type: {0}": "Type de chant : {0}",
    "Edge color: {0}": "Couleur de chant : {0}",
    "Not specified": "Non précisé",
    "Print measurements": "Imprimer",
    "Open the entry table in a separate window": "Ouvrir dans une fenêtre",
    "All changes are saved": "Tout est enregistré",
    "Length": "Longueur",
    "Right length side": "Chant long droit",
    "{0} — {1} — {2} — {3}": "{0} — {1} — {2} — {3}",
    "Unavailable profile": "Profil indisponible",
    "Default": "Défaut",
    "Order edge color": "Couleur de commande",
};

let armed = false;
const calls = [];
let direction = "ltr";

function translate(message, replacements) {
    if (!armed) throw new Error(`translation during load: ${message}`);
    calls.push(String(message));
    let text = Object.prototype.hasOwnProperty.call(french, message) ? french[message] : `FR:${message}`;
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.split(`{${index}}`).join(String(value));
        });
    }
    return text;
}

function load(relative) {
    const document = documentStub();
    const window = {
        document,
        addEventListener() {},
        requestAnimationFrame(callback) { callback(); return 0; },
        setTimeout(callback) { callback(); return 0; },
        clearTimeout() {},
        innerWidth: 1024,
        innerHeight: 768,
        MutationObserver: class { observe() {} disconnect() {} },
        AlmdinaLocale: {
            translate,
            direction() { return direction; },
            isRTL() { return direction === "rtl"; },
        },
        AlmdinaUi: {
            button(options) {
                return `<button type="button" class="${options.className || ""}" aria-label="${options.attrs && options.attrs["aria-label"] || ""}"></button>`;
            },
        },
    };
    const handlers = [];
    const frappe = {
        ui: { form: { on(doctype, events) { handlers.push({ doctype, events }); } } },
        utils: { escape_html(value) { return String(value ?? ""); } },
        msgprint(payload) { window.messages.push(payload); },
        show_alert(payload) { window.alerts.push(payload); },
        confirm(message, yes) { window.confirms.push(message); if (yes) yes(); },
        throw(message) { throw new Error(message); },
    };
    window.messages = [];
    window.alerts = [];
    window.confirms = [];
    const context = vm.createContext({
        window,
        document,
        frappe,
        __: translate,
        $: () => ({ append() {} }),
        Object,
        Boolean,
        String,
        Number,
        Array,
        Map,
        Promise,
        Math,
        Date,
        Set,
        console,
        MutationObserver: window.MutationObserver,
        CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
        Event: class { constructor(type) { this.type = type; } },
        AlmdinaLocale: window.AlmdinaLocale,
        setTimeout(callback) { callback(); return 0; },
        clearTimeout() {},
        requestAnimationFrame(callback) { callback(); return 0; },
    });
    vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    return { window, document, frappe, handlers };
}

armed = false;
const loaded = files.map(load);
armed = true;
assert.equal(calls.length, 0);

const layout = loaded[0].window.AlmdinaOrderTabLayoutUX;
const section = element("section");
section.className = "form-section";
const body = element("div");
body.className = "section-body";
section.appendChild(body);
const field = element("div");
body.appendChild(field);
const wrapper = element("div");
wrapper.appendChild(section);
layout.apply({
    wrapper,
    doctype: "Door Cutting Order",
    doc: { pieces: [{ qty: 2 }, { qty: 1 }], edge_color: "", default_edge_type: "" },
    fields_dict: { pieces_section: { wrapper: field } },
});
const heading = body.querySelector(".dco-order-section-heading");
assert.match(heading.innerHTML, /3 pièces/);
assert.equal(direction, "ltr");

const machine = loaded[1].window.AlmdinaOrderCuttingMachineUX;
const machineField = element("div");
const machineForm = element("div");
machineForm.appendChild(machineField);
machine.apply({
    wrapper: machineForm,
    doc: { order_cutting_machine: "مشرحة" },
    fields_dict: { order_cutting_machine: { wrapper: machineField } },
    is_new() { return true; },
    set_value() {},
});
const radios = machineField.querySelector(".dco-cutting-machine-radios");
assert.equal(radios.getAttribute("aria-label"), "Type de machine");
const values = machineField.querySelectorAll("input").map(input => input.value);
assert.deepEqual(values, ["CNC", "مشرحة"]);
assert.match(machineField.querySelectorAll("span").map(node => node.textContent).join(" "), /Scie à panneaux/);
assert.doesNotMatch(calls.join("\n"), /مشرحة/);

const deliveryContext = loaded[2];
const serverMessage = "رسالة الخادم الجاهزة";
deliveryContext.window.AlmdinaFrontend = {
    rpc(method) {
        if (String(method).includes("get_whatsapp_delivery_status")) return Promise.resolve({ working: true });
        return Promise.resolve({ ok: true, message: serverMessage });
    },
    errorMessage(error, fallback) { return String((error && error.message) || fallback); },
};
deliveryContext.window.AlmdinaPermissions = { can() { return true; }, canDocument() { return true; } };
deliveryContext.window.AlmdinaOrderRevisionUX = { canOfferEditSession() { return true; } };
const delivery = deliveryContext.window.AlmdinaOrderWhatsAppDeliveryUX;
const order = {
    doctype: "Door Cutting Order",
    doc: { name: "26-00089", status: "Draft", docstatus: 0, customer: "عميل التجربة" },
    is_new() { return false; },
    is_dirty() { return false; },
    __almdina_whatsapp_just_created: true,
};
assert.equal(delivery.buttonLabel(order), "Envoyer les mesures");
assert.equal(delivery.confirmMessage(order), "Envoyer le fichier ?");
assert.equal(delivery.BUTTON_ACTION_LABEL, "Send measurements via WhatsApp");

async function exercise() {
delivery.offerFromButton(order);
await Promise.resolve();
await Promise.resolve();
assert.equal(deliveryContext.window.alerts.at(-1).message, serverMessage);
assert.equal(calls.includes(serverMessage), false);

const actions = loaded[3];
const toolbar = element("div");
toolbar.className = "dco-fast-entry-toolbar";
const shell = element("div");
shell.className = "dco-fast-entry-shell";
const entry = element("div");
entry.appendChild(shell);
entry.appendChild(toolbar);
const parent = element("div");
parent.appendChild(entry);
actions.document.body.appendChild(parent);
const measurementForm = {
    doc: {
        name: "26-00089",
        customer: "عميل التجربة",
        edge_color: "لون الزبون الخاص",
        default_edge_type: "PVC أبيض",
        pieces: [],
    },
    fields_dict: { pieces_fast_entry: { $wrapper: { get() { return entry; } } } },
    is_dirty() { return false; },
};
actions.handlers[0].events.refresh(measurementForm);
assert.equal(toolbar.querySelector(".dco-print-measurements").textContent, "Imprimer");
assert.equal(toolbar.querySelector(".dco-open-measurements-window").querySelectorAll("span")[1].textContent, "Ouvrir dans une fenêtre");
toolbar.querySelector(".dco-open-measurements-window").click();
const overlay = actions.document.body.querySelector(".dco-measurement-entry-window");
assert.equal(overlay.getAttribute("dir"), "ltr");
assert.match(overlay.innerHTML, /عميل التجربة/);
assert.match(overlay.innerHTML, /لون الزبون الخاص/);
assert.match(overlay.innerHTML, /PVC أبيض/);
assert.equal(calls.includes("عميل التجربة"), false);
assert.equal(calls.includes("لون الزبون الخاص"), false);
assert.equal(calls.includes("PVC أبيض"), false);
overlay.remove();
measurementForm._dcoMeasurementEntryWindow = null;
direction = "rtl";
toolbar.querySelector(".dco-open-measurements-window").click();
const rtlOverlay = actions.document.body.querySelector(".dco-measurement-entry-window");
assert.equal(rtlOverlay.getAttribute("dir"), "rtl");
direction = "ltr";

const edges = loaded[6].window.AlmdinaMultiEdgeBanding;
const detail = edges.detailForSide(
    { doc: { default_edge_type: "PVC أبيض" }, _dco_side_edge_profiles: new Map() },
    { edge_long_right: 1, width_cm: 40, length_cm: 80, qty: 1 },
    "long_right"
);
assert.equal(detail.axis_label, "Longueur");
assert.equal(detail.edge_type, "PVC أبيض");
assert.equal(calls.includes("PVC أبيض"), false);
assert.match(detail.side_label, /Chant long droit|FR:Right length side/);

const colorRoot = element("div");
const badgeHost = element("div");
badgeHost.className = "dco-fast-entry-toolbar";
const colorField = element("div");
colorField.appendChild(badgeHost);
const colorForm = {
    doc: { edge_color: "لون الزبون الخاص", default_edge_type: "PVC أبيض" },
    fields_dict: {
        order_cost_invoice_html: { $wrapper: { get() { return colorRoot; } } },
        pieces_fast_entry: { $wrapper: { get() { return colorField; } } },
    },
};
const colorContext = loaded[5];
colorContext.handlers[0].events.refresh(colorForm);
const badge = badgeHost.querySelector(".dco-order-edge-color-badge");
assert.match(badge.innerHTML, /لون الزبون الخاص/);
assert.match(badge.innerHTML, /Couleur de chant/);
assert.equal(badge.getAttribute("title") || badge.title, "Couleur de commande");
assert.equal(calls.includes("لون الزبون الخاص"), false);

direction = "rtl";
const guard = loaded[8];
assert.equal(typeof guard.window.AlmdinaEdgeProfileDoubleClickGuard.cancelPendingClick, "function");
const controls = loaded[7].window.AlmdinaEdgeProfileControls;
const anchor = element("button");
const rowNode = element("tr");
const popoverDocument = loaded[7].document;
popoverDocument.body.appendChild(anchor);
rowNode.dataset.rowName = "ROW-1";
controls.openSidePopover(
    { doc: { docstatus: 0, default_edge_type: "", pieces: [{ name: "ROW-1" }] }, is_new() { return true; }, fields_dict: {} },
    rowNode,
    { side: "long_right", selectedField: "edge_long_right", overrideField: "edge_long_right_type_override", label: "Right long edge" },
    anchor
);
const popover = popoverDocument.getElementById("dco-edge-profile-popover");
assert.equal(popover.getAttribute("dir"), "rtl");

console.log("order entry locale ok");
}

exercise().catch(error => {
    console.error(error);
    process.exit(1);
});
