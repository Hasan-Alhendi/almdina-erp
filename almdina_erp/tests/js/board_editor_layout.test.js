"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(...relativePaths) {
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    relativePaths.forEach((relativePath) => {
        const source = fs.readFileSync(path.join(root, relativePath), "utf8");
        vm.runInContext(source, context, { filename: relativePath });
    });
    return context.window.AlmdinaBoardEditor;
}

function manySheets(count) {
    return Array.from({ length: count }, (_, index) => ({
        sheet_no: index + 1,
        full_width_cm: 122,
        full_length_cm: 244,
    }));
}

const editor = load(
    "public/js/board_editor/move_geometry.js",
    "public/js/board_editor/rotation_geometry.js",
    "public/js/board_editor/canvas_renderer.js"
);
const storeApi = load("public/js/board_editor/store.js");
const renderer = editor.CanvasRenderer;
const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
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
const baseOpen = (1100 * renderer.GRID_WIDTH_RATIO) / (1220 * 2 + 48);
assert.equal(openFour, baseOpen * renderer.OPENING_SCALE_FACTOR);
assert.ok(Math.abs(renderer.OPENING_SCALE_FACTOR - 0.7) < 1e-9);
assert.ok(boardPx < 1220 * baseOpen * 0.8);
assert.ok(boardPx <= renderer.BOARD_SCREEN_MAX_PX * renderer.OPENING_SCALE_FACTOR + 1);

const fitted = renderer.fitBoards(ten.fitBounds, 1100, 700);
assert.ok(fitted);
assert.ok(fitted.scale < openTen);
assert.ok(Number.isFinite(fitted.scrollX));
assert.ok(Number.isFinite(fitted.scrollY));
assert.ok(Number.isFinite(fitted.padX));
assert.ok(Number.isFinite(fitted.padY));
assert.equal(fitted.fitted, true);
assert.equal(renderer.fitBoards(ten.fitBounds, 0, 0), null);

const four = renderer.sheetLayout(manySheets(4), 2);
assert.equal(four.columns, 2);
assert.equal(Object.keys(four.positions).length, 4);
assert.equal(four.positions["1"].originY, four.positions["2"].originY);
assert.equal(four.positions["3"].originY, four.positions["4"].originY);
assert.ok(four.positions["3"].originY > four.positions["1"].originY);

