"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js");
const arabicText = /[\u0600-\u06FF]/;

const french = {
    "Factory management": "Gestion de l'usine",
    "Basic settings": "Paramètres de base",
    "3 core units": "3 unités principales",
    "Operational reports and cost": "Rapports opérationnels et coût",
    "Statistical and analytical data": "Données statistiques et analytiques",
    Customers: "Clients",
    "Manage customer records and contact details": "Gérer les fiches clients",
    "Edge banding types and prices": "Types et prix de chant",
    "Define edge banding types and their prices and thicknesses": "Définir les chants",
    "You do not have permission to access this section.": "Accès à cette section refusé.",
};

const translationCalls = [];

function translate(message) {
    translationCalls.push(message);
    assert.equal(Object.prototype.hasOwnProperty.call(french, message), true, message);
    return french[message];
}

function createText(value) {
    return {
        nodeType: 3,
        data: String(value),
        textContent: String(value),
        parentElement: null,
        parentNode: null,
    };
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
        style: {
            setProperty() {},
            removeProperty() {},
        },
    };

    const classes = new Set();
    element.classList = {
        add(...names) {
            names.filter(Boolean).forEach((name) => classes.add(name));
        },
        remove(...names) {
            names.forEach((name) => classes.delete(name));
        },
        contains(name) {
            return classes.has(name);
        },
        toggle(name, force) {
            const next = force === undefined ? !classes.has(name) : Boolean(force);
            if (next) classes.add(name);
            else classes.delete(name);
            return next;
        },
    };
    Object.defineProperty(element, "className", {
        get() {
            return [...classes].join(" ");
        },
        set(value) {
            classes.clear();
            String(value || "").split(/\s+/).filter(Boolean).forEach((name) => classes.add(name));
        },
    });

    element.getAttribute = (name) => (
        Object.prototype.hasOwnProperty.call(element.attributes, name)
            ? element.attributes[name]
            : null
    );
    element.setAttribute = (name, value) => {
        element.attributes[name] = String(value);
        if (name === "class") element.className = String(value);
        if (name === "id") document.ids.set(String(value), element);
    };
    element.removeAttribute = (name) => {
        delete element.attributes[name];
    };
    element.hasAttribute = (name) => Object.prototype.hasOwnProperty.call(element.attributes, name);
    element.dataset = new Proxy({}, {
        get(_target, prop) {
            const attr = "data-" + String(prop).replace(/[A-Z]/g, (char) => "-" + char.toLowerCase());
            const value = element.getAttribute(attr);
            return value === null ? undefined : value;
        },
        set(_target, prop, value) {
            const attr = "data-" + String(prop).replace(/[A-Z]/g, (char) => "-" + char.toLowerCase());
            element.setAttribute(attr, value);
            return true;
        },
        deleteProperty(_target, prop) {
            const attr = "data-" + String(prop).replace(/[A-Z]/g, (char) => "-" + char.toLowerCase());
            element.removeAttribute(attr);
            return true;
        },
    });

    Object.defineProperty(element, "textContent", {
        get() {
            return element.childNodes.map((node) => node.textContent || "").join("");
        },
        set(value) {
            element.childNodes = [createText(value)];
            element.childNodes[0].parentElement = element;
            element.childNodes[0].parentNode = element;
            element.children = [];
        },
    });
    element.innerHTML = "";

    element.appendChild = (node) => {
        if (node.parentElement && node.parentElement.removeChild) node.parentElement.removeChild(node);
        node.parentElement = element;
        node.parentNode = element;
        element.childNodes.push(node);
        if (node.nodeType === 1) element.children.push(node);
        return node;
    };
    element.insertBefore = (node, before) => {
        if (!before) return element.appendChild(node);
        if (node.parentElement && node.parentElement.removeChild) node.parentElement.removeChild(node);
        const index = element.childNodes.indexOf(before);
        node.parentElement = element;
        node.parentNode = element;
        element.childNodes.splice(index < 0 ? element.childNodes.length : index, 0, node);
        element.children = element.childNodes.filter((child) => child.nodeType === 1);
        return node;
    };
    element.removeChild = (node) => {
        element.childNodes = element.childNodes.filter((child) => child !== node);
        element.children = element.childNodes.filter((child) => child.nodeType === 1);
        node.parentElement = null;
        node.parentNode = null;
        return node;
    };
    element.remove = () => {
        if (element.parentElement) element.parentElement.removeChild(element);
    };
    Object.defineProperty(element, "firstChild", {
        get() {
            return element.childNodes[0] || null;
        },
    });
    element.querySelectorAll = (selector) => queryAll(element, selector);
    element.querySelector = (selector) => queryAll(element, selector)[0] || null;
    element.matches = (selector) => selector.split(",").some((part) => matchesCompound(element, part.trim()));
    element.closest = (selector) => {
        const groups = selector.split(",").map((part) => part.trim());
        let current = element;
        while (current) {
            if (current.nodeType === 1 && groups.some((part) => matchesCompound(current, part))) return current;
            current = current.parentElement;
        }
        return null;
    };
    element.contains = (node) => {
        let current = node;
        while (current) {
            if (current === element) return true;
            current = current.parentElement;
        }
        return false;
    };
    return element;
}

