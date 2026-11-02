"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const panelPath = path.join(
    root,
    "public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"
);
const pagePath = path.join(
    root,
    "almdina_erp/page/cnc_sheet_settings/cnc_sheet_settings.js"
);
const cssPath = path.join(root, "public/css/door_cutting_order_operational_files.css");
const translationsPath = path.join(root, "translations/ar.csv");

const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const pageSource = fs.readFileSync(pagePath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

assert.equal(ux.SHEET_PAGE_ROUTE, "cnc-sheet-settings");
assert.ok(typeof ux.openSheetSettingsTab === "function");
assert.ok(typeof ux.mountSheetSettingsPage === "function");
assert.ok(typeof ux.sheetSettingsUrl === "function");
assert.ok(panel.includes("openSheetSettingsTab("));
assert.ok(!panel.includes("openSheetDialog("));
assert.ok(!panel.includes("dco-operational-sheet-dialog"));
assert.ok(pageSource.includes('PAGE_ROUTE = "cnc-sheet-settings"'));
assert.ok(pageSource.includes("frappe.pages[PAGE_ROUTE]"));
assert.ok(pageSource.includes("mountSheetSettingsPage"));
assert.ok(css.includes(".dco-cnc-sheet-page"));
assert.ok(css.includes("font-size: 14px"));
assert.ok(translations.includes("العودة إلى الطلب"));
assert.ok(translations.includes("إعدادات لوح CNC"));

assert.equal(
    ux.sheetSettingsUrl("DCO-1", 2),
    "/desk/cnc-sheet-settings/DCO-1/2"
);

const opened = [];
windowObject.open = (url, target) => {
    opened.push({ url, target });
    return { closed: false };
};
const url = ux.openSheetSettingsTab("DCO-9", 3);
assert.equal(url, "/desk/cnc-sheet-settings/DCO-9/3");
assert.equal(opened.length, 1);
assert.equal(opened[0].target, "_blank");
assert.equal(opened[0].url, url);

function makeProgram() {
    return {
        sheet_width_mm: 2440,
        sheet_length_mm: 1220,
        geometry_ready: true,
        ready: true,
        issues: [],
        operations: [
            {
                operation_key: "cut_path",
                toolpaths: [
                    {
                        path_key: "cut_path:a",
                        operation_key: "cut_path",
                        closed: true,
                        ready: true,
                        issues: [],
                        points: [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]],
                        motions: [
                            { kind: "travel", x_mm: 0, y_mm: 0, depth_mm: null },
                            { kind: "plunge", x_mm: 0, y_mm: 0, depth_mm: 6 },
                            { kind: "cut", x_mm: 100, y_mm: 0, depth_mm: 6 },
                            { kind: "cut", x_mm: 100, y_mm: 100, depth_mm: 6 },
                            { kind: "cut", x_mm: 0, y_mm: 100, depth_mm: 6 },
                            { kind: "cut", x_mm: 0, y_mm: 0, depth_mm: 6 },
                            { kind: "retract", x_mm: 0, y_mm: 0, depth_mm: null },
                            { kind: "travel", x_mm: 0, y_mm: 0, depth_mm: null },
                            { kind: "plunge", x_mm: 0, y_mm: 0, depth_mm: 12 },
                            { kind: "cut", x_mm: 100, y_mm: 0, depth_mm: 12 },
                            { kind: "cut", x_mm: 100, y_mm: 100, depth_mm: 12 },
                            { kind: "cut", x_mm: 0, y_mm: 100, depth_mm: 12 },
                            { kind: "cut", x_mm: 0, y_mm: 0, depth_mm: 12 },
                            { kind: "retract", x_mm: 0, y_mm: 0, depth_mm: null },
                        ],
                    },
                ],
            },
        ],
    };
}

function createDocumentDom() {
    const nodesById = new Map();
    function register(node) {
        if (node && node.id) nodesById.set(node.id, node);
        (node.children || []).forEach(register);
    }
    function parseSvgFragment(html) {
        const markerMatches = [...html.matchAll(/<marker\b([^>]*)>/g)];
        const markers = markerMatches.map(match => {
            const attrs = match[1];
            const id = ((attrs.match(/\bid="([^"]+)"/) || [])[1]) || "";
            return { id, tagName: "marker", attrs };
        });
        const refs = [...html.matchAll(/marker-end="url\(#([^"]+)\)"/g)].map(match => match[1]);
        markers.forEach(marker => {
            if (!nodesById.has(marker.id)) nodesById.set(marker.id, marker);
        });
        return { markers, refs };
    }
    return {
        getElementById(id) {
            return nodesById.get(id) || null;
        },
        paint(html) {
            return parseSvgFragment(html);
        },
        clear() {
            nodesById.clear();
        },
        ids() {
            return Array.from(nodesById.keys());
        },
    };
}

const program = makeProgram();
const staleDom = createDocumentDom();

// Prove the old fixed-id collision: second paint keeps resolving to the first marker.
const fixedA = `<defs><marker id="cnc-cut-arrow-1"></marker></defs><polyline marker-end="url(#cnc-cut-arrow-1)"/>`;
const fixedB = `<defs><marker id="cnc-cut-arrow-1"></marker></defs><polyline marker-end="url(#cnc-cut-arrow-1)"/>`;
staleDom.paint(fixedA);
staleDom.paint(fixedB);
assert.equal(staleDom.ids().filter(id => id === "cnc-cut-arrow-1").length, 1);
assert.equal(staleDom.getElementById("cnc-cut-arrow-1") !== null, true);

const liveDom = createDocumentDom();
const scopes = [];
for (let index = 0; index < 10; index += 1) {
    const scope = ux.nextCutPreviewScope();
    scopes.push(scope);
    const markup = ux.cutPathPreviewMarkup(program, {
        markerScope: scope,
        layout: "page",
        selectedPathKey: "cut_path:a",
    });
    const painted = liveDom.paint(markup);
    assert.ok(painted.markers.length >= 2);
    painted.refs.forEach(ref => {
        assert.ok(ref.startsWith(`${scope}-arrow-`), `ref ${ref} must stay inside scope ${scope}`);
        assert.equal(liveDom.getElementById(ref) !== null, true, `missing marker for ${ref}`);
    });
    assert.ok(markup.includes("dco-cnc-cut-preview__badge"));
    assert.ok(markup.includes("font-size") || css.includes("font-size: 14px"));
    assert.ok(markup.includes("1,2") || markup.includes(">1,2<"));
}

const uniqueScopes = new Set(scopes);
assert.equal(uniqueScopes.size, 10, "each paint must allocate a unique marker scope");
const allIds = liveDom.ids();
assert.equal(allIds.length, new Set(allIds).size, "marker ids across repeated paints must remain unique in the DOM");
assert.ok(!allIds.includes("cnc-cut-arrow-1"));

const host = { innerHTML: "", getAttribute() { return "page"; } };
for (let index = 0; index < 10; index += 1) {
    ux.paintCutPathPreview(host, {
        status: "ready",
        program,
        selectedPathKey: "cut_path:a",
        layout: "page",
    });
    const ids = ux.collectMarkerIdsFromMarkup(host.innerHTML);
    assert.ok(ids.length >= 2);
    assert.equal(ids.length, new Set(ids).size);
    ids.forEach(id => {
        assert.ok(host.innerHTML.includes(`marker-end="url(#${id})"`));
    });
}

assert.ok(panel.includes("data-preview-layout"));
assert.ok(panel.includes("mountSheetSettingsPage("));
assert.ok(panel.includes("Back to the order"));

console.log("dco_operational_files_sheet_page.test.js passed");
