"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/snap_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/distribution.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_edge_display.js",
        "public/js/board_editor/plan_display_style.js",
        "public/js/board_editor/plan_edge_marks.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) }, ui: { form: { on() {} } } },
        __: (message) => message,
        document: { createElementNS: () => ({ setAttribute() {}, style: {}, appendChild() {} }) },
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

function makeHost() {
    const stage = {
        clientWidth: 1100,
        clientHeight: 700,
        scrollLeft: 0,
        scrollTop: 0,
        classList: { add() {}, remove() {} },
        style: {},
        addEventListener() {},
        setPointerCapture() {},
        getBoundingClientRect() {
            return { left: 0, top: 0, width: 1100, height: 700, right: 1100, bottom: 700 };
        },
    };
    return {
        clientWidth: 1100,
        clientHeight: 760,
        style: {},
        __html: "",
        set innerHTML(value) { this.__html = String(value); },
        get innerHTML() { return this.__html; },
        querySelector(sel) {
            if (sel === "[data-abe-stage]") return stage;
            return { onclick: null, addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; } };
        },
        querySelectorAll() { return []; },
    };
}

function pathNumbers(d) {
    return (String(d).match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
}

function materialPath(html, pieceKey) {
    const match = html.match(new RegExp(`data-piece-key="${pieceKey}"[\\s\\S]*?<path[^>]*\\sd="([^"]+)"`));
    assert.ok(match, `material path for ${pieceKey}`);
    return match[1];
}

function selectionBlock(html) {
    const match = html.match(/<g class="abe-selection-chrome"[\s\S]*?<\/g>/);
    return match ? match[0] : "";
}

const editor = load();
const { CanvasRenderer, SessionDocument, MoveGeometry, RotationGeometry, Distribution, History, createStore } = editor;

const projection = {
    board: { kerf_cm: 0.4, width_cm: 122, length_cm: 244 },
    edge_display: { default_edge_type: "" },
    layers: [{ match_key: "GEOMETRY", original_name: "GEOMETRY", aci_color: 7 }],
    sheets: [{
        sheet_no: 1,
        full_width_cm: 122,
        full_length_cm: 244,
        applied_trim_width_cm: 0,
        applied_trim_length_cm: 0,
        usable_width_cm: 122,
        usable_length_cm: 244,
    }],
    pieces: [{
        piece_id: 4,
        piece_instance_id: "pi-l",
        label: "L-1",
        sheet_no: 1,
        piece_type: "L-Shaped Corner",
        fill_role: "l_shaped",
        placement_cm: { x: 10, y: 12, w: 40, h: 60, rotated: false },
        allow_rotation: true,
        allow_rotation_proven: true,
    }],
    elements: [
        {
            element_id: "sheet-1",
            kind: "sheet_outline",
            layer_match_key: "SHEET",
            sheet_no: 1,
            payload: {
                resource_kind: "FULL_BOARD",
                full_width_cm: 122,
                full_length_cm: 244,
                usable_width_cm: 122,
                usable_length_cm: 244,
            },
        },
        {
            element_id: "outer",
            kind: "finished_outline",
            layer_match_key: "GEOMETRY",
            sheet_no: 1,
            piece_id: 4,
            piece_instance_id: "pi-l",
            payload: { fill_role: "l_shaped", geometry_source: "placed_parametric_polygon" },
            geometry: {
                outer: [[100, 120], [280, 120], [280, 300], [500, 300], [500, 720], [100, 720]],
            },
        },
    ],
};

const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
let session = SessionDocument.buildFromProjection(projection, layout);
const key = "instance:pi-l";
const history = History.create(session);
const store = createStore({ projection, orderName: "ORD", planName: "PLAN" });
store.attachSession(history.get(), history);
store.selectPiece(4, { pieceKey: key, sheetNo: 1, expandSheet: true });
store.setViewport({ scale: 0.25, opened: true, userAdjusted: true, columns: 1, cameraToken: 1 });
const host = makeHost();

function draw() {
    CanvasRenderer.render(host, store.snapshot(), {});
    return host.innerHTML;
}

let html = draw();
assert.equal((html.match(/data-abe-selection-chrome="1"/g) || []).length, 1);
const chrome = selectionBlock(html);
assert.match(chrome, /class="abe-selection-outline"/);
assert.match(chrome, /stroke="#0b5fff"/);
assert.match(chrome, /stroke-width="2"/);
assert.match(chrome, /vector-effect="non-scaling-stroke"/);
assert.match(chrome, /pointer-events="none"/);
assert.equal(/stroke-dasharray=/.test(chrome), false);
assert.match(html, /fill="#fff0c7"/);
assert.ok(html.indexOf("abe-selection-chrome") > html.indexOf('data-piece-key="instance:pi-l"'));
assert.equal(materialPath(html, key), chrome.match(/\sd="([^"]+)"/)[1]);
assert.equal(pathNumbers(chrome.match(/\sd="([^"]+)"/)[1]).length / 2, 6);

session = RotationGeometry.applyPieceRotation(store.snapshot().session, key, 37);
const world = MoveGeometry.worldFootprint(session.pieces[key], session.boards);
const moved = MoveGeometry.proposePieceDrop(session, key, world.bounds.x + 40, world.bounds.y + 20);
assert.equal(moved.ok, true);
session = MoveGeometry.applyPieceMove(session, moved);
history.commit(session);
store.commitSession(session);
html = draw();
assert.equal((html.match(/data-abe-selection-chrome="1"/g) || []).length, 1);
const movedChrome = selectionBlock(html);
assert.equal(materialPath(html, key), movedChrome.match(/\sd="([^"]+)"/)[1]);
assert.match(html, /fill="#fff0c7"/);
const outside = MoveGeometry.proposePieceDrop(store.snapshot().session, key, 3200, 80);
assert.equal(outside.ok, true);
store.commitSession(MoveGeometry.applyPieceMove(store.snapshot().session, outside));
html = draw();
assert.equal(materialPath(html, key), selectionBlock(html).match(/\sd="([^"]+)"/)[1]);
assert.ok(pathNumbers(materialPath(html, key))[0] > 2000);

store.undo();
html = draw();
const undone = materialPath(html, key);
assert.equal(undone, selectionBlock(html).match(/\sd="([^"]+)"/)[1]);
store.redo();
html = draw();
assert.notEqual(materialPath(html, key), undone);
assert.equal(materialPath(html, key), selectionBlock(html).match(/\sd="([^"]+)"/)[1]);
store.restoreEntry();
html = draw();
assert.equal((html.match(/data-abe-selection-chrome="1"/g) || []).length, 1);
assert.equal(materialPath(html, key), selectionBlock(html).match(/\sd="([^"]+)"/)[1]);

store.setLayerVisible("GEOMETRY", false);
html = draw();
assert.equal(html.includes('data-piece-key="instance:pi-l"'), false);
assert.equal(html.includes('fill="#fff0c7"'), false);
assert.equal((html.match(/data-abe-selection-chrome="1"/g) || []).length, 1);
const hiddenPoints = pathNumbers(selectionBlock(html).match(/\sd="([^"]+)"/)[1]);
const liveWorld = MoveGeometry.worldFootprint(store.snapshot().session.pieces[key], store.snapshot().session.boards);
assert.equal(hiddenPoints.length / 2, liveWorld.points.length);
assert.ok(Math.abs(hiddenPoints[0] - liveWorld.points[0][0]) < 0.01);
assert.ok(Math.abs(hiddenPoints[1] - liveWorld.points[0][1]) < 0.01);

store.selectPiece(null, { pieceKey: null, elementId: null });
html = draw();
assert.equal((html.match(/data-abe-selection-chrome="1"/g) || []).length, 0);

store.setLayerVisible("GEOMETRY", true);
store.selectPiece(4, { pieceKey: key, sheetNo: 1 });
const removed = Distribution.excludePiece(store.snapshot().session, key);
assert.equal(removed.ok, true);
store.commitSession(removed.session);
store.selectPiece(4, { pieceKey: key, elementId: null });
html = draw();
assert.equal((html.match(/data-abe-selection-chrome="1"/g) || []).length, 0);
assert.equal(html.includes('data-piece-key="instance:pi-l"'), false);

assert.equal(CanvasRenderer.clickTargetKeepsSelection({
    closest(selector) { return selector.includes("data-piece-key") ? {} : null; },
}), true);
assert.equal(CanvasRenderer.clickTargetKeepsSelection({
    closest() { return null; },
}), false);
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(controllerSource, /clearSelection:/);

console.log("board editor selection ok");
