"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function loadEditor() {
    const files = [
        "public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js",
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/snap_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_edge_display.js",
        "public/js/board_editor/plan_display_style.js",
        "public/js/board_editor/plan_edge_marks.js",
        "public/js/board_editor/position_geometry.js",
        "public/js/board_editor/alignment_geometry.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
        "public/js/board_editor/sidebar_renderer.js",
        "public/js/board_editor/right_sidebar_renderer.js",
    ];
    const context = {
        frappe: {
            utils: {
                escape_html: (value) => String(value),
                icon: (name) => `<span data-icon="${name}"></span>`,
            },
            ui: { form: { on() {} } },
        },
        __: (message, replace) => {
            if (!Array.isArray(replace) || !replace.length) return message;
            return replace.reduce(
                (text, value, index) => text.replace(`{${index}}`, String(value)),
                message
            );
        },
        document: {
            createElementNS: () => ({
                setAttribute() {},
                style: {},
                appendChild() {},
            }),
        },
        console,
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
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
        style: {},
        addEventListener() {},
        querySelector() { return null; },
        setPointerCapture() {},
        releasePointerCapture() {},
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
            if (sel === ".abe-layers-scroll" || sel === ".abe-tree-scroll") {
                return { scrollTop: 0 };
            }
            if (sel === "[data-abe-position-bar]") {
                if (!this.__html.includes("data-abe-position-bar")) return null;
                return { querySelectorAll: () => [], querySelector: () => null };
            }
            if (sel === "input[data-abe-show-edge-bands]" || sel === "input[data-abe-piece-edge-bands]") {
                if (!this.__html.includes(sel.replace("input[", "").replace("]", ""))) return null;
                return {
                    checked: /checked/.test(this.__html),
                    indeterminate: false,
                    addEventListener() {},
                    getAttribute(name) {
                        if (name === "data-abe-piece-key") {
                            const match = this.__html && this.__html.match(/data-abe-piece-key="([^"]+)"/);
                            return match ? match[1] : null;
                        }
                        return null;
                    },
                };
            }
            return {
                onclick: null,
                addEventListener() {},
                querySelector() { return null; },
                querySelectorAll() { return []; },
                appendChild() {},
                classList: { add() {}, remove() {}, contains() { return false; } },
                style: {},
                getBoundingClientRect() {
                    return { left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600 };
                },
            };
        },
        querySelectorAll() { return []; },
    };
}

function sheet() {
    return {
        sheet_no: 1,
        full_width_cm: 122,
        full_length_cm: 244,
        applied_trim_width_cm: 0,
        applied_trim_length_cm: 0,
        usable_width_cm: 122,
        usable_length_cm: 244,
    };
}

function bandCount(html) {
    return (String(html).match(/class="abe-edge-band"/g) || []).length;
}

function doubleMarkCount(html) {
    return (String(html).match(/stroke="#5a2d82"/g) || []).length;
}

function assertNoOverrides(storeApi) {
    assert.equal(Object.keys(storeApi.snapshot().pieceEdgeBandOverrides || {}).length, 0);
}

const editor = loadEditor();
const {
    CanvasRenderer,
    SessionDocument,
    createStore,
    History,
    SidebarRenderer,
    RightSidebarRenderer,
    isPieceEdgeBandVisibleInView,
} = editor;

const edgesA = {
    edge_width_top: 1,
    edge_width_bottom: 0,
    edge_long_left: 1,
    edge_long_right: 0,
};
const edgesB = {
    edge_width_top: 0,
    edge_width_bottom: 1,
    edge_long_left: 0,
    edge_long_right: 1,
    edge_long_right_type_override: "Blue PVC",
};

const projection = {
    edge_display: { default_edge_type: "" },
    board: { kerf_cm: 0.4, usable_width_cm: 122, usable_length_cm: 244 },
    layers: [
        { match_key: "CUT_PATH", original_name: "CUT_PATH", aci_color: 1 },
        { match_key: "GEOMETRY", original_name: "GEOMETRY", aci_color: 7 },
    ],
    sheets: [sheet()],
    pieces: [
        {
            piece_id: 1,
            piece_instance_id: "pi-a",
            label: "A",
            sheet_no: 1,
            piece_type: "Regular",
            fill_role: "regular",
            original_w: 20,
            original_h: 30,
            placement_cm: { x: 5, y: 5, w: 30, h: 20, rotated: false },
            display_edges: edgesA,
        },
        {
            piece_id: 1,
            piece_instance_id: "pi-b",
            label: "B",
            sheet_no: 1,
            piece_type: "Regular",
            fill_role: "regular",
            original_w: 15,
            original_h: 15,
            placement_cm: { x: 50, y: 40, w: 15, h: 15, rotated: false },
            display_edges: edgesB,
            extra_double: 1,
            extra_double_reference_sides: "edge_width_top",
        },
    ],
    elements: [
        {
            element_id: "sheet:1",
            kind: "sheet_outline",
            layer_match_key: "SHEET",
            sheet_no: 1,
            payload: {
                full_width_cm: 122,
                full_length_cm: 244,
                usable_width_cm: 122,
                usable_length_cm: 244,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
            },
        },
        {
            element_id: "p-a",
            kind: "placement_rect",
            layer_match_key: "GEOMETRY",
            sheet_no: 1,
            piece_id: 1,
            piece_instance_id: "pi-a",
            payload: {
                placement_cm: { x: 5, y: 5, w: 30, h: 20, rotated: false },
                display_edges: edgesA,
                geometry_source: "placement_rect",
                fill_role: "regular",
            },
        },
        {
            element_id: "p-b",
            kind: "placement_rect",
            layer_match_key: "GEOMETRY",
            sheet_no: 1,
            piece_id: 1,
            piece_instance_id: "pi-b",
            payload: {
                placement_cm: { x: 50, y: 40, w: 15, h: 15, rotated: false },
                display_edges: {
                    ...edgesB,
                    extra_double: 1,
                    extra_double_reference_sides: "edge_width_top",
                },
                geometry_source: "placement_rect",
                fill_role: "regular",
            },
        },
    ],
};

