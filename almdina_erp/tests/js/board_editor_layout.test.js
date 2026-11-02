"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(relativePath) {
    const source = fs.readFileSync(path.join(root, relativePath), "utf8");
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(source, context);
    return context.window.AlmdinaBoardEditor;
}

function manySheets(count) {
    return Array.from({ length: count }, (_, index) => ({
        sheet_no: index + 1,
        full_width_cm: 122,
        full_length_cm: 244,
    }));
}

const editor = load("public/js/board_editor/canvas_renderer.js");
const storeApi = load("public/js/board_editor/store.js");
const renderer = editor.CanvasRenderer;
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const sidebarSource = fs.readFileSync(path.join(root, "public/js/board_editor/sidebar_renderer.js"), "utf8");
const cssSource = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");

const sheets = [
    { sheet_no: 1, full_width_cm: 122, full_length_cm: 244, applied_trim_width_cm: 1, applied_trim_length_cm: 1 },
    { sheet_no: 2, full_width_cm: 100, full_length_cm: 200, applied_trim_width_cm: 0.5, applied_trim_length_cm: 0.5 },
    { sheet_no: 3, full_width_cm: 80, full_length_cm: 160 },
];
const layout = renderer.sheetLayout(sheets, 2);

assert.equal(layout.columns, 2);
assert.equal(layout.positions["1"].originX, 0);
assert.ok(layout.positions["2"].originX > layout.positions["1"].originX);
assert.equal(layout.positions["3"].originX, 0);
assert.equal(layout.positions["1"].originY, layout.positions["2"].originY);
assert.ok(layout.positions["3"].originY > layout.positions["1"].originY + layout.positions["1"].heightMm);
assert.equal(layout.maxBoardMm, 1220);
assert.equal(layout.fitBounds.width, 1220 * 2 + 48);
assert.equal(layout.staging.x, layout.fitBounds.width);
assert.ok(layout.staging.width > 0);
assert.equal(layout.positions["1"].trimX, 10);
assert.equal(layout.positions["2"].trimY, 5);

const single = renderer.sheetLayout(manySheets(1), 2);
assert.equal(single.positions["1"].originX, 0);
assert.ok(single.fitBounds.width < layout.fitBounds.width);

const ten = renderer.sheetLayout(manySheets(10), 2);
assert.equal(ten.positions["1"].originY, ten.positions["2"].originY);
assert.equal(ten.positions["9"].originX, 0);
assert.ok(ten.positions["10"].originX > 0);
assert.ok(ten.fitBounds.height > layout.fitBounds.height);

const openFour = renderer.openingScale(1220, 2, 1100);
const openTen = renderer.openingScale(1220, 2, 1100);
assert.equal(openFour, openTen);
const boardPx = 1220 * openFour;
assert.ok(boardPx >= renderer.BOARD_SCREEN_MIN_PX - 1);
assert.ok(boardPx <= renderer.BOARD_SCREEN_MAX_PX + 1);
assert.equal(openFour, (1100 * renderer.GRID_WIDTH_RATIO) / (1220 * 2 + 48));

const fitted = renderer.fitBoards(ten.fitBounds, 1100, 700);
assert.ok(fitted);
assert.ok(fitted.scale < openTen);
assert.equal(fitted.scrollX, 0);
assert.equal(fitted.scrollY, 0);
assert.equal(fitted.fitted, true);
assert.equal(renderer.fitBoards(ten.fitBounds, 0, 0), null);

assert.equal(renderer.columnCount(1220, 1100), 2);
assert.equal(renderer.columnCount(1220, 420), 1);

const store = storeApi.createStore({
    projection: {
        layers: [{ match_key: "GEOMETRY" }],
        sheets: [{ sheet_no: 1 }],
    },
});
store.setViewport({
    scale: openFour,
    scrollX: 40,
    scrollY: 80,
    opened: true,
    userAdjusted: false,
    fitted: false,
});
store.setLayerVisible("GEOMETRY", false);
assert.equal(store.snapshot().viewport.scale, openFour);
assert.equal(store.snapshot().viewport.scrollY, 80);
store.selectPiece(7, { sheetNo: 2, expandSheet: true });
assert.equal(store.snapshot().viewport.scale, openFour);
assert.equal(store.snapshot().viewport.scrollY, 80);

