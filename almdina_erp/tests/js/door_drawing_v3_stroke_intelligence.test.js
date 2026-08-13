"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_freehand_policy.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_stroke_intelligence.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/smart_stroke_corner_guard.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/tool_modifier_policy.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const I = V3.SmartStrokeIntelligence;
const C = V3.SmartStrokeCornerGuard;
const M = V3.ToolModifierPolicy;

const mouseState = I.createStabilizer("mouse", G.point(0, 0));
const penState = I.createStabilizer("pen", G.point(0, 0));
const mousePoint = I.pushStabilized(mouseState, G.point(10, 0), { motionScaleMm: 20 });
const penPoint = I.pushStabilized(penState, G.point(10, 0), { motionScaleMm: 20 });
assert.ok(mousePoint.x < penPoint.x, "Mouse preview should suppress hand jitter more aggressively than pen input");
assert.ok(penPoint.x < 10, "Pen input still receives light stabilization instead of bypassing the shared pipeline");

const mouseSeries = I.stabilizeSeries([
    G.point(0, 0), G.point(10, 2), G.point(20, -2), G.point(30, 1.5), G.point(40, 0),
], "mouse", { motionScaleMm: 18 });
assert.deepEqual(mouseSeries[0], G.point(0, 0));
assert.deepEqual(mouseSeries.at(-1), G.point(40, 0), "Live stabilization must preserve exact gesture endpoints for snapping/connection");

const roughRightAngle = [];
for (let x = 0; x <= 100; x += 5) roughRightAngle.push(G.point(x, x % 10 === 0 ? 0.45 : -0.4));
for (let y = 5; y <= 100; y += 5) roughRightAngle.push(G.point(y % 10 === 0 ? 100.45 : 99.55, y));
const automatic = I.interpret(roughRightAngle, {
    closed: false,
    straightToleranceMm: 2.4,
    simplifyToleranceMm: 1.2,
    straightRatio: 1.07,
    arcResidualRatio: 0.04,
    minimumSegmentMm: 20,
    smoothingPasses: 2,
    pathSmoothingPasses: 1,
    orthogonalAngleToleranceDeg: 10,
    preserveEndpoints: true,
    orthogonalize: true,
});
assert.equal(automatic.type, "path", "A clear corner drawn with one freehand gesture must remain the user's path unless correction is explicitly requested");
assert.equal(automatic.fidelity, true);
assert.deepEqual(automatic.points, roughRightAngle, "Automatic smart-pen interpretation must not rebuild an L stroke into straight segments");

const explicitCorner = C.sharpLineCorner(roughRightAngle, {
    straightToleranceMm: 2.4,
    straightRatio: 1.07,
    minimumSegmentMm: 20,
});
assert.ok(explicitCorner, "The line-corner recognizer remains available as an explicit assisted operation");
assert.equal(explicitCorner.type, "compound");
assert.equal(explicitCorner.segments.length, 2);
assert.deepEqual(explicitCorner.segments.map(segment => segment.type), ["line", "line"]);
assert.deepEqual(explicitCorner.segments[0].end, explicitCorner.segments[1].start, "Explicit split runs must share the exact same world-mm junction");
assert.ok(explicitCorner.cornerTurnDeg > 70, "Explicit corner recognition should still require a clearly deliberate change in direction");

const arcPoints = [];
for (let angle = -90; angle <= 10; angle += 5) {
    const radius = 80 + (angle % 10 === 0 ? 0.25 : -0.2);
    arcPoints.push(G.pointAt(G.point(200, 200), radius, angle));
}
const exactArc = I.arcThroughEndpoints(arcPoints, {
    straightToleranceMm: 1.5,
    arcResidualRatio: 0.04,
    minimumArcSweepDeg: 20,
    maximumArcSweepDeg: 335,
});
assert.ok(exactArc, "A curved run should remain recognizable for explicit assisted correction");
assert.equal(exactArc.type, "arc");
const reconstructedStart = G.pointAt(exactArc.center, exactArc.radiusMm, exactArc.startAngleDeg);
const reconstructedEnd = G.pointAt(exactArc.center, exactArc.radiusMm, exactArc.startAngleDeg + exactArc.sweepAngleDeg);
assert.ok(G.distance(reconstructedStart, arcPoints[0]) < 0.01, "Corrected arc must pass through the shared start junction");
assert.ok(G.distance(reconstructedEnd, arcPoints.at(-1)) < 0.01, "Corrected arc must pass through the shared end junction");

