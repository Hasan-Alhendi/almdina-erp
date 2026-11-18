"use strict";

// Dropping a piece used to rebuild the canvas from the stored viewport scroll
// while the stage was still showing the drag camera. These tests drive that
// rebuild, including a second paint from setDropMessage().

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const VIEW_W = 900;
const VIEW_H = 600;

function load() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/snap_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/plan_display_style.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        console,
        document: {
            createElementNS: () => ({
                setAttribute() {},
                style: {},
                appendChild() {},
                childNodes: [],
            }),
        },
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(
            fs.readFileSync(path.join(root, relative), "utf8"),
            context,
            { filename: relative }
        );
    });
    return context.window.AlmdinaBoardEditor;
}

function sheet(sheetNo) {
    return {
        sheet_no: sheetNo,
        full_width_cm: 122,
        full_length_cm: 244,
        applied_trim_width_cm: 0,
        applied_trim_length_cm: 0,
        usable_width_cm: 122,
        usable_length_cm: 244,
    };
}

function piece(id, sheetNo, x, y) {
    return {
        piece_id: id,
        piece_instance_id: `pi-${id}`,
        label: String(id),
        sheet_no: sheetNo,
        piece_type: "Regular",
        placement_cm: { x, y, w: 40, h: 30, rotated: false },
        allow_rotation: true,
    };
}

function projectionFor(sheets, pieces) {
    const elements = [];
    sheets.forEach((row) => {
        elements.push({
            element_id: `sheet:${row.sheet_no}`,
            kind: "sheet_outline",
            layer_match_key: "sheet_outline",
            sheet_no: row.sheet_no,
            payload: {
                full_width_cm: row.full_width_cm,
                full_length_cm: row.full_length_cm,
                usable_width_cm: row.usable_width_cm,
                usable_length_cm: row.usable_length_cm,
                applied_trim_width_cm: 0,
                applied_trim_length_cm: 0,
            },
        });
    });
    pieces.forEach((row) => {
        elements.push({
            element_id: `p${row.piece_id}`,
            kind: "placement_rect",
            layer_match_key: "geometry",
            sheet_no: row.sheet_no,
            piece_id: row.piece_id,
            piece_instance_id: row.piece_instance_id,
            payload: { placement_cm: row.placement_cm },
        });
    });
    return {
        board: { kerf_cm: 0.4 },
        layers: [{ match_key: "geometry", original_name: "GEOMETRY", aci_color: 5 }],
        sheets,
        pieces,
        elements,
    };
}

function makeHost() {
    const listeners = [];
    let html = "";
    let contentW = VIEW_W;
    let contentH = VIEW_H;
    let scrollLeft = 0;
    let scrollTop = 0;

    function clamp(value, content, view) {
        const max = Math.max(0, content - view);
        return Math.min(Math.max(0, Number(value) || 0), max);
    }

    const stage = {
        clientWidth: VIEW_W,
        clientHeight: VIEW_H,
        classList: {
            add() {},
            remove() {},
            toggle() {},
            contains() { return false; },
        },
        style: {},
        addEventListener(type, fn) { listeners.push({ type, fn }); },
        setPointerCapture() {},
        releasePointerCapture() {},
        getBoundingClientRect() {
            return { left: 0, top: 0, width: VIEW_W, height: VIEW_H, right: VIEW_W, bottom: VIEW_H };
        },
        querySelector() { return null; },
        querySelectorAll() { return []; },
    };
    function assignScroll(axis, value, silent) {
        const next = axis === "x"
            ? clamp(value, contentW, VIEW_W)
            : clamp(value, contentH, VIEW_H);
        const current = axis === "x" ? scrollLeft : scrollTop;
        if (axis === "x") scrollLeft = next;
        else scrollTop = next;
        if (!silent && next !== current) {
            listeners.filter((row) => row.type === "scroll").forEach((row) => row.fn());
        }
        return next;
    }
    Object.defineProperty(stage, "scrollLeft", {
        get() { return scrollLeft; },
        set(value) { assignScroll("x", value, false); },
    });
    Object.defineProperty(stage, "scrollTop", {
        get() { return scrollTop; },
        set(value) { assignScroll("y", value, false); },
    });
    const world = {
        setAttribute() {},
        querySelector() { return null; },
        querySelectorAll() { return []; },
        appendChild() {},
    };
    const svg = {
        setAttribute(name, value) {
            if (name === "width") contentW = Number(value) || contentW;
            if (name === "height") contentH = Number(value) || contentH;
            scrollLeft = clamp(scrollLeft, contentW, VIEW_W);
            scrollTop = clamp(scrollTop, contentH, VIEW_H);
        },
        getAttribute(name) {
            if (name === "width") return String(contentW);
            if (name === "height") return String(contentH);
            return null;
        },
        querySelector(sel) { return sel === ".abe-world" ? world : null; },
        querySelectorAll() { return []; },
        addEventListener() {},
    };
    const dummy = () => ({
        onclick: null,
        addEventListener() {},
        querySelector() { return null; },
        querySelectorAll() { return []; },
        setAttribute() {},
        style: {},
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    });
    const host = {
        clientWidth: VIEW_W,
        clientHeight: VIEW_H,
        style: {},
        get innerHTML() { return html; },
        set innerHTML(value) {
            html = String(value);
            const width = Number((html.match(/class="abe-svg"[^>]*width="([\d.]+)"/) || [])[1]);
            const height = Number((html.match(/class="abe-svg"[^>]*height="([\d.]+)"/) || [])[1]);
            contentW = width || VIEW_W;
            contentH = height || VIEW_H;
            scrollLeft = 0;
            scrollTop = 0;
            listeners.length = 0;
        },
        querySelector(sel) {
            if (sel === "[data-abe-stage]") return stage;
            if (sel === ".abe-svg") return svg;
            if (sel === ".abe-world") return world;
            return dummy();
        },
        querySelectorAll() { return []; },
    };
    return {
        host,
        html: () => html,
        maxScroll: () => ({
            x: Math.max(0, contentW - VIEW_W),
            y: Math.max(0, contentH - VIEW_H),
        }),
        setScroll(x, y, silent) {
            assignScroll("x", x, true);
            const appliedY = assignScroll("y", y, true);
            const appliedX = scrollLeft;
            if (!silent) {
                listeners.filter((row) => row.type === "scroll").forEach((row) => row.fn());
            }
            return { x: appliedX, y: appliedY };
        },
    };
}

