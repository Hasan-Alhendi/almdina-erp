"use strict";

/**
 * Reproduces the post-rotation ghost: selection follows world local_x while
 * material was drawn with entry+world_delta (missing board origin) after leaving
 * a board that is not at world (0,0).
 */

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
        "public/js/board_editor/plan_display_style.js",
        "public/js/board_editor/plan_edge_marks.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        document: {
            createElementNS: () => ({
                setAttribute() {},
                style: {},
                appendChild() {},
            }),
        },
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
    const listeners = {};
    const stage = {
        clientWidth: 1100,
        clientHeight: 700,
        scrollLeft: 0,
        scrollTop: 0,
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
        style: {},
        addEventListener(type, fn) {
            listeners[`stage:${type}`] = fn;
        },
        querySelector() { return null; },
        setPointerCapture() {},
        releasePointerCapture() {},
        getBoundingClientRect() {
            return { left: 0, top: 0, width: 1100, height: 700, right: 1100, bottom: 700 };
        },
    };
    const svg = {
        querySelectorAll() { return []; },
        addEventListener() {},
        getBoundingClientRect() {
            return { left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600 };
        },
    };
    const host = {
        clientWidth: 1100,
        clientHeight: 760,
        style: {},
        __html: "",
        set innerHTML(value) {
            this.__html = String(value);
        },
        get innerHTML() {
            return this.__html;
        },
        querySelector(sel) {
            if (sel === "[data-abe-stage]") return stage;
            if (sel === ".abe-svg") return svg;
            if (sel === ".abe-world") {
                return {
                    querySelector() { return null; },
                    querySelectorAll() { return []; },
                    appendChild() {},
                };
            }
            return {
                onclick: null,
                addEventListener() {},
                querySelectorAll() { return []; },
            };
        },
        querySelectorAll() { return []; },
    };
    return host;
}

function parsePathBounds(html, pieceKey) {
    const escaped = pieceKey.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const blockRe = new RegExp(
        `data-piece-key="${escaped}"[\\s\\S]*?<path[^>]*\\sd="([^"]+)"`,
        "g"
    );
    const points = [];
    let match = blockRe.exec(html);
    while (match) {
        const nums = match[1].match(/-?\d+(?:\.\d+)?/g) || [];
        for (let i = 0; i + 1 < nums.length; i += 2) {
            points.push([Number(nums[i]), Number(nums[i + 1])]);
        }
        match = blockRe.exec(html);
    }
    assert.ok(points.length >= 4, `expected material path for ${pieceKey}`);
    const xs = points.map((point) => point[0]);
    const ys = points.map((point) => point[1]);
    return {
        x: Math.min(...xs),
        y: Math.min(...ys),
        w: Math.max(...xs) - Math.min(...xs),
        h: Math.max(...ys) - Math.min(...ys),
    };
}

function parseSelectionBounds(html) {
    const match = html.match(/abe-selection-chrome[\s\S]*?d="([^"]+)"/);
    assert.ok(match, "expected selection chrome path");
    const nums = match[1].match(/-?\d+(?:\.\d+)?/g) || [];
    const points = [];
    for (let i = 0; i + 1 < nums.length; i += 2) {
        points.push([Number(nums[i]), Number(nums[i + 1])]);
    }
    const xs = points.map((point) => point[0]);
    const ys = points.map((point) => point[1]);
    return {
        x: Math.min(...xs),
        y: Math.min(...ys),
        w: Math.max(...xs) - Math.min(...xs),
        h: Math.max(...ys) - Math.min(...ys),
    };
}

const editor = load();
const { MoveGeometry, SessionDocument, CanvasRenderer, createStore, History, RotationGeometry } = editor;

