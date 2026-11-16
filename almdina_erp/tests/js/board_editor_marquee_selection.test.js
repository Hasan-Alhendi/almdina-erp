"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");

function load() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/marquee_geometry.js",
        "public/js/board_editor/move_interaction.js",
        "public/js/board_editor/marquee_interaction.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) }, ui: { form: { on() {} } } },
        __: (message) => message,
        document: {
            createElementNS: (_ns, tag) => {
                const attrs = {};
                return {
                    tagName: String(tag || "").toUpperCase(),
                    attrs,
                    setAttribute(name, value) { attrs[name] = String(value); },
                    getAttribute(name) { return attrs[name]; },
                    style: {},
                    appendChild() {},
                };
            },
        },
    };
    context.window = context;
    context.globalThis = context;
    const vm = require("node:vm");
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

const editor = load();
const {
    History,
    SessionDocument,
    MoveGeometry,
    MarqueeGeometry,
    CanvasRenderer,
    createStore,
    createMarqueeInteraction,
    createMoveInteraction,
    MOVE_THRESHOLD_PX,
} = editor;

assert.ok(MarqueeGeometry);
assert.ok(typeof createMarqueeInteraction === "function");
assert.ok(typeof CanvasRenderer.patchMarqueeOverlay === "function");
assert.ok(typeof CanvasRenderer.marqueeBlockedTarget === "function");

const projection = {
    board: { kerf_cm: 0.4 },
    layers: [{ match_key: "GEOMETRY", original_name: "GEOMETRY" }],
    sheets: [
        {
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
            usable_width_cm: 100,
            usable_length_cm: 100,
        },
    ],
    pieces: [
        {
            piece_id: 1,
            piece_instance_id: "pi-a",
            label: "A",
            sheet_no: 1,
            placement_cm: { x: 10, y: 10, w: 20, h: 20 },
        },
        {
            piece_id: 2,
            piece_instance_id: "pi-b",
            label: "B",
            sheet_no: 1,
            placement_cm: { x: 50, y: 10, w: 20, h: 20 },
        },
        {
            piece_id: 3,
            piece_instance_id: "pi-c",
            label: "C",
            sheet_no: 1,
            placement_cm: { x: 10, y: 50, w: 20, h: 20 },
        },
        {
            piece_id: 4,
            piece_instance_id: "pi-l",
            label: "L",
            sheet_no: 1,
            placement_cm: { x: 70, y: 60, w: 20, h: 20 },
        },
    ],
    elements: [
        {
            element_id: "a",
            kind: "finished_outline",
            piece_id: 1,
            piece_instance_id: "pi-a",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            geometry: { outer: [[100, 100], [300, 100], [300, 300], [100, 300]] },
        },
        {
            element_id: "b",
            kind: "finished_outline",
            piece_id: 2,
            piece_instance_id: "pi-b",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            geometry: { outer: [[500, 100], [700, 100], [700, 300], [500, 300]] },
        },
        {
            element_id: "c",
            kind: "finished_outline",
            piece_id: 3,
            piece_instance_id: "pi-c",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            geometry: { outer: [[100, 500], [300, 500], [300, 700], [100, 700]] },
        },
        {
            element_id: "l",
            kind: "finished_outline",
            piece_id: 4,
            piece_instance_id: "pi-l",
            sheet_no: 1,
            layer_match_key: "GEOMETRY",
            // L-shape: AABB spans 700..900 / 600..800 but the corner cutout is empty.
            geometry: {
                outer: [
                    [700, 600], [900, 600], [900, 700], [800, 700], [800, 800], [700, 800],
                ],
            },
        },
    ],
};

const layout = {
    positions: {
        1: { originX: 0, originY: 36, widthMm: 1000, heightMm: 1000, trimX: 0, trimY: 0 },
    },
};

const session = SessionDocument.buildFromProjection(projection, layout);
const keyA = "instance:pi-a";
const keyB = "instance:pi-b";
const keyC = "instance:pi-c";
const keyL = "instance:pi-l";