const editor = load();
const { CanvasRenderer, SessionDocument, MoveGeometry, History, createStore } = editor;
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(page, /canvas_renderer\.js\?v=58/);
assert.match(page, /controller\.js\?v=57/);
assert.match(controllerSource, /cameraUnapplied/);

function createRig(sheets, pieces, options) {
    const projection = projectionFor(sheets, pieces);
    const columns = sheets.length > 1 ? 2 : 1;
    const scale = Number(options && options.scale) || 1;
    const layout = CanvasRenderer.sheetLayout(projection.sheets, columns);
    const session = SessionDocument.buildFromProjection(projection, layout);
    const history = History.create(session);
    const store = createStore({ projection });
    store.attachSession(history.get(), history);
    let token = 1;
    let appliedCamera = 0;
    let liveScroll = { x: 36, y: 48 };
    store.setViewport({
        scale,
        scrollX: 36,
        scrollY: 48,
        padX: 16,
        padY: 16,
        trailX: 16,
        trailY: 16,
        minX: 0,
        minY: 0,
        columns,
        opened: true,
        userAdjusted: true,
        fitted: false,
        cameraToken: token,
    });
    const ui = makeHost();
    const handlers = {
        readScroll: () => ({ ...liveScroll }),
        onScroll: (x, y) => {
            liveScroll = { x: Number(x) || 0, y: Number(y) || 0 };
        },
        cameraUnapplied: (next) => next !== appliedCamera,
        takeCamera: (next) => {
            if (next === appliedCamera) return false;
            appliedCamera = next;
            return true;
        },
        persistCamera: (partial) => {
            if (partial.scrollX != null || partial.scrollY != null) {
                liveScroll = {
                    x: partial.scrollX != null ? Number(partial.scrollX) || 0 : liveScroll.x,
                    y: partial.scrollY != null ? Number(partial.scrollY) || 0 : liveScroll.y,
                };
            }
            store.patchViewport(partial);
        },
    };
    function paint() {
        return CanvasRenderer.render(ui.host, store.snapshot(), handlers);
    }
    function camera() {
        const metrics = ui.host.__abeWorldMetrics;
        return {
            scale: Number(metrics.scale) || 1,
            scrollX: ui.host.querySelector("[data-abe-stage]").scrollLeft,
            scrollY: ui.host.querySelector("[data-abe-stage]").scrollTop,
            padX: Number(metrics.padX),
            padY: Number(metrics.padY),
            minX: Number(metrics.minX) || 0,
            minY: Number(metrics.minY) || 0,
            worldW: Number(metrics.width) || 1,
            worldH: Number(metrics.height) || 1,
        };
    }
    paint();
    return {
        store,
        ui,
        paint,
        camera,
        live: () => liveScroll,
        keys: Object.keys(session.pieces),
        session: () => store.snapshot().session,
        pan(x, y, silent) {
            const max = ui.maxScroll();
            const targetX = Math.min(x, max.x);
            const targetY = Math.min(y, max.y);
            assert.ok(
                x <= max.x + 0.5 && y <= max.y + 0.5,
                `pan ${x},${y} does not fit in ${max.x},${max.y}`
            );
            const stale = { ...liveScroll };
            const applied = ui.setScroll(targetX, targetY, silent);
            if (silent) liveScroll = stale;
            assert.ok(Math.abs(applied.x - targetX) <= 1, `pan x clamped to ${applied.x}`);
            assert.ok(Math.abs(applied.y - targetY) <= 1, `pan y clamped to ${applied.y}`);
            return applied;
        },
        command(partial) {
            token += 1;
            store.setViewport({
                ...store.snapshot().viewport,
                ...partial,
                opened: true,
                userAdjusted: true,
                cameraToken: token,
            });
        },
    };
}

