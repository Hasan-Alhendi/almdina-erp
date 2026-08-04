(() => {
    "use strict";

    if (window.__almdinaOrderActionPermissionGuardLoaded) return;
    window.__almdinaOrderActionPermissionGuardLoaded = true;

    const PLAN_ACTION_SELECTOR = [
        ".dco-recalculate-plan",
        ".dco-auto-pro-plan",
        ".dco-deep-plan",
        ".dco-optimal-plan",
    ].join(",");
    const MODE_ACTION_SELECTOR = [
        ".dco-auto-pro-plan",
        ".dco-deep-plan",
        ".dco-optimal-plan",
    ].join(",");
    const OPTIMIZER_FIELDS = [
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ];
    const MEASUREMENT_PRINT_SELECTOR = [
        ".dco-print-measurements",
        ".dco-entry-window-print",
    ].join(",");
    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    let observerFrame = null;

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function can(frm, capability) {
        const api = permissions();
        if (!api) return false;
        if (frm && typeof api.canDocument === "function") {
            return api.canDocument(frm, capability);
        }
        return typeof api.can === "function" && api.can(capability);
    }

    function orderEditable(frm) {
        if (window.frappe && frappe.almdina && typeof frappe.almdina.orderCanEdit === "function") {
            return Boolean(frappe.almdina.orderCanEdit(frm));
        }
        return Boolean(
            frm
            && frm.doc
            && Number(frm.doc.docstatus || 0) === 0
            && EDITABLE_STATUSES.has(frm.doc.status || "Draft")
        );
    }

    function deny(message) {
        frappe.msgprint(__(message));
    }

    function protectPlanActions(frm) {
        const root = frm && frm.wrapper && (frm.wrapper[0] || frm.wrapper);
        if (!root) return;

        const mayRecalculate = can(frm, "recalculate_plan");
        const mayEditOptimizer = can(frm, "edit_optimizer_settings");
        const editable = orderEditable(frm);
        root.querySelectorAll(PLAN_ACTION_SELECTOR).forEach(button => {
            const modeButton = button.matches(MODE_ACTION_SELECTOR);
            const allowed = editable && mayRecalculate && (!modeButton || mayEditOptimizer);
            if (button.disabled === allowed) button.disabled = !allowed;
            const ariaValue = allowed ? "false" : "true";
            if (button.getAttribute("aria-disabled") !== ariaValue) {
                button.setAttribute("aria-disabled", ariaValue);
            }
            if (!allowed) {
                button.title = !editable
                    ? "لا يمكن تعديل خطة طلب معتمد أو دخل الإنتاج"
                    : modeButton && !mayEditOptimizer
                        ? "لا تملك صلاحية تعديل إعدادات المحسّن"
                        : "لا تملك صلاحية إعادة حساب خطة القص";
            } else if (button.title && button.title.includes("صلاحية")) {
                button.removeAttribute("title");
            }
        });

        const desiredReadOnly = mayEditOptimizer && editable ? 0 : 1;
        OPTIMIZER_FIELDS.forEach(fieldname => {
            const field = frm.fields_dict && frm.fields_dict[fieldname];
            if (!field || !field.df) return;
            if (Number(field.df.read_only || 0) !== desiredReadOnly) {
                frm.set_df_property(fieldname, "read_only", desiredReadOnly);
            }
        });
    }

    function protectMeasurementPrint(frm) {
        const allowed = can(frm, "print_measurements");
        document.querySelectorAll(MEASUREMENT_PRINT_SELECTOR).forEach(button => {
            if (allowed) {
                if (button.hidden) button.hidden = false;
                button.removeAttribute("aria-hidden");
                return;
            }
            if (!button.hidden) button.hidden = true;
            if (button.getAttribute("aria-hidden") !== "true") {
                button.setAttribute("aria-hidden", "true");
            }
        });
    }

    function protectSpecialDrawingEditor(frm) {
        const editor = window.AlmdinaSpecialShapeEditor;
        if (!editor || editor.__almdinaPermissionGuarded || typeof editor.open !== "function") return;

        const originalOpen = editor.open.bind(editor);
        editor.open = (targetFrm, row, options = {}) => {
            const activeFrm = targetFrm || frm;
            const readOnly = Boolean(options && options.readOnly);
            if (readOnly || can(activeFrm, "edit_special_drawing")) {
                return originalOpen(activeFrm, row, options);
            }
            if (can(activeFrm, "view_drawing_workspace")) {
                return originalOpen(activeFrm, row, { ...options, readOnly: true });
            }
            deny("ليس لديك صلاحية فتح مساحة رسم الدرفة الخاصة.");
            return undefined;
        };
        editor.__almdinaPermissionGuarded = true;
    }

    function protectMeasurementApi(frm) {
        const actions = window.AlmdinaMeasurementActions;
        if (!actions || actions.__almdinaPermissionGuarded || typeof actions.print !== "function") return;
        const originalPrint = actions.print.bind(actions);
        actions.print = targetFrm => {
            const active = targetFrm || frm || window.cur_frm;
            if (!can(active, "print_measurements")) {
                deny("ليس لديك صلاحية طباعة القياسات.");
                return false;
            }
            return originalPrint(active);
        };
        actions.__almdinaPermissionGuarded = true;
    }

    function apply(frm = window.cur_frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        protectPlanActions(frm);
        protectMeasurementPrint(frm);
        protectSpecialDrawingEditor(frm);
        protectMeasurementApi(frm);
    }

    function bindCaptureGuard(frm) {
        const root = frm && frm.wrapper && (frm.wrapper[0] || frm.wrapper);
        if (!root || root.__almdinaActionPermissionCaptureBound) return;
        root.__almdinaActionPermissionCaptureBound = true;
        root.addEventListener("click", event => {
            const planButton = event.target.closest && event.target.closest(PLAN_ACTION_SELECTOR);
            if (planButton && root.contains(planButton)) {
                if (!can(frm, "recalculate_plan")) {
                    event.preventDefault();
                    event.stopPropagation();
                    event.stopImmediatePropagation();
                    deny("ليس لديك صلاحية إعادة حساب خطة القص.");
                    return;
                }
                if (planButton.matches(MODE_ACTION_SELECTOR) && !can(frm, "edit_optimizer_settings")) {
                    event.preventDefault();
                    event.stopPropagation();
                    event.stopImmediatePropagation();
                    deny("ليس لديك صلاحية تغيير إعدادات المحسّن.");
                }
            }
        }, true);
    }

    function bindGlobalPrintGuard() {
        if (document.__almdinaMeasurementPrintPermissionBound) return;
        document.__almdinaMeasurementPrintPermissionBound = true;
        document.addEventListener("click", event => {
            const button = event.target.closest && event.target.closest(MEASUREMENT_PRINT_SELECTOR);
            if (!button) return;
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order" && can(frm, "print_measurements")) return;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            deny("ليس لديك صلاحية طباعة القياسات.");
        }, true);
    }

    function schedule(frm) {
        bindCaptureGuard(frm);
        bindGlobalPrintGuard();
        apply(frm);
        requestAnimationFrame(() => apply(frm));
        [100, 350, 900].forEach(delay => setTimeout(() => apply(frm), delay));
    }

    function scheduleObserverApply() {
        if (observerFrame !== null) return;
        observerFrame = requestAnimationFrame(() => {
            observerFrame = null;
            apply(window.cur_frm);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => schedule(window.cur_frm));

    const observer = new MutationObserver(scheduleObserverApply);
    observer.observe(document.documentElement, { childList: true, subtree: true });
})();
