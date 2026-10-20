"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(relativePath, context) {
    vm.runInContext(
        fs.readFileSync(path.resolve(__dirname, relativePath), "utf8"),
        context
    );
}

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    document: { documentElement: { lang: "ar" } },
    frappe: { utils: { escape_html(value) { return String(value ?? ""); } } },
    __(value) { return Array.isArray(value) ? value[0] : value; },
    Object,
    Array,
    Boolean,
    Number,
    String,
    Math,
    console,
});
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js", context);
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_ux.js", context);

const geometry = fakeWindow.AlmdinaLinerGeometry;
const editor = fakeWindow.AlmdinaLinerEditor;
const regular = geometry.pieceFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
});

function copy(value) {
    return JSON.parse(JSON.stringify(value));
}

assert.deepEqual(
    copy(geometry.availableSides("Regular")),
    ["edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right"]
);
assert.deepEqual(
    copy(geometry.availableSides("Clipped Corner")),
    ["edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right", "edge_break", "edge_break_only"]
);
assert.deepEqual(
    copy(geometry.availableSides("L-Shaped Corner")),
    ["edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right", "edge_break"]
);
assert.deepEqual(copy(geometry.availableSides("Special")), []);

for (const side of geometry.availableSides("Regular")) {
    const strip = geometry.stripPolygonMm(regular, side, 2, 1.5);
    assert.equal(geometry.validationCode(regular, side, 2, 1.5), "");
    assert.ok(strip.length >= 4);
}

assert.deepEqual(
    copy(geometry.stripPolygonMm(regular, "edge_width_top", 2, 1.5).map(point => point.map(value => Math.round(value)))),
    [[0, 20], [400, 20], [400, 35], [0, 35]]
);
const wide = geometry.pieceFromRow({ piece_type: "Regular", width_cm: 100, length_cm: 80 });
function segmentLength(start, end) {
    return Math.hypot(end[0] - start[0], end[1] - start[1]);
}
const partialRegion = geometry.regionPolygonMm(wide, "edge_width_top", 10, 1.8, 20, 30);
assert.ok(Math.abs(segmentLength(partialRegion[0], partialRegion[1]) - 300) < 0.1);
assert.ok(Math.abs(segmentLength(partialRegion[1], partialRegion[2]) - 18) < 0.1);
assert.ok(segmentLength(partialRegion[0], partialRegion[1]) < 1000);
const fullRegion = geometry.regionPolygonMm(wide, "edge_width_top", 10, 1.8, 0, 100);
assert.ok(Math.abs(segmentLength(fullRegion[0], fullRegion[1]) - 1000) < 0.1);
const grooveRegion = geometry.regionPolygonMm(wide, "edge_long_right", 4, 0.5, 10, 25);
assert.ok(Math.abs(segmentLength(grooveRegion[0], grooveRegion[1]) - 250) < 0.1);
assert.ok(segmentLength(grooveRegion[0], grooveRegion[1]) < 800);
const handleRegion = geometry.regionPolygonMm(wide, "edge_width_bottom", 2, 1.5, 15, 20);
assert.ok(Math.abs(segmentLength(handleRegion[0], handleRegion[1]) - 200) < 0.1);
assert.ok(segmentLength(handleRegion[0], handleRegion[1]) < 1000);
const breakPiece = geometry.pieceFromRow({
    piece_type: "Clipped Corner",
    width_cm: 40,
    length_cm: 60,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 10,
    clipped_corner_length_cm: 16,
});
const breakRegion = geometry.regionPolygonMm(breakPiece, "edge_break_only", 1, 0.8, 2, 4);
assert.ok(Math.abs(segmentLength(breakRegion[0], breakRegion[1]) - 40) < 0.2);
assert.ok(Math.abs(breakRegion[1][0] - breakRegion[0][0]) > 1);
assert.ok(Math.abs(breakRegion[1][1] - breakRegion[0][1]) > 1);

const clipped = geometry.pieceFromRow({
    piece_type: "Clipped Corner",
    width_cm: 40,
    length_cm: 60,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 10,
    clipped_corner_length_cm: 16,
});
for (const side of geometry.availableSides("Clipped Corner")) {
    assert.equal(geometry.validationCode(clipped, side, 1, 1), "");
}
const breakOnly = geometry.stripPolygonMm(clipped, "edge_break_only", 1, 1);
assert.ok(breakOnly.some(point => point[0] !== breakOnly[0][0] && point[1] !== breakOnly[0][1]));