function screenOf(point, camera) {
    return CanvasRenderer.worldToScreen(point.x, point.y, camera);
}

function assertHeld(label, before, after, points) {
    assert.equal(after.scale, before.scale, `${label} scale ${before.scale} -> ${after.scale}`);
    points.forEach((point) => {
        const start = screenOf(point, before);
        const end = screenOf(point, after);
        const drift = Math.hypot(end.x - start.x, end.y - start.y);
        assert.ok(
            drift <= 1,
            `${label} point ${point.x},${point.y} drifted ${drift}px `
            + `(${start.x},${start.y} -> ${end.x},${end.y}); `
            + `scroll ${before.scrollX},${before.scrollY} -> ${after.scrollX},${after.scrollY}`
        );
        console.log(
            `${label}: scroll ${before.scrollX},${before.scrollY} -> ${after.scrollX},${after.scrollY}`
            + ` scale ${after.scale} drift ${drift}`
        );
    });
}

function dropPiece(rig, key, x, y) {
    const proposal = MoveGeometry.proposePieceDrop(rig.session(), key, x, y);
    assert.equal(proposal.ok, true, proposal.reason || proposal.code);
    const next = MoveGeometry.applyPieceMove(rig.session(), proposal);
    rig.store.commitSession(next);
    rig.paint();
    rig.store.setDropMessage(null);
    rig.paint();
}

function piecePoint(rig, key) {
    const fp = MoveGeometry.worldFootprint(rig.session().pieces[key], rig.session().boards);
    return { x: fp.bounds.x + 5, y: fp.bounds.y + 5 };
}

const anchor = { x: 400, y: 220 };

// Far right, with the scroll event already copied into liveScroll.
{
    const rig = createRig([sheet(1)], [piece(1, 1, 10, 12)]);
    const key = rig.keys[0];
    rig.store.selectPiece(1, { pieceKey: key, sheetNo: 1 });
    rig.pan(640, 980, false);
    const before = rig.camera();
    dropPiece(rig, key, 4200, 360);
    const after = rig.camera();
    assertHeld("far-right drop", before, after, [anchor, piecePoint(rig, key)]);
    assert.match(rig.ui.html(), new RegExp(`data-abe-selection-for="${key}"`));
    assert.match(rig.ui.html(), /is-selected/);
    rig.paint();
    assertHeld("far-right extra paint", before, rig.camera(), [anchor]);
    const held = rig.camera();
    assertHeld("far-right third paint", before, held, [anchor]);
    assert.ok(Math.abs(rig.live().x - held.scrollX) <= 1);
    assert.ok(Math.abs(rig.live().y - held.scrollY) <= 1);
    const stale = createRig([sheet(1)], [piece(11, 1, 10, 12)]);
    const staleKey = stale.keys[0];
    stale.store.selectPiece(11, { pieceKey: staleKey, sheetNo: 1 });
    stale.pan(640, 980, true);
    const staleBefore = stale.camera();
    dropPiece(stale, staleKey, 4200, 360);
    assertHeld("far-right before scroll event", staleBefore, stale.camera(), [anchor, piecePoint(stale, staleKey)]);
    rig.store.undo();
    rig.paint();
    assertHeld("undo after far-right", held, rig.camera(), [anchor]);
    rig.store.redo();
    rig.paint();
    assertHeld("redo after far-right", held, rig.camera(), [anchor]);
}