function elementChildren(node) {
    return (node.children || node.childNodes || []).filter((child) => child && child.nodeType === 1);
}

function matchesCompound(element, selector) {
    if (!element || element.nodeType !== 1 || !selector) return false;
    const tokens = [...selector.matchAll(/([a-zA-Z][\w-]*)|(\.[\w-]+)|(#[\w-]+)|(\[[\w-]+\])|:not\(([^)]+)\)|(:first-child)|(:last-child)/g)];
    if (!tokens.length) return false;
    return tokens.every((token) => {
        if (token[1]) return element.tagName === token[1].toUpperCase();
        if (token[2]) return element.classList.contains(token[2].slice(1));
        if (token[3]) return element.getAttribute("id") === token[3].slice(1);
        if (token[4]) return element.hasAttribute(token[4].slice(1, -1));
        if (token[5]) return !matchesCompound(element, token[5]);
        const siblings = elementChildren(element.parentElement || {});
        if (token[6]) return siblings[0] === element;
        if (token[7]) return siblings[siblings.length - 1] === element;
        return false;
    });
}

function walk(node, visit) {
    elementChildren(node).forEach((child) => {
        visit(child);
        walk(child, visit);
    });
}

function queryAll(root, selector) {
    const found = [];
    selector.split(",").map((part) => part.trim()).filter(Boolean).forEach((group) => {
        const steps = group.split(/\s+/);
        let current = [root];
        steps.forEach((step) => {
            const next = [];
            current.forEach((node) => {
                walk(node, (element) => {
                    if (matchesCompound(element, step)) next.push(element);
                });
            });
            current = next;
        });
        found.push(...current);
    });
    return [...new Set(found)];
}

const listeners = [];
const timers = [];
const document = {
    nodeType: 9,
    readyState: "loading",
    ids: new Map(),
    getElementById(id) {
        return this.ids.get(id) || null;
    },
    createElement,
    addEventListener(type, handler) {
        listeners.push({ type, handler });
    },
    querySelector(selector) {
        return queryAll(this.documentElement, selector)[0] || null;
    },
    querySelectorAll(selector) {
        return queryAll(this.documentElement, selector);
    },
};
document.documentElement = createElement("html");
document.head = createElement("head");
document.body = createElement("body");
document.documentElement.appendChild(document.head);
document.documentElement.appendChild(document.body);

const window = {
    document,
    location: { origin: "http://localhost", pathname: "/app/customer" },
    Node: { ELEMENT_NODE: 1, TEXT_NODE: 3 },
    URL,
    console,
    setTimeout(handler, delay) {
        const id = timers.length + 1;
        timers.push({ id, handler, delay: delay || 0 });
        return id;
    },
    clearTimeout(id) {
        const index = timers.findIndex((timer) => timer.id === id);
        if (index >= 0) timers.splice(index, 1);
    },
    requestAnimationFrame(handler) {
        return window.setTimeout(handler, 0);
    },
    cancelAnimationFrame(id) {
        window.clearTimeout(id);
    },
    addEventListener() {},
    MutationObserver: class {
        observe() {}
        disconnect() {}
    },
};
window.window = window;
global.Node = window.Node;

const context = vm.createContext(window);
context.__ = translate;

function load(relativePath) {
    vm.runInContext(fs.readFileSync(path.join(root, relativePath), "utf8"), context, { filename: relativePath });
}

load("almdina_shortcut_presentation.js");
load("almdina_workspace_home_ux.js");
load("almdina_desk_sidebar_ux.js");
load("shared_shell.js");

assert.deepEqual(translationCalls, []);

const presentation = context.AlmdinaShortcutPresentation;
const home = context.AlmdinaWorkspaceHomeUX;
assert.equal(presentation.SHORTCUT_BY_LINK_TO.Customer.label, "Customers");
assert.equal(presentation.SHORTCUT_BY_LINK_TO.Customer.desc, "Manage customer records and contact details");
assert.equal(presentation.SHORTCUT_BY_LINK_TO.Customer.icon, "users");
assert.equal(presentation.LABEL_TO_LINK_TO["الزبائن"], "Customer");
assert.equal(presentation.metaForLinkTo("customer").label, "Customers");
assert.equal(home.SECTION_PRESENTATION["master-data-header"].title, "Basic settings");
assert.equal(home.SECTION_PRESENTATION["master-data-header"].meta, "3 core units");
assert.equal(home.SECTION_PRESENTATION["master-data-header"].id, "master");
assert.equal(home.SHORTCUT_BLOCK_TO_LINK["customers-shortcut"], "Customer");
assert.equal(home.SHORTCUT_BLOCK_TO_LINK["orders-shortcut"], "Door Cutting Order");
assert.equal(translationCalls.length, 0);

function el(tag, className, text) {
    const node = createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

const page = el("div", "page-container");
page.setAttribute("id", "page-Workspaces");
const crumbs = el("ul", "navbar-breadcrumbs");
const homeItem = el("li");
const homeLink = el("a");
homeLink.appendChild(el("svg"));
homeItem.appendChild(homeLink);
const currentItem = el("li");
const currentLink = el("a", "title-text", "Almdina ERP");
currentItem.appendChild(currentLink);
crumbs.appendChild(homeItem);
crumbs.appendChild(currentItem);
const editor = el("div", "editor-js-container");

function headerBlock(id, arabicTitle) {
    const block = el("div", "ce-block");
    block.setAttribute("data-id", id);
    const header = el("div", "widget header");
    const host = el("div", "ce-header");
    const heading = el("span", "h4");
    heading.appendChild(el("b", "", arabicTitle));
    host.appendChild(heading);
    header.appendChild(host);
    block.appendChild(header);
    return block;
}

function shortcutBlock(id, widgetName, arabicLabel) {
    const block = el("div", "ce-block");
    if (id) block.setAttribute("data-id", id);
    const widget = el("div", "shortcut-widget-box");
    widget.setAttribute("data-widget-name", widgetName);
    const head = el("div", "widget-head");
    const label = el("div", "widget-label");
    const title = el("div", "widget-title");
    const ellipsis = el("span", "ellipsis", arabicLabel);
    ellipsis.setAttribute("title", arabicLabel);
    title.appendChild(ellipsis);
    label.appendChild(title);
    head.appendChild(label);
    head.appendChild(el("div", "widget-control"));
    widget.appendChild(head);
    block.appendChild(widget);
    return block;
}

editor.appendChild(headerBlock("master-data-header", "الإعدادات الأساسية"));
editor.appendChild(shortcutBlock("customers-shortcut", "الزبائن", "الزبائن"));
editor.appendChild(shortcutBlock("", "أنواع القشاط وأسعاره", "أنواع القشاط وأسعاره"));
editor.appendChild(headerBlock("reports-header", "التقارير التشغيلية والتكلفة"));
page.appendChild(crumbs);
page.appendChild(editor);
document.body.appendChild(page);

const sidebar = el("div", "body-sidebar");
const item = el("div", "sidebar-item-container");
item.setAttribute("title", "الزبائن");
const anchor = el("a", "item-anchor");
anchor.setAttribute("href", "/app/customer");
const sidebarLabel = el("span", "sidebar-item-label", "الزبائن");
const icon = el("span", "sidebar-item-icon");
item.appendChild(anchor);
item.appendChild(sidebarLabel);
item.appendChild(icon);
sidebar.appendChild(item);
document.body.appendChild(sidebar);

context.frappe = {
    boot: { workspace_sidebar_item: { main: { items: [] } } },
    app: {},
    workspaces: { "almdina-erp": {} },
    get_route: () => ["Workspaces", "almdina-erp"],
    get_route_str: () => "Workspaces/almdina-erp",
    router: {
        current_route: ["Workspaces", "almdina-erp"],
        slug: (value) => String(value || "").toLowerCase().replace(/ /g, "-"),
        on() {},
    },
    utils: { icon: (name) => `<svg data-icon="${name}"></svg>` },
    show_alert(payload) {
        context.alerts.push(payload);
    },
    set_route() {
        return Promise.resolve();
    },
};
context.alerts = [];
context.AlmdinaPermissions = {
    version: () => 7,
    navigation: () => ({
        shared_shell: true,
        home_page: "almdina-erp",
        workspaces: ["almdina-erp"],
        profile: "shared",
    }),
    surface: (name) => name !== "customer_admin",
};

home.polish();
context.AlmdinaDeskSidebarUX.apply();

const master = [...editor.querySelectorAll(".ce-block")].find((block) => block.getAttribute("data-id") === "master-data-header");
const reports = [...editor.querySelectorAll(".ce-block")].find((block) => block.getAttribute("data-id") === "reports-header");
const customer = [...editor.querySelectorAll(".ce-block")].find((block) => block.getAttribute("data-id") === "customers-shortcut");
const edge = [...editor.querySelectorAll(".shortcut-widget-box")].find((widget) => widget.getAttribute("data-widget-name") === "أنواع القشاط وأسعاره");

assert.equal(master.querySelector("b").textContent, french["Basic settings"]);
assert.equal(master.querySelector(".alm-workspace-section-meta").textContent, french["3 core units"]);
assert.equal(master.querySelector(".widget.header").getAttribute("data-alm-section"), "master");
assert.equal(reports.querySelector("b").textContent, french["Operational reports and cost"]);
assert.equal(reports.querySelector(".alm-workspace-section-meta").textContent, french["Statistical and analytical data"]);
assert.equal(reports.querySelector(".widget.header").getAttribute("data-alm-section"), "reports");
assert.equal(crumbs.querySelector("a.title-text").textContent, french["Factory management"]);
assert.equal(customer.querySelector(".shortcut-widget-box").getAttribute("data-alm-link-to"), "Customer");
assert.equal(customer.querySelector(".ellipsis").textContent, french.Customers);
assert.equal(customer.querySelector(".alm-workspace-shortcut-desc").textContent, french["Manage customer records and contact details"]);
assert.equal(edge.getAttribute("data-alm-link-to"), "Edge Banding Type");
assert.equal(edge.querySelector(".ellipsis").textContent, french["Edge banding types and prices"]);
assert.equal(edge.querySelector(".ellipsis").getAttribute("title"), french["Edge banding types and prices"]);
assert.equal(edge.querySelector(".alm-workspace-shortcut-desc").textContent, french["Define edge banding types and their prices and thicknesses"]);
assert.equal(anchor.getAttribute("href"), "/app/customer");
assert.equal(sidebarLabel.textContent, french.Customers);
assert.equal(icon.getAttribute("data-alm-sidebar-icon"), "users");
assert.equal(customer.getAttribute("data-id"), "customers-shortcut");
assert.equal(home.SECTION_PRESENTATION["reports-header"].id, "reports");
assert.equal(translationCalls.every((message) => !arabicText.test(message)), true);

context.frappe.get_route_str = () => "customer";
context.frappe.router.current_route = ["customer"];
listeners.filter((listener) => listener.type === "DOMContentLoaded").forEach((listener) => listener.handler());
timers.filter((timer) => timer.delay === 0).forEach((timer) => timer.handler());

assert.equal(context.alerts.length, 1);
assert.equal(context.alerts[0].message, french["You do not have permission to access this section."]);
assert.equal(
    translationCalls.includes("You do not have permission to access this section."),
    true
);
assert.equal(anchor.getAttribute("href"), "/app/customer");
assert.equal(customer.querySelector(".shortcut-widget-box").getAttribute("data-alm-link-to"), "Customer");
assert.equal(presentation.SHORTCUT_BY_LINK_TO["Door Cutting Order"].label, "Door cutting orders");
assert.equal(arabicText.test(presentation.SHORTCUT_BY_LINK_TO["Door Cutting Order"].label), false);
assert.equal(arabicText.test(presentation.SHORTCUT_BY_LINK_TO["Door Cutting Order"].desc), false);

console.log("workspace navigation locale ok");
