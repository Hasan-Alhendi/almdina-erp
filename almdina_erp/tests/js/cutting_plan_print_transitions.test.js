"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");
const geometry = () => ({full_board_width_cm: 122, full_board_length_cm: 244,
    usable_board_width_cm: 122, usable_board_length_cm: 244,
    sheets: [{sheet_no: 1, pieces: [{id: 1, label: "OWNED-CUT", x: 0, y: 0,
        w: 42, h: 81, original_w: 42, original_h: 81, piece_type: "Regular"}]}]});
const row = (name, plan = geometry(), revision = 1) => ({name, revision,
    board: {description: "White"}, snapshot_json: JSON.stringify(plan)});

function element(html) {
    return {innerHTML: html, dataset: {}, style: {setProperty() {}},
        get outerHTML() { return this.innerHTML; },
        querySelector(selector) { return this.innerHTML.includes(String(selector).replace(".", ""))
            ? element(this.innerHTML) : null; },
        querySelectorAll(selector) { const found = this.querySelector(selector); return found ? [found] : []; },
        cloneNode() { return element(this.innerHTML); }};
}

function harness({ sourceFirst = false } = {}) {
    const writes = [], messages = [];
    const reads = {snapshot: 0, displayedRow: 0};
    const frm = {doctype: "Door Cutting Order", doc: {name: "A", doctype: "Door Cutting Order",
        board_description: "White", pieces: []}, fields_dict: {cutting_plan_html: {
            $wrapper: {get() { return {querySelector() { return window.visibleRoot ? {} : null; }}; }},
        }}};
    let generation = 1, allowed = true, pendingIdentity = null;
    const state = {status: "ready", identity: "Door Cutting Order::A",
        data: {order_name: "A", capabilities: {print: true}, plans: {
            system_draft: row("SYSTEM-A"), uploaded_draft: row("CUSTOM-A"),
            approved: row("APPROVED-A")}, approved_plan: "APPROVED-A"}};
    const window = {
        cur_frm: frm,
        addEventListener() {},
        AlmdinaOrderDocumentPrintTheme: {headerHtml() { return ""; }, headerCss() { return ""; }},
        open() { return {document: {open() {}, write(html) { writes.push(String(html)); }, close() {}},
            close() {}}; },
        AlmdinaDocumentContext: {
            formIdentity() { return `Door Cutting Order::${frm.doc.name}`; },
            capture() { return {identity: frm.doc.name, generation}; },
            isCurrent(form, token) { return window.cur_frm === form && token.identity === frm.doc.name
                && token.generation === generation; },
        },
        AlmdinaPermissions: {canDocument(_form, capability) {
            return allowed && (capability === "print_cutting_plan"
                || capability.startsWith("view_") || capability === "view_cutting_plan");
        }},
        AlmdinaFactoryPrintIdentity: {get() { return pendingIdentity || Promise.resolve({}); }},
        AlmdinaPlanPreviewSession: {displayedPreviewRow() { return window.previewRow || null; }},
        AlmdinaPlanWorkspaceState: {
            snapshot() { reads.snapshot += 1; return state; },
            planForTab(_form, tab) { return state.data?.plans?.[{
                System: "system_draft", Custom: "uploaded_draft", Approved: "approved"}[tab]] || null; },
            displayedPlanForTab(form, tab) { reads.displayedRow += 1;
                return tab === "System" && window.previewRow
                ? window.previewRow : this.planForTab(form, tab); },
            load() { return Promise.resolve(state); },
        },
    };
    const document = {documentElement: {getAttribute(key) { return key === "dir" ? "rtl" : "ar"; }},
        getElementById() { return null; }, createElement() { return element(""); },
        head: {appendChild() {}}};
    const frappe = {boot: {lang: "ar"}, msgprint(message) { messages.push(message); },
        utils: {escape_html: String}};
    const context = vm.createContext({window, document, frappe, console, JSON, Number, String,
        Math, Object, Array, Set, Map, WeakMap, Promise, Boolean, Error, __: value => value});
    const files = ["drawing/door_cutting_order_special_shape_geometry.js",
        "drawing/door_cutting_order_shape_output_contract.js",
        "drawing/door_cutting_order_clipped_corner_ux.js",
        "cutting_plan/door_cutting_order_piece_geometry.js",
        "cutting_plan/door_cutting_order_cutting_plan_renderer.js",
        "cutting_plan/door_cutting_order_plan_source_presentation.js",
        "cutting_plan/door_cutting_order_plan_tabs_ux.js",
        "cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js"];
    if (sourceFirst) {
        const presenter = files.splice(files.indexOf(
            "cutting_plan/door_cutting_order_plan_source_presentation.js"), 1)[0];
        files.splice(files.indexOf(
            "cutting_plan/door_cutting_order_cutting_plan_renderer.js"), 0, presenter);
    }
    for (const file of files) {
        vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), context, {filename: file});
    }
    return {window, frm, state, writes, messages, reads,
        generation() { generation += 1; },
        permission(value) { allowed = value; },
        deferIdentity() { let release; pendingIdentity = new Promise(resolve => { release = resolve; });
            return () => { pendingIdentity = null; release({}); }; },
        async print() { return window.AlmdinaPlanTabsUX.printActivePlan(frm); },
    };
}

