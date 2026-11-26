"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const panelPath = path.join(
    root,
    "public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"
);
const pagePath = path.join(
    root,
    "almdina_erp/page/cnc_sheet_settings/cnc_sheet_settings.js"
);
const cssPath = path.join(root, "public/css/door_cutting_order_operational_files.css");
const translationsPath = path.join(root, "translations/ar.csv");

const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const pageSource = fs.readFileSync(pagePath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

assert.equal(ux.SHEET_PAGE_ROUTE, "cnc-sheet-settings");
assert.ok(typeof ux.openSheetSettingsTab === "function");
assert.ok(typeof ux.mountSheetSettingsPage === "function");
assert.ok(typeof ux.sheetSettingsUrl === "function");
assert.ok(panel.includes("openSheetSettingsTab("));
assert.ok(!panel.includes("openSheetDialog("));
assert.ok(!panel.includes("dco-operational-sheet-dialog"));
assert.ok(pageSource.includes('"/assets/almdina_erp/js/cnc/artcam_machining_ux.js?v=3"'));
assert.ok(pageSource.includes('"/assets/almdina_erp/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js?v=1"'));
assert.ok(pageSource.includes('door_cutting_order_operational_files.css?v=23'));
assert.ok(pageSource.includes("frappe.assets.load_asset(path, new URL(asset, window.location.origin).toString())"));
assert.ok(pageSource.includes('PAGE_ROUTE = "cnc-sheet-settings"'));
assert.ok(pageSource.includes("frappe.pages[PAGE_ROUTE]"));
assert.ok(pageSource.includes("mountSheetSettingsPage"));
assert.ok(css.includes(".dco-cnc-sheet-page"));
assert.ok(css.includes(".dco-operational-sheet .dco-artcam-readonly"));
assert.ok(css.includes("font-size: 14px"));
assert.ok(translations.includes("العودة إلى الطلب"));
assert.ok(translations.includes("إعدادات لوح CNC"));

assert.equal(
    ux.sheetSettingsUrl("DCO-1", 2),
    "/desk/cnc-sheet-settings/DCO-1/2"
);

const opened = [];
windowObject.open = (url, target) => {
    opened.push({ url, target });
    return { closed: false };
};
const url = ux.openSheetSettingsTab("DCO-9", 3);
assert.equal(url, "/desk/cnc-sheet-settings/DCO-9/3");
assert.equal(opened.length, 1);
assert.equal(opened[0].target, "_blank");
assert.equal(opened[0].url, url);

function motionChain(points, depth, closed) {
    const start = points[0];
    const motions = [
        { kind: "travel", x_mm: start[0], y_mm: start[1], depth_mm: null },
        { kind: "plunge", x_mm: start[0], y_mm: start[1], depth_mm: depth },
    ];
    points.slice(1).forEach(point => {
        motions.push({ kind: "cut", x_mm: point[0], y_mm: point[1], depth_mm: depth });
    });
    if (closed) {
        motions.push({ kind: "cut", x_mm: start[0], y_mm: start[1], depth_mm: depth });
    }
    const end = closed ? start : points[points.length - 1];
    motions.push({ kind: "retract", x_mm: end[0], y_mm: end[1], depth_mm: null });
    return motions;
}

function makeProgram() {
    const cutPoints = [[0, 0], [100, 0], [100, 100], [0, 100]];
    return {
        sheet_width_mm: 2440,
        sheet_length_mm: 1220,
        geometry_ready: true,
        ready: true,
        issues: [],
        operations: [
            {
                operation_key: "liner",
                toolpaths: [{
                    path_key: "liner:a",
                    operation_key: "liner",
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[10, 10], [40, 10]],
                    motions: motionChain([[10, 10], [40, 10]], 3, false),
                }],
            },
            {
                operation_key: "recessed_handle_cutout",
                toolpaths: [{
                    path_key: "recessed_handle_cutout:a",
                    operation_key: "recessed_handle_cutout",
                    closed: true,
                    ready: true,
                    issues: [],
                    points: [[50, 50], [70, 50], [70, 70], [50, 70]],
                    motions: motionChain([[50, 50], [70, 50], [70, 70], [50, 70]], 4, true),
                }],
            },
            {
                operation_key: "back_groove",
                toolpaths: [{
                    path_key: "back_groove:a",
                    operation_key: "back_groove",
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[20, 80], [90, 80]],
                    motions: motionChain([[20, 80], [90, 80]], 2, false),
                }],
            },
            {
                operation_key: "cut_path",
                toolpaths: [{
                    path_key: "cut_path:a",
                    operation_key: "cut_path",
                    closed: true,
                    ready: true,
                    issues: [],
                    points: [...cutPoints, cutPoints[0]],
                    motions: [
                        ...motionChain(cutPoints, 6, true),
                        ...motionChain(cutPoints, 12, true),
                    ],
                }],
            },
        ],
    };
}

