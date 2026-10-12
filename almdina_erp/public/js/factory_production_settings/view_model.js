(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsViewModel) return;

    function create(options = {}) {
        const translate = options.translate;
        if (typeof translate !== "function") {
            throw new Error("Production Settings view-model translator is unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);

        function values(current = {}) {
            return current.values || current || {};
        }

        function sectionEditable(current, section) {
            return Boolean(
                current
                && current.permissions
                && current.permissions.sections
                && current.permissions.sections[section]
                && current.permissions.sections[section].editable
            );
        }

        function canManageWhatsAppSession(current) {
            return Boolean(current && current.permissions && current.permissions.can_manage_whatsapp_session);
        }

        function canManageBackups(current) {
            return Boolean(current && current.permissions && current.permissions.can_manage_backups);
        }

        function canRestoreBackups(current) {
            return Boolean(current && current.permissions && current.permissions.can_restore_backups);
        }

        function yesNo(value) {
            return Number(value || 0) ? t("Yes") : t("No");
        }

        function display(value, fallback = "—") {
            return value === undefined || value === null || value === "" ? fallback : value;
        }

        function catalogLabel(current, catalogName, value) {
            const normalized = String(value || "").trim();
            if (!normalized) return "—";
            const catalog = Array.isArray(current && current[catalogName])
                ? current[catalogName]
                : [];
            const entry = catalog.find(item => String(item && item.id || "").trim() === normalized);
            return entry ? String(entry.label || entry.id || normalized) : normalized;
        }

        function section(key, title, description, rows, current) {
            return {
                key,
                title,
                description,
                editable: sectionEditable(current, key),
                rows: rows.map(([label, value, multiline = false]) => ({
                    label,
                    value: display(value),
                    multiline,
                })),
            };
        }

        function sections(current = {}) {
            const source = values(current);
            return [
                section("cutting", t("Cutting and optimizer"), t("Default geometry, distribution algorithm, and search limits."), [
                    [t("Default kerf (mm)"), source.default_kerf_mm],
                    [t("Trimming margin (mm)"), source.default_trim_margin_mm],
                    [t("Algorithm"), t(catalogLabel(current, "optimization_catalog", source.default_packing_mode))],
                    [t("Cutting machine type"), t(catalogLabel(current, "machine_type_catalog", source.default_cutting_machine_type))],
                    [t("Optimization timeout (s)"), source.default_optimization_time_limit_sec],
                    [t("Piece limit for optimal search"), source.optimal_search_piece_limit],
                ], current),
                section("costing", t("Default cost"), t("Cutting fee, special door leaf charges, and their default margins."), [
                    [t("Cutting fee / board"), `${display(source.default_cutting_cost_per_board_usd)} USD`],
                    [t("Custom design drawing"), `${display(source.default_special_design_fee_usd)} USD`],
                    [t("Custom CNC drawing"), `${display(source.default_special_cnc_fee_usd)} USD`],
                    [t("Manual edge banding drawing"), `${display(source.default_special_manual_edge_fee_usd)} USD`],
                    [t("Special door leaf margin"), `${display(source.default_special_margin_percent)}%`],
                ], current),
                section("extra_addons", t("Door leaf add-ons"), t("Fixed sale prices per door leaf. The order stores a copy of the price at the time it is created, and existing orders are not affected later."), [
                    [t("Double / door leaf"), `${display(source.default_extra_double_unit_price_usd)} USD`],
                    [t("Full door leaf double fee"), `${display(source.default_extra_full_door_double_unit_price_usd)} USD`],
                    [t("Liner / door leaf"), `${display(source.default_extra_liner_unit_price_usd)} USD`],
                    [t("Back groove / door leaf"), `${display(source.default_extra_back_groove_unit_price_usd)} USD`],
                    [t("Hidden handle cutout / door leaf"), `${display(source.default_extra_recessed_handle_cutout_unit_price_usd)} USD`],
                ], current),
                section("production", t("Production controls"), t("The default route can be left empty and routes built from the route management screen. A real route must be selected when sending the order to production."), [
                    [t("Default production route"), source.default_production_routing || t("Not specified")],
                    [t("Bypass stage sequence"), source.allow_stage_override ? t("Allowed") : t("Denied")],
                    [t("Approve unallocated pieces"), source.allow_unplaced_approval ? t("Allowed") : t("Denied")],
                ], current),
                section("print_identity", t("Print sheet identity"), t("This data appears automatically on the measurements printout, cutting plan, and customer invoice."), [
                    [t("Factory name"), source.print_factory_name],
                    [t("Factory overview"), source.print_factory_description],
                    [t("Address"), source.print_factory_address],
                    [t("Contact numbers"), source.print_factory_contacts || "—", true],
                ], current),
                section("whatsapp_messages", t("WhatsApp messages"), `${t("The measurements text, its edits, and the invoice are attached with the PDF file in one message limited to 1024 characters. Stage completion messages remain text from the production route. Use")} {order_name} ${t("for the order number and")} {stage_label} ${t("for the stage name.")}`, [
                    [t("Measurements message"), source.whatsapp_measurements_text, true],
                    [t("Measurement changes message"), source.whatsapp_measurement_amendments_text, true],
                    [t("Invoice message"), source.whatsapp_invoice_text, true],
                    ...((current && current.whatsapp_stage_message_rows) || []).map(row => [
                        `${t("Completion message")} — ${display(row && row.label)}`,
                        row && row.text,
                        true,
                    ]),
                ], current),
                ...(canManageBackups(current) ? [section("backup_restore", t("Backup & Restore"), t("Independent local and external backups built on the official Frappe mechanism, with separate retention and a secure SFTP connection."), [
                    [t("Local backup"), source.local_backup_enabled ? t("Enabled") : t("Disabled")],
                    [t("Local schedule"), `${t(source.local_backup_frequency || "Daily")} · ${display(source.local_backup_time, "02:00")}`],
                    [t("Local retention"), `${t("Other")} ${display(source.local_backup_retention, 7)} ${t("Backups")}`],
                    [t("External backup"), source.external_backup_enabled ? t("Enabled") : t("Disabled")],
                    [t("External schedule"), `${t(source.external_backup_frequency || "Daily")} · ${display(source.external_backup_time, "03:00")}`],
                    [t("External retention"), `${t("Other")} ${display(source.external_backup_retention, 4)} ${t("Backups")}`],
                    [t("SSH server"), source.ssh_host ? `${source.ssh_host}:${display(source.ssh_port, 22)}` : t("Not configured")],
                    [t("SSH user"), source.ssh_username || t("Not configured")],
                    [t("Authentication method"), t(source.ssh_auth_method || "Private Key")],
                    [t("Remote path"), source.remote_backup_path || t("Not configured")],
                    [t("Credentials"), (source.ssh_password_configured || source.ssh_private_key_configured) ? t("Saved securely") : t("Not set up")],
                ], current)] : []),
            ];
        }

        function legacy(current = {}) {
            const source = current.legacy_values || {};
            if (!source || typeof source !== "object") return [];
            return [
                [t("Legacy stock control"), yesNo(source.enforce_stock_control)],
                [t("Legacy default warehouse"), display(source.default_warehouse)],
                [t("Reserve stock on approval"), yesNo(source.reserve_stock_on_approval)],
                [t("Stock consumption point"), display(source.stock_consumption_point)],
                [t("Prefer board remnants before full boards"), yesNo(source.prefer_remnants_before_full_boards)],
                [t("Minimum remnant width (mm)"), display(source.min_remnant_width_mm)],
                [t("Minimum remnant length (mm)"), display(source.min_remnant_length_mm)],
                [t("Minimum remnant area (m²)"), display(source.min_remnant_area_m2)],
                [t("Remnant cost policy"), display(source.remnant_cost_policy)],
                [t("Remnant price / m²"), `${display(source.remnant_rate_usd_per_m2)} USD`],
            ].map(([label, value]) => ({ label, value }));
        }

        function page(current = {}) {
            return {
                sections: sections(current),
                legacy: legacy(current),
                hasLegacy: Boolean(current.legacy_values && typeof current.legacy_values === "object"),
                canManageWhatsAppSession: canManageWhatsAppSession(current),
                showBackupPanel: canManageBackups(current) || canRestoreBackups(current),
            };
        }

        return Object.freeze({
            values,
            sectionEditable,
            canManageWhatsAppSession,
            canManageBackups,
            canRestoreBackups,
            yesNo,
            display,
            catalogLabel,
            sections,
            legacy,
            page,
        });
    }

    window.AlmdinaFactoryProductionSettingsViewModel = Object.freeze({ create });
})();
