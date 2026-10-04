"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_save_render_performance_ux.js"
    ),
    "utf8"
);

function parseShellOrderName(html) {
    const match = String(html || "").match(/data-order-name="([^"]+)"/);
    return match ? match[1] : "";
}

function createElement(tagName = "div") {
    const children = [];
    const classSet = new Set();
    const dataset = {};
    let innerHTML = "";
    const node = {
        tagName: String(tagName).toUpperCase(),
        children,
        parentNode: null,
        dataset,
        style: {},
        get className() {
            return [...classSet].join(" ");
        },
        set className(value) {
            classSet.clear();
            String(value || "")
                .split(/\s+/)
                .filter(Boolean)
                .forEach((token) => classSet.add(token));
        },
        classList: {
            add(...tokens) {
                tokens.forEach((token) => classSet.add(token));
            },
            contains(token) {
                return classSet.has(token);
            },
        },
        get innerHTML() {
            return innerHTML;
        },
        set innerHTML(value) {
            innerHTML = String(value || "");
            if (this.tagName === "TEMPLATE") {
                this.content._html = innerHTML;
            }
            if (this.tagName !== "TEMPLATE") {
                this._shell = null;
                if (innerHTML.includes("dco-cost-shell")) {
                    this._shell = {
                        dataset: { orderName: parseShellOrderName(innerHTML) },
                        querySelectorAll() {
                            return [];
                        },
                    };
                }
            }
        },
        appendChild(child) {
            if (child.parentNode && typeof child.parentNode.removeChild === "function") {
                child.parentNode.removeChild(child);
            }
            child.parentNode = this;
            children.push(child);
            return child;
        },
        removeChild(child) {
            const index = children.indexOf(child);
            if (index >= 0) children.splice(index, 1);
            child.parentNode = null;
            return child;
        },
        closest(selector) {
            let current = this;
            while (current) {
                if (selector === ".tab-pane" && current.classList.contains("tab-pane")) {
                    return current;
                }
                current = current.parentNode;
            }
            return null;
        },
        querySelector(selector) {
            if (selector === ".dco-cost-shell") {
                if (this.tagName === "TEMPLATE" || this._isTemplateContent) {
                    const html = this._html || "";
                    if (!html.includes("dco-cost-shell")) return null;
                    return {
                        dataset: { orderName: parseShellOrderName(html) },
                        querySelectorAll() {
                            return [];
                        },
                    };
                }
                return this._shell || null;
            }
            return null;
        },
        querySelectorAll() {
            return [];
        },
        addEventListener() {},
        setAttribute() {},
        getAttribute() {
            return null;
        },
    };

    if (node.tagName === "TEMPLATE") {
        node.content = {
            _isTemplateContent: true,
            _html: "",
            querySelector(selector) {
                return node.querySelector.call(this, selector);
            },
            querySelectorAll() {
                return [];
            },
        };
    }
    return node;
}

function loadModule() {
    const formHandlers = {};
    const renderCalls = [];
    const rafQueue = [];

    const pane = createElement("div");
    pane.className = "tab-pane";
    const htmlRoot = createElement("div");
    htmlRoot.innerHTML = (
        '<div class="dco-cost-shell" data-order-name="DCO-DEFER-1">'
        + '<div class="dco-cost-empty">loading</div>'
        + "</div>"
    );
    pane.appendChild(htmlRoot);

    const wrapper = {
        0: htmlRoot,
        length: 1,
        html(value) {
            if (typeof value === "string") htmlRoot.innerHTML = value;
            return this;
        },
    };

    const formRoot = createElement("div");
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-DEFER-1", pieces: [] },
        wrapper: formRoot,
        fields_dict: {
            pieces_fast_entry: null,
            order_cost_invoice_html: {
                $wrapper: wrapper,
                wrapper,
            },
        },
        _dco_cost_render_deferred: false,
    };

    const fakeWindow = {
        AlmdinaOrderCostUX: {
            render(target) {
                renderCalls.push(target);
                wrapper.html(
                    '<div class="dco-cost-shell" data-order-name="DCO-DEFER-1">'
                    + '<div class="dco-cost-invoice-section"><h4>تفاصيل عرض السعر</h4></div>'
                    + "</div>"
                );
                return true;
            },
        },
        requestAnimationFrame(callback) {
            rafQueue.push(callback);
            return rafQueue.length;
        },
    };

    const context = vm.createContext({
        window: fakeWindow,
        document: {
            createElement,
            body: createElement("body"),
        },
        console,
        Object,
        Array,
        Boolean,
        String,
        Number,
        CSS: {
            escape(value) {
                return String(value).replace(/["\\]/g, "\\$&");
            },
        },
        frappe: {
            ui: {
                form: {
                    on(_doctype, handlers) {
                        Object.assign(formHandlers, handlers);
                    },
                },
            },
        },
    });

    vm.runInContext(source, context, {
        filename: "door_cutting_order_save_render_performance_ux.js",
    });

    return {
        frm,
        pane,
        wrapper,
        htmlRoot,
        formHandlers,
        renderCalls,
        rafQueue,
        api: fakeWindow.AlmdinaSaveRenderPerformanceUX,
        flushFrames() {
            const pending = rafQueue.splice(0, rafQueue.length);
            pending.forEach((callback) => callback());
        },
    };
}

function verifyDeferredPaintFlushesOnTabChange() {
    const env = loadModule();
    assert.ok(env.api, "save-render performance UX must expose a flush API");
    assert.equal(typeof env.api.flushDeferredCostRender, "function");
    assert.equal(typeof env.formHandlers.on_tab_change, "function");

    env.api.install(env.frm);

    assert.equal(env.api.costTabIsActive(env.frm), false);
    env.wrapper.html(
        '<div class="dco-cost-shell" data-order-name="DCO-DEFER-1">'
        + '<div class="dco-cost-invoice-section"><h4>تفاصيل عرض السعر</h4></div>'
        + "</div>"
    );
    assert.equal(env.frm._dco_cost_render_deferred, true);
    assert.match(env.htmlRoot.innerHTML, /dco-cost-empty/);
    assert.equal(env.renderCalls.length, 0);

    env.pane.classList.add("active", "show");
    env.formHandlers.on_tab_change(env.frm);
    assert.equal(env.rafQueue.length >= 1, true, "on_tab_change must schedule a deferred Cost flush");
    env.flushFrames();

    assert.equal(env.renderCalls.length, 1, "deferred Cost paint must flush without requiring a tab click");
    assert.equal(env.frm._dco_cost_render_deferred, false);
    assert.match(env.htmlRoot.innerHTML, /تفاصيل عرض السعر/);
    assert.doesNotMatch(env.htmlRoot.innerHTML, /dco-cost-empty/);
}

function verifyFlushIsNoopWhileCostTabInactive() {
    const env = loadModule();
    env.api.install(env.frm);
    env.frm._dco_cost_render_deferred = true;

    assert.equal(env.api.flushDeferredCostRender(env.frm), false);
    assert.equal(env.renderCalls.length, 0);
    assert.equal(env.frm._dco_cost_render_deferred, true);
}

verifyDeferredPaintFlushesOnTabChange();
verifyFlushIsNoopWhileCostTabInactive();
console.log("Cost deferred render flush simulation passed");
