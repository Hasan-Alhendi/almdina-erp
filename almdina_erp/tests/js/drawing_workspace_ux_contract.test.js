"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicJs = path.resolve(__dirname, "../../public/js");
const workspacePath = path.join(publicJs, "door_cutting_order_drawing_workspace_ux.js");
const hooksPath = path.resolve(__dirname, "../../hooks.py");
const source = fs.readFileSync(workspacePath, "utf8");
const hooks = fs.readFileSync(hooksPath, "utf8");

assert.doesNotThrow(() => new Function(source), "Drawing workspace UX must remain valid JavaScript");

for (const marker of [
    "ضلع بمقاس",
    "الموصى به",
    "اضغط نقطة البداية",
    "وجّه الضلع",
    "اكتب الطول",
    "إضافة الضلع بهذا القياس",
    "خط توضيحي",
    "ليس له قياس إنتاجي",
    "القوالب الجاهزة",
    "افتح معرضًا واضحًا بدل القائمة الضيقة",
    "dco-drawing-workspace-gallery",
    "grid-template-columns:repeat(3,minmax(0,1fr))",
    "data-smart-template",
]) {
    assert.ok(source.includes(marker), `Drawing workspace should include ${marker}`);
}

const dimensionsUx = hooks.indexOf("door_cutting_order_exact_segment_dimensions_ux.js");
const workspaceUx = hooks.indexOf("door_cutting_order_drawing_workspace_ux.js");
const closeUx = hooks.indexOf("door_cutting_order_special_shape_close_ux.js");
assert.ok(dimensionsUx >= 0 && workspaceUx > dimensionsUx, "Workspace UX must load after exact dimensions UX");
assert.ok(closeUx > workspaceUx, "Workspace UX must load before modal close guard");

console.log("Simplified drawing workspace UX contract passed");
