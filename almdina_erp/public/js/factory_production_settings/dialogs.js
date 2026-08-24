(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsDialogs) return;

    function create(options = {}) {
        const translate = options.translate;
        const escapeHtml = options.escapeHtml;
        if (typeof translate !== "function" || typeof escapeHtml !== "function") {
            throw new Error("Production Settings dialog dependencies are unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);
        const ownedSurfaces = new Map();
        const drafts = new Map();

        function own(surface, draftKey = "") {
            if (surface && typeof surface.hide === "function") {
                ownedSurfaces.set(surface, String(draftKey || ""));
            }
            return surface;
        }

        function restoreDraft(surface, draftKey) {
            if (!drafts.has(draftKey) || !surface || typeof surface.set_values !== "function") return;
            surface.set_values(drafts.get(draftKey));
        }

        function complete(surface, draftKey) {
            drafts.delete(draftKey);
            if (!ownedSurfaces.has(surface)) return;
            ownedSurfaces.delete(surface);
            surface.hide();
        }

        function deactivate() {
            for (const [surface, draftKey] of ownedSurfaces) {
                if (draftKey && typeof surface.get_values === "function") {
                    const values = surface.get_values(true);
                    if (values && typeof values === "object") drafts.set(draftKey, { ...values });
                }
                surface.hide();
            }
            ownedSurfaces.clear();
        }

        function dispose() {
            deactivate();
            drafts.clear();
        }

        function sectionFields(section, current = {}) {
            const values = current.values || current;
            if (section === "cutting") {
                return [
                    { fieldname: "default_packing_mode", fieldtype: "Select", label: t("خوارزمية التوزيع"), options: (current.packing_options || []).join("\n"), default: values.default_packing_mode, reqd: 1 },
                    { fieldname: "default_cutting_machine_type", fieldtype: "Select", label: t("نوع آلة القص"), options: (current.machine_options || []).join("\n"), default: values.default_cutting_machine_type, reqd: 1 },
                    { fieldname: "default_kerf_mm", fieldtype: "Float", label: t("Kerf الافتراضي (مم)"), default: values.default_kerf_mm, reqd: 1 },
                    { fieldname: "default_trim_margin_mm", fieldtype: "Float", label: t("هامش التشذيب (مم)"), default: values.default_trim_margin_mm, reqd: 1 },
                    { fieldname: "default_optimization_time_limit_sec", fieldtype: "Float", label: t("مهلة التحسين (ثانية)"), default: values.default_optimization_time_limit_sec, reqd: 1 },
                    { fieldname: "optimal_search_piece_limit", fieldtype: "Int", label: t("حد القطع للبحث الأمثل"), default: values.optimal_search_piece_limit, reqd: 1 },
                ];
            }
            if (section === "costing") {
                return [
                    { fieldname: "default_cutting_cost_per_board_usd", fieldtype: "Currency", label: t("أجرة القص لكل لوح (USD)"), default: values.default_cutting_cost_per_board_usd, reqd: 1 },
                    { fieldname: "default_special_design_fee_usd", fieldtype: "Currency", label: t("رسم التصميم الخاص / قطعة"), default: values.default_special_design_fee_usd, reqd: 1 },
                    { fieldname: "default_special_cnc_fee_usd", fieldtype: "Currency", label: t("رسم CNC الخاص / قطعة"), default: values.default_special_cnc_fee_usd, reqd: 1 },
                    { fieldname: "default_special_manual_edge_fee_usd", fieldtype: "Currency", label: t("رسم القشاط اليدوي / قطعة"), default: values.default_special_manual_edge_fee_usd, reqd: 1 },
                    { fieldname: "default_special_margin_percent", fieldtype: "Percent", label: t("هامش الدرف الخاصة"), default: values.default_special_margin_percent, reqd: 1 },
                ];
            }
            if (section === "print_identity") {
                return [
                    { fieldname: "print_factory_name", fieldtype: "Data", label: t("اسم المعمل"), default: values.print_factory_name, reqd: 1 },
                    { fieldname: "print_factory_description", fieldtype: "Small Text", label: t("لمحة مختصرة عن المعمل"), default: values.print_factory_description, reqd: 1 },
                    { fieldname: "print_factory_address", fieldtype: "Small Text", label: t("العنوان"), default: values.print_factory_address, reqd: 1 },
                    { fieldname: "print_factory_contacts", fieldtype: "Small Text", label: t("أرقام التواصل"), description: t("سطر مستقل لكل رقم: أرضي / موبايل / واتس اب."), default: values.print_factory_contacts || "" },
                ];
            }
            return [
                { fieldname: "default_production_routing", fieldtype: "Select", label: t("مسار الإنتاج الافتراضي (اختياري)"), options: ["", ...(current.routing_options || [])].join("\n"), default: values.default_production_routing || "", reqd: 0 },
                { fieldname: "allow_stage_override", fieldtype: "Check", label: t("السماح بتجاوز تسلسل المراحل"), default: values.allow_stage_override },
                { fieldname: "allow_unplaced_approval", fieldtype: "Check", label: t("السماح الاستثنائي باعتماد قطع غير موزعة"), default: values.allow_unplaced_approval },
            ];
        }

        function sectionTitle(section) {
            if (section === "cutting") return t("تعديل القص والمحسّن");
            if (section === "costing") return t("تعديل التكلفة الافتراضية");
            if (section === "print_identity") return t("تعديل هوية أوراق الطباعة");
            return t("تعديل ضوابط الإنتاج");
        }

        function openSection(config = {}) {
            const draftKey = `section:${config.section}`;
            const dialog = own(new frappe.ui.Dialog({
                title: sectionTitle(config.section),
                fields: sectionFields(config.section, config.current || {}),
                primary_action_label: t("حفظ التغييرات"),
                primary_action(payload) {
                    const button = dialog.get_primary_btn();
                    button.prop("disabled", true);
                    let action;
                    try {
                        action = config.onSubmit ? config.onSubmit(payload) : Promise.resolve();
                    } catch (error) {
                        action = Promise.reject(error);
                    }
                    Promise.resolve(action)
                        .then(() => {
                            complete(dialog, draftKey);
                        })
                        .catch(error => {
                            if (!ownedSurfaces.has(dialog)) return;
                            const fallback = t("حدث خطأ غير متوقع.");
                            const message = error && error.message ? error.message : fallback;
                            own(frappe.msgprint({
                                title: t("تعذر الحفظ"),
                                message: escapeHtml(message),
                                indicator: "red",
                            }));
                        })
                        .finally(() => {
                            if (ownedSurfaces.has(dialog)) button.prop("disabled", false);
                        });
                },
            }), draftKey);
            restoreDraft(dialog, draftKey);
            dialog.show();
            return dialog;
        }

        function openAudit(initialHtml) {
            const dialog = own(new frappe.ui.Dialog({
                title: t("سجل تغييرات إعدادات المعمل"),
                size: "large",
                fields: [{ fieldname: "audit_html", fieldtype: "HTML" }],
            }));
            const $wrapper = dialog.fields_dict.audit_html.$wrapper;
            $wrapper.html(String(initialHtml || ""));
            dialog.show();
            return Object.freeze({
                dialog,
                setHtml(html) { $wrapper.html(String(html || "")); },
            });
        }

        function showSaved() {
            frappe.show_alert({ message: t("تم تحديث إعدادات المعمل."), indicator: "green" });
        }

        return Object.freeze({
            sectionFields,
            sectionTitle,
            openSection,
            openAudit,
            showSaved,
            deactivate,
            dispose,
        });
    }

    window.AlmdinaFactoryProductionSettingsDialogs = Object.freeze({ create });
})();
