"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

global.window = {};
global.document = { documentElement: { lang: "ar" } };
global.frappe = { boot: { lang: "ar" } };

const source = fs.readFileSync(
    path.join(
        __dirname,
        "../public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js"
    ),
    "utf8"
);
vm.runInThisContext(source, { filename: "door_cutting_order_clipped_corner_ux.js" });

const geometry = window.AlmdinaClippedCornerGeometry;
assert.ok(geometry, "The shared clipped-corner geometry API should be available");

const piece = {
    piece_type: "Clipped Corner",
    width_cm: 100,
    length_cm: 200,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 40,
};

assert.deepEqual(
    geometry.points(piece, 100, 100),
    [[0, 0], [80, 0], [100, 20], [100, 100], [0, 100]],
    "Top-right clipping should create one diagonal and five polygon vertices"
);

const rotated = {
    ...piece,
    original_w: 100,
    original_h: 200,
    w: 200,
    h: 100,
    rotated: true,
};
assert.deepEqual(
    geometry.points(rotated, 200, 100),
    [[0, 0], [200, 0], [200, 80], [160, 100], [0, 100]],
    "A clockwise rotation should move top-right to bottom-right and swap cut distances"
);
assert.deepEqual(
    geometry.dxfPoints(rotated, 10, 20, 200, 100),
    [[10, 120], [210, 120], [210, 40], [170, 20], [10, 20]],
    "DXF coordinates should preserve the same rotated shape in a bottom-left coordinate system"
);

const defaults = geometry.baseConfig({
    piece_type: "Clipped Corner",
    width_cm: 80,
    length_cm: 200,
});
assert.equal(defaults.position, "Top Right");
assert.equal(defaults.cutWidth, 16);
assert.equal(defaults.cutLength, 40);
assert.equal(defaults.remainingWidth, 64);
assert.equal(defaults.remainingLength, 160);
assert.equal(geometry.remainingFromCut(100, 20), 80);
assert.equal(geometry.cutFromRemaining(100, 80), 20);
assert.equal(geometry.clampRemaining(100, 80), 80);
assert.equal(geometry.clampRemaining(50, 80), 49.9);
assert.equal(geometry.adjustCutForNewTotal(100, 20, 120), 40);
assert.equal(geometry.adjustCutForNewTotal(100, 20, 100), 20);

const resizedL = {
    piece_type: "L-Shaped Corner",
    width_cm: 120,
    length_cm: 220,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 40,
};
assert.equal(
    geometry.preserveRemainingOnResize(resizedL, {
        width: 100,
        length: 200,
        cutWidth: 20,
        cutLength: 40,
    }),
    true,
    "Resizing an L door must rewrite cut distances to keep remaining lengths"
);
assert.equal(resizedL.clipped_corner_width_cm, 40);
assert.equal(resizedL.clipped_corner_length_cm, 60);
assert.equal(geometry.remainingFromCut(120, resizedL.clipped_corner_width_cm), 80);
assert.equal(geometry.remainingFromCut(220, resizedL.clipped_corner_length_cm), 160);
assert.deepEqual(
    geometry.baseConfig(resizedL),
    {
        position: "Top Right",
        cutWidth: 40,
        cutLength: 60,
        remainingWidth: 80,
        remainingLength: 160,
        originalWidth: 120,
        originalLength: 220,
    },
    "Opening the shape editor after a resize must still show the same remaining sides"
);
assert.equal(
    geometry.preserveRemainingOnResize(
        { piece_type: "Regular", width_cm: 120, clipped_corner_width_cm: 20 },
        { width: 100, cutWidth: 20, length: 200, cutLength: 40 }
    ),
    false
);
assert.match(geometry.summary(piece), /أعلى اليمين/);
assert.match(geometry.summary(piece), /80×160 سم متبقي/);
assert.equal(geometry.isClipped({ piece_type: "Regular" }), false);
assert.equal(geometry.isCornerCut({ piece_type: "Regular" }), false);
assert.equal(geometry.isCornerCut(piece), true);
assert.equal(geometry.cutStyle(piece), "diagonal");
assert.equal(geometry.typeLabel(piece), "الزاوية الكسر");
assert.deepEqual(
    geometry.breakAdjacentSides("Bottom Right"),
    ["edge_width_bottom", "edge_long_right"]
);

