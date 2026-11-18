"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");

function load(relative, sandbox) {
    const file = path.join(root, relative);
    vm.runInNewContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
}

const css = fs.readFileSync(path.join(root, "public/css/door_cutting_order_operational_files.css"), "utf8");
const translations = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
const machineForm = fs.readFileSync(path.join(root, "almdina_erp/doctype/cnc_machine/cnc_machine.js"), "utf8");
const profileForm = fs.readFileSync(path.join(root, "almdina_erp/doctype/cnc_machining_profile/cnc_machining_profile.js"), "utf8");

const sandbox = {
    window: {},
    document: { documentElement: { lang: "en", getAttribute() { return "ltr"; } } },
    frappe: { boot: { lang: "en" } },
};
sandbox.window = sandbox;
load("public/js/almdina_locale.js", sandbox);
load("public/js/cnc/cnc_field_labels.js", sandbox);
load("public/js/cnc/cnc_tool_picker.js", sandbox);
load("public/js/cnc/artcam_machining_ux.js", sandbox);
load("public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js", sandbox);

const labels = sandbox.AlmdinaCncLabels;
const artcam = sandbox.AlmdinaArtcamMachining;
const ux = sandbox.AlmdinaOperationalFilesUX;

assert.strictEqual(labels.toolLabel("Stepdown"), "Stepdown");
assert.strictEqual(labels.toolLabel("Tool Name"), "Tool Name");
assert.strictEqual(labels.profileLabel("Profile Name"), "Profile Name");
assert.strictEqual(labels.activeStopFields("Bottom Left").join(","), "left_stop_cm,bottom_stop_cm");
assert.strictEqual(labels.activeStopFields("Bottom Right").join(","), "right_stop_cm,bottom_stop_cm");
assert.strictEqual(labels.activeStopFields("Top Left").join(","), "left_stop_cm,top_stop_cm");
assert.strictEqual(labels.activeStopFields("Top Right").join(","), "right_stop_cm,top_stop_cm");
assert.strictEqual(labels.activeStopFields("Center").join(","), "");

sandbox.frappe.boot.lang = "ar";
sandbox.document.documentElement.lang = "ar";
sandbox.__ = message => ({
    "Tool Name": "اسم الريشة",
    "Tool Number": "رقم الريشة",
    "Tool Diameter (mm)": "قطر الريشة (مم)",
    "Spindle Speed (RPM)": "سرعة الدوران (دورة/دقيقة)",
    "Stepdown": "عمق التمريرة",
    "Final Tool Offset": "الإزاحة النهائية للريشة",
    "Stepover Size": "مقدار التداخل",
    "Stepover Percent of D": "نسبة التداخل",
    "Feed Rate": "سرعة التغذية",
    "Plunge Rate": "سرعة الغطس",
    "Feed Rate (mm/sec)": "سرعة التغذية (مم/ث)",
    "Plunge Rate (mm/sec)": "سرعة الغطس (مم/ث)",
    "Notes": "الملاحظات",
    "Profile Name": "اسم البروفايل",
}[message] || message);
assert.strictEqual(labels.toolLabel("Tool Name"), "اسم الريشة");
assert.strictEqual(labels.toolLabel("Tool Number"), "رقم الريشة");
assert.strictEqual(labels.toolLabel("Tool Diameter (mm)"), "قطر الريشة (مم)");
assert.strictEqual(labels.toolLabel("Spindle Speed (RPM)"), "سرعة الدوران (دورة/دقيقة)");
assert.strictEqual(labels.toolLabel("Stepdown"), "عمق التمريرة (Stepdown)");
assert.strictEqual(labels.toolLabel("Final Tool Offset"), "الإزاحة النهائية للريشة (Final Tool Offset)");
assert.strictEqual(labels.toolLabel("Stepover Size"), "مقدار التداخل (Stepover - mm)");
assert.strictEqual(labels.toolLabel("Stepover Percent of D"), "نسبة التداخل (Stepover - %)");
assert.strictEqual(labels.toolLabel("Feed Rate (mm/sec)"), "سرعة التغذية (Feed Rate)");
assert.strictEqual(labels.toolLabel("Plunge Rate (mm/sec)"), "سرعة الغطس (Plunge Rate)");
assert.strictEqual(labels.toolLabel("Notes"), "الملاحظات (Notes)");
assert.strictEqual(labels.profileLabel("Profile Name"), "اسم البروفايل");
assert.ok(!labels.profileLabel("Profile Name").includes("(Profile Name)"));

function context(mode, ready, form, associations) {
    return {
        sheet: {
            machining: {
                availability: {
                    layers: [{ operation_key: "cut_path", dxf_layer: "CUT_PATH", disabled: false }],
                    vectors: [],
                    sheet_perimeter: { disabled: false },
                },
                associations: associations || [],
            },
        },
        state: {
            perimeterJoinMode: mode,
            perimeterGeometryReady: ready,
            artcamForm: form,
        },
    };
}

