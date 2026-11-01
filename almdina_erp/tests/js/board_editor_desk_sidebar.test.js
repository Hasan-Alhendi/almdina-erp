"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appRoot = path.resolve(__dirname, "../..");
const pageSource = fs.readFileSync(
    path.join(appRoot, "almdina_erp/page/board_editor/board_editor.js"),
    "utf8"
);
const cssSource = fs.readFileSync(
    path.join(appRoot, "public/css/board_editor.css"),
    "utf8"
);

function entityFromRoute(route) {
    switch (route.length) {
        case 1:
            return route[0];
        case 3:
            return route[0] === "Workspaces" && route[1] === "private" ? route[2] : route[1];
        case 2:
            return route[1];
        default:
            return route[1];
    }
}

function getWorkspaceSidebars(allSidebarItems, linkTo) {
    const sidebars = [];
    Object.entries(allSidebarItems).forEach(([name, sidebar]) => {
        const { items, label } = sidebar;
        (items || []).forEach((item) => {
            if (item.link_to === linkTo) sidebars.push(label || name);
        });
    });
    return sidebars;
}

const workspaceSidebars = {
    "almdina erp": {
        label: "Almdina ERP",
        app: "almdina_erp",
        items: [
            { link_to: "Door Cutting Order", label: "طلبات قص الدرف", type: "DocType" },
            { link_to: "factory-master-data", label: "إدارة مسارات الإنتاج", type: "Page" },
            { link_to: "Customer", label: "الزبائن", type: "DocType" },
        ],
    },
};

const boardRoute = ["board-editor", "26-00001", "PLAN-1"];
const boardEntity = entityFromRoute(boardRoute);
assert.equal(boardEntity, "26-00001");
assert.deepEqual(getWorkspaceSidebars(workspaceSidebars, boardEntity), []);
assert.deepEqual(getWorkspaceSidebars(workspaceSidebars, "board-editor"), []);
assert.deepEqual(getWorkspaceSidebars(workspaceSidebars, "factory-master-data"), ["Almdina ERP"]);

function loadPageHelpers() {
    const calls = [];
    const sidebarItems = { children: [] };
    const context = {
        console,
        URL,
        document: {
            querySelector(selector) {
                if (selector === ".body-sidebar-top .sidebar-items") return sidebarItems;
                return null;
            },
        },
        window: {},
        locals: {
            Page: {
                "board-editor": { module: "Almdina ERP", name: "board-editor", title: "Board layout editor" },
            },
        },
        frappe: {
            pages: { "board-editor": {} },
            boot: { developer_mode: 1, assets_json: {} },
            utils: { escape_html: (value) => String(value == null ? "" : value) },
            ui: { make_app_page() {} },
            require() { return Promise.resolve(); },
            assets: { load_asset() { return Promise.resolve(); } },
            get_route() { return boardRoute; },
            app: {
                sidebar: {
                    sidebar_title: null,
                    show_sidebar_for_module(moduleName) {
                        calls.push(["show_sidebar_for_module", moduleName]);
                        this.sidebar_title = moduleName;
                        sidebarItems.children = [
                            { classList: { contains() { return false; } } },
                            { classList: { contains() { return false; } } },
                        ];
                        sidebarItems.querySelectorAll = () => sidebarItems.children;
                    },
                    setup(moduleName) {
                        calls.push(["setup", moduleName]);
                    },
                },
            },
        },
        __: (message) => message,
        $() {
            return { off() { return this; }, on() { return this; } };
        },
    };
    sidebarItems.querySelectorAll = () => sidebarItems.children;
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(pageSource, context);
    return { context, calls, sidebarItems };
}

const first = loadPageHelpers();
assert.equal(first.context.AlmdinaBoardEditor.pageModule(), "Almdina ERP");
const cold = first.context.AlmdinaBoardEditor.ensureDeskNavigationSidebar();
assert.equal(cold.applied, true);
assert.equal(cold.reason, "module-sidebar");
assert.equal(cold.moduleName, "Almdina ERP");
assert.deepEqual(first.calls, [["show_sidebar_for_module", "Almdina ERP"]]);
assert.ok(cold.count >= 1);

const warm = first.context.AlmdinaBoardEditor.ensureDeskNavigationSidebar();
assert.equal(warm.applied, false);
assert.equal(warm.reason, "already-populated");
assert.deepEqual(first.calls, [["show_sidebar_for_module", "Almdina ERP"]]);

assert.doesNotMatch(cssSource, /(^|\s)(\.body-sidebar|\.desk-sidebar|\.sidebar-items)(\s|\{|,|:)/);
assert.doesNotMatch(cssSource, /body\.ald-/);
assert.match(pageSource, /ensureDeskNavigationSidebar/);
assert.match(pageSource, /show_sidebar_for_module/);
assert.doesNotMatch(pageSource, /body-sidebar-top[\s\S]{0,80}innerHTML/);

console.log("board editor desk sidebar contract passed");
