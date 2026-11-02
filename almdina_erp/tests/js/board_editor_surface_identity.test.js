"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "../../public/js");
const CONTEXT_PATH = path.join(
    ROOT,
    "door_cutting_order/cutting_plan/door_cutting_order_plan_context_actions_ux.js",
);
const TABS_PATH = path.join(
    ROOT,
    "door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js",
);
const STATE_PATH = path.join(
    ROOT,
    "door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js",
);

function loadContext(workspacePayload, permissions = {
    approve_dxf: true,
    view_cutting_plan: true,
    view_system_cutting_plan: true,
    view_approved_cutting_plan: true,
}) {
    const document = {
        documentElement: { getAttribute: () => "rtl" },
        getElementById: () => null,
        createElement: () => ({
            id: "",
            textContent: "",
            setAttribute() {},
        }),
        head: { appendChild() {} },
    };
    const host = {
        length: 1,
        jquery: true,
        empty() { this.htmlValue = ""; return this; },
        html(value) {
            if (value === undefined) return this.htmlValue || "";
            this.htmlValue = String(value);
            return this;
        },
        find() {
            return {
                off() { return this; },
                on() { return this; },
            };
        },
    };
    const routes = [];
    const windowObj = {
        addEventListener() {},
        AlmdinaLocale: {
            translate: (message) => message,
            direction: () => "rtl",
        },
        AlmdinaUi: {
            button: ({ label, disabled, className }) => (
                `<button class="${className || ""}"${disabled ? " disabled" : ""}>${label}</button>`
            ),
        },
        AlmdinaPermissions: {
            canDocument: (_frm, capability) => Boolean(permissions[capability]),
            can: (capability) => Boolean(permissions[capability]),
        },
        AlmdinaDocumentContext: {
            canMutateCurrentStage: () => true,
            stageMutationBlockReason: () => "",
        },
        AlmdinaPlanWorkspaceState: {
            snapshot: () => ({
                status: "ready",
                identity: "Door Cutting Order::26-00021",
                data: workspacePayload,
            }),
        },
        AlmdinaPlanControlsUX: {
            runApproval: async () => true,
        },
        document,
        frappe: null,
        $: null,
    };
    const context = {
        window: windowObj,
        document,
        frappe: {
            utils: { escape_html: (value) => String(value ?? "") },
            msgprint() {},
            show_alert() {},
            confirm(_message, yes) { yes(); },
            set_route(...args) { routes.push(args); },
            call: async () => ({ message: {} }),
            almdina: {},
            provide() {},
            ui: { form: { on() {} } },
        },
        $: (value) => (value && value.jquery ? value : host),
        console,
    };
    windowObj.frappe = context.frappe;
    windowObj.$ = context.$;
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(CONTEXT_PATH, "utf8"), context);
    return { owner: context.window.AlmdinaPlanContextActionsUX, host, context, routes };
}

const planA = {
    name: "CP-A",
    source_type: "Board Editor",
    status: "Draft",
    revision: 11,
    modified: "2026-01-11",
    content_identity: "CP-A|11|2026-01-11|fpA|d1",
    can_approve: true,
    manufacturing_blocked: false,
    validation: { status: "Valid", needs_recalculation: false },
    totals: { required_boards: 2 },
    snapshot_json: JSON.stringify({ sheets: [{ sheet_no: 1, pieces: [{ id: 1, x: 10 }] }] }),
};

const afterApproveA = {
    order_name: "26-00021",
    approved_plan: "CP-A",
    capabilities: {
        approve: true,
        print: true,
        export_dxf: true,
        view_system: true,
        view_approved: true,
        upload_dxf: true,
        replace_dxf: true,
    },
    plans: {
        system_draft: null,
        uploaded_draft: null,
        board_editor_draft: {
            ...planA,
            status: "Approved",
            display_context: "current_approved",
            can_approve: false,
            is_current_approved_tip: true,
        },
        approved: {
            ...planA,
            status: "Approved",
            display_context: "current_approved",
        },
    },
};

{
    const { owner, host, routes } = loadContext(afterApproveA);
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "BoardEditor",
        fields_dict: {},
    };
    const row = owner.rowForTab(frm, "BoardEditor");
    assert.equal(row.name, "CP-A", "Edited keeps approved tip A");
    assert.equal(row.status, "Approved");
    assert.equal(owner.canApprove(frm, "BoardEditor", row), false);
    assert.equal(owner.canOpenBoardEditor(frm, row), true);
    owner.render(frm, host);
    assert.doesNotMatch(host.html(), /Approve the edited plan/);
    assert.match(host.html(), /Open board editor/);
    owner.runOpenBoardEditor(frm);
    assert.deepEqual(routes[0], ["board-editor", "26-00021", "CP-A"]);
}

{
    const withB = JSON.parse(JSON.stringify(afterApproveA));
    withB.plans.board_editor_draft = {
        name: "CP-B",
        source_type: "Board Editor",
        status: "Draft",
        revision: 12,
        modified: "2026-01-12",
        content_identity: "CP-B|12|2026-01-12|fpB|d2",
        can_approve: true,
        manufacturing_blocked: false,
        validation: { status: "Valid", needs_recalculation: false },
        totals: { required_boards: 2 },
        snapshot_json: JSON.stringify({ sheets: [{ sheet_no: 1, pieces: [{ id: 1, x: 99 }] }] }),
        editor_draft: { present: false, unapplied: false },
    };
    assert.equal(withB.approved_plan, "CP-A");
    assert.equal(withB.plans.approved.name, "CP-A");
    const { owner, routes } = loadContext(withB);
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "BoardEditor",
        fields_dict: {},
    };
    assert.equal(owner.rowForTab(frm, "BoardEditor").name, "CP-B");
    assert.equal(owner.rowForTab(frm, "Approved").name, "CP-A");
    assert.equal(owner.canApprove(frm, "BoardEditor", owner.rowForTab(frm)), true);
    owner.runOpenBoardEditor(frm);
    assert.deepEqual(routes[0], ["board-editor", "26-00021", "CP-B"]);
}

{
    const denied = loadContext(afterApproveA, {
        approve_dxf: true,
        view_cutting_plan: false,
        view_system_cutting_plan: false,
        view_approved_cutting_plan: false,
    });
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "BoardEditor",
        fields_dict: {},
    };
    assert.equal(
        denied.owner.canOpenBoardEditor(frm, denied.owner.rowForTab(frm)),
        false,
        "unauthorized open remains closed",
    );
}

{
    const tabsSource = fs.readFileSync(TABS_PATH, "utf8");
    assert.match(tabsSource, /planPaintIdentity/);
    assert.match(tabsSource, /data-almdina-plan-paint-key/);
    assert.match(tabsSource, /Unapplied board-editor draft/);
    const stateSource = fs.readFileSync(STATE_PATH, "utf8");
    assert.match(stateSource, /board_editor_draft/);
    assert.match(stateSource, /requestId/);
    assert.match(stateSource, /owns\(frm, requestToken\)/);
}

console.log("board_editor_surface_identity.test.js: ok");
