"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/precision_input.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const P = V3.PrecisionInput;

const start = G.point(100, 200);
const pointer = G.point(400, 200);

const exactLine = P.lineFromInput(start, pointer, "214");
assert.ok(exactLine);
assert.equal(G.lineLength(exactLine), 214, "Typing 214 must create exactly 214 mm regardless of viewport pixels");
assert.deepEqual(exactLine.geometry.start, start);
assert.deepEqual(exactLine.geometry.end, G.point(314, 200));

const diagonalLine = P.lineFromInput(start, G.point(200, 300), "100");
assert.ok(diagonalLine);
assert.equal(G.lineLength(diagonalLine), 100);
assert.equal(G.lineAngle(diagonalLine), 45);

const rectangle = P.rectangleFromInput(G.point(0, 0), G.point(1000, 800), "600x350");
assert.ok(rectangle);
assert.equal(rectangle.geometry.widthMm, 600);
assert.equal(rectangle.geometry.heightMm, 350);

const reversedRectangle = P.rectangleFromInput(G.point(100, 100), G.point(0, 0), "80×40");
assert.deepEqual(reversedRectangle.geometry.origin, G.point(20, 60));
assert.equal(reversedRectangle.geometry.widthMm, 80);
assert.equal(reversedRectangle.geometry.heightMm, 40);

const defaultDiameter = P.parseCircle("500");
assert.equal(defaultDiameter.mode, "diameter");
assert.equal(defaultDiameter.radiusMm, 250);
const explicitRadius = P.parseCircle("r250");
assert.equal(explicitRadius.mode, "radius");
assert.equal(explicitRadius.radiusMm, 250);
const explicitDiameter = P.circleFromInput(G.point(0, 0), "d500");
assert.equal(explicitDiameter.geometry.radiusMm, 250);

assert.equal(P.parseArc("275", "radius").radiusMm, 275);
assert.equal(P.parseArc("90", "sweep").sweepAngleDeg, 90);
assert.equal(P.parseArc("-45", "sweep").sweepAngleDeg, -45);
const arc = P.arcFromSweep(G.point(0, 0), 275, 0, "90");
assert.equal(arc.geometry.radiusMm, 275);
assert.equal(arc.geometry.sweepAngleDeg, 90);
assert.equal(G.arcLength(arc), G.roundMm(275 * Math.PI / 2));

let circleState = P.state("circle", "size", "");
circleState = P.append(circleState, "r");
circleState = P.append(circleState, "2");
circleState = P.append(circleState, "5");
circleState = P.append(circleState, "0");
assert.equal(circleState.buffer, "r250");
assert.equal(P.display(circleState), "R  250 mm");

let rectangleState = P.state("rectangle", "size", "");
for (const key of ["6", "0", "0", "×", "3", "5", "0"]) rectangleState = P.append(rectangleState, key);
assert.equal(rectangleState.buffer, "600x350");
assert.equal(P.parseRectangle(rectangleState.buffer).heightMm, 350);
rectangleState = P.backspace(rectangleState);
assert.equal(rectangleState.buffer, "600x35");

assert.equal(P.parseLine("0"), null);
assert.equal(P.parseRectangle("600x"), null, "Incomplete two-value input must not silently commit a rectangle");
assert.equal(P.parseCircle("r0"), null);
assert.equal(P.parseArc("0", "sweep"), null);

console.log("Door Drawing V3 precision input tests passed");