const projection = {
    board: { kerf_cm: 0.4 },
    layers: [{ match_key: "geometry", original_name: "GEOMETRY", aci_color: 5 }],
    sheets: [
        {
            sheet_no: 3,
            full_width_cm: 122,
            full_length_cm: 244,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
            usable_width_cm: 122,
            usable_length_cm: 244,
        },
    ],
    pieces: [
        {
            piece_id: 31,
            piece_instance_id: "pi-3-1",
            label: "3.1",
            sheet_no: 3,
            piece_type: "Regular",
            placement_cm: { x: 20, y: 30, w: 40, h: 25, rotated: false },
            allow_rotation: true,
            allow_rotation_proven: true,
        },
    ],
    elements: [
        {
            element_id: "p31:placement",
            kind: "placement_rect",
            layer_match_key: "geometry",
            layer_original_name: "GEOMETRY",
            sheet_no: 3,
            piece_id: 31,
            piece_instance_id: "pi-3-1",
            payload: {
                placement_cm: { x: 20, y: 30, w: 40, h: 25, rotated: false },
                apply_rotated_to_dimensions: true,
            },
            aci_color: 5,
        },
        {
            element_id: "sheet:3:outline",
            kind: "sheet_outline",
            layer_match_key: "sheet_outline",
            sheet_no: 3,
            payload: {
                full_width_cm: 122,
                full_length_cm: 244,
                usable_width_cm: 122,
                usable_length_cm: 244,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
            },
        },
    ],
};

// Put board 3 on the right column so its usable origin is far from world 0.
const layout = CanvasRenderer.sheetLayout(projection.sheets, 2);
layout.positions["3"] = {
    originX: 1300,
    originY: 36,
    titleY: 26,
    widthMm: 1220,
    heightMm: 2440,
    trimX: 0,
    trimY: 0,
    sheetNo: 3,
};

let session = SessionDocument.buildFromProjection(projection, layout);
session.boards["3"].origin_x_mm = 1300;
session.boards["3"].origin_y_mm = 36;
const pieceKey = "instance:pi-3-1";
assert.equal(Object.keys(session.pieces).length, 1);

const beforeWorld = MoveGeometry.worldFootprint(session.pieces[pieceKey], session.boards);
assert.ok(Math.abs(beforeWorld.bounds.x - 1500) < 1e-6);

// Move the piece fully outside to the right of the board.
const outsideX = 2700;
const outsideY = beforeWorld.bounds.y;
const proposal = MoveGeometry.proposePieceDrop(session, pieceKey, outsideX, outsideY);
assert.equal(proposal.ok, true);
assert.equal(proposal.target_sheet_no, null);
session = MoveGeometry.applyPieceMove(session, proposal);
assert.equal(session.pieces[pieceKey].sheet_no, null);
assert.equal(Object.keys(session.pieces).length, 1);

const afterWorld = MoveGeometry.worldFootprint(session.pieces[pieceKey], session.boards);
assert.ok(Math.abs(afterWorld.bounds.x - outsideX) < 1e-6, `world x ${afterWorld.bounds.x}`);
assert.ok(Math.abs(afterWorld.bounds.y - outsideY) < 1e-6, `world y ${afterWorld.bounds.y}`);

const history = History.create(session);
const store = createStore({
    projection,
    orderName: "ORD",
    planName: "PLAN",
});
store.attachSession(history.get(), history);
store.selectPiece(31, { pieceKey, sheetNo: null, expandSheet: true });
store.setViewport({
    scale: 0.4,
    scrollX: 0,
    scrollY: 0,
    columns: 2,
    opened: true,
    userAdjusted: true,
    fitted: false,
    cameraToken: 1,
});

const host = makeHost();
CanvasRenderer.render(host, store.snapshot(), {});
const html = host.innerHTML;
assert.equal((html.match(/data-piece-key="instance:pi-3-1"/g) || []).length >= 1, true);

