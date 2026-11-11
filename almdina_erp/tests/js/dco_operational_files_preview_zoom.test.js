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
const cssPath = path.join(root, "public/css/door_cutting_order_operational_files.css");
const translationsPath = path.join(root, "translations/ar.csv");
const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

assert.ok(typeof ux.clampCutPreviewPan === "function");
assert.ok(typeof ux.normalizeCutPreviewPan === "function");
assert.ok(typeof ux.scaleCutPreviewPan === "function");
assert.ok(panel.includes("data-cut-viewport"));
assert.ok(panel.includes("Board preview viewport"));
assert.ok(panel.includes("translate("));
assert.ok(panel.includes("__cutPreviewPan"));
assert.ok(css.includes(".dco-cnc-cut-preview__viewport"));
assert.ok(css.includes("overflow: hidden"));
assert.ok(translations.includes("مساحة عرض اللوح"));

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

const program = {
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
                    sequence: 1,
                    closed: true,
                    ready: true,
                    issues: [],
                    points: [[0, 0], [100, 0], [100, 100], [0, 100]],
                    motions: [
                        ...motionChain([[0, 0], [100, 0], [100, 100], [0, 100]], 6, true),
                        ...motionChain([[0, 0], [100, 0], [100, 100], [0, 100]], 12, true),
                    ],
                },
                {
                    path_key: "cut_path:b",
                    operation_key: "cut_path",
                    sequence: 2,
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[200, 50], [400, 50]],
                    motions: motionChain([[200, 50], [400, 50]], 8, false),
                },
            ],
        },
        {
            operation_key: "liner",
            toolpaths: [{
                path_key: "liner:a",
                operation_key: "liner",
                sequence: 1,
                closed: false,
                ready: true,
                issues: [],
                points: [[10, 10], [40, 10]],
                motions: motionChain([[10, 10], [40, 10]], 3, false),
            }],
        },
    ],
};

assert.equal(ux.CUT_PREVIEW_ZOOM.MIN, 0.4);
assert.equal(ux.CUT_PREVIEW_ZOOM.INITIAL, 0.55);
assert.equal(ux.CUT_PREVIEW_ZOOM.MAX, 2.5);
assert.equal(ux.CUT_PREVIEW_ZOOM.STEP, 0.15);

const pageMarkup = ux.cutPathPreviewMarkup(program, {
    layout: "page",
    markerScope: "cnc-zoom-page",
    zoom: ux.CUT_PREVIEW_ZOOM.INITIAL,
});
assert.ok(pageMarkup.includes("data-cut-viewport"));
assert.ok(pageMarkup.includes("data-cut-stage"));
assert.ok(!pageMarkup.includes('data-cut-zoom="in"'));
assert.ok(!pageMarkup.includes('data-cut-zoom="out"'));
assert.ok(!pageMarkup.includes('data-cut-zoom="reset"'));
assert.ok(!pageMarkup.includes("dco-cnc-cut-preview__legend"));
assert.ok(!pageMarkup.includes("dco-cnc-cut-preview__badge"));
assert.ok(pageMarkup.includes("max-inline-size:260px"));
assert.ok(pageMarkup.includes("aspect-ratio:2440 / 1220"));
assert.ok(pageMarkup.indexOf("data-cut-viewport") < pageMarkup.indexOf("data-cut-stage"));

const dialogMarkup = ux.cutPathPreviewMarkup(program, {
    markerScope: "cnc-zoom-dialog",
});
assert.ok(!dialogMarkup.includes("data-cut-viewport"), "dialog preview does not create page viewport chrome");
assert.ok(dialogMarkup.includes("data-cut-stage"));

assert.deepEqual(ux.normalizeCutPreviewPan(null), { x: 0, y: 0 });
assert.deepEqual(ux.normalizeCutPreviewPan({ x: "12.5", y: "-3" }), { x: 12.5, y: -3 });

const viewport = { width: 800, height: 400 };
assert.deepEqual(
    ux.clampCutPreviewPan({ x: 9999, y: -9999 }, 0.55, viewport),
    { x: 0, y: 0 },
    "pan is disabled when zoom is at or below 1"
);
assert.deepEqual(
    ux.clampCutPreviewPan({ x: 9999, y: -9999 }, 1, viewport),
    { x: 0, y: 0 }
);
const clamped = ux.clampCutPreviewPan({ x: 9999, y: -9999 }, 2.5, viewport);
assert.equal(clamped.x, (800 * (2.5 - 1)) / 2);
assert.equal(clamped.y, -((400 * (2.5 - 1)) / 2));

const scaled = ux.scaleCutPreviewPan({ x: 40, y: -20 }, 1, 2);
assert.deepEqual(scaled, { x: 80, y: -40 });

