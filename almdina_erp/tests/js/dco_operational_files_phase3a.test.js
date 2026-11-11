const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const panelPath = path.join(
    root,
    "public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"
);
const translationsPath = path.join(root, "translations/ar.csv");
const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

const markup = ux.programMarkup({
    sheet_width_mm: 1000,
    sheet_length_mm: 2000,
    machine_origin: "not_established",
    depth_convention: "positive_millimetres",
    issues: [],
    operations: [
        {
            operation_key: "liner",
            toolpaths: [
                {
                    path_key: "liner:a:1",
                    operation_key: "liner",
                    piece_label: "1.1",
                    closed: false,
                    direction: "start_to_end",
                    start: [10, 20],
                    end: [10, 80],
                    points: [[10, 20], [10, 80]],
                    preset_name: "Finish",
                    preset: { final_depth_mm: 7, tool_diameter_mm: 5 },
                    ready: true,
                    issues: [],
                    issue_messages: [],
                    motions: [
                        { kind: "travel", depth_mm: null },
                        { kind: "plunge", depth_mm: 7 },
                        { kind: "cut", depth_mm: 7 },
                        { kind: "retract", depth_mm: null },
                    ],
                },
            ],
        },
        {
            operation_key: "cut_path",
            toolpaths: [
                {
                    path_key: "cut_path:a:outer",
                    operation_key: "cut_path",
                    piece_label: "1.1",
                    closed: true,
                    direction: "ccw",
                    start: [0, 0],
                    end: [0, 0],
                    points: [[0, 0], [100, 0], [100, 40], [0, 40]],
                    preset_name: "Finish",
                    preset: { final_depth_mm: 18.5 },
                    ready: false,
                    issues: ["geometry_invalid"],
                    issue_messages: ["This path geometry cannot be used."],
                    motions: [],
                },
            ],
        },
    ],
});

assert.ok(markup.drawing.includes("#C62828"));
assert.ok(markup.drawing.includes("marker-end"));
assert.ok(markup.drawing.includes("translate(0,2000) scale(1,-1)"));
assert.ok(markup.list.includes("Depth {0} mm") || markup.list.includes("7"));
assert.ok(markup.list.includes("Tool diameter {0} mm") || markup.list.includes("Tool diameter 5 mm"));
assert.ok(markup.list.includes("1.1"));
assert.ok(markup.list.includes("This path geometry cannot be used."));
assert.ok(markup.list.includes("Counterclockwise") || markup.list.includes("عكس عقارب الساعة"));
assert.ok(markup.list.indexOf("liner") === -1 || markup.list.includes("Liner operation"));
assert.ok(!markup.list.includes("data-cnc-generate-nc"));
assert.ok(panel.includes("Generate NC file"));
assert.ok(panel.includes("collectProgramIssues"));
assert.ok(panel.includes("showGenerationIssueDialog"));
assert.ok(!markup.list.includes("G01"));
assert.ok(!markup.drawing.includes(".nc"));
assert.ok(panel.includes("get_cnc_sheet_program"));
assert.ok(panel.includes("generate_cnc_sheet_nc"));
assert.ok(!panel.includes("data-cnc-program"));
assert.ok(!panel.includes("scheduleProgram("));
assert.ok(!panel.includes("G01"));
assert.ok(translations.includes("توليد ملف NC"));
assert.ok(translations.includes("ما المشكلة؟"));
assert.ok(translations.includes("هذه المنطقة المغلقة ليست مسار ريشة، والخطة المعتمدة لا تتضمن إعدادات التفريز اللازمة لحسابه."));
assert.ok(translations.includes("مسار CUT_PATH {0} حُسب لسماكة القص المعتمدة ولا يطابق قطر الريشة المختارة."));
assert.ok(translations.includes("جُهّز NC للمحاكاة. هذا الملف غير معتمد لماكينة الورشة."));
assert.ok(translations.includes("أصل الماكينة غير محدد"));

console.log("dco_operational_files_phase3a.test.js passed");