const irregular = [
    G.point(0, 0), G.point(12, 8), G.point(24, -5), G.point(36, 17), G.point(48, -12),
    G.point(60, 21), G.point(72, 2), G.point(84, 19), G.point(96, -4), G.point(108, 11),
];
const irregularResult = I.interpret(irregular, {
    closed: false,
    straightToleranceMm: 1,
    simplifyToleranceMm: 2,
    minimumSegmentMm: 28,
});
assert.equal(irregularResult.type, "path", "Intelligence must preserve genuinely irregular mouse gestures as freehand paths");
assert.deepEqual(irregularResult.points, irregular);

assert.equal(M.penConstraint({ altKey: true }), M.PEN_CONSTRAINTS.STRAIGHT, "Alt should request a perfectly straight pen gesture");
assert.equal(M.penConstraint({ shiftKey: true }), M.PEN_CONSTRAINTS.AXIS, "Shift should request an axis-constrained pen gesture");
assert.equal(M.penConstraint({ altKey: true, shiftKey: true }), M.PEN_CONSTRAINTS.AXIS, "Shift axis constraint should win when both modifiers are held");
assert.deepEqual(M.constrainEndpoint(G.point(0, 0), G.point(100, 12), M.PEN_CONSTRAINTS.AXIS), G.point(100, 0));
assert.deepEqual(M.constrainEndpoint(G.point(0, 0), G.point(12, 100), M.PEN_CONSTRAINTS.AXIS), G.point(0, 100));
assert.deepEqual(M.constrainEndpoint(G.point(0, 0), G.point(100, 12), M.PEN_CONSTRAINTS.STRAIGHT), G.point(100, 12));
assert.equal(M.effectiveTool("pen", true), "select", "Ctrl selection is temporary and must not overwrite the chosen pen tool");
assert.equal(M.effectiveTool("pen", false), "pen", "Releasing Ctrl must restore the chosen tool");
assert.equal(M.normalizeTool("rectangle"), "rectangle");

const entry = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_cutting_order_special_shape_ux.js"), "utf8");
const modifiers = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/tool_modifiers.js"), "utf8");
assert.match(entry, /application\/tool_modifier_policy\.js/);
assert.match(entry, /application\/tool_modifiers\.js/);
assert.ok(entry.indexOf("application/tool_modifier_policy.js") < entry.indexOf("presentation/canvas_view.js"), "Pure modifier policy must load before presentation/controllers");
assert.ok(entry.indexOf("application/magnetic_connection.js") < entry.indexOf("application/tool_modifiers.js"));
assert.ok(entry.indexOf("application/tool_modifiers.js") < entry.indexOf("application/smart_pen.js"), "Modifier controller must install before smart-pen capture handlers");
assert.match(entry, /__doorDrawingV3PersistentTools:\s*true/);
assert.match(entry, /__doorDrawingV3ModifierConstraints:\s*true/);
assert.match(entry, /__doorDrawingV3TemporarySelect:\s*true/);
assert.match(modifiers, /function beginConstrainedPen/);
assert.match(modifiers, /function promoteFreehandToConstraint/);
assert.match(modifiers, /options\.axisLock = true/);
assert.match(modifiers, /c\.persistentTool/);
assert.match(modifiers, /event\.key === "Control"/);
assert.match(modifiers, /G\.line\(nextId\("line"\)/);
assert.match(modifiers, /event\.stopImmediatePropagation\(\)/);
assert.doesNotMatch(modifiers, /special_shape_geometry_json\s*=/, "Modifier shortcuts must not fabricate manufacturing geometry");

console.log("Door Drawing V3 smart stroke intelligence and modifier-key tests passed");
