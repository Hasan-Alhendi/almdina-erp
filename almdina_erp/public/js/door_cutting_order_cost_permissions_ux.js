(() => {
    "use strict";

    const COST_INPUT_FIELDS = Object.freeze([
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);
    const EDITABLE_ORDER_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
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
        "clipped_corner_edge_price_usd",
        "clipped_corner_edge_price_status",
        "clipped_corner_edge_price_note",
        "clipped_corner_edge_price_set_by",
        "clipped_corner_edge_price_set_on",
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

    function documentContext() {
        return window.AlmdinaDocumentContext;
    }

    function costWrapper(frm) {
        const field = frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper ? field.$wrapper : null;
    }

    function setCostTabVisibility(frm, visible) {
        const wrapper = costWrapper(frm);
        if (!visible && wrapper) wrapper.empty();

        // Tab navigation is owned by AlmdinaOrderTabPermissionsUX. Never mutate
        // the cost Tab Break df here: changing a Tab Break's hidden property can
        // rebuild the Frappe layout and erase already-rendered plan HTML.
        const tabs = window.AlmdinaOrderTabPermissionsUX;
        if (tabs && typeof tabs.apply === "function") {
            tabs.apply(frm);
        }
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

    function orderIsEditable(frm) {
        if (!frm || !frm.doc || frm.is_new()) return false;
        if (window.frappe && frappe.almdina && typeof frappe.almdina.orderCanEdit === "function") {
            return Boolean(frappe.almdina.orderCanEdit(frm));
        }
        return (
            Number(frm.doc.docstatus || 0) === 0
            && EDITABLE_ORDER_STATUSES.has(frm.doc.status || "Draft")
        );
    }

    function orderCostFieldsEditable(frm) {
        return Boolean(
            can(frm, "edit_cost_settings")
            && orderIsEditable(frm)
        );
    }

    function configureCostInputFields(frm) {
        const visible = can(frm, "view_costs");
        const editable = orderCostFieldsEditable(frm);
        COST_INPUT_FIELDS.forEach(fieldname => {
            frm.set_df_property(fieldname, "hidden", visible ? 0 : 1);
            frm.set_df_property(fieldname, "read_only", editable ? 0 : 1);
        });
    }

    function editSpecialPrice(frm, piece) {
        if (!orderIsEditable(frm)) {
            frappe.msgprint(__("افتح الطلب للتعديل أولاً قبل تغيير أسعار القشاط."));
            return;
        }
        const approved = piece.special_shape_price_status === "Approved";
        frappe.prompt(
            [
                {
                    fieldname: "unit_price_usd",
                    fieldtype: "Currency",
                    label: __("إجمالي تكلفة قشاط الدرفة الخاصة ($)"),
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
                        ? __("جاري تحديث سعر القشاط...")
                        : __("جاري حفظ سعر قشاط الدرفة الخاصة..."),
                }).then(() => {
                    frappe.show_alert({
                        message: approved
                            ? __("تم تحديث سعر القشاط.")
                            : __("تم حفظ سعر قشاط الدرفة الخاصة."),
                        indicator: "green",
                    }, 5);
                    return frm.reload_doc();
                });
            },
            __("تعديل السعر"),
            __("حفظ السعر")
        );
    }

    function editCutCornerEdgePrice(frm, piece) {
        if (!orderIsEditable(frm)) {
            frappe.msgprint(__("افتح الطلب للتعديل أولاً قبل تغيير أسعار القشاط."));
            return;
        }
        const priced = piece.clipped_corner_edge_price_status === "Priced";
        frappe.prompt(
            [
                {
                    fieldname: "edge_price_usd",
                    fieldtype: "Currency",
                    label: __("تكلفة معالجة قشاط الزاوية المقصوصة ($)"),
                    reqd: 1,
                    non_negative: 1,
                    default: Number(piece.clipped_corner_edge_price_usd) || 0,
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
                    method: "almdina_erp.almdina_erp.services.cost_permission_service.update_clipped_corner_edge_price",
                    args: {
                        order_name: frm.doc.name,
                        piece_name: piece.name,
                        edge_price_usd: values.edge_price_usd,
                        note: values.note || "",
                    },
                    freeze: true,
                    freeze_message: __("جاري حفظ سعر قشاط الزاوية المقصوصة..."),
                }).then(() => {
                    frappe.show_alert({
                        message: priced
                            ? __("تم تحديث سعر قشاط الزاوية المقصوصة.")
                            : __("تم حفظ سعر قشاط الزاوية المقصوصة."),
                        indicator: "green",
                    }, 5);
                    return frm.reload_doc();
                });
            },
            __("تعديل السعر"),
            __("حفظ السعر")
        );
    }

    function canUseCostTab(frm) {
        return can(frm, "view_costs") || can(frm, "print_customer_invoice");
    }

    function ensurePrintInvoiceButton(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper || !wrapper.find(".dco-cost-shell").length) return;

        const selectors = ".dco-print-customer-invoice, .dco-secure-print-customer-invoice";
        if (!can(frm, "print_customer_invoice")) {
            wrapper.find(selectors).remove();
            return;
        }

        wrapper.find(selectors)
            .prop("disabled", false)
            .removeClass("is-plan-stale")
            .attr("aria-disabled", "false");
    }

    function installActionPermissions(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper || !wrapper.find(".dco-cost-shell").length) return;

        ensurePrintInvoiceButton(frm);
        wrapper.find(".dco-edit-cost-settings").remove();

        wrapper.find(".dco-approve-special-price,.dco-capability-special-price").remove();
        wrapper.find("[data-special-row]").each(function installPriceAction() {
            const card = $(this);
            const piece = sourcePiece(frm, card.attr("data-special-row"));
            if (!piece) return;
            const approved = piece.special_shape_price_status === "Approved";
            const capability = approved ? "edit_special_price" : "approve_special_price";
            if (!can(frm, capability) || !orderIsEditable(frm)) {
                return;
            }
            const button = $(
                `<button type="button" class="btn btn-primary btn-xs dco-capability-special-price">${__("تعديل السعر")}</button>`
            );
            card.find(".dco-special-price-actions").prepend(button);
            button.on("click", () => editSpecialPrice(frm, piece));
        });

        wrapper.find(".dco-capability-cut-corner-price").remove();
        wrapper.find("[data-cut-corner-row]").each(function installCutCornerPriceAction() {
            const card = $(this);
            const piece = sourcePiece(frm, card.attr("data-cut-corner-row"));
            if (!piece) return;
            const priced = piece.clipped_corner_edge_price_status === "Priced";
            const capability = priced ? "edit_special_price" : "approve_special_price";
            if (!can(frm, capability) || !orderIsEditable(frm)) {
                return;
            }
            const button = $(
                `<button type="button" class="btn btn-primary btn-xs dco-capability-cut-corner-price">${__("تعديل السعر")}</button>`
            );
            card.find(".dco-special-price-actions").prepend(button);
            button.on("click", () => editCutCornerEdgePrice(frm, piece));
        });
    }

    function installActionsAfterRender(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper || !wrapper[0]) return;
        if (frm.__almdina_cost_actions_observer) {
            frm.__almdina_cost_actions_observer.disconnect();
            frm.__almdina_cost_actions_observer = null;
        }
        if (wrapper.find(".dco-cost-shell").length) {
            installActionPermissions(frm);
            return;
        }

        const identity = documentContext().capture(frm);
        const observer = new MutationObserver(() => {
            if (!documentContext().isCurrent(frm, identity)) {
                observer.disconnect();
                if (frm.__almdina_cost_actions_observer === observer) {
                    frm.__almdina_cost_actions_observer = null;
                }
                return;
            }
            if (!wrapper.find(".dco-cost-shell").length) return;
            observer.disconnect();
            if (frm.__almdina_cost_actions_observer === observer) {
                frm.__almdina_cost_actions_observer = null;
            }
            installActionPermissions(frm);
        });
        observer.observe(wrapper[0], { childList: true, subtree: true });
        frm.__almdina_cost_actions_observer = observer;
        setTimeout(() => {
            observer.disconnect();
            if (frm.__almdina_cost_actions_observer === observer) {
                frm.__almdina_cost_actions_observer = null;
            }
            if (documentContext().isCurrent(frm, identity)) {
                installActionPermissions(frm);
            }
        }, 1500);
    }

    function renderAuthorizedCost(frm) {
        if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
            window.AlmdinaOrderCostUX.render(frm);
        }
        installActionsAfterRender(frm);
    }

    function loadCostSnapshot(frm) {
        if (frm.is_new()) {
            renderAuthorizedCost(frm);
            return Promise.resolve();
        }
        const context = documentContext();
        if (
            frm.__almdinaCostSnapshotPromise
            && context.isCurrent(frm, frm.__almdinaCostSnapshotContext)
        ) {
            return frm.__almdinaCostSnapshotPromise;
        }

        const identity = context.capture(frm);
        const orderName = frm.doc.name;
        const snapshotPromise = Promise.resolve(frappe.call({
            method: "almdina_erp.almdina_erp.services.cost_permission_service.get_order_cost_snapshot",
            args: { order_name: orderName },
        })).then((response) => {
            if (!context.isCurrent(frm, identity)) return;
            mergeSnapshot(frm, response.message || {});
            renderAuthorizedCost(frm);
        }).finally(() => {
            if (frm.__almdinaCostSnapshotPromise === snapshotPromise) {
                frm.__almdinaCostSnapshotPromise = null;
                frm.__almdinaCostSnapshotContext = null;
            }
        });

        frm.__almdinaCostSnapshotContext = identity;
        frm.__almdinaCostSnapshotPromise = snapshotPromise;
        return snapshotPromise;
    }

    function apply(frm) {
        configureCostInputFields(frm);

        if (!canUseCostTab(frm)) {
            scrubCostData(frm);
            setCostTabVisibility(frm, false);
            return;
        }

        setCostTabVisibility(frm, true);

        if (can(frm, "view_costs")) {
            const context = documentContext();
            const identity = context.capture(frm);
            loadCostSnapshot(frm).catch((error) => {
                if (!context.isCurrent(frm, identity)) return;
                console.error("Failed to load protected cost snapshot", error);
                scrubCostData(frm);
                setCostTabVisibility(frm, false);
            });
            return;
        }

        renderAuthorizedCost(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            setTimeout(() => apply(frm), 0);
        },
        refresh(frm) {
            setTimeout(() => apply(frm), 0);
        },
        almdina_edit_session_changed(frm) {
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
