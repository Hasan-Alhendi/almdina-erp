"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const responsiveSource = fs.readFileSync(
    "almdina_erp/public/js/responsive_device.js",
    "utf8"
);
const source = fs.readFileSync(
    "almdina_erp/public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js",
    "utf8"
);
const cardCss = fs.readFileSync(
    "almdina_erp/public/css/door_cutting_order_responsive.css",
    "utf8"
);

const handlers = {};
const rootClasses = new Set();
let rootWidth = 390;
let orderCanEdit = true;

const root = {
    classList: {
        toggle(name, enabled) {
            if (enabled) rootClasses.add(name);
            else rootClasses.delete(name);
        },
        remove(name) {
            rootClasses.delete(name);
        },
    },
    closest(selector) {
        void selector;
        return null;
    },
    querySelector(selector) {
        if (selector === ".dco-fast-entry-shell") {
            return {
                classList: root.classList,
                closest: root.closest,
            };
        }
        return null;
    },
    getBoundingClientRect() {
        return { width: rootWidth };
    },
};

class ResizeObserverMock {
    constructor(callback) {
        this.callback = callback;
    }
    observe(node) {
        this.node = node;
    }
    disconnect() {
        this.node = null;
    }
}

const context = {
    console,
    document: {
        documentElement: { clientWidth: 390 },
    },
    frappe: {
        almdina: {
            orderCanEdit() {
                return orderCanEdit;
            },
        },
        ui: {
            form: {
                on(doctype, config) {
                    assert.strictEqual(doctype, "Door Cutting Order");
                    Object.assign(handlers, config);
                },
            },
        },
    },
    requestAnimationFrame(callback) {
        callback();
    },
    ResizeObserver: ResizeObserverMock,
    window: {
        innerWidth: 390,
        screen: { width: 390, height: 844 },
        addEventListener() {},
        removeEventListener() {},
    },
    AlmdinaMeasurementLifecycle: {
        registerFeature(key, owner) {
            assert.strictEqual(key, "mobile-piece-layout");
            assert.equal(typeof owner, "function");
        },
    },
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(responsiveSource, context);
vm.runInContext(source, context);

const frm = {
    fields_dict: {
        pieces_fast_entry: {
            $wrapper: { get: () => root },
        },
    },
};

const sectionClasses = new Set();

const section = {
    classList: {
        toggle(name, enabled) {
            if (enabled) sectionClasses.add(name);
            else sectionClasses.delete(name);
        },
    },
};

root.closest = (selector) => {
    if (String(selector).includes("dco-measurements-card")) return section;
    return null;
};

function resetPhoneLayout() {
    context.document.documentElement.clientWidth = 390;
    context.window.innerWidth = 390;
    context.window.screen.width = 390;
    context.window.screen.height = 844;
    rootWidth = 390;
}

orderCanEdit = true;
resetPhoneLayout();
handlers.refresh(frm);
assert(!rootClasses.has("dco-mobile-piece-cards"), "inline phone must not use card rows anymore");
assert(rootClasses.has("dco-mobile-piece-read-table"), "inline phone must use the print-like scroll table");
assert(sectionClasses.has("dco-measurements-mobile-scroll"), "measurements section must expand full width on phone");
assert(!rootClasses.has("dco-measurement-readonly-surface"), "editable phone keeps edit affordances");

orderCanEdit = false;
rootClasses.clear();
handlers.refresh(frm);
assert(rootClasses.has("dco-mobile-piece-read-table"), "read-only phone must keep the scroll table");
assert(rootClasses.has("dco-measurement-readonly-surface"), "read-only phone must hide edit chrome");

orderCanEdit = true;
context.document.documentElement.clientWidth = 700;
context.window.innerWidth = 700;
context.window.screen.width = 1366;
context.window.screen.height = 768;
rootWidth = 620;
rootClasses.clear();
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(!rootClasses.has("dco-mobile-piece-read-table"), "a narrow laptop surface must keep the desktop table");

orderCanEdit = false;
rootClasses.clear();
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(!rootClasses.has("dco-mobile-piece-read-table"), "read-only on a laptop must keep the desktop table");

orderCanEdit = true;
context.document.documentElement.clientWidth = 844;
context.window.innerWidth = 844;
context.window.screen.width = 390;
context.window.screen.height = 844;
rootWidth = 760;
rootClasses.clear();
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(rootClasses.has("dco-mobile-piece-read-table"), "a phone in landscape must use the scroll table");

orderCanEdit = true;
context.document.documentElement.clientWidth = 700;
context.window.innerWidth = 700;
context.window.screen.width = 800;
context.window.screen.height = 1280;
rootWidth = 680;
rootClasses.clear();
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(!rootClasses.has("dco-mobile-piece-read-table"), "a tablet or laptop must retain the fast table");

assert(cardCss.includes(".dco-mobile-piece-read-table .dco-fast-entry-scroll"), "mobile scroll css must enable horizontal scroll");
assert(cardCss.includes("overflow-x: auto !important"), "mobile scroll css must expose sideways scrolling");
assert(cardCss.includes("dco-measurement-readonly-surface"), "readonly mobile chrome must stay scoped");

console.log("Mobile piece-card responsive simulation passed");