test("ready, loading, stale and forced reload gate the actual handler", async () => {
    const h = harness();
    h.frm.__almdina_active_plan_tab = "System";
    assert.equal(await h.print(), true);
    assert.match(h.writes.at(-1), /SYSTEM-A/);
    assert.ok(h.reads.displayedRow >= 3 && h.reads.snapshot >= 3,
        "one command consults the displayed row and workspace more than once");
    h.state.status = "loading";
    assert.equal(await h.print(), false);
    h.state.status = "ready";
    assert.equal(await h.print(), true);
    h.state.status = "loading"; // forced reload while retaining the painted row
    assert.equal(await h.print(), false);
    h.state.status = "ready";
    assert.equal(await h.print(), true);
    h.state.status = "stale";
    assert.equal(await h.print(), false);
    assert.equal(h.writes.length, 6);
});

test("a visible owned plan must print through the real Form identity", async () => {
    const h = harness();
    h.frm.__almdina_active_plan_tab = "System";
    assert.equal(await h.print(), true, "hidden initial plan prints from its owned row");
    h.window.visibleRoot = true;
    assert.equal(await h.print(), true,
        "a mounted plan must not turn the real Form into a synthetic, non-current Form");
    assert.match(h.writes.at(-1), /SYSTEM-A/);
    const aPlan = JSON.parse(h.state.data.plans.system_draft.snapshot_json);
    const before = h.writes.length;
    assert.equal(await h.window.AlmdinaCuttingPlanRender.print(h.frm, aPlan,
        {tab: "System", row: {...h.state.data.plans.system_draft, revision: 99}}), false,
    "a visible plan cannot bypass the selected row revision hint");
    assert.equal(h.writes.length, before);
    h.frm.doc.name = "B";
    h.generation();
    h.state.identity = "Door Cutting Order::B";
    h.state.data.order_name = "B";
    h.state.data.plans.system_draft = row("SYSTEM-B", {
        ...geometry(), sheets: [{sheet_no: 1, pieces: [{...geometry().sheets[0].pieces[0], w: 57}]}],
    });
    assert.equal(await h.print(), true);
    assert.match(h.writes.at(-1), /SYSTEM-B/);
    assert.equal(await h.window.AlmdinaCuttingPlanRender.print(h.frm, aPlan), false,
        "a visible B plan cannot authorize A geometry");
});

test("both lazy-asset evaluation orders install one safe print contract", async () => {
    const first = harness({sourceFirst: true});
    assert.equal(Boolean(first.window.AlmdinaCuttingPlanRender.__almadina179SourcePresentation),
        false, "the source module can evaluate before its renderer");
    assert.equal(first.window.AlmdinaPlanSourcePresentation.install(), true);
    assert.equal(first.window.AlmdinaPlanSourcePresentation.install(), false);
    assert.equal(Boolean(first.window.AlmdinaCuttingPlanRender.__almadina179SourcePresentation), true);
    first.window.visibleRoot = true;
    first.frm.__almdina_active_plan_tab = "System";
    assert.equal(await first.print(), true);

    const second = harness();
    assert.equal(Boolean(second.window.AlmdinaCuttingPlanRender.__almadina179SourcePresentation), true);
    second.window.visibleRoot = true;
    second.frm.__almdina_active_plan_tab = "System";
    assert.equal(await second.print(), true);
});

test("tabs, preview and independent representation keep or reject the selected source", async () => {
    const h = harness();
    for (const [tab, name] of [["System", "SYSTEM-A"], ["Custom", "CUSTOM-A"],
        ["Approved", "APPROVED-A"]]) {
        h.frm.__almdina_active_plan_tab = tab;
        assert.equal(await h.print(), true);
        assert.match(h.writes.at(-1), new RegExp(name));
    }
    h.frm.__almdina_active_plan_tab = "System";
    h.window.previewRow = row("preview:owned");
    assert.equal(await h.print(), true);
    assert.match(h.writes.at(-1), /preview:owned/);
    h.window.previewRow = null;
    const canonical = h.state.data.plans.system_draft;
    const samePlan = JSON.parse(canonical.snapshot_json);
    Object.defineProperty(samePlan, "__offcut_assignments", {value: [], enumerable: false});
    assert.equal(await h.window.AlmdinaCuttingPlanRender.print(h.frm, samePlan,
        {tab: "System", row: {...canonical}}), true);
    const reordered = {sheets: samePlan.sheets, full_board_width_cm: 122,
        full_board_length_cm: 244, usable_board_width_cm: 122, usable_board_length_cm: 244};
    const before = h.writes.length;
    assert.equal(await h.window.AlmdinaCuttingPlanRender.print(h.frm, reordered,
        {tab: "System", row: canonical}), false,
    "JSON key order changes the byte comparison even when the controlled geometry is equal");
    assert.equal(h.writes.length, before);
});

