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
        "public/js/board_editor/store.js",
        "public/js/board_editor/move_interaction.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        document: {
            createElementNS: () => ({
                setAttribute() {},
                style: {},
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

const editor = load();
const { MoveGeometry, SnapGeometry, createStore, History, createMoveInteraction } = editor;

assert.equal(SnapGeometry.SNAP_ENTER_PX, 8);
assert.equal(SnapGeometry.SNAP_EXIT_PX, 12);
assert.equal(SnapGeometry.thresholdMmFromScale(2, 8), 4);
assert.equal(SnapGeometry.thresholdMmFromScale(0.5, 8), 16);

const session = {
    boards: {
        1: {
            sheet_no: 1,
            origin_x_mm: 0,
            origin_y_mm: 0,
            width_mm: 1000,
            height_mm: 1000,
            trim_x_mm: 10,
            trim_y_mm: 10,
            usable_width_mm: 980,
            usable_length_mm: 980,
            title_band_mm: 36,
        },
    },
    pieces: {
        "instance:a": {
            piece_key: "instance:a",
            piece_id: 1,
            piece_instance_id: "a",
            sheet_no: 1,
            local_x_mm: 100,
            local_y_mm: 100,
            placement_cm: { x: 10, y: 10, w: 20, h: 20 },
            outline_mm: [[100, 100], [300, 100], [300, 300], [100, 300]],
            editable: true,
            glass_host_key: null,
        },
        "instance:b": {
            piece_key: "instance:b",
            piece_id: 2,
            piece_instance_id: "b",
            sheet_no: 1,
            local_x_mm: 500,
            local_y_mm: 100,
            placement_cm: { x: 50, y: 10, w: 20, h: 20 },
            outline_mm: [[500, 100], [700, 100], [700, 300], [500, 300]],
            editable: true,
            glass_host_key: null,
        },
        "instance:hidden": {
            piece_key: "instance:hidden",
            piece_id: 3,
            piece_instance_id: "hidden",
            sheet_no: 1,
            local_x_mm: 100,
            local_y_mm: 500,
            placement_cm: { x: 10, y: 50, w: 20, h: 10 },
            outline_mm: [[100, 500], [300, 500], [300, 600], [100, 600]],
            editable: true,
            glass_host_key: null,
        },
    },
    kerf_mm: 4,
    stale_cut_path_sheets: [],
    stale_unbound_text_sheets: [],
};

// Snap to usable left (world usable x = 10). Current world x = 110.
{
    const suggestion = SnapGeometry.suggestPieceSnap(session, "instance:a", 12, 110, {
        magnetEnabled: true,
        thresholdMm: 12,
    });
    assert.equal(suggestion.ok, true);
    const proposal = MoveGeometry.proposePieceDrop(
        session,
        "instance:a",
        110 + suggestion.dx,
        110 + suggestion.dy
    );
    assert.equal(proposal.ok, true);
    assert.equal(Math.round(proposal.local_x_mm), 0);
    assert.ok(suggestion.guides.length >= 1);
}

// Neighbour snap uses kerf once.
{
    const suggestion = SnapGeometry.suggestPieceSnap(session, "instance:a", 310, 110, {
        magnetEnabled: true,
        thresholdMm: 25,
    });
    assert.equal(suggestion.ok, true);
    const proposal = MoveGeometry.proposePieceDrop(
        session,
        "instance:a",
        110 + suggestion.dx,
        110 + suggestion.dy
    );
    assert.equal(proposal.ok, true);
    assert.equal(Math.round(proposal.local_x_mm + 200 + session.kerf_mm), 500);
}

// Magnet off / Alt path → no snap.
{
    const off = SnapGeometry.suggestPieceSnap(session, "instance:a", 12, 110, {
        magnetEnabled: false,
        thresholdMm: 12,
    });
    assert.equal(off.ok, false);
}

// Hidden piece still participates as a snap/validation target.
{
    const suggestion = SnapGeometry.suggestPieceSnap(session, "instance:a", 110, 400, {
        magnetEnabled: true,
        thresholdMm: 30,
    });
    if (suggestion.ok) {
        const proposal = MoveGeometry.proposePieceDrop(
            session,
            "instance:a",
            110 + suggestion.dx,
            110 + suggestion.dy
        );
        assert.equal(proposal.ok, true);
        // Must clear kerf against the hidden piece when snapping vertically near it.
        const aBottom = proposal.local_y_mm + 200;
        if (Math.abs(proposal.local_x_mm - 100) < 1) {
            assert.ok(aBottom + session.kerf_mm <= 500 + 1e-6 || proposal.local_y_mm >= 600 + session.kerf_mm - 1e-6);
        }
    }
}

// Self-group edges are not snap targets: host+guest moving together.
{
    const hosted = JSON.parse(JSON.stringify(session));
    hosted.pieces["instance:b"].glass_host_key = "instance:a";
    hosted.pieces["instance:b"].local_x_mm = 150;
    hosted.pieces["instance:b"].local_y_mm = 150;
    hosted.pieces["instance:b"].outline_mm = [[150, 150], [250, 150], [250, 250], [150, 250]];
    const ids = MoveGeometry.draggedPieceIds(hosted, "instance:a");
    assert.ok(ids.includes("instance:b"));
    const suggestion = SnapGeometry.suggestPieceSnap(hosted, "instance:a", 160, 160, {
        magnetEnabled: true,
        thresholdMm: 40,
    });
    if (suggestion.ok) {
        assert.notEqual(suggestion.source, "piece:instance:b");
    }
}

// Store magnet flag is session UI state, not History.
{
    const store = createStore({ projection: { sheets: [], pieces: [], layers: [] } });
    assert.equal(store.snapshot().magnetEnabled, true);
    store.toggleMagnet();
    assert.equal(store.snapshot().magnetEnabled, false);
    store.setMagnetEnabled(true);
    assert.equal(store.snapshot().magnetEnabled, true);
}

// Interaction applies snap to the committed delta and clears guides on cancel.
{
    let now = 0;
    const timers = new Map();
    let tid = 1;
    const store = createStore({ projection: { sheets: [], pieces: [], layers: [] } });
    const history = History.create(session);
    store.attachSession(history.get(), history);
    const stage = {
        classList: {
            _set: new Set(),
            toggle(name, on) { if (on) this._set.add(name); else this._set.delete(name); },
            contains(name) { return this._set.has(name); },
            add(name) { this._set.add(name); },
            remove(name) { this._set.delete(name); },
        },
        style: {},
        scrollLeft: 0,
        scrollTop: 0,
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 }),
    };
    const svg = { getBoundingClientRect: () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 }) };
    const target = { setPointerCapture() {}, releasePointerCapture() {} };
    let lastPreview = null;
    const interaction = createMoveInteraction({
        store,
        getStageEl: () => stage,
        getSvgEl: () => svg,
        getWorldMetrics: () => ({ minX: 0, minY: 0, width: 800, height: 600, scale: 1 }),
        getScale: () => 1,
        onPreview: (preview) => { lastPreview = preview; },
        isPanKey: () => false,
        isAltKey: () => false,
        now: () => now,
        setTimeout: (fn, ms) => { const id = tid++; timers.set(id, { at: now + ms, fn }); return id; },
        clearTimeout: (id) => timers.delete(id),
    });
    function advance(ms) {
        now += ms;
        [...timers.entries()].filter(([, row]) => row.at <= now).forEach(([id, row]) => {
            timers.delete(id);
            row.fn();
        });
    }
    function pointer(x, y) {
        return {
            button: 0,
            pointerId: 1,
            pointerType: "mouse",
            clientX: x,
            clientY: y,
            currentTarget: target,
            target,
            stopPropagation() {},
            preventDefault() {},
        };
    }

    // World metrics map client→world 1:1 with scale in metrics width/height matching svg.
    // piece world origin for a is (110,110). Start drag there, move near usable left.
    interaction.beginPieceGesture("instance:a", pointer(110, 110), { pieceId: 1 });
    interaction.onPointerMove(pointer(110 + 6, 110));
    interaction.onPointerMove(pointer(20, 110));
    assert.equal(interaction.getPhase(), "dragging");
    assert.ok(lastPreview);
    assert.equal(lastPreview.snapped, true);
    assert.ok((lastPreview.guides || []).length >= 1);
    const snappedDx = lastPreview.dx;
    interaction.onPointerUp(pointer(20, 110));
    assert.equal(history.state().canUndo, true);
    assert.equal(Math.round(store.snapshot().session.pieces["instance:a"].local_x_mm), 0);
    assert.equal(Math.round(snappedDx), Math.round(0 - 100));

    // Undo restores exact pre-snap placement.
    store.undo();
    assert.equal(store.snapshot().session.pieces["instance:a"].local_x_mm, 100);

    // Cancel clears guides.
    interaction.beginPieceGesture("instance:a", pointer(110, 110), { pieceId: 1 });
    interaction.onPointerMove(pointer(116, 110));
    interaction.onPointerMove(pointer(20, 110));
    assert.equal(lastPreview.snapped, true);
    interaction.cancel();
    assert.equal(lastPreview, null);
}

const canvasSource = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
assert.match(canvasSource, /data-abe-magnet/);
assert.match(canvasSource, /data-abe-guide/);
assert.match(canvasSource, /vector-effect/);
assert.doesNotMatch(canvasSource, /abe-tool-select/);

console.log("board_editor_snap.test.js: ok");
