(() => {
    "use strict";

    const EDGE_PROFILE_LOOKUP_METHOD = "almdina_erp.almdina_erp.services.edge_banding_lookup_service.get_order_edge_banding_options";

    function translateOrderMaterialLabels(frm) {
        const labels = {
            order_details_section: "Order details",
            customer: "Customer",
            order_date: "Order Date",
            order_notes: "Order Notes",
            order_cutting_machine: "Cutting machine type",
            board_section: "Material and edge banding",
            board_description: "Board Item",
            board_length_cm: "Board length (cm)",
            board_width_cm: "Board width (cm)",
            default_edge_type: "Default edge banding type",
            edge_color: "Edge Color",
            allow_piece_mirroring: "Does this board type allow piece mirroring?",
        };
        Object.entries(labels).forEach(([fieldname, message]) => {
            const field = frm.fields_dict[fieldname];
            const label = __(message);
            if (field && field.df && field.df.label !== label) {
                frm.set_df_property(fieldname, "label", label);
            }
        });
        if (frm.fields_dict.board_description) {
            const description = __("Write the type, thickness, and color in one line, for example: white MDF 18 mm.");
            if (frm.fields_dict.board_description.df.description !== description) {
                frm.set_df_property("board_description", "description", description);
            }
        }
        if (frm.fields_dict.edge_color) {
            const description = __("Enter the edge color manually for this order.");
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

        // Frappe may return a jqXHR-like thenable rather than a native Promise.
        // Normalize at this boundary before using native Promise.finally().
        const request = Promise.resolve(
            frappe.call({
                method: EDGE_PROFILE_LOOKUP_METHOD,
                args: { order_name: orderLookupName(frm) },
            })
        ).then(response => {
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

        return Promise.resolve(
            frappe.call({
                method: "almdina_erp.almdina_erp.services.order_defaults_service.get_order_defaults",
            })
        ).then(r => {
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
        // New orders intentionally start blank. Existing documents keep their
        // persisted values; opening a form must never invent board dimensions.
        bindBoardDimensionInputs(frm);
        refreshBoardDimensionValidation(frm);
    }

    function liveFieldValue(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        const input = field && field.$input;
        if (input && typeof input.val === "function") return input.val();
        return frm && frm.doc ? frm.doc[fieldname] : undefined;
    }

    function positiveNumber(value) {
        if (value === null || value === undefined || String(value).trim() === "") return null;
        const number = Number(String(value).replace(",", "."));
        return Number.isFinite(number) && number > 0 ? number : null;
    }

    function boardDimensions(frm) {
        const length = positiveNumber(liveFieldValue(frm, "board_length_cm"));
        const width = positiveNumber(liveFieldValue(frm, "board_width_cm"));
        return {
            length,
            width,
            valid: length !== null && width !== null,
        };
    }

    function boardError(fieldname) {
        const label = fieldname === "board_length_cm"
            ? __("Board length must be a positive number.")
            : __("Board width must be a positive number.");
        return label;
    }

    function setBoardFieldError(frm, fieldname, message) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        const wrapper = field && field.$wrapper && field.$wrapper.get
            ? field.$wrapper.get(0)
            : null;
        if (!wrapper) return;
        let error = wrapper.querySelector(".dco-board-dimension-error");
        if (message) {
            if (!error) {
                error = document.createElement("div");
                error.className = "dco-board-dimension-error text-danger small mt-1";
                const inputWrapper = wrapper.querySelector(".control-input-wrapper") || wrapper;
                inputWrapper.appendChild(error);
            }
            error.textContent = message;
            const input = wrapper.querySelector("input");
            if (input) input.setAttribute("aria-invalid", "true");
        } else if (error) {
            error.remove();
            const input = wrapper.querySelector("input");
            if (input) input.removeAttribute("aria-invalid");
        }
    }

    function refreshBoardDimensionValidation(frm) {
        const dimensions = boardDimensions(frm);
        setBoardFieldError(
            frm,
            "board_length_cm",
            positiveNumber(liveFieldValue(frm, "board_length_cm")) === null
                ? boardError("board_length_cm")
                : "",
        );
        setBoardFieldError(
            frm,
            "board_width_cm",
            positiveNumber(liveFieldValue(frm, "board_width_cm")) === null
                ? boardError("board_width_cm")
                : "",
        );
        frm._almdinaBoardDimensions = dimensions;
        return dimensions;
    }

    function bindBoardDimensionInputs(frm) {
        ["board_length_cm", "board_width_cm"].forEach(fieldname => {
            const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
            const input = field && field.$input;
            const element = input && typeof input.get === "function" ? input.get(0) : null;
            if (!element || field.__almdinaDimensionValidationInput === element) return;
            field.__almdinaDimensionValidationInput = element;
            element.addEventListener("input", () => {
                refreshBoardDimensionValidation(frm);
                if (window.AlmdinaDoorCuttingFastEntry && typeof window.AlmdinaDoorCuttingFastEntry.refreshValidation === "function") {
                    window.AlmdinaDoorCuttingFastEntry.refreshValidation(frm);
                }
            });
        });
    }

    function notifyBoardRequired() {
        const message = __("Please enter board length and width first.");
        if (frappe && typeof frappe.msgprint === "function") {
            frappe.msgprint({ message, indicator: "orange" });
        }
        return message;
    }

    function syncBoardDimensions(frm) {
        const length = Number(frm.doc.board_length_cm || 0);
        const width = Number(frm.doc.board_width_cm || 0);
        frm.doc.full_board_length_mm = length * 10;
        frm.doc.full_board_width_mm = width * 10;
        frm.dirty();
        refreshBoardDimensionValidation(frm);
        if (window.AlmdinaDoorCuttingFastEntry && typeof window.AlmdinaDoorCuttingFastEntry.refreshValidation === "function") {
            window.AlmdinaDoorCuttingFastEntry.refreshValidation(frm);
        }
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

    window.AlmdinaOrderDimensionValidation = Object.freeze({
        boardDimensions,
        refreshBoardDimensionValidation,
        notifyBoardRequired,
        positiveNumber,
    });

    window.AlmdinaOrderEdgeOptions = Object.freeze({
        load: loadSafeEdgeOptions,
        snapshot: safeEdgeOptions,
    });
})();