const material = parsePathBounds(html, pieceKey);
const selection = parseSelectionBounds(html);
assert.ok(Math.abs(material.x - selection.x) < 1.5, `material.x=${material.x} selection.x=${selection.x}`);
assert.ok(Math.abs(material.y - selection.y) < 1.5, `material.y=${material.y} selection.y=${selection.y}`);
assert.ok(Math.abs(material.w - selection.w) < 1.5);
assert.ok(Math.abs(material.h - selection.h) < 1.5);
assert.ok(material.x > 2000, "material must stay in the outside/world seat, not the old board frame");
assert.match(html, /fill="#e4f5ff"/, "regular piece uses the cutting-plan fill, not the old blue wash");
assert.equal((html.match(/data-piece-key="instance:pi-3-1"/g) || []).length, 1);

// Rotate 37° then move again: selection and material remain aligned.
let rotated = RotationGeometry.applyPieceRotation(session, pieceKey, 37);
const rotatedWorld = MoveGeometry.worldFootprint(rotated.pieces[pieceKey], rotated.boards);
const movedAgain = MoveGeometry.proposePieceDrop(
    rotated,
    pieceKey,
    rotatedWorld.bounds.x + 80,
    rotatedWorld.bounds.y + 40
);
assert.equal(movedAgain.ok, true);
rotated = MoveGeometry.applyPieceMove(rotated, movedAgain);
history.commit(rotated);
store.selectPiece(31, { pieceKey, sheetNo: null, expandSheet: true });
CanvasRenderer.render(host, store.snapshot(), {});
const html2 = host.innerHTML;
const material2 = parsePathBounds(html2, pieceKey);
const selection2 = parseSelectionBounds(html2);
assert.ok(Math.abs(material2.x - selection2.x) < 1.5);
assert.ok(Math.abs(material2.y - selection2.y) < 1.5);
assert.equal((html2.match(/data-piece-key="instance:pi-3-1"/g) || []).length, 1);

