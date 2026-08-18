(() => {
    "use strict";

    const EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);

    const ADVANCED_MODES = [
        { value: "Auto Pro", label: "أفضل توزيع متقدم" },
        { value: "Deep Search", label: "بحث معمق" },
        { value: "Optimal Search", label: "بحث أمثل" },
    ];

    const DUPLICATED_ACTIONS = [
        ".dco-auto-pro-plan",
        ".dco-deep-plan",
        ".dco-optimal-plan",
        ".dco-algorithm-palette",
    ].join(",");

    const OPTIMIZER_FIELDS = [
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ];

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function stateOwner() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function api() {
        return window.AlmdinaPlanWorkspaceAPI || null;
    }

    function workspaceSnapshot(frm) {
        const owner = stateOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function workspaceData(frm) {
        const state = workspaceSnapshot(frm);
        return state && state.status === "ready" ? state.data : null;
    }

    function workspaceReady(frm) {
        return Boolean(workspaceData(frm));
    }

    function workspaceEditing(frm) {
        const state = workspaceSnapshot(frm);
        return Boolean(state && state.editing);
    }

    function plans(frm) {
        const data = workspaceData(frm);
        return (data && data.plans) || {};
    }

    function activePlan(frm) {
        const owner = stateOwner();
        return owner && typeof owner.activePlan === "function"
            ? owner.activePlan(frm, "System")
            : null;
    }

    function activeSettings(frm) {
        const state = workspaceSnapshot(frm);
        if (state && state.editing && state.draft) return { ...state.draft };
        const row = activePlan(frm);
        return row && row.settings ? { ...row.settings } : null;
    }

    function approvedPlanName(frm) {
        const data = workspaceData(frm);
        return String((data && data.approved_plan) || "").trim();
    }

    function setTextIfChanged(target, value) {
        if (!target || !target.length) return;
        if (String(target.text() || "") !== String(value || "")) target.text(value);
    }

    function installStyles() {
        if (document.getElementById("dco-simple-plan-controls-css")) return;
        $("head").append(`
            <style id="dco-simple-plan-controls-css">
                [data-fieldname="plan_control_actions"] .dco-plan-actions {
                    display:flex !important;align-items:center !important;justify-content:flex-start !important;
                    gap:8px !important;flex-wrap:wrap !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-document-actions {
                    display:flex !important;align-items:center !important;gap:8px !important;flex-wrap:wrap !important;
                }
                [data-fieldname="plan_control_actions"] .dco-recalculate-plan,
                [data-fieldname="plan_control_actions"] .dco-approve-cutting-plan {
                    min-width:210px;min-height:40px !important;font-weight:850 !important;border-radius:10px !important;
                }
                [data-fieldname="plan_control_actions"] .dco-print-cutting-plan,
                [data-fieldname="plan_control_actions"] .dco-export-dxf,
                [data-fieldname="plan_control_actions"] .dco-upload-dxf-plan {
                    min-height:36px !important;border-radius:10px !important;font-weight:800 !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-actions-title { margin-bottom:10px !important; }
                @media (max-width:560px) {
                    [data-fieldname="plan_control_actions"] .dco-recalculate-plan,
                    [data-fieldname="plan_control_actions"] .dco-approve-cutting-plan,
                    [data-fieldname="plan_control_actions"] .dco-print-cutting-plan,
                    [data-fieldname="plan_control_actions"] .dco-export-dxf,
                    [data-fieldname="plan_control_actions"] .dco-upload-dxf-plan { width:100%;min-width:0; }
                }
            </style>
        `);
    }

    function ensureAdvancedModes(frm) {
        const field = frm.fields_dict && frm.fields_dict.packing_mode;
        if (!field || !field.df) return;
        const options = String(field.df.options || "")
            .split("\n")
            .map((value) => value.trim())
            .filter(Boolean);
        let changed = false;
        ADVANCED_MODES.forEach(({ value }) => {
            if (!options.includes(value)) {
                options.push(value);
                changed = true;
            }
        });
        if (changed) {
            field.df.options = options.join("\n");
            if (typeof field.set_options === "function") field.set_options(options);
            else if (typeof field.refresh === "function") field.refresh();
        }

        const settings = activeSettings(frm);
        const selected = String((settings && settings.packing_mode) || "Auto");
        const input = field.$input && field.$input.length ? field.$input : field.$wrapper.find("select");
        if (!input || !input.length) return;
        ADVANCED_MODES.forEach(({ value, label }) => {
            let option = input.find("option").filter(function matchValue() {
                return this.value === value;
            }).first();
            if (!option.length) {
                input.append($("<option>", { value, text: label }));
                option = input.find("option").filter(function matchInsertedValue() {
                    return this.value === value;
                }).first();
            }
            if (String(option.text() || "") !== label) option.text(label);
        });
        if (String(input.val() || "") !== selected) input.val(selected);
    }

    function applyOptimizerFieldAccess(frm) {
        // A5.2: native DCO optimizer fields are compatibility display only.
        // The detached Plan workspace editor is the sole writable surface.
        OPTIMIZER_FIELDS.forEach((fieldname) => {
            const field = frm.fields_dict && frm.fields_dict[fieldname];
            if (!field || !field.df) return;
            if (Number(field.df.read_only || 0) !== 1) {
                frm.set_df_property(fieldname, "read_only", 1);
            }
        });
    }

    function holdsStageOperationalRole(frm) {
        const context = documentContext();
        if (context && typeof context.holdsStageOperationalRole === "function") {
            return context.holdsStageOperationalRole(frm);
        }
        return Boolean(frm && frm.__almdina_actor_holds_stage_role);
    }

    function canMutateCurrentStage(frm) {
        const context = documentContext();
        if (context && typeof context.canMutateCurrentStage === "function") {
            return context.canMutateCurrentStage(frm);
        }
        return holdsStageOperationalRole(frm);
    }

    function isDrawingStage(frm) {
        if (!frm || !frm.doc) return false;
        const status = String(frm.doc.status || "").trim();
        const stageType = String(
            frm.__almdina_stage_type
            || (frm.__almdina_stage_context && frm.__almdina_stage_context.active_stage_type)
            || ""
        ).trim();
        return status === "At Drawing" || stageType === "Drawing";
    }

    function canTuneCuttingAlgorithm(frm) {
        if (!frm || frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (String(frm.doc.revision_state || "Current") === "Superseded") return false;
        if (!workspaceReady(frm)) return false;

        const approved = approvedPlanName(frm);
        if (approved && isDrawingStage(frm)) return canMutateCurrentStage(frm);
        if (approved) return false;

        const context = documentContext();
        if (context && typeof context.canTuneCuttingAlgorithm === "function") {
            return context.canTuneCuttingAlgorithm(frm);
        }
        if (!canMutateCurrentStage(frm)) return false;
        if (frm.doc.current_production_stage) return true;
        return EDITABLE_ORDER_STATUSES.has(frm.doc.status || "Draft");
    }

    function stageMutationBlockReason(frm) {
        const context = documentContext();
        if (context && typeof context.stageMutationBlockReason === "function") {
            return context.stageMutationBlockReason(frm) || "";
        }
        return "";
    }

    function canCalculate(frm) {
        return Boolean(
            workspaceReady(frm)
            && !workspaceEditing(frm)
            && canTuneCuttingAlgorithm(frm)
            && can(frm, "recalculate_plan")
        );
    }

    function recalculationDisabledReason(frm) {
        if (frm.is_new()) return __("احفظ الطلب أولًا قبل حساب خطة القص.");
        if (!workspaceReady(frm)) return __("انتظر حتى يكتمل تحميل خطة القص.");
        if (workspaceEditing(frm)) return __("احفظ أو ألغِ تعديل إعدادات الخطة قبل إعادة الحساب.");
        if (approvedPlanName(frm) && !isDrawingStage(frm)) {
            return __("الخطة المعتمدة لا يمكن إعادة حسابها خارج مرحلة الرسم.");
        }
        if (!can(frm, "recalculate_plan")) return __("تحتاج صلاحية «إعادة حساب الخطة» لتشغيل المحرك.");
        const stageReason = stageMutationBlockReason(frm);
        if (stageReason) return __(stageReason);
        return "";
    }

    async function preparePlanInputs(frm) {
        const compatibility = window.AlmdinaTextBoardPlanUX;
        if (compatibility && typeof compatibility.preparePlanInputs === "function") {
            return Boolean(await compatibility.preparePlanInputs(frm));
        }
        const boardUX = window.AlmdinaBoardTextUX;
        if (boardUX && typeof boardUX.syncInputs === "function") await boardUX.syncInputs(frm);
        if (!boardUX || !boardUX.canCalculatePlan(frm)) {
            frappe.msgprint(__("أدخل صنف اللوح ومقاساته وقياسًا واحدًا صحيحًا على الأقل قبل حساب خطة القص."));
            return false;
        }
        return true;
    }

    async function persistPendingOrderInputs(frm) {
        const fastSave = window.AlmdinaFastSaveUX;
        if (fastSave && typeof fastSave.persistPendingOrderInputs === "function") {
            return Boolean(await fastSave.persistPendingOrderInputs(frm));
        }
        // Order requirements remain owned by DCO. Persisting genuinely dirty
        // measurements before a Plan command is therefore intentional.
        if (frm && frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(__("تعذر تثبيت تعديلات القياسات قبل حساب خطة القص. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            return false;
        }
        return true;
    }

    async function ensureWorkspaceLoaded(frm) {
        const owner = stateOwner();
        if (!owner || typeof owner.load !== "function") return null;
        if (workspaceReady(frm)) return workspaceSnapshot(frm);
        return owner.load(frm);
    }

    async function refreshWorkspaceOwners(frm) {
        const planOwner = stateOwner();
        if (planOwner && typeof planOwner.load === "function") {
            await planOwner.load(frm, { force: true });
        }
        const costOwner = window.AlmdinaCostWorkspaceState;
        if (costOwner && typeof costOwner.load === "function" && costOwner.canView(frm)) {
            await costOwner.load(frm, { force: true });
        }
        const adapter = window.AlmdinaPlanWorkspacePresenterAdapter;
        if (adapter && typeof adapter.project === "function") adapter.project(frm);
    }

    async function runRecalculation(frm) {
        await ensureWorkspaceLoaded(frm);
        if (!canCalculate(frm)) {
            frappe.msgprint(recalculationDisabledReason(frm));
            return false;
        }
        if (!(await preparePlanInputs(frm))) return false;

        const revisionUx = window.AlmdinaOrderRevisionUX;
        const wasEditing = Boolean(
            revisionUx && typeof revisionUx.captureEditSessionPresence === "function"
                ? revisionUx.captureEditSessionPresence(frm)
                : frm.__almdina_edit_session
        );
        if (!(await persistPendingOrderInputs(frm))) return false;

        const transport = api();
        const settings = activeSettings(frm);
        if (!transport || typeof transport.recalculate !== "function" || !settings) {
            frappe.msgprint(__("تعذر تجهيز أمر إعادة حساب خطة القص."));
            return false;
        }

        try {
            await transport.recalculate(frm.doc.name, settings);
            await refreshWorkspaceOwners(frm);
            frappe.show_alert({ message: __("تم تحديث خطة القص والنتائج."), indicator: "green" }, 4);
            if (revisionUx && typeof revisionUx.restorePrimaryAfterPlanEngine === "function") {
                revisionUx.restorePrimaryAfterPlanEngine(frm, wasEditing);
            }
            return true;
        } catch (error) {
            console.error("Cutting plan recalculation failed", error);
            throw error;
        }
    }

    function rowHasPlan(row) {
        if (!row || !row.snapshot_json) return false;
        try {
            const plan = typeof row.snapshot_json === "object"
                ? row.snapshot_json
                : JSON.parse(row.snapshot_json);
            return Boolean(plan && Array.isArray(plan.sheets) && plan.sheets.length);
        } catch (error) {
            return false;
        }
    }

    function approvalSource(frm) {
        const available = plans(frm);
        if (frm.__almdina_active_plan_tab === "Custom" && rowHasPlan(available.uploaded_draft)) {
            return "Custom";
        }
        return "System";
    }

    function approvalRow(frm, source) {
        const available = plans(frm);
        return source === "Custom" ? available.uploaded_draft : available.system_draft;
    }

    function approvalAllowed(frm, source) {
        const row = approvalRow(frm, source);
        return Boolean(
            workspaceReady(frm)
            && !workspaceEditing(frm)
            && can(frm, "approve_dxf")
            && !frm.is_new()
            && canMutateCurrentStage(frm)
            && rowHasPlan(row)
            && !(source === "System" && row && row.validation && row.validation.needs_recalculation)
        );
    }

    async function runApproval(frm) {
        await ensureWorkspaceLoaded(frm);
        const source = approvalSource(frm);
        if (!approvalAllowed(frm, source)) {
            const row = approvalRow(frm, source);
            if (workspaceEditing(frm)) {
                frappe.msgprint(__("احفظ أو ألغِ تعديل إعدادات الخطة قبل الاعتماد."));
            } else if (source === "System" && row && row.validation && row.validation.needs_recalculation) {
                frappe.msgprint(__("أعد حساب خطة القص وراجع النتيجة الجديدة قبل الاعتماد."));
            } else if (!can(frm, "approve_dxf")) {
                frappe.msgprint(__("ليست لديك صلاحية اعتماد خطة القص."));
            } else {
                const reason = stageMutationBlockReason(frm);
                frappe.msgprint(__(reason || "لا توجد خطة صالحة للاعتماد في الحالة الحالية."));
            }
            return false;
        }

        const sourceLabel = source === "Custom" ? __("خطة DXF المرفوعة") : __("خطة النظام الحالية");
        const warning = approvedPlanName(frm)
            ? __("يوجد اعتماد سابق. سيؤدي المتابعة إلى إنشاء اعتماد جديد واستبدال الخطة المعتمدة الحالية.")
            : __("سيتم تثبيت هذه الخطة كنسخة الإنتاج النهائية.");
        const transport = api();
        if (!transport || typeof transport.approve !== "function") return false;

        return new Promise((resolve) => {
            frappe.confirm(
                `${warning}<br><br><b>${sourceLabel}</b>`,
                async () => {
                    try {
                        await transport.approve(frm.doc.name, source);
                        await refreshWorkspaceOwners(frm);
                        frappe.show_alert({ message: __("تم اعتماد خطة القص للإنتاج."), indicator: "green" }, 5);
                        resolve(true);
                    } catch (error) {
                        console.error("Cutting plan approval failed", error);
                        resolve(false);
                        throw error;
                    }
                },
                () => resolve(false)
            );
        });
    }

    function approvalButtonState(frm, button) {
        const source = approvalSource(frm);
        const row = approvalRow(frm, source);
        const allowed = approvalAllowed(frm, source);
        if (button.prop("disabled") === allowed) button.prop("disabled", !allowed);
        button.attr("aria-disabled", allowed ? "false" : "true");
        setTextIfChanged(button, source === "Custom" ? __("اعتماد خطة DXF") : __("اعتماد خطة القص"));
        if (!allowed) {
            button.attr(
                "title",
                source === "System" && row && row.validation && row.validation.needs_recalculation
                    ? __("أعد حساب الخطة قبل اعتمادها")
                    : __("الاعتماد غير متاح في حالة الطلب الحالية أو لا توجد صلاحية")
            );
        } else button.removeAttr("title");
    }

    function installApprovalAction(frm, field) {
        if (!can(frm, "approve_dxf") || !canMutateCurrentStage(frm)) {
            field.$wrapper.find(".dco-approve-cutting-plan").remove();
            return;
        }
        let host = field.$wrapper.find(".dco-plan-actions").first();
        if (!host.length) host = field.$wrapper;
        let button = field.$wrapper.find(".dco-approve-cutting-plan").first();
        if (!button.length) {
            button = $('<button type="button" class="btn btn-success btn-sm dco-approve-cutting-plan"></button>');
            host.append(button);
        }
        approvalButtonState(frm, button);
        const element = button.get(0);
        if (element && !element.__almdinaApprovePlanBound) {
            button.off("click");
            button.on("click.almdinaApprovePlan", (event) => {
                event.preventDefault();
                event.stopImmediatePropagation();
                runApproval(frm);
            });
            element.__almdinaApprovePlanBound = true;
        }
    }

    function bindRecalculationAction(frm, button) {
        if (!button || !button.length) return;
        setTextIfChanged(button, __("إعادة الحساب بالإعدادات الحالية"));
        const allowed = canCalculate(frm);
        if (button.prop("disabled") === allowed) button.prop("disabled", !allowed);
        button.attr("aria-disabled", allowed ? "false" : "true");
        button.attr(
            "title",
            recalculationDisabledReason(frm)
            || __("إعادة حساب خطة القص باستخدام إعدادات Plan Workspace الحالية")
        );
        const element = button.get(0);
        if (element && !element.__almdinaPlanCommandBound) {
            button.off("click");
            button.on("click.almdinaPlanCommand", (event) => {
                event.preventDefault();
                event.stopImmediatePropagation();
                runRecalculation(frm);
            });
            element.__almdinaPlanCommandBound = true;
        }
    }

    function simplifyActions(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;
        if (!workspaceReady(frm)) {
            field.$wrapper.empty();
            return;
        }

        const shell = field.$wrapper.find(".dco-plan-actions-shell").first();
        if (!shell.length) {
            const presenter = window.AlmdinaDoorCuttingPlanUX;
            if (presenter && typeof presenter.refresh === "function") presenter.refresh(frm);
            return;
        }

        const duplicated = field.$wrapper.find(DUPLICATED_ACTIONS);
        if (duplicated.length) duplicated.remove();
        bindRecalculationAction(frm, field.$wrapper.find(".dco-recalculate-plan").first());
        installApprovalAction(frm, field);

        const note = field.$wrapper.find(".dco-plan-note").first();
        if (note.length) {
            const message = can(frm, "edit_optimizer_settings")
                ? "عدّل إعدادات الخطة من «تعديل خطة القص»، احفظها، ثم أعد الحساب. لا تحتاج صلاحية التكلفة أو تعديل الطلب."
                : can(frm, "recalculate_plan")
                    ? "يمكنك إعادة حساب الخطة بالإعدادات الحالية. تغيير الخوارزمية يحتاج صلاحية «تعديل خوارزمية القص»."
                    : "تحتاج صلاحية «إعادة حساب الخطة» لتشغيل محرك خطة القص.";
            setTextIfChanged(note, message);
        }
    }

    function apply(frm) {
        installStyles();
        ensureAdvancedModes(frm);
        applyOptimizerFieldAccess(frm);
        simplifyActions(frm);
    }

    function scheduleSimplify(frm) {
        if (frm.__dcoSimplePlanControlsScheduled) return;
        frm.__dcoSimplePlanControlsScheduled = true;
        const run = () => {
            frm.__dcoSimplePlanControlsScheduled = false;
            simplifyActions(frm);
        };
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "simple-plan-controls", run);
            return;
        }
        requestAnimationFrame(() => {
            if (window.cur_frm === frm) run();
        });
    }

    function observeActions(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        const node = field && field.$wrapper && field.$wrapper[0];
        if (!node || frm.__dcoSimplePlanControlsObserver) return;
        frm.__dcoSimplePlanControlsObserver = new MutationObserver(() => scheduleSimplify(frm));
        frm.__dcoSimplePlanControlsObserver.observe(node, { childList: true, subtree: true });
        const context = documentContext();
        if (context && typeof context.registerObserver === "function") {
            context.registerObserver(frm, "simple-plan-controls-observer", frm.__dcoSimplePlanControlsObserver);
        }
    }

    function refresh(frm) {
        const context = documentContext();
        const token = context && typeof context.capture === "function" ? context.capture(frm) : null;
        const run = () => {
            if (context && !context.isCurrent(frm, token)) return;
            apply(frm);
            observeActions(frm);
        };
        if (context && typeof context.ensureStageContext === "function") {
            context.ensureStageContext(frm).then(run);
            return;
        }
        run();
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        board_description(frm) { refresh(frm); },
        board_length_cm(frm) { refresh(frm); },
        board_width_cm(frm) { refresh(frm); },
    });

    [
        "almdina:permissions-updated",
        "almdina:stage-context-ready",
        "almdina:plan-workspace-updated",
    ].forEach((eventName) => {
        window.addEventListener(eventName, (event) => {
            const frm = eventName === "almdina:stage-context-ready"
                ? event.detail && event.detail.frm
                : window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order" && frm === window.cur_frm) refresh(frm);
        });
    });

    window.AlmdinaPlanControlsUX = Object.freeze({
        apply,
        applyOptimizerFieldAccess,
        canCalculate,
        preparePlanInputs,
        persistPendingOrderInputs,
        runRecalculation,
        runApproval,
        refreshWorkspaceOwners,
    });
})();
