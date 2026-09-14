(() => {
    "use strict";

    if (window.AlmdinaCostOffcutAssignmentUX) return;

    const STYLE_ID = "dco-cost-offcut-assignment-v1";
    const ROOT_CLASS = "dco-cost-offcut-assignment";
    const EMPTY_STATE = "UNASSIGNED";
    const CUSTOMER = "CUSTOMER";
    const FACTORY = "FACTORY";

    const STATE_BY_SELECTION = Object.freeze({
        [`${CUSTOMER}:${FACTORY}`]: "CUSTOMER_FACTORY",
        [`${CUSTOMER}:${CUSTOMER}`]: "CUSTOMER_CUSTOMER",
        [`${FACTORY}:${FACTORY}`]: "FACTORY_FACTORY",
    });

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function captureDocument(frm) {
        const context = documentContext();
        return context && typeof context.capture === "function"
            ? context.capture(frm)
            : { name: String(frm && frm.doc && frm.doc.name || "") };
    }

    function documentStillCurrent(frm, token) {
        const context = documentContext();
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, token);
        }
        return window.cur_frm === frm
            && String(frm && frm.doc && frm.doc.name || "") === String(token && token.name || "");
    }

    function costData(frm) {
        const owner = window.AlmdinaCostWorkspaceState;
        const state = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
        return state && state.status === "ready" && state.data ? state.data : null;
    }

    function projection(frm) {
        const data = costData(frm);
        const offcut = data && data.offcut;
        return offcut && Array.isArray(offcut.assignments) && offcut.assignments.length
            ? offcut
            : null;
    }

    function canEdit(frm) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && (
                typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, "set_offcut_execution_owner")
                    : permissions.can("set_offcut_execution_owner")
            )
        );
    }

    function sourceForState(state) {
        const value = String(state || "");
        if (value === "FACTORY_FACTORY") return FACTORY;
        if (value.startsWith("CUSTOMER_")) return CUSTOMER;
        return "";
    }

    function executionForState(state) {
        const value = String(state || "");
        if (value === "CUSTOMER_CUSTOMER") return CUSTOMER;
        if (value.endsWith("_FACTORY")) return FACTORY;
        return "";
    }

    function stateFor(source, execution) {
        return STATE_BY_SELECTION[`${source}:${execution}`] || EMPTY_STATE;
    }

    function summaryHtml(summary) {
        return (summary || []).map(item => `
            <div class="dco-cost-offcut-summary__item">
                <span>${esc(item.label)}</span>
                <strong>${Number(item.count || 0)}</strong>
            </div>
        `).join("");
    }

    function rowHtml(item, editable) {
        const state = String(item.business_state || EMPTY_STATE);
        const source = sourceForState(state);
        const execution = executionForState(state);
        const disabled = editable ? "" : "disabled";
        return `
            <article class="dco-cost-offcut-row" data-piece-instance-id="${esc(item.piece_instance_id)}">
                <div class="dco-cost-offcut-row__identity">
                    <strong>${esc(item.piece_label || item.piece_instance_id || __("قطعة"))}</strong>
                    <span>${esc(item.business_state_label || __("غير محدد"))}</span>
                </div>
                <label>المصدر
                    <select class="form-control input-sm dco-cost-offcut-source" ${disabled}>
                        <option value="" ${!source ? "selected" : ""}>غير محدد</option>
                        <option value="${CUSTOMER}" ${source === CUSTOMER ? "selected" : ""}>من الزبون</option>
                        <option value="${FACTORY}" ${source === FACTORY ? "selected" : ""}>من المعمل</option>
                    </select>
                </label>
                <label>التنفيذ
                    <select class="form-control input-sm dco-cost-offcut-execution" ${disabled}>
                        <option value="" ${!execution ? "selected" : ""}>غير محدد</option>
                        <option value="${FACTORY}" ${execution === FACTORY ? "selected" : ""}>في المعمل</option>
                        <option value="${CUSTOMER}" ${execution === CUSTOMER ? "selected" : ""}>عند الزبون</option>
                    </select>
                </label>
            </article>
        `;
    }

    function html(offcut, editable) {
        return `
            <section class="${ROOT_CLASS} dco-cost-section" aria-label="${esc(__("قطع النقص"))}">
                <div class="dco-cost-section-title">
                    <div>
                        <h4>${esc(__("قطع النقص"))}</h4>
                        <span>${esc(__("حدد مصدر الفضلة ومكان التنفيذ لكل قطعة فعلية."))}</span>
                    </div>
                    <span class="dco-cost-offcut-count">${offcut.assignments.length} ${esc(__("قطع"))}</span>
                </div>
                <div class="dco-cost-offcut-summary">${summaryHtml(offcut.summary)}</div>
                ${editable ? `
                    <div class="dco-cost-offcut-bulk">
                        <label>المصدر
                            <select class="form-control input-sm dco-cost-offcut-bulk-source">
                                <option value="${CUSTOMER}">من الزبون</option>
                                <option value="${FACTORY}">من المعمل</option>
                            </select>
                        </label>
                        <label>التنفيذ
                            <select class="form-control input-sm dco-cost-offcut-bulk-execution">
                                <option value="${FACTORY}">في المعمل</option>
                                <option value="${CUSTOMER}">عند الزبون</option>
                            </select>
                        </label>
                        <button type="button" class="btn btn-default btn-sm dco-cost-offcut-apply-all">تطبيق على الكل</button>
                        <button type="button" class="btn btn-primary btn-sm dco-cost-offcut-save">حفظ قطع النقص</button>
                    </div>
                ` : ""}
                <div class="dco-cost-offcut-rows">${offcut.assignments.map(item => rowHtml(item, editable)).join("")}</div>
            </section>
        `;
    }

    function normalizeExecution(row) {
        const source = row.find(".dco-cost-offcut-source").val();
        const execution = row.find(".dco-cost-offcut-execution");
        if (source === FACTORY) {
            execution.val(FACTORY).prop("disabled", true);
            return;
        }
        if (!source) {
            execution.val("").prop("disabled", true);
            return;
        }
        execution.prop("disabled", false);
    }

    function assignments(root) {
        return root.find(".dco-cost-offcut-row").map(function () {
            const row = $(this);
            const source = row.find(".dco-cost-offcut-source").val();
            const execution = row.find(".dco-cost-offcut-execution").val();
            return {
                piece_instance_id: row.attr("data-piece-instance-id"),
                business_state: stateFor(source, execution),
            };
        }).get();
    }

    async function save(frm, root) {
        const api = window.AlmdinaPlanWorkspaceAPI;
        const policy = window.AlmdinaOrderMutationImpactPolicy;
        const offcut = projection(frm);
        if (!api || typeof api.saveOffcutAssignments !== "function" || !policy
            || typeof policy.reconcileOffcutMutation !== "function" || !offcut) {
            frappe.msgprint(__("تعذر تحميل مسار حفظ قطع النقص."));
            return false;
        }

        const token = captureDocument(frm);
        const button = root.find(".dco-cost-offcut-save");
        button.prop("disabled", true);
        try {
            const result = await api.saveOffcutAssignments(offcut.plan_name, assignments(root));
            if (!documentStillCurrent(frm, token)) return false;
            await policy.reconcileOffcutMutation(frm, result);
            if (!documentStillCurrent(frm, token)) return false;
            frappe.show_alert({ message: __("تم حفظ تصنيف قطع النقص."), indicator: "green" }, 4);
            return true;
        } finally {
            if (documentStillCurrent(frm, token)) button.prop("disabled", false);
        }
    }

    function bind(frm, root) {
        root.off(".almdinaCostOffcut");
        root.on("change.almdinaCostOffcut", ".dco-cost-offcut-source", function () {
            normalizeExecution($(this).closest(".dco-cost-offcut-row"));
        });
        root.on("change.almdinaCostOffcut", ".dco-cost-offcut-bulk-source", function () {
            const bulk = $(this).closest(".dco-cost-offcut-bulk");
            const execution = bulk.find(".dco-cost-offcut-bulk-execution");
            if ($(this).val() === FACTORY) execution.val(FACTORY).prop("disabled", true);
            else execution.prop("disabled", false);
        });
        root.on("click.almdinaCostOffcut", ".dco-cost-offcut-apply-all", () => {
            const bulk = root.find(".dco-cost-offcut-bulk");
            const source = bulk.find(".dco-cost-offcut-bulk-source").val();
            const execution = bulk.find(".dco-cost-offcut-bulk-execution").val();
            root.find(".dco-cost-offcut-row").each(function () {
                const row = $(this);
                row.find(".dco-cost-offcut-source").val(source);
                row.find(".dco-cost-offcut-execution").val(source === FACTORY ? FACTORY : execution);
                normalizeExecution(row);
            });
        });
        root.on("click.almdinaCostOffcut", ".dco-cost-offcut-save", () => { save(frm, root); });
        root.find(".dco-cost-offcut-row").each(function () { normalizeExecution($(this)); });
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("<style>", { id: STYLE_ID, text: `
            .${ROOT_CLASS}{direction:rtl}
            .${ROOT_CLASS}> .dco-cost-section-title{display:flex;align-items:center;justify-content:space-between;gap:12px}
            .dco-cost-offcut-count{display:inline-flex;padding:4px 9px;border-radius:999px;background:var(--subtle-fg,#f4f6f8);font-size:11px;font-weight:800}
            .dco-cost-offcut-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:12px 14px 0}
            .dco-cost-offcut-summary__item{padding:9px 10px;border-radius:10px;background:var(--subtle-fg,#f6f8fa)}
            .dco-cost-offcut-summary__item span{display:block;color:var(--text-muted,#687481);font-size:10px;font-weight:700}
            .dco-cost-offcut-summary__item strong{display:block;margin-top:3px;font-size:16px}
            .dco-cost-offcut-bulk{display:grid;grid-template-columns:minmax(130px,1fr) minmax(130px,1fr) auto auto;gap:8px;align-items:end;padding:12px 14px;border-bottom:1px solid var(--border-color,#e1e6ea)}
            .dco-cost-offcut-bulk label,.dco-cost-offcut-row label{display:grid;gap:4px;margin:0;font-size:10px;font-weight:800;color:var(--text-muted,#687481)}
            .dco-cost-offcut-bulk .btn{min-height:34px;border-radius:9px;font-weight:800;white-space:nowrap}
            .dco-cost-offcut-rows{display:grid;gap:8px;padding:12px 14px 14px}
            .dco-cost-offcut-row{display:grid;grid-template-columns:minmax(180px,1.4fr) minmax(120px,.8fr) minmax(120px,.8fr);gap:10px;align-items:end;padding:11px;border:1px solid var(--border-color,#e1e6ea);border-radius:12px;background:var(--card-bg,#fff)}
            .dco-cost-offcut-row__identity strong{display:block;font-size:12px}
            .dco-cost-offcut-row__identity span{display:block;margin-top:3px;color:var(--text-muted,#687481);font-size:10px}
            @media(max-width:760px){.dco-cost-offcut-summary,.dco-cost-offcut-bulk,.dco-cost-offcut-row{grid-template-columns:1fr 1fr}.dco-cost-offcut-bulk .btn{width:100%}}
            @media(max-width:480px){.dco-cost-offcut-summary,.dco-cost-offcut-bulk,.dco-cost-offcut-row{grid-template-columns:1fr}.dco-cost-offcut-row__identity{padding-bottom:3px}}
        ` }).appendTo("head");
    }

    function render(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return false;
        installStyles();
        wrapper.find(`.${ROOT_CLASS}`).remove();
        const offcut = projection(frm);
        if (!offcut) return false;
        const measurement = wrapper.find(".dco-cost-measurements-section").first();
        const section = $(html(offcut, canEdit(frm)));
        if (measurement.length) section.insertBefore(measurement);
        else wrapper.find(".dco-cost-shell").first().append(section);
        bind(frm, section);
        return true;
    }

    window.AlmdinaCostOffcutAssignmentUX = Object.freeze({ render });
})();