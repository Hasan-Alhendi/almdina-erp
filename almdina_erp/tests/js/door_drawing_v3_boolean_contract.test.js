"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../..");
const read = relative => fs.readFileSync(path.join(ROOT, relative), "utf8");

const activeFacade = read("public/js/door_cutting_order/drawing/special_shape_facade.js");
const domain = read("public/js/door_drawing_v3/domain/boolean_geometry_domain.js");
const view = read("public/js/door_drawing_v3/presentation/boolean_operations_view.js");
const application = read("public/js/door_drawing_v3/application/boolean_operations.js");
const persistence = read("public/js/door_drawing_v3/infrastructure/bezier_path_persistence.js");
const css = read("public/css/door_drawing_v3_boolean.css");

// Boolean operations remain regression-covered inside the retired V3 bounded
// subsystem. The public editor facade is owned exclusively by V4.
assert.match(activeFacade, /door_drawing_v4\/domain\/geometry\.js/);
assert.match(activeFacade, /door_drawing_v4\/presentation\/editor_controller\.js/);
assert.match(activeFacade, /__doorDrawingV4:\s*true/);
assert.doesNotMatch(activeFacade, /door_drawing_v3\//);
assert.doesNotMatch(activeFacade, /__doorDrawingV3Boolean/);

assert.match(domain, /DEFAULT_TOLERANCE_MM\s*=\s*0\.05/);
assert.match(domain, /OPERATIONS\s*=\s*Object\.freeze\(\["union",\s*"subtract",\s*"intersect",\s*"exclude"\]\)/);
assert.match(domain, /G\.flattenPath\(object, tolerance\)/);
assert.match(domain, /splitAtIntersections/);
assert.match(domain, /orientedBoundaryFragments/);
assert.match(domain, /fragmentsToContours/);
assert.match(domain, /selfIntersects/);
assert.match(domain, /pointInPolygon/);
assert.match(domain, /coreContours\(firstData\.points, secondData\.points/);
assert.doesNotMatch(domain, /document\.createElement|querySelector|frappe\./, "pure boolean domain must not own DOM or Frappe behavior");

assert.match(view, /selectedIds\(c\)/);
assert.match(view, /ids\.length !== 2/);
assert.match(view, /B\.isBooleanOperand/);
assert.match(view, /data-ddv3-boolean-action=\"\$\{action\}\"/);
assert.match(view, /button\("union",\s*"دمج"/);
assert.match(view, /button\("subtract",\s*"طرح"/);
assert.match(view, /button\("intersect",\s*"تقاطع"/);
assert.match(view, /button\("exclude",\s*"استبعاد"/);
assert.match(view, /A − B/);

assert.match(application, /B\.booleanContours\(primary, secondary, operation/);
assert.match(application, /D\.removeObject\(document, primary\.id\)/);
assert.match(application, /D\.removeObject\(document, secondary\.id\)/);
assert.match(application, /G\.path\(id, contour, true/);
assert.match(application, /D\.addObject\(document, object\)/);
assert.match(application, /c\.history\.execute\(document/);
assert.match(application, /c\.dirty = true/);
assert.match(application, /result\.approximated/);
assert.match(application, /Ctrl\+Z/);

assert.match(persistence, /authoritative:\s*"door_drawing_v3"/);
assert.match(persistence, /G\.flattenPath\(object, 0\.2\)/);

assert.match(css, /\.ddv3-boolean-actionbar/);
assert.match(css, /right:\s*64px/);
assert.match(css, /flex-direction:\s*column/);
assert.doesNotMatch(css, /\.ddv3-toolbar/, "Boolean controls must never modify the primary black bottom toolbar");

console.log("Door Drawing V3 Boolean legacy subsystem contracts passed; active facade remains V4");