const shaped = geometry.pieceFromRow({
    piece_type: "L-Shaped Corner",
    width_cm: 40,
    length_cm: 60,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 12,
    clipped_corner_length_cm: 18,
});
assert.equal(geometry.validationCode(shaped, "edge_break", 1, 1), "");
assert.equal(geometry.validationCode(shaped, "edge_break_only", 1, 1), "side_unavailable");

const lInputContract = geometry.pieceFromRow({
    piece_type: "L-Shaped Corner",
    width_cm: 60,
    length_cm: 60,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 30,
    clipped_corner_length_cm: 30,
});
const innerBandLiner = geometry.pieceFromRow({
    piece_type: "L-Shaped Corner",
    width_cm: 60,
    length_cm: 60,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 30,
    clipped_corner_length_cm: 30,
});
innerBandLiner.cutWidthCm = 30.1;
innerBandLiner.cutLengthCm = 30.1;
const actualLPath = geometry.edgePaths(innerBandLiner).edge_break;
assert.equal(actualLPath.slice(1).reduce((total, point, index) => total + segmentLength(actualLPath[index], point), 0), 602);
assert.equal(geometry.centerlineMm(innerBandLiner, "edge_break", 1, 1, 0, 60).length, 3);
assert.equal(geometry.centerlineMm(innerBandLiner, "edge_break", 1, 1, 0, 60.2).length, 3,
    "effective geometry remains available to manufacturing consumers");
for (const kind of ["liner", "back_groove", "recessed_handle_cutout"]) {
    const draft = editor.draftFromRow({
        piece_type: "L-Shaped Corner",
        width_cm: 60,
        length_cm: 60,
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 30,
        clipped_corner_length_cm: 30,
    }, kind);
    draft.piece = innerBandLiner;
    draft.side = "edge_break";
    draft.offsetCm = 1;
    draft.widthCm = 1;
    draft.startCm = 0;
    draft.lengthCm = 60.2;
    draft.fullLength = false;
    assert.equal(editor.validationIssue(draft), null, `${kind} must accept the 60.2 cm effective span`);
    draft.lengthCm = 60.226;
    assert.equal(editor.validationIssue(draft).code, "liner_span_exceeds_edge", `${kind} must reject lengths beyond the effective path`);
}

assert.equal(geometry.validationCode(regular, "edge_width_top", -1, 1), "offset_invalid");
assert.equal(geometry.validationCode(regular, "edge_width_top", 0, 0), "width_invalid");
assert.equal(geometry.validationCode(regular, "edge_width_top", 50, 20), "strip_outside");

const near = geometry.stripPolygonMm(regular, "edge_width_top", 2, 1.5);
const far = geometry.stripPolygonMm(regular, "edge_width_top", 4, 3);
assert.notDeepEqual(copy(near), copy(far));

const overlay = geometry.syntheticOverlay({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
    kerf_mm: 5,
    rotated: true,
    x: 0,
    y: 0,
});
assert.equal(overlay.kind, "liner");
assert.equal(overlay.synthetic, true);
assert.equal(overlay.geometry.closed, false);
assert.equal(overlay.geometry.toolpath, true);
assert.ok(overlay.geometry.path.length > 4);
const xs = overlay.geometry.path.map(point => point[0]);
const ys = overlay.geometry.path.map(point => point[1]);
assert.ok(Math.min(...xs) > 540);
assert.ok(Math.max(...ys) > 300);

const imported = geometry.syntheticOverlay({
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_width_cm: 1.5,
    overlays: [{ kind: "liner", geometry: { path: [[0, 0], [1, 1]] } }],
    geometry: { outer: [[0, 0], [10, 0], [10, 10]] },
});
assert.equal(imported, null);

const firstPreview = editor.previewSvg(editor.draftFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
}));
const moved = editor.draftFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_long_right",
    liner_offset_cm: 5,
    liner_width_cm: 3,
});
const blank = editor.draftFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
}, "liner", { blankWhenMissing: true });
assert.equal(blank.side, "");
assert.equal(editor.draftFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
}).side, "edge_width_top");
assert.equal(editor.draftFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "not-a-side",
}).side, "");
assert.match(editor.validationMessage(blank), /reference side/);
const secondPreview = editor.previewSvg(moved);
assert.match(firstPreview, /data-liner-strip="1"/);
assert.match(firstPreview, /data-liner-offset-line="1"/);
assert.match(firstPreview, /data-liner-width-line="1"/);
assert.match(firstPreview, /data-liner-side="edge_width_top"/);
assert.notEqual(firstPreview, secondPreview);
assert.match(secondPreview, /data-liner-side="edge_long_right"/);
assert.equal(editor.validationMessage(Object.assign({}, moved, { widthCm: 0 })), "عرض اللاينر يجب أن يكون أكبر من صفر.");