function createDocumentDom() {
    const nodesById = new Map();
    function register(node) {
        if (node && node.id) nodesById.set(node.id, node);
        (node.children || []).forEach(register);
    }
    function parseSvgFragment(html) {
        const markerMatches = [...html.matchAll(/<marker\b([^>]*)>/g)];
        const markers = markerMatches.map(match => {
            const attrs = match[1];
            const id = ((attrs.match(/\bid="([^"]+)"/) || [])[1]) || "";
            return { id, tagName: "marker", attrs };
        });
        const refs = [...html.matchAll(/marker-end="url\(#([^"]+)\)"/g)].map(match => match[1]);
        markers.forEach(marker => {
            if (!nodesById.has(marker.id)) nodesById.set(marker.id, marker);
        });
        return { markers, refs };
    }
    return {
        getElementById(id) {
            return nodesById.get(id) || null;
        },
        paint(html) {
            return parseSvgFragment(html);
        },
        clear() {
            nodesById.clear();
        },
        ids() {
            return Array.from(nodesById.keys());
        },
    };
}

assert.equal(ux.CUT_PREVIEW_ZOOM.MIN, 1);
assert.equal(ux.CUT_PREVIEW_ZOOM.INITIAL, 1);
assert.equal(ux.CUT_PREVIEW_ZOOM.MAX, 16);
assert.equal(ux.CUT_PREVIEW_ZOOM.STEP, 0.5);
assert.equal(ux.clampCutPreviewZoom(0.1), 1);
assert.equal(ux.clampCutPreviewZoom(20), 16);
assert.equal(ux.PROGRAM_COLORS.cut_path, "#C62828");
assert.equal(ux.PROGRAM_COLORS.liner, "#C62828");
assert.equal(ux.PROGRAM_COLORS.recessed_handle_cutout, "#C62828");
assert.equal(ux.PROGRAM_COLORS.back_groove, "#C62828");
assert.equal(ux.PROGRAM_COLORS.sheet_perimeter, "#C62828");
assert.ok(css.includes("padding-inline: clamp("));
assert.ok(css.includes("overflow-x: hidden"));
assert.ok(!/dco-cnc-sheet-page \.dco-operational-sheet__settings \{\s*max-block-size: calc\(100vh - 11rem\);\s*overflow: auto;/.test(css));

const program = makeProgram();
const allExecutions = ux.collectCutExecutions(program);
assert.equal(allExecutions.length, 5);
assert.deepEqual(
    allExecutions.map(item => item.operation_key),
    ["liner", "recessed_handle_cutout", "back_groove", "cut_path", "cut_path"]
);
assert.ok(!allExecutions.some(item => !Array.isArray(item.points) || item.points.length < 2));

const colored = ux.cutPathPreviewMarkup(program, {
    markerScope: "cnc-multi",
    layout: "page",
    zoom: ux.CUT_PREVIEW_ZOOM.INITIAL,
});
assert.ok(!colored.includes("--cut-zoom:"));
assert.ok(!colored.includes("dco-cnc-cut-preview__legend"));
assert.ok(!colored.includes("data-cut-layer"));
assert.ok(!colored.includes("max-inline-size:390px"));
assert.ok(colored.includes("max-inline-size:100%"));
assert.ok(!colored.includes("dco-cnc-cut-preview__canvas-fill"));
assert.ok(colored.includes("dco-cnc-cut-preview__board-fill"));
assert.ok(colored.includes('patternTransform="rotate(45)"'));
assert.ok(colored.includes(ux.PROGRAM_COLORS.liner));
assert.ok(colored.includes(ux.PROGRAM_COLORS.recessed_handle_cutout));
assert.ok(colored.includes(ux.PROGRAM_COLORS.back_groove));
assert.ok(colored.includes(ux.PROGRAM_COLORS.cut_path));
assert.ok(colored.includes('data-operation-key="liner"'));
assert.ok(colored.includes('data-operation-key="back_groove"'));

const hiddenLiner = ux.cutPathPreviewMarkup(program, {
    markerScope: "cnc-hidden",
    layout: "page",
    hiddenOperations: ["liner"],
});
assert.ok(!hiddenLiner.includes('data-operation-key="liner"') || hiddenLiner.includes('data-cut-layer="liner"'));
assert.ok(!hiddenLiner.includes('data-execution-path="liner:a"'));
assert.ok(!hiddenLiner.includes('data-operation-key="liner"') || hiddenLiner.includes('data-cut-layer="liner"'));
assert.ok(hiddenLiner.includes('data-execution-path="cut_path:a"'));
assert.ok(hiddenLiner.includes("data-execution-path-id="));

const zoomHost = {
    innerHTML: "",
    setAttribute() {},
    removeAttribute() {},
    getAttribute() { return "page"; },
    querySelector(selector) {
        if (selector === "[data-cut-stage]") {
            const match = this.innerHTML.match(/data-cut-stage[^>]*style="([^"]*)"/);
            const styleText = (match && match[1]) || "";
            const props = {};
            styleText.split(";").forEach(part => {
                const [key, value] = part.split(":");
                if (key && value) props[key.trim()] = value.trim();
            });
            return {
                style: {
                    getPropertyValue(name) { return props[name] || ""; },
                    setProperty(name, value) { props[name] = String(value); },
                    transform: "",
                },
            };
        }
        if (selector === "[data-cut-viewport]") {
            return {
                classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
                getBoundingClientRect() { return { width: 800, height: 400 }; },
                addEventListener() {},
                setPointerCapture() {},
            };
        }
        if (selector === '[data-cut-zoom="out"]' || selector === '[data-cut-zoom="in"]') {
            return { disabled: false, addEventListener() {} };
        }
        return null;
    },
    querySelectorAll(selector) {
        if (selector === "[data-cut-zoom]" || selector === "[data-cut-layer]") return [];
        return [];
    },
};
ux.paintCutPathPreview(zoomHost, { status: "ready", program, layout: "page" });
assert.equal(zoomHost.__cutPreviewZoom, 1);
ux.paintCutPathPreview(zoomHost, {
    status: "ready",
    program,
    layout: "page",
    selectedPathKey: "cut_path:a",
    zoom: 0.85,
});
assert.equal(zoomHost.__cutPreviewZoom, 1);
ux.paintCutPathPreview(zoomHost, {
    status: "ready",
    program,
    layout: "page",
    selectedPathKey: "liner:a",
});
assert.equal(zoomHost.__cutPreviewZoom, 1, "the board stays inside its fitted viewport");
assert.equal(ux.clampCutPreviewZoom(1 - ux.CUT_PREVIEW_ZOOM.STEP), 1);
assert.equal(ux.clampCutPreviewZoom(16 + ux.CUT_PREVIEW_ZOOM.STEP), 16);

