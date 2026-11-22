"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");
const pending = () => {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
};
const settings = {
    packing_mode: "smart",
    cutting_machine_type: "CNC Router",
    kerf_mm: 4,
    trim_margin_mm: 0,
    optimization_time_limit_sec: 5,
};
const rejection = {
    calculation_rejected: true,
    accepted: false,
    order_name: "DCO-1",
    plan: null,
    addon_cutter_rejections: [
        { door_no: 4, kind: "liner", width_mm: 5, diameter_mm: 8, code: "liner_narrower_than_cutter" },
        { door_no: 9, kind: "recessed_handle_cutout", width_mm: 4, diameter_mm: 8, code: "liner_narrower_than_cutter" },
    ],
};
const success = {
    preview_id: "preview-1",
    order_name: "DCO-1",
    source_plan_name: "CP-1",
    source_plan_revision: 1,
    source_plan_modified: "before",
    summary: { settings, validation: { status: "Valid" } },
    candidates: [{
        candidate_id: "one",
        manufacturing_status: "Validated",
        summary: { settings, validation: { status: "Valid", needs_recalculation: false } },
    }],
    candidate_id: "one",
    plan: { sheets: [{ sheet_no: 1, pieces: [] }], preview_candidate_id: "one" },
    expires_in_sec: 60,
};

function element(className) {
    return {
        className,
        children: [],
        remove() {
            if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
        },
        querySelector(selector) {
            return this.querySelectorAll(selector)[0] || null;
        },
        querySelectorAll(selector) {
            return this.children.filter(child => {
                if (String(selector).includes("server")) return child.source === "server";
                if (String(selector).includes("dco-board-gallery")) return child.className === "dco-board-gallery";
                return child.className === "dco-addon-cutter-warning";
            });
        },
        insertAdjacentHTML(where, markup) {
            const node = element("dco-addon-cutter-warning");
            node.source = markup.includes("server") ? "server" : "";
            node.markup = markup;
            node.parent = this;
            if (where === "beforebegin" && this.parent) {
                const index = this.parent.children.indexOf(this);
                this.parent.children.splice(index, 0, node);
                node.parent = this.parent;
                return;
            }
            this.children.unshift(node);
        },
    };
}

async function run() {
    const jobs = [];
    const prints = [];
    const planRoot = element("dco-cutting-plan");
    const gallery = element("dco-board-gallery");
    gallery.parent = planRoot;
    planRoot.children.push(gallery);
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-1" },
        fields_dict: {
            cutting_plan_html: {
                $wrapper: {
                    length: 1,
                    find(selector) {
                        return {
                            length: selector === ".dco-plan-tab-content" ? 0 : 1,
                            each(callback) {
                                if (selector === ".dco-cutting-plan") callback(0, planRoot);
                            },
                            prepend() {},
                            first() { return this; },
                        };
                    },
                },
            },
        },
    };
    const window = {
        cur_frm: frm,
        dispatchEvent() {},
        AlmdinaDocumentContext: { formIdentity(form) { return `DCO::${form.doc.name}`; } },
        AlmdinaPlanWorkspaceAPI: {
            preview() {
                const job = pending();
                jobs.push(job);
                return job.promise;
            },
        },
        AlmdinaCuttingPlanRender: {
            mountAddonCutterBanner(root, findings) {
                root.querySelectorAll(".dco-addon-cutter-warning[data-addon-cutter-source='server']")
                    .forEach(node => node.remove());
                if (!findings || !findings.length) return;
                const galleryNode = root.querySelector(".dco-board-gallery");
                galleryNode.insertAdjacentHTML(
                    "beforebegin",
                    `<div class="dco-addon-cutter-warning" data-addon-cutter-source="server">${findings.length}</div>`
                );
            },
        },
        frappe: { msgprint(message) { prints.push(message); } },
    };
    const context = vm.createContext({
        window,
        document: { getElementById() { return { id: "styles" }; } },
        $() { return { append() {} }; },
        frappe: window.frappe,
        __: value => value,
        console,
        CustomEvent: class {
            constructor(name, options) {
                this.type = name;
                this.detail = options && options.detail;
            }
        },
    });
    vm.runInContext(
        fs.readFileSync(path.join(root, "cutting_plan/door_cutting_order_plan_preview_session.js"), "utf8"),
        context
    );
    vm.runInContext(
        fs.readFileSync(path.join(root, "cutting_plan/door_cutting_order_plan_preview_presenter.js"), "utf8"),
        context
    );
    const session = window.AlmdinaPlanPreviewSession;
    const presenter = window.AlmdinaPlanPreviewPresenter;
    const failed = session.preview(frm, settings);
    jobs[0].resolve(rejection);
    assert.equal(await failed, false);
    const rejectedState = session.snapshot(frm);
    assert.equal(rejectedState.status, "error");
    assert.equal(rejectedState.payload, null);
    assert.equal(rejectedState.addonCutterRejections.length, 2);
    presenter.renderPersistedEditingState(frm, rejectedState.status);
    assert.equal(planRoot.children[0].className, "dco-addon-cutter-warning");
    assert.equal(planRoot.children[1].className, "dco-board-gallery");
    assert.equal(prints.length, 0);

    const corrected = session.preview(frm, settings);
    jobs[1].resolve(success);
    assert.equal(await corrected, true);
    const ready = session.snapshot(frm);
    assert.equal(ready.status, "ready");
    assert.equal(ready.addonCutterRejections.length, 0);
    presenter.renderPreviewPlan(frm, ready, true);
    assert.equal(planRoot.querySelector(".dco-addon-cutter-warning"), null);
}

run().catch(error => {
    console.error(error);
    process.exit(1);
});
