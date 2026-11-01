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
assert.match(sidebarSource, /abe-layers-scroll/);
assert.match(sidebarSource, /abe-tree-scroll/);
assert.doesNotMatch(sidebarSource, /scrollIntoView/);

console.log("board editor layout contract passed");
