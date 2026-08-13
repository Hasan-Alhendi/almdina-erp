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

    function pendingPriceFields(piece) {
        if (!piece || !piece.__almdina_pending_price_edit) return null;
        if (piece.__almdina_pending_price_edit === "clipped") {
            return {
                __almdina_pending_price_edit: "clipped",
                clipped_corner_edge_price_usd: piece.clipped_corner_edge_price_usd,
                clipped_corner_edge_price_status: piece.clipped_corner_edge_price_status,
                clipped_corner_edge_price_note: piece.clipped_corner_edge_price_note,
                clipped_corner_edge_price_set_by: piece.clipped_corner_edge_price_set_by,
                clipped_corner_edge_price_set_on: piece.clipped_corner_edge_price_set_on,
            };
        }
        return {
            __almdina_pending_price_edit: "special",
            special_shape_custom_unit_price_usd: piece.special_shape_custom_unit_price_usd,
            special_shape_final_unit_price_usd: piece.special_shape_final_unit_price_usd,
            special_shape_price_status: piece.special_shape_price_status,
            special_shape_price_note: piece.special_shape_price_note,
            special_shape_price_approved_by: piece.special_shape_price_approved_by,
            special_shape_price_approved_on: piece.special_shape_price_approved_on,
        };
    }

    function mergeSnapshot(frm, snapshot) {
        Object.assign(frm.doc, (snapshot && snapshot.order) || {});
        const byName = new Map(
            ((snapshot && snapshot.pieces) || []).map((piece) => [piece.name, piece])
        );
        (frm.doc.pieces || []).forEach((piece) => {
            const costPiece = byName.get(piece.name);
            if (!costPiece) return;
            const pending = pendingPriceFields(piece);
            Object.assign(piece, costPiece);
            if (pending) Object.assign(piece, pending);
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

    function editSessionActive(frm) {
        const revisionUx = window.AlmdinaOrderRevisionUX;
        if (
            revisionUx
            && typeof revisionUx.captureEditSessionPresence === "function"
        ) {
            return Boolean(revisionUx.captureEditSessionPresence(frm));
        }
        return Boolean(
            frm
            && frm.__almdina_edit_session
            && !frm.__almdina_edit_session_abandoned
            && frm.__almdina_edit_session_order === (frm.doc && frm.doc.name)
        );
    }

    function canEditInlinePiecePrice(frm, piece) {
        if (!frm || !piece || !orderIsEditable(frm) || !editSessionActive(frm)) {
            return false;
        }
        if (piece.piece_type === "Special") {
            const capability = piece.special_shape_price_status === "Approved"
                ? "edit_special_price"
                : "approve_special_price";
            return can(frm, capability);
        }
        if (piece.piece_type === "Clipped Corner") {
            const capability = piece.clipped_corner_edge_price_status === "Priced"
                ? "edit_special_price"
                : "approve_special_price";
            return can(frm, capability);
        }
        return false;
    }

    function orderCostFieldsEditable(frm) {
        return Boolean(
            can(frm, "edit_cost_settings")
            && orderIsEditable(frm)
        );
    }

    function configureCostInputFields(frm) {
        // Force USD display for Currency inputs regardless of company default (e.g. LBP).
        if (!frm.doc.costing_currency) {
            frm.doc.costing_currency = "USD";
        }
        const visible = can(frm, "view_costs");
        const editable = orderCostFieldsEditable(frm);
        COST_INPUT_FIELDS.forEach(fieldname => {
            frm.set_df_property(fieldname, "options", "costing_currency");
            frm.set_df_property(fieldname, "hidden", visible ? 0 : 1);
            frm.set_df_property(fieldname, "read_only", editable ? 0 : 1);
            if (typeof frm.refresh_field === "function") {
                frm.refresh_field(fieldname);
            }
        });
    }

    function markFormDirty(frm) {
        if (!frm) return;
        if (typeof frm.dirty === "function") {
            frm.dirty();
            return;
        }
        if (frm.doc) frm.doc.__unsaved = 1;
    }

    function syncLocalInvoiceTotals(frm) {
        const costUx = window.AlmdinaOrderCostUX;
        if (costUx && typeof costUx.quoteTotal === "function") {
            frm.doc.customer_quote_total_usd = costUx.quoteTotal(frm);
        }
        if ((frm.doc.pieces || []).some((row) =>
            row.piece_type === "Special" && row.special_shape_price_status === "Approved"
        )) {
            const allApproved = (frm.doc.pieces || [])
                .filter((row) => row.piece_type === "Special")
                .every((row) => row.special_shape_price_status === "Approved");
            frm.doc.customer_quote_status = allApproved ? "Approved" : "Partially Approved";
        }
    }

    function applyInlinePriceToPiece(piece, kind, rawValue) {
        const price = Math.max(0, Number(rawValue) || 0);
        if (kind === "clipped") {
            piece.clipped_corner_edge_price_usd = price;
            piece.clipped_corner_edge_price_status = price > 0 ? "Priced" : "Unpriced";
            piece.clipped_corner_edge_price_set_by =
                piece.clipped_corner_edge_price_set_by
                || (frappe.session && frappe.session.user)
                || "";
            piece.clipped_corner_edge_price_set_on =
                piece.clipped_corner_edge_price_set_on
                || (frappe.datetime && frappe.datetime.now_datetime
                    ? frappe.datetime.now_datetime()
                    : null);
            piece.__almdina_pending_price_edit = "clipped";
            return;
        }
        piece.special_shape_custom_unit_price_usd = price;
        piece.special_shape_final_unit_price_usd = price;
        piece.special_shape_price_status = price > 0 ? "Approved" : "Estimated";
        piece.special_shape_price_approved_by =
            piece.special_shape_price_approved_by
            || (frappe.session && frappe.session.user)
            || "";
        piece.special_shape_price_approved_on =
            piece.special_shape_price_approved_on
            || (frappe.datetime && frappe.datetime.now_datetime
                ? frappe.datetime.now_datetime()
                : null);
        piece.__almdina_pending_price_edit = "special";
    }

    function refreshInvoiceAfterInlinePrice(frm) {
        syncLocalInvoiceTotals(frm);
        const costUx = window.AlmdinaOrderCostUX;
        if (costUx && typeof costUx.refreshInvoiceSection === "function") {
            costUx.refreshInvoiceSection(frm);
            return;
        }
        renderAuthorizedCost(frm);
    }

    function pendingPricePieces(frm) {
        return (frm.doc.pieces || []).filter((piece) => piece.__almdina_pending_price_edit);
    }

    function clearPriceOnlyDirty(frm) {
        if (!frm || !frm.doc) return;
        if (pendingPricePieces(frm).length) return;
        frm.doc.__unsaved = 0;
    }

    async function flushPendingPriceEdits(frm) {
        const pending = pendingPricePieces(frm);
        if (!pending.length) return false;

        for (const piece of pending) {
            if (piece.__almdina_pending_price_edit === "clipped") {
                await frappe.call({
                    method: "almdina_erp.almdina_erp.services.cost_permission_service.update_clipped_corner_edge_price",
                    args: {
                        order_name: frm.doc.name,
                        piece_name: piece.name,
                        edge_price_usd: piece.clipped_corner_edge_price_usd,
                        note: piece.clipped_corner_edge_price_note || "",
                    },
                    freeze: true,
                    freeze_message: __("جاري اعتماد أسعار القشاط..."),
                });
            } else {
                await frappe.call({
                    method: "almdina_erp.almdina_erp.services.special_shape_service.approve_special_piece_price",
                    args: {
                        order_name: frm.doc.name,
                        piece_name: piece.name,
                        unit_price_usd: piece.special_shape_custom_unit_price_usd,
                        note: piece.special_shape_price_note || "",
                    },
                    freeze: true,
                    freeze_message: __("جاري اعتماد أسعار القشاط..."),
                });
            }
            delete piece.__almdina_pending_price_edit;
        }

        frm.__almdinaCostSnapshotPromise = null;
        frm.__almdinaCostSnapshotContext = null;
        await loadCostSnapshot(frm);
        clearPriceOnlyDirty(frm);
        return true;
    }

    function bindInlinePriceInputs(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper || !wrapper.find(".dco-cost-shell").length) return;

        wrapper.find(".dco-inline-price-input").each(function syncInlinePriceInput() {
            const input = this;
            const piece = sourcePiece(frm, input.getAttribute("data-piece-name"));
            const editable = canEditInlinePiecePrice(frm, piece);
            input.disabled = !editable;
            input.setAttribute("aria-label", editable ? __("تعديل السعر") : __("السعر للعرض فقط"));
            if (editable) {
                input.removeAttribute("readonly");
            } else {
                input.setAttribute("readonly", "readonly");
            }
        });

        wrapper.off(".almdinaInlinePrice");
        wrapper.on("change.almdinaInlinePrice", ".dco-inline-price-input", function onInlinePriceChange() {
            const input = this;
            const piece = sourcePiece(frm, input.getAttribute("data-piece-name"));
            if (!canEditInlinePiecePrice(frm, piece)) return;
            applyInlinePriceToPiece(
                piece,
                input.getAttribute("data-price-kind"),
                input.value
            );
            markFormDirty(frm);
            const cell = input.closest(".dco-special-price-cell");
            if (cell) {
                const priced = Number(input.value) > 0;
                cell.classList.toggle("is-unpriced", !priced);
            }
            refreshInvoiceAfterInlinePrice(frm);
            const revisionUx = window.AlmdinaOrderRevisionUX;
            if (revisionUx && typeof revisionUx.schedulePrimaryActionSync === "function") {
                revisionUx.schedulePrimaryActionSync(frm);
            }
        });
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
        wrapper.find(".dco-approve-special-price,.dco-capability-special-price,.dco-capability-cut-corner-price").remove();
        bindInlinePriceInputs(frm);
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
        flushPendingPriceEdits,
        pendingPricePieces,
    });
})();