const breakPiece = {
    ...piece,
    edge_width_top: 1,
    edge_long_right: 1,
    edge_width_bottom: 1,
    edge_break: 1,
};
geometry.applyEdgeBreakPolicy(breakPiece);
assert.equal(breakPiece.edge_break, 1);
assert.equal(breakPiece.edge_width_top, 0);
assert.equal(breakPiece.edge_long_right, 0);
assert.equal(breakPiece.edge_width_bottom, 1);

const mutuallyExclusive = {
    ...piece,
    edge_break: 0,
    edge_break_only: 1,
};
geometry.toggleEdgeSelection(mutuallyExclusive, "edge_break");
assert.equal(mutuallyExclusive.edge_break, 1);
assert.equal(mutuallyExclusive.edge_break_only, 0);
geometry.applyEdgeBreakPolicy(mutuallyExclusive);
assert.equal(mutuallyExclusive.edge_break, 1, "Applying the full-path policy again must not revert it to break-only");
assert.equal(mutuallyExclusive.edge_break_only, 0);
geometry.toggleEdgeSelection(mutuallyExclusive, "edge_break_only");
assert.equal(mutuallyExclusive.edge_break, 0);
assert.equal(mutuallyExclusive.edge_break_only, 1);

const editableCorner = {
    ...piece,
    edge_width_top: 0,
    edge_long_right: 0,
    edge_break: 0,
    edge_break_only: 0,
};
geometry.toggleEdgeSelection(editableCorner, "edge_break_only");
assert.equal(editableCorner.edge_break_only, 1, "Break-only can be added after creating the piece");
geometry.toggleEdgeSelection(editableCorner, "edge_break_only");
assert.equal(editableCorner.edge_break_only, 0, "Break-only can be removed after creating the piece");
geometry.toggleEdgeSelection(editableCorner, "edge_break");
assert.equal(editableCorner.edge_break, 1, "Full path can be added after creating the piece");
geometry.toggleEdgeSelection(editableCorner, "edge_break");
assert.equal(editableCorner.edge_break, 0, "Full path can be removed after creating the piece");
editableCorner.edge_break_only = 1;
geometry.toggleEdgeSelection(editableCorner, "edge_break");
assert.equal(editableCorner.edge_break, 1);
assert.equal(editableCorner.edge_break_only, 0, "Break-only can switch to full path");
geometry.toggleEdgeSelection(editableCorner, "edge_break_only");
assert.equal(editableCorner.edge_break, 0);
assert.equal(editableCorner.edge_break_only, 1, "Full path can switch to break-only");

const fullPathUpdates = window.AlmdinaClippedCornerEditor.cornerValueUpdates(
    { position: "Top Right", cutWidth: 20, cutLength: 40 },
    { ...editableCorner, edge_break: 1, edge_break_only: 0 }
);
assert.deepEqual(
    fullPathUpdates.slice(-2),
    [["edge_break_only", 0], ["edge_break", 1]],
    "Apply must clear break-only before persisting the full path"
);
const reopenedCorner = {
    ...piece,
    ...Object.fromEntries(fullPathUpdates),
};
geometry.applyEdgeBreakPolicy(reopenedCorner);
assert.equal(reopenedCorner.edge_break, 1, "Reopening must preserve the saved full path");
assert.equal(reopenedCorner.edge_break_only, 0);

const editableL = {
    ...piece,
    piece_type: "L-Shaped Corner",
    edge_break: 0,
    edge_break_only: 0,
};
geometry.toggleEdgeSelection(editableL, "edge_break");
assert.equal(editableL.edge_break, 1, "L corner banding can be added after creation");
geometry.toggleEdgeSelection(editableL, "edge_break");
assert.equal(editableL.edge_break, 0, "L corner banding can be removed after creation");