const staleDom = createDocumentDom();

// Prove the old fixed-id collision: second paint keeps resolving to the first marker.
const fixedA = `<defs><marker id="cnc-cut-arrow-1"></marker></defs><polyline marker-end="url(#cnc-cut-arrow-1)"/>`;
const fixedB = `<defs><marker id="cnc-cut-arrow-1"></marker></defs><polyline marker-end="url(#cnc-cut-arrow-1)"/>`;
staleDom.paint(fixedA);
staleDom.paint(fixedB);
assert.equal(staleDom.ids().filter(id => id === "cnc-cut-arrow-1").length, 1);
assert.equal(staleDom.getElementById("cnc-cut-arrow-1") !== null, true);

const liveDom = createDocumentDom();
const scopes = [];
for (let index = 0; index < 10; index += 1) {
    const scope = ux.nextCutPreviewScope();
    scopes.push(scope);
    const markup = ux.cutPathPreviewMarkup(program, {
        markerScope: scope,
        layout: "page",
        selectedPathKey: "cut_path:a",
    });
    const painted = liveDom.paint(markup);
    assert.ok(painted.markers.length >= 2);
    painted.refs.forEach(ref => {
        assert.ok(ref.startsWith(`${scope}-arrow-`), `ref ${ref} must stay inside scope ${scope}`);
        assert.equal(liveDom.getElementById(ref) !== null, true, `missing marker for ${ref}`);
    });
    assert.ok(markup.includes("data-path-markers"));
    assert.ok(!markup.includes("dco-cnc-cut-preview__badge"));
    assert.ok(markup.includes("font-size") || css.includes("font-size: 14px"));
    const cutPhysical = ux.collectPhysicalPaths(program).find(item => item.path_key === "cut_path:a");
    assert.ok(cutPhysical);
    assert.equal(cutPhysical.pass_count, 2);
    assert.ok(!markup.includes(`<span>${cutPhysical.path_number}</span>`));
    assert.ok(!markup.includes("<span>4,5</span>"), "depth passes must not keep dual badge numbers");
}