const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
const session = SessionDocument.buildFromProjection(projection, layout);
const history = History.create(session);
const store = createStore({ projection, order_name: "O", plan_name: "P" });
store.attachSession(history.get(), history);
store.setViewport({
    scale: 0.25,
    opened: true,
    userAdjusted: true,
    columns: 1,
    scrollX: 0,
    scrollY: 0,
    fitted: false,
    cameraToken: 1,
});

const keyA = "instance:pi-a";
const keyB = "instance:pi-b";
assert.ok(store.snapshot().session.pieces[keyA]);
assert.ok(store.snapshot().session.pieces[keyB]);

// Default open: edge bands hidden; double-edge purple marks stay.
{
    assert.equal(store.snapshot().showEdgeBands, false);
    assertNoOverrides(store);
    const host = makeHost();
    CanvasRenderer.render(host, store.snapshot(), {});
    assert.equal(bandCount(host.innerHTML), 0);
    assert.ok(doubleMarkCount(host.innerHTML) > 0, "double-edge marks must remain visible");
    assert.match(host.innerHTML, /abe-piece/);
    assert.match(host.innerHTML, /CUT_PATH|GEOMETRY|abe-piece/);
}

// Global show reveals red/blue bands without dirtying draft/history.
{
    const dirtyBefore = store.snapshot().distributionDirty;
    const undoBefore = store.snapshot().canUndo;
    const fingerprintBefore = SessionDocument.distributionFingerprint(store.snapshot().session);
    store.setShowEdgeBands(true);
    assert.equal(store.snapshot().showEdgeBands, true);
    assertNoOverrides(store);
    assert.equal(store.snapshot().distributionDirty, dirtyBefore);
    assert.equal(store.snapshot().canUndo, undoBefore);
    assert.equal(
        SessionDocument.distributionFingerprint(store.snapshot().session),
        fingerprintBefore
    );
    const host = makeHost();
    CanvasRenderer.render(host, store.snapshot(), {});
    assert.ok(bandCount(host.innerHTML) >= 3);
}

// Global hide clears overrides and hides bands again.
{
    store.setPieceEdgeBandVisible(keyA, false);
    assert.equal(store.isPieceEdgeBandVisible(keyA), false);
    store.setShowEdgeBands(false);
    assertNoOverrides(store);
    assert.equal(store.isPieceEdgeBandVisible(keyA), false);
    assert.equal(store.isPieceEdgeBandVisible(keyB), false);
    const host = makeHost();
    CanvasRenderer.render(host, store.snapshot(), {});
    assert.equal(bandCount(host.innerHTML), 0);
}

// Per-piece override while global is hidden.
{
    store.setShowEdgeBands(false);
    store.setPieceEdgeBandVisible(keyB, true);
    assert.equal(store.isPieceEdgeBandVisible(keyA), false);
    assert.equal(store.isPieceEdgeBandVisible(keyB), true);
    assert.equal(isPieceEdgeBandVisibleInView(store.snapshot(), keyB), true);
    const ui = store.edgeBandGlobalUiState();
    assert.equal(ui.indeterminate, true);
    assert.equal(ui.checked, false);
    const host = makeHost();
    CanvasRenderer.render(host, store.snapshot(), {});
    const bands = bandCount(host.innerHTML);
    assert.ok(bands >= 1 && bands <= 4, `expected only B bands, got ${bands}`);
}

// Mixed global click shows all and clears overrides.
{
    store.setShowEdgeBands(true);
    assertNoOverrides(store);
    assert.equal(store.isPieceEdgeBandVisible(keyA), true);
    assert.equal(store.isPieceEdgeBandVisible(keyB), true);
    const ui = store.edgeBandGlobalUiState();
    assert.equal(ui.indeterminate, false);
    assert.equal(ui.checked, true);
}

// Per-piece hide while global is shown.
{
    store.setPieceEdgeBandVisible(keyA, false);
    assert.equal(store.isPieceEdgeBandVisible(keyA), false);
    assert.equal(store.isPieceEdgeBandVisible(keyB), true);
    const ui = store.edgeBandGlobalUiState();
    assert.equal(ui.indeterminate, true);
}

