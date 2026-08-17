"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
global.window = { AlmdinaDoorDrawingV4: Object.create(null), AlmdinaDoorDrawingProfessional: Object.create(null) };

for (const file of [
    "public/js/door_drawing_v4/domain/geometry.js",
    "public/js/door_drawing_v4/domain/document.js",
    "public/js/door_drawing_v4/domain/dimension.js",
    "public/js/door_drawing_v4/professional/editor_view_model.js",
]) require(path.join(root, file));

const v4 = global.window.AlmdinaDoorDrawingV4;
const professional = global.window.AlmdinaDoorDrawingProfessional;
let document = v4.DocumentModel.create({ widthMm: 500, heightMm: 700 });
document = v4.DocumentModel.addNode(document, { id: "n1", xMm: 20, yMm: 30 });
document = v4.DocumentModel.addNode(document, { id: "n2", xMm: 220, yMm: 30 });
document = v4.DocumentModel.addNode(document, { id: "n3", xMm: 220, yMm: 330 });
document = v4.DocumentModel.addNode(document, { id: "n4", xMm: 20, yMm: 330 });
document = v4.DocumentModel.addPath(document, { id: "p1", startNodeId: "n1" });
for (const segment of [
    { id: "s1", startNodeId: "n1", endNodeId: "n2" },
    { id: "s2", startNodeId: "n2", endNodeId: "n3" },
    { id: "s3", startNodeId: "n3", endNodeId: "n4" },
    { id: "s4", startNodeId: "n4", endNodeId: "n1" },
]) document = v4.DocumentModel.addLineToPath(document, "p1", segment);
document = v4.DocumentModel.closePath(document, "p1", "s4");

const state = { document, selection: { kind: "path", id: "p1" }, toolState: { activeTool: "select" } };
const box = professional.EditorViewModel.pathBounds(document, "p1");
assert.deepEqual(box, { xMm: 20, yMm: 30, widthMm: 200, heightMm: 300 });
assert.equal(professional.EditorViewModel.layers(state)[0].label, "محيط الدرفة");
const properties = professional.EditorViewModel.properties(state);
assert.equal(properties.kind, "path");
assert.ok(properties.values.some(item => item.label === "W" && item.value === "200 mm"));
assert.ok(properties.values.some(item => item.label === "H" && item.value === "300 mm"));

const overlaySource = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/professional/selection_overlay.js"), "utf8");
assert.ok(overlaySource.includes('const BLUE = "#0d99ff"'));
assert.ok(overlaySource.includes("sizeBadge(ctx, box, screenBox)"));
assert.ok(overlaySource.includes("handle(ctx, screenBox.x"));
assert.ok(!overlaySource.includes("frappe."), "selection overlay must remain presentation-only and Frappe-independent");

console.log("Professional selection view model and Figma overlay contract passed");
