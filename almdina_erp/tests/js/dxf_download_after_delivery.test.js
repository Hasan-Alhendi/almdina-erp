"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan");
const context = fs.readFileSync(path.join(root, "door_cutting_order_plan_context_actions_ux.js"), "utf8");
const exporter = fs.readFileSync(path.join(root, "secure_dxf_export.js"), "utf8");

function method(source, start, end, scope) {
    const begin = source.indexOf(start);
    const finish = source.indexOf(end, begin);
    assert.ok(begin >= 0 && finish > begin, `missing source method ${start}`);
    return vm.runInNewContext(`${source.slice(begin, finish)}; ${start.slice("function ".length, start.indexOf("("))}`, scope);
}

const operational = method(context, "function hasOperationalAccess(frm)", "function canApprove", {
    canMutateCurrentStage: () => true,
});
assert.equal(operational({doc: {status: "Delivered", production_path: "Cutting"}}), false);
assert.equal(operational({doc: {status: "At Drawing", production_path: "Cutting"}}), true);

const exportAllowed = method(context, "function canExport(frm, row)", "function uploadedFile", {
    workspaceCapabilities: () => ({export_dxf: true}),
    isEditing: () => false,
    rowHasPlan: () => true,
    can: (_frm, cap) => cap === "export_dxf",
    hasOperationalAccess: () => { throw new Error("read-only download must not ask for stage mutation"); },
});
assert.equal(exportAllowed({doc: {status: "Delivered"}}, {}), true);

const original = method(exporter, "function shouldDownloadOriginalUpload(planSource, options)", "function decodeBase64Bytes", {
    ORIGINAL_UPLOAD_SOURCES: new Set(["custom", "uploaded"]),
    preferOriginalUpload: (options) => options?.preferOriginalUpload !== false,
});
assert.equal(original("Custom", {preferOriginalUpload: false}), true);
assert.equal(original("Approved", {hasOriginalFile: true, preferOriginalUpload: false}), false);
assert.equal(original("Approved", {hasOriginalFile: true, preferOriginalUpload: true}), true);

console.log("Delivered cutting plan DXF download/read-only contract passed");
