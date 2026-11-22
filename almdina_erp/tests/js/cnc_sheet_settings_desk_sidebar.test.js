"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appRoot = path.resolve(__dirname, "../..");
const pageSource = fs.readFileSync(
    path.join(appRoot, "almdina_erp/page/cnc_sheet_settings/cnc_sheet_settings.js"),
    "utf8"
);
const cssSource = fs.readFileSync(
    path.join(appRoot, "public/css/door_cutting_order_operational_files.css"),
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

const sheetRoute = ["cnc-sheet-settings", "26-00024", "2"];
assert.equal(entityFromRoute(sheetRoute), "26-00024");
assert.deepEqual(getWorkspaceSidebars(workspaceSidebars, "26-00024"), []);
assert.deepEqual(getWorkspaceSidebars(workspaceSidebars, "cnc-sheet-settings"), []);
assert.deepEqual(getWorkspaceSidebars(workspaceSidebars, "Door Cutting Order"), ["Almdina ERP"]);

function loadPageHelpers() {
    const calls = [];
    const sidebarItems = { children: [] };
    const context = {
        console,
        document: {
            body: { classList: { add() {}, remove() {} } },
            querySelector(selector) {
                if (selector === ".body-sidebar-top .sidebar-items") return sidebarItems;
                return null;
            },
        },
        window: {},
        locals: {
            Page: {
                "cnc-sheet-settings": { module: "Almdina ERP", name: "cnc-sheet-settings" },
            },
        },
        frappe: {
            pages: { "cnc-sheet-settings": {} },
            utils: { escape_html: (value) => String(value == null ? "" : value) },
            ui: { make_app_page() {} },
            require() { return Promise.resolve(); },
            get_route() { return sheetRoute; },
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
    return { context, calls };
}

const first = loadPageHelpers();
assert.equal(first.context.AlmdinaCncSheetSettings.pageModule(), "Almdina ERP");
const cold = first.context.AlmdinaCncSheetSettings.ensureDeskNavigationSidebar();
assert.equal(cold.applied, true);
assert.equal(cold.reason, "module-sidebar");
assert.equal(cold.moduleName, "Almdina ERP");
assert.deepEqual(first.calls, [["show_sidebar_for_module", "Almdina ERP"]]);
assert.ok(cold.count >= 1);

const warm = first.context.AlmdinaCncSheetSettings.ensureDeskNavigationSidebar();
assert.equal(warm.applied, false);
assert.equal(warm.reason, "already-populated");
assert.deepEqual(first.calls, [["show_sidebar_for_module", "Almdina ERP"]]);

assert.match(pageSource, /ensureDeskNavigationSidebar\(\)/);
assert.match(pageSource, /show_sidebar_for_module/);
assert.doesNotMatch(pageSource, /body-sidebar-top[\s\S]{0,80}innerHTML/);
assert.doesNotMatch(cssSource, /(^|\s)(\.body-sidebar|\.desk-sidebar|\.sidebar-items)(\s|\{|,|:)/);

console.log("cnc sheet settings desk sidebar contract passed");