assert.equal(session.pieces[keyA].piece_instance_id, "pi-a");
assert.equal(session.pieces[keyB].piece_instance_id, "pi-b");

// Session world Y includes the board title band (36 mm).
const worldA = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards);
const worldB = MoveGeometry.worldFootprint(session.pieces[keyB], session.boards);
const worldL = MoveGeometry.worldFootprint(session.pieces[keyL], session.boards);
assert.ok(worldA.bounds.y > 100);

function sortedKeys(keys) {
    return Array.from(keys || []).slice().sort();
}

// 1) Fully inside.
{
    const rect = MarqueeGeometry.normalizeRect(
        worldA.bounds.x - 10,
        worldA.bounds.y - 10,
        worldA.bounds.x + worldA.bounds.w + 10,
        worldA.bounds.y + worldA.bounds.h + 10
    );
    const hits = MarqueeGeometry.hitTestPieceKeys(session, rect);
    assert.deepStrictEqual(sortedKeys(hits), [keyA]);
}

// 2) Partial touch only.
{
    const rect = MarqueeGeometry.normalizeRect(
        worldA.bounds.x + worldA.bounds.w - 20,
        worldA.bounds.y + 40,
        worldA.bounds.x + worldA.bounds.w + 20,
        worldA.bounds.y + 80
    );
    const hits = MarqueeGeometry.hitTestPieceKeys(session, rect);
    assert.ok(hits.includes(keyA));
    assert.equal(hits.includes(keyB), false);
}

// 3) No intersection.
{
    const rect = MarqueeGeometry.normalizeRect(
        worldA.bounds.x + worldA.bounds.w + 20,
        worldA.bounds.y + worldA.bounds.h + 20,
        worldA.bounds.x + worldA.bounds.w + 80,
        worldA.bounds.y + worldA.bounds.h + 80
    );
    const hits = MarqueeGeometry.hitTestPieceKeys(session, rect);
    assert.deepStrictEqual(sortedKeys(hits), []);
}

// 4) All four drag directions normalize the same rect and hit set.
{
    const x1 = worldA.bounds.x - 10;
    const y1 = worldA.bounds.y - 10;
    const x2 = worldB.bounds.x + worldB.bounds.w + 10;
    const y2 = worldB.bounds.y + worldB.bounds.h + 10;
    const expected = MarqueeGeometry.normalizeRect(x1, y1, x2, y2);
    const directions = [
        [x1, y1, x2, y2],
        [x2, y2, x1, y1],
        [x2, y1, x1, y2],
        [x1, y2, x2, y1],
    ];
    directions.forEach((coords) => {
        const rect = MarqueeGeometry.normalizeRect(...coords);
        assert.deepStrictEqual(rect, expected);
        const hits = MarqueeGeometry.hitTestPieceKeys(session, rect);
        assert.deepStrictEqual(sortedKeys(hits), sortedKeys([keyA, keyB]));
    });
}

// Geometric touch on L arm only (AABB would also hit, but empty corner must miss).
{
    const touchArm = MarqueeGeometry.normalizeRect(
        worldL.bounds.x + 10,
        worldL.bounds.y + 10,
        worldL.bounds.x + 30,
        worldL.bounds.y + 30
    );
    assert.ok(MarqueeGeometry.hitTestPieceKeys(session, touchArm).includes(keyL));
    const missCutout = MarqueeGeometry.normalizeRect(
        worldL.bounds.x + worldL.bounds.w - 80,
        worldL.bounds.y + worldL.bounds.h - 80,
        worldL.bounds.x + worldL.bounds.w - 20,
        worldL.bounds.y + worldL.bounds.h - 20
    );
    assert.equal(MarqueeGeometry.hitTestPieceKeys(session, missCutout).includes(keyL), false);
}

