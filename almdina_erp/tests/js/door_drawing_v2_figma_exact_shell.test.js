"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const uxPath = path.resolve(
    __dirname,
    "../../public/js/door_drawing_v2/presentation/figma_exact_shell_ux.js"
);
const cssPath = path.resolve(
    __dirname,
    "../../public/css/door_drawing_v2_figma_exact.css"
);
const bootstrapPath = path.resolve(
    __dirname,
    "../../public/js/door_drawing_v2/bootstrap.js"
);

const ux = fs.readFileSync(uxPath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");
const bootstrap = fs.readFileSync(bootstrapPath, "utf8");

assert.match(ux, /dco-v2-left-panel/, "Figma shell must provide a left Layers\/Assets rail");
assert.match(ux, /data-v2-figma-tab="layers"/);
assert.match(ux, /data-v2-figma-tab="assets"/);
assert.match(ux, /data-figma-tool/);
assert.match(ux, /selectCreatedLine/, "A created line should return to selected-object editing instead of leaving a wizard open");
assert.match(ux, /SelectionOverlayUX\.render/);
assert.match(ux, /__doorDrawingV2FigmaExactIntegrated/);

assert.match(css, /grid-template-columns:\s*224px\s+minmax\(0,\s*1fr\)\s+272px/);
assert.match(css, /\.dco-v2-line-draft-panel/);
assert.match(css, /\.dco-exact-shape-card/);
assert.match(css, /\.dco-v2-line-draft-measurement text/);
assert.match(css, /fill:\s*#0788e5\s*!important/, "Live measurement should use the compact blue treatment");
assert.match(css, /background:\s*#fff\s*!important/, "The Design inspector should use the light panel treatment");
assert.doesNotMatch(css, /^body\s*\{/m, "Drawing-shell styling must stay scoped to the custom-door modal");

const lineTool = bootstrap.indexOf("line_tool_ux.js");
const figmaShell = bootstrap.indexOf("figma_exact_shell_ux.js");
assert.ok(lineTool >= 0 && figmaShell > lineTool, "Figma shell must load after the exact-line adapter it simplifies");

console.log("Door Drawing V2 Figma-exact shell contract passed");