const form = {
    association_id: "association:edit",
    name: "Pocket",
    source: "layer:cut_path",
    profile_id: "profile-1",
    tool_preset: "T9",
    fields: { final_depth_mm: 6 },
    tool: { stepdown_mm: 4, tool_number: "9" },
    toolOpen: true,
};
const connected = artcam.sourceOptions(context("connected", true, form), form).map(row => row.value);
assert.ok(connected.includes("sheet_perimeter"));
assert.ok(connected.includes("layer:cut_path"));
const disconnected = artcam.sourceOptions(context("disconnected", null, form), form).map(row => row.value);
assert.ok(!disconnected.includes("sheet_perimeter"));
assert.ok(disconnected.includes("layer:cut_path"));

const editing = { ...form, source: "sheet_perimeter" };
const state = context("disconnected", null, editing).state;
artcam.clearEditingPerimeterSource(state);
assert.strictEqual(state.artcamForm.source, "");
assert.strictEqual(state.artcamForm.name, "Pocket");
assert.strictEqual(state.artcamForm.profile_id, "profile-1");
assert.strictEqual(state.artcamForm.fields.final_depth_mm, 6);
assert.strictEqual(state.artcamForm.tool.stepdown_mm, 4);

const owned = artcam.sourceOptions(context("connected", true, form, [{
    association_id: "association:saved",
    name: "Outer",
    selection: { kind: "sheet_perimeter" },
    vector_ids: ["cut_path:sheet_perimeter"],
    profile_id: "profile-1",
}]), form).map(row => row.value);
assert.ok(!owned.includes("sheet_perimeter"));

const stale = { perimeterJoinMode: "disconnected", perimeterGeometryReady: null, artcamForm: { ...form } };
assert.strictEqual(ux.acceptPerimeterPreview(stale, 1, 2, "connected", { issues: [] }), false);
assert.strictEqual(stale.perimeterGeometryReady, null);
const current = { perimeterJoinMode: "connected", perimeterGeometryReady: null, artcamForm: { ...form, source: "layer:cut_path" } };
assert.strictEqual(ux.acceptPerimeterPreview(current, 2, 2, "connected", { issues: [] }), true);
assert.strictEqual(current.perimeterGeometryReady, true);
assert.strictEqual(ux.acceptPerimeterPreview(current, 3, 3, "connected", { issues: [{ code: "perimeter_not_closed" }] }), true);
assert.strictEqual(current.perimeterGeometryReady, false);

const toolState = {
    artcamForm: {
        association_id: "association:tool",
        name: "Edge",
        source: "layer:cut_path",
        profile_id: "profile-1",
        tool_preset: "T9",
        fields: { final_depth_mm: 8 },
        tool: { stepdown_mm: 3.5, tool_number: "9", feed_rate_mm_sec: 12 },
        toolOpen: false,
    },
};
const markup = artcam.markup({}, {
    machining: { profiles: [{ profile_id: "profile-1", name: "Finish", enabled: true }], associations: [], availability: { layers: [], vectors: [] } },
}, toolState);
assert.ok(markup.includes("data-tool-picker"));
assert.ok(markup.includes('aria-expanded="false"'));
assert.ok(markup.includes("data-tool-picker-panel hidden"));
assert.ok(markup.includes('data-field="stepdown_mm"'));
assert.ok(markup.includes('value="3.5"'));
assert.ok(markup.includes('value="12"'));
assert.ok(markup.indexOf("data-tool-picker-select") < markup.indexOf("data-tool-picker-settings"));
assert.equal(markup.includes("data-tool-settings-toggle"), false);
assert.ok(css.includes(".dco-tool-picker__face"));
assert.ok(css.includes("min-height: 32px"));
assert.equal(profileForm.includes("data-tool-settings-toggle"), false);
assert.ok(profileForm.includes("AlmdinaCncToolPicker"));
assert.ok(machineForm.includes("work_zero_position(frm)"));
assert.ok(machineForm.includes("apply_corner_stops(frm)"));
assert.ok(translations.includes("عمق التمريرة (مم)"));
assert.ok(translations.includes("المصادم الأيمن (سم)"));
assert.ok(translations.includes("المصادم العلوي (سم)"));
assert.ok(translations.includes("اسم الربط"));
const labelsSource = fs.readFileSync(path.join(root, "public/js/cnc/cnc_field_labels.js"), "utf8");
assert.ok(labelsSource.includes('position === "Center"'));
const machineMeta = fs.readFileSync(path.join(root, "almdina_erp/doctype/cnc_machine/cnc_machine.json"), "utf8");
assert.ok(!machineMeta.includes("Top Right\\nCenter"));

const reference = ux.physicalSheetOffsetCm({
    width_cm: 200,
    length_cm: 400,
    work_zero_position: "Top Right",
    width_stop_side: "Left Side",
    length_stop_side: "Bottom Side",
    left_stop_cm: 99,
    right_stop_cm: 5,
    bottom_stop_cm: 99,
    top_stop_cm: 10,
}, 120, 240);
assert.strictEqual(reference.offset_left_cm * 10, 800);
assert.strictEqual(reference.offset_bottom_cm * 10, 1600);
const physicalX = 200 + reference.offset_left_cm * 10;
const physicalY = 300 + reference.offset_bottom_cm * 10;
assert.strictEqual(physicalX - 2000, -1000);
assert.strictEqual(physicalY - 4000, -2100);

console.log("cnc_ux_refinements.test.js passed");