// Override survives selection changes / sheet moves in the same session.
{
    store.setShowEdgeBands(false);
    store.setPieceEdgeBandVisible(keyA, true);
    store.selectPiece(1, { pieceKey: keyB, sheetNo: 1, mode: "replace" });
    assert.equal(store.isPieceEdgeBandVisible(keyA), true);
    store.selectPiece(1, { pieceKey: keyA, sheetNo: 1, mode: "replace" });
    assert.equal(store.isPieceEdgeBandVisible(keyA), true);
    const piece = store.snapshot().session.pieces[keyA];
    piece.sheet_no = 1;
    assert.equal(store.isPieceEdgeBandVisible(keyA), true);
}

// DXF layer toggles stay independent of edge-band preference.
{
    store.setShowEdgeBands(true);
    store.setLayerVisible("CUT_PATH", false);
    assert.equal(store.snapshot().layerVisibility.CUT_PATH, false);
    assert.equal(store.snapshot().layerVisibility.GEOMETRY, true);
    assert.equal(store.snapshot().showEdgeBands, true);
    store.setAllLayersVisible(true);
    assert.equal(store.snapshot().showEdgeBands, true);
}

// Left sidebar shows display option before DXF layers; not a fake layer key.
{
    store.setShowEdgeBands(false);
    const host = makeHost();
    SidebarRenderer.render(host, store.snapshot(), {
        setShowEdgeBands: (visible) => store.setShowEdgeBands(visible),
        edgeBandGlobalUiState: () => store.edgeBandGlobalUiState(),
        setLayerVisible() {},
        setAllLayersVisible() {},
        showOnlyLayer() {},
        toggleSheet() {},
        selectSheet() {},
        selectPiece() {},
        setSidebarSplit() {},
    });
    assert.match(host.innerHTML, /data-abe-display-options/);
    assert.match(host.innerHTML, /data-abe-show-edge-bands/);
    assert.match(host.innerHTML, /Show edge banding/);
    assert.match(host.innerHTML, /data-layer-key="CUT_PATH"/);
    assert.doesNotMatch(host.innerHTML, /data-layer-key="[^"]*edge/i);
    const displayIdx = host.innerHTML.indexOf("data-abe-display-options");
    const cutIdx = host.innerHTML.indexOf('data-layer-key="CUT_PATH"');
    assert.ok(displayIdx >= 0 && cutIdx > displayIdx);
}

// Right sidebar: single selection only.
{
    store.selectPiece(1, { pieceKey: keyA, sheetNo: 1, mode: "replace" });
    const host = makeHost();
    RightSidebarRenderer.render(host, store.snapshot(), {
        setPieceEdgeBandVisible: (pieceKey, visible) => store.setPieceEdgeBandVisible(pieceKey, visible),
    });
    assert.match(host.innerHTML, /data-abe-piece-edge-bands/);
    assert.match(host.innerHTML, /Show edge banding for this piece/);
    assert.match(host.innerHTML, /data-abe-piece-key="instance:pi-a"/);

    store.selectPiece(1, { pieceKey: keyA, sheetNo: 1, mode: "replace" });
    store.selectPiece(1, { pieceKey: keyB, sheetNo: 1, mode: "toggle" });
    const multi = makeHost();
    RightSidebarRenderer.render(multi, store.snapshot(), {});
    assert.doesNotMatch(multi.innerHTML, /data-abe-piece-edge-bands/);
}

// Re-open style reset: new store defaults to hidden.
{
    const again = createStore({ projection, order_name: "O", plan_name: "P" });
    assert.equal(again.snapshot().showEdgeBands, false);
    assertNoOverrides(again);
}

// Asset pins + i18n.
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const arCsv = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
const storeSource = fs.readFileSync(path.join(root, "public/js/board_editor/store.js"), "utf8");
assert.match(page, /store\.js\?v=21/);
assert.match(page, /canvas_renderer\.js\?v=37/);
assert.match(page, /sidebar_renderer\.js\?v=21/);
assert.match(page, /right_sidebar_renderer\.js\?v=5/);
assert.match(page, /controller\.js\?v=34/);
assert.match(page, /board_editor\.css\?v=38/);
assert.match(storeSource, /showEdgeBands:\s*false/);
assert.match(storeSource, /pieceEdgeBandOverrides/);
assert.match(
    storeSource,
    /function sessionFingerprint\(\) \{\s*const api = window\.AlmdinaBoardEditor && window\.AlmdinaBoardEditor\.SessionDocument;\s*if \(!api \|\| !state\.session\) return "";\s*return api\.distributionFingerprint\(state\.session\);\s*\}/
);
assert.doesNotMatch(storeSource, /distributionFingerprint\([^)]*showEdgeBands/);
assert.doesNotMatch(storeSource, /history\.commit[\s\S]{0,80}showEdgeBands/);
[
    "Display options",
    "Show edge banding",
    "Show edge banding for this piece",
    "Show edge banding marks on pieces",
    "Show edge banding marks for this piece only",
].forEach((messageId) => {
    assert.ok(arCsv.includes(messageId), `missing ar.csv key: ${messageId}`);
});

console.log("board_editor_edge_band_visibility.test.js: ok");
