(() => {
    "use strict";

    if (window.AlmdinaPageEditActionUX) return;

    const TAB_KIND = Object.freeze({
        order_tab: "order",
        results_tab: "plan",
        cost_tab: "cost",
    });
    const KIND_CONFIG = Object.freeze({
        order: Object.freeze({
            title: "معلومات الطلب",
        }),
        plan: Object.freeze({
            title: "خطة القص",
        }),
        cost: Object.freeze({
            title: "تكلفة الطلب",
        }),
    });
    const EDIT_LABEL = "تعديل";
    const SAVE_LABEL = "حفظ";
    const CANCEL_LABEL = "إلغاء";
    const TOOLBAR_CLASS = "dco-tab-edit-toolbar";
    const TOOLBAR_SLOT_CLASS = "dco-tab-edit-toolbar-slot";
    const PAGE_CLASS = "dco-tab-local-edit-actions";
    const STYLE_ID = "dco-tab-local-edit-actions-css";
    const TAB_LISTENER_KEY = "__almdinaPageEditTabListenerInstalled";
    const BUSY_KEY = "__almdinaPageEditActionBusy";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function permissionsResolved() {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && typeof permissions.version === "function"
            && permissions.version() > 0
        );
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("head").append(`
            <style id="${STYLE_ID}">
                .${PAGE_CLASS} .page-actions .primary-action {
                    display:none !important;
                }
                .${PAGE_CLASS} .page-actions .dco-context-edit-cancel {
                    display:none !important;
                }
                .${TOOLBAR_CLASS} {
                    display:flex;
                    align-items:center;
                    justify-content:flex-end;
                    gap:12px;
                    margin:0;
                    padding:0;
                    border:0;
                    border-radius:0;
                    background:transparent;
                    box-shadow:none;
                    direction:rtl;
                }
                .${TOOLBAR_SLOT_CLASS} {
                    margin-inline-start:auto;
                    list-style:none;
                    display:flex;
                    align-items:center;
                }
                .${TOOLBAR_CLASS}__identity {
                    display:flex;
                    align-items:center;
                    gap:8px;
                    min-width:0;
                }
                .${TOOLBAR_CLASS}[data-compact="1"] .${TOOLBAR_CLASS}__identity {
                    display:none;
                }
                .${TOOLBAR_CLASS}__title {
                    font-size:13px;
                    font-weight:850;
                    color:var(--text-color,#26313b);
                    white-space:nowrap;
                }
                .${TOOLBAR_CLASS}__state {
                    display:inline-flex;
                    align-items:center;
                    min-height:24px;
                    padding:3px 8px;
                    border-radius:999px;
                    background:var(--subtle-fg,#f4f6f8);
                    color:var(--text-muted,#687481);
                    font-size:10px;
                    font-weight:750;
                    white-space:nowrap;
                }
                .${TOOLBAR_CLASS}[data-editing="1"] {
                    border-color:rgba(36,144,239,.34);
                    box-shadow:0 0 0 3px rgba(36,144,239,.08);
                }
                .${TOOLBAR_CLASS}[data-editing="1"] .${TOOLBAR_CLASS}__state {
                    background:rgba(36,144,239,.1);
                    color:var(--primary,#2490ef);
                }
                .${TOOLBAR_CLASS}__actions {
                    display:flex;
                    align-items:center;
                    gap:8px;
                    flex:0 0 auto;
                }
                .${TOOLBAR_CLASS}__actions .btn {
                    min-width:82px;
                    min-height:34px;
                    border-radius:9px;
                    font-weight:800;
                }
                .${TOOLBAR_CLASS}__actions .btn:focus-visible {
                    outline:none !important;
                    box-shadow:0 0 0 3px rgba(36,144,239,.15) !important;
                }
                .dco-plan-settings-readonly {
                    margin:0 0 12px;
                    padding:13px 14px;
                    border:1px solid var(--border-color,#dfe3e8);
                    border-radius:13px;
                    background:linear-gradient(180deg,var(--card-bg,#fff),var(--subtle-fg,#fafbfc));
                    direction:rtl;
                }
                .dco-plan-settings-readonly__header {
                    display:flex;
                    align-items:flex-start;
                    justify-content:space-between;
                    gap:10px;
                    margin-bottom:10px;
                }
                .dco-plan-settings-readonly__title {
                    margin:0;
                    font-size:13px;
                    font-weight:850;
                    color:var(--text-color,#26313b);
                }
                .dco-plan-settings-readonly__help {
                    margin:3px 0 0;
                    color:var(--text-muted,#687481);
                    font-size:10.5px;
                    line-height:1.55;
                }
                .dco-plan-settings-readonly__grid {
                    display:grid;
                    grid-template-columns:repeat(5,minmax(0,1fr));
                    gap:8px;
                }
                .dco-plan-settings-readonly__item {
                    min-width:0;
                    padding:9px 10px;
                    border-radius:10px;
                    background:var(--subtle-fg,#f6f8fa);
                }
                .dco-plan-settings-readonly__label {
                    display:block;
                    margin-bottom:4px;
                    color:var(--text-muted,#687481);
                    font-size:10px;
                    font-weight:750;
                }
                .dco-plan-settings-readonly__value {
                    display:block;
                    overflow:hidden;
                    text-overflow:ellipsis;
                    color:var(--text-color,#26313b);
                    font-size:12px;
                    font-weight:850;
                    white-space:nowrap;
                }
                .dco-a53-workspace-polish [data-fieldname="plan_control_actions"][data-almdina-workspace-editing="1"]::before,
                .dco-a53-workspace-polish [data-fieldname="order_cost_invoice_html"][data-almdina-workspace-editing="1"]::before {
                    content:"وضع التعديل مفعّل — غيّر القيم المطلوبة ثم استخدم «حفظ» أو «إلغاء» داخل هذا القسم." !important;
                }
                @media (max-width:900px) {
                    .dco-plan-settings-readonly__grid {
                        grid-template-columns:repeat(2,minmax(0,1fr));
                    }
                }
                @media (max-width:560px) {
                    .${TOOLBAR_CLASS} {
                        align-items:stretch;
                        flex-direction:row;
                        width:100%;
                        justify-content:flex-end;
                    }
                    .${TOOLBAR_CLASS}__actions {
                        width:auto;
                    }
                    .${TOOLBAR_CLASS}__actions .btn {
                        min-width:76px;
                    }
                    .dco-plan-settings-readonly__grid {
                        grid-template-columns:1fr;
                    }
                }
            </style>
        `);
    }

    function formRoot(frm) {
        const wrapper = frm && frm.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function pageRoot(frm) {
        const wrapper = frm && frm.page && frm.page.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function orderApi() {
        return window.AlmdinaOrderRevisionUX || null;
    }

    function planApi() {
        return window.AlmdinaPlanEditSessionUX || null;
    }

    function costApi() {
        return window.AlmdinaCostEditSessionUX || null;
    }

    function apiFor(kind) {
        if (kind === "plan") return planApi();
        if (kind === "cost") return costApi();
        return orderApi();
    }

    function canEdit(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (kind === "plan" && typeof api.canEditPlanSettings === "function") {
            return Boolean(api.canEditPlanSettings(frm));
        }
        if (kind === "cost" && typeof api.canEditCostWorkspace === "function") {
            return Boolean(api.canEditCostWorkspace(frm));
        }
        if (kind === "cost" && typeof api.canEditCostSettings === "function") {
            return Boolean(api.canEditCostSettings(frm));
        }
        if (kind === "order" && typeof api.canOfferEditSession === "function") {
            return Boolean(api.canOfferEditSession(frm));
        }
        return false;
    }

    function isEditing(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (kind === "order" && typeof api.captureEditSessionPresence === "function") {
            return Boolean(api.captureEditSessionPresence(frm));
        }
        return typeof api.isEditing === "function" && Boolean(api.isEditing(frm));
    }

    function activeEditingKind(frm) {
        return ["order", "plan", "cost"].find((kind) => isEditing(frm, kind)) || null;
    }

    function currentTabFieldname(frm) {
        const activeTab = frm && typeof frm.get_active_tab === "function"
            ? frm.get_active_tab()
            : null;
        const native = String(
            activeTab
            && activeTab.df
            && activeTab.df.fieldname
            || ""
        );
        if (TAB_KIND[native]) return native;

        const root = formRoot(frm);
        if (!root || !root.querySelector) return "order_tab";
        for (const fieldname of Object.keys(TAB_KIND)) {
            const node = root.querySelector(`[data-fieldname="${fieldname}"]`);
            const nav = node && (node.closest("li,.nav-item") || node);
            const link = nav && nav.querySelector ? nav.querySelector(".nav-link") : null;
            if (
                (nav && nav.classList && nav.classList.contains("active"))
                || (link && link.classList && link.classList.contains("active"))
                || (link && link.getAttribute("aria-selected") === "true")
            ) {
                return fieldname;
            }
        }
        return "order_tab";
    }

    function activeKind(frm) {
        return TAB_KIND[currentTabFieldname(frm)] || "order";
    }

    function toolbarSelector(kind) {
        return `.${TOOLBAR_CLASS}[data-almdina-tab-edit-kind="${kind}"]`;
    }

    function wrapperNode(wrapper) {
        if (!wrapper) return null;
        if (wrapper.nodeType) return wrapper;
        if (wrapper[0] && wrapper[0].nodeType) return wrapper[0];
        return null;
    }

    function toolbarSlotHost(frm) {
        const root = formRoot(frm);
        if (!root || !root.querySelector) return null;
        for (const fieldname of Object.keys(TAB_KIND)) {
            const node = root.querySelector(`[data-fieldname="${fieldname}"]`);
            if (!node) continue;
            const tabNode = node.closest("li,.nav-item") || node;
            const parent = tabNode.parentElement;
            if (parent) return parent;
        }
        return null;
    }

    function toolbarSlotFor(frm) {
        const root = formRoot(frm);
        return root && root.querySelector
            ? root.querySelector(`.${TOOLBAR_SLOT_CLASS}`)
            : null;
    }

    function ensureToolbarSlot(frm) {
        const existing = toolbarSlotFor(frm);
        if (existing && existing.isConnected) return existing;
        const host = toolbarSlotHost(frm);
        if (!host) return null;
        const isList = host.tagName === "UL" || host.tagName === "OL";
        const slot = document.createElement(isList ? "li" : "div");
        slot.className = TOOLBAR_SLOT_CLASS;
        host.appendChild(slot);
        return slot;
    }

    function toolbarFor(frm, kind) {
        const root = formRoot(frm);
        return root && root.querySelector ? root.querySelector(toolbarSelector(kind)) : null;
    }

    function ensureToolbar(frm, kind) {
        const existing = toolbarFor(frm, kind);
        if (existing && existing.isConnected) return existing;
        const slot = ensureToolbarSlot(frm);
        if (!slot) return null;
        const toolbar = document.createElement("div");
        toolbar.className = TOOLBAR_CLASS;
        toolbar.setAttribute("data-almdina-tab-edit-kind", kind);
        toolbar.setAttribute("data-compact", "1");
        slot.replaceChildren(toolbar);
        return toolbar;
    }

    function removeToolbars(frm) {
        const root = formRoot(frm);
        if (!root || !root.querySelectorAll) return;
        root.querySelectorAll(`.${TOOLBAR_CLASS}`).forEach((node) => node.remove());
        root.querySelectorAll(`.${TOOLBAR_SLOT_CLASS}`).forEach((node) => {
            if (!node.childElementCount) node.remove();
        });
    }

    function editBlockedMessage(frm, kind, competingKind = null) {
        if (competingKind && competingKind !== kind) {
            return "احفظ أو ألغِ التعديل المفتوح في القسم الآخر أولًا.";
        }
        if (!permissionsResolved()) return "جاري التحقق من صلاحيات التعديل.";
        if (kind === "order") return "لا تملك صلاحية تعديل الطلب أو أن حالته الحالية لا تسمح بالتعديل.";
        if (kind === "plan") return "لا تملك صلاحية تعديل إعدادات خطة القص أو أن حالة الطلب الحالية لا تسمح بذلك.";
        return "لا تملك صلاحية تعديل التكلفة أو تسعير الدرف الخاصة لهذا المستند.";
    }

    function button(label, className, disabled, title) {
        return `
            <button
                type="button"
                class="btn btn-sm ${className}"
                ${disabled ? "disabled" : ""}
                ${title ? `title="${frappe.utils.escape_html(__(title))}"` : ""}
            >${frappe.utils.escape_html(__(label))}</button>
        `;
    }

    function renderToolbar(frm, kind) {
        const toolbar = ensureToolbar(frm, kind);
        const config = KIND_CONFIG[kind];
        if (!toolbar || !config) return false;

        const busy = Boolean(frm[BUSY_KEY]);
        const editingKind = activeEditingKind(frm);
        const editing = editingKind === kind;
        const competing = Boolean(editingKind && editingKind !== kind);
        const editable = permissionsResolved() && canEdit(frm, kind);
        const editDisabled = busy || competing || !editable;
        const blockMessage = editDisabled ? editBlockedMessage(frm, kind, editingKind) : "";

        toolbar.setAttribute("data-editing", editing ? "1" : "0");
        toolbar.innerHTML = `
            <div class="${TOOLBAR_CLASS}__identity">
                <strong class="${TOOLBAR_CLASS}__title">${frappe.utils.escape_html(__(config.title))}</strong>
                <span class="${TOOLBAR_CLASS}__state">${frappe.utils.escape_html(__(editing ? "وضع التعديل" : "وضع القراءة"))}</span>
            </div>
            <div class="${TOOLBAR_CLASS}__actions">
                ${editing
                    ? button(CANCEL_LABEL, "btn-default dco-tab-edit-cancel", busy, "إلغاء التغييرات غير المحفوظة")
                        + button(SAVE_LABEL, "btn-primary dco-tab-edit-save", busy, "حفظ تعديلات هذا القسم فقط")
                    : button(EDIT_LABEL, "btn-default dco-tab-edit-start", editDisabled, blockMessage)}
            </div>
        `;

        const start = toolbar.querySelector(".dco-tab-edit-start");
        const save = toolbar.querySelector(".dco-tab-edit-save");
        const cancel = toolbar.querySelector(".dco-tab-edit-cancel");
        if (start && !start.disabled) {
            start.addEventListener("click", () => runAction(frm, () => startFor(frm, kind)));
        }
        if (save && !save.disabled) {
            save.addEventListener("click", () => runAction(frm, () => saveFor(frm, kind)));
        }
        if (cancel && !cancel.disabled) {
            cancel.addEventListener("click", () => runAction(frm, () => cancelFor(frm, kind)));
        }
        return true;
    }

    async function cancelOrder(frm) {
        const api = orderApi();
        if (!api || !isEditing(frm, "order")) return false;
        if (typeof api.lockEditSession === "function") {
            api.lockEditSession(frm, { silent: true });
        }
        await frm.reload_doc();
        return true;
    }

    function startFor(frm, kind) {
        const api = apiFor(kind);
        if (!api || activeEditingKind(frm)) return false;
        if (kind === "order" && typeof api.enterEditSession === "function") {
            return api.enterEditSession(frm);
        }
        return typeof api.startEditing === "function" ? api.startEditing(frm) : false;
    }

    function saveFor(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (kind === "order" && typeof api.commitEditSession === "function") {
            return api.commitEditSession(frm);
        }
        return typeof api.saveEditing === "function" ? api.saveEditing(frm) : false;
    }

    function cancelFor(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (kind === "order") return cancelOrder(frm);
        return typeof api.cancelEditing === "function" ? api.cancelEditing(frm) : false;
    }

    async function runAction(frm, callback) {
        if (!frm || frm[BUSY_KEY]) return false;
        frm[BUSY_KEY] = true;
        sync(frm);
        try {
            await Promise.resolve(callback());
            return true;
        } finally {
            frm[BUSY_KEY] = false;
            sync(frm);
            schedule(frm);
        }
    }

    function ensurePlanSummaryVisible(frm) {
        let changed = false;
        ["plan_result_section", "plan_controls_intro"].forEach((fieldname) => {
            const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
            if (!field || !field.df || Number(field.df.hidden || 0) !== 1) return;
            if (typeof frm.set_df_property === "function") {
                frm.set_df_property(fieldname, "hidden", 0);
            } else {
                field.df.hidden = 0;
                if (typeof field.refresh === "function") field.refresh();
            }
            changed = true;
        });
        if (changed) {
            const planUx = window.AlmdinaDoorCuttingPlanUX;
            window.requestAnimationFrame(() => {
                if (planUx && typeof planUx.refresh === "function") planUx.refresh(frm);
            });
        }
        return changed;
    }

    function planWorkspaceRow(frm) {
        const owner = window.AlmdinaPlanWorkspaceState;
        return owner && typeof owner.activePlan === "function"
            ? owner.activePlan(frm, "System")
            : null;
    }

    function planWorkspaceReady(frm) {
        const owner = window.AlmdinaPlanWorkspaceState;
        const state = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
        return Boolean(state && state.status === "ready");
    }

    function planSettingValue(value, suffix = "") {
        if (value === null || value === undefined || String(value).trim() === "") return "—";
        return `${String(value)}${suffix}`;
    }

    function renderPlanSettingsReadOnly(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return false;
        wrapper.find(".dco-plan-settings-readonly").remove();
        if (isEditing(frm, "plan") || !planWorkspaceReady(frm)) return false;

        const row = planWorkspaceRow(frm) || {};
        const settings = row.settings || {};
        const values = [
            ["الخوارزمية", planSettingValue(settings.packing_mode || "Auto Pro")],
            ["آلة القص", planSettingValue(settings.cutting_machine_type || "Auto")],
            ["سماكة القص Kerf", planSettingValue(settings.kerf_mm, " مم")],
            ["هامش التشذيب", planSettingValue(settings.trim_margin_mm, " مم")],
            ["مهلة التحسين", planSettingValue(settings.optimization_time_limit_sec, " ث")],
        ];
        const items = values.map(([label, value]) => `
            <div class="dco-plan-settings-readonly__item">
                <span class="dco-plan-settings-readonly__label">${frappe.utils.escape_html(__(label))}</span>
                <strong class="dco-plan-settings-readonly__value">${frappe.utils.escape_html(value)}</strong>
            </div>
        `).join("");
        wrapper.prepend(`
            <section class="dco-plan-settings-readonly" data-almdina-plan-settings-readonly="1">
                <div class="dco-plan-settings-readonly__header">
                    <div>
                        <h4 class="dco-plan-settings-readonly__title">${frappe.utils.escape_html(__("إعدادات خطة القص"))}</h4>
                        <p class="dco-plan-settings-readonly__help">${frappe.utils.escape_html(__("القيم المحفوظة في خطة القص الحالية. اضغط «تعديل» في هذا القسم لتغييرها."))}</p>
                    </div>
                </div>
                <div class="dco-plan-settings-readonly__grid">${items}</div>
            </section>
        `);
        return true;
    }

    function removeLegacyPageCancel(frm) {
        const root = pageRoot(frm);
        if (!root || !root.querySelectorAll) return;
        root.querySelectorAll(".dco-context-edit-cancel").forEach((node) => node.remove());
    }

    function sync(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order" || !frm.page) return false;
        installStyles();
        const page = pageRoot(frm);

        if (frm.is_new && frm.is_new()) {
            if (page && page.classList) page.classList.remove(PAGE_CLASS);
            removeToolbars(frm);
            return true;
        }

        if (page && page.classList) page.classList.add(PAGE_CLASS);
        removeLegacyPageCancel(frm);
        ensurePlanSummaryVisible(frm);
        renderToolbar(frm, activeKind(frm));
        renderPlanSettingsReadOnly(frm);
        return true;
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "tab-local-edit-actions", () => sync(frm));
            return;
        }
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) sync(frm);
        });
    }

    function tabFieldFromEventTarget(target) {
        if (!target || !target.closest) return "";
        const node = target.closest(
            '[data-fieldname="order_tab"],'
            + '[data-fieldname="results_tab"],'
            + '[data-fieldname="cost_tab"]'
        );
        if (!node) return "";
        const nav = node.closest("li,.nav-item");
        if (!nav && !node.classList.contains("nav-link")) return "";
        return String(node.getAttribute("data-fieldname") || "");
    }

    function installTabListener(frm) {
        const root = formRoot(frm);
        if (!root || root[TAB_LISTENER_KEY]) return;
        root.addEventListener("click", (event) => {
            const targetField = tabFieldFromEventTarget(event.target);
            if (!targetField) return;
            const currentField = currentTabFieldname(frm);
            const editingKind = activeEditingKind(frm);
            if (editingKind && targetField !== currentField) {
                event.preventDefault();
                event.stopImmediatePropagation();
                frappe.msgprint(__("احفظ أو ألغِ التعديل الحالي قبل الانتقال إلى قسم آخر."));
                return;
            }
            window.requestAnimationFrame(() => schedule(frm));
        }, true);
        root[TAB_LISTENER_KEY] = true;
    }

    function refresh(frm) {
        installStyles();
        installTabListener(frm);
        // Synchronous sync prevents the legacy global primary action from being
        // painted for a frame before the local tab controls take ownership.
        sync(frm);
        schedule(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        almdina_edit_session_changed(frm) { sync(frm); schedule(frm); },
        refresh_plan_controls(frm) { schedule(frm); },
    });

    [
        "almdina:permissions-updated",
        "almdina:stage-context-ready",
        "almdina:surfaces-settled",
        "almdina:plan-workspace-updated",
        "almdina:cost-workspace-updated",
    ].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    window.AlmdinaPageEditActionUX = Object.freeze({
        activeKind,
        activeEditingKind,
        canEdit,
        isEditing,
        renderToolbar,
        renderPlanSettingsReadOnly,
        sync,
        schedule,
    });
})();
