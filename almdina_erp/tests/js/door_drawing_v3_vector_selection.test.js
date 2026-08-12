"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/document.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/smart_path_domain.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/vector_selection.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const S = V3.VectorSelectionGeometry;

const left = G.rectangle("left", G.point(0, 0), 20, 20);
const middle = G.rectangle("middle", G.point(35, 10), 10, 10);
const right = G.rectangle("right", G.point(80, 0), 20, 40);
const diagonal = G.line("line", G.point(-20, -10), G.point(30, 30));
const circle = G.circle("circle", G.point(120, 50), 15);
const arc = G.arc("arc", G.point(200, 200), 50, 0, 90);
const pathObject = G.path("path", [G.point(0, 80), G.point(40, 80), G.point(40, 120), G.point(0, 120)], true);

assert.deepEqual(S.boundsOfObject(left), {
    left: 0, top: 0, right: 20, bottom: 20, width: 20, height: 20, cx: 10, cy: 10,
});
assert.deepEqual(S.boundsOfObject(diagonal), {
    left: -20, top: -10, right: 30, bottom: 30, width: 50, height: 40, cx: 5, cy: 10,
});
assert.deepEqual(S.boundsOfObject(circle), {
    left: 105, top: 35, right: 135, bottom: 65, width: 30, height: 30, cx: 120, cy: 50,
});
assert.deepEqual(S.boundsOfObject(arc), {
    left: 200, top: 200, right: 250, bottom: 250, width: 50, height: 50, cx: 225, cy: 225,
});
assert.deepEqual(S.boundsOfObject(pathObject), {
    left: 0, top: 80, right: 40, bottom: 120, width: 40, height: 40, cx: 20, cy: 100,
});

const group = S.unionBounds([left, middle, right]);
assert.deepEqual(group, { left: 0, top: 0, right: 100, bottom: 40, width: 100, height: 40, cx: 50, cy: 20 });

let document = D.create({ widthMm: 300, heightMm: 300 });
[left, middle, right].forEach(object => { document = D.addObject(document, object); });
const containRect = S.normalizeRect(G.point(-1, -1), G.point(46, 31));
assert.deepEqual([...S.idsInRect(document, containRect, "contain")], ["left", "middle"]);
const intersectRect = S.normalizeRect(G.point(18, 18), G.point(36, 25));
assert.deepEqual([...S.idsInRect(document, intersectRect, "intersect")], ["left", "middle"]);

const leftOffsets = S.alignOffsets([left, middle, right], "left");
assert.deepEqual(leftOffsets.left, { dx: 0, dy: 0 });
assert.deepEqual(leftOffsets.middle, { dx: -35, dy: 0 });
assert.deepEqual(leftOffsets.right, { dx: -80, dy: 0 });

const topOffsets = S.alignOffsets([left, middle, right], "top");
assert.equal(topOffsets.left.dy, 20, "Visual top uses maximum world Y because the canvas Y axis is inverted");
assert.equal(topOffsets.middle.dy, 20);
assert.equal(topOffsets.right.dy, 0);

const distributed = S.distributeOffsets([left, middle, right], "horizontal");
const movedMiddle = G.translateObject(middle, distributed.middle.dx, distributed.middle.dy);
const boxes = [left, movedMiddle, right].map(S.boundsOfObject);
const firstGap = boxes[1].left - boxes[0].right;
const secondGap = boxes[2].left - boxes[1].right;
assert.equal(firstGap, secondGap, "Horizontal distribution must create equal visible gaps");

assert.deepEqual([...S.segmentNodeIndices(pathObject, [0, 3])], [0, 1, 3], "Closing path segment maps back to the first node");
assert.deepEqual(S.midpointOfSegment(pathObject, 1), G.point(40, 100));

console.log("Door Drawing V3 vector selection tests passed");
