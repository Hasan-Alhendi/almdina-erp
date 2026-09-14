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

    function optionForState(state) {
        const value = String(state || EMPTY_STATE);
        return ["CUSTOMER_FACTORY", "FACTORY_FACTORY", "CUSTOMER_CUSTOMER"].includes(value) ? value : "";
    }
    function rowLabel(item) {
        const number = item.piece_number || item.piece_no || item.sequence || item.piece_label || item.index || "—";
        const width = item.width || item.width_cm || item.w;
        const length = item.length || item.length_cm || item.h;
        const measure = item.measurement || item.size || (width && length ? `${width}x${length}` : "—");
        return { number, measure };
    }
    function rowHtml(item, editable) {
        const selected = optionForState(item.business_state);
        const disabled = editable ? "" : "disabled";
        const options = [["CUSTOMER_FACTORY","المصدر الزبون · التنفيذ في المعمل"],["FACTORY_FACTORY","المصدر المعمل · التنفيذ في المعمل"],["CUSTOMER_CUSTOMER","المصدر الزبون · التنفيذ عند الزبون"]];
        return `<tr class="dco-cost-offcut-row" data-piece-instance-id="${esc(item.piece_instance_id)}"><th scope="row"><strong>درفة ${esc(rowLabel(item).number)}</strong><span class="dco-cost-offcut-measure">${esc(rowLabel(item).measure)}</span></th><td class="dco-cost-offcut-options"><div class="dco-cost-offcut-option-group" role="radiogroup" aria-label="${esc(rowLabel(item))}">${options.map(([value,label]) => `<label class="dco-cost-offcut-option"><input type="radio" name="dco-offcut-${esc(item.piece_instance_id)}" value="${value}" ${selected===value?"checked":""} ${disabled}><span>${esc(label)}</span></label>`).join("")}</div></td></tr>`;
    }

    function html(offcut, editable) {
        return `<section class="${ROOT_CLASS} dco-cost-section" aria-label="${esc(__("قطع النقص"))}"><div class="dco-cost-section-title"><div><h4>${esc(__("قطع النقص"))}</h4><span>اختر أحد الخيارات الثلاثة لكل درفة.</span></div><span class="dco-cost-offcut-count">${offcut.assignments.length} درفة</span></div><div class="dco-cost-offcut-table-wrap"><table class="dco-cost-offcut-table"><thead><tr><th>الدرفة</th><th>مصدر الكلفة ومكان التنفيذ</th></tr></thead><tbody>${offcut.assignments.map(item => rowHtml(item, editable)).join("")}</tbody></table></div></section>`;
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
            const businessState = row.find("input[type=radio]:checked").val() || EMPTY_STATE;
            return {
                piece_instance_id: row.attr("data-piece-instance-id"),
                business_state: businessState,
            };
        }).get();
    }

    function pendingMap(frm) {
        if (!frm.__almdina_offcut_pending_assignments) frm.__almdina_offcut_pending_assignments = {};
        return frm.__almdina_offcut_pending_assignments;
    }

    function rootFor(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper;
        return wrapper && wrapper.length ? wrapper.find(`.${ROOT_CLASS}`).first() : null;
    }

    function hasPending(frm) {
        const root = rootFor(frm);
        const offcut = projection(frm);
        if (!root || !root.length || !offcut) return false;
        const current = assignments(root).map(item => [item.piece_instance_id, item.business_state]);
        const saved = offcut.assignments.map(item => [item.piece_instance_id, item.business_state]);
        return JSON.stringify(current) !== JSON.stringify(saved);
    }

    function syncPriceVisibility(frm, root) {
        const price = root.closest(".dco-cost-settings-offcut").find(".dco-offcut-price-section").first();
        if (!price.length) return;
        const factorySelected = root.find('input[type="radio"][value="FACTORY_FACTORY"]:checked').length > 0;
        price.toggle(factorySelected);
        price.find("[data-offcut-price-input]").prop("disabled", !factorySelected).prop("readOnly", !factorySelected);
    }

    async function savePending(frm) {
        const root = rootFor(frm);
        return root && root.length && hasPending(frm) ? save(frm, root) : true;
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
        try {
            const result = await api.saveOffcutAssignments(offcut.plan_name, assignments(root));
            if (!documentStillCurrent(frm, token)) return false;
            await policy.reconcileOffcutMutation(frm, result);
            if (!documentStillCurrent(frm, token)) return false;
            frm.__almdina_offcut_pending_assignments = {};
            frappe.show_alert({ message: __("تم حفظ تصنيف قطع النقص."), indicator: "green" }, 4);
            return true;
        } finally {

        }
    }

    function bind(frm, root) {
        root.off(".almdinaCostOffcut");
        root.on("change.almdinaCostOffcut input.almdinaCostOffcut", 'input[type="radio"]', () => {
            const map = pendingMap(frm);
            assignments(root).forEach(item => { map[item.piece_instance_id] = item.business_state; });
            syncPriceVisibility(frm, root);
        });
        syncPriceVisibility(frm, root);
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("<style>", { id: STYLE_ID, text: `
            .${ROOT_CLASS}{direction:rtl}.dco-cost-offcut-table-wrap{overflow:auto;padding:10px 12px 12px}.dco-cost-offcut-table{width:100%;border-collapse:separate;border-spacing:0 7px;font-size:12px}.dco-cost-offcut-table th{padding:9px 10px;text-align:right;white-space:nowrap}.dco-cost-offcut-table tbody th,.dco-cost-offcut-table tbody td{padding:10px;border:1px solid var(--border-color,#e1e6ea);background:var(--card-bg,#fff);vertical-align:middle}.dco-cost-offcut-table tbody th{border-radius:10px 0 0 10px;width:24%;font-weight:900}.dco-cost-offcut-measure{display:block;margin-top:4px;color:var(--text-muted,#687481);font-size:10px;font-weight:700}.dco-cost-offcut-table tbody td{border-right:0;border-radius:0 10px 10px 0}.dco-cost-offcut-option-group{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.dco-cost-offcut-option{display:flex;align-items:center;gap:7px;min-height:34px;margin:0;padding:7px 9px;border:1px solid var(--border-color,#e1e6ea);border-radius:9px;background:var(--subtle-fg,#f8fafc);font-size:11px;font-weight:800;cursor:pointer}.dco-cost-offcut-option:has(input:checked){border-color:var(--primary,#2490ef);background:rgba(36,144,239,.08)}.dco-cost-offcut-option input{margin:0;accent-color:var(--primary,#2490ef)}.dco-cost-offcut-option input:disabled+span{opacity:.72}.dco-cost-offcut-actions{display:flex;justify-content:flex-start;padding:0 12px 12px}@media(max-width:800px){.dco-cost-offcut-option-group{grid-template-columns:1fr}.dco-cost-offcut-table tbody th{width:32%}}
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
        const slot = wrapper.find(".dco-cost-settings-offcut").first();
        if (!slot.length) return false;
        const editing = window.AlmdinaCostEditSessionUX && typeof window.AlmdinaCostEditSessionUX.isEditing === "function" ? window.AlmdinaCostEditSessionUX.isEditing(frm) : false;
        const pending = pendingMap(frm);
        const visibleAssignments = offcut.assignments.map(item => ({
            ...item,
            business_state: pending[item.piece_instance_id] || item.business_state,
        }));
        const section = $(html({ ...offcut, assignments: visibleAssignments }, canEdit(frm) && editing));
        const price = slot.find(".dco-offcut-price-section").detach();
        slot.append(section);
        if (price.length) slot.append(price);
        bind(frm, section);
        return true;
    }

    window.AlmdinaCostOffcutAssignmentUX = Object.freeze({ render, hasPending, savePending });
})();