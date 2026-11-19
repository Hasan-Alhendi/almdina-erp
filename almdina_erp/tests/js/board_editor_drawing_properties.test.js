"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const helperSource = fs.readFileSync(path.join(root, "tests/js/board_editor_polyline_input.test.js"), "utf8");

function load(files) {
    const context = {
        console,
        __: (message) => message,
        frappe: { utils: { escape_html: (value) => String(value == null ? "" : value) }, boot: { lang: "en" } },
        document: null,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    vm.runInContext(
        `${helperSource.slice(helperSource.indexOf("const VOID"), helperSource.indexOf("function loadEditor"))}\nthis.MiniElement = MiniElement;\n`,
        context
    );
    context.document = {
        createElementNS(_ns, tag) { return new context.MiniElement(tag, {}, context.document); },
    };
    return context;
}

const dom = load([
    "public/js/board_editor/editor_mode.js",
    "public/js/board_editor/canvas_renderer.js",
    "public/js/board_editor/drawing_properties_panel.js",
]);

function renderPair(view) {
    const canvas = new dom.MiniElement("section", { class: "abe-canvas-host" }, dom.document);
    const properties = new dom.MiniElement("aside", {}, dom.document);
    dom.AlmdinaBoardEditor.CanvasRenderer.render(canvas, view, {});
    dom.AlmdinaBoardEditor.DrawingProperties.render(properties, view, {});
    return { canvas, properties };
}

const base = {
    editorMode: "drawing",
    drawingTarget: { status: "special", canEdit: true, label: "Special door", widthCm: 60, lengthCm: 210 },
    viewport: { scale: 1, opened: true, userAdjusted: true, scrollX: 40, scrollY: 12 },
    session: { pieces: {}, boards: {} },
    selectedPieceKeys: [],
    projection: { pieces: [], sheets: [], elements: [] },
};

const selectView = Object.assign({}, base, {
    drawingView: {
        tool: "select",
        ready: true,
        persisted: true,
        pathForm: { role: "manufacturing_outer" },
        paths: [],
        shapes: [],
    },
});
const selected = renderPair(selectView);
assert.match(selected.canvas.innerHTML, /data-abe-drawing-tool="select"/);
assert.match(selected.canvas.innerHTML, /data-abe-drawing-tool="polyline"/);
assert.match(selected.canvas.innerHTML, /data-abe-drawing-tool="shapes"/);
assert.match(selected.canvas.innerHTML, /data-abe-drawing-tool="pen"/);
assert.match(selected.canvas.innerHTML, /data-abe-drawing-tool="node_edit"/);
assert.match(selected.canvas.innerHTML, /data-abe-snap-toggle/);
assert.match(selected.canvas.innerHTML, /data-abe-reference-toggle/);
assert.match(selected.canvas.innerHTML, /data-abe-drawing-history="undo"/);
assert.match(selected.canvas.innerHTML, /abe-zoom-in/);
assert.doesNotMatch(selected.canvas.innerHTML, /data-abe-path-form|data-abe-shape-form|data-abe-reference-form|data-abe-snap-menu|abe-undo\b|abe-measure/);
assert.match(selected.properties.innerHTML, /data-abe-path-form/);
assert.match(selected.properties.innerHTML, /Special door/);
assert.match(selected.properties.innerHTML, /Saved drawing/);
assert.equal(selected.properties.querySelectorAll("[data-abe-path-form]").length, 1);
assert.equal(selected.canvas.querySelector("[data-abe-drawing-cursor]"), null);

const polyline = renderPair(Object.assign({}, base, {
    drawingView: {
        tool: "polyline",
        ready: true,
        dirty: true,
        canFinish: true,
        measure: { mode: "draw", enabled: true, lengthMm: 180, angleDeg: 0 },
        paths: [],
        shapes: [],
    },
}));
assert.equal(polyline.canvas.querySelectorAll("[data-abe-drawing-length]").length, 1);
assert.equal(polyline.canvas.querySelector("[data-abe-drawing-cursor] [data-abe-drawing-length]").getAttribute("tabindex"), null);
assert.equal(polyline.properties.querySelector("[data-abe-drawing-length]"), null);
assert.match(polyline.properties.innerHTML, /data-abe-drawing-action="finish"/);
assert.match(polyline.properties.innerHTML, /Unsaved drawing/);
assert.equal(polyline.canvas.innerHTML.includes("scale("), true);

dom.AlmdinaLocale = { direction: () => "rtl" };
dom.AlmdinaBoardEditor.DrawingProperties.reset();
const rtl = renderPair(selectView);
assert.equal(rtl.properties.querySelector("[data-abe-draw-props]").getAttribute("dir"), "rtl");
assert.equal(rtl.properties.querySelector("[data-abe-path-dx]").getAttribute("dir"), "ltr");
dom.AlmdinaLocale = { direction: () => "ltr" };
dom.AlmdinaBoardEditor.DrawingProperties.reset();
const collapsedHost = new dom.MiniElement("aside", {}, dom.document);
dom.AlmdinaBoardEditor.DrawingProperties.render(collapsedHost, selectView, {}, true);
assert.match(collapsedHost.innerHTML, /is-collapsed/);
assert.equal(collapsedHost.querySelector("[data-abe-path-form]"), null);

const nodeView = Object.assign({}, base, {
    drawingView: {
        tool: "node_edit",
        ready: true,
        shapeForm: {
            mode: "node",
            fields: [{ key: "x_mm", labelKey: "X (mm)", value: "12" }],
            actions: { insert: true, remove: true },
        },
        paths: [],
        shapes: [],
    },
});
dom.AlmdinaBoardEditor.DrawingProperties.reset();
const node = renderPair(nodeView);
assert.equal(node.properties.querySelectorAll("[data-abe-shape-form]").length, 1);
assert.equal(node.properties.querySelector("[data-abe-shape-mode]").getAttribute("data-abe-shape-mode"), "node");

const css = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(css, /grid-template-areas:\s*"sidebar canvas inspector"/);
assert.match(css, /\.abe-body\.is-drawing\s*\{[^}]*--abe-right-sidebar-width:\s*300px/);
assert.match(css, /\.abe-body\.is-drawing\.is-draw-props-collapsed\s*\{[^}]*--abe-right-sidebar-width:\s*36px/);
assert.match(css, /\.abe-page\[dir="rtl"\] \.abe-draw-props/);
assert.match(page, /drawing_properties_panel\.js\?v=4/);
assert.match(page, /canvas_renderer\.js\?v=58/);
assert.match(page, /controller\.js\?v=57/);
assert.match(page, /board_editor\.css\?v=53/);
assert.match(controller, /DrawingProperties\.render/);
assert.match(controller, /lastCanvasStageWidth - stageWidth/);
assert.doesNotMatch(controller.slice(controller.indexOf("const stageAfter"), controller.indexOf("restoreDrawingMeasureFocus(canvas)")), /scale:/);

console.log("board editor drawing properties tests ok");