// Outside-board pieces (sheet_no null) remain marquee-selectable.
{
    // Park C left of the board so a mixed marquee can cover A+C without B.
    const outsideDrop = MoveGeometry.proposePieceDrop(session, keyC, -500, 120);
    assert.equal(outsideDrop.ok, true);
    const outsideSession = MoveGeometry.applyPieceMove(session, outsideDrop);
    assert.equal(outsideSession.pieces[keyC].sheet_no, null);
    assert.equal(MarqueeGeometry.isSelectablePiece(outsideSession.pieces[keyC]), true);
    const worldOutside = MoveGeometry.worldFootprint(
        outsideSession.pieces[keyC],
        outsideSession.boards
    );
    assert.ok(worldOutside.bounds.x + worldOutside.bounds.w < 0
        || worldOutside.bounds.x < worldA.bounds.x);
    // Fully outside the board and fully inside the marquee.
    const fullOutside = MarqueeGeometry.normalizeRect(
        worldOutside.bounds.x - 5,
        worldOutside.bounds.y - 5,
        worldOutside.bounds.x + worldOutside.bounds.w + 5,
        worldOutside.bounds.y + worldOutside.bounds.h + 5
    );
    assert.ok(MarqueeGeometry.hitTestPieceKeys(outsideSession, fullOutside).includes(keyC));
    assert.equal(MarqueeGeometry.hitTestPieceKeys(outsideSession, fullOutside).includes(keyA), false);
    // Partial touch while still outside the board.
    const partialOutside = MarqueeGeometry.normalizeRect(
        worldOutside.bounds.x + worldOutside.bounds.w - 15,
        worldOutside.bounds.y + 10,
        worldOutside.bounds.x + worldOutside.bounds.w + 40,
        worldOutside.bounds.y + 40
    );
    assert.ok(MarqueeGeometry.hitTestPieceKeys(outsideSession, partialOutside).includes(keyC));
    // Mixed: on-board A + outside C in one marquee (stops before B).
    const mixed = MarqueeGeometry.normalizeRect(
        worldOutside.bounds.x - 10,
        Math.min(worldA.bounds.y, worldOutside.bounds.y) - 10,
        worldA.bounds.x + worldA.bounds.w + 10,
        Math.max(worldA.bounds.y + worldA.bounds.h, worldOutside.bounds.y + worldOutside.bounds.h) + 10
    );
    assert.deepStrictEqual(
        sortedKeys(MarqueeGeometry.hitTestPieceKeys(outsideSession, mixed)),
        sortedKeys([keyA, keyC])
    );
    // Excluded pieces stay out of marquee hits.
    const excludedSession = JSON.parse(JSON.stringify(outsideSession));
    excludedSession.pieces[keyC].distribution = "excluded";
    assert.equal(MarqueeGeometry.isSelectablePiece(excludedSession.pieces[keyC]), false);
    assert.equal(
        MarqueeGeometry.hitTestPieceKeys(excludedSession, fullOutside).includes(keyC),
        false
    );
}

const store = createStore({ projection });
const history = History.create(session);
store.attachSession(history.get(), history);

// 5) Replace previous selection on plain marquee commit path.
store.selectPiece(3, { pieceKey: keyC, mode: "replace" });
assert.deepStrictEqual(sortedKeys(store.snapshot().selectedPieceKeys), [keyC]);
store.selectPieces([keyA, keyB], { mode: "replace" });
assert.deepStrictEqual(sortedKeys(store.snapshot().selectedPieceKeys), sortedKeys([keyA, keyB]));

// 6) Shift/add keeps previous and appends.
store.selectPiece(3, { pieceKey: keyC, mode: "replace" });
store.selectPieces([keyA], { mode: "add" });
assert.deepStrictEqual(sortedKeys(store.snapshot().selectedPieceKeys), sortedKeys([keyA, keyC]));

// 7) No duplicates.
store.selectPieces([keyA, keyA, keyC], { mode: "add" });
assert.equal(store.snapshot().selectedPieceKeys.filter((key) => key === keyA).length, 1);
assert.deepStrictEqual(
    sortedKeys(MarqueeGeometry.mergePieceKeys([keyA], [keyA, keyB], "add")),
    sortedKeys([keyA, keyB])
);

