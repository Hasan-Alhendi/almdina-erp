"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../../..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");

const bootstrap = read("almdina_erp/public/js/door_cutting_order_special_shape_ux.js");
const domain = read("almdina_erp/public/js/door_drawing_v3/domain/transform_domain.js");
const view = read("almdina_erp/public/js/door_drawing_v3/presentation/transform_box_view.js");
const application = read("almdina_erp/public/js/door_drawing_v3/application/transform_box.js");
const css = read("almdina_erp/public/css/door_drawing_v3_transform.css");

const bezierDomain = bootstrap.indexOf("domain/bezier_path_domain.js");
const transformDomain = bootstrap.indexOf("domain/transform_domain.js");
const vectorView = bootstrap.indexOf("presentation/vector_editing_view.js");
const transformView = bootstrap.indexOf("presentation/transform_box_view.js");
const shortcuts = bootstrap.indexOf("application/editor_shortcuts.js");
const transformApplication = bootstrap.indexOf("application/transform_box.js");
assert.ok(bezierDomain >= 0 && transformDomain > bezierDomain, "Transform domain must load after Bezier geometry");
assert.ok(vectorView >= 0 && transformView > vectorView, "Transform view must layer on top of vector selection view");
assert.ok(shortcuts >= 0 && transformApplication > shortcuts, "Transform interactions must install after professional keyboard policies");
assert.match(bootstrap, /door_drawing_v3_transform\.css/);
assert.match(bootstrap, /__doorDrawingV3TransformBox:\s*true/);
assert.match(bootstrap, /__doorDrawingV3TransformResize:\s*true/);
assert.match(bootstrap, /__doorDrawingV3TransformFlip:\s*true/);
assert.match(bootstrap, /__doorDrawingV3TransformInspector:\s*true/);

assert.match(domain, /function matrix\(/);
assert.match(domain, /function multiply\(/);
assert.match(domain, /function scaleAround\(/);
assert.match(domain, /function rotateAround\(/);
assert.match(domain, /function transformPoint\(/);
assert.match(domain, /function transformVector\(/);
assert.match(domain, /function transformPath\(/);
assert.match(domain, /function rectanglePath\(/);
assert.match(domain, /function circlePath\(/);
assert.match(domain, /function arcPath\(/);
assert.doesNotMatch(domain, /document\.|querySelector|getBoundingClientRect|clientX|clientY|\.style\.(?:transform|left|top|width|height|cssText)/, "Affine transforms must remain a pure world-mm domain without DOM presentation access");

for (const role of ["nw", "n", "ne", "e", "se", "s", "sw", "w"]) {
    assert.match(view, new RegExp(`"${role}"`), `Transform box should expose ${role} handle`);
}
assert.match(view, /data-ddv3-transform-handle/);
assert.match(view, /data-ddv3-transform-action="flip-horizontal"/);
assert.match(view, /data-ddv3-transform-action="flip-vertical"/);
assert.match(view, /data-ddv3-transform-prop="x"/);
assert.match(view, /data-ddv3-transform-prop="y"/);
assert.match(view, /data-ddv3-transform-prop="width"/);
assert.match(view, /data-ddv3-transform-prop="height"/);
assert.match(view, /Shift يحافظ على النسبة/);
assert.match(view, /Alt من المركز/);

assert.match(application, /function beginResize\(/);
assert.match(application, /function moveResize\(/);
assert.match(application, /function endResize\(/);
assert.match(application, /event\.shiftKey/);
assert.match(application, /event\.altKey/);
assert.match(application, /T\.scaleAround/);
assert.match(application, /S\.resolvePoint/);
assert.match(application, /c\.history\.execute/);
assert.match(application, /function flip\(/);
assert.match(application, /function transformProperty\(/);
assert.doesNotMatch(application, /special_shape_geometry_json\s*=/, "Transform UI must not fabricate manufacturing output from screen geometry");

assert.match(css, /\.ddv3-transform-outline/);
assert.match(css, /\.ddv3-transform-handle-dot/);
assert.match(css, /nwse-resize/);
assert.match(css, /nesw-resize/);
assert.match(css, /ns-resize/);
assert.match(css, /ew-resize/);
assert.match(css, /\.ddv3-transform-contextbar/);
assert.match(css, /\.ddv3-transform-inspector/);
assert.doesNotMatch(css, /^body\s*\{/m);
assert.doesNotMatch(css, /^\.form-layout\s*\{/m);

console.log("Door Drawing V3 professional transform architecture contract passed");