assert.match(controllerSource, /scheduleOpeningCamera/);
assert.match(controllerSource, /openingScale/);
assert.match(controllerSource, /fitAll: \(\) => fitCurrentBoards\(\)/);
assert.doesNotMatch(controllerSource, /abe-title-block/);
assert.doesNotMatch(controllerSource, /scheduleInitialFit/);
assert.match(controllerSource, /isPanKey/);
assert.match(controllerSource, /Space/);
assert.doesNotMatch(cssSource, /min-height:\s*calc\(100vh/);
assert.match(cssSource, /\.abe-canvas-stage[\s\S]*overflow:\s*auto/);
assert.match(cssSource, /\.abe-canvas-tools/);
assert.match(cssSource, /grid-template-columns:\s*270px/);
assert.match(cssSource, /\.abe-float-dock[\s\S]*pointer-events:\s*none/);
assert.match(cssSource, /\.abe-float-tools[\s\S]*pointer-events:\s*auto/);
assert.match(cssSource, /overflow-x:\s*hidden/);
assert.match(cssSource, /--alm-surface/);
assert.match(cssSource, /--alm-shadow-sm/);
assert.doesNotMatch(cssSource, /\.abe-canvas-toolbar/);
assert.doesNotMatch(cssSource, /\.abe-canvas-hint/);
assert.match(sidebarSource, /abe-layers-scroll/);
assert.match(sidebarSource, /abe-tree-scroll/);
assert.match(sidebarSource, /abe-layer-visibility/);
assert.doesNotMatch(sidebarSource, /abe-layer-solo/);
assert.doesNotMatch(sidebarSource, /abe-show-all/);
assert.doesNotMatch(sidebarSource, /abe-hide-all/);
assert.doesNotMatch(sidebarSource, /scrollIntoView/);
assert.match(controllerSource, /abe-float-tools/);

function chromeHost() {
    return {
        clientWidth: 900,
        clientHeight: 640,
        style: {},
        __html: "",
        set innerHTML(value) { this.__html = String(value); },
        get innerHTML() { return this.__html; },
        querySelector() {
            return {
                scrollTop: 0,
                clientWidth: 900,
                clientHeight: 640,
                scrollLeft: 0,
                scrollTop: 0,
                classList: { add() {}, remove() {} },
                style: {},
                addEventListener() {},
                setPointerCapture() {},
                querySelector() { return null; },
                querySelectorAll() { return []; },
                getBoundingClientRect() {
                    return { left: 0, top: 0, width: 900, height: 640, right: 900, bottom: 640 };
                },
            };
        },
        querySelectorAll() { return []; },
    };
}

const canvasHost = chromeHost();
renderer.render(canvasHost, {
    projection: { layers: [], sheets: [{ sheet_no: 1, full_width_cm: 100, full_length_cm: 100 }], elements: [] },
    session: null,
    layerVisibility: {},
    viewport: { scale: 0.4, opened: true, userAdjusted: true, columns: 1, cameraToken: 1, scrollX: 0, scrollY: 0 },
    magnetEnabled: true,
    canUndo: false,
    canRedo: false,
    selectedPieceKeys: [],
    selectedSheetNo: null,
    dropMessage: "",
}, {});
assert.equal(canvasHost.innerHTML.includes("abe-canvas-toolbar"), false);
assert.equal(canvasHost.innerHTML.includes("abe-canvas-hint"), false);
assert.equal(canvasHost.innerHTML.includes("Click to select"), false);
assert.match(canvasHost.innerHTML, /abe-float-dock/);
assert.match(canvasHost.innerHTML, /abe-float-tools/);
assert.ok(canvasHost.innerHTML.indexOf("data-abe-stage") < canvasHost.innerHTML.indexOf("abe-float-dock"));
assert.match(canvasHost.innerHTML, /#icon-zoom-in/);
assert.match(canvasHost.innerHTML, /#icon-zoom-out/);
assert.match(canvasHost.innerHTML, /#icon-maximize-2/);
assert.match(canvasHost.innerHTML, /#icon-undo-2/);
assert.match(canvasHost.innerHTML, /#icon-redo-2/);
assert.match(canvasHost.innerHTML, /#icon-refresh-ccw/);
assert.match(canvasHost.innerHTML, /#icon-magnet/);
assert.match(canvasHost.innerHTML, /#icon-trash-2/);
assert.match(canvasHost.innerHTML, /#icon-square-x/);
assert.match(canvasHost.innerHTML, /#icon-arrow-left/);
assert.match(canvasHost.innerHTML, /#icon-save/);
assert.match(canvasHost.innerHTML, /#icon-clipboard-check/);
assert.match(canvasHost.innerHTML, /data-abe-save-state="clean"/);
assert.match(canvasHost.innerHTML, /No unsaved changes/);
assert.match(canvasHost.innerHTML, /aria-pressed="true"/);
assert.match(canvasHost.innerHTML, /aria-label="Rotation angle in degrees"/);
assert.doesNotMatch(canvasHost.innerHTML, />Angle</);
assert.match(canvasHost.innerHTML, /°/);
const svgHeight = Number((canvasHost.innerHTML.match(/class="abe-svg"[^>]*height="(\d+)"/) || [])[1]);
assert.ok(svgHeight >= 640 + renderer.FLOAT_CLEARANCE_PX);

const sidebarApi = load("public/js/board_editor/sidebar_renderer.js");
function sidebarHtml(visibility) {
    const host = chromeHost();
    sidebarApi.SidebarRenderer.render(host, {
        projection: {
            layers: [
                { match_key: "A", original_name: "GEOMETRY", content_state: "empty", aci_color: 1 },
                { match_key: "B", original_name: "CUT_PATH", content_state: "unavailable", aci_color: 3 },
                { match_key: "C", original_name: "TEXT", content_state: "present", aci_color: 5 },
            ],
            sheets: [
                { sheet_no: 1, resource_kind: "FULL_BOARD", pieces: [{ piece_id: 9, label: "A very long piece name that must stay readable" }] },
                { sheet_no: 2, resource_kind: "OFFCUT", pieces: [] },
            ],
        },
        layerVisibility: visibility,
        expandedSheets: {},
        selectedPieceKeys: [],
        sidebarSplit: 0.4,
    }, {});
    return host.innerHTML;
}
const allVisible = sidebarHtml({ A: true, B: true, C: true });
assert.match(allVisible, /data-abe-layer-action="hide-all"/);
assert.match(allVisible, /data-abe-layer-state="all-visible"/);
assert.match(allVisible, /#icon-eye-off/);
assert.match(allVisible, /All layers are visible\. Hide all\./);
const allHidden = sidebarHtml({ A: false, B: false, C: false });
assert.match(allHidden, /data-abe-layer-action="show-all"/);
assert.match(allHidden, /data-abe-layer-state="all-hidden"/);
assert.match(allHidden, /#icon-eye"/);
assert.match(allHidden, /All layers are hidden\. Show all\./);
const mixed = sidebarHtml({ A: true, B: false, C: true });
assert.match(mixed, /data-abe-layer-state="mixed"/);
assert.match(mixed, /Some layers are hidden\. Show all\./);
[allVisible, allHidden, mixed].forEach((html) => {
    assert.equal(html.includes("abe-layer-solo"), false);
    assert.equal(html.includes("abe-show-all"), false);
    assert.equal(html.includes("abe-hide-all"), false);
    assert.equal(html.includes("abe-layer-badge"), false);
    assert.equal(html.includes(">Only<"), false);
    assert.equal(html.includes(">Empty<"), false);
    assert.equal(html.includes(">Unavailable<"), false);
    assert.equal(html.includes(">FULL_BOARD<"), false);
    assert.match(html, /data-resource-kind="FULL_BOARD"/);
    assert.match(html, />OFFCUT</);
    assert.match(html, /No content on this layer/);
    assert.match(html, /Content is unavailable for this layer/);
    assert.match(html, /A very long piece name/);
    assert.match(html, /abe-sheet-chevron/);
    assert.equal(html.includes("content_state"), false);
});

console.log("board editor layout contract passed");
