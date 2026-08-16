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
            $main.html(`<div class="aw-loading">${t("جاري تحميل مستخدمي المعمل...")}</div>`);
        }

        function renderError(message) {
            $main.html(`
                <div class="aw-error" dir="rtl">
                    <b>${t("تعذر تحميل إدارة المستخدمين")}</b>
                    <div class="aw-error-copy">${esc(message || t("حدث خطأ غير متوقع."))}</div>
                </div>
            `);
        }

        function toolbarHtml(model) {
            return `
                <div class="aw-toolbar">
                    <div class="aw-field">
                        <label>${t("بحث بالاسم أو البريد")}</label>
                        <input class="aw-search" type="search" value="${esc(model.search)}" placeholder="${t("اكتب للبحث...")}">
                    </div>
                    <div class="aw-field">
                        <label>${t("حالة الحساب")}</label>
                        <select class="aw-enabled-filter">
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
            return `<div class="aw-summary">${cards.map(item => `<div class="aw-stat"><span>${esc(item.label)}</span><b>${esc(item.value)}</b></div>`).join("")}</div>`;
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
                : `<span class="aw-badge">${t("بدون أدوار مخصصة")}</span>`;
            const activeBadge = user.activeAssignments
                ? `<span class="aw-badge is-warning">${t("مراحل نشطة")}: ${user.activeAssignments}</span>`
                : "";
            const warning = user.showActiveAssignmentWarning
                ? `<div class="text-muted aw-active-warning">${t("يجب إعادة إسناد المراحل النشطة قبل تعطيل المستخدم أو تغيير أدواره.")}</div>`
                : "";

            return `
                <article class="aw-card">
                    <div class="aw-card-head">
                        <div>
                            <h3 class="aw-name">${esc(user.name)}</h3>
                            <div class="aw-email">${esc(user.email)}</div>
                            <div class="aw-badges">
                                <span class="aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}">${user.enabled ? t("مفعّل") : t("معطّل")}</span>
                                ${activeBadge}
                            </div>
                            <div class="aw-badges">${roleBadges}</div>
                        </div>
                    </div>
                    <div class="aw-details">
                        <div class="aw-detail"><span>${t("اللغة")}</span><b>${esc(user.languageLabel)}</b></div>
                        <div class="aw-detail"><span>${t("مساحة العمل")}</span><b>${esc(user.defaultWorkspace)}</b></div>
                        <div class="aw-detail"><span>${t("آخر نشاط")}</span><b>${esc(user.lastActive)}</b></div>
                    </div>
                    ${warning}
                    <div class="aw-actions">${buttons.join("")}</div>
                </article>
            `;
        }

        function availableUserCardHtml(user) {
            return `
                <article class="aw-card is-available">
                    <div class="aw-card-head">
                        <div>
                            <h3 class="aw-name">${esc(user.name)}</h3>
                            <div class="aw-email">${esc(user.email)}</div>
                            <div class="aw-badges">
                                <span class="aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}">${user.enabled ? t("مفعّل") : t("معطّل")}</span>
                                <span class="aw-badge is-neutral">${t("خارج المعمل")}</span>
                            </div>
                        </div>
                    </div>
                    <div class="aw-details">
                        <div class="aw-detail"><span>${t("التطبيق الحالي")}</span><b>${esc(user.source)}</b></div>
                        <div class="aw-detail"><span>${t("مساحة العمل")}</span><b>${esc(user.defaultWorkspace)}</b></div>
                        <div class="aw-detail"><span>${t("آخر نشاط")}</span><b>${esc(user.lastActive)}</b></div>
                    </div>
                    <div class="aw-scope-note">${t("إضافته إلى المعمل لا تمنحه أي دور أو صلاحية تشغيلية تلقائيًا. بعد الإضافة يمكنك اختيار أدوار المعمل له بشكل صريح.")}</div>
                    <div class="aw-actions"><button class="btn btn-primary aw-adopt-user" data-user="${esc(user.email)}">${t("إضافة إلى المعمل")}</button></div>
                </article>
            `;
        }

        function usersHtml(users) {
            if (!users.length) return `<div class="aw-empty">${t("لا يوجد مستخدمون في المعمل مطابقون للبحث الحالي.")}</div>`;
            return users.map(userCardHtml).join("");
        }

        function availableUsersHtml(users) {
            if (!users.length) return `<div class="aw-empty">${t("لا توجد حسابات System User خارج المعمل مطابقة للبحث الحالي.")}</div>`;
            return users.map(availableUserCardHtml).join("");
        }

        function workforceSectionHtml(model) {
            return `
                <section class="aw-section">
                    <div class="aw-section-head">
                        <div>
                            <h2 class="aw-section-title">${t("مستخدمو المعمل")}</h2>
                            <p class="aw-section-copy">${t("الحسابات التي تم ضمها إلى Almdina ويمكن إدارة أدوارها وصلاحياتها من هنا.")}</p>
                        </div>
                        <span class="aw-section-count">${model.users.length}</span>
                    </div>
                    <div class="aw-list">${usersHtml(model.users)}</div>
                </section>
            `;
        }

        function availableUsersSectionHtml(model) {
            if (!model.canCreateUsers) return "";
            return `
                <section class="aw-section">
                    <div class="aw-section-head">
                        <div>
                            <h2 class="aw-section-title">${t("مستخدمون غير مضافين إلى المعمل")}</h2>
                            <p class="aw-section-copy">${t("حسابات System User الموجودة في Frappe ولم تُضم بعد إلى نطاق Almdina.")}</p>
                        </div>
                        <span class="aw-section-count">${model.availableUsers.length}</span>
                    </div>
                    <div class="aw-list">${availableUsersHtml(model.availableUsers)}</div>
                </section>
            `;
        }

        function render(model) {
            $main.html(`
                <div class="aw-shell">
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
            `).join("") || `<div class="aw-empty">${t("لا توجد تغييرات مسجلة.")}</div>`}</div>`;
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