// L-shaped parametric outline plus liner overlay share the same session transform.
const lProjection = {
    board: { kerf_cm: 0.4 },
    layers: [
        { match_key: "GEOMETRY", original_name: "GEOMETRY" },
        { match_key: "LINER", original_name: "Liner" },
    ],
    sheets: [{
        sheet_no: 1,
        full_width_cm: 122,
        full_length_cm: 244,
        applied_trim_width_cm: 0.5,
        applied_trim_length_cm: 0.5,
        usable_width_cm: 121,
        usable_length_cm: 243,
    }],
    pieces: [{
        piece_id: 4,
        piece_instance_id: "pi-l",
        label: "4.1",
        sheet_no: 1,
        piece_type: "L-Shaped Corner",
        fill_role: "l_shaped",
        placement_cm: { x: 10, y: 12, w: 40, h: 60, rotated: false },
        allow_rotation: true,
        allow_rotation_proven: true,
    }],
    elements: [
        {
            element_id: "sheet:1:outline",
            kind: "sheet_outline",
            layer_match_key: "SHEET_OUTLINE",
            sheet_no: 1,
            payload: {
                full_width_cm: 122,
                full_length_cm: 244,
                usable_width_cm: 121,
                usable_length_cm: 243,
                applied_trim_width_cm: 0.5,
                applied_trim_length_cm: 0.5,
                resource_kind: "FULL_BOARD",
            },
        },
        {
            element_id: "p4:outer",
            kind: "finished_outline",
            layer_match_key: "GEOMETRY",
            layer_original_name: "GEOMETRY",
            sheet_no: 1,
            piece_id: 4,
            piece_instance_id: "pi-l",
            payload: {
                fill_role: "l_shaped",
                geometry_source: "placed_parametric_polygon",
                display_edges: { edge_long_left: 1, edge_width_top: 0, edge_width_bottom: 0, edge_long_right: 0 },
            },
            geometry: {
                outer: [[100, 120], [280, 120], [280, 300], [500, 300], [500, 720], [100, 720]],
                holes: [],
            },
        },
        {
            element_id: "p4:liner",
            kind: "addon_overlay",
            layer_match_key: "LINER",
            layer_original_name: "Liner",
            sheet_no: 1,
            piece_id: 4,
            piece_instance_id: "pi-l",
            payload: { kind: "liner", synthetic: true, geometry_source: "parametric_visual" },
            geometry: { path: [[120, 140], [120, 500]], closed: false },
        },
    ],
};
const lLayout = CanvasRenderer.sheetLayout(lProjection.sheets, 1);
let lSession = SessionDocument.buildFromProjection(lProjection, lLayout);
const lKey = "instance:pi-l";
const lHistory = History.create(lSession);
const lStore = createStore({ projection: lProjection, orderName: "ORD", planName: "PLAN" });
lStore.attachSession(lHistory.get(), lHistory);
lStore.selectPiece(4, { pieceKey: lKey, sheetNo: 1, expandSheet: true });
lStore.setViewport({
    scale: 0.5,
    scrollX: 0,
    scrollY: 0,
    columns: 1,
    opened: true,
    userAdjusted: true,
    fitted: false,
    cameraToken: 2,
});
const lHost = makeHost();
CanvasRenderer.render(lHost, lStore.snapshot(), {});
const lHtml = lHost.innerHTML;
assert.match(lHtml, /data-fill-role="l_shaped"/);
assert.match(lHtml, /fill="#fff0c7"/);
assert.match(lHtml, /stroke="#8a5700"/);
assert.match(lHtml, /stroke="#1d6fbf"/);
assert.match(lHtml, /class="abe-piece-size"/);
assert.match(lHtml, /abe-board-waste-hatch/);
const lBefore = parsePathBounds(lHtml, lKey);
lSession = RotationGeometry.applyPieceRotation(lSession, lKey, 15);
const worldBeforeDrop = MoveGeometry.worldFootprint(lSession.pieces[lKey], lSession.boards);
const drop = MoveGeometry.proposePieceDrop(
    lSession,
    lKey,
    worldBeforeDrop.bounds.x + 40,
    worldBeforeDrop.bounds.y + 25
);
assert.equal(drop.ok, true);
lSession = MoveGeometry.applyPieceMove(lSession, drop);
lHistory.commit(lSession);
lStore.commitSession(lSession);
CanvasRenderer.render(lHost, lStore.snapshot(), {});
const lAfter = lHost.innerHTML;
const lMoved = parsePathBounds(lAfter, lKey);
const worldAfter = MoveGeometry.worldFootprint(lSession.pieces[lKey], lSession.boards);
assert.ok(Math.abs(lMoved.x - worldAfter.bounds.x) < 2, `drawn ${lMoved.x} world ${worldAfter.bounds.x}`);
assert.ok(Math.abs(worldAfter.bounds.x - (worldBeforeDrop.bounds.x + 40)) < 2);
const pieceMarks = (lAfter.match(/data-piece-key="instance:pi-l"/g) || []).length;
assert.ok(pieceMarks >= 2 && pieceMarks <= 3, `expected outline and liner marks, got ${pieceMarks}`);
assert.match(lAfter, /stroke="#1d6fbf"/);

