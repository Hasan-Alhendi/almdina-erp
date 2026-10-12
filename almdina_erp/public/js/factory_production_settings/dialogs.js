(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsDialogs) return;

    function create(options = {}) {
        const translate = options.translate;
        const escapeHtml = options.escapeHtml;
        if (typeof translate !== "function" || typeof escapeHtml !== "function") {
            throw new Error("Production Settings dialog dependencies are unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);
        const ownedSurfaces = new Map();
        const drafts = new Map();

        function rememberDraft(surface, draftKey) {
            if (!draftKey || !surface || typeof surface.get_values !== "function") return;
            const values = surface.get_values(true);
            if (values && typeof values === "object") drafts.set(draftKey, { ...values });
        }

        function own(surface, draftKey = "") {
            if (surface && typeof surface.hide === "function") {
                const key = String(draftKey || "");
                if (key) {
                    for (const [previous, previousKey] of ownedSurfaces) {
                        if (previousKey !== key) continue;
                        rememberDraft(previous, previousKey);
                        ownedSurfaces.delete(previous);
                        previous.hide();
                    }
                }
                ownedSurfaces.set(surface, key);
            }
            return surface;
        }

        function restoreDraft(surface, draftKey) {
            if (!drafts.has(draftKey) || !surface || typeof surface.set_values !== "function") return;
            surface.set_values(drafts.get(draftKey));
        }

        function complete(surface, draftKey) {
            drafts.delete(draftKey);
            if (!ownedSurfaces.has(surface)) return;
            ownedSurfaces.delete(surface);
            surface.hide();
        }

        function deactivate() {
            for (const [surface, draftKey] of ownedSurfaces) {
                rememberDraft(surface, draftKey);
                surface.hide();
            }
            ownedSurfaces.clear();
        }

        function dispose() {
            deactivate();
            drafts.clear();
        }

        function optimizationCatalog(current = {}) {
            return (current.optimization_catalog || [])
                .map((entry) => ({
                    id: String(entry && entry.id || "").trim(),
                    label: String(entry && entry.label || entry && entry.id || "").trim(),
                    available: entry && entry.available !== false,
                }))
                .filter((entry) => entry.id && entry.label);
        }

        function machineCatalog(current = {}) {
            return (current.machine_type_catalog || [])
                .map((entry) => ({
                    id: String(entry && entry.id || "").trim(),
                    label: String(entry && entry.label || entry && entry.id || "").trim(),
                }))
                .filter((entry) => entry.id && entry.label);
        }

        function catalogWithCurrent(catalog, value) {
            const normalized = String(value || "").trim();
            if (!normalized || catalog.some((entry) => entry.id === normalized)) return catalog;
            return [
                ...catalog,
                { id: normalized, label: normalized, available: true, compatibility: true },
            ];
        }

        function catalogLabel(catalog, value) {
            const normalized = String(value || "").trim();
            const entry = catalog.find((item) => item.id === normalized);
            return entry ? entry.label : normalized;
        }

        function sectionFields(section, current = {}) {
            const values = current.values || current;
            if (section === "cutting") {
                const algorithms = catalogWithCurrent(
                    optimizationCatalog(current),
                    values.default_packing_mode
                );
                const machines = catalogWithCurrent(
                    machineCatalog(current),
                    values.default_cutting_machine_type
                );
                return [
                    { fieldname: "default_packing_mode", fieldtype: "Select", label: t("Distribution algorithm"), options: algorithms.map(entry => entry.label).join("\n"), default: catalogLabel(algorithms, values.default_packing_mode), reqd: 1 },
                    { fieldname: "default_cutting_machine_type", fieldtype: "Select", label: t("Cutting machine type"), options: machines.map(entry => entry.label).join("\n"), default: catalogLabel(machines, values.default_cutting_machine_type), reqd: 1 },
                    { fieldname: "default_kerf_mm", fieldtype: "Float", label: t("Default kerf (mm)"), default: values.default_kerf_mm, reqd: 1 },
                    { fieldname: "default_trim_margin_mm", fieldtype: "Float", label: t("Trimming margin (mm)"), default: values.default_trim_margin_mm, reqd: 1 },
                    { fieldname: "default_optimization_time_limit_sec", fieldtype: "Float", label: t("Optimization timeout (seconds)"), default: values.default_optimization_time_limit_sec, reqd: 1 },
                    { fieldname: "optimal_search_piece_limit", fieldtype: "Int", label: t("Piece limit for optimal search"), default: values.optimal_search_piece_limit, reqd: 1 },
                ];
            }
            if (section === "costing") {
                return [
                    { fieldname: "default_cutting_cost_per_board_usd", fieldtype: "Currency", label: t("Cutting fee per board (USD)"), default: values.default_cutting_cost_per_board_usd, reqd: 1 },
                    { fieldname: "default_special_design_fee_usd", fieldtype: "Currency", label: t("Custom design drawing / piece"), default: values.default_special_design_fee_usd, reqd: 1 },
                    { fieldname: "default_special_cnc_fee_usd", fieldtype: "Currency", label: t("Custom CNC drawing / piece"), default: values.default_special_cnc_fee_usd, reqd: 1 },
                    { fieldname: "default_special_manual_edge_fee_usd", fieldtype: "Currency", label: t("Manual edge banding drawing / piece"), default: values.default_special_manual_edge_fee_usd, reqd: 1 },
                    { fieldname: "default_special_margin_percent", fieldtype: "Percent", label: t("Special door leaf margin"), default: values.default_special_margin_percent, reqd: 1 },
                ];
            }
            if (section === "extra_addons") {
                return [
                    { fieldname: "default_extra_double_unit_price_usd", fieldtype: "Currency", label: t("Double price per door leaf (USD)"), description: t("Sale price added automatically for each door leaf with the option enabled."), default: values.default_extra_double_unit_price_usd, reqd: 1 },
                    { fieldname: "default_extra_full_door_double_unit_price_usd", fieldtype: "Currency", label: t("Full door leaf double fee (USD)"), description: t("Processing fee added per original door leaf when full door leaf double is selected."), default: values.default_extra_full_door_double_unit_price_usd, reqd: 1 },
                    { fieldname: "default_extra_liner_unit_price_usd", fieldtype: "Currency", label: t("Liner price per door leaf (USD)"), description: t("Not used for the special door leaf; the special door leaf's liner stays within its all-inclusive special price."), default: values.default_extra_liner_unit_price_usd, reqd: 1 },
                    { fieldname: "default_extra_back_groove_unit_price_usd", fieldtype: "Currency", label: t("Back groove price per door leaf (USD)"), description: t("Not used for the special door leaf; the special door leaf's back groove stays within its all-inclusive special price."), default: values.default_extra_back_groove_unit_price_usd, reqd: 1 },
                    { fieldname: "default_extra_recessed_handle_cutout_unit_price_usd", fieldtype: "Currency", label: t("Hidden handle cutout price per door leaf (USD)"), default: values.default_extra_recessed_handle_cutout_unit_price_usd, reqd: 1 },
                ];
            }
            if (section === "print_identity") {
                return [
                    { fieldname: "print_factory_name", fieldtype: "Data", label: t("Factory name"), default: values.print_factory_name, reqd: 1 },
                    { fieldname: "print_factory_description", fieldtype: "Small Text", label: t("Factory brief overview"), default: values.print_factory_description, reqd: 1 },
                    { fieldname: "print_factory_address", fieldtype: "Small Text", label: t("Address"), default: values.print_factory_address, reqd: 1 },
                    { fieldname: "print_factory_contacts", fieldtype: "Small Text", label: t("Contact numbers"), description: t("One separate line for each number: landline / mobile / WhatsApp."), default: values.print_factory_contacts || "" },
                ];
            }
            if (section === "whatsapp_messages") {
                const stageRows = Array.isArray(current.whatsapp_stage_message_rows)
                    ? current.whatsapp_stage_message_rows
                    : [];
                return [
                    {
                        fieldname: "whatsapp_measurements_text",
                        fieldtype: "Small Text",
                        label: t("Measurements message"),
                        description: `${t("Attached with the PDF file in a single message on first send. Limit is 1024 characters. Use")} {order_name} ${t("for the order number.")}`,
                    },
                    {
                        fieldname: "whatsapp_measurement_amendments_text",
                        fieldtype: "Small Text",
                        label: t("Measurement changes message"),
                        description: `${t("Attached with the PDF file in a single message when sending edits. Limit is 1024 characters. Use")} {order_name} ${t("for the order number.")}`,
                    },
                    {
                        fieldname: "whatsapp_invoice_text",
                        fieldtype: "Small Text",
                        label: t("Invoice message"),
                        description: `${t("Attached with the PDF file in a single message. Limit is 1024 characters. Use")} {order_name} ${t("for the order number.")}`,
                    },
                    ...stageRows.map(row => ({
                        fieldname: stageMessageFieldname(row && row.id),
                        fieldtype: "Small Text",
                        label: `${t("Completion message")} — ${row && row.label ? row.label : row && row.id}`,
                        description: `${t("Sent when this stage is completed. Use")} {order_name} ${t("and")} {stage_label}.`,
                    })),
                ];
            }
            if (section === "backup_restore") {
                const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
                return [
                    { fieldname: "local_section", fieldtype: "Section Break", label: t("Local Backup") },
                    { fieldname: "local_backup_enabled", fieldtype: "Check", label: t("Enable Local Backup"), default: values.local_backup_enabled },
                    { fieldname: "local_backup_frequency", fieldtype: "Select", label: t("Schedule"), options: "Daily\nWeekly\nMonthly", default: values.local_backup_frequency || "Daily", reqd: 1 },
                    { fieldname: "local_backup_time", fieldtype: "Time", label: t("Time"), default: values.local_backup_time || "02:00", reqd: 1 },
                    { fieldname: "local_backup_weekday", fieldtype: "Select", label: t("Day of Week"), options: weekdays.join("\n"), default: values.local_backup_weekday || "Monday", depends_on: "eval:doc.local_backup_frequency==='Weekly'" },
                    { fieldname: "local_backup_day_of_month", fieldtype: "Int", label: t("Day of Month"), default: values.local_backup_day_of_month || 1, depends_on: "eval:doc.local_backup_frequency==='Monthly'" },
                    { fieldname: "local_backup_retention", fieldtype: "Int", label: t("Keep Last N Backups"), default: values.local_backup_retention || 7, reqd: 1 },
                    { fieldname: "external_section", fieldtype: "Section Break", label: t("External Backup — SSH") },
                    { fieldname: "external_backup_enabled", fieldtype: "Check", label: t("Enable External Backup"), default: values.external_backup_enabled },
                    { fieldname: "external_backup_frequency", fieldtype: "Select", label: t("Schedule"), options: "Daily\nWeekly\nMonthly", default: values.external_backup_frequency || "Daily", reqd: 1 },
                    { fieldname: "external_backup_time", fieldtype: "Time", label: t("Time"), default: values.external_backup_time || "03:00", reqd: 1 },
                    { fieldname: "external_backup_weekday", fieldtype: "Select", label: t("Day of Week"), options: weekdays.join("\n"), default: values.external_backup_weekday || "Monday", depends_on: "eval:doc.external_backup_frequency==='Weekly'" },
                    { fieldname: "external_backup_day_of_month", fieldtype: "Int", label: t("Day of Month"), default: values.external_backup_day_of_month || 1, depends_on: "eval:doc.external_backup_frequency==='Monthly'" },
                    { fieldname: "external_backup_retention", fieldtype: "Int", label: t("Keep Last N Backups"), default: values.external_backup_retention || 4, reqd: 1 },
                    { fieldname: "ssh_section", fieldtype: "Section Break", label: t("SSH Connection") },
                    { fieldname: "ssh_host", fieldtype: "Data", label: t("SSH Host"), default: values.ssh_host || "" },
                    { fieldname: "ssh_port", fieldtype: "Int", label: t("SSH Port"), default: values.ssh_port || 22 },
                    { fieldname: "ssh_username", fieldtype: "Data", label: t("SSH Username"), default: values.ssh_username || "" },
                    { fieldname: "ssh_auth_method", fieldtype: "Select", label: t("Authentication Method"), options: "Private Key\nPassword", default: values.ssh_auth_method || "Private Key" },
                    { fieldname: "ssh_password", fieldtype: "Password", label: t("SSH Password"), description: values.ssh_password_configured ? t("Password is saved. Leave the field empty to keep it.") : t("Stored encrypted through Frappe and never returned to the browser."), depends_on: "eval:doc.ssh_auth_method==='Password'" },
                    { fieldname: "ssh_private_key", fieldtype: "Code", options: "text", label: t("SSH Private Key"), description: values.ssh_private_key_configured ? t("Key is saved. Leave the field empty to keep it.") : t("Paste the private key; it will be stored encrypted through Frappe."), depends_on: "eval:doc.ssh_auth_method==='Private Key'" },
                    { fieldname: "ssh_private_key_passphrase", fieldtype: "Password", label: t("Private Key Passphrase (Optional)"), description: values.ssh_private_key_passphrase_configured ? t("Passphrase is saved. Leave the field empty to keep it.") : "", depends_on: "eval:doc.ssh_auth_method==='Private Key'" },
                    { fieldname: "remote_backup_path", fieldtype: "Data", label: t("Remote Backup Path"), description: t("Absolute non-root POSIX path. The server key must be registered beforehand in known_hosts for the bench user."), default: values.remote_backup_path || "" },
                ];
            }
            return [
                { fieldname: "default_production_routing", fieldtype: "Select", label: t("Default production route (optional)"), options: ["", ...(current.routing_options || [])].join("\n"), default: values.default_production_routing || "", reqd: 0 },
                { fieldname: "allow_stage_override", fieldtype: "Check", label: t("Allow bypassing stage sequence"), default: values.allow_stage_override },
                { fieldname: "allow_unplaced_approval", fieldtype: "Check", label: t("Exceptional approval of unallocated pieces"), default: values.allow_unplaced_approval },
            ];
        }

        function sectionTitle(section) {
            if (section === "cutting") return t("Edit cutting and optimizer");
            if (section === "costing") return t("Edit default cost");
            if (section === "extra_addons") return t("Edit door leaf add-on prices");
            if (section === "print_identity") return t("Edit print sheet identity");
            if (section === "whatsapp_messages") return t("Edit WhatsApp messages");
            if (section === "backup_restore") return t("Backup & Restore settings");
            return t("Edit production controls");
        }

        function stageMessageFieldname(id) {
            return `whatsapp_stage_msg__${String(id || "").replace(/[^A-Za-z0-9_]/g, "_")}`;
        }

        function fieldInputValue(dialog, fieldname, fallback) {
            const field = dialog && dialog.fields_dict && dialog.fields_dict[fieldname];
            if (field && field.$input && typeof field.$input.val === "function") {
                return field.$input.val();
            }
            return fallback == null ? "" : fallback;
        }

        function normalizeSectionPayload(section, current, payload = {}, dialog) {
            if (section === "whatsapp_messages") {
                const stageMessages = {};
                for (const row of current.whatsapp_stage_message_rows || []) {
                    if (!row || !row.id) continue;
                    stageMessages[row.id] = fieldInputValue(
                        dialog,
                        stageMessageFieldname(row.id),
                        payload[stageMessageFieldname(row.id)]
                    );
                }
                return {
                    whatsapp_measurements_text: fieldInputValue(
                        dialog,
                        "whatsapp_measurements_text",
                        payload.whatsapp_measurements_text
                    ),
                    whatsapp_measurement_amendments_text: fieldInputValue(
                        dialog,
                        "whatsapp_measurement_amendments_text",
                        payload.whatsapp_measurement_amendments_text
                    ),
                    whatsapp_invoice_text: fieldInputValue(
                        dialog,
                        "whatsapp_invoice_text",
                        payload.whatsapp_invoice_text
                    ),
                    whatsapp_stage_messages: stageMessages,
                };
            }
            if (section !== "cutting") return payload;
            const values = current.values || current;
            const algorithms = catalogWithCurrent(
                optimizationCatalog(current),
                values.default_packing_mode
            );
            const machines = catalogWithCurrent(
                machineCatalog(current),
                values.default_cutting_machine_type
            );
            const algorithm = algorithms.find(entry => entry.label === payload.default_packing_mode);
            const machine = machines.find(entry => entry.label === payload.default_cutting_machine_type);
            return {
                ...payload,
                default_packing_mode: algorithm ? algorithm.id : payload.default_packing_mode,
                default_cutting_machine_type: machine ? machine.id : payload.default_cutting_machine_type,
            };
        }

        function disableUnavailableAlgorithms(dialog, current) {
            const field = dialog && dialog.fields_dict && dialog.fields_dict.default_packing_mode;
            const input = field && field.$input;
            if (!input || !input.length) return;
            const unavailableLabels = new Set(
                optimizationCatalog(current)
                    .filter(entry => !entry.available)
                    .map(entry => entry.label)
            );
            input.find("option").each((_, option) => {
                const $option = $(option);
                if (!unavailableLabels.has(String($option.val() || ""))) return;
                $option.prop("disabled", true);
                $option.text(`${$option.text()} — ${t("Currently unavailable")}`);
            });
        }

        function openSection(config = {}) {
            const draftKey = `section:${config.section}`;
            const current = config.current || {};
            const dialog = own(new frappe.ui.Dialog({
                title: sectionTitle(config.section),
                fields: sectionFields(config.section, current),
                primary_action_label: t("Save changes"),
                primary_action(payload) {
                    const button = dialog.get_primary_btn();
                    button.prop("disabled", true);
                    let action;
                    try {
                        const normalizedPayload = normalizeSectionPayload(
                            config.section,
                            current,
                            payload,
                            dialog
                        );
                        action = config.onSubmit ? config.onSubmit(normalizedPayload) : Promise.resolve();
                    } catch (error) {
                        action = Promise.reject(error);
                    }
                    Promise.resolve(action)
                        .then(() => {
                            complete(dialog, draftKey);
                        })
                        .catch(error => {
                            if (!ownedSurfaces.has(dialog)) return;
                            const fallback = t("An unexpected error occurred.");
                            const message = error && error.message ? error.message : fallback;
                            own(frappe.msgprint({
                                title: t("Could not save"),
                                message: escapeHtml(message),
                                indicator: "red",
                            }));
                        })
                        .finally(() => {
                            if (ownedSurfaces.has(dialog)) button.prop("disabled", false);
                        });
                },
            }), draftKey);
            restoreDraft(dialog, draftKey);
            dialog.show();
            if (config.section === "whatsapp_messages" && !drafts.has(draftKey)) {
                const values = current.values || current;
                if (typeof dialog.set_values === "function") {
                    const nextValues = {
                        whatsapp_measurements_text: values.whatsapp_measurements_text || "",
                        whatsapp_measurement_amendments_text: values.whatsapp_measurement_amendments_text || "",
                        whatsapp_invoice_text: values.whatsapp_invoice_text || "",
                    };
                    for (const row of current.whatsapp_stage_message_rows || []) {
                        if (!row || !row.id) continue;
                        nextValues[stageMessageFieldname(row.id)] = row.text || "";
                    }
                    dialog.set_values(nextValues);
                }
            }
            if (config.section === "cutting") disableUnavailableAlgorithms(dialog, current);
            return dialog;
        }

        function openAudit(initialHtml) {
            const dialog = own(new frappe.ui.Dialog({
                title: t("Factory settings change log"),
                size: "large",
                fields: [{ fieldname: "audit_html", fieldtype: "HTML" }],
            }));
            const $wrapper = dialog.fields_dict.audit_html.$wrapper;
            $wrapper.html(String(initialHtml || ""));
            dialog.show();
            return Object.freeze({
                dialog,
                setHtml(html) { $wrapper.html(String(html || "")); },
            });
        }

        function showSaved() {
            frappe.show_alert({ message: t("Factory settings updated."), indicator: "green" });
        }

        function openQr(config = {}) {
            const dialog = own(new frappe.ui.Dialog({
                title: t("Scan WhatsApp code"),
                fields: [{ fieldname: "qr_html", fieldtype: "HTML" }],
                on_hide() {
                    if (typeof config.onHide === "function") config.onHide();
                },
            }));
            const $wrapper = dialog.fields_dict.qr_html.$wrapper;
            function setQr(dataUrl, status) {
                const source = String(dataUrl || "");
                const safeSource = source.indexOf("data:image/") === 0 ? source : "";
                $wrapper.html(`
                    <div class="aps-whatsapp-qr">
                        <p>${escapeHtml(config.statusLabel ? config.statusLabel(status) : String(status || t("Waiting for code scan")))}</p>
                        ${safeSource ? `<img alt="${escapeHtml(t("QR code"))}" src="${escapeHtml(safeSource)}">` : `<div class="aps-whatsapp-qr-wait">${t("Preparing the code...")}</div>`}
                        <small>${t("The code refreshes every 5 seconds. Scan it from WhatsApp on your phone.")}</small>
                    </div>
                `);
            }
            dialog.show();
            return Object.freeze({
                dialog,
                setQr,
                close() {
                    complete(dialog);
                },
            });
        }

        function openRestore(config = {}) {
            const phrase = String(config.confirmationPhrase || "");
            const dialog = own(new frappe.ui.Dialog({
                title: t("Restore backup"),
                fields: [
                    {
                        fieldname: "warning",
                        fieldtype: "HTML",
                        options: `<div class="aps-restore-warning"><strong>${escapeHtml(t("Warning: Restore replaces the current database and files."))}</strong><span>${escapeHtml(t("The system will first create a full backup, then use Frappe Restore and run migrate."))}</span><code>${escapeHtml(phrase)}</code></div>`,
                    },
                    { fieldname: "confirmation", fieldtype: "Data", label: t("Type the confirmation phrase as shown above"), reqd: 1 },
                ],
                primary_action_label: t("Create backup, then Restore"),
                primary_action(values) {
                    const confirmation = String(values.confirmation || "").trim();
                    if (confirmation !== phrase) {
                        frappe.msgprint({ title: t("Confirmation does not match"), message: t("Type the confirmation phrase exactly."), indicator: "red" });
                        return;
                    }
                    const button = dialog.get_primary_btn();
                    button.prop("disabled", true);
                    Promise.resolve(config.onSubmit ? config.onSubmit(confirmation) : null)
                        .then(() => complete(dialog))
                        .catch(error => {
                            if (!ownedSurfaces.has(dialog)) return;
                            frappe.msgprint({
                                title: t("Could not start the restore"),
                                message: escapeHtml(error && error.message ? error.message : t("An unexpected error occurred.")),
                                indicator: "red",
                            });
                        })
                        .finally(() => {
                            if (ownedSurfaces.has(dialog)) button.prop("disabled", false);
                        });
                },
            }));
            dialog.show();
            return dialog;
        }

        return Object.freeze({
            sectionFields,
            sectionTitle,
            openSection,
            openAudit,
            openQr,
            openRestore,
            showSaved,
            deactivate,
            dispose,
        });
    }

    window.AlmdinaFactoryProductionSettingsDialogs = Object.freeze({ create });
})();
