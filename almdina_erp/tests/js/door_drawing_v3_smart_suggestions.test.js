"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../../public/js/door_drawing_v3");
global.window = {};
require(path.join(ROOT, "domain/geometry.js"));
require(path.join(ROOT, "domain/document.js"));
require(path.join(ROOT, "domain/smart_path_domain.js"));
require(path.join(ROOT, "application/smart_freehand_policy.js"));
require(path.join(ROOT, "application/smart_suggestion_policy.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const P = V3.SmartSuggestionPolicy;

const linePoints = [
    G.point(0, 0),
    G.point(20, 0.35),
    G.point(40, -0.25),
    G.point(60, 0.2),
    G.point(80, -0.15),
    G.point(100, 0.1),
];
const lineSnapshot = JSON.stringify(linePoints);
const lineSuggestion = P.analyze(linePoints, {
    closeReady: false,
    straightToleranceMm: 2,
    straightRatio: 1.05,
    simplifyToleranceMm: 1,
    smoothingPasses: 0,
});
assert.ok(lineSuggestion, "A clearly near-straight freehand stroke should receive an optional suggestion");
assert.equal(lineSuggestion.type, "line");
assert.equal(JSON.stringify(linePoints), lineSnapshot, "Suggestion analysis must never mutate the user's sampled points");
const lineCandidate = P.candidateObject(lineSuggestion, "source-path", { stroke: "#111", strokeWidthMm: 0.35 });
assert.equal(lineCandidate.type, "line");
assert.equal(lineCandidate.id, "source-path", "Accepting a suggestion should replace the source object in place");

const circlePoints = [];
for (let angle = 0; angle < 360; angle += 15) {
    const radius = 50 + (angle % 30 === 0 ? 0.25 : -0.2);
    circlePoints.push(G.pointAt(G.point(120, 80), radius, angle));
}
const circleSuggestion = P.analyze(circlePoints, {
    closeReady: true,
    straightToleranceMm: 1.5,
    circleResidualRatio: 0.04,
    arcResidualRatio: 0.04,
    simplifyToleranceMm: 1,
    smoothingPasses: 0,
});
assert.ok(circleSuggestion, "A clearly circular gesture may be proposed as a precise circle");
assert.equal(circleSuggestion.type, "circle");

const nearClosedIrregular = [
    G.point(0, 0),
    G.point(46, 12),
    G.point(72, 48),
    G.point(34, 86),
    G.point(-18, 42),
    G.point(3, 2),
];
const closeSuggestion = P.analyze(nearClosedIrregular, {
    closeReady: true,
    straightToleranceMm: 1,
    circleResidualRatio: 0.02,
    arcResidualRatio: 0.02,
    simplifyToleranceMm: 0.5,
    smoothingPasses: 0,
});
assert.ok(closeSuggestion);
assert.equal(closeSuggestion.type, "close", "A near-closed irregular stroke should be offered closure without replacing its shape");
const closedCandidate = P.candidateObject(closeSuggestion, "irregular-path", {});
assert.equal(closedCandidate.type, G.PATH_TYPE);
assert.equal(closedCandidate.geometry.closed, true);
assert.deepEqual(
    closedCandidate.geometry.points,
    nearClosedIrregular.slice(0, -1),
    "Close suggestion must preserve the drawn contour instead of rebuilding it"
);

const irregularOpen = [
    G.point(0, 0), G.point(12, 18), G.point(24, -9), G.point(36, 26),
    G.point(48, -15), G.point(60, 21), G.point(72, -5), G.point(84, 16),
];
assert.equal(P.analyze(irregularOpen, {
    closeReady: false,
    straightToleranceMm: 1,
    circleResidualRatio: 0.01,
    arcResidualRatio: 0.01,
    simplifyToleranceMm: 0.5,
    smoothingPasses: 0,
}), null, "An ambiguous freehand shape should receive no automatic correction suggestion");

const entry = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_cutting_order_special_shape_ux.js"), "utf8");
const controller = fs.readFileSync(path.join(ROOT, "application/non_destructive_smart_suggestions.js"), "utf8");
const view = fs.readFileSync(path.join(ROOT, "presentation/smart_suggestion_view.js"), "utf8");
const smartPen = fs.readFileSync(path.join(ROOT, "application/smart_pen.js"), "utf8");
const css = fs.readFileSync(path.resolve(__dirname, "../../public/css/door_drawing_v3_smart_pen.css"), "utf8");

assert.match(entry, /application\/smart_suggestion_policy\.js/);
assert.match(entry, /presentation\/smart_suggestion_view\.js/);
assert.match(entry, /application\/non_destructive_smart_suggestions\.js/);
assert.ok(entry.indexOf("application/smart_suggestion_policy.js") < entry.indexOf("presentation/canvas_view.js"));
assert.ok(entry.indexOf("presentation/smart_path_view.js") < entry.indexOf("presentation/smart_suggestion_view.js"));
assert.ok(entry.indexOf("application/smart_pen.js") < entry.indexOf("application/non_destructive_smart_suggestions.js"));
assert.match(entry, /__doorDrawingV3NonDestructiveSuggestions:\s*true/);

assert.match(controller, /window\.addEventListener\("pointermove", onPointerMove, true\)/);
assert.match(controller, /window\.addEventListener\("pointerup", onPointerUp, true\)/);
assert.match(controller, /const previewPoint = closeReady \? raw/);
assert.match(controller, /points\[points\.length - 1\] = closeReady \? rawEnd : endSnap\.point/);
assert.match(controller, /closed:\s*false/);
assert.match(controller, /Suggest\.analyze/);
assert.match(controller, /D\.replaceObject\(c\.history\.current\(\), state\.candidate\)/);
assert.match(controller, /function acceptSuggestion/);
assert.match(controller, /function dismissSuggestion/);
assert.doesNotMatch(controller, /closeReady \? stroke\.startPoint/, "The non-destructive owner must never force the endpoint onto the start point");

assert.match(view, /ddv3-smart-suggestion-ghost/);
assert.match(view, /data-ddv3-suggestion-accept/);
assert.match(view, /data-ddv3-suggestion-dismiss/);
assert.match(view, /closeLabel\.textContent = "إغلاق\?"/);
assert.match(view, /يحافظ على رسمك/);
assert.match(css, /\.ddv3-smart-suggestion-ghost/);
assert.match(css, /\.ddv3-smart-suggestion-accept/);
assert.match(smartPen, /const CLOSE_CAPTURE_PX = 8/);
assert.match(smartPen, /const FREEHAND_ENDPOINT_SNAP_PX = 8/);

console.log("Door Drawing V3 non-destructive smart suggestions passed");
