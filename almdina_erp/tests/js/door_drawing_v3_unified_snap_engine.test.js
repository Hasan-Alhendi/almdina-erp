"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/text_annotation_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/snapping.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_path_snapping.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/move_snap_policy.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_guides.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/unified_snap_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/snap_axis_policy.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/advanced_snap_engine.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const S = V3.Snapping;

assert.equal(S.MOVE_JOIN_CAPTURE_PX, 20, "Whole-object magnetic join capture remains 20px");
assert.ok(S.INTENT_RANK.joint > S.INTENT_RANK.intersection);
assert.ok(S.INTENT_RANK.intersection > S.INTENT_RANK.perpendicular);
assert.ok(S.INTENT_RANK.perpendicular > S.INTENT_RANK.midpoint);
assert.ok(S.INTENT_RANK.midpoint > S.INTENT_RANK.surface);
assert.ok(S.INTENT_RANK.surface > S.INTENT_RANK.alignment);

// 1) After drawing, moving a vertical line can land its endpoint on the body
// of a lower line, not only on one of the lower line's endpoints.
let surfaceDoc = D.create({ widthMm: 1000, heightMm: 1000 });
const baseline = G.line("baseline", G.point(0, 0), G.point(500, 0));
const vertical = G.line("vertical", G.point(170, 100), G.point(170, 300));
surfaceDoc = D.addObject(surfaceDoc, baseline);
surfaceDoc = D.addObject(surfaceDoc, vertical);
const movedToSurface = S.resolveObjectMove(surfaceDoc, vertical, 0, -89, { viewportScale: 1 });
assert.equal(movedToSurface.snapped, true);
assert.equal(movedToSurface.kind, "surface");
assert.deepEqual(movedToSurface.object.geometry.start, G.point(170, 0));
assert.deepEqual(movedToSurface.object.geometry.end, G.point(170, 200));
assert.equal(movedToSurface.smartGuide.type, "surface");

// 2) Remote alignment works while moving an already-created object. The
// geometry is corrected, not only the guide rendered on screen.
let alignDoc = D.create({ widthMm: 1000, heightMm: 1000 });
const reference = G.line("reference", G.point(400, 0), G.point(400, 200));
const moving = G.line("moving", G.point(100, 20), G.point(100, 220));
alignDoc = D.addObject(alignDoc, reference);
alignDoc = D.addObject(alignDoc, moving);
const alignedMove = S.resolveObjectMove(alignDoc, moving, 0, -17, { viewportScale: 1 });
assert.equal(alignedMove.snapped, true);
assert.equal(alignedMove.kind, "alignment");
assert.equal(alignedMove.object.geometry.end.y, 200);
assert.equal(alignedMove.object.geometry.start.y, 0);
assert.equal(alignedMove.smartGuide.type, "horizontal-alignment");

// 3) Midpoint is a stronger intent than merely landing somewhere on an edge.
let midpointDoc = D.create({ widthMm: 500, heightMm: 500 });
const horizontal = G.line("horizontal", G.point(0, 0), G.point(200, 0));
const shortVertical = G.line("short", G.point(108, 5), G.point(108, 55));
midpointDoc = D.addObject(midpointDoc, horizontal);
midpointDoc = D.addObject(midpointDoc, shortVertical);
const midpointSnap = S.resolveObjectMove(midpointDoc, shortVertical, 0, 0, { viewportScale: 1 });
assert.equal(midpointSnap.snapped, true);
assert.equal(midpointSnap.kind, "midpoint");
assert.deepEqual(midpointSnap.object.geometry.start, G.point(100, 0));
assert.equal(midpointSnap.smartGuide.type, "midpoint");

// 4) Endpoint editing uses the same engine. When the dragged endpoint is close
// to the exact perpendicular foot on another segment, the stronger geometric
// intent wins over a generic surface placement.
let handleDoc = D.create({ widthMm: 500, heightMm: 500 });
const lower = G.line("lower", G.point(0, 0), G.point(300, 0));
const edited = G.line("edited", G.point(130, 100), G.point(130, 200));
handleDoc = D.addObject(handleDoc, lower);
handleDoc = D.addObject(handleDoc, edited);
const handleSurface = S.resolvePoint(handleDoc, G.point(131, 7), {
    anchor: edited.geometry.end,
    viewportScale: 1,
    excludeId: edited.id,
});
assert.equal(handleSurface.snapped, true);
assert.equal(handleSurface.kind, "perpendicular");
assert.deepEqual(handleSurface.point, G.point(130, 0));

