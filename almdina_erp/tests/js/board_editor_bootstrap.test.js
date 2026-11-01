"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appRoot = path.resolve(__dirname, "../..");
const benchRoot = path.resolve(appRoot, "../../..");
const assetsSource = fs.readFileSync(
    path.join(benchRoot, "apps/frappe/frappe/public/js/frappe/assets.js"),
    "utf8"
);
const foundationSource = fs.readFileSync(
    path.join(appRoot, "public/js/frontend_foundation.js"),
    "utf8"
);
const pageSource = fs.readFileSync(
    path.join(appRoot, "almdina_erp/page/board_editor/board_editor.js"),
    "utf8"
);

function createNode(tag) {
    const node = {
        tag,
        className: "",
        children: [],
        parentElement: null,
        style: {},
        innerHTML: "",
        appendChild(child) {
            child.parentElement = node;
            node.children.push(child);
            return child;
        },
        querySelector(selector) {
            const className = String(selector || "").replace(/^\./, "");
            const walk = (current) => {
                if (!current) return null;
                const classes = String(current.className || "").split(/\s+/);
                if (className && classes.includes(className)) return current;
                for (const child of current.children || []) {
                    const found = walk(child);
                    if (found) return found;
                }
                return null;
            };
            return walk(node);
        },
        closest(selector) {
            const className = String(selector || "").replace(/^\./, "");
            let current = node;
            while (current) {
                const classes = String(current.className || "").split(/\s+/);
                if (classes.includes(className)) return current;
                current = current.parentElement;
            }
            return null;
        },
        getBoundingClientRect() {
            return { top: 128, left: 0, width: 1100, height: 640 };
        },
    };
    return node;
}

function bootContext() {
    const listeners = [];
    const scriptSrcs = [];
    let resizeObservers = 0;
    const logs = [];
    const context = {
        console: {
            error(...args) { logs.push(args); },
            debug() {},
            log() {},
        },
        URL,
        setTimeout,
        clearTimeout,
        localStorage: {
            getItem() { return null; },
            setItem() {},
            removeItem() {},
        },
        document: {
            head: null,
            getElementById() { return null; },
            querySelector() { return null; },
            createElement(tag) {
                return { tagName: String(tag).toLowerCase(), src: "", href: "", rel: "", type: "", id: "" };
            },
        },
    };
    context.window = context;
    context.globalThis = context;
    context.location = {
        origin: "http://almdina.local:8000",
        hostname: "almdina.local",
    };
    context._version_number = "bootstrap-test";
    context.performance = { getEntriesByType() { return [{ type: "navigate" }]; } };
    context.ResizeObserver = function ResizeObserver() {
        resizeObservers += 1;
        this.observe = () => {};
        this.disconnect = () => {};
    };
    context.addEventListener = (eventName, handler) => {
        listeners.push({ eventName, handler });
    };
    context.removeEventListener = (eventName, handler) => {
        const index = listeners.findIndex((row) => row.eventName === eventName && row.handler === handler);
        if (index >= 0) listeners.splice(index, 1);
    };
    context.__ = (message) => message;
    context.$ = () => ({
        off() { return this; },
        on() { return this; },
    });
    context.frappe = {
        boot: { developer_mode: 1, assets_json: {} },
        pages: { "board-editor": {} },
        dom: { freeze() {}, unfreeze() {} },
        call() {},
        get_route() { return ["board-editor", "Door Cutting Order 26-00001", "PLAN-1"]; },
        utils: { escape_html: (value) => String(value == null ? "" : value) },
        ui: {
            make_app_page({ parent }) {
                const body = createNode("div");
                body.className = "page-body";
                const section = createNode("div");
                section.className = "layout-main-section";
                body.appendChild(section);
                parent.appendChild(body);
            },
        },
    };
    context.document.head = {
        appendChild(element) {
            const src = String(element.src || element.href || "");
            if (element.tagName === "script") {
                scriptSrcs.push(src);
                const file = moduleFile(src);
                if (file) vm.runInContext(fs.readFileSync(file, "utf8"), context);
            }
            if (typeof element.onload === "function") element.onload();
        },
    };
    vm.createContext(context);
    vm.runInContext(assetsSource, context);
    vm.runInContext(foundationSource, context);
    vm.runInContext(pageSource, context);
    return { context, listeners, scriptSrcs, logs, resizeObserverCount: () => resizeObservers };
}

