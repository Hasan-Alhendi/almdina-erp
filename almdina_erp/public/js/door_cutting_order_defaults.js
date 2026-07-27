(() => {
    "use strict";

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function translateOrderMaterialLabels(frm) {
        if (!isArabic()) return;
        const labels = {
            board_section: "اللوح",
            board_description: "صنف اللوح",
            board_length_cm: "طول اللوح (سم)",
            board_width_cm: "عرض اللوح (سم)",
            cutting_settings_section: "إعدادات مواد وتكلفة الطلب",
            edge_color: "لون القشاط",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            if (frm.fields_dict[fieldname]) frm.set_df_property(fieldname, "label", label);
        });
        if (frm.fields_dict.board_description) {
            frm.set_df_property(
                "board_description",
                "description",
                "اكتب النوع والسماكة واللون في نص واحد، مثال: MDF أبيض 18 مم."
            );
        }
        if (frm.fields_dict.edge_color) {
            frm.set_df_property(
                "edge_color",
                "description",
                "يُجلب تلقائيًا من نوع القشاط، ويمكن تعديله لهذا الطلب."
            );
        }
    }

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
            if (values.cutting_machine_type) updates.cutting_machine_type = values.cutting_machine_type;
            if (values.optimization_time_limit_sec !== undefined) updates.optimization_time_limit_sec = values.optimization_time_limit_sec;
            return frm.set_value(updates);
        }).catch(error => console.error("Failed to load Almdina ERP order defaults", error));
    }

    function applyBoardTextDefaults(frm) {
        let changed = false;
        if (!String(frm.doc.board_description || "").trim() && frm.doc.board_item) {
            frm.doc.board_description = frm.doc.board_item;
            changed = true;
        }
        if (!Number(frm.doc.board_length_cm)) {
            frm.doc.board_length_cm = Number(frm.doc.full_board_length_mm || 0) / 10 || 244;
            changed = true;
        }
        if (!Number(frm.doc.board_width_cm)) {
            frm.doc.board_width_cm = Number(frm.doc.full_board_width_mm || 0) / 10 || 122;
            changed = true;
        }
        frm.doc.full_board_length_mm = Number(frm.doc.board_length_cm || 244) * 10;
        frm.doc.full_board_width_mm = Number(frm.doc.board_width_cm || 122) * 10;
        if (changed) {
            ["board_description", "board_length_cm", "board_width_cm"].forEach(fieldname => {
                if (frm.fields_dict[fieldname]) frm.refresh_field(fieldname);
            });
        }
    }

    function syncBoardDimensions(frm) {
        const length = Number(frm.doc.board_length_cm || 0);
        const width = Number(frm.doc.board_width_cm || 0);
        frm.doc.full_board_length_mm = length * 10;
        frm.doc.full_board_width_mm = width * 10;
        frm.dirty();
    }

    function apply_edge_color_default(frm, force = false) {
        const requestedType = frm.doc.default_edge_type;
        if (!requestedType) {
            if (force && frm.doc.edge_color) return frm.set_value("edge_color", "");
            return Promise.resolve();
        }
        if (!force && String(frm.doc.edge_color || "").trim()) return Promise.resolve();

        return frappe.db.get_value("Edge Banding Type", requestedType, "edge_color")
            .then(r => {
                if (frm.doc.default_edge_type !== requestedType) return;
                const color = (r && r.message && r.message.edge_color) || "";
                if (force || !String(frm.doc.edge_color || "").trim()) {
                    return frm.set_value("edge_color", color);
                }
            })
            .catch(error => console.error("Failed to load edge color default", error));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload(frm) {
            translateOrderMaterialLabels(frm);
            apply_factory_defaults(frm);
            applyBoardTextDefaults(frm);
            if (frm.doc.default_edge_type && !frm.doc.edge_color) apply_edge_color_default(frm, false);
        },
        refresh(frm) {
            translateOrderMaterialLabels(frm);
            applyBoardTextDefaults(frm);
        },
        board_description(frm) {
            if (window.AlmdinaBoardTextUX) window.AlmdinaBoardTextUX.refresh(frm);
        },
        board_length_cm(frm) {
            syncBoardDimensions(frm);
        },
        board_width_cm(frm) {
            syncBoardDimensions(frm);
        },
        default_edge_type(frm) {
            apply_edge_color_default(frm, true);
        },
    });
})();