// Fractional scale: growing the world changes the stored trail, which used to
// rebuild the camera from the old viewport instead of the stage.
{
    const rig = createRig([sheet(1)], [piece(8, 1, 10, 12)], { scale: 0.35 });
    const key = rig.keys[0];
    rig.store.selectPiece(8, { pieceKey: key, sheetNo: 1 });
    const room = rig.ui.maxScroll();
    rig.pan(Math.min(150, room.x), Math.min(240, room.y), false);
    const before = rig.camera();
    assert.ok(Math.abs(before.scrollY - 48) > 20);
    dropPiece(rig, key, 3600, 280);
    assertHeld("far-right fractional world", before, rig.camera(), [anchor, piecePoint(rig, key)]);
}

// Far down, and a pointerup that lands before the scroll listener runs.
{
    const rig = createRig([sheet(1)], [piece(2, 1, 20, 30)]);
    const key = rig.keys[0];
    rig.store.selectPiece(2, { pieceKey: key, sheetNo: 1 });
    rig.pan(180, 1240, true);
    assert.ok(Math.abs(rig.live().y - 48) < 1e-6, "stale liveScroll must stay at the stored camera");
    const before = rig.camera();
    assert.ok(before.scrollY > 1000);
    dropPiece(rig, key, 240, 5200);
    assertHeld("far-down stale scroll", before, rig.camera(), [anchor, piecePoint(rig, key)]);
    rig.store.setDropMessage("placed");
    rig.paint();
    rig.store.setDropMessage(null);
    rig.paint();
    assertHeld("far-down message repaint", before, rig.camera(), [anchor]);
}

// Negative world origin, including a piece that is already outside the boards.
{
    const rig = createRig([sheet(1)], [piece(3, 1, 15, 18)]);
    const key = rig.keys[0];
    rig.store.selectPiece(3, { pieceKey: key, sheetNo: 1 });
    rig.pan(80, 90, false);
    const first = rig.camera();
    dropPiece(rig, key, -1600, -700);
    assertHeld("first negative drop", first, rig.camera(), [anchor, piecePoint(rig, key)]);
    assert.ok(rig.camera().minX < 0 && rig.camera().minY < 0);
    rig.pan(40, 70, true);
    const before = rig.camera();
    dropPiece(rig, key, -2400, -1100);
    const afterNegative = rig.camera();
    assertHeld("negative outside move", before, afterNegative, [anchor, piecePoint(rig, key)]);
    assert.ok(afterNegative.minX < -1600);
    rig.store.undo();
    rig.paint();
    assertHeld("undo negative move", afterNegative, rig.camera(), [anchor]);
    rig.store.redo();
    rig.paint();
    assertHeld("redo negative move", afterNegative, rig.camera(), [anchor]);
}

// Board to board, several selected pieces, and a whole board.
{
    const rig = createRig(
        [sheet(1), sheet(2)],
        [piece(4, 1, 12, 16), piece(5, 1, 70, 20)]
    );
    const [keyA, keyB] = rig.keys;
    rig.store.selectPieces([keyA, keyB]);
    rig.pan(520, 760, false);
    const board2 = rig.session().boards["2"];
    const beforeBoard = rig.camera();
    dropPiece(rig, keyA, board2.origin_x_mm + 30, board2.origin_y_mm + 40);
    assert.equal(rig.session().pieces[keyA].sheet_no, 2);
    assertHeld("board-to-board", beforeBoard, rig.camera(), [anchor, piecePoint(rig, keyA)]);

    const beforeGroup = rig.camera();
    const group = MoveGeometry.proposeGroupMove(rig.session(), [keyA, keyB], 2800, 640);
    assert.equal(group.ok, true, group.reason || group.code);
    let next = rig.session();
    group.commands.forEach((command) => {
        next = MoveGeometry.applyPieceMove(next, command);
    });
    rig.store.commitSession(next);
    rig.paint();
    rig.store.setDropMessage(null);
    rig.paint();
    assertHeld("group drop", beforeGroup, rig.camera(), [anchor, piecePoint(rig, keyA), piecePoint(rig, keyB)]);
    assert.match(rig.ui.html(), new RegExp(keyA));
    assert.match(rig.ui.html(), new RegExp(keyB));

    const beforeSheet = rig.camera();
    const movedBoard = MoveGeometry.proposeBoardDrop(rig.session(), 2, 4600, 1800);
    assert.equal(movedBoard.ok, true, movedBoard.reason || movedBoard.code);
    const boarded = MoveGeometry.applyBoardMove(rig.session(), {
        sheet_no: 2,
        origin_x_mm: movedBoard.origin_x_mm,
        origin_y_mm: movedBoard.origin_y_mm,
    });
    rig.store.commitSession(boarded);
    rig.paint();
    rig.store.setDropMessage(null);
    rig.paint();
    assertHeld("board drag", beforeSheet, rig.camera(), [anchor]);
}