// Empty replace clears.
store.selectPieces([], { mode: "replace" });
assert.deepStrictEqual(sortedKeys(store.snapshot().selectedPieceKeys), []);

// 8–9) Group move keeps relative spacing for marquee-selected keys.
store.selectPieces([keyA, keyB], { mode: "replace" });
const plan = MoveGeometry.groupMovePlan(store.snapshot().session, store.snapshot().selectedPieceKeys, keyA);
assert.deepStrictEqual(sortedKeys(plan.roots), sortedKeys([keyA, keyB]));
const gapBefore = MoveGeometry.pieceWorldOrigin(store.snapshot().session, keyB).x
    - MoveGeometry.pieceWorldOrigin(store.snapshot().session, keyA).x;
const proposed = MoveGeometry.proposeGroupMove(store.snapshot().session, plan.roots, 25, 15);
assert.equal(proposed.ok, true);
let moved = store.snapshot().session;
proposed.commands.forEach((command) => {
    moved = MoveGeometry.applyPieceMove(moved, command);
});
const gapAfter = MoveGeometry.pieceWorldOrigin(moved, keyB).x
    - MoveGeometry.pieceWorldOrigin(moved, keyA).x;
assert.ok(Math.abs(gapBefore - gapAfter) < 0.01);

// 10) Zoom/pan-aware client→world conversion remains consistent.
{
    const svg = {
        getBoundingClientRect: () => ({ left: 40, top: 20, width: 400, height: 300 }),
        getAttribute: (name) => (name === "width" ? "800" : name === "height" ? "600" : null),
    };
    const metrics = {
        minX: -100,
        minY: 50,
        width: 1000,
        height: 800,
        scale: 0.5,
        padX: 16,
        padY: 16,
        contentWidth: 800,
        contentHeight: 600,
    };
    const mapped = CanvasRenderer.clientToWorldViaMetrics(svg, metrics, 140, 80);
    const mappedAgain = CanvasRenderer.clientToWorldViaMetrics(svg, metrics, 140, 80);
    assert.ok(mapped);
    assert.equal(mapped.x, mappedAgain.x);
    assert.equal(mapped.y, mappedAgain.y);
    const metricsZoomed = { ...metrics, scale: 1.25 };
    const worldZoomed = CanvasRenderer.clientToWorldViaMetrics(svg, metricsZoomed, 140, 80);
    assert.notEqual(worldZoomed.x, mapped.x);
    // Hit test still uses world geometry after a different camera.
    const hits = MarqueeGeometry.hitTestPieceKeys(
        session,
        MarqueeGeometry.normalizeRect(
            worldA.bounds.x,
            worldA.bounds.y,
            worldA.bounds.x + worldA.bounds.w,
            worldA.bounds.y + worldA.bounds.h
        )
    );
    assert.deepStrictEqual(sortedKeys(hits), [keyA]);
}

// 11) Measure/rotate/piece targets block marquee start; empty sheet does not.
assert.equal(
    CanvasRenderer.marqueeBlockedTarget({
        closest: (sel) => (sel.includes("data-abe-rotate-handle") ? {} : null),
    }),
    true
);
assert.equal(
    CanvasRenderer.marqueeBlockedTarget({
        closest: (sel) => (sel.includes("data-piece-key") ? {} : null),
    }),
    true
);
assert.equal(
    CanvasRenderer.marqueeBlockedTarget({
        closest: (sel) => (sel.includes("data-board-drag") ? {} : null),
    }),
    true
);
assert.equal(
    CanvasRenderer.marqueeBlockedTarget({
        closest: () => null,
    }),
    false
);

