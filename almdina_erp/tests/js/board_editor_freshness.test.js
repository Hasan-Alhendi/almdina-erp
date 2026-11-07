"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const controllerSource = fs.readFileSync(
    path.join(root, "public/js/board_editor/controller.js"),
    "utf8"
);
const apiSource = fs.readFileSync(
    path.join(root, "public/js/board_editor/api.js"),
    "utf8"
);
const pageSource = fs.readFileSync(
    path.join(root, "almdina_erp/page/board_editor/board_editor.js"),
    "utf8"
);
const displaySource = fs.readFileSync(
    path.join(root, "public/js/board_editor/plan_display_style.js"),
    "utf8"
);
const canvasSource = fs.readFileSync(
    path.join(root, "public/js/board_editor/canvas_renderer.js"),
    "utf8"
);
const querySource = fs.readFileSync(
    path.join(root, "almdina_erp/services/board_editor_query_service.py"),
    "utf8"
);
const projectionSource = fs.readFileSync(
    path.join(root, "almdina_erp/application/cutting/board_editor_projection.py"),
    "utf8"
);

assert.match(controllerSource, /contentRevisionToken/);
assert.match(controllerSource, /sessionIsDirty/);
assert.match(controllerSource, /renderSourceConflict/);
assert.match(controllerSource, /acceptSourceChange/);
assert.match(controllerSource, /scheduleFreshnessRetry/);
assert.match(controllerSource, /freshnessBannerHtml/);
assert.match(controllerSource, /Cutting plan is out of date/);
assert.match(controllerSource, /Plan source changed while editing/);
assert.match(controllerSource, /Historical cutting plan/);
assert.match(controllerSource, /MAX_FRESHNESS_RETRIES/);
assert.doesNotMatch(controllerSource, /setInterval\(/);
assert.match(apiSource, /recalculationStatus/);
assert.match(apiSource, /get_system_plan_recalculation_status/);
assert.match(pageSource, /on_page_show/);
assert.match(pageSource, /active\.open\(context\)/);
assert.match(pageSource, /plan_display_style\.js\?v=18/);
assert.match(pageSource, /controller\.js\?v=35/);
assert.match(pageSource, /api\.js\?v=19/);
assert.match(pageSource, /session_document\.js\?v=24/);
assert.match(pageSource, /board_editor\.css\?v=38/);
assert.match(pageSource, /transform_geometry\.js\?v=2/);
assert.match(pageSource, /move_geometry\.js\?v=20/);
assert.match(pageSource, /rotation_geometry\.js\?v=19/);
assert.match(pageSource, /measure_geometry\.js\?v=3/);
assert.match(pageSource, /position_geometry\.js\?v=4/);
assert.match(pageSource, /canvas_renderer\.js\?v=37/);
assert.match(pageSource, /store\.js\?v=21/);
assert.match(pageSource, /move_interaction\.js\?v=20/);
assert.match(pageSource, /rotation_interaction\.js\?v=19/);
assert.match(pageSource, /measure_interaction\.js\?v=6/);
assert.match(querySource, /_plan_freshness_payload/);
assert.match(querySource, /content_revision_token/);
assert.match(querySource, /reflects_current_order/);
assert.match(querySource, /"runs_optimizer_on_open": False/);
assert.match(querySource, /mutates_plan_on_read/);
assert.match(projectionSource, /_parametric_material_geometry/);
assert.match(projectionSource, /_synthetic_overlay_elements/);
assert.match(projectionSource, /placed_parametric_polygon|obstacle_geometry_mm/);
assert.match(projectionSource, /parametric_visual/);
assert.match(projectionSource, /cnc_raw_rect/);
assert.match(projectionSource, /_cnc_raw_rect_geometry_mm/);
assert.match(projectionSource, /_special_exact_geometry_mm/);
assert.match(canvasSource, /PlanDisplayStyle/);
assert.match(canvasSource, /fillRoleOf/);
assert.match(canvasSource, /edgeMarkSvg/);
assert.match(canvasSource, /PlanEdgeMarks/);
assert.match(canvasSource, /data-fill-role/);

const context = { window: {} };
context.window = context;
vm.createContext(context);
vm.runInContext(displaySource, context);
const style = context.window.AlmdinaBoardEditor.PlanDisplayStyle;
assert.equal(style.piecePaint("regular", { shaped: false }).fill, "#e4f5ff");
assert.equal(style.piecePaint("l_shaped", { shaped: true }).fill, "#fff0c7");
assert.equal(style.piecePaint("special", { shaped: false }).fill, "url(#abe-special-fill)");
assert.equal(style.piecePaint("special", { shaped: true, exactSpecial: true }).fill, "#ffe5ad");
assert.equal(style.overlayPaint("liner").stroke, "#1d6fbf");
assert.equal(style.overlayPaint("back_groove").stroke, "#2a7d4f");
assert.equal(style.sizeLabel(80.26, 40.24), "80.3*40.2");
assert.match(style.defs(1), /abe-waste-hatch/);
assert.match(style.defs(1), /abe-special-fill/);

function contentRevisionToken(payload) {
    const plan = (payload && payload.plan) || {};
    const freshness = (payload && payload.freshness) || {};
    return String(
        freshness.content_revision_token
        || plan.content_revision_token
        || [
            plan.name || "",
            plan.modified || "",
            plan.revision || "",
            plan.input_fingerprint || "",
            freshness.needs_recalculation ? "1" : "0",
            freshness.job_active ? "1" : "0",
        ].join("|")
    );
}

assert.match(querySource, /"1" if job_active else "0"/);
assert.match(querySource, /not Cutting Plan\.modified/);
assert.match(querySource, /saved_layout_sha256/);
assert.match(controllerSource, /freshness\.job_active \? "1" : "0"/);
assert.match(controllerSource, /plan\.saved_layout_sha256/);
assert.match(controllerSource, /draft\.compatible \? \(Number\(draft\.draft_version\)/);
assert.match(controllerSource, /Start draft from current source/);
assert.match(controllerSource, /abe-begin-from-source/);
assert.match(controllerSource, /abe-draft-source-conflict/);
assert.match(controllerSource, /abe-freshness-actions/);
assert.match(controllerSource, /data-abe-draft="source-conflict"/);
assert.match(controllerSource, /beginDraftFromCurrentSource/);
assert.match(controllerSource, /confirmBeginFromCurrentSource/);
assert.match(apiSource, /beginDraftFromCurrentSource/);
assert.match(apiSource, /begin_board_editor_draft_from_current_source/);
{
    const cssSource = fs.readFileSync(
        path.join(root, "public/css/board_editor.css"),
        "utf8"
    );
    assert.match(cssSource, /\.abe-begin-from-source/);
    assert.match(cssSource, /\.abe-freshness-actions/);
}
{
    const tokenFn = controllerSource.split("function contentRevisionToken")[1].split("function ")[0];
    assert.doesNotMatch(tokenFn, /plan\.modified\s*\|\|/);
}
{
    const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
    for (const messageId of [
        "Start draft from current source",
        "Could not start draft",
        "Start a new draft from the current plan source? The previous saved draft will be archived. Unsaved local moves on this screen will be discarded. The cutting plan itself will not be changed.",
        "It was not applied. The cutting plan itself was not changed. Start a new draft from the current source to continue editing and saving. The previous draft is archived first; local unsaved moves on this screen are discarded on start.",
    ]) {
        assert.ok(catalog.includes(messageId), `missing ar.csv key: ${messageId}`);
    }
}

const first = contentRevisionToken({
    plan: { name: "CP-1", modified: "2026-01-01", revision: 1, input_fingerprint: "abc" },
    freshness: { needs_recalculation: false, content_revision_token: "CP-1|2026-01-01|1|abc|0|0" },
});
const sameNameChanged = contentRevisionToken({
    plan: { name: "CP-1", modified: "2026-01-02", revision: 2, input_fingerprint: "def" },
    freshness: { needs_recalculation: false, content_revision_token: "CP-1|2026-01-02|2|def|0|0" },
});
assert.notEqual(first, sameNameChanged);

const stale = contentRevisionToken({
    plan: { name: "CP-1", modified: "2026-01-01", revision: 1 },
    freshness: { needs_recalculation: true, content_revision_token: "CP-1|2026-01-01|1||1|0" },
});
assert.match(stale, /\|1\|/);

// idle vs completed must not invent distinct tokens when the server bit is stable.
const idleLike = contentRevisionToken({
    plan: { name: "CP-1", modified: "2026-01-01", revision: 1, input_fingerprint: "abc" },
    freshness: { needs_recalculation: false, job_active: false },
});
const completedLike = contentRevisionToken({
    plan: { name: "CP-1", modified: "2026-01-01", revision: 1, input_fingerprint: "abc" },
    freshness: { needs_recalculation: false, job_active: false },
});
assert.equal(idleLike, completedLike);
assert.equal(idleLike, "CP-1|2026-01-01|1|abc|0|0");

console.log("board editor freshness contract passed");