// Auto-scroll that the browser already clamped, then a drop that grows the world.
{
    const rig = createRig([sheet(1)], [piece(6, 1, 8, 14)]);
    const key = rig.keys[0];
    const max = rig.ui.maxScroll();
    const applied = rig.ui.setScroll(max.x + 5000, max.y + 5000, true);
    assert.ok(Math.abs(applied.x - max.x) <= 1);
    assert.ok(Math.abs(applied.y - max.y) <= 1);
    const before = rig.camera();
    dropPiece(rig, key, 3900, 4700);
    const after = rig.camera();
    assertHeld("clamped autoscroll drop", before, after, [anchor, piecePoint(rig, key)]);
    assert.ok(after.scrollX + 1 >= before.scrollX);
    assert.ok(after.scrollY + 1 >= before.scrollY);
}

// Zoom around a pointer, then Fit All, both as explicit camera commands.
{
    const rig = createRig([sheet(1)], [piece(7, 1, 18, 22)]);
    rig.pan(610, 880, false);
    const before = rig.camera();
    const focal = { x: 260, y: 180 };
    const world = CanvasRenderer.cameraPointToWorld(
        before.scrollX,
        before.scrollY,
        focal.x,
        focal.y,
        before.scale,
        before
    );
    const zoomed = CanvasRenderer.zoomAroundFocal(
        before,
        focal,
        1.25,
        { width: VIEW_W, height: VIEW_H },
        { width: before.worldW, height: before.worldH }
    );
    assert.ok(
        Math.abs(zoomed.scrollX - before.scrollX) > 1 || Math.abs(zoomed.scrollY - before.scrollY) > 1,
        "zoom fixture must change scroll"
    );
    rig.command({
        scale: zoomed.scale,
        scrollX: zoomed.scrollX,
        scrollY: zoomed.scrollY,
        padX: zoomed.padX,
        padY: zoomed.padY,
        trailX: zoomed.trailX,
        trailY: zoomed.trailY,
        minX: zoomed.minX,
        minY: zoomed.minY,
        fitted: false,
    });
    rig.paint();
    const afterZoom = rig.camera();
    assert.ok(Math.abs(afterZoom.scale - zoomed.scale) < 1e-9);
    assert.ok(Math.abs(afterZoom.scrollX - zoomed.scrollX) <= 1, `zoom scrollX ${afterZoom.scrollX} vs ${zoomed.scrollX}`);
    assert.ok(Math.abs(afterZoom.scrollY - zoomed.scrollY) <= 1, `zoom scrollY ${afterZoom.scrollY} vs ${zoomed.scrollY}`);
    const zoomedScreen = screenOf(world, afterZoom);
    assert.ok(Math.abs(zoomedScreen.x - focal.x) <= 1, `zoom focal x ${zoomedScreen.x}`);
    assert.ok(Math.abs(zoomedScreen.y - focal.y) <= 1, `zoom focal y ${zoomedScreen.y}`);
    rig.paint();
    assertHeld("zoom holds on the next paint", afterZoom, rig.camera(), [world, anchor]);

    const layout = CanvasRenderer.mergeSessionLayout(
        CanvasRenderer.sheetLayout(rig.store.snapshot().projection.sheets, 1),
        rig.session()
    );
    const fitted = CanvasRenderer.fitBoards(layout.fitBounds, VIEW_W, VIEW_H);
    assert.ok(fitted);
    rig.command({
        scale: fitted.scale,
        scrollX: fitted.scrollX,
        scrollY: fitted.scrollY,
        padX: fitted.padX,
        padY: fitted.padY,
        minX: Number(layout.worldMinX) || 0,
        minY: Number(layout.worldMinY) || 0,
        fitted: true,
    });
    const panScroll = rig.camera();
    rig.paint();
    const afterFit = rig.camera();
    assert.ok(Math.abs(afterFit.scale - fitted.scale) < 1e-9);
    assert.ok(Math.abs(afterFit.scrollX - fitted.scrollX) <= 1, `fit scrollX ${afterFit.scrollX}`);
    assert.ok(Math.abs(afterFit.scrollY - fitted.scrollY) <= 1, `fit scrollY ${afterFit.scrollY}`);
    assert.ok(
        Math.abs(afterFit.scrollX - panScroll.scrollX) > 20
        || Math.abs(afterFit.scrollY - panScroll.scrollY) > 20,
        "fit must replace the panned camera"
    );
}

console.log("board_editor_camera_drop_stability.test.js: ok");