const expectedBandCoordinates = {
    edge_width_top: [[36, 34], [324, 34]],
    edge_width_bottom: [[36, 206], [324, 206]],
    edge_long_left: [[34, 36], [34, 204]],
    edge_long_right: [[326, 36], [326, 204]],
};
let referenceOutline = null;
let referenceMachining = null;
for (const [side, expected] of Object.entries(expectedBandCoordinates)) {
    const row = {
        [`${side}`]: 1,
    };
    const preview = editor.previewSvg({
        piece: regular,
        row,
        kind: "liner",
        side: "edge_width_top",
        offsetCm: 2,
        widthCm: 1.5,
        startCm: 4,
        lengthCm: 20,
        enabled: true,
    });
    const outline = preview.match(/<polygon points="([^"]+)"/)[1];
    const band = preview.match(/data-liner-edge="1"[^>]*points="([^"]+)"/)[1]
        .split(" ").map(point => point.split(",").map(Number));
    assert.deepEqual(band, expected, `${side} indicator must be inset and shortened on its assigned side`);
    if (referenceOutline === null) referenceOutline = outline;
    else assert.equal(outline, referenceOutline, "preview edge indication must not alter the actual piece outline");
    const machining = [
        preview.match(/data-liner-center="1"[^>]*points="([^"]+)"/)?.[1] || "",
        preview.match(/data-liner-strip="1"[^>]*points="([^"]+)"/)?.[1] || "",
    ];
    if (referenceMachining === null) referenceMachining = machining;
    else assert.deepEqual(machining, referenceMachining, "edge preview styling must not move machining overlays");
}

for (const kind of ["liner", "back_groove", "recessed_handle_cutout"]) {
    const partial = editor.previewSvg({
        piece: geometry.pieceFromRow({ piece_type: "Regular", width_cm: 30, length_cm: 30 }),
        row: {},
        kind,
        side: "edge_long_left",
        offsetCm: 2,
        widthCm: 1.5,
        startCm: 5,
        lengthCm: 20,
        enabled: true,
    });
    const points = partial.match(/data-liner-strip="1"[^>]*points="([^"]+)"/)[1]
        .split(" ").map(point => point.split(",").map(Number));
    assert.ok(Math.abs(segmentLength(points[0], points[1]) - 120) < 0.1, `${kind} visible area must span only the selected 20 cm region`);
    assert.ok(Math.abs(points[0][1] - 60) < 0.1, `${kind} visible area must start at 5 cm`);
    assert.ok(Math.abs(points[1][1] - 180) < 0.1, `${kind} visible area must end at 25 cm`);
}

const operator = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"),
    "utf8"
);
const ux = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_liner_ux.js"),
    "utf8"
);
assert.match(operator, /fieldname === "extra_liner"/);
assert.match(ux, /commitChildValues/);
assert.match(ux, /resolveChildRow/);
assert.match(ux, /queueChildApply/);
assert.match(ux, /if \(saved\) dialog.hide\(\)/);
const clearedLiner = editor.valuesFor("liner", {
    side: "edge_width_top",
    offsetCm: 2,
    widthCm: 1.5,
    startCm: 0,
    lengthCm: 40,
}, false);
assert.equal(clearedLiner.extra_liner, 0);
assert.equal(clearedLiner.liner_reference_side, "");
assert.equal(clearedLiner.liner_offset_cm, 0);
assert.equal(clearedLiner.liner_width_cm, 0);
assert.equal(clearedLiner.liner_start_cm, 0);
assert.equal(clearedLiner.liner_length_cm, 0);
assert.doesNotMatch(ux, /createElement\("style"\)/);

const shapedLiner = geometry.pieceFromRow({
    piece_type: "L-Shaped Corner",
    width_cm: 100,
    length_cm: 80,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 30,
});
assert.deepEqual(
    copy(geometry.stripPolygonMm(shapedLiner, "edge_break", 1, 0.8).map(point => point.map(value => Math.round(value)))),
    [[790, 0], [790, 310], [1000, 310], [1000, 318], [782, 318], [782, 0]]
);