function moduleFile(src) {
    const pathname = new URL(src, "http://almdina.local:8000").pathname;
    if (pathname.includes("/js/board_editor/")) {
        return path.join(appRoot, "public/js/board_editor", path.basename(pathname));
    }
    if (pathname.endsWith("/js/frontend_foundation.js")) {
        return path.join(appRoot, "public/js/frontend_foundation.js");
    }
    return "";
}

async function loaderRejectsVersionedRequire() {
    const { context, scriptSrcs } = bootContext();
    const asset = "/assets/almdina_erp/js/board_editor/controller.js?v=2";
    let caught = null;
    try {
        await context.frappe.require(asset);
    } catch (error) {
        caught = error;
    }
    assert.ok(caught, "frappe.require of a ?v=2 path must reject");
    assert.equal(caught.name, "TypeError");
    assert.equal(caught.message, "handler is not a function");
    assert.match(String(caught.stack), /AssetManager\.load_asset/);
    const extension = context.frappe.assets.extn(asset);
    assert.equal(extension, "v=2");
    assert.deepEqual(scriptSrcs, []);
    return caught;
}

async function pageBootstrapLoadsVersionedScripts() {
    const harness = bootContext();
    const { context, listeners, scriptSrcs } = harness;
    const wrapper = createNode("div");
    const page = context.frappe.pages["board-editor"];
    page.on_page_load(wrapper);
    await wrapper.__almdinaBoardEditorBoot;
    await Promise.resolve();

    const section = wrapper.querySelector(".layout-main-section");
    assert.ok(section);
    assert.equal(String(section.innerHTML).includes("Reload the page and try again"), false);
    assert.equal(harness.logs.length, 0);
    assert.ok(wrapper.__almdinaBoardEditorController);
    assert.equal(typeof wrapper.__almdinaBoardEditorController.open, "function");

    const versioned = scriptSrcs.filter((src) => src.includes("/js/board_editor/"));
    assert.deepEqual(versioned.map((src) => path.basename(new URL(src, "http://almdina.local:8000").pathname)), [
        "api.js",
        "history.js",
        "session_document.js",
        "distribution.js",
        "move_geometry.js",
        "snap_geometry.js",
        "rotation_geometry.js",
        "move_interaction.js",
        "rotation_interaction.js",
        "plan_display_style.js",
        "plan_edge_marks.js",
        "store.js",
        "canvas_renderer.js",
        "sidebar_renderer.js",
        "controller.js",
    ]);
    versioned.forEach((src) => {
        const url = new URL(src, "http://almdina.local:8000");
        assert.equal(url.searchParams.get("v"), "14");
        assert.equal(context.frappe.assets.extn(url.pathname), "js");
    });

    const resizeListeners = listeners.filter((row) => row.eventName === "resize");
    assert.equal(resizeListeners.length, 1);
    page.on_page_show(wrapper);
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(listeners.filter((row) => row.eventName === "resize").length, 1);
    assert.equal(harness.resizeObserverCount(), 0);
    assert.equal(String(section.innerHTML).includes("Reload the page and try again"), false);
}

async function main() {
    const failure = await loaderRejectsVersionedRequire();
    assert.match(failure.stack, /load_asset/);
    await pageBootstrapLoadsVersionedScripts();
    console.log("board editor bootstrap contract passed");
    console.log(`loader failure: ${failure.name}: ${failure.message}`);
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
