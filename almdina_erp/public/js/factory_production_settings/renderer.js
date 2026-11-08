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

        function backupTypeLabel(value) {
            const key = String(value || "").trim();
            const labels = {
                Manual: t("Manual"),
                Scheduled: t("Scheduled"),
                Safety: t("Safety"),
                Imported: t("Imported"),
                Restore: t("Restore"),
            };
            return labels[key] || key || "—";
        }

        function backupTargetLabel(value) {
            const key = String(value || "").trim();
            if (key === "Local") return t("Local");
            if (key === "External") return t("External");
            if (key === "Restore") return t("Restore");
            return key || "—";
        }

        function sizeLabel(value) {
            const bytes = Number(value || 0);
            if (!Number.isFinite(bytes) || bytes <= 0) return "—";
            if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
            if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
            return `${(bytes / 1024).toFixed(1)} KB`;
        }

        const DELETE_ORPHAN_CODES = Object.freeze({
            backup_delete_pending: true,
            backup_delete_files_failed: true,
            backup_delete_record_failed_after_files: true,
        });

        function isDeletableBackupRow(row) {
            const status = String(row && row.status || "");
            const opType = String(row && row.operation_type || "");
            const target = String(row && row.target || "");
            if (opType === "Restore" || target === "Restore") return false;
            if (status === "Completed") return true;
            if (status === "Failed") {
                return Boolean(DELETE_ORPHAN_CODES[String(row.error_summary || "").trim()]);
            }
            return false;
        }

        function backupRetryHtml(row) {
            const attempts = Number(row && row.attempt_count || 0);
            const nextRetry = String(row && row.next_retry_on || "").trim();
            const error = String(row && row.error_summary || "").trim();
            const failed = String(row && row.status || "") === "Failed";
            if (!failed && attempts <= 1 && !nextRetry) return "";
            const parts = [];
            if (attempts > 0) parts.push(`${t("Attempts")}: <span class="aps-ltr-value" dir="ltr">${esc(String(attempts))}</span>`);
            if (error) parts.push(`${t("Error")}: <span class="aps-backup-error">${esc(error)}</span>`);
            if (nextRetry) parts.push(`${t("Next retry")}: <span class="aps-ltr-value" dir="ltr">${esc(nextRetry)}</span>`);
            if (!parts.length) return "";
            return `<div class="aps-backup-retry" role="status">${parts.join(" · ")}</div>`;
        }

        function lastSuccessfulBackup(rows) {
            const completed = (Array.isArray(rows) ? rows : []).filter(row => {
                if (String(row.status || "") !== "Completed") return false;
                if (String(row.operation_type || "") === "Restore") return false;
                if (String(row.target || "") === "Restore") return false;
                return true;
            });
            if (!completed.length) return null;
            return completed.slice().sort((left, right) => {
                const a = String(left.completed_on || left.requested_on || "");
                const b = String(right.completed_on || right.requested_on || "");
                return a < b ? 1 : (a > b ? -1 : 0);
            })[0];
        }

        function backupSummaryHtml(snapshot = {}) {
            const last = lastSuccessfulBackup(snapshot.history);
            if (!last) {
                return `
                    <section class="aps-backup-summary" data-backup-summary>
                        <div class="aps-backup-summary-empty">
                            <strong>${t("No successful backup yet")}</strong>
                            <span>${t("Create a local backup or import a ZIP package to see the latest successful copy here.")}</span>
                        </div>
                    </section>
                `;
            }
            const when = last.completed_on || last.requested_on || "—";
            return `
                <section class="aps-backup-summary" data-backup-summary>
                    <div class="aps-backup-summary-head">
                        <strong>${t("Latest successful backup")}</strong>
                        ${uiBadge({ label: backupStatusLabel(last.status), tone: backupStatusTone(last.status) })}
                    </div>
                    <div class="aps-backup-summary-grid">
                        <div><span>${t("Name")}</span><b class="aps-ltr-value" dir="ltr">${esc(last.backup_identifier || last.operation_id || "—")}</b></div>
                        <div><span>${t("Date & time")}</span><b class="aps-ltr-value" dir="ltr">${esc(when)}</b></div>
                        <div><span>${t("Type")}</span><b>${esc(backupTypeLabel(last.operation_type))}</b></div>
                        <div><span>${t("Source")}</span><b>${esc(backupTargetLabel(last.target))}</b></div>
                        <div><span>${t("Size")}</span><b class="aps-ltr-value" dir="ltr">${esc(sizeLabel(last.total_size))}</b></div>
                        <div><span>${t("Status")}</span><b>${esc(backupStatusLabel(last.status))}</b></div>
                    </div>
                </section>
            `;
        }

        function backupFilterOption(value, selected, label) {
            const isSelected = String(selected || "") === String(value || "");
            return `<option value="${esc(value)}"${isSelected ? " selected" : ""}>${esc(label)}</option>`;
        }

        function filterBackupRows(rows, filters = {}) {
            const query = String(filters.query || "").trim().toLowerCase();
            const type = String(filters.type || "").trim();
            const source = String(filters.source || "").trim();
            const status = String(filters.status || "").trim();
            const sort = String(filters.sort || "date_desc");
            let result = (Array.isArray(rows) ? rows.slice() : []).filter(row => {
                if (type && String(row.operation_type || "") !== type) return false;
                if (source && String(row.target || "") !== source) return false;
                if (status && String(row.status || "") !== status) return false;
                if (!query) return true;
                const haystack = [
                    row.backup_identifier,
                    row.operation_id,
                    row.operation_type,
                    row.target,
                    row.status,
                    row.error_summary,
                ].map(value => String(value || "").toLowerCase()).join(" ");
                return haystack.includes(query);
            });
            result.sort((left, right) => {
                const a = String(left.requested_on || left.completed_on || "");
                const b = String(right.requested_on || right.completed_on || "");
                if (sort === "date_asc") return a < b ? -1 : (a > b ? 1 : 0);
                return a < b ? 1 : (a > b ? -1 : 0);
            });
            return result;
        }

        function backupToolbarHtml(filters = {}) {
            return `
                <div class="aps-backup-toolbar" data-backup-toolbar>
                    <label class="aps-backup-filter aps-backup-filter--search">
                        <span>${t("Search by name")}</span>
                        <input type="search" class="aps-backup-filter-input" data-backup-filter="query" value="${esc(filters.query || "")}" placeholder="${esc(t("Backup name or identifier"))}" autocomplete="off">
                    </label>
                    <label class="aps-backup-filter">
                        <span>${t("Type")}</span>
                        <select class="aps-backup-filter-input" data-backup-filter="type">
                            ${backupFilterOption("", filters.type, t("All types"))}
                            ${backupFilterOption("Manual", filters.type, t("Manual"))}
                            ${backupFilterOption("Scheduled", filters.type, t("Scheduled"))}
                            ${backupFilterOption("Safety", filters.type, t("Safety"))}
                            ${backupFilterOption("Imported", filters.type, t("Imported"))}
                            ${backupFilterOption("Restore", filters.type, t("Restore"))}
                        </select>
                    </label>
                    <label class="aps-backup-filter">
                        <span>${t("Source")}</span>
                        <select class="aps-backup-filter-input" data-backup-filter="source">
                            ${backupFilterOption("", filters.source, t("All sources"))}
                            ${backupFilterOption("Local", filters.source, t("Local"))}
                            ${backupFilterOption("External", filters.source, t("External"))}
                        </select>
                    </label>
                    <label class="aps-backup-filter">
                        <span>${t("Status")}</span>
                        <select class="aps-backup-filter-input" data-backup-filter="status">
                            ${backupFilterOption("", filters.status, t("All statuses"))}
                            ${backupFilterOption("Completed", filters.status, t("Completed"))}
                            ${backupFilterOption("Failed", filters.status, t("Failed"))}
                            ${backupFilterOption("Queued", filters.status, t("Pending"))}
                            ${backupFilterOption("Running", filters.status, t("In progress"))}
                            ${backupFilterOption("Prepared", filters.status, t("Restore prepared"))}
                        </select>
                    </label>
                    <label class="aps-backup-filter">
                        <span>${t("Sort by date")}</span>
                        <select class="aps-backup-filter-input" data-backup-filter="sort">
                            ${backupFilterOption("date_desc", filters.sort || "date_desc", t("Newest first"))}
                            ${backupFilterOption("date_asc", filters.sort, t("Oldest first"))}
                        </select>
                    </label>
                </div>
            `;
        }

        function backupHistoryHtml(snapshot = {}, filters = {}) {
            const allRows = Array.isArray(snapshot.history) ? snapshot.history : [];
            const rows = filterBackupRows(allRows, filters);
            const restorable = new Map((snapshot.restorable || []).map(row => [row.operation_id, row]));
            if (!allRows.length) {
                return `<div class="aps-backup-history" data-backup-list><div class="aps-empty"><strong>${t("No backups yet")}</strong><span>${t("Use Create Backup Now to create the first local backup.")}</span></div></div>`;
            }
            if (!rows.length) {
                return `<div class="aps-backup-history" data-backup-list><div class="aps-empty"><strong>${t("No matching backups")}</strong><span>${t("Adjust the search or filters to see other backups.")}</span></div></div>`;
            }
            return `<div class="aps-backup-history" data-backup-list>${rows.map(row => {
                const candidate = restorable.get(row.operation_id);
                const canManage = Boolean(snapshot.permissions && snapshot.permissions.can_manage);
                const canRestore = Boolean(snapshot.permissions && snapshot.permissions.can_restore);
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
                const restoreButton = candidate && canRestore && snapshot.restore_runtime_ready
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
                const detailsButton = uiButton({
                    label: t("Details"),
                    variant: "secondary",
                    className: "aps-backup-details",
                    attrs: { "data-operation-id": row.operation_id },
                });
                const deleteButton = canManage && isDeletableBackupRow(row)
                    ? uiButton({
                        label: t("Delete"),
                        variant: "danger",
                        className: "aps-backup-delete",
                        attrs: {
                            "data-operation-id": row.operation_id,
                            "data-backup-identifier": row.backup_identifier || "",
                            "data-backup-target": row.target || "",
                        },
                    })
                    : "";
                return `
                    <article class="aps-backup-row" data-operation-id="${esc(row.operation_id || "")}">
                        <div class="aps-backup-row-main">
                            <div>
                                <strong class="aps-ltr-value" dir="ltr">${esc(row.backup_identifier || row.operation_id || "—")}</strong>
                                <span>${esc(backupTypeLabel(row.operation_type))} · ${esc(backupTargetLabel(row.target))}</span>
                            </div>
                            ${uiBadge({ label: backupStatusLabel(row.status), tone: backupStatusTone(row.status) })}
                        </div>
                        <div class="aps-backup-row-meta">
                            <span class="aps-ltr-value" dir="ltr">${esc(row.requested_on || "—")}</span>
                            <span class="aps-ltr-value" dir="ltr">${esc(sizeLabel(row.total_size))}</span>
                            <span class="aps-backup-row-actions">${downloadButton}${restoreButton}${detailsButton}${deleteButton}</span>
                        </div>
                        ${backupRetryHtml(row)}
                    </article>
                `;
            }).join("")}</div>`;
        }

        function dbRestoreOption(value, selected, label) {
            const isSelected = String(selected || "") === String(value || "");
            return `<option value="${esc(value)}"${isSelected ? " selected" : ""}>${esc(label || value)}</option>`;
        }

        function dbRestoreSettingsHtml(snapshot = {}) {
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
                <div class="aps-backup-advanced-block" data-db-restore-settings>
                    <div class="aps-backup-advanced-block-head">
                        <div>
                            <strong>${t("Database & Restore Settings")}</strong>
                            <small>${t("Configure privileged database connection for restore readiness without changing the site application login.")}</small>
                        </div>
                        <span class="aps-readonly-chip">${esc(readiness)}</span>
                    </div>
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
                </div>
            `;
        }

        function backupScheduleSettingsHtml(scheduleSection) {
            if (!scheduleSection) return "";
            return `
                <div class="aps-backup-advanced-block" data-backup-schedule-settings>
                    <div class="aps-backup-advanced-block-head">
                        <div>
                            <strong>${esc(scheduleSection.title)}</strong>
                            <small>${esc(scheduleSection.description || "")}</small>
                        </div>
                        ${scheduleSection.editable ? uiButton({
                            label: t("Edit"),
                            variant: "secondary",
                            className: "aps-edit",
                            attrs: { "data-section": "backup_restore" },
                        }) : ""}
                    </div>
                    <div class="aps-backup-advanced-rows">
                        ${(scheduleSection.rows || []).map(rowHtml).join("")}
                    </div>
                </div>
            `;
        }

        function backupAdvancedHtml(snapshot = {}, options = {}) {
            const schedule = options.scheduleSection || null;
            const dbHtml = dbRestoreSettingsHtml(snapshot);
            if (!schedule && !dbHtml) return "";
            const open = Boolean(options.advancedOpen);
            return `
                <details class="aps-backup-advanced" data-backup-advanced${open ? " open" : ""}>
                    <summary>
                        <span class="aps-legacy-summary-copy">
                            <span class="aps-legacy-icon" aria-hidden="true">⚙</span>
                            <span>
                                <strong>${t("Advanced settings")}</strong>
                                <small>${t("Schedules, retention, External SSH, encryption, and database restore credentials.")}</small>
                            </span>
                        </span>
                    </summary>
                    <div class="aps-backup-advanced-body">
                        ${backupScheduleSettingsHtml(schedule)}
                        ${dbHtml}
                    </div>
                </details>
            `;
        }

        function backupHtml(snapshot = {}, options = {}) {
            const canManage = Boolean(snapshot.permissions && snapshot.permissions.can_manage);
            const canRestore = Boolean(snapshot.permissions && snapshot.permissions.can_restore);
            const filters = options.filters || {};
            return `
                <div class="aps-section-head">
                    <div class="aps-section-copy">
                        <span class="aps-section-accent" aria-hidden="true"></span>
                        <div class="aps-section-titles">
                            <span class="aps-section-kicker">${t("Administration and execution")}</span>
                            <h3>${t("Backup Management")}</h3>
                            <div class="aps-section-desc">${t("Daily backup actions stay here. Schedules and credentials stay under Advanced settings.")}</div>
                        </div>
                    </div>
                </div>
                ${backupSummaryHtml(snapshot)}
                <section class="aps-backup-primary" data-backup-primary-actions>
                    <div class="aps-backup-primary-head">
                        <strong>${t("Primary actions")}</strong>
                        <span>${t("Create, import, or verify connectivity without opening advanced settings.")}</span>
                    </div>
                    <div class="aps-section-tools aps-backup-actions">
                        ${canManage ? uiButton({ label: t("Create Backup Now"), variant: "primary", className: "aps-backup-create" }) : ""}
                        ${canManage ? uiButton({ label: t("Import Backup"), variant: "secondary", className: "aps-backup-import" }) : ""}
                        ${canManage ? uiButton({ label: t("Test SSH Connection"), variant: "secondary", className: "aps-backup-test" }) : ""}
                    </div>
                </section>
                <div class="aps-backup-guide" role="note">
                    <strong>${t("Encrypted External path")}</strong>
                    <span>${t("Download encrypted files offline → decrypt and verify → build an almdina.backup.zip → Import Backup.")}</span>
                </div>
                ${canRestore && !snapshot.restore_runtime_ready ? `<div class="aps-readonly-note">${t("Restore is disabled until database root connection settings are complete in Almadina ERP Settings or Frappe operational configuration.")}</div>` : ""}
                ${canRestore && snapshot.restore_runtime_ready ? `<div class="aps-readonly-note">${t("Local Manual, Scheduled, Safety, and Imported backups can be restored. External backups are never restored directly — import an almdina.backup.zip first (decrypt encrypted External packages offline).")}</div>` : ""}
                <section class="aps-backup-list-panel" data-backup-list-panel>
                    <div class="aps-backup-list-head">
                        <strong>${t("Backup list")}</strong>
                        <span>${t("Search, filter, and open actions for each backup.")}</span>
                    </div>
                    ${backupToolbarHtml(filters)}
                    ${backupHistoryHtml(snapshot, filters)}
                </section>
                ${backupAdvancedHtml(snapshot, options)}
            `;
        }

        function readBackupFilters($root) {
            const read = name => {
                if (!$root || typeof $root.find !== "function") return "";
                return String($root.find(`[data-backup-filter="${name}"]`).val() || "").trim();
            };
            return {
                query: read("query"),
                type: read("type"),
                source: read("source"),
                status: read("status"),
                sort: read("sort") || "date_desc",
            };
        }

        function renderBackup(snapshot, options = {}) {
            const $root = $body.find("[data-backup-root]");
            if (!$root.length) return;
            let advancedOpen = Boolean(options.advancedOpen);
            let filters = options.filters || null;
            if (typeof $root.find === "function") {
                const $advanced = $root.find("[data-backup-advanced]");
                if (!("advancedOpen" in options)) {
                    advancedOpen = Boolean($advanced && typeof $advanced.prop === "function" && $advanced.prop("open"));
                }
                if (!filters) filters = readBackupFilters($root);
            }
            $root.html(backupHtml(snapshot || {}, {
                advancedOpen,
                filters: filters || { sort: "date_desc" },
                scheduleSection: options.scheduleSection || null,
            }));
        }

        function renderBackupList(snapshot, filters = {}) {
            const $list = $body.find("[data-backup-list]");
            if (!$list.length) {
                renderBackup(snapshot, { filters });
                return;
            }
            const html = backupHistoryHtml(snapshot || {}, filters || { sort: "date_desc" });
            $list.replaceWith(html);
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
            renderBackupList,
            renderBackupError,
        });
    }

    window.AlmdinaFactoryProductionSettingsRenderer = Object.freeze({ create });
})();
