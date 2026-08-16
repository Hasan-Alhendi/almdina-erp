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
            $body.html(`<div class="aps-empty">${t("جاري تحميل إعدادات المعمل...")}</div>`);
        }

        function renderError(message) {
            $body.html(`<div class="aps-error">${esc(message || t("تعذر تحميل إعدادات المعمل."))}</div>`);
        }

        function rowHtml(row) {
            const value = row.multiline ? multiline(row.value) : esc(row.value);
            return `<div class="aps-value"><span>${esc(row.label)}</span><b>${value}</b></div>`;
        }

        function sectionCard(section) {
            return `
                <article class="aps-section">
                    <div class="aps-section-head">
                        <div><h3>${esc(section.title)}</h3><div class="aps-section-desc">${esc(section.description)}</div></div>
                        <span class="aps-permission ${section.editable ? "" : "readonly"}">${section.editable ? t("قابل للتعديل") : t("عرض فقط")}</span>
                    </div>
                    <div class="aps-values">${section.rows.map(rowHtml).join("")}</div>
                    ${section.editable ? `<div class="aps-actions"><button class="btn btn-primary aps-edit" data-section="${esc(section.key)}">${t("تعديل هذا القسم")}</button></div>` : ""}
                </article>
            `;
        }

        function legacySettingsDetails(model) {
            if (!model.hasLegacy) return "";
            return `
                <details class="aps-legacy">
                    <summary><span>${t("بيانات إعدادات قديمة محفوظة")}<span class="aps-readonly-chip">${t("للقراءة فقط")}</span></span></summary>
                    <div class="aps-legacy-copy">${t("هذه القيم كانت مستخدمة في وظائف مخزون وبقايا ألواح قديمة تم إيقافها تشغيليًا. لم نحذفها من قاعدة البيانات، وتظهر هنا فقط حتى تبقى جميع بيانات إعدادات المعمل في مكان واحد دون فقدان أي قيمة تاريخية.")}</div>
                    <div class="aps-legacy-grid">${model.legacy.map(rowHtml).join("")}</div>
                </details>
            `;
        }

        function render(model) {
            $body.html(`
                <div class="aps-shell">
                    <section class="aps-hero">
                        <h2>${t("الإعدادات الافتراضية للمعمل")}</h2>
                        <p>${t("هذه هي الواجهة الموحدة الوحيدة لإعدادات المعمل. جميع الإعدادات النشطة موجودة هنا، والقيم القديمة المحفوظة تظهر في قسم منفصل للقراءة فقط. كل تعديل نشط يمر عبر الصلاحيات وسجل التغييرات.")}</p>
                    </section>
                    <section class="aps-sections">${model.sections.map(sectionCard).join("")}</section>
                    ${legacySettingsDetails(model)}
                    <div class="aps-note">${t("الرابط القديم لنموذج Almdina ERP Settings أصبح مسارًا تاريخيًا فقط وسيتم تحويله تلقائيًا إلى هذه الصفحة. لا يتم حذف أي قيمة من السجل عند التحويل، وأرقام التواصل تقبل عدة أسطر مثل: أرضي، موبايل، واتس اب.")}</div>
                </div>
            `);
        }

        function auditHtml(rows) {
            if (!rows.length) return `<div class="aps-empty">${t("لا توجد تغييرات مسجلة.")}</div>`;
            return `<div class="aps-audit">${rows.map(row => `
                <div class="aps-audit-item">
                    <div class="aps-audit-head"><span>${esc(row.action)}</span><span>${esc(row.changed_on)}</span></div>
                    <div class="aps-audit-meta">${t("بواسطة")}: ${esc(row.changed_by)} · ${esc(row.source || "")}</div>
                    ${row.changed_fields ? `<div class="aps-audit-meta">${t("الحقول")}: ${esc(row.changed_fields)}</div>` : ""}
                </div>
            `).join("")}</div>`;
        }

        function auditLoadingHtml() {
            return `<div class="aps-empty">${t("جاري تحميل السجل...")}</div>`;
        }

        function auditErrorHtml(message) {
            return `<div class="aps-error">${esc(message || t("تعذر تحميل السجل."))}</div>`;
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