function createZoomHost() {
    const listeners = new Map();
    const stageStyle = {
        props: { "--cut-zoom": "0.55" },
        transform: "",
        getPropertyValue(name) { return this.props[name] || ""; },
        setProperty(name, value) { this.props[name] = String(value); },
    };
    const viewportNode = {
        className: "dco-cnc-cut-preview__viewport",
        clientWidth: 800,
        clientHeight: 400,
        classList: {
            values: new Set(),
            toggle(name, force) {
                if (force) this.values.add(name);
                else this.values.delete(name);
                viewportNode.className = ["dco-cnc-cut-preview__viewport", ...this.values].join(" ");
            },
            add(name) { this.values.add(name); },
            remove(name) { this.values.delete(name); },
            contains(name) { return this.values.has(name); },
        },
        getBoundingClientRect() {
            return { width: 800, height: 400, left: 0, top: 0, right: 800, bottom: 400 };
        },
        addEventListener(type, handler) {
            const list = listeners.get(type) || [];
            list.push(handler);
            listeners.set(type, list);
        },
        setPointerCapture() {},
        dispatch(type, event) {
            (listeners.get(type) || []).forEach(handler => handler(event));
        },
    };
    const stageNode = {
        style: stageStyle,
    };
    const buttons = {
        out: { disabled: false, addEventListener(type, handler) { this._out = handler; } },
        in: { disabled: false, addEventListener(type, handler) { this._in = handler; } },
        reset: { disabled: false, addEventListener(type, handler) { this._reset = handler; } },
    };
    const host = {
        innerHTML: "",
        __cutPreviewZoom: null,
        __cutPreviewPan: null,
        getAttribute() { return "page"; },
        querySelector(selector) {
            if (selector === "[data-cut-stage]") return stageNode;
            if (selector === "[data-cut-viewport]") return viewportNode;
            if (selector === '[data-cut-zoom="out"]') return buttons.out;
            if (selector === '[data-cut-zoom="in"]') return buttons.in;
            if (selector === '[data-cut-zoom="reset"]') return buttons.reset;
            return null;
        },
        querySelectorAll(selector) {
            if (selector === "[data-cut-zoom]") {
                return [
                    { getAttribute() { return "out"; }, addEventListener(type, handler) { buttons.out._handler = handler; } },
                    { getAttribute() { return "reset"; }, addEventListener(type, handler) { buttons.reset._handler = handler; } },
                    { getAttribute() { return "in"; }, addEventListener(type, handler) { buttons.in._handler = handler; } },
                ];
            }
            if (selector === "[data-cut-layer]") return [];
            return [];
        },
        stageStyle,
        viewportNode,
        buttons,
    };
    return host;
}

const host = createZoomHost();
ux.paintCutPathPreview(host, {
    status: "ready",
    program,
    layout: "page",
    zoom: ux.CUT_PREVIEW_ZOOM.INITIAL,
});
assert.equal(host.__cutPreviewZoom, 1);
assert.deepEqual(host.__cutPreviewPan, { x: 0, y: 0 });
assert.ok(host.innerHTML.includes("data-cut-viewport"));
assert.ok(!host.innerHTML.includes("data-cut-zoom"));
assert.ok(host.stageStyle.transform.includes("scale(1)"));

host.viewportNode.dispatch("pointerdown", {
    button: 0,
    shiftKey: true,
    clientX: 100,
    clientY: 100,
    pointerId: 1,
    target: host.viewportNode,
    preventDefault() {},
});
host.viewportNode.dispatch("pointermove", { clientX: 180, clientY: 40 });
assert.deepEqual(host.__cutPreviewPan, { x: 0, y: 0 });
assert.equal(host.__cutPreviewZoom, 1);

const physical = ux.collectPhysicalPaths(program);
assert.ok(physical.length >= 2);
const selectedMarkup = ux.cutPathPreviewMarkup(program, {
    layout: "page",
    markerScope: "cnc-zoom-select",
    selectedExecutionPathId: physical[0].execution_path_id,
    zoom: 2.05,
});
assert.ok(selectedMarkup.includes("is-cnc-path-selected"));
assert.ok(selectedMarkup.includes(`data-execution-path-id="${physical[0].execution_path_id}"`));
assert.ok(selectedMarkup.includes("scale(calc(1 / var(--cut-zoom, 1)))") || css.includes("scale(calc(1 / var(--cut-zoom, 1)))"));

assert.ok(!panel.includes("cutter_center_paths"));
assert.ok(!panel.includes("build_board_program"));
assert.ok(panel.includes("overflow: hidden") || css.includes(".dco-cnc-cut-preview__viewport"));
assert.ok(css.includes("overflow-x: hidden"));

console.log("dco_operational_files_preview_zoom.test.js passed");