const breakOnlyWithOuterSides = {
    ...piece,
    edge_width_top: 1,
    edge_long_right: 1,
    edge_break_only: 1,
};
geometry.applyEdgeBreakPolicy(breakOnlyWithOuterSides);
assert.equal(breakOnlyWithOuterSides.edge_break, 1);
assert.equal(breakOnlyWithOuterSides.edge_break_only, 0);
assert.equal(breakOnlyWithOuterSides.edge_width_top, 0);
assert.equal(breakOnlyWithOuterSides.edge_long_right, 0);
const breakOnlyMarkup = geometry.edgeBandSvgMarkup(
    { ...piece, edge_break_only: 1 },
    100,
    100
);
assert.match(breakOnlyMarkup, /dco-edge-break-only-svg/);
assert.equal(
    (breakOnlyMarkup.match(/dco-edge-break-only-svg"[^>]*points="([^"]+)"/) || [])[1].split(" ").length,
    2,
    "Break-only highlighting must cover the diagonal segment only"
);

const breakMarkup = geometry.edgeBandSvgMarkup(
    {
        ...piece,
        edge_break: 1,
        edge_width_bottom: 1,
    },
    100,
    100
);
assert.match(breakMarkup, /dco-edge-break-svg/);
assert.match(breakMarkup, /polyline/);
assert.match(breakMarkup, /stroke-linecap="round"/);
assert.match(breakMarkup, /stroke-linejoin="round"/);
assert.match(
    geometry.edgeSelectionSummary({
        piece_type: "Clipped Corner",
        edge_break: 1,
        edge_width_bottom: 1,
    }),
    /الكسر/
);
assert.match(
    geometry.edgeSelectionSummary({
        piece_type: "Clipped Corner",
        edge_width_bottom: 1,
    }),
    /أسفل/
);

const diagonalVertices = {
    "Top Right": [1, 2],
    "Top Left": [0, 4],
    "Bottom Right": [2, 3],
    "Bottom Left": [4, 3],
};
for (const position of ["Top Right", "Top Left", "Bottom Right", "Bottom Left"]) {
    const corner = { ...piece, clipped_corner_position: position };
    const paths = geometry.clippedEdgePaths(corner, 50, 100);
    assert.ok(Math.abs(paths.top[0][1] - paths.top[1][1]) < 1e-7, `${position} top band must stay horizontal`);
    assert.ok(Math.abs(paths.bottom[0][1] - paths.bottom[1][1]) < 1e-7, `${position} bottom band must stay horizontal`);
    assert.ok(Math.abs(paths.left[0][0] - paths.left[1][0]) < 1e-7, `${position} left band must stay vertical`);
    assert.ok(Math.abs(paths.right[0][0] - paths.right[1][0]) < 1e-7, `${position} right band must stay vertical`);
    assert.deepEqual(
        paths.breakOnly,
        paths.break.slice(1, 3),
        `${position} break-only and full path must share the same inset diagonal`
    );
    const diagonal = paths.breakOnly;
    const visualDx = diagonal[1][0] - diagonal[0][0];
    const visualDy = diagonal[1][1] - diagonal[0][1];
    const boundary = geometry.points(corner, 50, 100);
    const [startIndex, endIndex] = diagonalVertices[position];
    const sourceDx = boundary[endIndex][0] - boundary[startIndex][0];
    const sourceDy = boundary[endIndex][1] - boundary[startIndex][1];
    assert.ok(
        Math.abs(visualDx * sourceDy - visualDy * sourceDx) < 1e-7,
        `${position} diagonal band must remain parallel to the clipped edge`
    );
    const insetDistance = Math.abs(
        sourceDy * (diagonal[0][0] - boundary[startIndex][0])
        - sourceDx * (diagonal[0][1] - boundary[startIndex][1])
    ) / Math.hypot(sourceDx, sourceDy);
    assert.ok(Math.abs(insetDistance - 1.75) < 1e-7, `${position} diagonal inset must match the outer-side inset`);
}

const shallowCorner = {
    ...piece,
    width_cm: 100,
    length_cm: 100,
    clipped_corner_width_cm: 90,
    clipped_corner_length_cm: 1,
};
const shallowBoundary = geometry.points(shallowCorner, 100, 100);
const shallowPaths = geometry.clippedEdgePaths(shallowCorner, 100, 100);
const shallowSourceDx = shallowBoundary[2][0] - shallowBoundary[1][0];
const shallowSourceDy = shallowBoundary[2][1] - shallowBoundary[1][1];
const shallowVisualDx = shallowPaths.breakOnly[1][0] - shallowPaths.breakOnly[0][0];
const shallowVisualDy = shallowPaths.breakOnly[1][1] - shallowPaths.breakOnly[0][1];
assert.ok(
    Math.abs(shallowVisualDx * shallowSourceDy - shallowVisualDy * shallowSourceDx) < 1e-7,
    "A shallow clipped edge must use a bounded bevel without tilting its banding line"
);
assert.ok(
    shallowPaths.break.flat().every(value => value >= 0 && value <= 100),
    "A shallow-corner banding path must stay inside the piece viewport"
);

const planPiece = {
    piece_type: "Clipped Corner",
    original_w: 100,
    original_h: 200,
    w: 100,
    h: 200,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 40,
    edge_break: 1,
    edge_width_top: 0,
    edge_long_right: 0,
    edge_width_bottom: 0,
    edge_long_left: 0,
};
const planBreakMarkup = geometry.edgeBandSvgMarkup(planPiece, 100, 100);
assert.match(
    planBreakMarkup,
    /dco-edge-break-svg/,
    "Plan placed pieces must render break banding from edge_break alone"
);

const lBreakPiece = {
    piece_type: "L-Shaped Corner",
    width_cm: 100,
    length_cm: 100,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 20,
    edge_break: 1,
    edge_width_top: 1,
    edge_long_right: 1,
    edge_width_bottom: 1,
};
geometry.applyEdgeBreakPolicy(lBreakPiece);
assert.equal(lBreakPiece.edge_break, 1);
assert.equal(lBreakPiece.edge_width_top, 1, "L corner strap must not clear outer sides");
assert.equal(lBreakPiece.edge_long_right, 1, "L corner strap must not clear outer sides");
assert.equal(lBreakPiece.edge_width_bottom, 1);
assert.equal(geometry.locksAdjacentSidesForBreak(lBreakPiece), false);
assert.equal(geometry.breakEdgeLabel(lBreakPiece), "قشاط الزاوية");
const lBreakMarkup = geometry.edgeBandSvgMarkup(lBreakPiece, 100, 100);
assert.match(lBreakMarkup, /dco-edge-break-svg/);
assert.equal(
    (lBreakMarkup.match(/dco-edge-break-svg"[^>]*points="([^"]+)"/) || [])[1].split(" ").length,
    3,
    "L corner strap path should cover only the inner notch (two edges)"
);
const lBreakPath = geometry.clippedEdgePaths(lBreakPiece, 100, 100).break;
assert.equal(lBreakPath[0][0], lBreakPath[1][0], "The first L strap segment must stay vertical");
assert.equal(lBreakPath[1][1], lBreakPath[2][1], "The second L strap segment must stay horizontal");
for (const position of ["Top Left", "Bottom Right", "Bottom Left"]) {
    const path = geometry.clippedEdgePaths({ ...lBreakPiece, clipped_corner_position: position }, 100, 100).break;
    const firstIsAxisAligned = path[0][0] === path[1][0] || path[0][1] === path[1][1];
    const secondIsAxisAligned = path[1][0] === path[2][0] || path[1][1] === path[2][1];
    assert.ok(firstIsAxisAligned && secondIsAxisAligned, `${position} L strap must follow the right-angle notch`);
}

const lPiece = {
    piece_type: "L-Shaped Corner",
    width_cm: 100,
    length_cm: 100,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 20,
};
assert.equal(geometry.isClipped(lPiece), false);
assert.equal(geometry.isLShaped(lPiece), true);
assert.equal(geometry.isCornerCut(lPiece), true);
assert.equal(geometry.cutStyle(lPiece), "L");
assert.equal(geometry.typeLabel(lPiece), "زاوية L");
assert.deepEqual(
    geometry.points(lPiece, 100, 100),
    [[0, 0], [80, 0], [80, 20], [100, 20], [100, 100], [0, 100]],
    "Top-right L clipping should insert a right-angle vertex instead of a diagonal"
);
assert.deepEqual(
    geometry.points({ ...lPiece, clipped_corner_position: "Top Left" }, 100, 100),
    [[20, 0], [100, 0], [100, 100], [0, 100], [0, 20], [20, 20]]
);
assert.deepEqual(
    geometry.points({ ...lPiece, clipped_corner_position: "Bottom Right" }, 100, 100),
    [[0, 0], [100, 0], [100, 80], [80, 80], [80, 100], [0, 100]]
);
assert.deepEqual(
    geometry.points({ ...lPiece, clipped_corner_position: "Bottom Left" }, 100, 100),
    [[0, 0], [100, 0], [100, 100], [20, 100], [20, 80], [0, 80]]
);

const rotatedL = {
    ...lPiece,
    width_cm: 100,
    length_cm: 200,
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 40,
    original_w: 100,
    original_h: 200,
    w: 200,
    h: 100,
    rotated: true,
};
assert.deepEqual(
    geometry.points(rotatedL, 200, 100),
    [[0, 0], [200, 0], [200, 80], [160, 80], [160, 100], [0, 100]],
    "A clockwise rotation should move an L top-right cut to a six-vertex bottom-right L"
);
assert.deepEqual(
    geometry.dxfPoints(rotatedL, 10, 20, 200, 100),
    [[10, 120], [210, 120], [210, 40], [170, 40], [170, 20], [10, 20]]
);

const squareFrame = geometry.previewFrame(100, 100);
assert.equal(squareFrame.width, squareFrame.height);
assert.equal(squareFrame.width, 220);
assert.equal(squareFrame.x, 100);
assert.equal(squareFrame.y, 30);

const squareCuts = {
    piece_type: "L-Shaped Corner",
    width_cm: 100,
    length_cm: 100,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 20,
    clipped_corner_length_cm: 20,
};
const squareCutPoints = geometry.points(squareCuts, squareFrame.width, squareFrame.height);
assert.equal(
    squareFrame.width - squareCutPoints[1][0],
    squareCutPoints[2][1],
    "Equal cut distances on a square piece should use the same pixel scale on both axes"
);
assert.equal(squareFrame.width - squareCutPoints[1][0], 44);

const diagonalSquare = geometry.points({
    ...squareCuts,
    piece_type: "Clipped Corner",
}, squareFrame.width, squareFrame.height);
assert.equal(squareFrame.width - diagonalSquare[1][0], diagonalSquare[2][1]);

const tallFrame = geometry.previewFrame(40, 200);
assert.equal(tallFrame.width / tallFrame.height, 40 / 200);
assert.equal(tallFrame.height, 220);
assert.equal(tallFrame.width, 44);

let printed = null;
global.frappe.msgprint = (payload) => {
    printed = payload;
};
global.frappe.ui = {
    Dialog: function Dialog() {
        throw new Error("Corner editor must not open before piece dimensions exist");
    },
};

window.AlmdinaClippedCornerEditor.open({}, {
    piece_type: "Clipped Corner",
    width_cm: 0,
    length_cm: 0,
});
assert.ok(printed, "Missing dimensions should show a guidance message instead of an error");
assert.match(printed.message, /أدخل عرض الدرفة وطولها أولًا، ثم افتح إعداد الزاوية/);

window.AlmdinaClippedCornerEditor.open({}, {
    piece_type: "L-Shaped Corner",
});
assert.match(printed.message, /أدخل عرض الدرفة وطولها أولًا، ثم افتح إعداد الزاوية/);

console.log("Clipped-corner and L-shaped geometry, rotation, DXF, defaults, and labels passed");