// Interaction: no selection change without real drag; shift add; replace; overlay path.
function makeMarqueeHarness(initialKeys) {
    const overlayRects = [];
    const selections = [];
    const dragStore = createStore({ projection });
    const dragHistory = History.create(SessionDocument.buildFromProjection(projection, layout));
    dragStore.attachSession(dragHistory.get(), dragHistory);
    if (Array.isArray(initialKeys) && initialKeys.length) {
        dragStore.selectPieces(initialKeys, { mode: "replace" });
    }
    const stage = {
        classList: {
            _set: new Set(),
            toggle(name, on) {
                if (on) this._set.add(name);
                else this._set.delete(name);
            },
            contains(name) { return this._set.has(name); },
            add(name) { this._set.add(name); },
            remove(name) { this._set.delete(name); },
        },
        style: { cursor: "" },
        setPointerCapture() {},
        releasePointerCapture() {},
    };
    const svg = {
        getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 800 }),
        getAttribute: (name) => (name === "width" ? "1000" : name === "height" ? "800" : null),
    };
    const host = {
        querySelector(sel) {
            if (sel === ".abe-world") {
                const kids = [];
                return {
                    querySelector(inner) {
                        return kids.find((node) => node.getAttribute
                            && node.getAttribute("data-abe-marquee") === "1") || null;
                    },
                    appendChild(node) { kids.push(node); },
                    _kids: kids,
                };
            }
            return null;
        },
    };
    const interaction = createMarqueeInteraction({
        store: dragStore,
        getStageEl: () => stage,
        getSvgEl: () => svg,
        getCanvasHost: () => host,
        getWorldMetrics: () => ({
            minX: 0,
            minY: 0,
            width: 1000,
            height: 800,
            scale: 1,
            padX: 0,
            padY: 0,
            contentWidth: 1000,
            contentHeight: 800,
        }),
        onOverlay: (rect) => overlayRects.push(rect),
        onSelectKeys: (keys, meta) => {
            selections.push({ keys: keys.slice(), meta });
            dragStore.selectPieces(keys, { mode: "replace" });
        },
    });
    return { interaction, store: dragStore, overlayRects, selections, stage };
}

function pointer(type, x, y, extra) {
    return {
        type,
        pointerId: 1,
        button: 0,
        clientX: x,
        clientY: y,
        pointerType: "mouse",
        shiftKey: false,
        preventDefault() {},
        stopPropagation() {},
        currentTarget: { setPointerCapture() {}, releasePointerCapture() {} },
        ...(extra || {}),
    };
}

const dragFromA = {
    x1: worldA.bounds.x - 10,
    y1: worldA.bounds.y - 10,
    x2: worldB.bounds.x + worldB.bounds.w + 10,
    y2: worldB.bounds.y + worldB.bounds.h + 10,
};
const dragOnlyA = {
    x1: worldA.bounds.x - 10,
    y1: worldA.bounds.y - 10,
    x2: worldA.bounds.x + worldA.bounds.w + 10,
    y2: worldA.bounds.y + worldA.bounds.h + 10,
};
const dragMiss = {
    x1: worldA.bounds.x + worldA.bounds.w + 30,
    y1: worldA.bounds.y + worldA.bounds.h + 30,
    x2: worldA.bounds.x + worldA.bounds.w + 90,
    y2: worldA.bounds.y + worldA.bounds.h + 90,
};