// 5) Hysteresis keeps a deliberate connection stable beyond the capture
// radius, but only for the same geometric intent.
const firstSurface = S.resolveObjectMove(surfaceDoc, vertical, 0, -89, { viewportScale: 1 });
const stickySurface = S.resolveObjectMove(surfaceDoc, vertical, 0, -84, {
    viewportScale: 1,
    stickySource: firstSurface.source,
    stickyTarget: firstSurface.target,
    stickyKind: firstSurface.kind,
});
assert.equal(stickySurface.snapped, true);
assert.equal(stickySurface.kind, "surface");
assert.equal(stickySurface.sticky, true);
assert.equal(stickySurface.object.geometry.start.y, 0);

// 6) Shift/axis constraints never report a false exact joint. A nearby point
// off the constrained axis may still produce a guide, but the constrained
// geometry must stay on its exact X/Y axis.
let axisDoc = D.create({ widthMm: 500, heightMm: 500 });
axisDoc = D.addObject(axisDoc, G.line("off-axis", G.point(110, 10), G.point(110, 100)));
const axisSafe = S.resolvePoint(axisDoc, G.point(109, 10), {
    anchor: G.point(100, 0),
    axisLock: true,
    shiftKey: true,
    viewportScale: 1,
});
assert.equal(axisSafe.axis, "vertical");
assert.equal(axisSafe.point.x, 100);
assert.notEqual(axisSafe.kind, "joint");

// 7) Intersections are real geometry targets, not merely visual guides.
let intersectionDoc = D.create({ widthMm: 500, heightMm: 500 });
intersectionDoc = D.addObject(intersectionDoc, G.line("cross-h", G.point(0, 100), G.point(300, 100)));
intersectionDoc = D.addObject(intersectionDoc, G.line("cross-v", G.point(150, 0), G.point(150, 300)));
const intersectionSnap = S.resolvePoint(intersectionDoc, G.point(154, 104), { viewportScale: 1 });
assert.equal(intersectionSnap.snapped, true);
assert.equal(intersectionSnap.kind, "intersection");
assert.deepEqual(intersectionSnap.point, G.point(150, 100));
assert.equal(intersectionSnap.smartGuide.type, "intersection");

// 8) An edited endpoint can become exactly perpendicular to a target segment.
let perpendicularDoc = D.create({ widthMm: 500, heightMm: 500 });
perpendicularDoc = D.addObject(perpendicularDoc, G.line("perp-base", G.point(0, 0), G.point(300, 0)));
const perpendicularSnap = S.resolvePoint(perpendicularDoc, G.point(123, 6), {
    anchor: G.point(120, 140),
    viewportScale: 1,
});
assert.equal(perpendicularSnap.snapped, true);
assert.equal(perpendicularSnap.kind, "perpendicular");
assert.deepEqual(perpendicularSnap.point, G.point(120, 0));

// 9) Parallel intent preserves requested length when it is not close to an
// existing segment length.
let parallelDoc = D.create({ widthMm: 600, heightMm: 600 });
parallelDoc = D.addObject(parallelDoc, G.line("parallel-base", G.point(0, 0), G.point(300, 0)));
const parallelSnap = S.resolvePoint(parallelDoc, G.point(160, 205), {
    anchor: G.point(0, 200),
    viewportScale: 1,
});
assert.equal(parallelSnap.snapped, true);
assert.equal(parallelSnap.kind, "parallel");
assert.deepEqual(parallelSnap.point, G.point(160.078, 200));

