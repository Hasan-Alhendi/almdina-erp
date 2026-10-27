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
                        ${model.showCustomerBotPanel ? `
                        <article class="aps-section aps-bot" data-bot-root>
                            <div class="aps-bot-loading">${t("Loading customer bot settings...")}</div>
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
                            ${restoreButton}
                        </div>
                    </div>
                `;
            }).join("")}</div>`;
        }

        function backupHtml(snapshot = {}) {
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
                        ${canManage ? uiButton({ label: t("Create Backup Now"), variant: "primary", className: "aps-backup-create" }) : ""}
                    </div>
                </div>
                ${canRestore && !snapshot.restore_runtime_ready ? `<div class="aps-readonly-note">${t("Restore is disabled until DB root credentials are configured in the operational Frappe settings.")}</div>` : ""}
                ${backupHistoryHtml(snapshot)}
            `;
        }

        function renderBackup(snapshot) {
            const $root = $body.find("[data-backup-root]");
            if ($root.length) $root.html(backupHtml(snapshot));
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

        function renderCustomerBot(model) {
            const $root = $body.find("[data-bot-root]");
            if (!$root.length || !model) return;
            $root.html(customerBotHtml(model));
        }

        function renderCustomerBotOperation(model) {
            const host = $body.find("[data-bot-operation]");
            if (!host.length || !model) return;
            host.html(customerBotOperationHtml(model.operation || {}));
        }

        function customerBotTab(tab) {
            return uiButton({
                label: tab.label || "",
                variant: tab.selected ? "primary" : "secondary",
                attrs: {
                    "data-bot-tab": tab.id || "",
                    role: "tab",
                    id: `aps-bot-tab-${tab.id || ""}`,
                    "aria-controls": `aps-bot-panel-${tab.id || ""}`,
                    "aria-selected": tab.selected ? "true" : "false",
                    tabindex: tab.selected ? "0" : "-1",
                },
            });
        }

        function customerBotField(field) {
            const variables = Array.isArray(field.variables) ? field.variables : [];
            return `
                <div class="aps-bot-field" data-bot-field-wrap="${esc(field.key || "")}" data-bot-group="${esc(field.groupId || "")}" data-bot-label="${esc(field.label || "")}" ${field.hidden ? "hidden" : ""}>
                    <label class="aps-bot-field-label" for="aps-bot-text-${esc(field.key || "")}">
                        <span>${esc(field.label || "")}</span>
                        <span class="aps-bot-key aps-ltr-value" dir="ltr">${esc(field.key || "")}</span>
                    </label>
                    <textarea id="aps-bot-text-${esc(field.key || "")}" data-bot-field="${esc(field.key || "")}" dir="auto" rows="2"${field.maxLength ? ` maxlength="${esc(field.maxLength)}"` : ""} aria-invalid="${field.invalid ? "true" : "false"}">${esc(field.value || "")}</textarea>
                    ${field.maxLength ? `<span class="aps-bot-count" data-bot-count="${esc(field.key || "")}">${esc(field.countLabel || "")}</span>` : ""}
                    <p class="aps-bot-field-error" data-bot-error="${esc(field.key || "")}" ${field.invalid ? "" : "hidden"}>${esc(field.error || "")}</p>
                    ${variables.length ? `
                        <ul class="aps-bot-variables">
                            ${variables.map(variable => `
                                <li>
                                    <code class="aps-ltr-value" dir="ltr">{${esc(variable.name || "")}}</code>
                                    <span>${esc(variable.meaning || "")}</span>
                                    ${variable.example ? `<span class="aps-ltr-value" dir="ltr">${t("Example")}: ${esc(variable.example)}</span>` : ""}
                                </li>
                            `).join("")}
                        </ul>
                    ` : ""}
                </div>
            `;
        }

        function customerBotFact(row) {
            const ltr = Boolean(row && row.ltr);
            return `
                <div>
                    <dt>${esc((row && row.label) || "")}</dt>
                    <dd class="${ltr ? "aps-ltr-value" : ""}"${ltr ? ' dir="ltr"' : ""}>${esc((row && row.value) || "")}</dd>
                </div>
            `;
        }

        function customerBotOperationHtml(operation) {
            if (!operation || !operation.visible) {
                return `<p class="aps-bot-notice">${esc((operation && operation.unavailable) || "")}</p>`;
            }
            const facts = Array.isArray(operation.facts) ? operation.facts : [];
            const events = Array.isArray(operation.events) ? operation.events : [];
            return `
                <div class="aps-bot-card">
                    <div class="aps-bot-head">
                        <h3>${t("Customer bot")}</h3>
                        ${operation.stateLabel ? uiBadge({
                            label: operation.stateLabel,
                            tone: operation.tone || "neutral",
                            className: "aps-bot-badge",
                        }) : ""}
                    </div>
                    ${operation.reason ? `<p class="aps-bot-reason" data-bot-reason data-tone="${esc(operation.reasonTone || "neutral")}">${esc(operation.reason)}</p>` : ""}
                    ${operation.pending ? "" : `
                    <div class="aps-bot-toolbar">
                        ${operation.showStart ? uiButton({
                            label: t("Start the bot"),
                            variant: "primary",
                            disabled: Boolean(operation.startDisabled),
                            attrs: { "data-bot-start": "1" },
                        }) : ""}
                        ${operation.showStop ? uiButton({
                            label: t("Stop the bot"),
                            variant: "primary",
                            disabled: Boolean(operation.stopDisabled),
                            attrs: { "data-bot-stop": "1" },
                        }) : ""}
                        ${uiButton({
                            label: t("Check connection"),
                            variant: "secondary",
                            disabled: Boolean(operation.checkDisabled),
                            attrs: { "data-bot-check": "1" },
                        })}
                        ${uiButton({
                            label: t("Test the bot"),
                            variant: "secondary",
                            attrs: { "data-bot-test": "1" },
                        })}
                        ${uiButton({
                            label: t("Details"),
                            variant: "secondary",
                            className: "aps-bot-btn-quiet",
                            attrs: {
                                "data-bot-details-toggle": "1",
                                "aria-expanded": operation.detailsOpen ? "true" : "false",
                            },
                        })}
                    </div>
                    `}
                    <div class="aps-bot-details" data-bot-details ${operation.detailsOpen ? "" : "hidden"}>
                        <dl class="aps-bot-facts">${facts.map(customerBotFact).join("")}</dl>
                        <dl class="aps-bot-events">${events.map(customerBotFact).join("")}</dl>
                        <p class="aps-bot-help">${t("Gateway acceptance is not proof the customer received the message.")}</p>
                        ${operation.technical ? `
                            ${uiButton({
                                label: t("Technical details"),
                                variant: "secondary",
                                className: "aps-bot-btn-quiet",
                                attrs: {
                                    "data-bot-technical": "1",
                                    "aria-expanded": operation.technicalOpen ? "true" : "false",
                                },
                            })}
                            <p data-bot-technical-panel ${operation.technicalOpen ? "" : "hidden"}>${esc(operation.technical)}</p>
                        ` : ""}
                    </div>
                </div>
            `;
        }

        function customerBotHtml(model) {
            const groups = Array.isArray(model.groups) ? model.groups : [];
            const scenarios = Array.isArray(model.scenarios) ? model.scenarios : [];
            const tabs = Array.isArray(model.tabs) ? model.tabs : [];
            const fields = Array.isArray(model.fields) ? model.fields : [];
            const active = model.activeTab || "texts";
            const operationVisible = Boolean(model.operation && model.operation.visible);
            return `
                ${operationVisible ? `<div data-bot-operation>${customerBotOperationHtml(model.operation || {})}</div>` : `
                    <header class="aps-bot-head"><h3>${t("Customer bot")}</h3></header>
                    ${customerBotOperationHtml(model.operation || {})}
                `}
                ${model.canEditTexts === false ? "" : `
                <div class="aps-bot-copy">
                <div class="aps-bot-statusline">
                    <p class="aps-bot-flag" data-bot-unsaved ${model.unsaved ? "" : "hidden"}>${t("Customer bot unsaved changes")}</p>
                    <p class="aps-bot-flag" data-bot-unpublished ${model.unpublished ? "" : "hidden"}>${t("Unpublished changes")}</p>
                    <p class="aps-bot-meta">${model.publishedAt ? `<time class="aps-ltr-value" dir="ltr" datetime="${esc(model.publishedAt)}">${esc(model.publishedLabel || "")}</time>` : esc(model.publishedLabel || "")}</p>
                    <p class="aps-bot-meta aps-ltr-value" dir="ltr">${esc(model.revisionLabel || "")}</p>
                </div>
                <div data-bot-alert role="status"></div>
                <div class="aps-bot-tabs" role="tablist" aria-label="${esc(model.tabsLabel || "")}">
                    ${tabs.map(customerBotTab).join("")}
                </div>
                <section class="aps-bot-panel" id="aps-bot-panel-texts" role="tabpanel" aria-labelledby="aps-bot-tab-texts" data-bot-panel="texts" ${active === "texts" ? "" : "hidden"}>
                    <label class="aps-bot-field">
                        <span>${t("Search")}</span>
                        <input type="search" data-bot-search value="${esc(model.query || "")}" dir="auto" placeholder="${esc(model.searchPlaceholder || "")}">
                    </label>
                    <p data-bot-search-empty ${model.searchEmpty ? "" : "hidden"}>${t("No matching message")}</p>
                    <div class="aps-bot-editor">
                        <div class="aps-bot-groups" role="group" aria-label="${esc(model.groupsLabel || "")}">
                            ${groups.map(group => uiButton({
                                label: group.label || "",
                                variant: group.selected ? "primary" : "secondary",
                                className: "aps-bot-group-button",
                                attrs: {
                                    "data-bot-group-button": group.id || "",
                                    "data-bot-group-match": group.hasMatch ? "1" : "0",
                                    "aria-pressed": group.selected ? "true" : "false",
                                },
                            })).join("")}
                        </div>
                        <div>
                            ${fields.map(customerBotField).join("")}
                            <p class="aps-bot-help">${esc(model.saveHelp || "")}</p>
                            <div class="aps-bot-actions">
                                ${uiButton({
                                    label: t("Save draft"),
                                    variant: "secondary",
                                    attrs: { "data-bot-save": "1" },
                                })}
                                ${uiButton({
                                    label: t("Publish draft"),
                                    variant: "primary",
                                    attrs: { "data-bot-publish": "1" },
                                })}
                            </div>
                        </div>
                    </div>
                </section>
                <section class="aps-bot-panel" id="aps-bot-panel-preview" role="tabpanel" aria-labelledby="aps-bot-tab-preview" data-bot-panel="preview" ${active === "preview" ? "" : "hidden"}>
                    <p>${t("Preview uses sample data and does not send a message.")}</p>
                    <p class="aps-bot-preview-note" data-bot-preview-note>${esc(model.previewNote || "")}</p>
                    <div class="aps-bot-choice">
                        <label><input type="radio" name="aps-bot-source" value="draft" ${model.previewSource === "published" ? "" : "checked"}> ${t("Preview the texts in the editors")}</label>
                        <label><input type="radio" name="aps-bot-source" value="published" ${model.previewSource === "published" ? "checked" : ""}> ${t("Preview the published copy")}</label>
                    </div>
                    <label class="aps-bot-field">
                        <span>${t("Sample situation")}</span>
                        <select data-bot-scenario>
                            ${scenarios.map(item => `<option value="${esc(item.id || "")}" ${item.selected ? "selected" : ""}>${esc(item.label || "")}</option>`).join("")}
                        </select>
                    </label>
                    <p data-bot-hint>${esc(model.scenarioHint || "")}</p>
                    <div class="aps-bot-actions">
                        ${uiButton({
                            label: t("Restart preview"),
                            variant: "secondary",
                            attrs: { "data-bot-restart": "1" },
                        })}
                    </div>
                    <div class="aps-bot-transcript" data-bot-transcript role="log" aria-relevant="additions"></div>
                    <div class="aps-bot-compose">
                        <label class="aps-bot-field">
                            <span>${t("Customer message")}</span>
                            <input type="text" data-bot-preview-input dir="auto" maxlength="500">
                        </label>
                        ${uiButton({
                            label: t("Send in preview"),
                            variant: "primary",
                            attrs: { "data-bot-preview-send": "1" },
                        })}
                    </div>
                </section>
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
            renderCustomerBot,
            renderCustomerBotOperation,
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