const uniqueScopes = new Set(scopes);
assert.equal(uniqueScopes.size, 10, "each paint must allocate a unique marker scope");
const allIds = liveDom.ids();
assert.equal(allIds.length, new Set(allIds).size, "marker ids across repeated paints must remain unique in the DOM");
assert.ok(!allIds.includes("cnc-cut-arrow-1"));

const host = {
    innerHTML: "",
    getAttribute() { return "page"; },
    setAttribute() {},
    removeAttribute() {},
};
for (let index = 0; index < 10; index += 1) {
    ux.paintCutPathPreview(host, {
        status: "ready",
        program,
        selectedPathKey: "cut_path:a",
        layout: "page",
    });
    const ids = ux.collectMarkerIdsFromMarkup(host.innerHTML);
    assert.ok(ids.length >= 2);
    assert.equal(ids.length, new Set(ids).size);
    ids.forEach(id => {
        assert.ok(host.innerHTML.includes(`marker-end="url(#${id})"`));
    });
}

assert.ok(panel.includes("data-preview-layout"));
assert.ok(panel.includes("mountSheetSettingsPage("));
assert.ok(!panel.includes("data-cnc-back-order"));
assert.ok(panel.includes("dco-cnc-sheet-page__actions"));
assert.ok(panel.includes("[data-cnc-page-actions]"));
assert.ok(panel.includes("Save sheet settings"));
assert.ok(panel.includes("Generate NC file"));
assert.ok(panel.includes("data-cnc-export-bar"));
assert.equal(panel.includes("data-cnc-post-processor"), false);
assert.ok(panel.includes("Complete the CNC machine settings. Choose the post processor on the machine before generating a new NC file."));
assert.equal(panel.includes("post_processor: String(state.postProcessor"), false);
assert.ok(panel.includes("_blank"));
assert.ok(css.includes("dco-operational-sheet__export"));
assert.ok(translations.includes("Post Processor,معالج المخرجات"));
assert.ok(translations.includes("IMA-WH (*.nc),IMA-WH (*.nc)"));

const restored = ux.sheetState({
    sheet_no: 1,
    settings_revision: 12,
    post_processor: "ima_wh_ncstudio",
    operations: [],
    paths: [],
});
assert.equal(restored.postProcessor, undefined);
assert.equal(restored.settingsRevision, 12);
const unset = ux.sheetState({ sheet_no: 1, operations: [], paths: [] });
assert.equal(unset.postProcessor, undefined);
const generateArgs = ux.sheetGenerateArgs(
    { doc: { name: "ORD-1" } },
    { cutting_plan: "PLAN", plan_revision: 3 },
    { sheet_no: 1 },
    restored
);
assert.equal(generateArgs.post_processor, undefined);
assert.equal(generateArgs.base_revision, 12);