// 10) Parallel and equal-length intents can combine into one exact result.
let parallelEqualDoc = D.create({ widthMm: 600, heightMm: 600 });
parallelEqualDoc = D.addObject(parallelEqualDoc, G.line("equal-base", G.point(0, 0), G.point(200, 0)));
const parallelEqual = S.resolvePoint(parallelEqualDoc, G.point(198, 204), {
    anchor: G.point(0, 200),
    viewportScale: 1,
});
assert.equal(parallelEqual.snapped, true);
assert.equal(parallelEqual.kind, "parallel-equal");
assert.deepEqual(parallelEqual.point, G.point(200, 200));
assert.deepEqual(Array.from(parallelEqual.intents), ["parallel", "equal-length"]);

// 11) Whole-object movement can land an endpoint on a geometric intersection
// without changing the line's own exact length.
const movable = G.line("move-to-cross", G.point(156, 106), G.point(156, 206));
let moveIntersectionDoc = D.addObject(intersectionDoc, movable);
const movedIntersection = S.resolveObjectMove(moveIntersectionDoc, movable, 0, 0, { viewportScale: 1 });
assert.equal(movedIntersection.snapped, true);
assert.equal(movedIntersection.kind, "intersection");
assert.deepEqual(movedIntersection.object.geometry.start, G.point(150, 100));
assert.deepEqual(movedIntersection.object.geometry.end, G.point(150, 200));
assert.equal(G.lineLength(movedIntersection.object), 100);

// 12) TXT is an annotation object in the same authoritative millimetre
// document. It survives translation, editing, and serialization exactly.
assert.ok(D.SUPPORTED_TYPES.includes("text"));
let textDoc = D.create({ widthMm: 800, heightMm: 2100 });
const note = G.text("txt-1", G.point(12.5, 33.25), "ملاحظة باب", { fontSizeMm: 28 });
textDoc = D.addObject(textDoc, note);
const translatedNote = G.translateObject(note, 10, -3);
assert.deepEqual(translatedNote.geometry.position, G.point(22.5, 30.25));
const editedNote = G.setText(translatedNote, { text: "ملاحظة جديدة", fontSizeMm: 36 });
textDoc = D.replaceObject(textDoc, editedNote);
const restoredTextDoc = D.normalize(JSON.parse(D.serialize(textDoc)));
const restoredNote = D.objectById(restoredTextDoc, "txt-1");
assert.equal(restoredNote.type, "text");
assert.equal(restoredNote.text, "ملاحظة جديدة");
assert.equal(restoredNote.style.fontSizeMm, 36);
assert.deepEqual(restoredNote.geometry.position, G.point(22.5, 30.25));

// 13) Browser integration contract: Text is a direct on-canvas tool, not a
// secondary Frappe modal, and advanced snapping is booted before the editor.
const publicRoot = path.resolve(__dirname, "../../public");
const bootstrapSource = fs.readFileSync(path.join(publicRoot, "js/door_cutting_order/drawing/special_shape_facade.js"), "utf8");
const textEditorSource = fs.readFileSync(path.join(publicRoot, "js/door_drawing_v3/application/text_annotation_editor.js"), "utf8");
const textViewSource = fs.readFileSync(path.join(publicRoot, "js/door_drawing_v3/presentation/text_annotation_view.js"), "utf8");
const textCssSource = fs.readFileSync(path.join(publicRoot, "css/door_drawing_v3_text.css"), "utf8");
assert.ok(bootstrapSource.includes("domain/text_annotation_domain.js"));
assert.ok(bootstrapSource.includes("application/advanced_snap_engine.js"));
assert.ok(bootstrapSource.includes("presentation/advanced_snap_view.js"));
assert.ok(bootstrapSource.includes("presentation/text_annotation_view.js"));
assert.ok(bootstrapSource.includes("application/text_annotation_editor.js"));
assert.ok(textViewSource.includes('data-ddv3-tool="text"'));
assert.ok(textEditorSource.includes("startInline"));
assert.ok(textEditorSource.includes('String(event.key || "").toLowerCase() === "t"'));
assert.ok(textEditorSource.includes('document.createElement("textarea")'));
assert.equal(textEditorSource.includes("frappe.ui.Dialog"), false, "Text editing must not open its own modal");
assert.ok(textCssSource.includes(".ddv3-text-object"));
assert.ok(textCssSource.includes(".ddv3-inline-text-editor"));

console.log("Door Drawing V3 unified/advanced snap and text annotation tests passed");