const centers = copy(geometry.cutterCenterOffsetsMm(18, 5)).map(value => Math.round(value * 1000) / 1000);
assert.deepEqual(centers, [2.5, 7.5, 10.5, 15.5]);
assert.deepEqual(copy(geometry.cutterCenterOffsetsMm(5, 5)), [2.5]);
assert.throws(() => geometry.cutterCenterOffsetsMm(4, 5), /liner_narrower_than_cutter/);
const center = geometry.centerlineMm(regular, "edge_width_top", 2, 1.5);
assert.deepEqual(copy(center), [[0, 27.5], [400, 27.5]]);
const lCenter = geometry.centerlineMm(shapedLiner, "edge_break", 0, 1.8);
assert.equal(lCenter.length, 3);
const display = geometry.centerlineOverlay({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
    rotated: true,
    x: 0,
    y: 0,
});
assert.equal(display.geometry.toolpath, false);
assert.equal(display.geometry.closed, false);
assert.deepEqual(copy(display.geometry.path), [[572.5, 0], [572.5, 400]]);
const toolpath = geometry.toolpathMm(regular, "edge_width_top", 0, 1.8, 5);
const toolXs = toolpath.map(point => point[0]);
const toolYs = [...new Set(toolpath.map(point => Math.round(point[1] * 1000) / 1000))].sort((a, b) => a - b);
assert.equal(Math.round(Math.min(...toolXs) * 10) / 10, -2.5);
assert.equal(Math.round(Math.max(...toolXs) * 10) / 10, 402.5);
assert.deepEqual(copy(toolYs), [2.5, 7.5, 10.5, 15.5]);
const lPiece = geometry.pieceFromRow({
    piece_type: "L-Shaped Corner",
    width_cm: 100,
    length_cm: 80,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 30,
});
const lPath = geometry.toolpathMm(lPiece, "edge_break", 0, 1.8, 5);
assert.equal(lPath.length, 12);
const notchPath = [[900, 100], [900, 200]];
const lPolygon = geometry.piecePolygonMm(lPiece);
assert.equal(geometry.extensionConflict(notchPath, 5, {
    minX: -20, minY: -20, maxX: 1100, maxY: 900,
}, [{ polygon: lPolygon }]), "");
assert.equal(geometry.extensionConflict(notchPath, 5, {
    minX: -20, minY: -20, maxX: 1100, maxY: 900,
}, [{ minX: 0, minY: 0, maxX: 1000, maxY: 800 }]), "liner_extension_hits_piece");
const widerBit = geometry.toolpathMm(regular, "edge_width_top", 0, 1.8, 6);
assert.notDeepEqual(copy(toolpath), copy(widerBit));
const missingBit = geometry.syntheticOverlay({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 0,
    liner_width_cm: 1.8,
});
assert.equal(missingBit.error, "cutter_diameter_invalid");
const blocked = geometry.extensionConflict(toolpath, 5, {
    minX: 0, minY: 0, maxX: 400, maxY: 600,
}, []);
assert.equal(blocked, "");
const clear = geometry.extensionConflict(toolpath, 5, {
    minX: -10, minY: -10, maxX: 410, maxY: 610,
}, []);
assert.equal(clear, "");

