(() => {
    "use strict";

    function apply_factory_defaults(frm) {
        if (!frm.is_new() || frm._almdina_factory_defaults_loaded) return;
        frm._almdina_factory_defaults_loaded = true;

        frappe.call({
            method: "almdina_erp.almdina_erp.services.order_defaults_service.get_order_defaults",
        }).then(r => {
            const values = r.message || {};
            const updates = {};
            if (values.kerf_mm !== undefined) updates.kerf_mm = values.kerf_mm;
            if (values.trim_margin_mm !== undefined) updates.trim_margin_mm = values.trim_margin_mm;
            if (values.cutting_cost_per_board_usd !== undefined) updates.cutting_cost_per_board_usd = values.cutting_cost_per_board_usd;
            if (values.packing_mode) updates.packing_mode = values.packing_mode;
            return frm.set_value(updates);
        }).catch(error => console.error("Failed to load Almdina ERP order defaults", error));
    }

    function apply_board_defaults(frm) {
        if (!frm.doc.board_item || !["Draft", "Rejected", undefined, null, ""].includes(frm.doc.status)) return;
        const requestedItem = frm.doc.board_item;
        frappe.call({
            method: "almdina_erp.almdina_erp.services.order_defaults_service.get_board_defaults",
            args: { board_item: requestedItem },
        }).then(r => {
            if (frm.doc.board_item !== requestedItem) return;
            const values = r.message || {};
            return frm.set_value({
                board_material: values.board_material || "",
                board_color: values.board_color || "",
                board_thickness_mm: values.board_thickness_mm || 0,
                full_board_length_mm: values.board_length_mm || 0,
                full_board_width_mm: values.board_width_mm || 0,
                board_rate_usd: values.board_rate_usd || 0,
            });
        }).catch(error => console.error("Failed to load MDF board defaults", error));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload(frm) {
            apply_factory_defaults(frm);
            if (frm.is_new() && frm.doc.board_item) apply_board_defaults(frm);
        },
        board_item(frm) {
            apply_board_defaults(frm);
        },
    });
})();
