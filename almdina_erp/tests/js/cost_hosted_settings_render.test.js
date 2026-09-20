"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_presenter_adapter.js"
    ),
    "utf8"
);

function createHostedCostDom() {
    const htmlNode = {
        children: [],
        parentNode: null,
        contains(node) {
            let current = node;
            while (current) {
                if (current === this) return true;
                current = current.parentNode;
            }
            return false;
        },
        removeChild(child) {
            this.children = this.children.filter((item) => item !== child);
            child.parentNode = null;
            return child;
        },
    };
    const parent = {
        children: [htmlNode],
        insertBefore(node, reference) {
            if (node.parentNode && typeof node.parentNode.removeChild === "function") {
                node.parentNode.removeChild(node);
            }
            node.parentNode = this;
            const index = this.children.indexOf(reference);
            this.children.splice(index < 0 ? this.children.length : index, 0, node);
            return node;
        },
    };
    htmlNode.parentNode = parent;

    function makeField(fieldname) {
        const node = {
            fieldname,
            parentNode: htmlNode,
            closest(selector) {
                return selector === ".form-group" ? this : null;
            },
        };
        htmlNode.children.push(node);
        return {
            df: { fieldname },
            $wrapper: {
                0: node,
                length: 1,
                get() { return node; },
                closest() { return { 0: node, length: 1 }; },
            },
            node,
        };
    }

    const htmlReplaces = [];
    const htmlWrapper = {
        0: htmlNode,
        length: 1,
        get() { return htmlNode; },
        html(value) {
            htmlReplaces.push(String(value || ""));
            htmlNode.children.slice().forEach((child) => {
                child.parentNode = null;
            });
            htmlNode.children = [];
            return this;
        },
        find() {
            return { first() { return { length: 0 }; }, length: 0 };
        },
    };

    return { parent, htmlNode, htmlWrapper, htmlReplaces, makeField };
}

function loadAdapter(options = {}) {
    const listeners = new Map();
    const enhanceCalls = [];
    const legacyRenders = [];
    const dom = createHostedCostDom();
    const board = dom.makeField("board_rate_usd");
    const cutting = dom.makeField("cutting_cost_per_board_usd");
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-HOSTED-SETTINGS", pieces: [] },
        fields_dict: {
            order_cost_invoice_html: { $wrapper: dom.htmlWrapper },
            board_rate_usd: board,
            cutting_cost_per_board_usd: cutting,
        },
    };
    const fakeWindow = {
        cur_frm: frm,
        addEventListener(name, callback) {
            listeners.set(name, callback);
        },
        AlmdinaCostWorkspaceState: {
            snapshot() {
                return options.snapshot || { status: "loading", data: null };
            },
            canView() {
                return true;
            },
        },
        AlmdinaCostPageLayoutUX: {
            enhance(target) {
                enhanceCalls.push(target);
                return true;
            },
        },
        AlmdinaOrderCostUX: {
            render() {
                legacyRenders.push("render");
                dom.htmlWrapper.html("<div class=\"dco-cost-shell\">ready</div>");
                return true;
            },
            refreshInvoiceSection() {
                legacyRenders.push("refreshInvoiceSection");
                return true;
            },
            invoiceLines() { return []; },
            invoiceTotal() { return 0; },
            quoteTotal() { return 0; },
        },
        AlmdinaCostPermissionsUX: {
            reconcileRenderedActions() { return true; },
        },
    };
    const context = vm.createContext({
        window: fakeWindow,
        console,
        Object,
        Array,
        Map,
        Boolean,
        Promise,
        String,
        Number,
        __: value => value,
        frappe: {
            utils: {
                escape_html(value) { return String(value); },
            },
        },
    });
    vm.runInContext(source, context, {
        filename: "door_cutting_order_cost_workspace_presenter_adapter.js",
    });
    return {
        frm,
        board,
        cutting,
        dom,
        enhanceCalls,
        legacyRenders,
        presenter: fakeWindow.AlmdinaOrderCostUX,
    };
}

function verifyPendingRenderParksHostedNativeFields() {
    const env = loadAdapter({ snapshot: { status: "loading", data: null } });
    assert.equal(env.dom.htmlNode.contains(env.board.node), true);

    env.presenter.render(env.frm);

    assert.equal(env.legacyRenders.length, 0, "a pending Cost paint must not call the ready presenter");
    assert.ok(env.dom.htmlReplaces.length >= 1, "pending paint still replaces the HTML shell");
    assert.equal(
        env.board.node.parentNode,
        env.dom.parent,
        "native board rate control must survive the HTML replace"
    );
    assert.equal(
        env.cutting.node.parentNode,
        env.dom.parent,
        "native cutting rate control must survive the HTML replace"
    );
    assert.equal(env.enhanceCalls.length, 1, "pending paint must restore the cost settings accordion");
}

function verifyReadyRenderAlsoParksHostedNativeFields() {
    const env = loadAdapter({
        snapshot: {
            status: "ready",
            data: { order: { board_rate_usd: 10, cutting_cost_per_board_usd: 2 }, pieces: [] },
        },
    });

    env.presenter.render(env.frm);

    assert.ok(env.legacyRenders.includes("render"));
    assert.equal(env.board.node.parentNode, env.dom.parent);
    assert.equal(env.cutting.node.parentNode, env.dom.parent);
    assert.ok(env.enhanceCalls.length >= 1);
}

verifyPendingRenderParksHostedNativeFields();
verifyReadyRenderAlsoParksHostedNativeFields();
console.log("Cost hosted settings render simulation passed");