function placedLiner(fields) {
    return Object.assign({
        piece_type: "Regular",
        width_cm: 40,
        length_cm: 50,
        extra_liner: 1,
        liner_reference_side: "edge_width_top",
        liner_offset_cm: 0,
        liner_width_cm: 1.8,
        kerf_mm: 5,
        x: 0,
        y: 0,
    }, fields);
}
function straightSpan(path, axis) {
    let best = 0;
    let run = [path[0]];
    for (let index = 1; index < path.length; index += 1) {
        const same = Math.abs(path[index][axis] - path[index - 1][axis]) <= 0.05;
        if (same) {
            run.push(path[index]);
            continue;
        }
        if (run.length >= 2) best = Math.max(best, Math.abs(run[run.length - 1][1 - axis] - run[0][1 - axis]));
        run = [path[index]];
    }
    if (run.length >= 2) best = Math.max(best, Math.abs(run[run.length - 1][1 - axis] - run[0][1 - axis]));
    return best;
}
const boardEdge = geometry.syntheticOverlay(placedLiner({ width_cm: 122, length_cm: 50 }));
assert.equal(boardEdge.error, undefined);
const boardXs = boardEdge.geometry.path.map(point => point[0]);
assert.equal(Math.round(Math.min(...boardXs) * 10) / 10, -2.5);
assert.equal(Math.round(Math.max(...boardXs) * 10) / 10, 1222.5);
const fullBoard = geometry.syntheticOverlay(placedLiner({
    width_cm: 122,
    length_cm: 244,
    board: { minX: 0, minY: 0, maxX: 1220, maxY: 2440 },
}));
assert.equal(fullBoard.error, undefined);
const fullXs = fullBoard.geometry.path.map(point => point[0]);
assert.equal(Math.round(Math.min(...fullXs) * 10) / 10, -2.5);
assert.equal(Math.round(Math.max(...fullXs) * 10) / 10, 1222.5);
assert.ok(straightSpan(fullBoard.geometry.path, 0) > 10);
const flushLeft = geometry.syntheticOverlay(placedLiner({
    width_cm: 40,
    board: { minX: 0, minY: 0, maxX: 1220, maxY: 2440 },
}));
const flushXs = flushLeft.geometry.path.map(point => point[0]);
assert.equal(Math.round(Math.min(...flushXs) * 10) / 10, -2.5);
assert.equal(Math.round(Math.max(...flushXs) * 10) / 10, 402.5);
const insetDoor = geometry.syntheticOverlay(placedLiner({
    x: 5,
    width_cm: 40,
    board: { minX: 0, minY: 0, maxX: 1220, maxY: 2440 },
}));
const insetXs = insetDoor.geometry.path.map(point => point[0]);
assert.equal(Math.round(Math.min(...insetXs) * 10) / 10, 47.5);
assert.equal(Math.round(Math.max(...insetXs) * 10) / 10, 452.5);
const openBoard = { minX: 0, minY: 0, maxX: 1220, maxY: 2440 };
assert.equal(geometry.extensionConflict(boardEdge.geometry.path, 5, openBoard, []), "");
const betweenDoorsPiece = placedLiner({ id: 1, label: "1.1", x: 20, width_cm: 40 });
const betweenDoors = geometry.syntheticOverlay(betweenDoorsPiece);
const leftNeighbor = geometry.placedPolygonMm(placedLiner({ x: 0, width_cm: 19.5, length_cm: 50 }));
const rightNeighbor = geometry.placedPolygonMm(placedLiner({ x: 60.5, width_cm: 30, length_cm: 50 }));
assert.equal(geometry.extensionConflict(betweenDoors.geometry.path, 5, openBoard, [
    { polygon: leftNeighbor },
    { polygon: rightNeighbor },
]), "");
const rotatedNeighbour = placedLiner({
    id: 2,
    label: "2.1",
    x: 0,
    w: 19.5,
    h: 50,
    width_cm: 50,
    length_cm: 19.5,
    rotated: true,
    extra_liner: 0,
});
const rotatedObstacles = geometry.sheetObstaclesMm(
    { pieces: [betweenDoorsPiece, rotatedNeighbour] },
    Object.assign({}, betweenDoorsPiece)
);
assert.equal(rotatedObstacles.length, 1);
assert.equal(rotatedObstacles[0].diagnostic.geometrySource, "placement_box");
assert.deepEqual(copy(rotatedObstacles[0].polygon), [[0, 0], [195, 0], [195, 500], [0, 500]]);
assert.equal(geometry.extensionConflict(betweenDoors.geometry.path, 5, openBoard, rotatedObstacles), "");

const offcutNeighbour = placedLiner({
    id: 3,
    label: "OFFCUT-3",
    x: 60.5,
    w: 30,
    h: 50,
    width_cm: 30,
    length_cm: 50,
    resource_kind: "OFFCUT",
    extra_liner: 0,
});
const offcutObstacles = geometry.sheetObstaclesMm(
    { pieces: [betweenDoorsPiece, offcutNeighbour] },
    Object.assign({}, betweenDoorsPiece)
);
assert.equal(offcutObstacles[0].diagnostic.label, "OFFCUT-3");
assert.equal(geometry.extensionConflict(betweenDoors.geometry.path, 5, openBoard, offcutObstacles), "");

