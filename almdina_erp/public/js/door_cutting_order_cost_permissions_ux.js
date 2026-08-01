(() => {
    "use strict";

    const ORDER_COST_FIELDS = [
        "board_rate_usd",
        "cutting_cost_per_board_usd",
        "mdf_cost_usd",
        "cutting_cost_usd",
        "edge_cost_usd",
        "total_cost_usd",
        "special_shapes_baseline_cost_usd",
        "special_shapes_estimated_total_usd",
        "special_shapes_final_total_usd",
        "customer_quote_total_usd",
        "customer_quote_status",
        "material_variance_cost_usd",
        "internal_loss_cost_usd",
        "actual_cost_usd",
    ];
    const PIECE_COST_FIELDS = [
        "edge_long_rate_usd",
        "edge_width_rate_usd",
        "edge_long_cost_usd",
        "edge_width_cost_usd",
        "edge_cost_usd",
        "edge_rate_usd",
        "special_shape_estimated_unit_price_usd",
        "special_shape_custom_unit_price_usd",
        "special_shape_final_unit_price_usd",
        "special_shape_price_status",
        "special_shape_price_note",
        "special_shape_price_approved_by",
        "special_shape_price_approved_on",
    ];

    function can(capability) {
        return Boolean(
            window.AlmdinaPermissions &&
            window.AlmdinaPermissions.can(capability)
        );
    }

    function documentContext() {
        return window.AlmdinaDocumentContext;
    }

    function costWrapper(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper ? field.$wrapper : null;
    }

    function setCostTabVisibility(frm, visible) {
        frm.set_df_property("cost_tab", "hidden", visible ? 0 : 1);
        const wrapper = costWrapper(frm);
        if (!visible && wrapper) wrapper.empty();
    }

    function scrubCostData(frm) {
        ORDER_COST_FIELDS.forEach((fieldname) => {
            if (Object.prototype.hasOwnProperty.call(frm.doc, fieldname)) {
                delete frm.doc[fieldname];
            }
        });
        (frm.doc.pieces || []).forEach((piece) => {
            PIECE_COST_FIELDS.forEach((fieldname) => {
                if (Object.prototype.hasOwnProperty.call(piece, fieldname)) {
                    delete piece[fieldname];
                }
            });
        });
        frm.__almdina_cost_snapshot_order = null;
    }

    function mergeSnapshot(frm, snapshot) {
        Object.assign(frm.doc, (snapshot && snapshot.order) || {});
        const byName = new Map(
            ((snapshot && snapshot.pieces) || []).map((piece) => [piece.name, piece])
        );
        (frm.doc.pieces || []).forEach((piece) => {
            const costPiece = byName.get(piece.name);
            if (costPiece) Object.assign(piece, costPiece);
        });
        frm.__almdina_cost_snapshot_order = frm.doc.name;
    }

    function sourcePiece(frm, rowName) {
        return (frm.doc.pieces || []).find((row) => row.name === rowName) || null;
    }

    function editCostSettings(frm) {
        frappe.prompt(
            [
                {
                    fieldname: "board_rate_usd",
                    fieldtype: "Currency",
                    label: __("سعر اللوح ($)"),
                    reqd: 1,
                    non_negative: 1,
                    default: Number(frm.doc.board_rate_usd || 0),
                },
                {
                    fieldname: "cutting_cost_per_board_usd",
                    fieldtype: "Currency",
                    label: __("أجور القص لكل لوح ($)"),
                    reqd: 1,
                    non_negative: 1,
                    default: Number(frm.doc.cutting_cost_per_board_usd || 0),
                },
            ],
            (values) => {
                frappe.call({
                    method: "almdina_erp.almdina_erp.services.cost_permission_service.update_order_cost_settings",
                    args: {
                        order_name: frm.doc.name,
                        board_rate_usd: values.board_rate_usd,
                        cutting_cost_per_board_usd: values.cutting_cost_per_board_usd,
                    },
                    freeze: true,
                    freeze_message: __("جاري تحديث إعدادات التكلفة..."),
                }).then((response) => {
                    mergeSnapshot(frm, response.message || {});
                    frappe.show_alert({
                        message: __("تم تحديث إعدادات التكلفة وإعادة حساب الطلب."),
                        indicator: "green",
                    }, 5);
                    return frm.reload_doc();
                });
            },
            __("إعدادات تكلفة الطلب"),
            __("حفظ وإعادة الحساب")
        );
    }

    function editSpecialPrice(frm, piece) {
        const approved = piece.special_shape_price_status === "Approved";
        frappe.prompt(
            [
                {
                    fieldname: "unit_price_usd",
                    fieldtype: "Currency",
                    label: __("السعر الشامل للدرفة الواحدة ($)"),
                    reqd: 1,
                    non_negative: 1,
                    default: Number(
                        approved
                            ? piece.special_shape_custom_unit_price_usd
                            : piece.special_shape_estimated_unit_price_usd
                    ) || 0,
                },
                {
                    fieldname: "note",
                    fieldtype: "Small Text",
                    label: __("ملاحظة التسعير (اختياري)"),
                    default: piece.special_shape_price_note || "",
                },
            ],
            (values) => {
                frappe.call({
                    method: "almdina_erp.almdina_erp.services.special_shape_service.approve_special_piece_price",
                    args: {
                        order_name: frm.doc.name,
                        piece_name: piece.name,
                        unit_price_usd: values.unit_price_usd,
                        note: values.note || "",
                    },
                    freeze: true,
                    freeze_message: approved
                        ? __("جاري تحديث السعر المعتمد...")
                        : __("جاري اعتماد سعر الدرفة الخاصة..."),
                }).then(() => {
                    frappe.show_alert({
                        message: approved
                            ? __("تم تحديث السعر المعتمد.")
                            : __("تم اعتماد السعر الشامل."),
                        indicator: "green",
                    }, 5);
                    return frm.reload_doc();
                });
            },
            approved ? __("تعديل السعر المعتمد") : __("اعتماد سعر الدرفة الخاصة"),
            approved ? __("تحديث السعر") : __("اعتماد السعر")
        );
    }

    function installActionPermissions(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper) return;

        if (!(can("view_costs") && can("print_customer_invoice"))) {
            wrapper.find(".dco-print-customer-invoice").remove();
        }

        const actions = wrapper.find(".dco-cost-actions");
        actions.find(".dco-edit-cost-settings").remove();
        if (can("edit_cost_settings") && !frm.is_new()) {
            actions.prepend(
                `<button type="button" class="btn btn-default btn-sm dco-edit-cost-settings">${__("تعديل إعدادات التكلفة")}</button>`
            );
            actions.find(".dco-edit-cost-settings").on("click", () => editCostSettings(frm));
        }

        wrapper.find(".dco-approve-special-price,.dco-capability-special-price").remove();
        wrapper.find("[data-special-row]").each(function installPriceAction() {
            const card = $(this);
            const piece = sourcePiece(frm, card.attr("data-special-row"));
            if (!piece) return;
            const approved = piece.special_shape_price_status === "Approved";
            const capability = approved ? "edit_special_price" : "approve_special_price";
            if (!can(capability) || frm.is_new() || piece.special_shape_status !== "Documented") {
                return;
            }
            const button = $(
                `<button type="button" class="btn ${approved ? "btn-default" : "btn-primary"} btn-xs dco-capability-special-price">${approved ? __("تعديل السعر") : __("اعتماد سعر")}</button>`
            );
            card.find(".dco-special-price-actions").find(".dco-view-special-sketch").after(button);
            button.on("click", () => editSpecialPrice(frm, piece));
        });
    }

    function renderAuthorizedCost(frm) {
        if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
            window.AlmdinaOrderCostUX.render(frm);
        }
        setTimeout(() => installActionPermissions(frm), 0);
    }

    function loadCostSnapshot(frm) {
        if (frm.is_new()) {
            renderAuthorizedCost(frm);
            return Promise.resolve();
        }
        const context = documentContext();
        const identity = context.capture(frm);
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.cost_permission_service.get_order_cost_snapshot",
            args: { order_name: frm.doc.name },
        }).then((response) => {
            if (!context.isCurrent(frm, identity)) return;
            mergeSnapshot(frm, response.message || {});
            renderAuthorizedCost(frm);
        });
    }

    function apply(frm) {
        if (!can("view_costs")) {
            scrubCostData(frm);
            setCostTabVisibility(frm, false);
            return;
        }
        setCostTabVisibility(frm, true);
        loadCostSnapshot(frm).catch((error) => {
            console.error("Failed to load protected cost snapshot", error);
            scrubCostData(frm);
            setCostTabVisibility(frm, false);
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            setTimeout(() => apply(frm), 0);
        },
        refresh(frm) {
            setTimeout(() => apply(frm), 0);
        },
    });

    window.AlmdinaCostPermissionsUX = Object.freeze({
        apply,
        can,
        mergeSnapshot,
        scrubCostData,
    });
})();