const mutationState = {};
const firstMutation = ux.beginSheetMutation(mutationState);
assert.equal(firstMutation, 1);
assert.equal(ux.beginSheetMutation(mutationState), 0);
assert.equal(ux.sheetMutationIsCurrent(mutationState, firstMutation), true);
assert.equal(ux.finishSheetMutation(mutationState, firstMutation + 1), false);
assert.equal(mutationState.sheetMutationInFlight, true);
assert.equal(ux.finishSheetMutation(mutationState, firstMutation), true);
const secondMutation = ux.beginSheetMutation(mutationState);
assert.equal(secondMutation, 2);
assert.equal(ux.sheetMutationIsCurrent(mutationState, firstMutation), false);
windowObject.AlmdinaArtcamMachining = {
    markup() { return '<form data-artcam-editor><input data-field="name"><select data-field="source"></select><select data-field="profile_id"></select></form>'; },
};
const viewOnlyMarkup = ux.dialogMarkup(
    { can_prepare: false, cutting_plan: "PLAN", plan_revision: 3, cnc_machines: [] },
    { sheet_no: 1, status: "Settings Saved", machining: { associations: [], profiles: [] } },
    {},
    { exportBar: true }
);
assert.match(viewOnlyMarkup, /data-sheet-section="associations"[^]*?<fieldset class="dco-artcam-readonly" disabled><form data-artcam-editor>[^]*?<\/form><\/fieldset>/);
const pageMarkup = ux.dialogMarkup(
    {
        can_prepare: true,
        cutting_plan: "PLAN",
        plan_revision: 3,
        cnc_machines: [],
        post_processors: [{ id: "ima_wh_ncstudio", label: "IMA-WH (*.nc)" }],
    },
    { sheet_no: 1, status: "Settings Saved", machining: { associations: [], profiles: [] } },
    unset,
    { exportBar: true }
);
assert.ok(!pageMarkup.includes('class="dco-artcam-readonly"'));
const settingsMarkup = pageMarkup.slice(pageMarkup.indexOf("dco-operational-sheet__settings"));
assert.ok(settingsMarkup.includes("dco-cnc-sheet-page__identity"));
assert.ok(settingsMarkup.indexOf("dco-cnc-sheet-page__identity") < settingsMarkup.indexOf('data-sheet-section="placement"'));
assert.ok(settingsMarkup.indexOf('data-sheet-section="order"') < settingsMarkup.indexOf("data-cnc-export-bar"));
assert.equal(settingsMarkup.includes("dco-operational-sheet__preview"), false);
assert.equal(pageMarkup.includes("data-cnc-post-processor"), false);
assert.ok(pageMarkup.includes("data-cnc-save-sheet"));
assert.ok(pageMarkup.includes("data-cnc-generate-nc"));
assert.ok(pageMarkup.includes("Download cutting file"));
assert.ok(pageMarkup.indexOf("data-cnc-save-sheet") < pageMarkup.indexOf("data-cnc-generate-nc"));
assert.ok(pageMarkup.includes("dco-cnc-preview-toolbar"));
assert.equal(pageMarkup.includes("data-cnc-preview-zoom"), false);
assert.ok(pageMarkup.indexOf("dco-cnc-preview-toolbar") < pageMarkup.indexOf("data-sheet-preview"));
assert.equal(pageMarkup.includes("dco-operational-sheet__selection"), false);
assert.equal(pageMarkup.includes("data-sheet-nc-status"), false);
const dialogMarkup = ux.dialogMarkup(
    { can_prepare: true, cutting_plan: "PLAN", plan_revision: 3, cnc_machines: [] },
    { sheet_no: 1, status: "Settings Saved", machining: { associations: [], profiles: [] } },
    unset
);
assert.equal(dialogMarkup.includes("data-cnc-export-bar"), false);
assert.equal(dialogMarkup.includes("dco-cnc-sheet-page__identity"), false);
assert.ok(dialogMarkup.includes("dco-operational-sheet__selection"));
assert.ok(dialogMarkup.includes("data-sheet-nc-status"));
assert.ok(pageMarkup.includes("Machine placement"));
assert.ok(pageMarkup.includes("Vector Associations"));
assert.ok(pageMarkup.includes("Associations appear here after they are saved."));
assert.ok(!pageMarkup.includes("dco-sheet-acc"));
assert.ok(pageMarkup.indexOf('data-sheet-section="placement"') < pageMarkup.indexOf('data-sheet-section="perimeter"'));
assert.ok(pageMarkup.indexOf('data-sheet-section="perimeter"') < pageMarkup.indexOf('data-sheet-section="associations"'));
assert.ok(pageMarkup.indexOf('data-sheet-section="associations"') < pageMarkup.indexOf('data-sheet-section="order"'));
assert.ok(panel.includes("data-cnc-page-actions"));
assert.ok(panel.includes("placePageActions("));
assert.ok(css.includes("grid-template-columns: minmax(0, 65fr) minmax(16rem, 35fr)"));
assert.ok(panel.includes("data-sheet-grid-pattern"));
assert.ok(panel.includes("8 / scale"));
assert.ok(panel.includes('patternTransform="rotate(45)"'));
assert.ok(panel.includes('fill="#ffffff"'));
assert.ok(panel.includes('stroke="rgba(71,85,105,.18)"'));
assert.ok(panel.includes('class="dco-cnc-preview-toolbar" dir="ltr"'));
assert.ok(css.includes("dco-cnc-cut-preview__board-grid"));
assert.ok(css.includes("dco-cnc-cut-preview__grid-line"));
assert.ok(css.includes("rgba(71, 85, 105, 0.18)"));
assert.ok(css.includes("background-size: 24px 24px"));
assert.ok(css.includes("rgba(15, 23, 42, 0.03)"));
assert.ok(css.includes(".dco-cnc-sheet-page .dco-cnc-preview-toolbar"));
assert.ok(css.includes("justify-content: space-between"));
assert.ok(css.includes(".dco-cnc-sheet-page [data-cnc-save-sheet]"));
assert.ok(css.includes(".dco-cnc-sheet-page .btn.alm-btn-primary[data-cnc-save-sheet]"));
assert.ok(css.includes("background-color: var(--alm-accent);"));
assert.ok(panel.includes("alm-btn-primary"));
assert.ok(css.includes("direction: ltr;"));
assert.ok(css.includes("inset-block-start: var(--navbar-height, 48px)"));
assert.ok(css.includes("100dvh - var(--navbar-height, 48px) - 0.85rem"));
assert.ok(css.includes(".dco-cnc-sheet-page .dco-cnc-cut-preview__viewport > .dco-cnc-cut-preview__zoom"));
assert.ok(css.includes(".dco-cnc-sheet-page .dco-cnc-cut-preview__piece"));
assert.ok(translations.includes("Download cutting file,تحميل ملف القص"));
const ncErrorHandler = panel.split("method: `${METHOD}.generate_cnc_sheet_nc`", 2)[1]
    .split("silent: true", 1)[0];
