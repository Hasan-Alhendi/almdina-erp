"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(
    "almdina_erp/public/js/door_cutting_order_mobile_cards_ux.js",
    "utf8"
);

const installed = new Map();
const handlers = {};
const rootClasses = new Set();
let rootWidth = 390;

const root = {
    classList: {
        toggle(name, enabled) {
            if (enabled) rootClasses.add(name);
            else rootClasses.delete(name);
        },
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
        head: {
            appendChild(node) {
                installed.set(node.id, node);
            },
        },
        createElement() {
            return { id: "", textContent: "" };
        },
        getElementById(id) {
            return installed.get(id) || null;
        },
    },
    frappe: {
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
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(source, context);

const frm = {
    fields_dict: {
        pieces_fast_entry: {
            $wrapper: { get: () => root },
        },
    },
};

handlers.refresh(frm);
assert(rootClasses.has("dco-mobile-piece-cards"), "a phone screen must force card rows");
assert(installed.has("dco-mobile-piece-cards-css"), "card CSS must be installed from doctype source");
const cardCss = installed.get("dco-mobile-piece-cards-css").textContent;
assert(cardCss.includes("grid-template-columns:repeat(6,minmax(0,1fr))"), "phone cards must keep a compact six-track grid");
assert(cardCss.includes("--dco-compact-control-height:38px"), "phone controls must use the compact height");
assert(!cardCss.includes("grid-template-columns:1fr;\n            }\n            .dco-mobile-piece-cards .dco-fast-table tbody td"), "phone cards must not collapse every field into one long column");

context.document.documentElement.clientWidth = 700;
context.window.innerWidth = 700;
context.window.screen.width = 1366;
context.window.screen.height = 768;
rootWidth = 620;
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(!rootClasses.has("dco-mobile-piece-cards"), "a narrow laptop surface must still keep the fast table");

context.document.documentElement.clientWidth = 844;
context.window.innerWidth = 844;
context.window.screen.width = 390;
context.window.screen.height = 844;
rootWidth = 760;
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(rootClasses.has("dco-mobile-piece-cards"), "a phone in landscape must still use compact cards");

context.document.documentElement.clientWidth = 700;
context.window.innerWidth = 700;
context.window.screen.width = 800;
context.window.screen.height = 1280;
rootWidth = 680;
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(!rootClasses.has("dco-mobile-piece-cards"), "a tablet or laptop must retain the fast table");

console.log("Mobile piece-card responsive simulation passed");
