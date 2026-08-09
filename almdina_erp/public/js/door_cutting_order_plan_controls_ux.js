(() => {
    "use strict";

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

    const RECALCULATE_METHOD =
        "almdina_erp.almdina_erp.services.order_plan_permission_service.recalculate_order";
    const APPROVE_METHOD =
        "almdina_erp.almdina_erp.services.drawing_approval_service.approve_production_dxf";

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function setTextIfChanged(target, value) {
        if (!target || !target.length) return;
        if (String(target.text() || "") !== String(value || "")) {
            target.text(value);
        }
    }

    function installStyles() {
        if (document.getElementById("dco-simple-plan-controls-css")) return;
        $("head").append(`
            <style id="dco-simple-plan-controls-css">
                [data-fieldname="plan_control_actions"] .dco-plan-actions {
                    display:flex !important;
                    align-items:center !important;
                    justify-content:flex-start !important;
                    gap:8px !important;
                    flex-wrap:wrap !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-document-actions {
                    display:flex !important;
                    align-items:center !important;
                    gap:8px !important;
                    flex-wrap:wrap !important;
                }
                [data-fieldname="plan_control_actions"] .dco-recalculate-plan,
                [data-fieldname="plan_control_actions"] .dco-approve-cutting-plan {
                    min-width:210px;
                    min-height:40px !important;
                    font-weight:850 !important;
                    border-radius:10px !important;
                }
                [data-fieldname="plan_control_actions"] .dco-print-cutting-plan,
                [data-fieldname="plan_control_actions"] .dco-export-dxf,
                [data-fieldname="plan_control_actions"] .dco-upload-dxf-plan {
                    min-height:36px !important;
                    border-radius:10px !important;
                    font-weight:800 !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-actions-title {
                    margin-bottom:10px !important;
                }
                @media (max-width:560px) {
                    [data-fieldname="plan_control_actions"] .dco-recalculate-plan,
                    [data-fieldname="plan_control_actions"] .dco-approve-cutting-plan,
                    [data-fieldname="plan_control_actions"] .dco-print-cutting-plan,
                    [data-fieldname="plan_control_actions"] .dco-export-dxf,
                    [data-fieldname="plan_control_actions"] .dco-upload-dxf-plan {
                        width:100%;
                        min-width:0;
                    }
                }
            </style>
        `);
    }

    function ensureAdvancedModes(frm) {
        const field = frm.fields_dict && frm.fields_dict.packing_mode;
        if (!field) return;

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
            if (typeof field.set_options === "function") {
                field.set_options(options);
            } else if (typeof field.refresh === "function") {
                field.refresh();
            }
        }

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

        if (String(input.val() || "") !== String(frm.doc.packing_mode || "Auto")) {
            input.val(frm.doc.packing_mode || "Auto");
        }
    }

    function applyOptimizerFieldAccess(frm) {
        const editable = Boolean(
            can(frm, "edit_optimizer_settings")
            && !frm.is_new()
            && !frm.doc.approved_plan
        );
        const desiredReadOnly = editable ? 0 : 1;
        OPTIMIZER_FIELDS.forEach((fieldname) => {
            const field = frm.fields_dict && frm.fields_dict[fieldname];
            if (!field || !field.df) return;
            if (Number(field.df.read_only || 0) !== desiredReadOnly) {
                frm.set_df_property(fieldname, "read_only", desiredReadOnly);
            }
        });
    }

    function optimizerArgs(frm) {
        return {
            order_name: frm.doc.name,
            packing_mode: frm.doc.packing_mode,
            cutting_machine_type: frm.doc.cutting_machine_type,
            kerf_mm: frm.doc.kerf_mm,
            trim_margin_mm: frm.doc.trim_margin_mm,
            optimization_time_limit_sec: frm.doc.optimization_time_limit_sec,
        };
    }

    function canCalculate(frm) {
        return Boolean(
            frm
            && !frm.is_new()
            && !frm.doc.approved_plan
            && can(frm, "recalculate_plan")
        );
    }

    function recalculationDisabledReason(frm) {
        if (frm.is_new()) return __("احفظ الطلب أولًا قبل حساب خطة القص.");
        if (frm.doc.approved_plan) return __("الخطة معتمدة ومقفلة ولا يمكن إعادة حسابها.");
        if (!can(frm, "recalculate_plan")) return __("تحتاج صلاحية «إعادة حساب الخطة» لتشغيل المحرك.");
        return "";
    }

    async function preparePlanInputs(frm) {
        const compatibility = window.AlmdinaTextBoardPlanUX;
        if (compatibility && typeof compatibility.preparePlanInputs === "function") {
            return Boolean(await compatibility.preparePlanInputs(frm));
        }

        const boardUX = window.AlmdinaBoardTextUX;
        if (boardUX && typeof boardUX.syncInputs === "function") {
            await boardUX.syncInputs(frm);
        }
        if (!boardUX || !boardUX.canCalculatePlan(frm)) {
            frappe.msgprint(__("أدخل صنف اللوح ومقاساته وقياسًا واحدًا صحيحًا على الأقل قبل حساب خطة القص."));
            return false;
        }
        return true;
    }

    async function runRecalculation(frm) {
        if (!canCalculate(frm)) {
            frappe.msgprint(recalculationDisabledReason(frm));
            return false;
        }
        if (!(await preparePlanInputs(frm))) return false;

        try {
            await frappe.call({
                method: RECALCULATE_METHOD,
                args: optimizerArgs(frm),
                freeze: true,
                freeze_message: __("جاري إعادة حساب خطة القص..."),
            });
            frappe.show_alert({ message: __("تم تحديث خطة القص والنتائج."), indicator: "green" }, 4);
            await frm.reload_doc();
            return true;
        } catch (error) {
            console.error("Cutting plan recalculation failed", error);
            throw error;
        }
    }

    function parsePlan(raw) {
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        try {
            return JSON.parse(raw);
        } catch (error) {
            return null;
        }
    }

    function hasPlan(raw) {
        const plan = parsePlan(raw);
        return Boolean(plan && Array.isArray(plan.sheets) && plan.sheets.length);
    }

    function atDrawing(frm) {
        return Boolean(
            frm.doc.status === "At Drawing"
            || (frm.doc.production_path === "Drawing" && frm.doc.current_department === "رسم")
        );
    }

    function approvalSource(frm) {
        const requested = frm.__almdina_active_plan_tab === "Custom" ? "Custom" : "System";
        if (
            requested === "Custom"
            && frm.doc.production_dxf
            && hasPlan(frm.doc.custom_plan_json)
        ) {
            return "Custom";
        }
        return "System";
    }

    function hasApprovalPlan(frm, source) {
        if (source === "Custom") {
            return Boolean(frm.doc.production_dxf && hasPlan(frm.doc.custom_plan_json));
        }
        return hasPlan(frm.doc.system_plan_json) || hasPlan(frm.doc.cutting_plan_json);
    }

    function runApproval(frm) {
        const source = approvalSource(frm);
        if (!can(frm, "approve_dxf")) {
            frappe.msgprint(__("ليست لديك صلاحية اعتماد خطة القص."));
            return;
        }
        if (!atDrawing(frm)) {
            frappe.msgprint(__("اعتماد خطة القص متاح فقط عندما يكون الطلب في مرحلة الرسم."));
            return;
        }
        if (!hasApprovalPlan(frm, source)) {
            frappe.msgprint(__("لا توجد خطة صالحة للاعتماد."));
            return;
        }
        if (source === "System" && Number(frm.doc.plan_needs_recalculation || 0) === 1) {
            frappe.msgprint(__("أعد حساب خطة القص وراجع النتيجة الجديدة قبل الاعتماد."));
            return;
        }

        const sourceLabel = source === "Custom" ? __("خطة DXF المرفوعة") : __("خطة النظام الحالية");
        const warning = frm.doc.approved_plan
            ? __("يوجد اعتماد سابق. سيؤدي المتابعة إلى إنشاء اعتماد جديد واستبدال الخطة المعتمدة الحالية.")
            : __("سيتم تثبيت هذه الخطة كنسخة الإنتاج النهائية.");
        frappe.confirm(
            `${warning}<br><br><b>${sourceLabel}</b>`,
            () => frappe.call({
                method: APPROVE_METHOD,
                args: { order_name: frm.doc.name, plan_source: source },
                freeze: true,
                freeze_message: __("جاري اعتماد خطة القص..."),
            }).then(() => {
                frappe.show_alert({ message: __("تم اعتماد خطة القص للإنتاج."), indicator: "green" }, 5);
                return frm.reload_doc();
            })
        );
    }

    function approvalButtonState(frm, button) {
        const source = approvalSource(frm);
        const allowed = Boolean(
            can(frm, "approve_dxf")
            && !frm.is_new()
            && atDrawing(frm)
            && hasApprovalPlan(frm, source)
            && !(source === "System" && Number(frm.doc.plan_needs_recalculation || 0) === 1)
        );
        if (button.prop("disabled") === allowed) button.prop("disabled", !allowed);
        button.attr("aria-disabled", allowed ? "false" : "true");
        setTextIfChanged(
            button,
            source === "Custom" ? __("اعتماد خطة DXF") : __("اعتماد خطة القص")
        );
        if (!allowed) {
            button.attr(
                "title",
                Number(frm.doc.plan_needs_recalculation || 0) === 1
                    ? __("أعد حساب الخطة قبل اعتمادها")
                    : __("الاعتماد غير متاح في حالة الطلب الحالية أو لا توجد صلاحية")
            );
        } else {
            button.removeAttr("title");
        }
    }

    function installApprovalAction(frm, field) {
        if (!can(frm, "approve_dxf")) {
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
        const reason = recalculationDisabledReason(frm);
        button.attr(
            "title",
            reason || __("إعادة حساب خطة القص باستخدام الخوارزمية والماكينة والهامش المحددة حاليًا")
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

        const duplicated = field.$wrapper.find(DUPLICATED_ACTIONS);
        if (duplicated.length) duplicated.remove();

        bindRecalculationAction(
            frm,
            field.$wrapper.find(".dco-recalculate-plan").first()
        );
        installApprovalAction(frm, field);

        const note = field.$wrapper.find(".dco-plan-note").first();
        if (note.length) {
            const message = can(frm, "edit_optimizer_settings")
                ? "يمكنك تغيير الخوارزمية وإعدادات المحسّن ثم إعادة الحساب. لا تحتاج هذه العملية إلى صلاحية التكلفة أو تعديل الطلب."
                : can(frm, "recalculate_plan")
                    ? "يمكنك إعادة حساب الخطة بالإعدادات الحالية. تغيير الخوارزمية يحتاج صلاحية «تعديل إعدادات المحسّن»."
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
        requestAnimationFrame(() => {
            frm.__dcoSimplePlanControlsScheduled = false;
            simplifyActions(frm);
        });
    }

    function observeActions(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        const node = field && field.$wrapper && field.$wrapper[0];
        if (!node || frm.__dcoSimplePlanControlsObserver) return;

        frm.__dcoSimplePlanControlsObserver = new MutationObserver(() => {
            scheduleSimplify(frm);
        });
        frm.__dcoSimplePlanControlsObserver.observe(node, { childList: true, subtree: true });
    }

    function refresh(frm) {
        apply(frm);
        observeActions(frm);
        requestAnimationFrame(() => apply(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        packing_mode(frm) { refresh(frm); },
        cutting_machine_type(frm) { refresh(frm); },
        kerf_mm(frm) { refresh(frm); },
        trim_margin_mm(frm) { refresh(frm); },
        optimization_time_limit_sec(frm) { refresh(frm); },
        board_description(frm) { refresh(frm); },
        board_length_cm(frm) { refresh(frm); },
        board_width_cm(frm) { refresh(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") refresh(frm);
    });

    window.AlmdinaPlanControlsUX = Object.freeze({
        apply,
        canCalculate,
        preparePlanInputs,
        runRecalculation,
    });
})();
