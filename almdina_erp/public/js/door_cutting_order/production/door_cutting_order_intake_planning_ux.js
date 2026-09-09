(() => {
    "use strict";

    const DATA_ENTRY = "DATA_ENTRY";
    const READY_TO_DISPATCH = "READY_TO_DISPATCH";
    const DISPATCH_CAPABILITY = "dispatch_order";
    const INTAKE_STAGES = new Set([DATA_ENTRY, READY_TO_DISPATCH]);
    const INTAKE_ACTION_LABELS = [
        "إنهاء إدخال البيانات",
        "تعديل خطة الإرسال",
        "إرسال للإنتاج",
    ];
    const PLAN_SUMMARY_CLASS = "almadina-dispatch-plan-summary";

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
            "احفظ تعديلات الطلب أولًا، ثم أعد المحاولة حتى لا تضيع أي تعديلات غير محفوظة."
        ));
        return false;
    }

    function canDocument(frm, capability) {
        const context = permissions();
        if (!context) return false;
        if (typeof context.canDocument === "function") {
            return Boolean(context.canDocument(frm, capability));
        }
        return Boolean(typeof context.can === "function" && context.can(capability));
    }

    function canEditOrder(frm) {
        return canDocument(frm, "edit_order");
    }

    function canDispatchOrder(frm) {
        return canDocument(frm, DISPATCH_CAPABILITY);
    }

    function canShowIntakeEditor(frm) {
        return !(frm.is_new() || !canEditOrder(frm) || productionStarted(frm));
    }

    function removeLegacyDispatchAction(frm) {
        if (!INTAKE_STAGES.has(String(frm.doc.workflow_stage || ""))) return;
        frm.remove_custom_button(__("إرسال للإنتاج"));
    }

    function removeIntakeActions(frm) {
        INTAKE_ACTION_LABELS.forEach((label) => frm.remove_custom_button(__(label)));
    }

    function escapeHtml(value) {
        return frappe.utils.escape_html(String(value || ""));
    }

    function routeStagesHtml(route) {
        return (route && Array.isArray(route.stages) ? route.stages : []).map((stage, index) => `
            <span style="display:inline-flex;flex-direction:column;gap:2px;padding:8px 11px;border-radius:12px;background:var(--subtle-fg,#f3f5f7);font-size:12px;font-weight:700">
                <span>${index + 1}. ${escapeHtml(stage.department || stage.stage_type)}</span>
                <small style="font-weight:500;color:var(--text-muted,#667085)">${escapeHtml(stage.operational_role || "")}</small>
            </span>`).join('<span style="color:var(--text-muted,#98a2b3)">←</span>');
    }

    function routePreview(routes, routeName) {
        const route = routes.find((item) => item.value === routeName) || routes[0];
        if (!route) return "";
        return `<div dir="rtl" style="padding:12px;border:1px solid var(--border-color,#e5e7eb);border-radius:12px;background:var(--fg-color,#fff)">
            <div style="font-weight:800;margin-bottom:8px">${escapeHtml(route.label || route.value)}</div>
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">${routeStagesHtml(route)}</div>
        </div>`;
    }

    function dispatchPlanHtml(payload, { compact = false } = {}) {
        const route = payload.route || {};
        const first = route.first_stage || {};
        const padding = compact ? "12px" : "14px";
        return `<div dir="rtl" style="padding:${padding};border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff);box-shadow:0 1px 2px rgba(16,24,40,.04)">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:10px">
                <strong style="font-size:14px">${__("خطة الإرسال الحالية")}</strong>
                <span style="font-size:12px;color:var(--text-muted,#667085)">${__("لم يبدأ الإنتاج بعد")}</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px 14px;margin-bottom:10px">
                <div><small style="color:var(--text-muted,#667085)">${__("مسار الإنتاج")}</small><div style="font-weight:700">${escapeHtml(route.label || route.value || payload.planned_production_route)}</div></div>
                <div><small style="color:var(--text-muted,#667085)">${__("العامل الأول")}</small><div style="font-weight:700">${escapeHtml(payload.planned_first_assignee)}</div></div>
                <div><small style="color:var(--text-muted,#667085)">${__("المرحلة الأولى")}</small><div style="font-weight:700">${escapeHtml(first.department || first.stage_type)}</div></div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">${routeStagesHtml(route)}</div>
        </div>`;
    }

    function dispatchPlanHost(frm) {
        const field = frm.fields_dict && frm.fields_dict.shop_floor_section;
        if (!field || !field.$wrapper || !field.$wrapper.length) return null;
        let host = field.$wrapper.find(`.${PLAN_SUMMARY_CLASS}`);
        if (!host.length) {
            host = $(`<div class="${PLAN_SUMMARY_CLASS}" style="margin:10px 0 14px"></div>`);
            field.$wrapper.append(host);
        }
        return host;
    }

    function clearDispatchPlanSummary(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.shop_floor_section;
        if (!field || !field.$wrapper) return;
        field.$wrapper.find(`.${PLAN_SUMMARY_CLASS}`).remove();
    }

    function fetchPlannedDispatchContext(frm, token, { freeze = false } = {}) {
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.planned_dispatch_service.get_planned_dispatch_context",
            args: { order_name: frm.doc.name },
            freeze,
            freeze_message: freeze ? __("جاري التحقق من خطة الإرسال...") : undefined,
        }).then((response) => {
            if (!isCurrentDocumentContext(frm, token)) return null;
            return response.message || null;
        });
    }

    function renderReadyDispatchPlan(frm) {
        if (
            !frm
            || !frm.doc
            || String(frm.doc.workflow_stage || "") !== READY_TO_DISPATCH
            || productionStarted(frm)
        ) {
            clearDispatchPlanSummary(frm);
            return null;
        }
        const token = captureDocumentContext(frm);
        if (!token) return null;
        return fetchPlannedDispatchContext(frm, token).then((payload) => {
            if (!payload || !isCurrentDocumentContext(frm, token)) return;
            const host = dispatchPlanHost(frm);
            if (host) host.html(dispatchPlanHtml(payload));
        }).catch(() => {
            if (!isCurrentDocumentContext(frm, token)) return;
            const host = dispatchPlanHost(frm);
            if (!host) return;
            host.html(`<div dir="rtl" style="padding:12px;border:1px solid var(--border-color,#e5e7eb);border-radius:12px;color:var(--text-muted,#667085)">
                ${__("تعذر التحقق من خطة الإرسال الحالية. استخدم «تعديل خطة الإرسال» ثم أعد المحاولة.")}
            </div>`);
        });
    }

    function workerOptions(workers, routeName) {
        return (workers[routeName] || []).map((worker) => ({
            label: worker.full_name && worker.full_name !== worker.name
                ? `${worker.full_name} — ${worker.name}`
                : worker.name,
            value: worker.name,
        }));
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

    function openDispatchConfirmation(frm) {
        if (!requirePersistedFormState(frm)) return null;
        const optionsToken = captureDocumentContext(frm);
        if (!optionsToken) {
            frappe.msgprint(__("تعذر تثبيت سياق الطلب الحالي. أعد فتح الطلب ثم حاول مرة أخرى."));
            return null;
        }

        return fetchPlannedDispatchContext(frm, optionsToken, { freeze: true }).then((payload) => {
            if (!payload || !isCurrentDocumentContext(frm, optionsToken)) return;
            let dispatching = false;
            const dialog = new frappe.ui.Dialog({
                title: __("تأكيد الإرسال للإنتاج"),
                size: "large",
                fields: [
                    { fieldname: "plan", fieldtype: "HTML" },
                ],
                primary_action_label: __("تأكيد الإرسال للإنتاج"),
                primary_action() {
                    if (dispatching || !isCurrentDocumentContext(frm, optionsToken)) {
                        dialog.hide();
                        return;
                    }
                    if (!requirePersistedFormState(frm)) return;

                    const mutationToken = captureDocumentContext(frm);
                    if (!mutationToken) return;
                    dispatching = true;
                    dialog.disable_primary_action();
                    frappe.call({
                        method: "almdina_erp.almdina_erp.services.planned_dispatch_service.dispatch_planned_order",
                        args: { order_name: frm.doc.name },
                        freeze: true,
                        freeze_message: __("جاري إرسال الطلب للإنتاج..."),
                    }).then(() => {
                        if (!isCurrentDocumentContext(frm, mutationToken)) return;
                        dialog.hide();
                        frappe.show_alert({
                            message: __("تم إرسال الطلب للإنتاج وإسناد المرحلة الأولى بنجاح."),
                            indicator: "green",
                        });
                        if (hasUnsavedChanges(frm)) {
                            frappe.msgprint(__(
                                "تم الإرسال على الخادم، لكن توجد تعديلات محلية أحدث؛ لم يُعد تحميل الطلب حتى لا تضيع."
                            ));
                            return null;
                        }
                        return frm.reload_doc();
                    }).catch(() => {
                        dispatching = false;
                        if (isCurrentDocumentContext(frm, mutationToken)) {
                            dialog.enable_primary_action();
                        }
                    });
                },
            });
            dialog.show();
            dialog.fields_dict.plan.$wrapper.html(dispatchPlanHtml(payload, { compact: true }));
        });
    }

    function reconcileIntakeActions(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order" || !frm.doc) return false;

        removeIntakeActions(frm);
        removeLegacyDispatchAction(frm);

        const stage = String(frm.doc.workflow_stage || "");
        if (stage !== READY_TO_DISPATCH) clearDispatchPlanSummary(frm);
        if (frm.is_new() || productionStarted(frm)) return false;

        if (stage === DATA_ENTRY) {
            if (!canShowIntakeEditor(frm)) return false;
            frm.add_custom_button(__("إنهاء إدخال البيانات"), () => openIntakePlanningDialog(frm));
            return true;
        }
        if (stage === READY_TO_DISPATCH) {
            renderReadyDispatchPlan(frm);
            let visible = false;
            if (canEditOrder(frm)) {
                frm.add_custom_button(__("تعديل خطة الإرسال"), () => openIntakePlanningDialog(frm));
                visible = true;
            }
            if (canDispatchOrder(frm)) {
                frm.add_custom_button(__("إرسال للإنتاج"), () => openDispatchConfirmation(frm));
                visible = true;
            }
            return visible;
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
