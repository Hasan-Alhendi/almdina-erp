(() => {
    "use strict";

    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const TERMINAL = new Set(["Delivered", "Cancelled"]);
    const CUTTING_OR_LATER = new Set([
        "At Sharyoun",
        "At CNC",
        "At Sanding",
        "Ready for Delivery",
        "Delivered",
        "Cancelled",
        "Completed",
        "Cutting In Progress",
        "Cut Completed",
        "Edge Banding In Progress",
        "Quality Check",
        "Partially Completed",
    ]);
    const EDIT_LABEL = __("تعديل");
    const CONFIRM_EDIT_LABEL = __("اعتماد التعديل");
    const ORDER_INPUT_FIELDS = [
        "customer",
        "order_date",
        "external_reference",
        "order_notes",
        "board_description",
        "board_length_cm",
        "board_width_cm",
        "default_edge_type",
        "edge_color",
        "cutting_cost_per_board_usd",
        "board_rate_usd",
        "kerf_mm",
        "trim_margin_mm",
        "packing_mode",
        "cutting_machine_type",
        "optimization_time_limit_sec",
    ];

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions &&
            (
                typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, capability)
                    : permissions.can(capability)
            )
        );
    }

    function revisionState(frm) {
        return (frm && frm.doc && frm.doc.revision_state) || "Current";
    }

    function isBeforeCutting(status) {
        const normalized = status || "Draft";
        if (TERMINAL.has(normalized)) return false;
        return !CUTTING_OR_LATER.has(normalized);
    }

    function sessionStore() {
        frappe.provide("frappe.almdina");
        if (!frappe.almdina._orderEditSessions) {
            frappe.almdina._orderEditSessions = Object.create(null);
        }
        return frappe.almdina._orderEditSessions;
    }

    function sessionEntry(name) {
        if (!name) return null;
        const store = sessionStore();
        const raw = store[name];
        if (!raw) return null;
        if (raw === true) {
            store[name] = { active: true, recalculated: false };
            return store[name];
        }
        return raw;
    }

    function isEditSessionActive(frm) {
        if (!frm || !frm.doc) return false;
        if (frm.__almdina_edit_session) return true;
        const entry = sessionEntry(frm.doc.name);
        return Boolean(entry && entry.active);
    }

    function setEditSession(frm, active, options = {}) {
        if (!frm) return;
        const enabled = Boolean(active);
        frm.__almdina_edit_session = enabled;
        const name = frm.doc && frm.doc.name;
        if (!name || frm.is_new()) {
            if (!enabled) {
                frm.__almdina_recalc_after_edit = false;
            }
            return;
        }
        if (enabled) {
            let recalculated = false;
            if (options.resetRecalc === true) {
                recalculated = false;
            } else if (options.recalculated === true) {
                recalculated = true;
            } else {
                const previous = sessionEntry(name);
                recalculated = Boolean(previous && previous.recalculated);
            }
            sessionStore()[name] = { active: true, recalculated };
            frm.__almdina_recalc_after_edit = recalculated;
        } else {
            delete sessionStore()[name];
            frm.__almdina_recalc_after_edit = false;
        }
    }

    function markEditSessionRecalculated(frm) {
        if (!frm || !frm.doc || !frm.doc.name || !isEditSessionActive(frm)) return;
        frm.__almdina_recalc_after_edit = true;
        const entry = sessionEntry(frm.doc.name) || { active: true, recalculated: false };
        entry.active = true;
        entry.recalculated = true;
        sessionStore()[frm.doc.name] = entry;
    }

    function invalidateEditSessionRecalculation(frm) {
        if (!frm || !isEditSessionActive(frm)) return;
        frm.__almdina_recalc_after_edit = false;
        frm.doc.plan_needs_recalculation = 1;
        const name = frm.doc && frm.doc.name;
        if (!name) return;
        const entry = sessionEntry(name) || { active: true, recalculated: false };
        entry.active = true;
        entry.recalculated = false;
        sessionStore()[name] = entry;
    }

    function editSessionRecalculated(frm) {
        if (frm && frm.__almdina_recalc_after_edit) return true;
        const entry = frm && frm.doc && sessionEntry(frm.doc.name);
        return Boolean(entry && entry.recalculated);
    }

    function canOfferEditSession(frm) {
        if (!frm || !frm.doc || frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (revisionState(frm) === "Superseded") return false;
        if (!can(frm, "edit_order")) return false;
        return isBeforeCutting(frm.doc.status || "Draft");
    }

    function orderCanEdit(frm) {
        if (!frm || !frm.doc || Number(frm.doc.docstatus || 0) !== 0) return false;
        if (frm.is_new()) return can(frm, "create_order");
        return canOfferEditSession(frm) && isEditSessionActive(frm);
    }

    function planReadyForConfirm(frm) {
        if (!frm || !frm.doc) return false;
        if (!editSessionRecalculated(frm)) return false;
        if (Number(frm.doc.plan_needs_recalculation || 0) === 1) return false;
        if (!frm.doc.cutting_plan_json) return false;
        if (frm.is_dirty && frm.is_dirty()) return false;
        return true;
    }

    function canCreateRevision(frm) {
        if (!frm || frm.is_new() || !can(frm, "create_order_revision")) return false;
        const status = frm.doc.status || "Draft";
        if (DRAFT_LIKE.has(status) || TERMINAL.has(status)) return false;
        return revisionState(frm) !== "Superseded";
    }

    function installEditPolicy() {
        frappe.provide("frappe.almdina");
        frappe.almdina.orderCanEdit = orderCanEdit;
        frappe.almdina.isOrderEditSessionActive = isEditSessionActive;
        frappe.almdina.canOfferOrderEditSession = canOfferEditSession;
        frappe.almdina.markOrderEditSessionRecalculated = markEditSessionRecalculated;
        frappe.almdina.invalidateOrderEditSessionRecalculation = invalidateEditSessionRecalculation;
    }

    function applyEditableFields(frm) {
        const editable = orderCanEdit(frm);
        frm.toggle_enable(ORDER_INPUT_FIELDS, editable);
        if (frm.is_new()) {
            frm.enable_save();
            return;
        }
        if (editable) {
            frm.enable_save();
        } else {
            frm.disable_save();
        }
    }

    function removeEditSessionButtons(frm) {
        frm.remove_custom_button(EDIT_LABEL);
        frm.remove_custom_button(CONFIRM_EDIT_LABEL);
        frm.remove_custom_button(EDIT_LABEL, __("دورة الطلب"));
        frm.remove_custom_button(CONFIRM_EDIT_LABEL, __("دورة الطلب"));
        frm.remove_custom_button(__("تعديل الطلب"));
        frm.remove_custom_button(__("تعديل الطلب"), __("دورة الطلب"));
    }

    function refreshDependentUx(frm) {
        const field = frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        if (field && field.$wrapper) {
            // Bypass the save-render HTML guard so lock/unlock actually replaces
            // disabled inputs on already-entered piece rows.
            field.$wrapper._dcoForceHtmlReplace = true;
        }
        if (typeof frm.trigger === "function") {
            frm.trigger("almdina_edit_session_changed");
            frm.trigger("refresh_plan_controls");
        }
        // Re-render custom HTML UIs after the session gate flips. Do not call
        // refresh_field on pieces_fast_entry: it wipes the operator table.
        if (field && field.$wrapper) {
            field.$wrapper._dcoForceHtmlReplace = true;
        }
        if (
            window.AlmdinaDoorCuttingFastEntry
            && typeof window.AlmdinaDoorCuttingFastEntry.render === "function"
        ) {
            window.AlmdinaDoorCuttingFastEntry.render(frm);
        }
        if (window.AlmdinaDoorCuttingPlanUX && typeof window.AlmdinaDoorCuttingPlanUX.refresh === "function") {
            window.AlmdinaDoorCuttingPlanUX.refresh(frm);
        }
    }

    function enterEditSession(frm) {
        if (!canOfferEditSession(frm)) {
            frappe.msgprint(__("لا يمكن تعديل هذا الطلب بعد بدء مرحلة القص (شريون أو CNC)."));
            return;
        }
        setEditSession(frm, true, { resetRecalc: true });
        // Edits are not confirmed until an explicit recalculation runs in this session.
        frm.doc.plan_needs_recalculation = 1;
        frm.__almdina_recalc_after_edit = false;
        applyEditableFields(frm);
        installEditSessionButtons(frm);
        refreshDependentUx(frm);
        frappe.show_alert({
            message: __("وضع التعديل مفعّل. عدّل الدرف والحقول، ثم أعد حساب الخطة قبل «اعتماد التعديل»."),
            indicator: "blue",
        }, 6);
    }

    function confirmEditSession(frm) {
        if (!planReadyForConfirm(frm)) {
            frappe.msgprint(
                __("لا يمكن اعتماد التعديل قبل إعادة حساب خطة القص بالبيانات الجديدة. احفظ التغييرات إن لزم، ثم اضغط «إعادة الحساب».")
            );
            return;
        }

        // Confirming an edit only locks the form. It never approves the order/plan.
        setEditSession(frm, false);
        applyEditableFields(frm);
        installEditSessionButtons(frm);
        refreshDependentUx(frm);
        frappe.show_alert({
            message: __("تم اعتماد التعديل بعد إعادة الحساب، وأُعيد قفل الحقول. اعتماد الطلب/الخطة للإنتاج يتم بزر منفصل إن لزم."),
            indicator: "green",
        }, 6);
    }

    function installEditSessionButtons(frm) {
        removeEditSessionButtons(frm);
        if (!canOfferEditSession(frm)) return;

        if (isEditSessionActive(frm)) {
            const button = frm.add_custom_button(CONFIRM_EDIT_LABEL, () => confirmEditSession(frm));
            if (button && typeof button.addClass === "function") {
                button.addClass("btn-primary");
            }
            return;
        }

        const button = frm.add_custom_button(EDIT_LABEL, () => enterEditSession(frm));
        if (button && typeof button.addClass === "function") {
            button.addClass("btn-primary");
        }
    }

    function renderRevisionState(frm) {
        const state = revisionState(frm);
        if (state === "Pending Activation") {
            frm.set_intro(
                __("هذه نسخة تعديل غير مفعّلة. يمكن تجهيزها ومراجعتها، لكنها لن تُرسل للإنتاج قبل اعتمادها واستبدال النسخة السابقة بأمان."),
                "orange"
            );
            return;
        }
        if (state === "Superseded") {
            frm.set_intro(
                __("هذه نسخة تاريخية تم استبدالها بنسخة أحدث، وهي للقراءة والتوثيق فقط."),
                "red"
            );
            return;
        }
        if (frm.doc.revision_of) {
            frm.set_intro(
                __("هذه هي النسخة الحالية ضمن سلسلة مراجعات الطلب."),
                "green"
            );
            return;
        }
        if (
            canOfferEditSession(frm)
            && !isEditSessionActive(frm)
            && !DRAFT_LIKE.has(frm.doc.status || "Draft")
        ) {
            frm.set_intro(
                __("الحقول مقفلة. استخدم «تعديل» لتغيير الدرف والبيانات على نفس الطلب قبل القص، ثم أعد الحساب واضغط «اعتماد التعديل»."),
                "blue"
            );
        }
    }

    function createRevision(frm, reason = "") {
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision",
            args: {
                order_name: frm.doc.name,
                reason: String(reason || "").trim(),
            },
            freeze: true,
            freeze_message: __("جاري إنشاء نسخة تعديل مستقلة..."),
        }).then(response => {
            const data = response.message || {};
            if (!data.name) return;
            frappe.show_alert({
                message: data.already_exists
                    ? __("توجد نسخة تعديل مرتبطة بهذا الطلب.")
                    : __("تم إنشاء نسخة مسودة مع الحفاظ على الطلب والخطة الأصلية."),
                indicator: data.already_exists ? "orange" : "green",
            }, 6);
            frappe.set_route("Form", "Door Cutting Order", data.name);
        });
    }

    function openRevision(frm) {
        frappe.prompt(
            [{
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("سبب إنشاء نسخة التعديل (اختياري)"),
                description: __("ينشئ مستندًا مسودة مستقلاً دون تعديل الطلب الحالي مباشرة."),
                reqd: 0,
            }],
            values => createRevision(frm, values.reason),
            __("إنشاء نسخة تعديل"),
            __("إنشاء النسخة المسودة")
        );
    }

    installEditPolicy();
    frappe.almdina.openOrderRevisionDialog = openRevision;
    frappe.almdina.createOrderRevision = createRevision;

    frappe.ui.form.on("Door Cutting Order", {
        onload(frm) {
            // Restore an in-progress edit session for this order after reload/recalc.
            const entry = frm.doc && sessionEntry(frm.doc.name);
            if (entry && entry.active) {
                frm.__almdina_edit_session = true;
                frm.__almdina_recalc_after_edit = Boolean(entry.recalculated);
            } else if (!frm.is_new()) {
                frm.__almdina_edit_session = false;
                frm.__almdina_recalc_after_edit = false;
            }
        },
        refresh(frm) {
            const entry = frm.doc && sessionEntry(frm.doc.name);
            if (entry && entry.active) {
                frm.__almdina_edit_session = true;
                frm.__almdina_recalc_after_edit = Boolean(entry.recalculated);
            } else if (frm.is_new()) {
                frm.__almdina_edit_session = true;
            } else {
                frm.__almdina_edit_session = false;
            }

            applyEditableFields(frm);
            renderRevisionState(frm);
            removeEditSessionButtons(frm);

            frm.remove_custom_button(__("إنشاء نسخة تعديل"), __("دورة الطلب"));

            if (frm.doc.revision_of) {
                frm.add_custom_button(__("فتح الطلب الأصلي"), () => {
                    frappe.set_route("Form", "Door Cutting Order", frm.doc.revision_of);
                }, __("دورة الطلب"));
            }

            if (frm.doc.superseded_by) {
                frm.add_custom_button(__("فتح نسخة التعديل"), () => {
                    frappe.set_route("Form", "Door Cutting Order", frm.doc.superseded_by);
                }, __("دورة الطلب"));
                return;
            }

            installEditSessionButtons(frm);

            if (canCreateRevision(frm) && !canOfferEditSession(frm)) {
                frm.add_custom_button(
                    __("إنشاء نسخة تعديل"),
                    () => openRevision(frm),
                    __("دورة الطلب")
                );
            }

            if (isEditSessionActive(frm)) {
                // After reload_doc (e.g. recalc), re-enable the piece grid.
                requestAnimationFrame(() => refreshDependentUx(frm));
            }
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        if (!canOfferEditSession(frm)) {
            setEditSession(frm, false);
        }
        applyEditableFields(frm);
        installEditSessionButtons(frm);
    });

    window.AlmdinaOrderRevisionUX = Object.freeze({
        canCreateRevision,
        canOfferEditSession,
        createRevision,
        applyImmutableFields: applyEditableFields,
        isEditableDraft: orderCanEdit,
        isEditSessionActive,
        markEditSessionRecalculated,
        invalidateEditSessionRecalculation,
        openRevision,
        enterEditSession,
        confirmEditSession,
    });
})();
