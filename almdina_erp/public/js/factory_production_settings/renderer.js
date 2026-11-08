(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsRenderer) return;

    function create(options = {}) {
        const $body = options.$body;
        const esc = options.escapeHtml;
        const translate = options.translate;
        if (!$body || typeof esc !== "function" || typeof translate !== "function") {
            throw new Error("Production Settings renderer dependencies are unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);

        function uiDirection() {
            const locale = window.AlmdinaLocale;
            if (locale && typeof locale.direction === "function") {
                const value = locale.direction();
                if (value === "ltr" || value === "rtl") return value;
            }
            const root = typeof document !== "undefined" ? document.documentElement : null;
            const dir = root && root.getAttribute("dir");
            return dir === "ltr" ? "ltr" : "rtl";
        }


        function uiButton(options) {
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.button !== "function") {
                throw new Error("AlmdinaUi.button is required for Production Settings rendering");
            }
            return ui.button(options);
        }

        function uiBadge(options) {
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.badge !== "function") {
                throw new Error("AlmdinaUi.badge is required for Production Settings rendering");
            }
            return ui.badge(options);
        }

        function multiline(value) {
            return esc(value || "—").replace(/\r?\n/g, "<br>");
        }

        function renderLoading() {
            $body.html(`
                <div class="aps-loading" dir="${uiDirection()}" role="status" aria-live="polite">
                    <span class="aps-loading-dot" aria-hidden="true"></span>
                    <div><strong>${t("Loading factory settings")}</strong><span>${t("Preparing current values and permissions...")}</span></div>
                </div>
            `);
        }

        function renderError(message) {
            $body.html(`
                <div class="aps-error" dir="${uiDirection()}" role="alert">
                    <span class="aps-error-icon" aria-hidden="true">!</span>
                    <div><strong>${t("Could not load factory settings")}</strong><span>${esc(message || t("Could not load factory settings."))}</span></div>
                </div>
            `);
        }

        function statusTone(value) {
            const normalized = String(value ?? "").trim();
            if (normalized === t("Allowed") || normalized === "مسموح") return "success";
            if (normalized === t("Denied") || normalized === "غير مسموح") return "danger";
            return "";
        }

        function needsLtrIsolate(value) {
            const text = String(value || "").trim();
            if (!text || text === "—") return false;
            if (/[\u0600-\u06FF]/.test(text)) return false;
            return /\d/.test(text);
        }

        function rowHtml(row) {
            const tone = row.multiline ? "" : statusTone(row.value);
            const isolate = !tone && !row.multiline && needsLtrIsolate(row.value);
            const value = row.multiline
                ? multiline(row.value)
                : (
                    tone
                        ? uiBadge({
                            label: row.value,
                            tone,
                            className: `aps-status-pill ${tone === "success" ? "is-allowed" : "is-denied"}`,
                        })
                        : esc(row.value)
                );
            return `
                <div class="aps-value ${row.multiline ? "is-multiline" : ""}${tone ? " has-status" : ""}">
                    <span class="aps-value-label">${esc(row.label)}</span>
                    <b class="aps-value-data${isolate ? " aps-ltr-value" : ""}"${isolate ? ' dir="ltr"' : ""}>${value}</b>
                </div>
            `;
        }

        function sectionCard(section) {
            const stateClass = section.editable ? "is-editable" : "is-readonly";
            return `
                <article class="aps-section ${stateClass}" data-section="${esc(section.key)}">
                    <div class="aps-section-head">
                        <div class="aps-section-copy">
                            <span class="aps-section-accent" aria-hidden="true"></span>
                            <div class="aps-section-titles">
                                <span class="aps-section-kicker">${t("Section settings")}</span>
                                <h3>${esc(section.title)}</h3>
                                <div class="aps-section-desc">${esc(section.description)}</div>
                            </div>
                        </div>
                        <div class="aps-section-tools">
                            ${section.editable ? uiButton({
                                label: t("Edit"),
                                variant: "secondary",
                                className: "aps-edit",
                                attrs: {
                                    "data-section": section.key,
                                    title: t("Edit this section"),
                                    "aria-label": t("Edit this section"),
                                },
                            }) : ""}
                        </div>
                    </div>
                    <div class="aps-values">${section.rows.map(rowHtml).join("")}</div>
                    ${section.editable ? "" : `
                        <div class="aps-readonly-note">${t("You can review the values here, but editing this section is not available for your current permissions.")}</div>
                    `}
                </article>
            `;
        }

        function legacySettingsDetails(model) {
            if (!model.hasLegacy) return "";
            return `
                <details class="aps-legacy">
                    <summary>
                        <span class="aps-legacy-summary-copy">
                            <span class="aps-legacy-icon" aria-hidden="true">↺</span>
                            <span><strong>${t("Legacy settings data kept")}</strong><small>${t("Historical values kept for documentation that do not affect current operations")}</small></span>
                        </span>
                        <span class="aps-readonly-chip">${t("Read-only")}</span>
                    </summary>
                    <div class="aps-legacy-body">
                        <div class="aps-legacy-copy">${t("These values were used in legacy stock and board remnant functions that have been operationally retired. We did not delete them from the database, and they appear here only so that all factory settings data stays in one place without losing any historical value.")}</div>
                        <div class="aps-legacy-grid">${model.legacy.map(rowHtml).join("")}</div>
                    </div>
                </details>
            `;
        }

        function render(model) {
            $body.html(`
                <div class="almdina-ui aps-shell alm-page alm-page--admin" dir="${uiDirection()}">
                    <header class="aps-hero alm-page-intro alm-page-intro--accented">
                        <div class="aps-hero-layout">
                            <div class="aps-hero-copy alm-page-intro__copy">
                                <div class="aps-hero-titles">
                                    <h2 class="alm-page-intro__title">${t("Default factory operating settings")}</h2>
                                    <p class="alm-page-intro__description">${t("Active operating values approved for all operations and workstations")}</p>
                                </div>
                            </div>
                        </div>
                    </header>

                    <div class="aps-section-intro alm-section-header">
                        <div>
                            <span class="alm-section-header__kicker">${t("Active settings")}</span>
                            <strong class="alm-section-header__title">${t("Configure each group from its dedicated place")}</strong>
                        </div>
                        <span class="aps-section-intro-note alm-section-header__note">${t("Editing is shown only for sections you are allowed to edit")}</span>
                    </div>
                    <section class="aps-sections">
                        ${model.sections.map(sectionCard).join("")}
                        ${model.canManageWhatsAppSession ? `
                        <article class="aps-section aps-whatsapp" data-whatsapp-root>
                            <div class="aps-whatsapp-loading">${t("Loading WhatsApp status...")}</div>
                        </article>
                        ` : ""}
                        ${model.showBackupPanel ? `
                        <article class="aps-section aps-backup" data-backup-root>
                            <div class="aps-backup-loading">${t("Loading backup history...")}</div>
                        </article>
                        ` : ""}
                    </section>
                    ${legacySettingsDetails(model)}
                    <div class="aps-note">
                        <span class="aps-note-icon" aria-hidden="true">i</span>
                        <div>${t("The legacy Almdina ERP Settings form link is now a historical route only and will be redirected to this page automatically. No value is deleted from the log on redirect, and contact numbers accept multiple lines such as: landline, mobile, WhatsApp.")}</div>
                    </div>
                </div>
            `);
        }

        function auditHtml(rows) {
            if (!rows.length) {
                return `<div class="aps-empty"><strong>${t("No log yet")}</strong><span>${t("No recorded changes.")}</span></div>`;
            }
            return `<div class="aps-audit" dir="${uiDirection()}">${rows.map(row => `
                <div class="aps-audit-item">
                    <span class="aps-audit-dot" aria-hidden="true"></span>
                    <div class="aps-audit-content">
                        <div class="aps-audit-head"><strong>${esc(row.action)}</strong><span class="aps-ltr-value" dir="ltr">${esc(row.changed_on)}</span></div>
                        <div class="aps-audit-meta">${t("By")}: ${esc(row.changed_by)} · ${esc(row.source || "")}</div>
                        ${row.changed_fields ? `<div class="aps-audit-fields">${t("Fields")}: ${esc(row.changed_fields)}</div>` : ""}
                    </div>
                </div>
            `).join("")}</div>`;
        }

        function auditLoadingHtml() {
            return `<div class="aps-empty" dir="${uiDirection()}" role="status" aria-live="polite"><strong>${t("Loading the log...")}</strong><span>${t("Restoring the latest factory settings changes.")}</span></div>`;
        }

        function auditErrorHtml(message) {
            return `<div class="aps-error" dir="${uiDirection()}" role="alert"><span class="aps-error-icon" aria-hidden="true">!</span><div><strong>${t("Could not load the log")}</strong><span>${esc(message || t("Could not load the log."))}</span></div></div>`;
        }

        function backupStatusLabel(status) {
            const labels = {
                Queued: t("Pending"),
                Running: t("In progress"),
                Prepared: t("Restore prepared"),
                Completed: t("Completed"),
                Failed: t("Failed"),
            };
            return labels[String(status || "")] || String(status || "—");
        }

        function backupStatusTone(status) {
            if (status === "Completed") return "success";
            if (status === "Failed") return "danger";
            return "warning";
        }

        function sizeLabel(value) {
            const bytes = Number(value || 0);
            if (!Number.isFinite(bytes) || bytes <= 0) return "—";
            if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
            if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
            return `${(bytes / 1024).toFixed(1)} KB`;
        }

        function backupHistoryHtml(snapshot = {}) {
            const rows = Array.isArray(snapshot.history) ? snapshot.history : [];
            const restorable = new Map((snapshot.restorable || []).map(row => [row.operation_id, row]));
            if (!rows.length) {
                return `<div class="aps-empty"><strong>${t("No backups yet")}</strong><span>${t("Use Create Backup Now to create the first local backup.")}</span></div>`;
            }
            return `<div class="aps-backup-history">${rows.map(row => {
                const candidate = restorable.get(row.operation_id);
                const canManage = Boolean(snapshot.permissions && snapshot.permissions.can_manage);
                const downloadButton = canManage && row.can_download
                    ? uiButton({
                        label: t("Download"),
                        variant: "secondary",
                        className: "aps-backup-download",
                        attrs: {
                            "data-operation-id": row.operation_id,
                            "data-backup-identifier": row.backup_identifier || "",
                        },
                    })
                    : "";
                const restoreButton = candidate && snapshot.permissions && snapshot.permissions.can_restore && snapshot.restore_runtime_ready
                    ? uiButton({
                        label: t("Restore"),
                        variant: "danger",
                        className: "aps-backup-restore",
                        attrs: {
                            "data-operation-id": row.operation_id,
                            "data-backup-identifier": row.backup_identifier || "",
                        },
                    })
                    : "";
                return `
                    <div class="aps-backup-row">
                        <div class="aps-backup-row-main">
                            <div><strong class="aps-ltr-value" dir="ltr">${esc(row.backup_identifier || row.operation_id || "—")}</strong><span>${esc(row.operation_type || "")} · ${esc(row.target || "")}</span></div>
                            ${uiBadge({ label: backupStatusLabel(row.status), tone: backupStatusTone(row.status) })}
                        </div>
                        <div class="aps-backup-row-meta">
                            <span>${esc(row.requested_on || "—")}</span>
                            <span class="aps-ltr-value" dir="ltr">${esc(sizeLabel(row.total_size))}</span>
                            ${row.error_summary ? `<span class="aps-backup-error">${esc(row.error_summary)}</span>` : ""}
                            <span class="aps-backup-row-actions">${downloadButton}${restoreButton}</span>
                        </div>
                    </div>
                `;
            }).join("")}</div>`;
        }

        function dbRestoreOption(value, selected, label) {
            const isSelected = String(selected || "") === String(value || "");
            return `<option value="${esc(value)}"${isSelected ? " selected" : ""}>${esc(label || value)}</option>`;
        }

        function dbRestoreSettingsHtml(snapshot = {}, { open = false } = {}) {
            const canManageDbRestore = Boolean(
                snapshot.permissions && snapshot.permissions.can_manage_db_restore_settings
            );
            if (!canManageDbRestore) return "";
            const db = snapshot.db_root && typeof snapshot.db_root === "object" ? snapshot.db_root : {};
            const selectedType = db.db_restore_type || "MariaDB";
            const passwordHint = db.db_restore_custom_password_configured
                ? t("Password is saved. Leave the field empty to keep it.")
                : (db.db_restore_root_password_configured
                    ? t("A Frappe operational root password is available. Enter a value only to store an Almadina-specific override.")
                    : t("Stored encrypted through Frappe and never returned to the browser."));
            const readiness = db.db_restore_ready ? t("Ready for restore") : t("Incomplete");
            const source = db.db_restore_source === "custom"
                ? t("Almadina settings")
                : t("Frappe operational settings");
            return `
                <details class="aps-db-restore" data-db-restore-settings${open ? " open" : ""}>
                    <summary>
                        <span class="aps-legacy-summary-copy">
                            <span class="aps-legacy-icon" aria-hidden="true">⚙</span>
                            <span>
                                <strong>${t("Database & Restore Settings")}</strong>
                                <small>${t("Configure privileged database connection for restore readiness without changing the site application login.")}</small>
                            </span>
                        </span>
                        <span class="aps-readonly-chip">${esc(readiness)}</span>
                    </summary>
                    <div class="aps-db-restore-body">
                        <div class="aps-db-restore-note">${t("Save these settings before using Test Connection. The test always uses the last saved values, with fallback to Frappe operational configuration when Almadina overrides are empty.")}</div>
                        <div class="aps-db-restore-meta">${t("Credential source")}: <strong>${esc(source)}</strong></div>
                        <div class="aps-db-restore-grid">
                            <label class="aps-db-restore-field">
                                <span>${t("Database Type")}</span>
                                <select class="aps-db-restore-input" data-db-restore-field="db_restore_type" dir="ltr">
                                    ${dbRestoreOption("MariaDB", selectedType, t("MariaDB"))}
                                    ${dbRestoreOption("PostgreSQL", selectedType, t("PostgreSQL"))}
                                    ${dbRestoreOption("SQLite", selectedType, t("SQLite"))}
                                </select>
                            </label>
                            <label class="aps-db-restore-field">
                                <span>${t("Database Host")}</span>
                                <input class="aps-db-restore-input aps-ltr-value" data-db-restore-field="db_restore_host" type="text" dir="ltr" autocomplete="off" value="${esc(db.db_restore_host || "")}">
                            </label>
                            <label class="aps-db-restore-field">
                                <span>${t("Database Port")}</span>
                                <input class="aps-db-restore-input aps-ltr-value" data-db-restore-field="db_restore_port" type="number" min="1" max="65535" dir="ltr" value="${esc(db.db_restore_port == null ? "" : db.db_restore_port)}">
                            </label>
                            <label class="aps-db-restore-field">
                                <span>${t("Root Username")}</span>
                                <input class="aps-db-restore-input aps-ltr-value" data-db-restore-field="db_restore_root_username" type="text" dir="ltr" autocomplete="off" value="${esc(db.db_restore_root_username || "")}">
                            </label>
                            <label class="aps-db-restore-field aps-db-restore-field--wide">
                                <span>${t("Root Password")}</span>
                                <input class="aps-db-restore-input" data-db-restore-field="db_restore_root_password" type="password" autocomplete="new-password" value="" placeholder="${esc(db.db_restore_root_password_configured ? t("Saved securely") : "")}">
                                <small>${esc(passwordHint)}</small>
                            </label>
                        </div>
                        <div class="aps-db-restore-actions">
                            ${uiButton({ label: t("Save database settings"), variant: "primary", className: "aps-db-restore-save" })}
                            ${uiButton({ label: t("Test Connection"), variant: "secondary", className: "aps-backup-test-db" })}
                        </div>
                    </div>
                </details>
            `;
        }

        function backupHtml(snapshot = {}, options = {}) {
            const canManage = Boolean(snapshot.permissions && snapshot.permissions.can_manage);
            const canRestore = Boolean(snapshot.permissions && snapshot.permissions.can_restore);
            return `
                <div class="aps-section-head">
                    <div class="aps-section-copy">
                        <span class="aps-section-accent" aria-hidden="true"></span>
                        <div class="aps-section-titles">
                            <span class="aps-section-kicker">${t("Administration and execution")}</span>
                            <h3>${t("Backup History & Actions")}</h3>
                            <div class="aps-section-desc">${t("Every backup is created with the official Frappe engine, and the result appears here without exposing local paths or credentials.")}</div>
                        </div>
                    </div>
                    <div class="aps-section-tools aps-backup-actions">
                        ${canManage ? uiButton({ label: t("Test SSH Connection"), variant: "secondary", className: "aps-backup-test" }) : ""}
                        ${canManage ? uiButton({ label: t("Import Backup"), variant: "secondary", className: "aps-backup-import" }) : ""}
                        ${canManage ? uiButton({ label: t("Create Backup Now"), variant: "primary", className: "aps-backup-create" }) : ""}
                    </div>
                </div>
                ${dbRestoreSettingsHtml(snapshot, { open: Boolean(options.dbRestoreOpen) })}
                ${canRestore && !snapshot.restore_runtime_ready ? `<div class="aps-readonly-note">${t("Restore is disabled until database root connection settings are complete in Almadina ERP Settings or Frappe operational configuration.")}</div>` : ""}
                ${backupHistoryHtml(snapshot)}
            `;
        }

        function renderBackup(snapshot) {
            const $root = $body.find("[data-backup-root]");
            if (!$root.length) return;
            let dbRestoreOpen = false;
            if (typeof $root.find === "function") {
                const $details = $root.find("[data-db-restore-settings]");
                dbRestoreOpen = Boolean($details && typeof $details.prop === "function" && $details.prop("open"));
            }
            $root.html(backupHtml(snapshot || {}, { dbRestoreOpen }));
        }

        function renderBackupError(message) {
            const $root = $body.find("[data-backup-root]");
            if ($root.length) $root.html(`<div class="aps-error" role="alert"><span class="aps-error-icon" aria-hidden="true">!</span><div><strong>${t("Could not load backup management")}</strong><span>${esc(message || t("An unexpected error occurred."))}</span></div></div>`);
        }

        function statusLabel(status) {
            const labels = {
                ready: t("Running"),
                created: t("Created"),
                initializing: t("Initializing"),
                qr_ready: t("Waiting for code scan"),
                authenticating: t("Verifying"),
                disconnected: t("Not connected"),
                action_required: t("Needs action"),
                failed: t("Failed"),
            };
            const key = String(status || "").trim();
            return labels[key] || (key ? key : t("Unknown"));
        }

        function whatsappHtml(snapshot = {}) {
            if (snapshot.configured === false) {
                return `
                    <div class="aps-section-head">
                        <div class="aps-section-copy">
                            <span class="aps-section-accent" aria-hidden="true"></span>
                            <div class="aps-section-titles">
                                <span class="aps-section-kicker">${t("External integration")}</span>
                                <h3>${t("WhatsApp session")}</h3>
                                <div class="aps-section-desc">${esc(snapshot.reason || t("WhatsApp server address or API key is not configured."))}</div>
                            </div>
                        </div>
                        <div class="aps-section-tools">
                            <span class="aps-permission readonly"><span class="aps-permission-dot" aria-hidden="true"></span>${t("Not configured")}</span>
                        </div>
                    </div>
                `;
            }
            if (!snapshot.session) {
                return `
                    <div class="aps-section-head">
                        <div class="aps-section-copy">
                            <span class="aps-section-accent" aria-hidden="true"></span>
                            <div class="aps-section-titles">
                                <span class="aps-section-kicker">${t("External integration")}</span>
                                <h3>${t("WhatsApp session")}</h3>
                                <div class="aps-section-desc">${t("Link one session with WhatsApp Web to send measurement sheets to customers.")}</div>
                            </div>
                        </div>
                        <div class="aps-section-tools">
                            <span class="aps-permission readonly"><span class="aps-permission-dot" aria-hidden="true"></span>${t("Not linked")}</span>
                        </div>
                    </div>
                    <div class="aps-actions">
                        ${uiButton({
                            label: t("Create and link WhatsApp"),
                            variant: "primary",
                            className: "aps-whatsapp-create",
                        })}
                    </div>
                `;
            }
            const session = snapshot.session || {};
            const working = Boolean(snapshot.working);
            const rows = [
                [t("Status"), statusLabel(session.status)],
                [t("Name"), session.name],
                [t("Session number"), session.phone],
                [t("Display name"), session.push_name],
            ];
            if (session.last_error) rows.push([t("Last error"), session.last_error]);
            return `
                <div class="aps-section-head">
                    <div class="aps-section-copy">
                        <span class="aps-section-accent" aria-hidden="true"></span>
                        <div class="aps-section-titles">
                            <span class="aps-section-kicker">${t("External integration")}</span>
                            <h3>${t("WhatsApp session")}</h3>
                            <div class="aps-section-desc">${working ? t("Session is connected and customer messages can be sent.") : esc(snapshot.reason || t("Session is not connected."))}</div>
                        </div>
                    </div>
                    <div class="aps-section-tools">
                        <span class="aps-permission ${working ? "" : "readonly"}">
                            <span class="aps-permission-dot" aria-hidden="true"></span>${working ? t("Running") : t("Not running")}
                        </span>
                    </div>
                </div>
                <div class="aps-values">${rows.map(([label, value]) => rowHtml({ label, value })).join("")}</div>
                ${working ? "" : `
                    <div class="aps-actions">
                        ${uiButton({
                            label: t("Reconnect"),
                            variant: "primary",
                            className: "aps-whatsapp-reconnect",
                        })}
                    </div>
                `}
            `;
        }

        function renderWhatsApp(snapshot) {
            const $root = $body.find("[data-whatsapp-root]");
            if (!$root.length) return;
            $root.html(whatsappHtml(snapshot));
        }

        return Object.freeze({
            renderLoading,
            renderError,
            render,
            renderWhatsApp,
            whatsappHtml,
            auditHtml,
            auditLoadingHtml,
            auditErrorHtml,
            renderBackup,
            renderBackupError,
        });
    }

    window.AlmdinaFactoryProductionSettingsRenderer = Object.freeze({ create });
})();
