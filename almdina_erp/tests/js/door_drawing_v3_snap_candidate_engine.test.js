"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/bezier_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/vector_selection.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/snapping.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_path_snapping.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_guides.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/unified_snap_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/snap_candidate_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/professional_move_policy.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const C = V3.SnapCandidateEngine;
const P = V3.ProfessionalMovePolicy;
const S = V3.Snapping;

function doc(objects) {
    return { blank: { widthMm: 1000, heightMm: 1000 }, objects };
}

const sourceLine = G.line("source", G.point(100, 0), G.point(150, 0));
let result = C.resolve(doc([sourceLine]), [sourceLine], 49, 1, {
    viewportScale: 1,
    includeSourceTargets: true,
});
assert.equal(result.snapped, true, "Alt-drag copy must be allowed to snap against its own original geometry");
assert.equal(result.dx, 50);
assert.equal(result.dy, 0);
assert.equal(result.candidate.kind, "endpoint");
assert.equal(result.candidate.source.role, "start");
assert.equal(result.candidate.target.role, "end");
assert.equal(result.guide.type, "geometry-point");

const sticky = C.resolve(doc([sourceLine]), [sourceLine], 62, 0, {
    viewportScale: 1,
    includeSourceTargets: true,
    stickyCandidate: result.stickyCandidate,
});
assert.equal(sticky.snapped, true, "A captured endpoint snap should remain sticky inside the release tolerance");
assert.equal(sticky.dx, 50, "Sticky snap must resist small pointer jitter instead of vibrating between states");
assert.equal(sticky.candidate.sticky, true);

const ordinarySelfMove = C.resolve(doc([sourceLine]), [sourceLine], 3, 0, { viewportScale: 1 });
assert.equal(ordinarySelfMove.snapped, false, "Normal drag must not snap an object back onto itself");

const targetLine = G.line("target", G.point(0, 0), G.point(100, 0));
const movingLine = G.line("moving", G.point(200, 10), G.point(250, 10));
result = P.resolve(doc([targetLine, movingLine]), [movingLine], -98, -9, { viewportScale: 1 });
assert.equal(result.dx, -100, "Moving endpoint must snap exactly onto the target endpoint");
assert.equal(result.dy, -10);
assert.equal(result.geometryCandidate.kind, "endpoint");
assert.ok(result.guides.some(guide => guide.type === "geometry-point"));
assert.ok(result.guides.some(guide => guide.type === "assist-label" && guide.text === "نقطة إلى نقطة"));

const endpointToEdge = G.line("edge-source", G.point(30, 8), G.point(30, 28));
result = P.resolve(doc([targetLine, endpointToEdge]), [endpointToEdge], 0, 0, { viewportScale: 1 });
assert.equal(result.geometryCandidate.kind, "segment", "A nearby endpoint should land on an exact straight edge without a separate CAD tool");
assert.equal(result.dx, 0);
assert.equal(result.dy, -8);
assert.deepEqual(result.geometryCandidate.claimedAxes, ["y"], "Horizontal target edge should constrain only the perpendicular move axis");
assert.ok(result.guides.some(guide => guide.type === "geometry-segment"));
assert.ok(result.guides.some(guide => guide.type === "assist-label" && guide.text === "على الضلع"));

const continuation = G.line("continuation", G.point(150, 5), G.point(200, 5));
result = P.resolve(doc([targetLine, continuation]), [continuation], 0, 0, { viewportScale: 1 });
assert.equal(result.geometryCandidate.kind, "collinear", "Parallel line near a reference should become a simple same-line continuation");
assert.equal(result.dx, 0);
assert.equal(result.dy, -5);
assert.ok(result.guides.some(guide => guide.type === "geometry-line"));
assert.ok(result.guides.some(guide => guide.type === "assist-label" && guide.text === "على نفس الخط"));

result = P.resolve(doc([sourceLine]), [sourceLine], 49, 1, {
    viewportScale: 1,
    lockedAxis: "x",
    includeSourceTargets: true,
});
assert.equal(result.dx, 50, "Shift+Alt drag must keep the horizontal lock and still snap compatible endpoints");
assert.equal(result.dy, 0);
assert.equal(result.geometryCandidate.kind, "endpoint");

const a = G.rectangle("a", G.point(0, 0), 50, 50);
const b = G.rectangle("b", G.point(100, 0), 50, 50); // A-B gap = 50 mm
result = P.resolve(doc([a, b]), [b], 101, 2, {
    viewportScale: 1,
    includeSourceTargets: true,
});
assert.equal(result.dx, 100, "Alt-drag third copy should match the existing A-B spacing");
assert.equal(result.dy, 0, "The duplicate should also stay on the original row automatically");
assert.ok(result.guides.some(guide => guide.type === "spacing" && Math.abs(guide.distanceMm - 50) < 0.01));
assert.ok(result.guides.some(guide => guide.type === "spacing-reference" && Math.abs(guide.distanceMm - 50) < 0.01));
assert.ok(result.guides.some(guide => guide.type === "geometry-line"), "Same-row intelligence may be expressed as exact collinear geometry rather than a bounding-box alignment");

const sameRow = P.resolve(doc([b]), [b], 100, 3, {
    viewportScale: 1,
    includeSourceTargets: true,
});
assert.equal(sameRow.dx, 100);
assert.equal(sameRow.dy, 0, "The original must participate as a same-line reference during Alt-drag");
assert.ok(sameRow.guides.some(guide => guide.type === "geometry-line"));

const c = G.rectangle("c", G.point(200, 0), 50, 50);
const d = G.rectangle("d", G.point(400, 0), 50, 50);
const repeated = P.resolve(doc([a, b, c, d]), [d], -98, 3, { viewportScale: 1 });
assert.equal(repeated.dx, -100, "A fourth item should settle onto the repeated 50 mm series");
assert.equal(repeated.dy, 0);
assert.equal(repeated.spacingX.mode, "repeat-series");
assert.ok(repeated.spacingX.seriesReferences.length >= 2, "Repeated spacing should use the whole visible pattern, not one accidental pair");
assert.ok(repeated.guides.filter(guide => guide.type === "spacing-reference" && guide.series).length >= 2);
assert.ok(repeated.guides.some(guide => guide.type === "assist-label" && (guide.text === "على نفس الخط" || guide.text === "نفس المسافة")));

const curved = G.path(
    "curve",
    [G.point(0, 100), G.point(100, 100)],
    false,
    {},
    [
        { type: "smooth", out: { x: 20, y: 60 } },
        { type: "smooth", in: { x: -20, y: 60 } },
    ]
);
assert.equal(S.collectSegments(doc([curved])).length, 0, "Bezier chords must never be exposed as fake straight edges to smart move snapping");
assert.equal(C.targetSegments(doc([curved])).length, 0, "Candidate engine must keep curved geometry out of linear projection/collinearity rules");

console.log("Door Drawing V3 snap candidate and operator-friendly smart move tests passed");