for (const pieceType of ["Clipped Corner", "L-Shaped Corner"]) {
    const shapedNeighbour = placedLiner({
        id: `shape-${pieceType}`,
        label: pieceType,
        piece_type: pieceType,
        x: 60.5,
        w: 30,
        h: 50,
        width_cm: 30,
        length_cm: 50,
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 10,
        clipped_corner_length_cm: 10,
        extra_liner: 0,
    });
    const shapedObstacles = geometry.sheetObstaclesMm(
        { pieces: [betweenDoorsPiece, shapedNeighbour] },
        Object.assign({}, betweenDoorsPiece)
    );
    assert.equal(shapedObstacles[0].diagnostic.geometrySource, "placed_parametric_polygon");
    assert.equal(geometry.extensionConflict(betweenDoors.geometry.path, 5, openBoard, shapedObstacles), "");
}
const crowded = geometry.placedPolygonMm(placedLiner({ x: 40.1, width_cm: 30, length_cm: 50 }));
assert.equal(geometry.extensionConflict(betweenDoors.geometry.path, 5, openBoard, [{ polygon: crowded }]), "liner_extension_hits_piece");
// Door 5 regression: Regular obstacle rings follow placed w/h, not an oversized
// width_cm that forgot the matching rotation flag (false positive into kerf).
const doorFive = geometry.syntheticOverlay(placedLiner({
    id: 5,
    label: "5",
    x: 40.5,
    y: 0,
    w: 30,
    h: 50,
    width_cm: 30,
    length_cm: 50,
    liner_reference_side: "edge_long_left",
}));
assert.equal(doorFive.error, undefined);
const mismatchedNeighbor = {
    id: 4,
    label: "4",
    piece_type: "Regular",
    x: 0,
    y: 0,
    w: 40,
    h: 50,
    width_cm: 50,
    length_cm: 40,
    rotated: 0,
};
assert.deepEqual(copy(geometry.obstaclePolygonMm(mismatchedNeighbor)), [
    [0, 0], [400, 0], [400, 500], [0, 500],
]);
assert.equal(geometry.extensionConflict(doorFive.geometry.path, 5, openBoard, [
    { polygon: geometry.obstaclePolygonMm(mismatchedNeighbor) },
]), "");
assert.equal(geometry.extensionConflict(doorFive.geometry.path, 5, openBoard, [
    { polygon: geometry.placedPolygonMm(mismatchedNeighbor) },
]), "liner_extension_hits_piece");
const crowdedDetails = geometry.extensionConflictDetails(doorFive.geometry.path, 5, openBoard, [
    {
        polygon: geometry.placedPolygonMm(mismatchedNeighbor),
        diagnostic: { label: "4", geometrySource: "placed_parametric_polygon" },
    },
]);
assert.equal(crowdedDetails.code, "liner_extension_hits_piece");
assert.equal(crowdedDetails.obstacle.label, "4");
assert.equal(crowdedDetails.cutterRadiusMm, 2.5);
assert.ok(Number.isFinite(crowdedDetails.minimumDistanceMm));
assert.ok([
    "endpoint_in_material",
    "segment_crosses_material_boundary",
    "clearance_below_cutter_radius",
].includes(crowdedDetails.rejectCondition));
const doorFivePiece = placedLiner({
    id: 5, label: "5", x: 40.5, y: 0, w: 30, h: 50, width_cm: 30, length_cm: 50,
});
const selfCopy = Object.assign({}, doorFivePiece);
assert.equal(doorFivePiece === selfCopy, false);
assert.equal(geometry.samePlacedPiece(doorFivePiece, selfCopy), true);
assert.equal(geometry.samePlacedPiece(doorFivePiece, mismatchedNeighbor), false);
assert.equal(geometry.pieceQuarterTurns({ rotation_quarter_turns: 3, rotated: 0 }), 3);
assert.equal(geometry.pieceQuarterTurns({ rotated: 1 }), 1);

