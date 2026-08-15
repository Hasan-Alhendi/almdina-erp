"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../../..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");

const bootstrap = read("almdina_erp/public/js/door_cutting_order/drawing/special_shape_facade.js");
const smartGuides = read("almdina_erp/public/js/door_drawing_v3/application/smart_guides.js");
const candidates = read("almdina_erp/public/js/door_drawing_v3/application/snap_candidate_engine.js");
const movePolicy = read("almdina_erp/public/js/door_drawing_v3/application/professional_move_policy.js");
const moveView = read("almdina_erp/public/js/door_drawing_v3/presentation/professional_move_view.js");
const moveApp = read("almdina_erp/public/js/door_drawing_v3/application/professional_move.js");
const orientedDomain = read("almdina_erp/public/js/door_drawing_v3/domain/oriented_transform_domain.js");
const orientedView = read("almdina_erp/public/js/door_drawing_v3/presentation/oriented_transform_view.js");
const orientedApp = read("almdina_erp/public/js/door_drawing_v3/application/oriented_transform.js");
const moveCss = read("almdina_erp/public/css/door_drawing_v3_professional_move.css");
const orientedCss = read("almdina_erp/public/css/door_drawing_v3_oriented_transform.css");

for (const modulePath of [
    "domain/oriented_transform_domain.js",
    "application/snap_candidate_engine.js",
    "application/professional_move_policy.js",
    "presentation/professional_move_view.js",
    "presentation/oriented_transform_view.js",
    "application/professional_move.js",
    "application/oriented_transform.js",
]) assert.match(bootstrap, new RegExp(modulePath.replaceAll("/", "\\/").replaceAll(".", "\\.")));
for (const flag of [
    "__doorDrawingV3AltDragDuplicate",
    "__doorDrawingV3ShiftAxisMove",
    "__doorDrawingV3EqualSpacingGuides",
    "__doorDrawingV3SnapCandidateEngine",
    "__doorDrawingV3DuplicateSnapTargets",
    "__doorDrawingV3GeometryPointSnap",
    "__doorDrawingV3EndpointSurfaceSnap",
    "__doorDrawingV3CollinearContinuation",
    "__doorDrawingV3RepeatedSpacingGuides",
    "__doorDrawingV3OperatorAssistLabels",
    "__doorDrawingV3ExactLinearSnapSafety",
    "__doorDrawingV3StickyMoveSnap",
    "__doorDrawingV3OrientedTransform",
    "__doorDrawingV3RotationHandle",
    "__doorDrawingV3RotationSnap",
    "__doorDrawingV3TransformPivot",
]) assert.match(bootstrap, new RegExp(`${flag}:\\s*true`));
assert.match(bootstrap, /door_drawing_v3_professional_move\.css/);
assert.match(bootstrap, /door_drawing_v3_oriented_transform\.css/);

const unifiedIndex = bootstrap.indexOf("application/unified_snap_engine.js");
const candidateIndex = bootstrap.indexOf("application/snap_candidate_engine.js");
const movePolicyIndex = bootstrap.indexOf("application/professional_move_policy.js");
assert.ok(unifiedIndex >= 0 && candidateIndex > unifiedIndex, "Move candidate engine must load after unified geometry features");
assert.ok(movePolicyIndex > candidateIndex, "Professional move policy must consume the candidate engine");

