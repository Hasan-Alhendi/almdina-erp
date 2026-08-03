"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const responsiveSource = fs.readFileSync(
    "almdina_erp/public/js/responsive_device.js",
    "utf8"
);
const source = fs.readFileSync(
    "almdina_erp/public/js/door_cutting_order_mobile_cards_ux.js",
    "utf8"
);
const cardCss = fs.readFileSync(
    "almdina_erp/public/css/door_cutting_order_responsive.css",
    "utf8"
);

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
vm.runInContext(responsiveSource, context);
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
assert(cardCss.includes("grid-template-columns: repeat(6, minmax(0, 1fr))"), "phone cards must use a structured six-track grid");
assert(cardCss.includes("--dco-piece-control-height: 42px"), "phone controls must remain compact and usable");
assert(cardCss.includes("grid-template-columns: repeat(2, minmax(0, 1fr)) !important"), "edge choices must remain readable on a narrow phone");
assert(cardCss.includes(".dco-help-secondary"), "secondary desktop help must be hidden in the mobile surface");

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