const centered = renderer.frameCamera(four.fitBounds, openFour, 1100, 700);
assert.ok(centered);
assert.ok(centered.padX >= renderer.SCENE_PAD_PX - 1e-6);
assert.ok(centered.scrollX >= 0);
assert.ok(centered.scrollY >= 0);

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
assert.match(cssSource, /--abe-sidebar-width:\s*208px/);
assert.match(cssSource, /--abe-right-sidebar-width:\s*240px/);
assert.match(cssSource, /grid-template-columns:\s*var\(--abe-sidebar-width\) minmax\(0, 1fr\) var\(--abe-right-sidebar-width\)/);
assert.match(cssSource, /grid-template-areas:\s*"sidebar canvas inspector"/);
assert.match(cssSource, /\.abe-body[\s\S]*direction:\s*ltr/);
assert.match(controllerSource, /data-abe-right-sidebar-host/);
/* Zoom width compensation must not clip the physical-left sidebar under RTL. */
assert.match(cssSource, /\.abe-shell-host/);
assert.match(cssSource, /direction:\s*ltr/);
assert.match(cssSource, /\.abe-page\s*\{[^}]*direction:\s*ltr/);
assert.match(cssSource, /width:\s*calc\(100% \/ var\(--abe-ui-zoom\)\)/);
assert.match(cssSource, /transform:\s*scale\(var\(--abe-ui-zoom\)\)/);
assert.match(cssSource, /transform-origin:\s*top left/);
assert.match(cssSource, /\.abe-page\[dir="rtl"\] \.abe-sidebar-host/);
assert.match(cssSource, /scrollbar-width:\s*thin/);
assert.doesNotMatch(cssSource, /grid-template-columns:\s*224px/);
assert.match(cssSource, /\.abe-canvas-stage[\s\S]*direction:\s*ltr/);
assert.match(controllerSource, /classList\.add\(["']abe-shell-host["']\)/);
assert.match(controllerSource, /classList\.remove\(["']abe-shell-host["']\)/);
assert.match(controllerSource, /frameCamera/);
assert.match(controllerSource, /lastCanvasPointerClient/);
assert.match(controllerSource, /zoomFocalClient/);
assert.match(controllerSource, /metrics\.minX/);
assert.match(
    fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8"),
    /viewBox="0 0 \$\{contentW\} \$\{contentH\}"/
);
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
assert.match(canvasHost.innerHTML, /abe-angle-0-180/);
assert.match(canvasHost.innerHTML, /abe-angle-90-270/);
assert.match(canvasHost.innerHTML, /abe-rotate-30/);
assert.match(canvasHost.innerHTML, /abe-angle-mirror/);
assert.match(canvasHost.innerHTML, /#icon-arrow-left-right/);
assert.match(canvasHost.innerHTML, /#icon-arrow-up-down/);
assert.match(canvasHost.innerHTML, /#icon-flip-horizontal-2|flip-horizontal-2/);
assert.doesNotMatch(canvasHost.innerHTML, /abe-float-tools[\s\S]*abe-save\b/);
assert.doesNotMatch(canvasHost.innerHTML, /abe-float-tools[\s\S]*abe-back\b/);
assert.doesNotMatch(canvasHost.innerHTML, /abe-float-tools[\s\S]*abe-create-plan\b/);
assert.doesNotMatch(canvasHost.innerHTML, /abe-float-tools[\s\S]*abe-review\b/);
assert.match(canvasHost.innerHTML, /aria-pressed="true"/);

{
    const pageHost = chromeHost();
    renderer.renderPageActions(pageHost, {
        saveState: "clean",
        createPlanInFlight: false,
        distributionDirty: false,
        draftVersion: 1,
        sourceOnly: false,
        canSaveLayout: true,
        reviewInFlight: false,
    }, {});
    assert.match(pageHost.innerHTML, /abe-page-actions/);
    assert.match(pageHost.innerHTML, /#icon-save/);
    assert.match(pageHost.innerHTML, /#icon-clipboard-check/);
    assert.match(pageHost.innerHTML, /#icon-arrow-left/);
    assert.match(pageHost.innerHTML, /data-abe-save-state="clean"/);
    assert.match(pageHost.innerHTML, /No unsaved changes/);
}
// Angle field always exposes an accessible name; idle chrome has no selection.
assert.match(canvasHost.innerHTML, /class="abe-angle-input"[^>]*aria-label="/);
assert.match(
    canvasHost.innerHTML,
    /aria-label="Select a piece to set its rotation angle\."/
);
assert.doesNotMatch(canvasHost.innerHTML, />Angle</);
assert.match(canvasHost.innerHTML, /°/);
assert.ok(catalog.includes("Select a piece to set its rotation angle."));
assert.ok(catalog.includes("Rotation angle in degrees"));

// Selected rotatable piece uses the degrees label (not a missing/generic name).
{
    const rotatableHost = chromeHost();
    const pieceKey = "instance:pi-rot";
    renderer.render(rotatableHost, {
        projection: {
            layers: [],
            sheets: [{ sheet_no: 1, full_width_cm: 100, full_length_cm: 100 }],
            elements: [],
        },
        session: {
            boards: {
                1: {
                    sheet_no: 1,
                    origin_x_mm: 0,
                    origin_y_mm: 36,
                    width_mm: 1000,
                    height_mm: 1000,
                    trim_x_mm: 0,
                    trim_y_mm: 0,
                    title_band_mm: 36,
                    user_moved: false,
                },
            },
            pieces: {
                [pieceKey]: {
                    piece_key: pieceKey,
                    piece_id: 7,
                    piece_instance_id: "pi-rot",
                    sheet_no: 1,
                    local_x_mm: 10,
                    local_y_mm: 20,
                    rotation_deg: 12.5,
                    editable: true,
                    distribution: "active",
                    allow_rotation: true,
                    allow_rotation_proven: true,
                    base_outline_mm: [[0, 0], [100, 0], [100, 40], [0, 40]],
                    outline_mm: [[0, 0], [100, 0], [100, 40], [0, 40]],
                },
            },
            kerf_mm: 4,
        },
        layerVisibility: {},
        viewport: {
            scale: 0.4,
            opened: true,
            userAdjusted: true,
            columns: 1,
            cameraToken: 1,
            scrollX: 0,
            scrollY: 0,
        },
        magnetEnabled: true,
        canUndo: false,
        canRedo: false,
        selectedPieceKey: pieceKey,
        selectedPieceKeys: [pieceKey],
        selectedSheetNo: 1,
        dropMessage: "",
    }, {});
    assert.match(
        rotatableHost.innerHTML,
        /class="abe-angle-input"[^>]*aria-label="Rotation angle in degrees"/
    );
    assert.doesNotMatch(rotatableHost.innerHTML, /abe-angle-field is-disabled/);
    assert.match(rotatableHost.innerHTML, /value="12\.5"/);
}
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