test("final OFFCUT HTML retains assigned business context from the verified row", async () => {
    const h = harness();
    h.frm.__almdina_active_plan_tab = "System";
    const plan = geometry();
    plan.sheets.push({sheet_no: 2, resource_kind: "OFFCUT", pieces: [{
        ...plan.sheets[0].pieces[0], piece_instance_id: "OFFCUT-PIECE-1",
    }]});
    h.state.data.plans.system_draft = {...row("SYSTEM-OFFCUT", plan), offcut: {
        assignments: [{piece_instance_id: "OFFCUT-PIECE-1",
            business_state: "FACTORY_FACTORY", business_state_label: "FACTORY-OWNED"}],
    }};
    assert.equal(await h.print(), true);
    assert.match(h.writes.at(-1), /data-resource-kind="OFFCUT"/);
    assert.match(h.writes.at(-1), /dco-offcut-business-context/);
    assert.match(h.writes.at(-1), /FACTORY-OWNED/);
});

test("unowned OFFCUT metadata cannot enter another order's final HTML", async () => {
    const h = harness();
    h.frm.doc.name = "B";
    h.generation();
    h.state.identity = "Door Cutting Order::B";
    h.state.data.order_name = "B";
    h.frm.__almdina_active_plan_tab = "System";
    const plan = geometry();
    plan.sheets.push({sheet_no: 2, resource_kind: "OFFCUT", pieces: [{
        ...plan.sheets[0].pieces[0], piece_instance_id: "OFFCUT-PIECE-1",
    }]});
    const owned = {piece_instance_id: "OFFCUT-PIECE-1",
        business_state: "FACTORY_FACTORY", business_state_label: "B-OWNED-LABEL"};
    h.state.data.plans.system_draft = {...row("SYSTEM-B", plan), offcut: {assignments: [owned]}};
    const untrustedOverride = JSON.parse(JSON.stringify(plan));
    Object.defineProperty(untrustedOverride, "__offcut_assignments", {value: [{...owned,
        business_state_label: "A-PRIVATE-LABEL"}], enumerable: false});
    assert.equal(await h.window.AlmdinaCuttingPlanRender.print(h.frm, untrustedOverride,
        {tab: "System", row: h.state.data.plans.system_draft}), true);
    assert.match(h.writes.at(-1), /B-OWNED-LABEL/);
    assert.doesNotMatch(h.writes.at(-1), /A-PRIVATE-LABEL/);

    const beforePending = h.writes.length;
    const release = h.deferIdentity();
    const pending = h.window.AlmdinaCuttingPlanRender.print(h.frm, untrustedOverride,
        {tab: "System", row: h.state.data.plans.system_draft});
    h.state.data.plans.system_draft = {...h.state.data.plans.system_draft, offcut: {
        assignments: [{...owned, business_state_label: "B-UPDATED-LABEL"}],
    }};
    release();
    assert.equal(await pending, false, "changed owned assignment cancels the frozen print");
    assert.equal(h.writes.length, beforePending + 1, "only preparation HTML was written");
    assert.doesNotMatch(h.writes.at(-1), /B-UPDATED-LABEL/);
});

test("changes at the async boundary reject revision, preview, permission and A→B→A", async () => {
    const h = harness();
    h.frm.__almdina_active_plan_tab = "System";
    const original = h.state.data.plans.system_draft;
    let release = h.deferIdentity();
    let pending = h.print();
    h.state.data.plans.system_draft = {...original, revision: 2};
    release();
    assert.equal(await pending, false);
    h.state.data.plans.system_draft = original;

    release = h.deferIdentity(); pending = h.print();
    h.window.previewRow = row("preview:changed");
    release(); assert.equal(await pending, false);
    h.window.previewRow = null;

    release = h.deferIdentity(); pending = h.print();
    h.state.freshness = "stale";
    release(); assert.equal(await pending, false);
    h.state.freshness = "fresh";

    h.permission(false);
    assert.equal(await h.window.AlmdinaCuttingPlanRender.print(h.frm), false);
    h.permission(true);
    release = h.deferIdentity(); pending = h.print();
    h.permission(false); release(); assert.equal(await pending, false);
    h.permission(true);

    release = h.deferIdentity(); pending = h.print();
    h.frm.doc.name = "B"; h.generation();
    h.frm.doc.name = "A"; h.generation();
    release(); assert.equal(await pending, false);
    assert.equal(h.writes.length, 5, "only preparation HTML, never a final document");
});

test("a ready-but-invalidated Plan snapshot waits until it becomes fresh", async () => {
    // WorkspaceStore.invalidate() retains status=ready and sets freshness=stale.
    const h = harness();
    h.state.freshness = "stale";
    assert.equal(await h.print(), false);
    h.state.freshness = "fresh";
    assert.equal(await h.print(), true);
});
