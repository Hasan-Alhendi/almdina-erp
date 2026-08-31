(() => {
    "use strict";

    if (window.AlmdinaOrderMutationImpactPolicy) return;

    const IMPACT_KEY = "__almdinaWorkspaceMutationImpact";
    const SPECIAL_PRICE_BASIS_FIELDS = new Set([
        "width_cm",
        "length_cm",
        "qty",
        "piece_type",
    ]);
    const ORDER_PLAN_COST_FIELDS = [
        "board_description",
        "board_length_cm",
        "board_width_cm",
        "default_edge_type",
    ];
    const PIECE_PLAN_COST_FIELDS = [
        "width_cm",
        "length_cm",
        "qty",
        "piece_type",
        "allow_rotation",
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
        "edge_long_right_type_override",
        "edge_long_left_type_override",
        "edge_width_top_type_override",
        "edge_width_bottom_type_override",
        "clipped_corner_position",
        "clipped_corner_width_cm",
        "clipped_corner_length_cm",
        "special_shape_geometry_json",
        "extra_full_door_double",
    ];
    const PIECE_COST_ONLY_FIELDS = [
        "extra_double",
        "extra_liner",
        "extra_recessed_handle_cutout",
    ];

    function syncCoordinator() {
        return window.AlmdinaWorkspaceSyncCoordinator || null;
    }

    function normalizeResources(values) {
        return [...new Set((values || []).map((value) => String(value || "").trim()).filter(Boolean))];
    }

    function pendingImpact(frm) {
        if (!frm) return null;
        if (!frm[IMPACT_KEY]) {
            frm[IMPACT_KEY] = {
                resources: [],
                reasons: [],
                specialPriceBasisChanged: false,
            };
        }
        return frm[IMPACT_KEY];
    }

    function recordImpact(frm, resources, reason, options = {}) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        const impact = pendingImpact(frm);
        impact.resources = normalizeResources([...(impact.resources || []), ...(resources || [])]);
        if (reason && !impact.reasons.includes(reason)) impact.reasons.push(reason);
        if (options.specialPriceBasisChanged) impact.specialPriceBasisChanged = true;

        const coordinator = syncCoordinator();
        if (coordinator && typeof coordinator.invalidate === "function") {
            coordinator.invalidate(frm, resources, reason || "order_inputs_changed");
        }
        return true;
    }

    function childRow(frm, cdt, cdn) {
        if (typeof locals !== "undefined" && locals[cdt] && locals[cdt][cdn]) {
            return locals[cdt][cdn];
        }
        return (frm && frm.doc && frm.doc.pieces || []).find((row) => row && row.name === cdn) || null;
    }

    function markSpecialPriceBasisStale(row, fieldname) {
        if (!row || !SPECIAL_PRICE_BASIS_FIELDS.has(fieldname)) return false;
        if ((row.piece_type || "Regular") !== "Special" && row.special_shape_price_status !== "Approved") {
            return false;
        }
        row.__almdina_special_price_basis_stale = true;
        row.__almdina_special_price_basis_stale_field = fieldname;
        return true;
    }

    function onOrderInputChanged(frm) {
        recordImpact(frm, ["plan", "cost"], "order_inputs_changed");
    }

    function onPieceCollectionChanged(frm) {
        // Frappe emits pieces_add / pieces_remove for child-table structural changes.
        // There may be no surviving row/field event after a deletion, so the
        // collection event itself must invalidate both derived workspaces.
        recordImpact(frm, ["plan", "cost"], "order_inputs_changed");
    }

    function onPieceInputChanged(fieldname, frm, cdt, cdn) {
        const row = childRow(frm, cdt, cdn);
        const specialPriceChanged = markSpecialPriceBasisStale(row, fieldname);
        recordImpact(
            frm,
            ["plan", "cost"],
            specialPriceChanged ? "special_price_basis_changed" : "order_inputs_changed",
            { specialPriceBasisChanged: specialPriceChanged }
        );
    }

    function onPieceCostInputChanged(fieldname, frm) {
        recordImpact(frm, ["cost"], `extra_addon_changed:${fieldname}`);
    }

    function planNeedsRecalculation(frm) {
        if (Number(frm && frm.doc && frm.doc.plan_needs_recalculation || 0) === 1) return true;
        const owner = window.AlmdinaPlanWorkspaceState;
        const state = owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
        const plans = state && state.data && state.data.plans;
        const system = plans && plans.system_draft;
        return Boolean(system && system.validation && system.validation.needs_recalculation);
    }

    function clearSpecialPriceStaleMarkers(frm) {
        (frm && frm.doc && frm.doc.pieces || []).forEach((row) => {
            if (!row) return;
            delete row.__almdina_special_price_basis_stale;
            delete row.__almdina_special_price_basis_stale_field;
        });
    }

    async function reconcileAfterSave(frm) {
        const impact = frm && frm[IMPACT_KEY];
        if (!impact || !(impact.resources || []).length) return false;
        frm[IMPACT_KEY] = null;

        const coordinator = syncCoordinator();
        if (!coordinator || typeof coordinator.refresh !== "function") return false;

        // Saving the order workspace must not immediately pay the hidden Plan/Cost
        // read cost. Their stores are already invalidated above; refresh only a
        // derived workspace that is actually visible, and let tab activation
        // resolve the rest later from the canonical server state.
        await coordinator.refresh(frm, impact.resources, {
            force: false,
            activeOnly: true,
            reason: "order_saved",
        });
        clearSpecialPriceStaleMarkers(frm);

        // The refreshed Cost snapshot now contains the authoritative special-price
        // status, but board/cutting totals still belong to the last calculated Plan.
        // Keep Cost visibly stale until the Plan dependency itself is recalculated.
        if (
            impact.resources.includes("cost")
            && impact.resources.includes("plan")
            && planNeedsRecalculation(frm)
        ) {
            coordinator.invalidate(frm, ["cost"], "plan_recalculation_required");
        }
        return true;
    }

    const orderHandlers = {
        after_save(frm) {
            reconcileAfterSave(frm).catch((error) => {
                console.error("DCO workspace reconciliation after save failed", error);
            });
        },
    };
    ORDER_PLAN_COST_FIELDS.forEach((fieldname) => {
        orderHandlers[fieldname] = onOrderInputChanged;
    });
    frappe.ui.form.on("Door Cutting Order", orderHandlers);

    const pieceHandlers = {
        pieces_add: onPieceCollectionChanged,
        pieces_remove: onPieceCollectionChanged,
    };
    PIECE_PLAN_COST_FIELDS.forEach((fieldname) => {
        pieceHandlers[fieldname] = (frm, cdt, cdn) => onPieceInputChanged(fieldname, frm, cdt, cdn);
    });
    PIECE_COST_ONLY_FIELDS.forEach((fieldname) => {
        pieceHandlers[fieldname] = (frm) => onPieceCostInputChanged(fieldname, frm);
    });
    frappe.ui.form.on("Door Cutting Order Detail", pieceHandlers);

    window.AlmdinaOrderMutationImpactPolicy = Object.freeze({
        SPECIAL_PRICE_BASIS_FIELDS,
        ORDER_PLAN_COST_FIELDS,
        PIECE_PLAN_COST_FIELDS,
        PIECE_COST_ONLY_FIELDS,
        recordImpact,
        reconcileAfterSave,
        planNeedsRecalculation,
    });
})();