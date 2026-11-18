const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const renderer = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");

assert.match(renderer, /mouse-pointer-2/);
assert.match(renderer, /pen-tool/);
assert.match(renderer, /waypoints/);
assert.match(renderer, /lock-open/);
assert.match(renderer, /data-abe-reference-upload/);
assert.match(renderer, /data-abe-reference-action="calibrate"/);
assert.match(renderer, /computePolylineHudPosition/);
assert.match(page, /canvas_renderer\.js\?v=56/);
assert.match(page, /controller\.js\?v=55/);
assert.match(page, /drawing_space\.js\?v=5/);
assert.match(page, /board_editor\.css\?v=51/);
assert.match(catalog, /Delete,حذف\n/);
assert.match(catalog, /Drawing X \(mm\),X \(مم\)/);
assert.match(catalog, /Drawing Y \(mm\),Y \(مم\)/);
assert.doesNotMatch(catalog, /Clipped corner,زاوية مقصوصة/);
