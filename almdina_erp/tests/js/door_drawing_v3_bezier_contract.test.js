"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../..");
const read = relative => fs.readFileSync(path.join(ROOT, relative), "utf8");

const bootstrap = read("public/js/door_cutting_order/drawing/special_shape_facade.js");
const domain = read("public/js/door_drawing_v3/domain/bezier_path_domain.js");
const topologyDomain = read("public/js/door_drawing_v3/domain/path_topology_domain.js");
const selection = read("public/js/door_drawing_v3/domain/bezier_selection_domain.js");
const persistence = read("public/js/door_drawing_v3/infrastructure/bezier_path_persistence.js");
const view = read("public/js/door_drawing_v3/presentation/bezier_path_view.js");
const topologyView = read("public/js/door_drawing_v3/presentation/path_topology_view.js");
const editing = read("public/js/door_drawing_v3/application/bezier_path_editing.js");
const topologyApp = read("public/js/door_drawing_v3/application/path_topology.js");
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
before(bootstrap, "/domain/bezier_path_domain.js", "/domain/path_topology_domain.js");
before(bootstrap, "/domain/path_topology_domain.js", "/domain/vector_selection.js");
before(bootstrap, "/domain/vector_selection.js", "/domain/bezier_selection_domain.js");
before(bootstrap, "/infrastructure/smart_path_persistence.js", "/infrastructure/bezier_path_persistence.js");
before(bootstrap, "/presentation/smart_path_view.js", "/presentation/bezier_path_view.js");
before(bootstrap, "/presentation/bezier_path_view.js", "/presentation/path_topology_view.js");
before(bootstrap, "/application/smart_pen.js", "/application/bezier_path_editing.js");
before(bootstrap, "/application/bezier_path_editing.js", "/application/vector_editing.js");
before(bootstrap, "/application/vector_editing.js", "/application/path_topology.js");

assert.match(bootstrap, /door_drawing_v3_bezier\.css/);
assert.match(bootstrap, /__doorDrawingV3BezierPaths:\s*true/);
assert.match(bootstrap, /__doorDrawingV3BezierPen:\s*true/);
assert.match(bootstrap, /__doorDrawingV3AdvancedNodeEditing:\s*true/);
assert.match(bootstrap, /__doorDrawingV3BezierPersistence:\s*true/);
assert.match(bootstrap, /__doorDrawingV3PathTopology:\s*true/);
assert.match(bootstrap, /__doorDrawingV3PathJoinSplit:\s*true/);

assert.match(domain, /NODE_CORNER\s*=\s*"corner"/);
assert.match(domain, /NODE_SMOOTH\s*=\s*"smooth"/);
assert.match(domain, /NODE_SYMMETRIC\s*=\s*"symmetric"/);
assert.match(domain, /splitPathSegment:\s*splitSegment/);
assert.match(domain, /flattenPath/);
assert.match(domain, /pathBounds/);
assert.match(domain, /setPathHandle/);
assert.match(domain, /convertPathSegment/);

assert.match(topologyDomain, /function reversePath/);
assert.match(topologyDomain, /in:\s*current\.out,\s*out:\s*current\.in/);
assert.match(topologyDomain, /function openPath/);
assert.match(topologyDomain, /function closePath/);
assert.match(topologyDomain, /G\.splitPathSegment\(object, segment\.index, 0\.5\)/);
assert.match(topologyDomain, /function joinOpenPaths/);
assert.match(topologyDomain, /gapMm:\s*G\.roundMm\(pair\.distanceMm\)/);

assert.match(selection, /pathPointAtSegment\(object, Number\(segmentIndex\), 0\.5\)/);
assert.match(selection, /G\.pathBounds\(object\)/);
assert.match(persistence, /G\.flattenPath\(object, 0\.2\)/);
assert.match(persistence, /authoritative:\s*"door_drawing_v3"/);

assert.match(view, /data-ddv3-path-handle/);
assert.match(view, /ddv3-bezier-contextbar/);
assert.match(view, /data-ddv3-bezier-action=\"\$\{action\}\"/);
assert.match(view, /C \$\{c1\.x\}/);

assert.match(topologyView, /ddv3-bezier-contextbar/);
assert.match(topologyView, /dataset\.ddv3PathTopologyAction\s*=\s*action/);
assert.match(topologyView, /paths\.length === 2 && paths\.every\(path => !path\.geometry\.closed\)/);
assert.match(topologyView, /"join", "join", "ربط"/);
assert.match(topologyView, /"split-node"/);
assert.match(topologyView, /"split-segment"/);

assert.match(editing, /HANDLE_ANGLE_STEP_DEG\s*=\s*45/);
assert.match(editing, /event\.altKey/);
assert.match(editing, /event\.shiftKey/);
assert.match(editing, /G\.splitPathSegment/);
assert.match(editing, /commitPenDraft/);
assert.match(editing, /window\.addEventListener\("pointerdown"/);
assert.match(editing, /setNodeTypes/);
assert.match(editing, /setSegmentTypes/);

assert.match(topologyApp, /T\.togglePathClosed/);
assert.match(topologyApp, /T\.reversePath/);
assert.match(topologyApp, /T\.splitPathAtNode/);
assert.match(topologyApp, /T\.splitPathAtSegmentMidpoint/);
assert.match(topologyApp, /T\.joinOpenPaths/);
assert.match(topologyApp, /D\.removeObject\(document, result\.consumedId\)/);
assert.match(topologyApp, /\[data-ddv3-path-toggle\]/, "Legacy path toggle must be intercepted by the Bezier-safe topology owner");
assert.match(topologyApp, /key === "j" && joinSelected\(c\)/);

assert.match(css, /\.ddv3-bezier-handle/);
assert.match(css, /\.ddv3-bezier-tangent-line/);
assert.match(css, /\.ddv3-bezier-contextbar/);
assert.match(css, /\.ddv3-topology-control/);
assert.match(css, /\.ddv3-topology-separator/);
assert.match(css, /@media \(max-width: 900px\)/);

console.log("Door Drawing V3 Bezier and path topology architecture contracts passed");