// Real persisted regression CP-2026-00092 / DCO 26-00112.
const nestedGlassSnapshot = JSON.parse(fs.readFileSync(
    path.resolve(__dirname, "../fixtures/liner_extension_nested_glass_snapshot.json"),
    "utf8"
));
const nestedPieces = nestedGlassSnapshot.sheets[0].pieces;
const nestedGlass = nestedPieces.find(piece => piece.label === "1.1");
const nestedDoorFive = nestedPieces.find(piece => piece.label === "5.1");
const nestedObstacles = geometry.sheetObstaclesMm(
    nestedGlassSnapshot.sheets[0],
    Object.assign({}, nestedDoorFive)
);
assert.equal(nestedObstacles.length, nestedPieces.length - 1);
assert.equal(nestedObstacles.some(obstacle => obstacle.diagnostic.pieceId === nestedDoorFive.id), false);
assert.equal(nestedObstacles.find(obstacle => obstacle.diagnostic.label === "1.1").holes.length, 1);
const nestedToolpath = geometry.syntheticOverlay(Object.assign({}, nestedDoorFive, {
    kerf_mm: 3,
    board: { minX: -5, minY: -5, maxX: 1215, maxY: 2435 },
}));
assert.equal(nestedToolpath.error, undefined);
assert.deepEqual(copy(nestedToolpath.geometry.path), [
    [80.5, 492.5], [80.5, 1075.5], [663.5, 1075.5], [663.5, 1078.5],
    [77.5, 1078.5], [77.5, 492.5], [74.5, 492.5], [74.5, 1081.5],
    [663.5, 1081.5], [663.5, 1084.5], [71.5, 1084.5], [71.5, 492.5],
    [68.5, 492.5], [68.5, 1087.5], [663.5, 1087.5], [663.5, 1090.5],
    [65.5, 1090.5], [65.5, 492.5],
]);
const glassObstacle = geometry.obstacleGeometryMm(nestedGlass);
assert.equal(glassObstacle.source, "placement_with_glass_hole");
assert.deepEqual(copy(glassObstacle.holes[0].map(point => point.map(value => Math.round(value * 1000) / 1000))), [
    [59, 491], [939, 491], [939, 2371], [59, 2371],
]);
const falseSolidDiagnostic = geometry.extensionConflictDetails(
    nestedToolpath.geometry.path,
    3,
    openBoard,
    [{ polygon: glassObstacle.outer, diagnostic: { label: "1.1" } }]
);
assert.equal(falseSolidDiagnostic.obstacle.label, "1.1");
assert.equal(falseSolidDiagnostic.rejectCondition, "endpoint_in_material");
assert.equal(falseSolidDiagnostic.segmentIndex, 0);
assert.ok(Math.abs(falseSolidDiagnostic.minimumDistanceMm - 60.5) < 1e-6);
assert.equal(falseSolidDiagnostic.cutterRadiusMm, 1.5);
assert.equal(geometry.extensionConflict(
    nestedToolpath.geometry.path,
    3,
    openBoard,
    nestedObstacles
), "");
const persistedUsableSheetObstacle = geometry.obstacleGeometryMm({
    piece_type: "Regular",
    x: 90,
    y: 80,
    w: 20,
    h: 10,
    rotated: true,
    geometry: {
        outer: [[100, 200], [300, 200], [300, 300], [100, 300]],
        holes: [[[140, 220], [260, 220], [260, 280], [140, 280]]],
    },
});
assert.equal(persistedUsableSheetObstacle.source, "persisted_geometry");
assert.deepEqual(copy(persistedUsableSheetObstacle.outer), [
    [100, 200], [300, 200], [300, 300], [100, 300],
]);
assert.deepEqual(copy(persistedUsableSheetObstacle.holes), [[
    [140, 220], [260, 220], [260, 280], [140, 280],
]]);
const partial = geometry.syntheticOverlay(placedLiner({
    liner_start_cm: 5,
    liner_length_cm: 20,
}));
assert.equal(partial.error, undefined);
assert.ok(straightSpan(partial.geometry.path, 0) > 10);
const startsInside = geometry.syntheticOverlay(placedLiner({ liner_start_cm: 5 }));
assert.equal(Math.round(Math.min(...startsInside.geometry.path.map(point => point[0])) * 10) / 10, 52.5);
assert.equal(Math.round(Math.max(...startsInside.geometry.path.map(point => point[0])) * 10) / 10, 402.5);
assert.ok(straightSpan(startsInside.geometry.path, 0) > 10);
const endsInside = geometry.syntheticOverlay(placedLiner({ liner_length_cm: 20 }));
assert.equal(Math.round(Math.min(...endsInside.geometry.path.map(point => point[0])) * 10) / 10, -2.5);
assert.equal(Math.round(Math.max(...endsInside.geometry.path.map(point => point[0])) * 10) / 10, 197.5);
["Clipped Corner", "L-Shaped Corner"].forEach(pieceType => {
    const shaped = geometry.syntheticOverlay(placedLiner({
        piece_type: pieceType,
        width_cm: 100,
        length_cm: 80,
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 20,
        clipped_corner_length_cm: 30,
        liner_reference_side: "edge_break",
        liner_offset_cm: 1,
        liner_width_cm: 0.8,
        kerf_mm: 4,
    }));
    assert.equal(shaped.error, undefined);
    const internal = geometry.syntheticOverlay(placedLiner({
        piece_type: pieceType,
        width_cm: 100,
        length_cm: 80,
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 20,
        clipped_corner_length_cm: 30,
        liner_reference_side: "edge_width_bottom",
        liner_start_cm: 4,
        liner_length_cm: 12,
    }));
    assert.equal(internal.error, undefined);
    assert.ok(straightSpan(internal.geometry.path, 0) > 10);
});
assert.deepEqual(
    copy(geometry.contourNotchCm({
        pieceType: "L-Shaped Corner",
        notchWidthCm: 8,
        notchLengthCm: 16,
        position: "Top Right",
        sideThicknessMm: { long_right: 3, width_top: 2, width_bottom: 1 },
        edgeBreak: true,
        innerMm: 1,
    })),
    { cutWidthCm: 7.8, cutLengthCm: 15.9 }
);
assert.deepEqual(
    copy(geometry.contourNotchCm({
        pieceType: "L-Shaped Corner",
        notchWidthCm: 8,
        notchLengthCm: 16,
        position: "Top Right",
        edgeBreak: true,
        innerMm: null,
    })),
    { cutWidthCm: 8, cutLengthCm: 16 }
);
for (const position of ["Top Right", "Top Left", "Bottom Right", "Bottom Left"]) {
    assert.deepEqual(
        copy(geometry.contourNotchCm({
            pieceType: "L-Shaped Corner",
            notchWidthCm: 20,
            notchLengthCm: 30,
            position,
            sideThicknessMm: {},
            edgeBreak: true,
            innerMm: 1,
        })),
        { cutWidthCm: 20.1, cutLengthCm: 30.1 }
    );
}
assert.deepEqual(
    copy(geometry.contourNotchCm({
        pieceType: "L-Shaped Corner",
        notchWidthCm: 20,
        notchLengthCm: 30,
        position: "Top Right",
        sideThicknessMm: { long_right: 1 },
        edgeBreak: true,
        innerMm: 1,
    })),
    { cutWidthCm: 20, cutLengthCm: 30.1 }
);
assert.deepEqual(
    copy(geometry.contourNotchCm({
        pieceType: "L-Shaped Corner",
        notchWidthCm: 20,
        notchLengthCm: 30,
        position: "Top Right",
        edgeBreak: false,
        innerMm: 0,
    })),
    { cutWidthCm: 20, cutLengthCm: 30 }
);
assert.deepEqual(
    copy(geometry.contourNotchCm({
        pieceType: "Clipped Corner",
        notchWidthCm: 54,
        notchLengthCm: 23,
        position: "Top Right",
        edgeBreak: true,
        innerMm: 1,
    })),
    { cutWidthCm: 54, cutLengthCm: 23 }
);