// 12) Empty click (no real drag) clears selection; Shift keeps it.
{
    const h = makeMarqueeHarness([keyC]);
    assert.equal(h.interaction.begin(pointer("pointerdown", 40, 40)), true);
    h.interaction.onPointerMove(pointer("pointermove", 42, 41));
    h.interaction.onPointerUp(pointer("pointerup", 42, 41));
    assert.deepStrictEqual(sortedKeys(h.store.snapshot().selectedPieceKeys), []);
    assert.equal(h.selections.length, 0);
    assert.equal(h.interaction.isActive(), false);
    assert.equal(h.interaction.consumeClickSuppression(), true);
}
{
    const h = makeMarqueeHarness([keyC]);
    assert.equal(h.interaction.begin(pointer("pointerdown", 40, 40, { shiftKey: true })), true);
    h.interaction.onPointerMove(pointer("pointermove", 42, 41, { shiftKey: true }));
    h.interaction.onPointerUp(pointer("pointerup", 42, 41, { shiftKey: true }));
    assert.deepStrictEqual(sortedKeys(h.store.snapshot().selectedPieceKeys), [keyC]);
    assert.equal(h.interaction.consumeClickSuppression(), true);
}
// Marquee drag replace must not clear-then-lose the new selection via empty-click path.
{
    const h = makeMarqueeHarness([keyC]);
    h.interaction.begin(pointer("pointerdown", dragFromA.x1, dragFromA.y1));
    h.interaction.onPointerMove(pointer(
        "pointermove",
        dragFromA.x1 + MOVE_THRESHOLD_PX + 1,
        dragFromA.y1
    ));
    assert.equal(h.interaction.isSelecting(), true);
    // Selection still previous until commit on pointerup.
    assert.deepStrictEqual(sortedKeys(h.store.snapshot().selectedPieceKeys), [keyC]);
    h.interaction.onPointerMove(pointer("pointermove", dragFromA.x2, dragFromA.y2));
    h.interaction.onPointerUp(pointer("pointerup", dragFromA.x2, dragFromA.y2));
    assert.deepStrictEqual(sortedKeys(h.store.snapshot().selectedPieceKeys), sortedKeys([keyA, keyB]));
}

// Real marquee replace.
{
    const h = makeMarqueeHarness([keyC]);
    assert.equal(h.interaction.begin(pointer("pointerdown", dragFromA.x1, dragFromA.y1)), true);
    h.interaction.onPointerMove(pointer(
        "pointermove",
        dragFromA.x1 + MOVE_THRESHOLD_PX + 1,
        dragFromA.y1
    ));
    assert.equal(h.interaction.isSelecting(), true);
    h.interaction.onPointerMove(pointer("pointermove", dragFromA.x2, dragFromA.y2));
    h.interaction.onPointerUp(pointer("pointerup", dragFromA.x2, dragFromA.y2));
    assert.deepStrictEqual(sortedKeys(h.store.snapshot().selectedPieceKeys), sortedKeys([keyA, keyB]));
    assert.equal(h.selections.length, 1);
    assert.equal(h.selections[0].meta.mode, "replace");
    assert.ok(h.overlayRects.some((rect) => rect && rect.w > 0));
    assert.equal(h.overlayRects[h.overlayRects.length - 1], null);
}

// Shift marquee adds.
{
    const h = makeMarqueeHarness([keyC]);
    h.interaction.begin(pointer("pointerdown", dragOnlyA.x1, dragOnlyA.y1, { shiftKey: true }));
    h.interaction.onPointerMove(pointer(
        "pointermove",
        dragOnlyA.x1 + MOVE_THRESHOLD_PX + 2,
        dragOnlyA.y1,
        { shiftKey: true }
    ));
    h.interaction.onPointerMove(pointer("pointermove", dragOnlyA.x2, dragOnlyA.y2, { shiftKey: true }));
    h.interaction.onPointerUp(pointer("pointerup", dragOnlyA.x2, dragOnlyA.y2, { shiftKey: true }));
    assert.deepStrictEqual(sortedKeys(h.store.snapshot().selectedPieceKeys), sortedKeys([keyA, keyC]));
    assert.equal(h.selections[0].meta.mode, "add");
}

// Empty marquee clears on replace.
{
    const h = makeMarqueeHarness([keyA, keyB]);
    h.interaction.begin(pointer("pointerdown", dragMiss.x1, dragMiss.y1));
    h.interaction.onPointerMove(pointer(
        "pointermove",
        dragMiss.x1 + MOVE_THRESHOLD_PX + 2,
        dragMiss.y1
    ));
    h.interaction.onPointerMove(pointer("pointermove", dragMiss.x2, dragMiss.y2));
    h.interaction.onPointerUp(pointer("pointerup", dragMiss.x2, dragMiss.y2));
    assert.deepStrictEqual(sortedKeys(h.store.snapshot().selectedPieceKeys), []);
}

