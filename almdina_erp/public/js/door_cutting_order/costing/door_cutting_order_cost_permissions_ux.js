(() => {
    "use strict";

    const COST_INPUT_FIELDS = Object.freeze([
        "board_rate_usd",
        "cutting_cost_per_board_usd",
    ]);
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
    const ACTION_OBSERVER_KEY = "cost-permissions-render-actions";
    const APPLY_FRAME_KEY = "cost-permissions-apply";
    const RECONCILE_FRAME_KEY = "cost-permissions-reconcile-actions";

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && (
                typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, capability)
                    : permissions.can(capability)
            )
        );
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function captureDocument(frm) {
        const context = documentContext();
        if (context && typeof context.capture === "function") return context.capture(frm);
        return Object.freeze({ name: String(frm && frm.doc && frm.doc.name || "") });
    }

    function documentStillCurrent(frm, token) {
        const context = documentContext();
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, token);
        }
        return Boolean(
            window.cur_frm === frm
            && String(frm && frm.doc && frm.doc.name || "") === String(token && token.name || "")
        );
    }

    function costWorkspaceState() {
        return window.AlmdinaCostWorkspaceState || null;
    }

    function costWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
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

    function sourcePiece(frm, rowName) {
        return (frm.doc.pieces || []).find((row) => row.name === rowName) || null;
    }

    function orderIsEditable(frm) {
        // Pricing has its own capabilities and its own Cost edit session. Do not
        // call frappe.almdina.orderCanEdit() here: that helper intentionally also
        // requires edit_order + the Order edit session and would couple two
        // independent permission surfaces. Mirror the server-side
        // assert_order_editable() lifecycle boundary instead.
        if (!frm || !frm.doc || frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (String(frm.doc.revision_state || "Current") === "Superseded") return false;
        return String(frm.doc.status || "Draft") === "Draft";
    }

    function editSessionActive(frm) {
        // Inline prices are part of the Cost tab, so the Cost edit session is the
        // primary owner. Keep the Order session fallback for legacy callers that
        // still save price edits through the order-level edit flow.
        const costEditUx = window.AlmdinaCostEditSessionUX;
        if (
            costEditUx
            && typeof costEditUx.isEditing === "function"
            && costEditUx.isEditing(frm)
        ) {
            return true;
        }

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

    function requiredInlinePriceCapability(piece) {
        if (!piece) return null;
        if (piece.__almdina_pending_price_capability) {
            return piece.__almdina_pending_price_capability;
        }
        if (piece.piece_type === "Special") {
            return piece.special_shape_price_status === "Approved"
                ? "edit_special_price"
                : "approve_special_price";
        }
        if (piece.piece_type === "Clipped Corner" || piece.piece_type === "L-Shaped Corner") {
            return piece.clipped_corner_edge_price_status === "Priced"
                ? "edit_special_price"
                : "approve_special_price";
        }
        return null;
    }

    function canEditInlinePiecePrice(frm, piece) {
        if (!frm || !piece || !orderIsEditable(frm) || !editSessionActive(frm)) {
            return false;
        }
        const capability = requiredInlinePriceCapability(piece);
        return Boolean(capability && can(frm, capability));
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
            const field = frm.fields_dict && frm.fields_dict[fieldname];
            if (!field || !field.df) return;
            const hidden = visible ? 0 : 1;
            const readOnly = editable ? 0 : 1;
            if (field.df.options !== "costing_currency") {
                frm.set_df_property(fieldname, "options", "costing_currency");
            }
            if (Number(field.df.hidden || 0) !== hidden) {
                frm.set_df_property(fieldname, "hidden", hidden);
            }
            if (Number(field.df.read_only || 0) !== readOnly) {
                frm.set_df_property(fieldname, "read_only", readOnly);
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

    function rememberPendingCapability(piece, kind) {
        if (!piece || piece.__almdina_pending_price_capability) return;
        if (kind === "clipped") {
            piece.__almdina_pending_price_capability =
                piece.clipped_corner_edge_price_status === "Priced"
                    ? "edit_special_price"
                    : "approve_special_price";
            return;
        }
        piece.__almdina_pending_price_capability =
            piece.special_shape_price_status === "Approved"
                ? "edit_special_price"
                : "approve_special_price";
    }

    function applyInlinePriceToPiece(piece, kind, rawValue) {
        const price = Math.max(0, Number(rawValue) || 0);
        rememberPendingCapability(piece, kind);
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
            reconcileRenderedActions(frm);
            return;
        }
        renderAuthorizedCost(frm);
    }

    function pendingPricePieces(frm) {
        return (frm.doc.pieces || []).filter((piece) => piece.__almdina_pending_price_edit);
    }

    function clearPendingPriceMarker(piece) {
        if (!piece) return;
        delete piece.__almdina_pending_price_edit;
        delete piece.__almdina_pending_price_capability;
    }

    function clearPriceOnlyDirty(frm) {
        if (!frm || !frm.doc) return;
        if (pendingPricePieces(frm).length) return;
        frm.doc.__unsaved = 0;
    }

    function pricingExpectedModified(frm) {
        return String(
            (frm && frm.__almdina_pricing_command_modified)
            || (frm && frm.doc && frm.doc.modified)
            || ""
        ).trim();
    }

    function rememberPricingCommandModified(frm, response) {
        const payload = response && response.message !== undefined
            ? response.message
            : null;
        const modified = String(payload && payload.order_modified || "").trim();
        if (!modified) {
            throw new Error(__("لم يعُد الخادم بنسخة الطلب بعد حفظ السعر."));
        }
        frm.__almdina_pricing_command_modified = modified;
        return modified;
    }

    function finalizePricingDocumentVersion(frm) {
        const modified = String(frm && frm.__almdina_pricing_command_modified || "").trim();
        if (!modified) return false;
        const coordinator = window.AlmdinaWorkspaceSyncCoordinator;
        if (!coordinator || typeof coordinator.syncDocumentModified !== "function") {
            return false;
        }
        const synced = coordinator.syncDocumentModified(frm, modified);
        if (synced) frm.__almdina_pricing_command_modified = null;
        return synced;
    }

    async function refreshAuthoritativeCost(frm) {
        const token = captureDocument(frm);
        const owner = costWorkspaceState();
        if (owner && typeof owner.load === "function") {
            await owner.load(frm, { force: true });
            return documentStillCurrent(frm, token);
        }
        if (!documentStillCurrent(frm, token)) return false;
        renderAuthorizedCost(frm);
        return true;
    }

    async function flushPendingPriceEdits(frm, options = {}) {
        const pending = pendingPricePieces(frm);
        if (!pending.length) return false;

        const token = captureDocument(frm);
        const orderName = String(frm && frm.doc && frm.doc.name || "");
        for (const piece of pending) {
            if (!documentStillCurrent(frm, token)) return false;
            const expectedModified = pricingExpectedModified(frm);
            if (!expectedModified) {
                throw new Error(__("تعذر التحقق من نسخة الطلب الحالية. أعد تحميل الطلب ثم حاول مرة أخرى."));
            }

            let response;
            if (piece.__almdina_pending_price_edit === "clipped") {
                response = await frappe.call({
                    method: "almdina_erp.almdina_erp.services.cost_permission_service.update_clipped_corner_edge_price",
                    args: {
                        order_name: orderName,
                        piece_name: piece.name,
                        edge_price_usd: piece.clipped_corner_edge_price_usd,
                        note: piece.clipped_corner_edge_price_note || "",
                        expected_modified: expectedModified,
                    },
                    freeze: true,
                    freeze_message: __("جاري اعتماد أسعار القشاط..."),
                });
            } else {
                response = await frappe.call({
                    method: "almdina_erp.almdina_erp.services.cost_permission_service.approve_special_piece_price",
                    args: {
                        order_name: orderName,
                        piece_name: piece.name,
                        unit_price_usd: piece.special_shape_custom_unit_price_usd,
                        note: piece.special_shape_price_note || "",
                        expected_modified: expectedModified,
                    },
                    freeze: true,
                    freeze_message: __("جاري اعتماد أسعار الدرف الخاصة..."),
                });
            }
            if (!documentStillCurrent(frm, token)) return false;
            rememberPricingCommandModified(frm, response);
            clearPendingPriceMarker(piece);
        }

        clearPriceOnlyDirty(frm);
        finalizePricingDocumentVersion(frm);
        if (options.refresh !== false) {
            return Boolean(await refreshAuthoritativeCost(frm));
        }
        return true;
    }

    async function discardPendingPriceEdits(frm, options = {}) {
        const pending = pendingPricePieces(frm);
        const hasCommandVersion = Boolean(
            String(frm && frm.__almdina_pricing_command_modified || "").trim()
        );
        if (!pending.length && !hasCommandVersion) return false;
        const token = captureDocument(frm);
        pending.forEach(clearPendingPriceMarker);
        clearPriceOnlyDirty(frm);
        finalizePricingDocumentVersion(frm);
        if (options.refresh !== false) {
            return Boolean(await refreshAuthoritativeCost(frm))
                && documentStillCurrent(frm, token);
        }
        return documentStillCurrent(frm, token);
    }

    function inlinePriceLabel(piece) {
        if (piece && piece.piece_type === "Special") {
            return __("السعر الخاص الشامل للدرفة");
        }
        if (piece && (piece.piece_type === "Clipped Corner" || piece.piece_type === "L-Shaped Corner")) {
            return piece.piece_type === "L-Shaped Corner"
                ? __("تكلفة معالجة قشاط زاوية L")
                : __("تكلفة معالجة قشاط الزاوية المقصوصة");
        }
        return __("السعر");
    }

    function bindInlinePriceInputs(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper || !wrapper.find(".dco-cost-shell").length) return;

        wrapper.find(".dco-inline-price-input").each(function syncInlinePriceInput() {
            const input = this;
            const piece = sourcePiece(frm, input.getAttribute("data-piece-name"));
            const editable = canEditInlinePiecePrice(frm, piece);
            input.disabled = !editable;
            const priceLabel = inlinePriceLabel(piece);
            input.setAttribute(
                "aria-label",
                editable ? `${__("تعديل السعر")}: ${priceLabel}` : priceLabel
            );
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
        if (!wrapper || !wrapper.find(".dco-cost-shell").length) return false;

        ensurePrintInvoiceButton(frm);
        wrapper.find(".dco-edit-cost-settings").remove();
        wrapper.find(".dco-approve-special-price,.dco-capability-special-price,.dco-capability-cut-corner-price").remove();
        bindInlinePriceInputs(frm);
        return true;
    }

    function clearActionObserver(frm) {
        const observer = frm && frm.__almdina_cost_actions_observer;
        if (observer && typeof observer.disconnect === "function") observer.disconnect();
        if (frm) frm.__almdina_cost_actions_observer = null;
    }

    function installActionsAfterRender(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper || !wrapper[0]) return false;
        clearActionObserver(frm);
        if (wrapper.find(".dco-cost-shell").length) {
            return installActionPermissions(frm);
        }

        const identity = captureDocument(frm);
        const observer = new MutationObserver(() => {
            if (!documentStillCurrent(frm, identity)) {
                clearActionObserver(frm);
                return;
            }
            if (!wrapper.find(".dco-cost-shell").length) return;
            clearActionObserver(frm);
            installActionPermissions(frm);
        });
        observer.observe(wrapper[0], { childList: true, subtree: true });
        frm.__almdina_cost_actions_observer = observer;
        const context = documentContext();
        if (context && typeof context.registerObserver === "function") {
            context.registerObserver(frm, ACTION_OBSERVER_KEY, observer);
        }
        return true;
    }

    function reconcileRenderedActions(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        return installActionsAfterRender(frm);
    }

    function renderAuthorizedCost(frm) {
        if (window.AlmdinaOrderCostUX && window.AlmdinaOrderCostUX.render) {
            window.AlmdinaOrderCostUX.render(frm);
        }
        reconcileRenderedActions(frm);
    }

    function apply(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        configureCostInputFields(frm);

        if (!canUseCostTab(frm)) {
            scrubCostData(frm);
            setCostTabVisibility(frm, false);
            return true;
        }

        setCostTabVisibility(frm, true);

        // CostWorkspaceState + its presenter adapter are the sole snapshot owner.
        // This permission layer projects capabilities only; it performs no GET.
        renderAuthorizedCost(frm);
        return true;
    }

    function scheduleApply(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const run = () => apply(frm);
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, APPLY_FRAME_KEY, run);
            return;
        }
        if (window.requestAnimationFrame) {
            window.requestAnimationFrame(() => {
                if (window.cur_frm === frm) run();
            });
            return;
        }
        if (window.cur_frm === frm) run();
    }

    function scheduleRenderedActions(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const run = () => reconcileRenderedActions(frm);
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, RECONCILE_FRAME_KEY, run);
            return;
        }
        if (window.requestAnimationFrame) {
            window.requestAnimationFrame(() => {
                if (window.cur_frm === frm) run();
            });
            return;
        }
        if (window.cur_frm === frm) run();
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) {
            scheduleApply(frm);
        },
        refresh(frm) {
            scheduleApply(frm);
        },
        almdina_edit_session_changed(frm) {
            // Edit-state changes should not cause a second Cost render. The store
            // owns data, the presenter owns markup, and this owner only reconciles
            // permissions onto the markup already present.
            configureCostInputFields(frm);
            scheduleRenderedActions(frm);
        },
    });

    window.AlmdinaCostPermissionsUX = Object.freeze({
        apply,
        scheduleApply,
        reconcileRenderedActions,
        scheduleRenderedActions,
        can,
        canEditInlinePiecePrice,
        scrubCostData,
        flushPendingPriceEdits,
        discardPendingPriceEdits,
        pendingPricePieces,
    });
})();