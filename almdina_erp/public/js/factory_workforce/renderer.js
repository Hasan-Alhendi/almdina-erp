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

        function renderLoading() {
            $main.html(`
                <div class="aw-loading" role="status" aria-live="polite">
                    <span class="aw-loading-dot" aria-hidden="true"></span>
                    <span>${t("جاري تحميل مستخدمي المعمل...")}</span>
                </div>
            `);
        }

        function renderError(message) {
            $main.html(`
                <div class="aw-error" dir="rtl" role="alert">
                    <div class="aw-error-icon" aria-hidden="true">!</div>
                    <div>
                        <b>${t("تعذر تحميل إدارة المستخدمين")}</b>
                        <div class="aw-error-copy">${esc(message || t("حدث خطأ غير متوقع."))}</div>
                    </div>
                </div>
            `);
        }

        function heroHtml(model) {
            return `
                <header class="aw-hero">
                    <div class="aw-hero-copy">
                        <span class="aw-eyebrow">${t("إدارة القوى العاملة")}</span>
                        <h2>${t("مستخدمو Almdina")}</h2>
                        <p>${t("أدر حسابات المعمل وأدوارها من مكان واحد. الأدوار والصلاحيات لا تُمنح تلقائيًا؛ الصلاحيات تملكها Almdina، أما صفحة الدخول فيحددها Home Page داخل Role في Frappe.")}</p>
                    </div>
                    <div class="aw-hero-meta" aria-label="${t("ملخص القائمة الحالية")}">
                        <span>${t("المستخدمون الظاهرون")}</span>
                        <strong>${model.users.length}</strong>
                    </div>
                </header>
            `;
        }

        function toolbarHtml(model) {
            return `
                <div class="aw-toolbar" role="search">
                    <div class="aw-toolbar-heading">
                        <span class="aw-toolbar-kicker">${t("تصفية القائمة")}</span>
                        <strong>${t("الوصول السريع للمستخدم")}</strong>
                    </div>
                    <div class="aw-field aw-search-field">
                        <label for="aw-workforce-search">${t("بحث بالاسم أو البريد")}</label>
                        <div class="aw-search-control">
                            <span class="aw-search-icon" aria-hidden="true">⌕</span>
                            <input id="aw-workforce-search" class="aw-search" type="search" value="${esc(model.search)}" placeholder="${t("اكتب للبحث...")}" autocomplete="off">
                        </div>
                    </div>
                    <div class="aw-field">
                        <label for="aw-enabled-filter">${t("حالة الحساب")}</label>
                        <select id="aw-enabled-filter" class="aw-enabled-filter">
                            <option value="all" ${model.enabled === "all" ? "selected" : ""}>${t("الكل")}</option>
                            <option value="1" ${model.enabled === "1" ? "selected" : ""}>${t("مفعّل")}</option>
                            <option value="0" ${model.enabled === "0" ? "selected" : ""}>${t("معطّل")}</option>
                        </select>
                    </div>
                    <button type="button" class="btn btn-default aw-refresh">${t("تحديث القائمة")}</button>
                </div>
            `;
        }

        function summaryHtml(cards) {
            const classes = ["total", "enabled", "disabled", "assignments"];
            return `<div class="aw-summary" aria-label="${t("ملخص القوى العاملة")}">${cards.map((item, index) => `
                <div class="aw-stat aw-stat-${classes[index] || "total"}">
                    <span>${esc(item.label)}</span>
                    <b>${esc(item.value)}</b>
                </div>
            `).join("")}</div>`;
        }

        function userCardHtml(user) {
            const buttons = [];
            if (user.canEdit) buttons.push(`<button class="btn btn-default aw-edit" data-user="${esc(user.email)}">${t("تعديل")}</button>`);
            if (user.canResetPassword) buttons.push(`<button class="btn btn-default aw-password" data-user="${esc(user.email)}">${t("كلمة مرور مؤقتة")}</button>`);
            if (user.canDisable) buttons.push(`<button class="btn btn-danger aw-toggle" data-enabled="0" data-user="${esc(user.email)}">${t("تعطيل")}</button>`);
            if (user.canEnable) buttons.push(`<button class="btn btn-primary aw-toggle" data-enabled="1" data-user="${esc(user.email)}">${t("تفعيل")}</button>`);
            buttons.push(`<button class="btn btn-default aw-audit-open" data-user="${esc(user.email)}">${t("سجل التغييرات")}</button>`);

            const roleBadges = user.roles.length
                ? user.roles.map(role => `<span class="aw-badge aw-role">${esc(role)}</span>`).join("")
                : `<span class="aw-badge is-neutral">${t("بدون أدوار مخصصة")}</span>`;
            const activeBadge = user.activeAssignments
                ? `<span class="aw-badge is-warning">${t("مراحل نشطة")}: ${user.activeAssignments}</span>`
                : "";
            const assignmentWarning = user.showActiveAssignmentWarning
                ? `<div class="aw-active-warning"><span aria-hidden="true">!</span><span>${t("يجب إعادة إسناد المراحل النشطة قبل تعطيل المستخدم أو تغيير أدواره.")}</span></div>`
                : "";
            const roleConflictWarning = user.roleHomeConflict
                ? `<div class="aw-active-warning"><span aria-hidden="true">!</span><span>${t("هناك أكثر من Role يحدد Home Page مختلفة. عدّل الأدوار في Frappe قبل تغييرها لهذا المستخدم.")}</span></div>`
                : "";
            const workspaceWarning = user.defaultWorkspaceConflict
                ? `<div class="aw-active-warning"><span aria-hidden="true">!</span><span>${t("Default Workspace مضبوط لهذا المستخدم وقد يتغلب على Home Page الخاصة بالدور في Frappe. راجعه من إعداد المستخدم إذا أردت أن يكون الدور هو مصدر صفحة الدخول.")}</span></div>`
                : "";

            return `
                <article class="aw-card ${user.enabled ? "is-enabled-user" : "is-disabled-user"}">
                    <div class="aw-card-head">
                        <div class="aw-identity">
                            <span class="aw-avatar" aria-hidden="true">${esc(String(user.name || user.email).trim().charAt(0) || "•")}</span>
                            <div class="aw-identity-copy">
                                <h3 class="aw-name">${esc(user.name)}</h3>
                                <div class="aw-email">${esc(user.email)}</div>
                            </div>
                        </div>
                        <span class="aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}">${user.enabled ? t("مفعّل") : t("معطّل")}</span>
                    </div>
                    <div class="aw-badges aw-role-row">${roleBadges}${activeBadge}</div>
                    <div class="aw-details">
                        <div class="aw-detail"><span>${t("اللغة")}</span><b>${esc(user.languageLabel)}</b></div>
                        <div class="aw-detail"><span>${t("Home Page للأدوار")}</span><b>${esc(user.roleHomeSummary)}</b></div>
                        <div class="aw-detail"><span>${t("Default Workspace")}</span><b>${esc(user.defaultWorkspace)}</b></div>
                        <div class="aw-detail"><span>${t("آخر نشاط")}</span><b>${esc(user.lastActive)}</b></div>
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
                                <div class="aw-email">${esc(user.email)}</div>
                            </div>
                        </div>
                        <div class="aw-badges aw-card-statuses">
                            <span class="aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}">${user.enabled ? t("مفعّل") : t("معطّل")}</span>
                            <span class="aw-badge is-neutral">${t("خارج المعمل")}</span>
                        </div>
                    </div>
                    <div class="aw-details">
                        <div class="aw-detail"><span>${t("التطبيق الحالي")}</span><b>${esc(user.source)}</b></div>
                        <div class="aw-detail"><span>${t("مساحة العمل")}</span><b>${esc(user.defaultWorkspace)}</b></div>
                        <div class="aw-detail"><span>${t("آخر نشاط")}</span><b>${esc(user.lastActive)}</b></div>
                    </div>
                    <div class="aw-scope-note">${t("إضافته إلى المعمل لا تمنحه أي دور أو صلاحية تشغيلية تلقائيًا، ولا تغيّر Default Workspace أو Default App. صفحة الدخول تبقى تحت إدارة Frappe.")}</div>
                    <div class="aw-actions aw-actions-single"><button class="btn btn-primary aw-adopt-user" data-user="${esc(user.email)}">${t("إضافة إلى المعمل")}</button></div>
                </article>
            `;
        }

        function usersHtml(users) {
            if (!users.length) return `<div class="aw-empty"><strong>${t("لا توجد نتائج")}</strong><span>${t("لا يوجد مستخدمون في المعمل مطابقون للبحث الحالي.")}</span></div>`;
            return users.map(userCardHtml).join("");
        }

        function availableUsersHtml(users) {
            if (!users.length) return `<div class="aw-empty"><strong>${t("لا توجد حسابات متاحة")}</strong><span>${t("لا توجد حسابات System User خارج المعمل مطابقة للبحث الحالي.")}</span></div>`;
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
                        t("مستخدمو المعمل"),
                        t("الحسابات التي تم ضمها إلى Almdina. الأدوار تحدد الصلاحيات، وFrappe Role.Home Page يحدد صفحة الدخول."),
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
                        t("مستخدمون غير مضافين إلى المعمل"),
                        t("حسابات System User الموجودة في Frappe ولم تُضم بعد إلى نطاق Almdina."),
                        model.availableUsers.length,
                        "is-secondary"
                    )}
                    <div class="aw-list aw-user-grid">${availableUsersHtml(model.availableUsers)}</div>
                </section>
            `;
        }

        function render(model) {
            $main.html(`
                <div class="aw-shell">
                    ${heroHtml(model)}
                    ${toolbarHtml(model)}
                    ${summaryHtml(model.summary)}
                    ${workforceSectionHtml(model)}
                    ${availableUsersSectionHtml(model)}
                </div>
            `);
        }

        function auditHtml(events) {
            return `<div class="aw-audit" dir="rtl">${events.map(event => `
                <div class="aw-audit-item">
                    <div class="aw-audit-title"><span>${esc(event.action || "")}</span><span>${esc(event.changed_on || "")}</span></div>
                    <div class="aw-audit-meta">${esc(event.changed_by || "")}${event.changed_fields ? ` · ${esc(event.changed_fields)}` : ""}</div>
                    <div class="aw-audit-summary">${esc(event.summary || "")}</div>
                </div>
            `).join("") || `<div class="aw-empty"><strong>${t("لا يوجد سجل")}</strong><span>${t("لا توجد تغييرات مسجلة.")}</span></div>`}</div>`;
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