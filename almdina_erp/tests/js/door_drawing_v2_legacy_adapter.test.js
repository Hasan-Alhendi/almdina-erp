"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};
require(path.resolve(__dirname, "../../public/js/door_drawing_v2/domain/precision_policy.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v2/domain/geometry_engine.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v2/domain/document_model.js"));
require(path.resolve(__dirname, "../../public/js/door_drawing_v2/infrastructure/legacy_adapter.js"));

const adapter = window.AlmdinaDoorDrawingV2.LegacyAdapter;

let migrated = adapter.fromRow({
    name:"ROW-1", width_cm:80, length_cm:210, qty:1,
    special_shape_geometry_json: JSON.stringify({
        version:1, kind:"polygon", units:"cm", template:"custom", blank_width_cm:80, blank_length_cm:210,
        points:[[0,0],[80,0],[80,210],[0,210]], exact:true,
    }),
});
assert.equal(migrated.status, "exact");
assert.equal(migrated.document.units, "mm");
assert.equal(migrated.document.door.width, 800);
assert.equal(migrated.document.door.height, 2100);
assert.deepEqual(migrated.document.objects[0].geometry.points[2], {x:800,y:2100});

migrated = adapter.fromRow({
    name:"ROW-2", width_cm:80, length_cm:210, qty:1,
    special_shape_drawing_json: JSON.stringify({ version:1, canvas:{width:1000,height:650}, elements:[
        { id:"l1", type:"line", color:"#111111", exact_line:{ version:1, units:"cm", start_cm:[0,0], end_cm:[21.4,0], length_cm:21.4, angle_deg:0 } },
        { id:"a1", type:"pen", color:"#111111", exact_arc:{ version:1, units:"cm", start_cm:[21.4,0], end_cm:[41.4,0], center_cm:[31.4,-7.5], radius_cm:12.5, rise_cm:5, side:1 } },
    ]}),
});
assert.equal(migrated.status, "exact");
const migratedLine = migrated.document.objects.find(item => item.id === "l1");
const migratedArc = migrated.document.objects.find(item => item.id === "a1");
assert.equal(migratedLine.geometry.end.x, 214, "Legacy exact centimeters must convert to exact millimeters");
assert.equal(migratedArc.geometry.radius, 125);

migrated = adapter.fromRow({
    name:"ROW-3", width_cm:80, length_cm:210, qty:1,
    special_shape_drawing_json: JSON.stringify({ version:1, canvas:{width:1000,height:650}, elements:[
        { id:"visual", type:"line", x1:10,y1:20,x2:400,y2:20,color:"#111111" },
    ]}),
});
assert.equal(migrated.status, "reference-only");
assert.equal(migrated.document.objects.filter(item => item.category === "geometry").length, 0, "Legacy screen coordinates must never be promoted to CNC geometry");
assert.ok(migrated.warnings.some(message => message.includes("reference-only")));

console.log("Door Drawing V2 legacy migration tests passed");
