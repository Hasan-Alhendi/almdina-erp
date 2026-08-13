"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../..");
const read = relative => fs.readFileSync(path.join(ROOT, relative), "utf8");

const bootstrap = read("public/js/door_cutting_order_special_shape_ux.js");
const domain = read("public/js/door_drawing_v3/domain/bezier_path_domain.js");
const selection = read("public/js/door_drawing_v3/domain/bezier_selection_domain.js");
const persistence = read("public/js/door_drawing_v3/infrastructure/bezier_path_persistence.js");
const view = read("public/js/door_drawing_v3/presentation/bezier_path_view.js");
const editing = read("public/js/door_drawing_v3/application/bezier_path_editing.js");
const css = read("public/css/door_drawing_v3_bezier.css");

function position(source, token) {
    const index = source.indexOf(token);
    assert.ok(index >= 0, `Expected ${token}`);
    return index;
}
function before(source, first, second) {
    assert.ok(position(source, first) < position(source, second), `${first} must load before ${second}`);
}

before(bootstrap, "/domain/smart_path_domain.js", "/domain/bezier_path_domain.js");
before(bootstrap, "/domain/bezier_path_domain.js", "/domain/vector_selection.js");
before(bootstrap, "/domain/vector_selection.js", "/domain/bezier_selection_domain.js");
before(bootstrap, "/infrastructure/smart_path_persistence.js", "/infrastructure/bezier_path_persistence.js");
before(bootstrap, "/presentation/smart_path_view.js", "/presentation/bezier_path_view.js");
before(bootstrap, "/application/smart_pen.js", "/application/bezier_path_editing.js");
before(bootstrap, "/application/bezier_path_editing.js", "/application/vector_editing.js");

assert.match(bootstrap, /door_drawing_v3_bezier\.css/);
assert.match(bootstrap, /__doorDrawingV3BezierPaths:\s*true/);
assert.match(bootstrap, /__doorDrawingV3BezierPen:\s*true/);
assert.match(bootstrap, /__doorDrawingV3AdvancedNodeEditing:\s*true/);
assert.match(bootstrap, /__doorDrawingV3BezierPersistence:\s*true/);

assert.match(domain, /NODE_CORNER\s*=\s*"corner"/);
assert.match(domain, /NODE_SMOOTH\s*=\s*"smooth"/);
assert.match(domain, /NODE_SYMMETRIC\s*=\s*"symmetric"/);
assert.match(domain, /splitPathSegment:\s*splitSegment/);
assert.match(domain, /flattenPath/);
assert.match(domain, /pathBounds/);
assert.match(domain, /setPathHandle/);
assert.match(domain, /convertPathSegment/);

assert.match(selection, /pathPointAtSegment\(object, Number\(segmentIndex\), 0\.5\)/);
assert.match(selection, /G\.pathBounds\(object\)/);
assert.match(persistence, /G\.flattenPath\(object, 0\.2\)/);
assert.match(persistence, /authoritative:\s*"door_drawing_v3"/);

assert.match(view, /data-ddv3-path-handle/);
assert.match(view, /ddv3-bezier-contextbar/);
assert.match(view, /data-ddv3-bezier-action=\"node-type\"/);
assert.match(view, /data-ddv3-bezier-action=\"segment-type\"/);
assert.match(view, /C \$\{c1\.x\}/);

assert.match(editing, /HANDLE_ANGLE_STEP_DEG\s*=\s*45/);
assert.match(editing, /event\.altKey/);
assert.match(editing, /event\.shiftKey/);
assert.match(editing, /G\.splitPathSegment/);
assert.match(editing, /commitPenDraft/);
assert.match(editing, /window\.addEventListener\("pointerdown"/);
assert.match(editing, /setNodeTypes/);
assert.match(editing, /setSegmentTypes/);

assert.match(css, /\.ddv3-bezier-handle/);
assert.match(css, /\.ddv3-bezier-tangent-line/);
assert.match(css, /\.ddv3-bezier-contextbar/);
assert.match(css, /@media \(max-width: 900px\)/);

console.log("Door Drawing V3 Bezier architecture contracts passed");
