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
let rootWidth = 980;

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
        documentElement: { clientWidth: 980 },
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
        innerWidth: 980,
        screen: { width: 390 },
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

context.document.documentElement.clientWidth = 1280;
context.window.innerWidth = 1280;
context.window.screen.width = 1280;
rootWidth = 1100;
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(!rootClasses.has("dco-mobile-piece-cards"), "a wide order surface must keep the fast table");

rootWidth = 700;
context.window.AlmdinaMobilePieceCardsUX.apply(frm);
assert(rootClasses.has("dco-mobile-piece-cards"), "a narrow embedded form must use cards");

console.log("Mobile piece-card responsive simulation passed");
