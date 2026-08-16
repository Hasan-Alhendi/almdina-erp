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

        function multiline(value) {
            return esc(value || "—").replace(/\r?\n/g, "<br>");
        }

        function renderLoading() {
            $body.html(`
                <div class="aps-loading" role="status" aria-live="polite">
                    <span class="aps-loading-dot" aria-hidden="true"></span>
                    <div><strong>${t("جاري تحميل إعدادات المعمل")}</strong><span>${t("يتم تجهيز القيم والصلاحيات الحالية...")}</span></div>
                </div>
            `);
        }

        function renderError(message) {
            $body.html(`
                <div class="aps-error" role="alert">
                    <span class="aps-error-icon" aria-hidden="true">!</span>
                    <div><strong>${t("تعذر تحميل إعدادات المعمل")}</strong><span>${esc(message || t("تعذر تحميل إعدادات المعمل."))}</span></div>
                </div>
            `);
        }

        function rowHtml(row) {
            const value = row.multiline ? multiline(row.value) : esc(row.value);
            return `
                <div class="aps-value ${row.multiline ? "is-multiline" : ""}">
                    <span>${esc(row.label)}</span>
                    <b>${value}</b>
                </div>
            `;
        }

        function sectionCard(section) {
            const stateClass = section.editable ? "is-editable" : "is-readonly";
            const stateLabel = section.editable ? t("قابل للتعديل") : t("عرض فقط");
            return `
                <article class="aps-section ${stateClass}" data-section="${esc(section.key)}">
                    <div class="aps-section-head">
                        <div class="aps-section-copy">
                            <span class="aps-section-kicker">${t("إعدادات القسم")}</span>
                            <h3>${esc(section.title)}</h3>
                            <div class="aps-section-desc">${esc(section.description)}</div>
                        </div>
                        <span class="aps-permission ${section.editable ? "" : "readonly"}">
                            <span class="aps-permission-dot" aria-hidden="true"></span>${stateLabel}
                        </span>
                    </div>
                    <div class="aps-values">${section.rows.map(rowHtml).join("")}</div>
                    ${section.editable ? `
                        <div class="aps-actions">
                            <button class="btn btn-primary aps-edit" data-section="${esc(section.key)}">${t("تعديل هذا القسم")}</button>
                        </div>
                    ` : `
                        <div class="aps-readonly-note">${t("يمكنك مراجعة القيم هنا، لكن تعديل هذا القسم غير متاح لصلاحياتك الحالية.")}</div>
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
                            <span><strong>${t("بيانات إعدادات قديمة محفوظة")}</strong><small>${t("قيم تاريخية محفوظة للتوثيق ولا تدخل في التشغيل الحالي")}</small></span>
                        </span>
                        <span class="aps-readonly-chip">${t("للقراءة فقط")}</span>
                    </summary>
                    <div class="aps-legacy-body">
                        <div class="aps-legacy-copy">${t("هذه القيم كانت مستخدمة في وظائف مخزون وبقايا ألواح قديمة تم إيقافها تشغيليًا. لم نحذفها من قاعدة البيانات، وتظهر هنا فقط حتى تبقى جميع بيانات إعدادات المعمل في مكان واحد دون فقدان أي قيمة تاريخية.")}</div>
                        <div class="aps-legacy-grid">${model.legacy.map(rowHtml).join("")}</div>
                    </div>
                </details>
            `;
        }

        function render(model) {
            $body.html(`
                <div class="aps-shell">
                    <header class="aps-hero">
                        <div class="aps-hero-layout">
                            <div class="aps-hero-copy">
                                <span class="aps-eyebrow">${t("إعدادات التشغيل")}</span>
                                <h2>${t("الإعدادات الافتراضية للمعمل")}</h2>
                                <p>${t("هذه هي الواجهة الموحدة الوحيدة لإعدادات المعمل. جميع الإعدادات النشطة موجودة هنا، والقيم القديمة المحفوظة تظهر في قسم منفصل للقراءة فقط. كل تعديل نشط يمر عبر الصلاحيات وسجل التغييرات.")}</p>
                            </div>
                            <div class="aps-hero-assurances" aria-label="${t("ضمانات إدارة الإعدادات")}">
                                <div class="aps-assurance"><span aria-hidden="true">✓</span><div><strong>${t("صلاحيات واضحة")}</strong><small>${t("كل قسم يوضح إن كان قابلًا للتعديل")}</small></div></div>
                                <div class="aps-assurance"><span aria-hidden="true">↺</span><div><strong>${t("سجل محفوظ")}</strong><small>${t("التغييرات النشطة قابلة للمراجعة")}</small></div></div>
                            </div>
                        </div>
                    </header>

                    <div class="aps-section-intro">
                        <div><span>${t("الإعدادات النشطة")}</span><strong>${t("اضبط كل مجموعة من مكانها المخصص")}</strong></div>
                        <span class="aps-section-intro-note">${t("التعديل يظهر فقط للأقسام المسموحة لك")}</span>
                    </div>
                    <section class="aps-sections">${model.sections.map(sectionCard).join("")}</section>
                    ${legacySettingsDetails(model)}
                    <div class="aps-note">
                        <span class="aps-note-icon" aria-hidden="true">i</span>
                        <div>${t("الرابط القديم لنموذج Almdina ERP Settings أصبح مسارًا تاريخيًا فقط وسيتم تحويله تلقائيًا إلى هذه الصفحة. لا يتم حذف أي قيمة من السجل عند التحويل، وأرقام التواصل تقبل عدة أسطر مثل: أرضي، موبايل، واتس اب.")}</div>
                    </div>
                </div>
            `);
        }

        function auditHtml(rows) {
            if (!rows.length) {
                return `<div class="aps-empty"><strong>${t("لا يوجد سجل بعد")}</strong><span>${t("لا توجد تغييرات مسجلة.")}</span></div>`;
            }
            return `<div class="aps-audit">${rows.map(row => `
                <div class="aps-audit-item">
                    <span class="aps-audit-dot" aria-hidden="true"></span>
                    <div class="aps-audit-content">
                        <div class="aps-audit-head"><strong>${esc(row.action)}</strong><span>${esc(row.changed_on)}</span></div>
                        <div class="aps-audit-meta">${t("بواسطة")}: ${esc(row.changed_by)} · ${esc(row.source || "")}</div>
                        ${row.changed_fields ? `<div class="aps-audit-fields">${t("الحقول")}: ${esc(row.changed_fields)}</div>` : ""}
                    </div>
                </div>
            `).join("")}</div>`;
        }

        function auditLoadingHtml() {
            return `<div class="aps-empty" role="status" aria-live="polite"><strong>${t("جاري تحميل السجل...")}</strong><span>${t("يتم استرجاع آخر تغييرات إعدادات المعمل.")}</span></div>`;
        }

        function auditErrorHtml(message) {
            return `<div class="aps-error" role="alert"><span class="aps-error-icon" aria-hidden="true">!</span><div><strong>${t("تعذر تحميل السجل")}</strong><span>${esc(message || t("تعذر تحميل السجل."))}</span></div></div>`;
        }

        return Object.freeze({
            renderLoading,
            renderError,
            render,
            auditHtml,
            auditLoadingHtml,
            auditErrorHtml,
        });
    }

    window.AlmdinaFactoryProductionSettingsRenderer = Object.freeze({ create });
})();