assert.ok(ncErrorHandler.includes("frontend.normalizeError(err, { fallback }).message"));
assert.ok(!ncErrorHandler.includes("err.exc"));
assert.ok(!ncErrorHandler.includes("err._server_messages"));
assert.ok(panel.includes("relocatePageZoomControls"));
assert.ok(translations.includes("Machine placement,تموضع اللوح على الماكينة"));
assert.ok(translations.includes("Vector Associations,ربط المتجهات"));
assert.ok(translations.includes("Associations appear here after they are saved.,يظهر الربط هنا بعد حفظه."));
assert.ok(translations.includes("{0} Vectors Selected,{0} متجهات محددة"));

const shaped = ux.cutPathPreviewMarkup({
    sheet_width_mm: 1000,
    sheet_length_mm: 1220,
    geometry_ready: true,
    ready: true,
    operations: [{
        operation_key: "cut_path",
        toolpaths: [{
            path_key: "cut_path:a",
            operation_key: "cut_path",
            closed: false,
            ready: true,
            points: [[10, 10], [40, 10]],
            motions: motionChain([[10, 10], [40, 10]], 6, false),
        }],
    }],
}, {
    layout: "page",
    sheetNo: 1,
    boardLayout: {
        sheets: [{
            sheet_no: 1,
            pieces: [
                {
                    piece_instance_id: "leaf-l",
                    geometry: {
                        unit: "mm",
                        coordinate_space: "usable_sheet",
                        outer: [[0, 0], [80, 0], [80, 30], [40, 30], [40, 70], [0, 70]],
                        holes: [],
                    },
                },
                {
                    piece_instance_id: "leaf-hole",
                    geometry: {
                        unit: "mm",
                        coordinate_space: "usable_sheet",
                        outer: [[200, 200], [400, 200], [400, 400], [200, 400]],
                        holes: [[[250, 250], [300, 250], [300, 300], [250, 300]]],
                    },
                },
            ],
        }],
    },
});
assert.ok(shaped.includes('fill="none" fill-rule="evenodd"'));
assert.ok(shaped.includes('data-piece-id="leaf-l"'));
assert.ok(shaped.includes("40 1190"), "an inner corner of a non-rectangular leaf stays on the outline");
assert.ok(shaped.includes('data-piece-id="leaf-hole"'));
assert.ok(shaped.includes("250 970"), "an opening inside a leaf is drawn from its own ring");
assert.ok(shaped.includes("10,10"));
assert.ok(shaped.includes("40,10"));
assert.equal((shaped.match(/dco-cnc-cut-preview__svg/g) || []).length, 1);

const incompleteProgram = {
    sheet_width_mm: 100,
    sheet_length_mm: 200,
    geometry_ready: false,
    ready: false,
    operations: [{
        operation_key: "cut_path",
        toolpaths: [{
            path_key: "cut_path:bad",
            operation_key: "cut_path",
            closed: false,
            ready: false,
            points: [[0, 0], [10, 0]],
            motions: [],
        }],
    }],
};
const incompletePage = ux.cutPathPreviewMarkup(incompleteProgram, { layout: "page" });
const incompleteDialog = ux.cutPathPreviewMarkup(incompleteProgram);
assert.equal(incompletePage.includes("Cutting path preview is incomplete."), false);
assert.ok(incompleteDialog.includes("Cutting path preview is incomplete."));

console.log("dco_operational_files_sheet_page.test.js passed");