// Cross-sheet session move: projection element order can place the piece markup
// before the destination sheet frame. Frame must still paint under the piece.
{
    const crossProjection = {
        board: { kerf_cm: 0.4 },
        layers: [{ match_key: "GEOMETRY", original_name: "GEOMETRY", aci_color: 7 }],
        sheets: [
            {
                sheet_no: 1,
                full_width_cm: 122,
                full_length_cm: 244,
                usable_width_cm: 122,
                usable_length_cm: 244,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
            },
            {
                sheet_no: 3,
                full_width_cm: 122,
                full_length_cm: 244,
                usable_width_cm: 122,
                usable_length_cm: 244,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
            },
        ],
        pieces: [
            {
                piece_id: 10,
                piece_instance_id: "pi-cross",
                label: "Cross",
                sheet_no: 3,
                placement_cm: { x: 0, y: 0, w: 50, h: 40 },
                fill_role: "regular",
            },
            {
                piece_id: 11,
                piece_instance_id: "pi-keep",
                label: "Keep",
                sheet_no: 1,
                placement_cm: { x: 10, y: 120, w: 40, h: 30 },
                fill_role: "regular",
            },
        ],
        elements: [
            {
                element_id: "p-cross",
                kind: "finished_outline",
                sheet_no: 3,
                piece_id: 10,
                piece_instance_id: "pi-cross",
                layer_match_key: "GEOMETRY",
                payload: { fill_role: "regular" },
                geometry: { outer: [[0, 0], [500, 0], [500, 400], [0, 400]], holes: [] },
            },
            {
                element_id: "sheet:1",
                kind: "sheet_outline",
                sheet_no: 1,
                layer_match_key: "SHEET",
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
                element_id: "sheet:3",
                kind: "sheet_outline",
                sheet_no: 3,
                layer_match_key: "SHEET",
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
                element_id: "p-keep",
                kind: "finished_outline",
                sheet_no: 1,
                piece_id: 11,
                piece_instance_id: "pi-keep",
                layer_match_key: "GEOMETRY",
                payload: { fill_role: "regular" },
                geometry: { outer: [[100, 1200], [500, 1200], [500, 1500], [100, 1500]], holes: [] },
            },
        ],
    };
    const crossLayout = CanvasRenderer.sheetLayout(crossProjection.sheets, 2);
    let crossSession = SessionDocument.buildFromProjection(crossProjection, crossLayout);
    const crossKey = "instance:pi-cross";
    // Simulate a completed cross-sheet session move (projection.sheet_no stays 3).
    crossSession = JSON.parse(JSON.stringify(crossSession));
    const moved = crossSession.pieces[crossKey];
    moved.sheet_no = 1;
    moved.local_x_mm = 20;
    moved.local_y_mm = 30;
    moved.outline_mm = [[20, 30], [520, 30], [520, 430], [20, 430]];
    assert.equal(crossSession.pieces[crossKey].sheet_no, 1);
    const crossHistory = History.create(crossSession);
    const crossStore = createStore({ projection: crossProjection, orderName: "ORD", planName: "PLAN" });
    crossStore.attachSession(crossHistory.get(), crossHistory);
    crossStore.selectPiece(10, { pieceKey: crossKey, sheetNo: 1, expandSheet: true });
    crossStore.setViewport({
        scale: 0.2,
        scrollX: 0,
        scrollY: 0,
        columns: 2,
        opened: true,
        userAdjusted: true,
        fitted: false,
        cameraToken: 3,
    });
    const crossHost = makeHost();
    CanvasRenderer.render(crossHost, crossStore.snapshot(), {});
    const crossHtml = crossHost.innerHTML;
    const groupStart = crossHtml.indexOf('<g data-sheet-group="1">');
    const groupEnd = crossHtml.indexOf('<g data-sheet-group="3">');
    assert.ok(groupStart >= 0 && groupEnd > groupStart, "sheet group 1 markup present");
    const groupHtml = crossHtml.slice(groupStart, groupEnd);
    const frameAt = groupHtml.indexOf('class="abe-sheet');
    const pieceAt = groupHtml.indexOf(`data-piece-key="${crossKey}"`);
    assert.ok(frameAt >= 0, "destination frame present");
    assert.ok(pieceAt >= 0, "moved piece present on destination sheet");
    assert.ok(frameAt < pieceAt, "sheet frame must paint under cross-sheet moved piece");
    assert.match(groupHtml, /data-piece-key="instance:pi-keep"/);

    // Live piece drag must elevate nodes above sheet groups so destination
    // board fills cannot cover the in-flight piece still parented under origin.
    const rendererSrc = fs.readFileSync(
        path.join(root, "public/js/board_editor/canvas_renderer.js"),
        "utf8"
    );
    assert.match(rendererSrc, /data-abe-drag-layer/);
    assert.match(rendererSrc, /function ensureDragLayer\(/);
    assert.match(rendererSrc, /function elevateDragNode\(/);
    assert.match(rendererSrc, /preview\.kind === "piece"[\s\S]*ensureDragLayer\(\)/);
}

console.log("board_editor_render_move.test.js: ok");
