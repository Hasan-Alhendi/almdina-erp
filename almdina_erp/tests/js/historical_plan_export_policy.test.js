"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_context_actions_ux.js"),
    "utf8",
);

function functionSource(name) {
    const start = source.indexOf(`function ${name}(`);
    assert.notEqual(start, -1, `${name} remains in the plan context action owner`);
    const open = source.indexOf("{", start);
    let depth = 0;
    for (let index = open; index < source.length; index += 1) {
        if (source[index] === "{") depth += 1;
        if (source[index] === "}") depth -= 1;
        if (depth === 0) return source.slice(start, index + 1);
    }
    throw new Error(`Unclosed function ${name}`);
}

let approvedPlan = "CP-APPROVED";
const workspaceData = () => ({ approved_plan: approvedPlan });
const isHistoricalRow = new Function(
    "workspaceData",
    `return (${functionSource("isHistoricalRow")})`,
)(workspaceData);
const hasOriginalDxfFile = row => Boolean(row.dxf && row.dxf.file);
const preferOriginalUpload = (_frm, row) => row.dxf.prefer_original_upload !== false;
const rowHasPlan = row => Boolean(row && row.snapshot_json);
const canExport = new Function(
    "workspaceCapabilities", "isEditing", "isHistoricalRow", "hasOriginalDxfFile",
    "preferOriginalUpload", "rowHasPlan", "can",
    `return (${functionSource("canExport")})`,
)(
    () => ({ export_dxf: true }),
    () => false,
    isHistoricalRow,
    hasOriginalDxfFile,
    preferOriginalUpload,
    rowHasPlan,
    () => true,
);

const historySystem = {
    name: "CP-SYSTEM-OLD",
    status: "Superseded",
    source_type: "System",
    display_context: "historical",
    snapshot_json: "{sheets: []}",
};
assert.equal(canExport({}, historySystem), false, "history cannot regenerate a manufacturing DXF");

const historyUpload = {
    name: "CP-UPLOAD-OLD",
    status: "Cancelled",
    source_type: "Uploaded DXF",
    display_context: "historical",
    snapshot_json: "{sheets: []}",
    dxf: { file: "/private/files/original.dxf", prefer_original_upload: true },
};
assert.equal(canExport({}, historyUpload), true, "a permitted source row can expose its attached archive");
historyUpload.dxf.prefer_original_upload = false;
assert.equal(canExport({}, historyUpload), false, "history cannot route to regeneration when no original download is selected");

const currentDraft = { ...historySystem, name: "CP-DRAFT", status: "Draft", display_context: "current_draft" };
assert.equal(canExport({}, currentDraft), true);
const currentApproved = {
    ...historySystem,
    name: "CP-APPROVED",
    status: "Approved",
    display_context: "current_approved",
};
assert.equal(isHistoricalRow({}, currentApproved), false);
approvedPlan = "CP-REPLACED";
currentApproved.display_context = "historical";
assert.equal(isHistoricalRow({}, currentApproved), true);

console.log("Historical DXF export is archive-only");