// Empty marquee with Shift keeps previous.
{
    const h = makeMarqueeHarness([keyA]);
    h.interaction.begin(pointer("pointerdown", dragMiss.x1, dragMiss.y1, { shiftKey: true }));
    h.interaction.onPointerMove(pointer(
        "pointermove",
        dragMiss.x1 + MOVE_THRESHOLD_PX + 2,
        dragMiss.y1,
        { shiftKey: true }
    ));
    h.interaction.onPointerMove(pointer("pointermove", dragMiss.x2, dragMiss.y2, { shiftKey: true }));
    h.interaction.onPointerUp(pointer("pointerup", dragMiss.x2, dragMiss.y2, { shiftKey: true }));
    assert.deepStrictEqual(sortedKeys(h.store.snapshot().selectedPieceKeys), [keyA]);
}

// Move interaction still owns piece gestures after marquee multi-select.
{
    const moveStore = createStore({ projection });
    const moveHistory = History.create(SessionDocument.buildFromProjection(projection, layout));
    moveStore.attachSession(moveHistory.get(), moveHistory);
    moveStore.selectPieces([keyA, keyB], { mode: "replace" });
    const move = createMoveInteraction({
        store: moveStore,
        getStageEl: () => ({
            classList: { toggle() {}, contains() { return false; }, add() {}, remove() {} },
            style: {},
            getBoundingClientRect: () => ({ left: 0, top: 0, right: 1000, bottom: 800, width: 1000, height: 800 }),
            scrollLeft: 0,
            scrollTop: 0,
        }),
        getSvgEl: () => ({
            getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 800 }),
            getAttribute: (name) => (name === "width" ? "1000" : name === "height" ? "800" : null),
        }),
        getWorldMetrics: () => ({
            minX: 0,
            minY: 0,
            width: 1000,
            height: 800,
            scale: 1,
            padX: 0,
            padY: 0,
            contentWidth: 1000,
            contentHeight: 800,
        }),
        getScale: () => 1,
    });
    const beforeGap = MoveGeometry.pieceWorldOrigin(moveStore.snapshot().session, keyB).x
        - MoveGeometry.pieceWorldOrigin(moveStore.snapshot().session, keyA).x;
    const startX = worldA.bounds.x + 20;
    const startY = worldA.bounds.y + 20;
    move.beginPieceGesture(keyA, pointer("pointerdown", startX, startY), { pieceId: 1 });
    move.onPointerMove(pointer("pointermove", startX + MOVE_THRESHOLD_PX + 4, startY));
    assert.equal(move.getPhase(), "dragging");
    const planRoots = MoveGeometry.groupMovePlan(
        moveStore.snapshot().session,
        moveStore.snapshot().selectedPieceKeys,
        keyA
    ).roots;
    assert.deepStrictEqual(sortedKeys(planRoots), sortedKeys([keyA, keyB]));
    move.onPointerMove(pointer("pointermove", startX + 40, startY + 12));
    move.onPointerUp(pointer("pointerup", startX + 40, startY + 12));
    const afterGap = MoveGeometry.pieceWorldOrigin(moveStore.snapshot().session, keyB).x
        - MoveGeometry.pieceWorldOrigin(moveStore.snapshot().session, keyA).x;
    assert.ok(Math.abs(beforeGap - afterGap) < 0.01);
    assert.notEqual(
        MoveGeometry.pieceWorldOrigin(moveStore.snapshot().session, keyA).x,
        worldA.bounds.x
    );
}

// Source wiring smoke checks.
const canvasSource = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const pageSource = fs.readFileSync(
    path.join(root, "almdina_erp/page/board_editor/board_editor.js"),
    "utf8"
);
assert.match(canvasSource, /beginMarqueeGesture/);
assert.match(canvasSource, /patchMarqueeOverlay/);
assert.match(controllerSource, /createMarqueeInteraction/);
assert.match(controllerSource, /beginMarqueeGesture/);
assert.match(pageSource, /marquee_geometry\.js/);
assert.match(pageSource, /marquee_interaction\.js/);

console.log("board_editor_marquee_selection.test.js: ok");
