(() => {
    "use strict";

    if (window.AlmdinaPlanEditSessionUX) return;

    const PLAN_SETTING_FIELDS = Object.freeze([
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ]);
    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const SAVE_METHOD =
        "almdina_erp.almdina_erp.services.plan_settings_edit_service.save_plan_settings";
    const BLOCKED_PLAN_ACTIONS = [
        ".dco-recalculate-plan",
        ".dco-approve-cutting-plan",
        ".dco-print-cutting-plan",
        ".dco-export-dxf",
        ".dco-upload-dxf-plan",
    ].join(",");
    const EDITING_KEY = "__almdina_plan_settings_editing";
    const IDENTITY_KEY = "__almdina_plan_settings_edit_identity";
    const ORIGINAL_DISABLED_ATTR = "data-almdina-plan-edit-original-disabled";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function formIdentity(frm) {
        const context = documentContext();
        if (context && typeof context.formIdentity === "function") {
            return context.formIdentity(frm);
        }
        if (!frm || !frm.doc) return "";
        return `${frm.doctype || frm.doc.doctype || ""}::${frm.doc.name || "__new__"}`;
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function hasActiveProductionStage(frm) {
        return Boolean(String(
            (frm && frm.doc && frm.doc.current_production_stage) || ""
        ).trim());
    }

    function hasProductionRoute(frm) {
        return Boolean(
            hasActiveProductionStage(frm)
            || String((frm && frm.doc && frm.doc.production_path) || "").trim()
        );
    }

    function lifecycleAllowsEdit(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (frm.is_new && frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (String(frm.doc.approved_plan || "").trim()) return false;
        if ((frm.doc.revision_state || "Current") === "Superseded") return false;

        // The focused plan-settings capability owns this edit surface. An active
        // production stage keeps the order in a mutable lifecycle, but its
        // operational role is not a second authorization gate for these fields.
        // Recalculation and other stage commands retain their separate policy.
        if (hasProductionRoute(frm)) {
            return hasActiveProductionStage(frm);
        }
        return DRAFT_LIKE.has(frm.doc.status || "Draft");
    }

    function canEditPlanSettings(frm) {
        return Boolean(
            can(frm, "edit_optimizer_settings")
            && lifecycleAllowsEdit(frm)
        );
    }

    function isEditing(frm) {
        if (!frm || !frm.doc || frm[EDITING_KEY] !== true) return false;
        return frm[IDENTITY_KEY] === formIdentity(frm);
    }

    function planSettingsMayWrite(frm) {
        return Boolean(isEditing(frm) && canEditPlanSettings(frm));
    }

    function setEditing(frm, enabled) {
        if (!frm) return;
        frm[EDITING_KEY] = Boolean(enabled);
        frm[IDENTITY_KEY] = enabled ? formIdentity(frm) : null;
    }

    function refreshFieldAccess(frm) {
        const adapter = window.AlmdinaPlanFieldAccessAdapter;
        if (adapter && typeof adapter.apply === "function") {
            adapter.apply(frm);
        }
    }

    function settingsArgs(frm) {
        return {
            order_name: frm.doc.name,
            packing_mode: frm.doc.packing_mode,
            cutting_machine_type: frm.doc.cutting_machine_type,
            kerf_mm: frm.doc.kerf_mm,
            trim_margin_mm: frm.doc.trim_margin_mm,
            optimization_time_limit_sec: frm.doc.optimization_time_limit_sec,
        };
    }

    function installStyles() {
        if (document.getElementById("dco-plan-edit-session-css")) return;
        $("head").append(`
            <style id="dco-plan-edit-session-css">
                .dco-plan-settings-edit-toolbar {
                    display:flex;
                    align-items:center;
                    justify-content:space-between;
                    gap:10px;
                    flex-wrap:wrap;
                    padding:0 0 11px;
                    margin:0 0 11px;
                    border-bottom:1px solid var(--border-color,#e5e7eb);
                }
                .dco-plan-settings-edit-toolbar .dco-plan-settings-edit-label {
                    display:flex;
                    align-items:center;
                    gap:8px;
                    min-width:0;
                    font-size:12px;
                    font-weight:800;
                    color:var(--text-color,#1f2937);
                }
                .dco-plan-settings-edit-toolbar .dco-plan-settings-edit-state {
                    display:inline-flex;
                    align-items:center;
                    border-radius:999px;
                    padding:3px 8px;
                    background:rgba(36,144,239,.10);
                    color:var(--primary,#2490ef);
                    font-size:10px;
                    font-weight:800;
                }
                .dco-plan-settings-edit-toolbar .dco-plan-settings-edit-actions {
                    display:flex;
                    align-items:center;
                    gap:7px;
                    flex-wrap:wrap;
                }
                .dco-plan-settings-edit-toolbar .btn {
                    min-height:34px;
                    border-radius:9px;
                    font-weight:800;
                    padding-inline:16px;
                }
                @media (max-width:560px) {
                    .dco-plan-settings-edit-toolbar,
                    .dco-plan-settings-edit-toolbar .dco-plan-settings-edit-actions {
                        width:100%;
                    }
                    .dco-plan-settings-edit-toolbar .dco-plan-settings-edit-actions .btn {
                        flex:1 1 0;
                    }
                }
            </style>
        `);
    }

    function actionSurface(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return null;
        const shell = wrapper.find(".dco-plan-actions-shell").first();
        if (!shell.length) return null;
        return { field, wrapper, shell };
    }

    function setPlanActionsSuspended(wrapper, suspended) {
        wrapper.find(BLOCKED_PLAN_ACTIONS).each((_, element) => {
            const button = $(element);
            if (suspended) {
                if (button.attr(ORIGINAL_DISABLED_ATTR) === undefined) {
                    button.attr(ORIGINAL_DISABLED_ATTR, button.prop("disabled") ? "1" : "0");
                }
                button.prop("disabled", true).attr("aria-disabled", "true");
                return;
            }

            const original = button.attr(ORIGINAL_DISABLED_ATTR);
            if (original === undefined) return;
            button.prop("disabled", original === "1");
            button.attr("aria-disabled", original === "1" ? "true" : "false");
            button.removeAttr(ORIGINAL_DISABLED_ATTR);
        });
    }

    function installActionGuard(frm, wrapper) {
        const node = wrapper && wrapper[0];
        if (!node || node.__almdinaPlanEditActionGuardInstalled) return;

        node.addEventListener("click", (event) => {
            if (!isEditing(frm)) return;
            const target = event.target && event.target.closest
                ? event.target.closest(BLOCKED_PLAN_ACTIONS)
                : null;
            if (!target || !node.contains(target)) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            frappe.msgprint(__("احفظ أو ألغِ تعديل إعدادات خطة القص أولًا."));
        }, true);
        node.__almdinaPlanEditActionGuardInstalled = true;
    }

    function render(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        installStyles();

        if (isEditing(frm) && !canEditPlanSettings(frm)) {
            setEditing(frm, false);
            refreshFieldAccess(frm);
        }

        const surface = actionSurface(frm);
        if (!surface) return false;
        const { wrapper, shell } = surface;
        installActionGuard(frm, wrapper);

        const editable = canEditPlanSettings(frm);
        const editing = planSettingsMayWrite(frm);
        setPlanActionsSuspended(wrapper, editing);

        let toolbar = shell.children(".dco-plan-settings-edit-toolbar").first();
        if (!editable) {
            if (toolbar.length) toolbar.remove();
            return true;
        }

        const state = editing ? "editing" : "readonly";
        if (toolbar.length && toolbar.attr("data-state") === state) return true;
        if (!toolbar.length) {
            toolbar = $('<div class="dco-plan-settings-edit-toolbar"></div>');
            shell.prepend(toolbar);
        }
        toolbar.attr("data-state", state);

        if (!editing) {
            toolbar.html(`
                <div class="dco-plan-settings-edit-label">
                    <span>${__("إعدادات خطة القص")}</span>
                    <span class="dco-plan-settings-edit-state">${__("للقراءة فقط")}</span>
                </div>
                <div class="dco-plan-settings-edit-actions">
                    <button type="button" class="btn btn-default dco-plan-settings-edit">${__("تعديل")}</button>
                </div>
            `);
            toolbar.find(".dco-plan-settings-edit").on("click", () => startEditing(frm));
            return true;
        }

        toolbar.html(`
            <div class="dco-plan-settings-edit-label">
                <span>${__("إعدادات خطة القص")}</span>
                <span class="dco-plan-settings-edit-state">${__("وضع التعديل")}</span>
            </div>
            <div class="dco-plan-settings-edit-actions">
                <button type="button" class="btn btn-default dco-plan-settings-cancel">${__("إلغاء")}</button>
                <button type="button" class="btn btn-primary dco-plan-settings-save">${__("حفظ")}</button>
            </div>
        `);
        toolbar.find(".dco-plan-settings-cancel").on("click", () => cancelEditing(frm));
        toolbar.find(".dco-plan-settings-save").on("click", () => saveEditing(frm));
        return true;
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "plan-settings-edit-session", () => render(frm));
            return;
        }
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) render(frm);
        });
    }

    function observeActions(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const node = field && field.$wrapper && field.$wrapper[0];
        if (!node || frm.__almdinaPlanEditSessionObserver) return;

        const observer = new MutationObserver(() => schedule(frm));
        observer.observe(node, { childList: true, subtree: true });
        frm.__almdinaPlanEditSessionObserver = observer;

        const context = documentContext();
        if (context && typeof context.registerObserver === "function") {
            context.registerObserver(frm, "plan-settings-edit-session-observer", observer);
        }
    }

    function refresh(frm) {
        const context = documentContext();
        const run = () => {
            if (!frm || window.cur_frm !== frm) return;
            render(frm);
            observeActions(frm);
        };
        if (context && typeof context.ensureStageContext === "function") {
            context.ensureStageContext(frm).then(run);
            return;
        }
        run();
    }

    function startEditing(frm) {
        if (!canEditPlanSettings(frm)) {
            frappe.msgprint(__("لا تملك صلاحية تعديل إعدادات خطة القص أو أن حالة الطلب الحالية لا تسمح بذلك."));
            return false;
        }
        if (frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(__("احفظ أو ألغِ التعديلات الحالية على الطلب قبل فتح تعديل إعدادات خطة القص."));
            return false;
        }

        setEditing(frm, true);
        refreshFieldAccess(frm);
        render(frm);
        const first = frm.fields_dict && frm.fields_dict.kerf_mm;
        if (first && first.$input && first.$input.length) first.$input.trigger("focus");
        return true;
    }

    async function cancelEditing(frm) {
        if (!isEditing(frm)) return false;
        setEditing(frm, false);
        refreshFieldAccess(frm);
        await frm.reload_doc();
        return true;
    }

    async function saveEditing(frm) {
        if (!isEditing(frm)) return false;
        if (!canEditPlanSettings(frm)) {
            setEditing(frm, false);
            refreshFieldAccess(frm);
            frappe.msgprint(__("لم تعد حالة الطلب الحالية تسمح لك بتعديل إعدادات خطة القص."));
            return false;
        }

        const surface = actionSurface(frm);
        const saveButton = surface && surface.wrapper.find(".dco-plan-settings-save").first();
        if (saveButton && saveButton.length) saveButton.prop("disabled", true);

        try {
            await frappe.call({
                method: SAVE_METHOD,
                args: settingsArgs(frm),
                freeze: true,
                freeze_message: __("جاري حفظ إعدادات خطة القص..."),
            });
            setEditing(frm, false);
            await frm.reload_doc();
            frappe.show_alert({
                message: __("تم حفظ إعدادات خطة القص. أعد الحساب لتحديث النتيجة."),
                indicator: "green",
            }, 5);
            return true;
        } catch (error) {
            refreshFieldAccess(frm);
            render(frm);
            throw error;
        } finally {
            if (saveButton && saveButton.length) saveButton.prop("disabled", false);
        }
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") refresh(frm);
    });

    window.addEventListener("almdina:stage-context-ready", (event) => {
        const frm = event.detail && event.detail.frm;
        if (frm && frm === window.cur_frm) refresh(frm);
    });

    window.addEventListener("almdina:surfaces-settled", (event) => {
        const frm = event.detail && event.detail.frm;
        if (frm && frm === window.cur_frm) schedule(frm);
    });

    window.AlmdinaPlanEditSessionUX = Object.freeze({
        PLAN_SETTING_FIELDS,
        canEditPlanSettings,
        isEditing,
        planSettingsMayWrite,
        startEditing,
        cancelEditing,
        saveEditing,
        render,
        schedule,
    });
})();
