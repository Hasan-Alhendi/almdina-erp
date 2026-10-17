"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const repo = path.resolve(__dirname, "../..");
const arabicText = /[\u0600-\u06FF]/;
const calls = [];
let direction = "ltr";
const protectedText = ["ملاحظة المستخدم", "نص مرسوم خاص", "AVIS-SERVEUR", "عميل التجربة"];

const french = {
    "Special door documentation": "Documentation de porte spéciale",
    "Save documentation": "Enregistrer la documentation",
    "Upload an image": "Téléverser une image",
    "Scan": "Numériser",
    "Clipped corner shape": "Coin coupé",
    "Smart pen": "Stylo intelligent",
    "Door documentation canvas": "Zone de documentation",
    "Documentation tools": "Outils de documentation",
    "Designer notes": "Notes du concepteur",
    "Door {0}": "Porte {0}",
    "{0} × {1} cm": "{0} × {1} cm",
    "The scanner program is not installed or is stopped. Install it once, or open it from the Start menu if it is already installed.": "Le programme du scanner est arrêté.",
    "Add a reference image or an explanatory element before saving.": "Ajoutez une image ou un élément.",
    "Note text": "Texte de la note",
    "Add a note": "Ajouter une note",
    "Add": "Ajouter",
    "Enter the size first": "Saisissez la taille d'abord",
    "Enter the door width and length first, then open the shape documentation.": "Saisissez la largeur et la longueur.",
    "Opening door documentation…": "Ouverture de la documentation…",
    "The documentation link is incomplete. Open it from the order.": "Le lien de documentation est incomplet.",
};

function translate(message, replacements) {
    calls.push(message);
    assert.equal(protectedText.includes(message), false, message);
    assert.equal(arabicText.test(String(message)), false, message);
    let text = Object.prototype.hasOwnProperty.call(french, message) ? french[message] : `FR:${message}`;
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.replaceAll(`{${index}}`, String(value));
        });
    }
    return text;
}