async function persistenceChecks() {
context.frappe.msgprint = () => {};
context.frappe.model = { set_value() { throw new Error("stale row write"); } };
const writes = [];
let releaseSave = () => {};
const saveGate = new Promise(resolve => { releaseSave = resolve; });
const currentRow = {
    doctype: "Door Cutting Order Detail",
    name: "current-row",
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
};
const staleRow = {
    doctype: "Door Cutting Order Detail",
    name: "stale-row",
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
};
fakeWindow.AlmdinaClippedCornerEditor = {
    resolveChildRow() { return currentRow; },
    queueChildApply(_frm, task) { return task(); },
    commitChildValues(_frm, row, values) {
        writes.push({ name: row.name, values });
        return saveGate;
    },
};
fakeWindow.AlmdinaDoorCuttingFastEntry = { render() {} };
const frm = { dirty() {}, doc: {} };
const linerValues = {
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
};
const firstSave = editor.applyLiner(frm, staleRow, linerValues);
const secondSave = editor.applyLiner(frm, staleRow, linerValues);
assert.equal(await secondSave, false);
releaseSave();
assert.equal(await firstSave, true);
assert.equal(writes.length, 1);
assert.equal(writes[0].name, "current-row");

fakeWindow.AlmdinaClippedCornerEditor.resolveChildRow = () => null;
assert.equal(await editor.applyLiner(frm, staleRow, linerValues), false);
assert.equal(writes.length, 1);

fakeWindow.AlmdinaClippedCornerEditor.resolveChildRow = () => Object.assign({}, currentRow, {
    piece_type: "Special",
});
assert.equal(await editor.applyLiner(frm, staleRow, linerValues), false);
assert.equal(writes.length, 1);
}

persistenceChecks().catch(error => {
    console.error(error);
    process.exit(1);
});
