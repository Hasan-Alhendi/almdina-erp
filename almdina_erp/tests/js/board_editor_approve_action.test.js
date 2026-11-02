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
const API_PATH = path.join(
    ROOT,
    "door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js",
);

function loadContext(workspacePayload, permissions = { approve_dxf: true }) {
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
            set_route() {},
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
    return { owner: context.window.AlmdinaPlanContextActionsUX, host, context };
}

const eligibleBoardEditor = {
    order_name: "26-00021",
    approved_plan: null,
    capabilities: {
        approve: true,
        print: true,
        export_dxf: true,
        view_system: true,
        upload_dxf: true,
        replace_dxf: true,
    },
    plans: {
        system_draft: {
            name: "CP-SYSTEM",
            source_type: "System",
            status: "Draft",
            validation: { status: "Valid", needs_recalculation: false },
            totals: { required_boards: 1 },
            snapshot_json: JSON.stringify({ sheets: [{ sheet_no: 1, pieces: [] }] }),
        },
        board_editor_draft: {
            name: "CP-2026-00014",
            source_type: "Board Editor",
            status: "Draft",
            can_approve: true,
            manufacturing_blocked: false,
            manufacturing_block_reason: null,
            validation: { status: "Valid", needs_recalculation: false },
            totals: { required_boards: 2 },
            snapshot_json: JSON.stringify({ sheets: [{ sheet_no: 1, pieces: [{ id: 1 }] }] }),
        },
        uploaded_draft: null,
        approved: null,
    },
};

{
    const { owner, host } = loadContext(eligibleBoardEditor);
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "BoardEditor",
        fields_dict: {},
    };
    assert.equal(
        owner.rowForTab(frm, "BoardEditor")?.name,
        "CP-2026-00014",
        "context actions must bind the Board Editor draft identity",
    );
    assert.equal(owner.canApprove(frm, "BoardEditor", owner.rowForTab(frm)), true);
    assert.equal(owner.render(frm, host), true);
    assert.match(host.html(), /Approve the edited plan/);
    assert.doesNotMatch(host.html(), /disabled/, "eligible edited plan shows an enabled approve action");
    assert.match(host.html(), /data-active-plan-source="BoardEditor"/);
}

{
    const blocked = JSON.parse(JSON.stringify(eligibleBoardEditor));
    blocked.plans.board_editor_draft.can_approve = false;
    blocked.plans.board_editor_draft.manufacturing_blocked = true;
    blocked.plans.board_editor_draft.manufacturing_block_reason = "board_editor_plan_not_ready";
    const { owner, host } = loadContext(blocked);
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "BoardEditor",
        fields_dict: {},
    };
    assert.equal(owner.canApprove(frm, "BoardEditor", owner.rowForTab(frm)), false);
    owner.render(frm, host);
    assert.match(
        host.html(),
        /This edited plan is not ready for approval or DXF export yet/,
        "authorized users see a concrete denial reason",
    );
    assert.match(host.html(), /disabled/);
}

{
    const approvedPayload = JSON.parse(JSON.stringify(eligibleBoardEditor));
    approvedPayload.approved_plan = "CP-BE-APPROVED";
    // After approving tip A, Edited keeps A (Approved) — it must not fall back
    // to null / an older leftover Draft merely because the tip left Draft.
    approvedPayload.plans.board_editor_draft = {
        name: "CP-BE-APPROVED",
        source_type: "Board Editor",
        status: "Approved",
        display_context: "current_approved",
        can_approve: false,
        is_current_approved_tip: true,
        content_identity: "CP-BE-APPROVED|11|2026-01-11|fp|abc",
        validation: { status: "Valid", needs_recalculation: false },
        totals: { required_boards: 2 },
        snapshot_json: JSON.stringify({ sheets: [{ sheet_no: 1, pieces: [{ id: 1 }] }] }),
    };
    approvedPayload.plans.approved = {
        name: "CP-BE-APPROVED",
        source_type: "Board Editor",
        status: "Approved",
        display_context: "current_approved",
        validation: { status: "Valid", needs_recalculation: false },
        totals: { required_boards: 2 },
        snapshot_json: JSON.stringify({ sheets: [{ sheet_no: 1, pieces: [{ id: 1 }] }] }),
    };
    const edited = loadContext(approvedPayload);
    const editedFrm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "BoardEditor",
        fields_dict: {},
    };
    assert.equal(
        edited.owner.rowForTab(editedFrm, "BoardEditor")?.name,
        "CP-BE-APPROVED",
        "Edited tab keeps the approved Board Editor tip identity",
    );
    assert.equal(edited.owner.canApprove(editedFrm, "BoardEditor", edited.owner.rowForTab(editedFrm)), false);
    edited.owner.render(editedFrm, edited.host);
    assert.doesNotMatch(edited.host.html(), /Approve the edited plan/);

    const { owner, host } = loadContext(approvedPayload);
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "Approved",
        fields_dict: {},
    };
    owner.render(frm, host);
    assert.match(host.html(), /Plan approved for production/);
    assert.doesNotMatch(host.html(), /Approve the edited plan/);
}

{
    const { owner, host } = loadContext(eligibleBoardEditor, { approve_dxf: false });
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "BoardEditor",
        fields_dict: {},
    };
    // Mirror server capability denial in the workspace payload.
    frm.__force = true;
    const payload = JSON.parse(JSON.stringify(eligibleBoardEditor));
    payload.capabilities.approve = false;
    const denied = loadContext(payload, { approve_dxf: false });
    denied.owner.render(frm, denied.host);
    assert.doesNotMatch(denied.host.html(), /Approve the edited plan/);
    assert.doesNotMatch(denied.host.html(), /is-blocked/);
}

{
    const { owner, host } = loadContext(eligibleBoardEditor);
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "System",
        fields_dict: {},
    };
    owner.render(frm, host);
    assert.match(host.html(), /Approve the system plan/);
    assert.equal(owner.rowForTab(frm, "System")?.name, "CP-SYSTEM");
}

{
    const source = fs.readFileSync(CONTEXT_PATH, "utf8");
    assert.match(source, /BoardEditor:\s*"board_editor_draft"/);
    assert.match(source, /approveDenialReason/);
    const api = fs.readFileSync(API_PATH, "utf8");
    assert.match(api, /args\.plan_name = explicitPlan/);
}

console.log("board_editor_approve_action.test.js: ok");