function decode(value) {
    return String(value)
        .replaceAll("&quot;", '"')
        .replaceAll("&#39;", "'")
        .replaceAll("&lt;", "<")
        .replaceAll("&gt;", ">")
        .replaceAll("&amp;", "&");
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function createText(value) {
    return { nodeType: 3, data: String(value), textContent: String(value), parentElement: null, parentNode: null };
}

function createElement(tag) {
    const element = {
        nodeType: 1,
        tagName: String(tag || "div").toUpperCase(),
        childNodes: [],
        children: [],
        parentElement: null,
        parentNode: null,
        attributes: {},
        style: { setProperty() {}, removeProperty() {} },
        disabled: false,
        hidden: false,
        checked: false,
        value: "",
        _listeners: {},
        files: null,
    };
    const classes = new Set();
    element.classList = {
        add(...names) { names.filter(Boolean).forEach(name => classes.add(name)); },
        remove(...names) { names.forEach(name => classes.delete(name)); },
        contains(name) { return classes.has(name); },
        toggle(name, force) {
            const next = force === undefined ? !classes.has(name) : Boolean(force);
            if (next) classes.add(name);
            else classes.delete(name);
            return next;
        },
    };
    Object.defineProperty(element, "className", {
        get() { return [...classes].join(" "); },
        set(value) {
            classes.clear();
            String(value || "").split(/\s+/).filter(Boolean).forEach(name => classes.add(name));
        },
    });
    Object.defineProperty(element, "href", {
        get() { return element.getAttribute("href"); },
        set(value) { element.setAttribute("href", value); },
    });
    element.getAttribute = name => Object.prototype.hasOwnProperty.call(element.attributes, name) ? element.attributes[name] : null;
    element.setAttribute = (name, value) => {
        element.attributes[name] = String(value);
        if (name === "class") element.className = String(value);
        if (name === "disabled") element.disabled = true;
        if (name === "hidden") element.hidden = true;
        if (name === "checked") element.checked = true;
    };
    element.removeAttribute = name => { delete element.attributes[name]; };
    element.hasAttribute = name => Object.prototype.hasOwnProperty.call(element.attributes, name);
    element.dataset = new Proxy({}, {
        get(_target, prop) {
            const attr = "data-" + String(prop).replace(/[A-Z]/g, char => "-" + char.toLowerCase());
            const value = element.getAttribute(attr);
            return value === null ? undefined : value;
        },
        set(_target, prop, value) {
            const attr = "data-" + String(prop).replace(/[A-Z]/g, char => "-" + char.toLowerCase());
            element.setAttribute(attr, value);
            return true;
        },
        deleteProperty(_target, prop) {
            const attr = "data-" + String(prop).replace(/[A-Z]/g, char => "-" + char.toLowerCase());
            element.removeAttribute(attr);
            return true;
        },
    });
    Object.defineProperty(element, "textContent", {
        get() { return element.childNodes.map(node => node.textContent || "").join(""); },
        set(value) {
            element.childNodes = [createText(value)];
            element.childNodes[0].parentElement = element;
            element.childNodes[0].parentNode = element;
            element.children = [];
        },
    });
    Object.defineProperty(element, "innerHTML", {
        get() { return element.childNodes.map(serialize).join(""); },
        set(value) { parseInto(element, String(value)); },
    });
    element.appendChild = node => {
        if (node.parentElement && node.parentElement.removeChild) node.parentElement.removeChild(node);
        node.parentElement = element;
        node.parentNode = element;
        element.childNodes.push(node);
        if (node.nodeType === 1) element.children.push(node);
        return node;
    };
    element.removeChild = node => {
        element.childNodes = element.childNodes.filter(child => child !== node);
        element.children = element.childNodes.filter(child => child.nodeType === 1);
        node.parentElement = null;
        node.parentNode = null;
        return node;
    };
    element.remove = () => { if (element.parentElement) element.parentElement.removeChild(element); };
    element.addEventListener = (type, handler) => {
        element._listeners[type] = element._listeners[type] || [];
        element._listeners[type].push(handler);
    };
    element.removeEventListener = () => {};
    element.dispatchEvent = event => {
        (element._listeners[event.type] || []).forEach(handler => handler(event));
    };
    element.click = () => {
        const event = { type: "click", target: element, preventDefault() {} };
        let current = element;
        while (current) {
            (current._listeners.click || []).forEach(handler => handler(event));
            current = current.parentElement;
        }
    };
    element.setPointerCapture = () => {};
    element.focus = () => {};
    element.querySelectorAll = selector => queryAll(element, selector);
    element.querySelector = selector => queryAll(element, selector)[0] || null;
    element.matches = selector => selector.split(",").some(part => matchesCompound(element, part.trim()));
    element.closest = selector => {
        const groups = selector.split(",").map(part => part.trim());
        let current = element;
        while (current) {
            if (current.nodeType === 1 && groups.some(part => matchesCompound(current, part))) return current;
            current = current.parentElement;
        }
        return null;
    };
    element.contains = node => {
        let current = node;
        while (current) {
            if (current === element) return true;
            current = current.parentElement;
        }
        return false;
    };
    return element;
}

function serialize(node) {
    if (!node || node.nodeType === 3) return escapeHtml(node ? node.textContent : "");
    const attrs = Object.entries(node.attributes).map(([name, value]) => ` ${name}="${escapeHtml(value)}"`).join("");
    return `<${node.tagName.toLowerCase()}${attrs}>${node.childNodes.map(serialize).join("")}</${node.tagName.toLowerCase()}>`;
}

function parseAttrs(element, source) {
    const re = /([:\w-]+)(?:="([^"]*)")?/g;
    let match;
    while ((match = re.exec(source))) {
        if (match[1] === "/") continue;
        element.setAttribute(match[1], decode(match[2] || ""));
    }
}

