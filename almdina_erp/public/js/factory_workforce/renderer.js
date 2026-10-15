(() => {
    "use strict";

    if (window.AlmdinaFactoryWorkforceRenderer) return;

    function create(options = {}) {
        const $main = options.$main;
        const esc = options.escapeHtml;
        const translate = options.translate;
        if (!$main || typeof esc !== "function" || typeof translate !== "function") {
            throw new Error("Factory workforce renderer dependencies are unavailable");
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
                throw new Error("AlmdinaUi.button is required for Factory Workforce rendering");
            }
            return ui.button(options);
        }

        function uiBadge(options) {
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.badge !== "function") {
                throw new Error("AlmdinaUi.badge is required for Factory Workforce rendering");
            }
            return ui.badge(options);
        }

        function renderLoading() {
            $main.html(`
                <div class="aw-loading" role="status" aria-live="polite">
                    <span class="aw-loading-dot" aria-hidden="true"></span>
                    <span>${t("Loading factory users...")}</span>
                </div>
            `);
        }

        function renderError(message) {
            $main.html(`
                <div class="aw-error" role="alert">
                    <div class="aw-error-icon" aria-hidden="true">!</div>
                    <div>
                        <b>${t("Could not load user management")}</b>
                        <div class="aw-error-copy">${esc(message || t("An unexpected error occurred."))}</div>
                    </div>
                </div>
            `);
        }

        function heroHtml(model) {
            return `
                <header class="aw-hero alm-page-intro alm-page-intro--accented">
                    <div class="aw-hero-copy alm-page-intro__copy">
                        <span class="aw-eyebrow alm-page-intro__eyebrow">${t("Workforce management")}</span>
                        <h2 class="alm-page-intro__title">${t("Almdina users")}</h2>
                        <p class="alm-page-intro__description">${t("Manage factory accounts and their roles from one place. Roles and permissions are not granted automatically; permissions are owned by Almdina, while the login page is determined by the Home Page in the Frappe Role.")}</p>
                    </div>
                    <div class="aw-hero-meta alm-page-intro__meta" aria-label="${t("Current list summary")}">
                        <span>${t("Visible users")}</span>
                        <strong>${model.users.length}</strong>
                    </div>
                </header>
            `;
        }

        function toolbarHtml() {
            return `
                <div class="aw-toolbar alm-toolbar" role="search">
                    <div class="aw-toolbar-heading alm-toolbar__heading">
                        <span class="aw-toolbar-kicker alm-toolbar__kicker">${t("Filter list")}</span>
                        <strong>${t("User quick access")}</strong>
                    </div>
                    <div class="aw-field aw-search-field">
                        <span class="aw-field-label">${t("Search by name or email")}</span>
                        <div class="aw-search-control">
                            <span class="aw-search-icon" aria-hidden="true">⌕</span>
                            <div class="aw-search-mount"></div>
                        </div>
                    </div>
                    <div class="aw-field aw-enabled-field">
                        <span class="aw-field-label">${t("Account status")}</span>
                        <div class="aw-enabled-mount aw-enabled-filter"></div>
                    </div>
                </div>
            `;
        }

        function summaryHtml(cards) {
            const classes = ["total", "enabled", "disabled", "assignments"];
            const tones = ["neutral", "success", "danger", "info"];
            return `<div class="aw-summary alm-summary-grid" aria-label="${t("Workforce summary")}">${cards.map((item, index) => `
                <div class="aw-stat aw-stat-${classes[index] || "total"} alm-summary-card" data-tone="${tones[index] || "neutral"}">
                    <span>${esc(item.label)}</span>
                    <b>${esc(item.value)}</b>
                </div>
            `).join("")}</div>`;
        }

        function userCardHtml(user) {
            const buttons = [];
            const userAttr = { "data-user": user.email };
            if (user.canEdit) {
                buttons.push(uiButton({
                    label: t("Edit"),
                    variant: "secondary",
                    className: "aw-edit",
                    attrs: userAttr,
                }));
            }
            if (user.canResetPassword) {
                buttons.push(uiButton({
                    label: t("Temporary password"),
                    variant: "secondary",
                    className: "aw-password",
                    attrs: userAttr,
                }));
            }
            if (user.canDisable) {
                buttons.push(uiButton({
                    label: t("Disable"),
                    variant: "danger",
                    className: "aw-toggle",
                    attrs: { ...userAttr, "data-enabled": "0" },
                }));
            }
            if (user.canEnable) {
                buttons.push(uiButton({
                    label: t("Enable"),
                    variant: "primary",
                    className: "aw-toggle",
                    attrs: { ...userAttr, "data-enabled": "1" },
                }));
            }
            buttons.push(uiButton({
                label: t("Change log"),
                variant: "secondary",
                className: "aw-audit-open",
                attrs: userAttr,
            }));

            const roleBadges = user.roles.length
                ? user.roles.map(role => uiBadge({
                    label: role,
                    tone: "info",
                    className: "aw-badge aw-role",
                })).join("")
                : uiBadge({
                    label: t("No custom roles"),
                    tone: "neutral",
                    className: "aw-badge",
                });
            const activeBadge = user.activeAssignments
                ? uiBadge({
                    label: `${t("Active stages")}: ${user.activeAssignments}`,
                    tone: "warning",
                    className: "aw-badge",
                })
                : "";
            const assignmentWarning = user.showActiveAssignmentWarning
                ? `<div class="aw-active-warning"><span aria-hidden="true">!</span><span>${t("Active stages must be reassigned before disabling the user or changing their roles.")}</span></div>`
                : "";
            const roleConflictWarning = user.roleHomeConflict
                ? `<div class="aw-active-warning"><span aria-hidden="true">!</span><span>${t("More than one Role defines a different Home Page. Edit the roles in Frappe before changing them for this user.")}</span></div>`
                : "";
            const workspaceWarning = user.defaultWorkspaceConflict
                ? `<div class="aw-active-warning"><span aria-hidden="true">!</span><span>${t("Default Workspace is set for this user and may override the Role's Home Page in Frappe. Review it in the user settings if you want the Role to be the source of the login page.")}</span></div>`
                : "";

            return `
                <article class="aw-card ${user.enabled ? "is-enabled-user" : "is-disabled-user"}">
                    <div class="aw-card-head">
                        <div class="aw-identity">
                            <span class="aw-avatar" aria-hidden="true">${esc(String(user.name || user.email).trim().charAt(0) || "•")}</span>
                            <div class="aw-identity-copy">
                                <h3 class="aw-name">${esc(user.name)}</h3>
                                <div class="aw-email" dir="ltr">${esc(user.email)}</div>
                            </div>
                        </div>
                        ${uiBadge({
                            label: user.enabled ? t("Enabled") : t("Disabled"),
                            tone: user.enabled ? "success" : "danger",
                            className: `aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}`,
                        })}
                    </div>
                    <div class="aw-badges aw-role-row">${roleBadges}${activeBadge}</div>
                    <div class="aw-details">
                        <div class="aw-detail"><span>${t("Language")}</span><b>${esc(user.languageLabel)}</b></div>
                        <div class="aw-detail"><span>${t("Home Page for Roles")}</span><b>${esc(user.roleHomeSummary)}</b></div>
                        <div class="aw-detail"><span>${t("Default Workspace")}</span><b>${esc(user.defaultWorkspace)}</b></div>
                        <div class="aw-detail"><span>${t("Last activity")}</span><b>${esc(user.lastActive)}</b></div>
                    </div>
                    ${assignmentWarning}${roleConflictWarning}${workspaceWarning}
                    <div class="aw-actions">${buttons.join("")}</div>
                </article>
            `;
        }

        function availableUserCardHtml(user) {
            return `
                <article class="aw-card is-available">
                    <div class="aw-card-head">
                        <div class="aw-identity">
                            <span class="aw-avatar is-available-avatar" aria-hidden="true">${esc(String(user.name || user.email).trim().charAt(0) || "•")}</span>
                            <div class="aw-identity-copy">
                                <h3 class="aw-name">${esc(user.name)}</h3>
                                <div class="aw-email" dir="ltr">${esc(user.email)}</div>
                            </div>
                        </div>
                        <div class="aw-badges aw-card-statuses">
                            ${uiBadge({
                                label: user.enabled ? t("Enabled") : t("Disabled"),
                                tone: user.enabled ? "success" : "danger",
                                className: `aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}`,
                            })}
                            ${uiBadge({
                                label: t("Outside the factory"),
                                tone: "neutral",
                                className: "aw-badge",
                            })}
                        </div>
                    </div>
                    <div class="aw-details">
                        <div class="aw-detail"><span>${t("Current app")}</span><b>${esc(user.source)}</b></div>
                        <div class="aw-detail"><span>${t("Workspace")}</span><b>${esc(user.defaultWorkspace)}</b></div>
                        <div class="aw-detail"><span>${t("Last activity")}</span><b>${esc(user.lastActive)}</b></div>
                    </div>
                    <div class="aw-scope-note">${t("Adding them to the factory does not automatically grant any role or operational permission, and does not change Default Workspace or Default App. The login page remains managed by Frappe.")}</div>
                    <div class="aw-actions aw-actions-single">${uiButton({
                        label: t("Add to factory"),
                        variant: "primary",
                        className: "aw-adopt-user",
                        attrs: { "data-user": user.email },
                    })}</div>
                </article>
            `;
        }

        function usersHtml(users) {
            if (!users.length) return `<div class="aw-empty"><strong>${t("No results")}</strong><span>${t("No factory users match the current search.")}</span></div>`;
            return users.map(userCardHtml).join("");
        }

        function availableUsersHtml(users) {
            if (!users.length) return `<div class="aw-empty"><strong>${t("No accounts available")}</strong><span>${t("No System User accounts outside the factory match the current search.")}</span></div>`;
            return users.map(availableUserCardHtml).join("");
        }

        function sectionHeading(title, copy, count, tone = "") {
            return `
                <div class="aw-section-head ${tone}">
                    <div>
                        <h2 class="aw-section-title">${title}</h2>
                        <p class="aw-section-copy">${copy}</p>
                    </div>
                    <span class="aw-section-count">${count}</span>
                </div>
            `;
        }

        function workforceSectionHtml(model) {
            return `
                <section class="aw-section aw-workforce-section">
                    ${sectionHeading(
                        t("Factory users"),
                        t("Accounts added to Almdina. Roles determine permissions, and Frappe Role.Home Page determines the login page."),
                        model.users.length
                    )}
                    <div class="aw-list aw-user-grid">${usersHtml(model.users)}</div>
                </section>
            `;
        }

        function availableUsersSectionHtml(model) {
            if (!model.canCreateUsers) return "";
            return `
                <section class="aw-section aw-available-section">
                    ${sectionHeading(
                        t("Users not added to the factory"),
                        t("System User accounts that exist in Frappe and have not yet been added to the Almdina scope."),
                        model.availableUsers.length,
                        "is-secondary"
                    )}
                    <div class="aw-list aw-user-grid">${availableUsersHtml(model.availableUsers)}</div>
                </section>
            `;
        }

        function updateContent(model) {
            $main.find(".aw-hero-meta strong").text(model.users.length);
            $main.find(".aw-summary").replaceWith(summaryHtml(model.summary));
            $main.find(".aw-workforce-section").replaceWith(workforceSectionHtml(model));
            const availableSection = availableUsersSectionHtml(model);
            const $available = $main.find(".aw-available-section");
            if (availableSection) {
                if ($available.length) $available.replaceWith(availableSection);
                else $main.find(".aw-shell").append(availableSection);
            } else {
                $available.remove();
            }
        }

        function render(model, options = {}) {
            if (options.preserveToolbar === true) {
                updateContent(model);
                return;
            }
            $main.html(`
                <div class="almdina-ui aw-shell alm-page alm-page--admin" dir="${uiDirection()}">
                    ${heroHtml(model)}
                    ${toolbarHtml()}
                    ${summaryHtml(model.summary)}
                    ${workforceSectionHtml(model)}
                    ${availableUsersSectionHtml(model)}
                </div>
            `);
        }

        function auditHtml(events) {
            return `<div class="aw-audit">${events.map(event => `
                <div class="aw-audit-item">
                    <div class="aw-audit-title"><span>${esc(event.action || "")}</span><span>${esc(event.changed_on || "")}</span></div>
                    <div class="aw-audit-meta">${esc(event.changed_by || "")}${event.changed_fields ? ` · ${esc(event.changed_fields)}` : ""}</div>
                    <div class="aw-audit-summary">${esc(event.summary || "")}</div>
                </div>
            `).join("") || `<div class="aw-empty"><strong>${t("No log")}</strong><span>${t("No recorded changes.")}</span></div>`}</div>`;
        }

        return Object.freeze({
            renderLoading,
            renderError,
            render,
            auditHtml,
        });
    }

    window.AlmdinaFactoryWorkforceRenderer = Object.freeze({ create });
})();
