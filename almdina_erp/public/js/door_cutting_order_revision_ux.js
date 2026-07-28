(() => {
    "use strict";

    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const TERMINAL = new Set(["Delivered", "Cancelled"]);
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

    function hasRole(role) {
        const roles = frappe.user_roles || [];
        return roles.includes("System Manager") || roles.includes(role);
    }

    function revisionState(frm) {
        return (frm && frm.doc && frm.doc.revision_state) || "Current";
    }

    function isEditableDraft(frm) {
        return Boolean(
            frm && frm.doc && frm.doc.docstatus === 0 && DRAFT_LIKE.has(frm.doc.status || "Draft")
        );
    }

    function canCreateRevision(frm) {
        if (!frm || frm.is_new()) return false;
        const status = frm.doc.status || "Draft";
        if (DRAFT_LIKE.has(status) || TERMINAL.has(status)) return false;
        if (revisionState(frm) === "Superseded") return false;
        return hasRole("Order Entry") || hasRole("Production Manager");
    }

    function installImmutableEditPolicy() {
        frappe.provide("frappe.almdina");
        frappe.almdina.orderCanEdit = isEditableDraft;
    }

    function applyImmutableFields(frm) {
        frm.toggle_enable(ORDER_INPUT_FIELDS, isEditableDraft(frm));
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
                __("هذه نسخة تاريخية تم استبدالها بنسخة أحدث، وهي للقراءة والتوثيق فقط ولا يمكن إرسالها للإنتاج."),
                "red"
            );
            return;
        }
        if (frm.doc.revision_of) {
            frm.set_intro(
                __("هذه هي النسخة الحالية المفعّلة ضمن سلسلة مراجعات الطلب."),
                "green"
            );
        }
    }

    function openRevision(frm) {
        frappe.prompt(
            [{
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("سبب إعادة الطلب للتعديل"),
                description: __("سيُحفظ السبب في سجل النسخة الجديدة، ولن يتم تعديل الطلب التاريخي الأصلي."),
                reqd: 1,
            }],
            values => {
                const reason = String(values.reason || "").trim();
                if (!reason) {
                    frappe.msgprint(__("اكتب سبب إعادة الطلب للتعديل."));
                    return;
                }
                return frappe.call({
                    method: "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision",
                    args: { order_name: frm.doc.name, reason },
                    freeze: true,
                    freeze_message: __("جاري إنشاء نسخة تعديل مستقلة..."),
                }).then(r => {
                    const data = r.message || {};
                    if (!data.name) return;
                    frappe.show_alert({
                        message: data.already_exists
                            ? __("توجد نسخة تعديل مرتبطة بهذا الطلب.")
                            : __("تم إنشاء نسخة مسودة للتعديل مع الحفاظ على الطلب والخطة الأصلية."),
                        indicator: data.already_exists ? "orange" : "green",
                    });
                    frappe.set_route("Form", "Door Cutting Order", data.name);
                });
            },
            __("إعادة الطلب للتعديل"),
            __("إنشاء النسخة المسودة")
        );
    }

    function installLegacyReturnButtonGuard(frm) {
        const pageRoot = frm.page && frm.page.wrapper && (frm.page.wrapper[0] || frm.page.wrapper);
        const root = pageRoot && pageRoot.addEventListener ? pageRoot : document;
        if (root._dcoRevisionReturnButtonGuard) return;

        root._dcoRevisionReturnButtonGuard = true;
        root.addEventListener("click", event => {
            const button = event.target && event.target.closest
                ? event.target.closest("button,.btn")
                : null;
            if (!button) return;
            if (root !== document && !root.contains(button)) return;
            const label = String(button.textContent || "").replace(/\s+/g, " ").trim();
            if (!label.includes(__("إعادة للمسودة")) && !label.includes("إعادة للمسودة")) return;

            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            openRevision(frm);
        }, true);
    }

    installImmutableEditPolicy();
    frappe.almdina.openOrderRevisionDialog = openRevision;

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            applyImmutableFields(frm);
            renderRevisionState(frm);
            installLegacyReturnButtonGuard(frm);
            frm.remove_custom_button(__("إعادة للمسودة"), __("دورة الطلب"));

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

            if (canCreateRevision(frm)) {
                frm.add_custom_button(__("إنشاء نسخة تعديل"), () => openRevision(frm), __("دورة الطلب"));
            }
        },
    });
})();
