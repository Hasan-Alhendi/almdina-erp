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
assert.ok(pageSource.includes('"/assets/almdina_erp/js/cnc/artcam_machining_ux.js"'));
assert.ok(pageSource.includes('"/assets/almdina_erp/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"'));
assert.equal(pageSource.includes("artcam_machining_ux.js?"), false);
assert.equal(pageSource.includes("door_cutting_order_operational_files_ux.js?"), false);
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

function motionChain(points, depth, closed) {
    const start = points[0];
    const motions = [
        { kind: "travel", x_mm: start[0], y_mm: start[1], depth_mm: null },
        { kind: "plunge", x_mm: start[0], y_mm: start[1], depth_mm: depth },
    ];
    points.slice(1).forEach(point => {
        motions.push({ kind: "cut", x_mm: point[0], y_mm: point[1], depth_mm: depth });
    });
    if (closed) {
        motions.push({ kind: "cut", x_mm: start[0], y_mm: start[1], depth_mm: depth });
    }
    const end = closed ? start : points[points.length - 1];
    motions.push({ kind: "retract", x_mm: end[0], y_mm: end[1], depth_mm: null });
    return motions;
}

function makeProgram() {
    const cutPoints = [[0, 0], [100, 0], [100, 100], [0, 100]];
    return {
        sheet_width_mm: 2440,
        sheet_length_mm: 1220,
        geometry_ready: true,
        ready: true,
        issues: [],
        operations: [
            {
                operation_key: "liner",
                toolpaths: [{
                    path_key: "liner:a",
                    operation_key: "liner",
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[10, 10], [40, 10]],
                    motions: motionChain([[10, 10], [40, 10]], 3, false),
                }],
            },
            {
                operation_key: "recessed_handle_cutout",
                toolpaths: [{
                    path_key: "recessed_handle_cutout:a",
                    operation_key: "recessed_handle_cutout",
                    closed: true,
                    ready: true,
                    issues: [],
                    points: [[50, 50], [70, 50], [70, 70], [50, 70]],
                    motions: motionChain([[50, 50], [70, 50], [70, 70], [50, 70]], 4, true),
                }],
            },
            {
                operation_key: "back_groove",
                toolpaths: [{
                    path_key: "back_groove:a",
                    operation_key: "back_groove",
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[20, 80], [90, 80]],
                    motions: motionChain([[20, 80], [90, 80]], 2, false),
                }],
            },
            {
                operation_key: "cut_path",
                toolpaths: [{
                    path_key: "cut_path:a",
                    operation_key: "cut_path",
                    closed: true,
                    ready: true,
                    issues: [],
                    points: [...cutPoints, cutPoints[0]],
                    motions: [
                        ...motionChain(cutPoints, 6, true),
                        ...motionChain(cutPoints, 12, true),
                    ],
                }],
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

assert.equal(ux.CUT_PREVIEW_ZOOM.MIN, 1);
assert.equal(ux.CUT_PREVIEW_ZOOM.INITIAL, 1);
assert.equal(ux.CUT_PREVIEW_ZOOM.MAX, 16);
assert.equal(ux.CUT_PREVIEW_ZOOM.STEP, 0.5);
assert.equal(ux.clampCutPreviewZoom(0.1), 1);
assert.equal(ux.clampCutPreviewZoom(20), 16);
assert.equal(ux.PROGRAM_COLORS.cut_path, "#C62828");
assert.equal(ux.PROGRAM_COLORS.liner, "#C62828");
assert.equal(ux.PROGRAM_COLORS.recessed_handle_cutout, "#C62828");
assert.equal(ux.PROGRAM_COLORS.back_groove, "#C62828");
assert.equal(ux.PROGRAM_COLORS.sheet_perimeter, "#C62828");
assert.ok(css.includes("padding-inline: clamp("));
assert.ok(css.includes("overflow-x: hidden"));
assert.ok(!/dco-cnc-sheet-page \.dco-operational-sheet__settings \{\s*max-block-size: calc\(100vh - 11rem\);\s*overflow: auto;/.test(css));

const program = makeProgram();
const allExecutions = ux.collectCutExecutions(program);
assert.equal(allExecutions.length, 5);
assert.deepEqual(
    allExecutions.map(item => item.operation_key),
    ["liner", "recessed_handle_cutout", "back_groove", "cut_path", "cut_path"]
);
assert.ok(!allExecutions.some(item => !Array.isArray(item.points) || item.points.length < 2));

const colored = ux.cutPathPreviewMarkup(program, {
    markerScope: "cnc-multi",
    layout: "page",
    zoom: ux.CUT_PREVIEW_ZOOM.INITIAL,
});
assert.ok(!colored.includes("--cut-zoom:"));
assert.ok(!colored.includes("dco-cnc-cut-preview__legend"));
assert.ok(!colored.includes("data-cut-layer"));
assert.ok(colored.includes("max-inline-size:390px"));
assert.ok(colored.includes(ux.PROGRAM_COLORS.liner));
assert.ok(colored.includes(ux.PROGRAM_COLORS.recessed_handle_cutout));
assert.ok(colored.includes(ux.PROGRAM_COLORS.back_groove));
assert.ok(colored.includes(ux.PROGRAM_COLORS.cut_path));
assert.ok(colored.includes('data-operation-key="liner"'));
assert.ok(colored.includes('data-operation-key="back_groove"'));

const hiddenLiner = ux.cutPathPreviewMarkup(program, {
    markerScope: "cnc-hidden",
    layout: "page",
    hiddenOperations: ["liner"],
});
assert.ok(!hiddenLiner.includes('data-operation-key="liner"') || hiddenLiner.includes('data-cut-layer="liner"'));
assert.ok(!hiddenLiner.includes('data-execution-path="liner:a"'));
assert.ok(!hiddenLiner.includes('data-operation-key="liner"') || hiddenLiner.includes('data-cut-layer="liner"'));
assert.ok(hiddenLiner.includes('data-execution-path="cut_path:a"'));
assert.ok(hiddenLiner.includes("data-execution-path-id="));

const zoomHost = {
    innerHTML: "",
    setAttribute() {},
    removeAttribute() {},
    getAttribute() { return "page"; },
    querySelector(selector) {
        if (selector === "[data-cut-stage]") {
            const match = this.innerHTML.match(/data-cut-stage[^>]*style="([^"]*)"/);
            const styleText = (match && match[1]) || "";
            const props = {};
            styleText.split(";").forEach(part => {
                const [key, value] = part.split(":");
                if (key && value) props[key.trim()] = value.trim();
            });
            return {
                style: {
                    getPropertyValue(name) { return props[name] || ""; },
                    setProperty(name, value) { props[name] = String(value); },
                    transform: "",
                },
            };
        }
        if (selector === "[data-cut-viewport]") {
            return {
                classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
                getBoundingClientRect() { return { width: 800, height: 400 }; },
                addEventListener() {},
                setPointerCapture() {},
            };
        }
        if (selector === '[data-cut-zoom="out"]' || selector === '[data-cut-zoom="in"]') {
            return { disabled: false, addEventListener() {} };
        }
        return null;
    },
    querySelectorAll(selector) {
        if (selector === "[data-cut-zoom]" || selector === "[data-cut-layer]") return [];
        return [];
    },
};
ux.paintCutPathPreview(zoomHost, { status: "ready", program, layout: "page" });
assert.equal(zoomHost.__cutPreviewZoom, 1);
ux.paintCutPathPreview(zoomHost, {
    status: "ready",
    program,
    layout: "page",
    selectedPathKey: "cut_path:a",
    zoom: 0.85,
});
assert.equal(zoomHost.__cutPreviewZoom, 1);
ux.paintCutPathPreview(zoomHost, {
    status: "ready",
    program,
    layout: "page",
    selectedPathKey: "liner:a",
});
assert.equal(zoomHost.__cutPreviewZoom, 1, "the board stays inside its fitted viewport");
assert.equal(ux.clampCutPreviewZoom(1 - ux.CUT_PREVIEW_ZOOM.STEP), 1);
assert.equal(ux.clampCutPreviewZoom(16 + ux.CUT_PREVIEW_ZOOM.STEP), 16);

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
    assert.ok(markup.includes("data-path-markers"));
    assert.ok(!markup.includes("dco-cnc-cut-preview__badge"));
    assert.ok(markup.includes("font-size") || css.includes("font-size: 14px"));
    const cutPhysical = ux.collectPhysicalPaths(program).find(item => item.path_key === "cut_path:a");
    assert.ok(cutPhysical);
    assert.equal(cutPhysical.pass_count, 2);
    assert.ok(!markup.includes(`<span>${cutPhysical.path_number}</span>`));
    assert.ok(!markup.includes("<span>4,5</span>"), "depth passes must not keep dual badge numbers");
}

const uniqueScopes = new Set(scopes);
assert.equal(uniqueScopes.size, 10, "each paint must allocate a unique marker scope");
const allIds = liveDom.ids();
assert.equal(allIds.length, new Set(allIds).size, "marker ids across repeated paints must remain unique in the DOM");
assert.ok(!allIds.includes("cnc-cut-arrow-1"));

const host = {
    innerHTML: "",
    getAttribute() { return "page"; },
    setAttribute() {},
    removeAttribute() {},
};
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
