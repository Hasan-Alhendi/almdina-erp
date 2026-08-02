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

    function can(capability) {
        return Boolean(
            window.AlmdinaPermissions &&
            window.AlmdinaPermissions.can(capability)
        );
    }

    function revisionState(frm) {
        return (frm && frm.doc && frm.doc.revision_state) || "Current";
    }

    function isEditableDraft(frm) {
        if (!frm || !frm.doc || Number(frm.doc.docstatus || 0) !== 0) return false;
        if (frm.is_new()) return can("create_order");
        return can("edit_order") && DRAFT_LIKE.has(frm.doc.status || "Draft");
    }

    function canCreateRevision(frm) {
        if (!frm || frm.is_new() || !can("create_order_revision")) return false;
        const status = frm.doc.status || "Draft";
        if (DRAFT_LIKE.has(status) || TERMINAL.has(status)) return false;
        return revisionState(frm) !== "Superseded";
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
                description: __("لن يتم تعديل الطلب التاريخي الأصلي."),
                reqd: 0,
            }],
            values => createRevision(frm, values.reason),
            __("إنشاء نسخة تعديل"),
            __("إنشاء النسخة المسودة")
        );
    }

    installImmutableEditPolicy();
    frappe.almdina.openOrderRevisionDialog = openRevision;
    frappe.almdina.createOrderRevision = createRevision;

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            applyImmutableFields(frm);
            renderRevisionState(frm);

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

            if (canCreateRevision(frm)) {
                frm.add_custom_button(
                    __("إنشاء نسخة تعديل"),
                    () => openRevision(frm),
                    __("دورة الطلب")
                );
            }
        },
    });

    window.AlmdinaOrderRevisionUX = Object.freeze({
        canCreateRevision,
        createRevision,
        isEditableDraft,
        openRevision,
    });
})();
