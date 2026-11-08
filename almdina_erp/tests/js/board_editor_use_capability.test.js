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

function loadContext(permissions) {
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
        location: { origin: "https://erp.example.test" },
        open() { return { opener: windowObj }; },
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
                data: {
                    order_name: "26-00021",
                    approved_plan: "",
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
                        system_draft: {
                            name: "CP-SYS",
                            source_type: "System",
                            status: "Draft",
                            revision: 1,
                            modified: "2026-01-01",
                            content_identity: "CP-SYS|1|2026-01-01|fp|d",
                            can_approve: true,
                            manufacturing_blocked: false,
                            validation: { status: "Valid", needs_recalculation: false },
                            totals: { required_boards: 1 },
                            snapshot_json: JSON.stringify({
                                sheets: [{ sheet_no: 1, pieces: [{ id: 1 }] }],
                            }),
                        },
                        uploaded_draft: null,
                        board_editor_draft: null,
                        approved: null,
                    },
                },
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
    return { owner: context.window.AlmdinaPlanContextActionsUX, host };
}

const basePermissions = {
    view_cutting_plan: true,
    view_system_cutting_plan: true,
    view_approved_cutting_plan: true,
};

{
    const { owner, host } = loadContext({
        ...basePermissions,
        use_board_editor: true,
    });
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "System",
        fields_dict: {},
    };
    const row = owner.rowForTab(frm, "System");
    assert.equal(owner.canOpenBoardEditor(frm, row), true);
    owner.render(frm, host);
    assert.match(host.html(), /dco-open-board-editor/);
}

{
    const { owner, host } = loadContext({
        ...basePermissions,
        use_board_editor: false,
    });
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "System",
        fields_dict: {},
    };
    assert.equal(
        owner.canOpenBoardEditor(frm, owner.rowForTab(frm, "System")),
        false,
    );
    owner.render(frm, host);
    assert.doesNotMatch(host.html(), /dco-open-board-editor/);
}

{
    const { owner, host } = loadContext({
        ...basePermissions,
        edit_optimizer_settings: true,
        use_board_editor: false,
    });
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "System",
        fields_dict: {},
    };
    assert.equal(
        owner.canOpenBoardEditor(frm, owner.rowForTab(frm, "System")),
        false,
        "edit algorithm alone must not open the board editor",
    );
    owner.render(frm, host);
    assert.doesNotMatch(host.html(), /dco-open-board-editor/);
}

{
    const { owner } = loadContext({
        use_board_editor: true,
        view_cutting_plan: false,
        view_system_cutting_plan: false,
        view_approved_cutting_plan: false,
    });
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "26-00021", status: "Draft", production_path: "" },
        __almdina_active_plan_tab: "System",
        fields_dict: {},
    };
    assert.equal(
        owner.canOpenBoardEditor(frm, owner.rowForTab(frm, "System")),
        false,
        "board editor capability without plan view stays closed",
    );
}

console.log("board_editor_use_capability.test.js: ok");
