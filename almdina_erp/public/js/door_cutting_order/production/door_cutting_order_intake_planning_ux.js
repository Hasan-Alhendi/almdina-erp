(() => {
    "use strict";

    const DATA_ENTRY = "DATA_ENTRY";
    const READY_TO_DISPATCH = "READY_TO_DISPATCH";
    const INTAKE_STAGES = new Set([DATA_ENTRY, READY_TO_DISPATCH]);
    const INTAKE_ACTION_LABELS = ["إنهاء إدخال البيانات", "تعديل خطة الإرسال"];

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function captureDocumentContext(frm) {
        const context = documentContext();
        if (!context || typeof context.capture !== "function") return null;
        return context.capture(frm);
    }

    function isCurrentDocumentContext(frm, token) {
        const context = documentContext();
        return Boolean(
            token
            && context
            && typeof context.isCurrent === "function"
            && context.isCurrent(frm, token)
        );
    }

    function hasUnsavedChanges(frm) {
        if (!frm || !frm.doc) return false;
        if (typeof frm.is_dirty === "function" && frm.is_dirty()) return true;
        return Boolean(frm.doc.__unsaved);
    }

    function productionStarted(frm) {
        return Boolean(
            frm
            && frm.doc
            && (frm.doc.production_path || frm.doc.current_production_stage)
        );
    }

    function requirePersistedFormState(frm) {
        if (!hasUnsavedChanges(frm)) return true;
        frappe.msgprint(__(
            "احفظ تعديلات الطلب أولًا، ثم أعد إنهاء إدخال البيانات حتى لا تضيع أي تعديلات غير محفوظة."
        ));
        return false;
    }

    function canEditOrder(frm) {
        const context = permissions();
        if (!context) return false;
        if (typeof context.canDocument === "function") {
            return Boolean(context.canDocument(frm, "edit_order"));
        }
        return Boolean(typeof context.can === "function" && context.can("edit_order"));
    }

    function removeLegacyDispatchAction(frm) {
        if (!INTAKE_STAGES.has(String(frm.doc.workflow_stage || ""))) return;
        frm.remove_custom_button(__("إرسال للإنتاج"));
    }

    function removeIntakeActions(frm) {
        INTAKE_ACTION_LABELS.forEach((label) => frm.remove_custom_button(__(label)));
    }

    function workerOptions(workers, routeName) {
        return (workers[routeName] || []).map((worker) => ({
            label: worker.full_name && worker.full_name !== worker.name
                ? `${worker.full_name} — ${worker.name}`
                : worker.name,
            value: worker.name,
        }));
    }

    function routePreview(routes, routeName) {
        const route = routes.find((item) => item.value === routeName) || routes[0];
        if (!route) return "";
        const escape = (value) => frappe.utils.escape_html(String(value || ""));
        const stages = (route.stages || []).map((stage, index) => `
            <span style="display:inline-flex;flex-direction:column;gap:2px;padding:8px 11px;border-radius:12px;background:var(--subtle-fg,#f3f5f7);font-size:12px;font-weight:700">
                <span>${index + 1}. ${escape(stage.department || stage.stage_type)}</span>
                <small style="font-weight:500;color:var(--text-muted,#667085)">${escape(stage.operational_role || "")}</small>
            </span>`).join('<span style="color:var(--text-muted,#98a2b3)">←</span>');
        return `<div dir="rtl" style="padding:12px;border:1px solid var(--border-color,#e5e7eb);border-radius:12px;background:var(--fg-color,#fff)">
            <div style="font-weight:800;margin-bottom:8px">${escape(route.label || route.value)}</div>
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">${stages}</div>
        </div>`;
    }

    function openIntakePlanningDialog(frm) {
        if (!requirePersistedFormState(frm)) return null;

        const documentName = frm.doc.name;
        const optionsToken = captureDocumentContext(frm);
        if (!optionsToken) {
            frappe.msgprint(__("تعذر تثبيت سياق الطلب الحالي. أعد فتح الطلب ثم حاول مرة أخرى."));
            return null;
        }

        return frappe.call({
            method: "almdina_erp.almdina_erp.services.order_intake_service.get_finish_data_entry_options",
            args: { order_name: documentName },
            freeze: true,
            freeze_message: __("جاري تحميل مسارات الإنتاج..."),
        }).then((response) => {
            if (!isCurrentDocumentContext(frm, optionsToken)) return;
            const payload = response.message || {};
            const routes = Array.isArray(payload.routes) ? payload.routes : [];
            const workers = payload.workers || {};
            if (!routes.length) {
                frappe.msgprint(__("لا يوجد مسار إنتاج مفعّل."));
                return;
            }

            const routeOptions = routes.map((route) => ({
                label: `${route.label} · ${route.stage_count || 0} ${__("مراحل")}`,
                value: route.value,
            }));
            const defaultRoute = routes.some((route) => route.value === payload.default_route)
                ? payload.default_route
                : routes[0].value;
            const initialWorkers = workerOptions(workers, defaultRoute);
            const plannedAssignee = String(payload.planned_first_assignee || "");
            const defaultAssignee = initialWorkers.some((worker) => worker.value === plannedAssignee)
                ? plannedAssignee
                : (initialWorkers[0] ? initialWorkers[0].value : "");

            const dialog = new frappe.ui.Dialog({
                title: payload.workflow_stage === READY_TO_DISPATCH
                    ? __("تعديل خطة الإرسال")
                    : __("إنهاء إدخال البيانات"),
                size: "large",
                fields: [
                    {
                        fieldname: "route_name",
                        fieldtype: "Select",
                        label: __("مسار الإنتاج"),
                        options: routeOptions,
                        default: defaultRoute,
                        reqd: 1,
                        onchange() {
                            const routeName = dialog.get_value("route_name");
                            const options = workerOptions(workers, routeName);
                            dialog.set_df_property("assignee", "options", options);
                            dialog.set_value("assignee", options[0] ? options[0].value : "");
                            dialog.fields_dict.route_preview.$wrapper.html(routePreview(routes, routeName));
                        },
                    },
                    { fieldname: "route_preview", fieldtype: "HTML" },
                    {
                        fieldname: "assignee",
                        fieldtype: "Select",
                        label: __("العامل الذي سيستلم أول مرحلة"),
                        options: initialWorkers,
                        default: defaultAssignee,
                        reqd: 1,
                    },
                ],
                primary_action_label: __("حفظ خطة الإرسال"),
                primary_action(values) {
                    if (!isCurrentDocumentContext(frm, optionsToken)) {
                        dialog.hide();
                        return;
                    }
                    if (!requirePersistedFormState(frm)) return;

                    const mutationToken = captureDocumentContext(frm);
                    if (!mutationToken) return;
                    dialog.disable_primary_action();
                    frappe.call({
                        method: "almdina_erp.almdina_erp.services.order_intake_service.finish_data_entry",
                        args: {
                            order_name: documentName,
                            route_name: values.route_name,
                            assignee: values.assignee,
                        },
                        freeze: true,
                        freeze_message: __("جاري حفظ خطة الإرسال..."),
                    }).then(() => {
                        if (!isCurrentDocumentContext(frm, mutationToken)) return;
                        dialog.hide();
                        frappe.show_alert({
                            message: __("تم حفظ خطة الإرسال. الطلب جاهز للإرسال ولم يبدأ الإنتاج بعد."),
                            indicator: "green",
                        });
                        if (hasUnsavedChanges(frm)) {
                            frappe.msgprint(__(
                                "تم حفظ خطة الإرسال، لكن توجد تعديلات محلية أحدث؛ لم يُعد تحميل الطلب حتى لا تضيع."
                            ));
                            return null;
                        }
                        return frm.reload_doc();
                    }).catch(() => {
                        if (isCurrentDocumentContext(frm, mutationToken)) {
                            dialog.enable_primary_action();
                        }
                    });
                },
            });
            dialog.show();
            dialog.fields_dict.route_preview.$wrapper.html(routePreview(routes, defaultRoute));
        });
    }

    function reconcileIntakeActions(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order" || !frm.doc) return false;

        removeIntakeActions(frm);
        removeLegacyDispatchAction(frm);
        if (frm.is_new() || !canEditOrder(frm) || productionStarted(frm)) return false;

        const stage = String(frm.doc.workflow_stage || "");
        if (stage === DATA_ENTRY) {
            frm.add_custom_button(__("إنهاء إدخال البيانات"), () => openIntakePlanningDialog(frm));
            return true;
        }
        if (stage === READY_TO_DISPATCH) {
            frm.add_custom_button(__("تعديل خطة الإرسال"), () => openIntakePlanningDialog(frm));
            return true;
        }
        return false;
    }

    frappe.ui.form.on("Door Cutting Order", { refresh: reconcileIntakeActions });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") {
            reconcileIntakeActions(frm);
        }
    });

    window.AlmdinaOrderIntakePlanningUX = Object.freeze({
        reconcileIntakeActions,
    });
})();