const forbiddenDom = /window\.document|globalThis\.document|document\.(querySelector|querySelectorAll|createElement|createElementNS|getElementById)|getBoundingClientRect|clientX|clientY/;
assert.match(candidates, /function bestPointCandidate\(/);
assert.match(candidates, /function bestSurfaceCandidate\(/);
assert.match(candidates, /function bestCollinearCandidate\(/);
assert.match(candidates, /function surfaceCandidate\(/);
assert.match(candidates, /function collinearCandidate\(/);
assert.match(candidates, /includeSourceTargets/);
assert.match(candidates, /stickyCandidate/);
assert.match(candidates, /claimedAxes/);
assert.match(candidates, /POINT_CAPTURE_PX/);
assert.match(candidates, /SEGMENT_CAPTURE_PX/);
assert.match(candidates, /COLLINEAR_CAPTURE_PX/);
assert.doesNotMatch(candidates, forbiddenDom, "Snap candidate engine must remain DOM independent world-mm policy");
assert.match(smartGuides, /curved:\s*Boolean\(segment\.curved\)/);
assert.match(smartGuides, /filter\(segment => !segment\.curved\)/);
assert.match(movePolicy, /function bestAlignment\(/);
assert.match(movePolicy, /function bestSpacing\(/);
assert.match(movePolicy, /function referenceGaps\(/);
assert.match(movePolicy, /function clusterReferenceGaps\(/);
assert.match(movePolicy, /repeat-series/);
assert.match(movePolicy, /نفس المسافة/);
assert.match(movePolicy, /على الضلع/);
assert.match(movePolicy, /على نفس الخط/);
assert.match(movePolicy, /Candidates\.resolve/);
assert.match(movePolicy, /includeSourceTargets/);
assert.match(movePolicy, /claimedAxes/);
assert.match(movePolicy, /lockedAxis/);
assert.doesNotMatch(movePolicy, forbiddenDom, "Move snapping policy must remain DOM independent");
assert.match(moveApp, /event\.altKey/);
assert.match(moveApp, /event\.shiftKey/);
assert.match(moveApp, /includeSourceTargets:\s*Boolean\(gesture\.duplicateMode\)/);
assert.match(moveApp, /stickyCandidate/);
assert.match(moveApp, /Duplicate and move/);
assert.match(moveApp, /c\.history\.execute/);
assert.match(moveApp, /vectorActiveTranslation/);
assert.match(moveView, /ddv3-move-spacing-label/);
assert.match(moveView, /spacing-reference/);
assert.match(moveView, /ddv3-move-duplicate-origin/);
assert.match(moveView, /geometry-point/);
assert.match(moveView, /geometry-segment/);
assert.match(moveView, /geometry-line/);
assert.match(moveView, /assist-label/);
assert.match(moveView, /ddv3-move-point-snap/);
assert.match(moveView, /ddv3-move-guide-surface/);
assert.match(moveView, /ddv3-move-guide-collinear/);

assert.match(orientedDomain, /function convexHull\(/);
assert.match(orientedDomain, /function minimumFrame\(/);
assert.match(orientedDomain, /function frameAtAngle\(/);
assert.match(orientedDomain, /function resizeMatrix\(/);
assert.match(orientedDomain, /function rotationDelta\(/);
assert.match(orientedDomain, /function snapAngle\(/);
assert.doesNotMatch(orientedDomain, forbiddenDom, "Oriented transform geometry must remain pure world-mm math");
assert.match(orientedView, /data-ddv3-oriented-transform-handle/);
assert.match(orientedView, /"rotate"/);
assert.match(orientedView, /"pivot"/);
assert.match(orientedView, /data-ddv3-oriented-prop="rotation"/);
assert.match(orientedView, /data-ddv3-oriented-prop="pivot-x"/);
assert.match(orientedView, /data-ddv3-oriented-prop="pivot-y"/);
assert.match(orientedApp, /O\.snapAngle\(absolute, 15\)/);
assert.match(orientedApp, /T\.rotateAround/);
assert.match(orientedApp, /event\.shiftKey/);
assert.match(orientedApp, /event\.altKey/);
assert.match(orientedApp, /localFlip/);
assert.match(orientedApp, /Set selection rotation/);
assert.match(orientedApp, /c\.history\.execute/);

assert.match(moveCss, /\.ddv3-move-guide-alignment/);
assert.match(moveCss, /\.ddv3-move-spacing-line/);
assert.match(moveCss, /\.ddv3-move-point-snap/);
assert.match(moveCss, /\.ddv3-move-guide-surface/);
assert.match(moveCss, /\.ddv3-move-guide-collinear/);
assert.match(moveCss, /\.ddv3-move-assist-label/);
assert.match(orientedCss, /\.ddv3-oriented-transform-outline/);
assert.match(orientedCss, /\.ddv3-oriented-rotation-handle/);
assert.match(orientedCss, /\.ddv3-oriented-pivot/);
assert.match(orientedCss, /\.ddv3-has-oriented-transform \.ddv3-transform-overlay/);
assert.doesNotMatch(moveCss + orientedCss, /^body\s*\{/m);
assert.doesNotMatch(moveCss + orientedCss, /^\.form-layout\s*\{/m);

console.log("Door Drawing V3 professional interaction architecture contracts passed");