function parseInto(parent, html) {
    parent.childNodes = [];
    parent.children = [];
    const voidTags = new Set(["INPUT", "BR", "IMG", "HR", "META", "LINK"]);
    const re = /<(\/?)([a-zA-Z][\w:-]*)([^>]*)>|([^<]+)/g;
    const stack = [parent];
    let match;
    while ((match = re.exec(html))) {
        if (match[4]) {
            const text = decode(match[4]);
            if (text.trim() || text) stack.at(-1).appendChild(createText(text));
            continue;
        }
        const tag = match[2].toUpperCase();
        if (match[1] === "/") {
            while (stack.length > 1 && stack.at(-1).tagName !== tag) stack.pop();
            if (stack.length > 1) stack.pop();
            continue;
        }
        const element = createElement(match[2]);
        parseAttrs(element, match[3] || "");
        stack.at(-1).appendChild(element);
        if (!voidTags.has(tag) && !/\/\s*$/.test(match[3] || "")) stack.push(element);
    }
}

function elementChildren(node) {
    return (node.children || []).filter(child => child && child.nodeType === 1);
}

function matchesCompound(element, selector) {
    if (!element || element.nodeType !== 1 || !selector) return false;
    const tokens = [...selector.matchAll(/([a-zA-Z][\w-]*)|(\.[\w-]+)|(#[\w-]+)|(\[[\w-]+(?:="[^"]*")?\])|:not\(([^)]+)\)/g)];
    if (!tokens.length) return false;
    return tokens.every(token => {
        if (token[1]) return element.tagName === token[1].toUpperCase();
        if (token[2]) return element.classList.contains(token[2].slice(1));
        if (token[3]) return element.getAttribute("id") === token[3].slice(1);
        if (token[4]) {
            const body = token[4].slice(1, -1);
            const [name, quoted] = body.split("=");
            if (!element.hasAttribute(name)) return false;
            return quoted === undefined || element.getAttribute(name) === quoted.slice(1, -1);
        }
        if (token[5]) return !matchesCompound(element, token[5]);
        return false;
    });
}

function walk(node, visit) {
    elementChildren(node).forEach(child => {
        visit(child);
        walk(child, visit);
    });
}

function queryAll(root, selector) {
    const found = [];
    selector.split(",").map(part => part.trim()).filter(Boolean).forEach(group => {
        const steps = group.split(/\s+/);
        let current = [root];
        steps.forEach(step => {
            const next = [];
            current.forEach(node => walk(node, element => {
                if (matchesCompound(element, step)) next.push(element);
            }));
            current = next;
        });
        found.push(...current);
    });
    return [...new Set(found)];
}

const document = {
    documentElement: null,
    createElement,
    querySelector(selector) { return queryAll(this.documentElement, selector)[0] || null; },
    querySelectorAll(selector) { return queryAll(this.documentElement, selector); },
};
document.documentElement = createElement("html");
document.body = createElement("body");
document.documentElement.appendChild(document.body);
document.documentElement.setAttribute("dir", "rtl");

const prints = [];
const prompts = [];
const routes = [];
const alerts = [];
const diagnostics = [];
const window = {
    document,
    console: {
        error(...args) { diagnostics.push(args.map(item => String(item && item.message || item)).join(" ")); },
        warn() {},
        log() {},
    },
    URL,
    setTimeout(handler) { handler(); return 1; },
    clearTimeout() {},
    addEventListener() {},
    removeEventListener() {},
    open() { return null; },
    AlmdinaLocale: {
        translate,
        direction() { return direction; },
    },
    AlmdinaUi: {
        button(options = {}) {
            const attrs = Object.entries(options.attrs || {}).map(([name, value]) => ` ${name}="${escapeHtml(value)}"`).join("");
            const disabled = options.disabled ? " disabled" : "";
            const className = options.className ? ` ${options.className}` : "";
            return `<button type="button" class="btn${className}"${disabled}${attrs}>${escapeHtml(options.label || "")}</button>`;
        },
    },
    AlmdinaPermissions: {
        can() { return true; },
        canDocument() { return true; },
    },
    frappe: {
        pages: { "door-drawing": {} },
        get_route: () => ["door-drawing"],
        set_route(...args) { routes.push(args); },
        msgprint(message) { prints.push(message); },
        show_alert(payload) { alerts.push(payload); },
        confirm(_message, yes) { yes(); },
        prompt(fields, callback, title, primary) {
            prompts.push({ label: fields[0] && fields[0].label, title, primary });
            callback({ text: "نص مرسوم خاص" });
        },
        utils: { escape_html: escapeHtml },
        ui: { make_app_page() {} },
        require() { return Promise.resolve(); },
    },
};
window.window = window;
window.__ = translate;
global.Node = { ELEMENT_NODE: 1, TEXT_NODE: 3 };

const context = vm.createContext(window);

function load(relativePath) {
    vm.runInContext(fs.readFileSync(path.join(repo, relativePath), "utf8"), context, { filename: relativePath });
}

assert.equal(calls.length, 0);
load("public/js/special_shape_documentation/application/templates.js");
load("public/js/special_shape_documentation/presentation/workspace_shell.js");
load("public/js/special_shape_documentation/presentation/workspace_controller.js");
load("public/js/door_cutting_order/drawing/special_shape_facade.js");
load("almdina_erp/page/door_drawing/door_drawing.js");
assert.deepEqual(calls, []);

const api = context.AlmdinaSpecialShapeDocumentation;
assert.equal(api.Templates.DEFINITIONS.find(item => item.id === "clipped-corner").label, "Clipped corner shape");
assert.equal(api.Templates.DEFINITIONS.map(item => item.id).join("|"), "clipped-corner|top-arch|side-arch|trapezoid|inner-opening|slanted-edge");
assert.equal(calls.length, 0);

const userDocument = {
    schema: "almdina.special-shape-documentation",
    version: 1,
    source: "pen",
    templateId: "clipped-corner",
    notes: "ملاحظة المستخدم",
    reference: null,
    canvas: { widthMm: 800, heightMm: 2100 },
    elements: [{ id: "text-1", type: "text", text: "نص مرسوم خاص" }],
};
const commits = [];
api.Document = {
    hasContent(doc) { return Boolean(doc.reference) || doc.elements.length > 0; },
    toStored(doc) { return doc; },
    fromStored() { return userDocument; },
    clone(value) { return { ...value }; },
    id(prefix) { return `${prefix}-1`; },
    addElement(doc, element) { return { ...doc, elements: [...doc.elements, element] }; },
    removeElement(doc, id) { return { ...doc, elements: doc.elements.filter(item => item.id !== id) }; },
    setNotes(doc, notes) { return { ...doc, notes }; },
    setReference(doc, reference) { return { ...doc, reference }; },
};
api.ReferenceCrop = {
    FULL: { x: 0, y: 0, width: 1, height: 1 },
    isFull() { return true; },
    normalize(value) { return value; },
    transform() { return { x: 0, y: 0, width: 1, height: 1 }; },
};
api.History = {
    create(doc) {
        let current = doc;
        return {
            get: () => current,
            state: () => ({ document: current, dirty: false, canUndo: false, canRedo: false }),
            commit(next) { current = next; commits.push(next); },
            markSaved() {},
            isDirty: () => false,
            undo() {},
            redo() {},
        };
    },
};
api.SmartPen = { clean: () => ({ points: [], suggestClose: false }), close: points => points };
api.ElementTransform = {};
api.ElementClipboard = { create: () => ({ clear() {}, copy() { return false; }, canPaste() { return false; }, paste() { return { id: "pasted" }; } }) };
api.KeyboardShortcuts = { physicalCode: () => "", isEditableTarget: () => false, resolve: () => null };
api.WorkspaceApi = {
    async load() {
        return {
            order: { name: "ORD-9", customer: "عميل التجربة" },
            piece: { name: "PIECE-1", piece_no: 4, width_cm: 80, length_cm: 210, special_shape_drawing_json: "{}" },
            permissions: { can_edit: true, edit_reason: "" },
            manufacturing_notice: "AVIS-SERVEUR",
        };
    },
    async save() { return { piece: { name: "PIECE-1" } }; },
    async removeImage() { return { removed: true }; },
};
api.ScannerBridge = {
    ERROR_CODES: { UNAVAILABLE: "bridge-unavailable", FORBIDDEN: "bridge-forbidden", BUSY: "scanner-busy", NO_SCANNER: "scanner-unavailable", SCAN_FAILED: "scan-failed", INVALID_IMAGE: "invalid-image", INVALID_RESPONSE: "invalid-response", IMAGE_TOO_LARGE: "image-too-large" },
    INSTALLER_URL: "https://example.invalid/AlmdinaScannerBridgeSetup.exe",
    async health() {
        const error = new Error("bridge down");
        error.code = "bridge-unavailable";
        throw error;
    },
    async scan() { return null; },
};
api.CanvasRenderer = {
    create() {
        return {
            draw() {},
            render() {},
            zoomPercentage: () => 100,
            referenceImageSize: () => null,
            suggestReferenceCrop: () => null,
            fitToContent() {},
            resetZoom() {},
            zoomBy() {},
            zoomAt() {},
            panBy() {},
            screenToMm: () => ({ xMm: 12, yMm: 20 }),
            screenDeltaToMm: () => ({ xMm: 1, yMm: 1 }),
            hitTest: () => null,
            selectionRegion: () => "move",
            cropRegion: () => null,
            cropPoint: () => null,
        };
    },
};

const wrapper = createElement("div");
const main = createElement("div");
main.className = "layout-main-section";
wrapper.appendChild(main);
document.body.appendChild(wrapper);

async function exercise() {
const controller = api.WorkspaceController.mount(wrapper);
await controller.open({ orderName: "ORD-9", pieceName: "PIECE-1" });
const workspace = main.querySelector(".ald-doc-workspace");
assert.equal(workspace.getAttribute("dir"), "ltr");
assert.equal(workspace.getAttribute("aria-label"), french["Special door documentation"]);
assert.equal(workspace.querySelector("h1").textContent, french["Special door documentation"]);
assert.equal(workspace.querySelector('[data-action="save"]').textContent, french["Save documentation"]);
assert.equal(workspace.querySelector('[data-action="choose-image"]').textContent.includes(french["Upload an image"]), true);
assert.equal(workspace.querySelector("[data-scan-label]").textContent, french.Scan);
assert.equal(workspace.querySelector('[data-template="clipped-corner"]').textContent.includes(french["Clipped corner shape"]), true);
assert.equal(workspace.querySelector('[data-template="clipped-corner"]').getAttribute("data-template"), "clipped-corner");
assert.equal(workspace.querySelector('.ald-doc-tool[data-tool="pen"]').getAttribute("aria-label"), french["Smart pen"]);
assert.equal(workspace.querySelector('.ald-doc-tool[data-tool="pen"]').getAttribute("data-tool"), "pen");
assert.equal(workspace.querySelector(".ald-doc-canvas").getAttribute("aria-label"), french["Door documentation canvas"]);
assert.equal(workspace.querySelector(".ald-doc-toolbar").getAttribute("aria-label"), french["Documentation tools"]);
assert.equal(workspace.querySelector(".ald-doc-notes span").textContent, french["Designer notes"]);
assert.equal(workspace.querySelector("[data-notes]").value, "ملاحظة المستخدم");
assert.equal(workspace.textContent.includes("عميل التجربة"), true);
assert.equal(workspace.textContent.includes("ORD-9"), true);
assert.equal(workspace.textContent.includes("AVIS-SERVEUR"), true);
assert.equal(workspace.textContent.includes("نص مرسوم خاص"), false);
assert.equal(workspace.querySelector('[data-layer="text-1"] small').textContent, "text");
assert.equal(workspace.querySelector(".ald-doc-piece-meta span").textContent, "Porte 4");
assert.equal(calls.includes("AVIS-SERVEUR"), false);
assert.equal(calls.includes("ملاحظة المستخدم"), false);
assert.equal(calls.includes("نص مرسوم خاص"), false);

api.Document.hasContent = () => false;
workspace.querySelector('[data-action="save"]').click();
assert.equal(prints.at(-1), french["Add a reference image or an explanatory element before saving."]);

workspace.querySelector('[data-action="scan-image"]').click();
await new Promise(resolve => setImmediate(resolve));
assert.equal(prints.at(-1), french["The scanner program is not installed or is stopped. Install it once, or open it from the Start menu if it is already installed."]);
assert.equal(workspace.querySelector("[data-scanner-status]").textContent, prints.at(-1));
assert.equal(workspace.querySelector("[data-scanner-install]").getAttribute("href"), "https://example.invalid/AlmdinaScannerBridgeSetup.exe");
assert.equal(diagnostics.some(line => line.includes("Scanner acquisition failed") && !arabicText.test(line)), true);

workspace.querySelector('.ald-doc-tool[data-tool="text"]').click();
workspace.querySelector(".ald-doc-canvas").dispatchEvent({ type: "pointerdown", button: 0, pointerId: 1, clientX: 4, clientY: 6, preventDefault() {} });
await Promise.resolve();
assert.equal(prompts.at(-1).label, french["Note text"]);
assert.equal(prompts.at(-1).title, french["Add a note"]);
assert.equal(prompts.at(-1).primary, french.Add);
assert.equal(commits.at(-1).elements.at(-1).text, "نص مرسوم خاص");
assert.equal(commits.at(-1).schema, "almdina.special-shape-documentation");

direction = "rtl";
await controller.open({ orderName: "ORD-9", pieceName: "PIECE-1" });
assert.equal(main.querySelector(".ald-doc-workspace").getAttribute("dir"), "rtl");

const titles = [];
const routeMessages = [];
context.frappe.ui.make_app_page = ({ parent, title }) => {
    titles.push(title);
    if (!parent.querySelector(".layout-main-section")) {
        const section = createElement("div");
        section.className = "layout-main-section";
        parent.appendChild(section);
    }
};
api.WorkspaceController = {
    mount() {
        return {
            suspend() {},
            open() {},
            showRouteError(message) { routeMessages.push(message); },
        };
    },
};
const pageWrapper = createElement("div");
document.body.appendChild(pageWrapper);
context.$ = () => ({ off() { return this; }, on() { return this; } });
context.frappe.pages["door-drawing"].on_page_load(pageWrapper);
assert.equal(titles[0], french["Special door documentation"]);
assert.equal(pageWrapper.textContent.includes(french["Opening door documentation…"]), true);
context.frappe.get_route = () => ["door-drawing"];
context.frappe.pages["door-drawing"].on_page_show(pageWrapper);
await pageWrapper.__almdinaDocumentationBoot;
await Promise.resolve();
assert.equal(routeMessages[0], french["The documentation link is incomplete. Open it from the order."]);

const editor = context.AlmdinaSpecialShapeEditor;
const frm = {
    doc: { name: "ORD-9", pieces: [{ name: "PIECE-1", idx: 1, width_cm: 0, length_cm: 0 }] },
    is_new() { return false; },
    is_dirty() { return false; },
};
await editor.open(frm, frm.doc.pieces[0]);
assert.equal(prints.at(-1).title, french["Enter the size first"]);
assert.equal(prints.at(-1).message, french["Enter the door width and length first, then open the shape documentation."]);
frm.doc.pieces[0].width_cm = 80;
frm.doc.pieces[0].length_cm = 210;
await editor.open(frm, frm.doc.pieces[0]);
assert.equal(routes.at(-1).join("|"), "door-drawing|ORD-9|PIECE-1");
}

exercise().then(() => {
    console.log("special shape documentation locale ok");
}).catch(error => {
    console.error(error);
    process.exit(1);
});
