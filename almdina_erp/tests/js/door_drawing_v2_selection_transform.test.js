"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

const publicJs = path.resolve(__dirname, "../../public/js");
require(path.join(publicJs, "door_drawing_v2/domain/precision_policy.js"));
require(path.join(publicJs, "door_drawing_v2/domain/geometry_engine.js"));
require(path.join(publicJs, "door_drawing_v2/domain/document_model.js"));
require(path.join(publicJs, "door_drawing_v2/interaction/workspace_policy.js"));
require(path.join(publicJs, "door_drawing_v2/application/selection_manager.js"));
require(path.join(publicJs, "door_drawing_v2/application/transform_manager.js"));

const v2 = window.AlmdinaDoorDrawingV2;
const documents = v2.DocumentModel;
const geometry = v2.Geometry;
const selection = v2.SelectionManager;
const transforms = v2.TransformManager;

let drawing = documents.createDocument({ widthMm: 800, heightMm: 2100 });
const line = documents.createObject("line", {
    start: { x: -500, y: 320 },
    end: { x: -286, y: 320 },
}, { id: "line-214" });
drawing = documents.addObject(drawing, line);

assert.equal(geometry.lineLength(line.geometry), 214, "A 214 mm line must stay exactly 214 mm outside door bounds");

let selected = selection.selectOnly(selection.clear(), "line-214");
assert.deepEqual(selected.ids, ["line-214"]);
assert.equal(selected.anchorId, "line-214");
selected = selection.toggle(selected, "line-2");
assert.deepEqual(selected.ids, ["line-214", "line-2"]);
selected = selection.toggle(selected, "line-2");
assert.deepEqual(selected.ids, ["line-214"]);
assert.deepEqual(selection.prune(drawing, selection.setMany(["line-214", "missing"])).ids, ["line-214"]);

let moved = transforms.translateSelection(drawing, ["line-214"], 3500, -1200);
let movedLine = moved.objects.find(object => object.id === "line-214");
assert.equal(geometry.lineLength(movedLine.geometry), 214, "Moving a line anywhere must not change its length");
assert.deepEqual(movedLine.geometry.start, { x: 3000, y: -880 });
assert.deepEqual(movedLine.geometry.end, { x: 3214, y: -880 });

let resized = transforms.setLineLength(moved, "line-214", 500, { anchor: "start", angleDeg: 90 });
let resizedLine = resized.objects.find(object => object.id === "line-214");
assert.equal(geometry.lineLength(resizedLine.geometry), 500);
assert.deepEqual(resizedLine.geometry.end, { x: 3000, y: -380 });

let endpointEdited = transforms.setLineEndpoint(
    resized,
    "line-214",
    "end",
    { x: 3450, y: -879.5 },
    { axisLock: "dominant" }
);
let editedLine = endpointEdited.objects.find(object => object.id === "line-214");
assert.equal(editedLine.geometry.end.y, resizedLine.geometry.start.y, "Shift-style dominant lock must make a mostly-horizontal edit exactly horizontal");
assert.equal(editedLine.geometry.end.x, 3450);

const bounds = transforms.selectionBounds(endpointEdited, ["line-214"]);
assert.equal(bounds.x, 3000);
assert.equal(bounds.y, -880);
assert.equal(bounds.width, 450);
assert.equal(bounds.height, 0);

console.log("Door Drawing V2 free selection and transform tests passed");
