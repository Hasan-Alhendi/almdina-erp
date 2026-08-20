(() => {
    "use strict";

    const EDGE_PROFILE_LOOKUP_METHOD = "almdina_erp.almdina_erp.services.edge_banding_lookup_service.get_order_edge_banding_options";

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
            order_details_section: "بيانات الطلب",
            customer: "العميل",
            order_date: "تاريخ الطلب",
            order_notes: "ملاحظات الطلب",
            board_section: "المادة والقشاط",
            board_description: "صنف اللوح",
            board_length_cm: "طول اللوح (سم)",
            board_width_cm: "عرض اللوح (سم)",
            default_edge_type: "نوع القشاط الافتراضي",
            edge_color: "لون القشاط",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.fields_dict[fieldname];
            if (field && field.df && field.df.label !== label) {
                frm.set_df_property(fieldname, "label", label);
            }
        });
        if (frm.fields_dict.board_description) {
            const description = "اكتب النوع والسماكة واللون في نص واحد، مثال: MDF أبيض 18 مم.";
            if (frm.fields_dict.board_description.df.description !== description) {
                frm.set_df_property("board_description", "description", description);
            }
        }
        if (frm.fields_dict.edge_color) {
            const description = "أدخل لون القشاط يدويًا لهذا الطلب.";
            if (frm.fields_dict.edge_color.df.description !== description) {
                frm.set_df_property("edge_color", "description", description);
            }
        }
    }

    function documentContext() {
        return window.AlmdinaDocumentContext;
    }

    function orderLookupName(frm) {
        return frm && frm.doc && !frm.is_new()
            ? String(frm.doc.name || "")
            : "";
    }

    function safeEdgeOptions(frm) {
        return (frm && frm._almdina_safe_edge_options_payload) || {
            options: [],
            include_financial: false,
        };
    }

    function applySafeEdgeOptions(frm, payload) {
        const resolved = payload || {};
        const options = Array.isArray(resolved.options) ? resolved.options : [];
        frm._almdina_safe_edge_options_payload = {
            options,
            include_financial: resolved.include_financial === true,
        };
        frm._almdina_safe_edge_options_loaded = true;

        // The legacy fast-entry renderer still has a direct Edge Banding Type
        // fallback. Mark its cache as resolved before it renders so non-master-data
        // users never fall through to that protected DocType lookup.
        frm._dco_edge_types = options.map(row => ({
            name: String(row.name || row.edge_type_name || ""),
            edge_type_name: String(row.edge_type_name || row.name || ""),
        })).filter(row => row.name);
        frm._dco_edge_types_loaded = true;

        if (
            window.AlmdinaDoorCuttingFastEntry
            && typeof window.AlmdinaDoorCuttingFastEntry.render === "function"
        ) {
            window.AlmdinaDoorCuttingFastEntry.render(frm);
        }
        return frm._almdina_safe_edge_options_payload;
    }

    function loadSafeEdgeOptions(frm) {
        if (!frm) return Promise.resolve({ options: [], include_financial: false });
        if (frm._almdina_safe_edge_options_loaded) {
            return Promise.resolve(safeEdgeOptions(frm));
        }
        if (frm._almdina_safe_edge_options_loading) {
            return frm._almdina_safe_edge_options_loading;
        }

        // Suppress the legacy master-data call synchronously. If the safe request
        // fails, this owner retries on the next form lifecycle event instead of
        // allowing a protected get_list() fallback to raise a permission popup.
        frm._dco_edge_types_loaded = true;
        frm._dco_edge_types = frm._dco_edge_types || [];

        const context = documentContext();
        const identity = context && typeof context.capture === "function"
            ? context.capture(frm)
            : null;
        const isCurrent = () => (
            !context
            || !identity
            || typeof context.isCurrent !== "function"
            || context.isCurrent(frm, identity)
        );

        const request = frappe.call({
            method: EDGE_PROFILE_LOOKUP_METHOD,
            args: { order_name: orderLookupName(frm) },
        }).then(response => {
            if (!isCurrent()) return safeEdgeOptions(frm);
            return applySafeEdgeOptions(frm, (response && response.message) || {});
        }).catch(error => {
            if (isCurrent()) {
                frm._almdina_safe_edge_options_loaded = false;
                console.error("Failed to load safe order edge options", error);
            }
            return safeEdgeOptions(frm);
        }).finally(() => {
            if (frm._almdina_safe_edge_options_loading === request) {
                frm._almdina_safe_edge_options_loading = null;
            }
        });
        frm._almdina_safe_edge_options_loading = request;
        return request;
    }

    function apply_factory_defaults(frm) {
        if (!frm.is_new() || frm._almdina_factory_defaults_loaded) return;
        frm._almdina_factory_defaults_loaded = true;
        const context = documentContext();
        const identity = context.capture(frm);

        return frappe.call({
            method: "almdina_erp.almdina_erp.services.order_defaults_service.get_order_defaults",
        }).then(r => {
            if (!context.isCurrent(frm, identity)) return;
            const values = r.message || {};
            const updates = {};
            if (values.kerf_mm !== undefined) updates.kerf_mm = values.kerf_mm;
            if (values.trim_margin_mm !== undefined) updates.trim_margin_mm = values.trim_margin_mm;
            if (values.cutting_cost_per_board_usd !== undefined) updates.cutting_cost_per_board_usd = values.cutting_cost_per_board_usd;
            if (values.packing_mode) updates.packing_mode = values.packing_mode;
            if (values.cutting_machine_type) updates.cutting_machine_type = values.cutting_machine_type;
            if (values.optimization_time_limit_sec !== undefined) updates.optimization_time_limit_sec = values.optimization_time_limit_sec;
            return frm.set_value(updates);
        }).catch(error => {
            if (context.isCurrent(frm, identity)) {
                delete frm._almdina_factory_defaults_loaded;
            }
            console.error("Failed to load Almdina ERP order defaults", error);
        });
    }

    function applyBoardTextDefaults(frm) {
        let changed = false;
        if (!Number(frm.doc.board_length_cm)) {
            frm.doc.board_length_cm = 244;
            changed = true;
        }
        if (!Number(frm.doc.board_width_cm)) {
            frm.doc.board_width_cm = 122;
            changed = true;
        }
        frm.doc.full_board_length_mm = Number(frm.doc.board_length_cm) * 10;
        frm.doc.full_board_width_mm = Number(frm.doc.board_width_cm) * 10;
        if (changed) {
            ["board_length_cm", "board_width_cm"].forEach(fieldname => {
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

    frappe.ui.form.on("Door Cutting Order", {
        onload(frm) {
            translateOrderMaterialLabels(frm);
            loadSafeEdgeOptions(frm);
            apply_factory_defaults(frm);
            applyBoardTextDefaults(frm);
        },
        refresh(frm) {
            translateOrderMaterialLabels(frm);
            loadSafeEdgeOptions(frm);
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
    });

    window.AlmdinaOrderEdgeOptions = Object.freeze({
        load: loadSafeEdgeOptions,
        snapshot: safeEdgeOptions,
    });
})();
