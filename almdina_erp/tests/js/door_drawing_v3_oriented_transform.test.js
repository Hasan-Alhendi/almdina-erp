"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/bezier_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/vector_selection.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/transform_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/oriented_transform_domain.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const T = V3.TransformDomain;
const O = V3.OrientedTransformDomain;

function close(actual, expected, epsilon = 0.02, message = "") {
    assert.ok(Math.abs(actual - expected) <= epsilon, message || `${actual} ≈ ${expected}`);
}
function pointClose(actual, expected, epsilon = 0.02) {
    close(actual.x, expected.x, epsilon);
    close(actual.y, expected.y, epsilon);
}

const rectangle = G.rectangle("rect", G.point(0, 0), 100, 50);
let frame = O.minimumFrame([rectangle]);
close(frame.width, 100);
close(frame.height, 50);
close(frame.angleDeg, 0);
pointClose(frame.center, G.point(50, 25));

const rotated = T.transformObject(rectangle, T.rotateAround(G.point(50, 25), 30));
frame = O.minimumFrame([rotated]);
close(frame.width, 100, 0.1, "Minimum oriented frame should preserve real rotated width");
close(frame.height, 50, 0.1, "Minimum oriented frame should preserve real rotated height");
close(Math.abs(frame.angleDeg), 30, 0.1, "Oriented frame should follow object rotation instead of its screen AABB");

const preferred = O.frameForObjects([rotated], 30);
close(preferred.angleDeg, 30);
close(preferred.width, 100, 0.1);
close(preferred.height, 50, 0.1);

const east = O.handleWorld(preferred, "e");
const resize = O.resizeMatrix(preferred, "e", G.point(east.x + Math.cos(Math.PI / 6) * 50, east.y + Math.sin(Math.PI / 6) * 50));
close(resize.sx, 1.5, 0.02, "Moving the east handle 50 mm outward should grow a 100 mm frame to 150 mm");
close(resize.sy, 1, 0.02);

const corner = O.handleWorld(preferred, "ne");
const keepAspect = O.resizeMatrix(preferred, "ne", G.point(corner.x + 50, corner.y + 50), { keepAspect: true });
close(Math.abs(keepAspect.sx), Math.abs(keepAspect.sy), 0.001, "Shift resize must preserve aspect ratio");

const centerResize = O.resizeMatrix(preferred, "e", G.point(east.x + 25, east.y + Math.sin(Math.PI / 6) * 25), { fromCenter: true });
assert.ok(centerResize.sx > 1, "Alt resize should expand around the center");
pointClose(T.transformPoint(preferred.center, centerResize.matrix), preferred.center, 0.02);

const pivot = G.point(50, 25);
const start = G.point(100, 25);
const end = G.point(50, 75);
close(O.rotationDelta(pivot, start, end), 90);
close(O.snapAngle(23, 15), 30);
close(O.snapAngle(7, 15), 0);

const hull = O.convexHull([G.point(0, 0), G.point(100, 0), G.point(100, 50), G.point(0, 50), G.point(50, 25)]);
assert.equal(hull.length, 4, "Interior points must not affect the oriented selection frame");

console.log("Door Drawing V3 oriented transform domain tests passed");
