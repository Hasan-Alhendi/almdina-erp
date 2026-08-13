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
require(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/professional_move_policy.js"));

const V3 = global.window.AlmdinaDoorDrawingV3;
const G = V3.Geometry;
const D = V3.DocumentModel;
const P = V3.ProfessionalMovePolicy;

function doc(objects) {
    return { blank: { widthMm: 1000, heightMm: 1000 }, objects };
}

const moving = G.rectangle("moving", G.point(100, 100), 50, 50);
const aligned = G.rectangle("aligned", G.point(300, 260), 70, 60);
let result = P.resolve(doc([moving, aligned]), [moving], 198, 158, { viewportScale: 1 });
assert.equal(result.dx, 200, "Move should snap the moving left edge to the target left edge");
assert.equal(result.dy, 160, "Move should snap the moving bottom edge to the target bottom edge");
assert.ok(result.guides.some(guide => guide.type === "alignment" && guide.axis === "x"));
assert.ok(result.guides.some(guide => guide.type === "alignment" && guide.axis === "y"));

const left = G.rectangle("left", G.point(0, 100), 50, 50);
const right = G.rectangle("right", G.point(150, 100), 50, 50);
const middle = G.rectangle("middle", G.point(300, 100), 50, 50);
result = P.resolve(doc([left, right, middle]), [middle], -198, 0, { viewportScale: 1 });
assert.equal(result.dx, -200, "Move should settle exactly between two neighbors when the gaps become equal");
assert.ok(result.guides.filter(guide => guide.type === "spacing").length >= 2, "Equal spacing should show both distances");

const a = G.rectangle("a", G.point(0, 0), 50, 50);
const b = G.rectangle("b", G.point(100, 0), 50, 50); // 50 mm reference gap
const c = G.rectangle("c", G.point(260, 0), 50, 50);
result = P.resolve(doc([a, b, c]), [c], -58, 0, { viewportScale: 1 });
assert.equal(result.dx, -60, "Move should match an existing 50 mm neighbor gap");
assert.ok(result.guides.some(guide => guide.type === "spacing-reference" && Math.abs(guide.distanceMm - 50) < 0.01));

result = P.resolve(doc([moving, aligned]), [moving], 205, 90, { viewportScale: 1, lockedAxis: "x" });
assert.equal(result.dy, 0, "Shift-style X lock must block vertical movement even when vertical snapping exists");
assert.equal(result.lockedAxis, "x");
assert.ok(result.guides.some(guide => guide.type === "axis-lock" && guide.axis === "x"));

assert.doesNotThrow(() => D.replaceObject(doc([moving]), G.translateObject(moving, 20, 0)));
console.log("Door Drawing V3 professional move policy tests passed");
