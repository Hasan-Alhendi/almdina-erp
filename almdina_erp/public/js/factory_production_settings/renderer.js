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

        function statusTone(value) {
            const normalized = String(value ?? "").trim();
            if (normalized === t("مسموح") || normalized === "مسموح") return "success";
            if (normalized === t("غير مسموح") || normalized === "غير مسموح") return "danger";
            return "";
        }

        function rowHtml(row) {
            const tone = row.multiline ? "" : statusTone(row.value);
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
                    <b class="aps-value-data">${value}</b>
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
                                <span class="aps-section-kicker">${t("إعدادات القسم")}</span>
                                <h3>${esc(section.title)}</h3>
                                <div class="aps-section-desc">${esc(section.description)}</div>
                            </div>
                        </div>
                        <div class="aps-section-tools">
                            ${section.editable ? uiButton({
                                label: t("تعديل"),
                                variant: "secondary",
                                className: "aps-edit",
                                attrs: {
                                    "data-section": section.key,
                                    title: t("تعديل هذا القسم"),
                                    "aria-label": t("تعديل هذا القسم"),
                                },
                            }) : ""}
                        </div>
                    </div>
                    <div class="aps-values">${section.rows.map(rowHtml).join("")}</div>
                    ${section.editable ? "" : `
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
                <div class="almdina-ui aps-shell alm-page alm-page--admin">
                    <header class="aps-hero alm-page-intro alm-page-intro--accented">
                        <div class="aps-hero-layout">
                            <div class="aps-hero-copy alm-page-intro__copy">
                                <div class="aps-hero-titles">
                                    <h2 class="alm-page-intro__title">${t("إعدادات تشغيل المعمل الافتراضية")}</h2>
                                    <p class="alm-page-intro__description">${t("القيم التشغيلية النشطة المعتمدة في كافة عمليات ومحطات العمل")}</p>
                                </div>
                            </div>
                        </div>
                    </header>

                    <div class="aps-section-intro alm-section-header">
                        <div>
                            <span class="alm-section-header__kicker">${t("الإعدادات النشطة")}</span>
                            <strong class="alm-section-header__title">${t("اضبط كل مجموعة من مكانها المخصص")}</strong>
                        </div>
                        <span class="aps-section-intro-note alm-section-header__note">${t("التعديل يظهر فقط للأقسام المسموحة لك")}</span>
                    </div>
                    <section class="aps-sections">
                        ${model.sections.map(sectionCard).join("")}
                        ${model.canManageWhatsAppSession ? `
                        <article class="aps-section aps-whatsapp" data-whatsapp-root>
                            <div class="aps-whatsapp-loading">${t("جاري تحميل حالة WhatsApp...")}</div>
                        </article>
                        ` : ""}
                        ${model.showBackupPanel ? `
                        <article class="aps-section aps-backup" data-backup-root>
                            <div class="aps-backup-loading">${t("جاري تحميل سجل النسخ الاحتياطية...")}</div>
                        </article>
                        ` : ""}
                    </section>
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

        function backupStatusLabel(status) {
            const labels = {
                Queued: t("في الانتظار"),
                Running: t("قيد التنفيذ"),
                Prepared: t("تم تجهيز الاستعادة"),
                Completed: t("مكتملة"),
                Failed: t("فشلت"),
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
                return `<div class="aps-empty"><strong>${t("لا توجد عمليات نسخ بعد")}</strong><span>${t("استخدم Create Backup Now لإنشاء أول نسخة محلية.")}</span></div>`;
            }
            return `<div class="aps-backup-history">${rows.map(row => {
                const candidate = restorable.get(row.operation_id);
                const restoreButton = candidate && snapshot.permissions && snapshot.permissions.can_restore && snapshot.restore_runtime_ready
                    ? uiButton({
                        label: t("استعادة"),
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
                            <div><strong>${esc(row.backup_identifier || row.operation_id || "—")}</strong><span>${esc(row.operation_type || "")} · ${esc(row.target || "")}</span></div>
                            ${uiBadge({ label: backupStatusLabel(row.status), tone: backupStatusTone(row.status) })}
                        </div>
                        <div class="aps-backup-row-meta">
                            <span>${esc(row.requested_on || "—")}</span>
                            <span>${esc(sizeLabel(row.total_size))}</span>
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
                            <span class="aps-section-kicker">${t("الإدارة والتنفيذ")}</span>
                            <h3>${t("Backup History & Actions")}</h3>
                            <div class="aps-section-desc">${t("كل نسخة تُنشأ بمحرك Frappe الرسمي، وتظهر النتيجة هنا دون عرض مسارات محلية أو بيانات اعتماد.")}</div>
                        </div>
                    </div>
                    <div class="aps-section-tools aps-backup-actions">
                        ${canManage ? uiButton({ label: t("Test SSH Connection"), variant: "secondary", className: "aps-backup-test" }) : ""}
                        ${canManage ? uiButton({ label: t("Create Backup Now"), variant: "primary", className: "aps-backup-create" }) : ""}
                    </div>
                </div>
                ${canRestore && !snapshot.restore_runtime_ready ? `<div class="aps-readonly-note">${t("الاستعادة معطّلة حتى تُضبط بيانات DB root في إعداد Frappe التشغيلي.")}</div>` : ""}
                ${backupHistoryHtml(snapshot)}
            `;
        }

        function renderBackup(snapshot) {
            const $root = $body.find("[data-backup-root]");
            if ($root.length) $root.html(backupHtml(snapshot));
        }

        function renderBackupError(message) {
            const $root = $body.find("[data-backup-root]");
            if ($root.length) $root.html(`<div class="aps-error" role="alert"><span class="aps-error-icon" aria-hidden="true">!</span><div><strong>${t("تعذر تحميل إدارة النسخ")}</strong><span>${esc(message || t("حدث خطأ غير متوقع."))}</span></div></div>`);
        }

        function statusLabel(status) {
            const labels = {
                ready: t("تعمل"),
                created: t("أُنشئت"),
                initializing: t("جاري التهيئة"),
                qr_ready: t("بانتظار مسح الرمز"),
                authenticating: t("جاري التحقق"),
                disconnected: t("غير متصلة"),
                action_required: t("تحتاج إجراء"),
                failed: t("فشلت"),
            };
            const key = String(status || "").trim();
            return labels[key] || (key ? key : t("غير معروفة"));
        }

        function whatsappHtml(snapshot = {}) {
            if (snapshot.configured === false) {
                return `
                    <div class="aps-section-head">
                        <div class="aps-section-copy">
                            <span class="aps-section-accent" aria-hidden="true"></span>
                            <div class="aps-section-titles">
                                <span class="aps-section-kicker">${t("تكامل خارجي")}</span>
                                <h3>${t("جلسة WhatsApp")}</h3>
                                <div class="aps-section-desc">${esc(snapshot.reason || t("لم يتم ضبط عنوان خادم WhatsApp أو مفتاح API."))}</div>
                            </div>
                        </div>
                        <div class="aps-section-tools">
                            <span class="aps-permission readonly"><span class="aps-permission-dot" aria-hidden="true"></span>${t("غير مضبوط")}</span>
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
                                <span class="aps-section-kicker">${t("تكامل خارجي")}</span>
                                <h3>${t("جلسة WhatsApp")}</h3>
                                <div class="aps-section-desc">${t("اربط جلسة واحدة مع واتساب ويب لإرسال جداول القياسات للزبائن.")}</div>
                            </div>
                        </div>
                        <div class="aps-section-tools">
                            <span class="aps-permission readonly"><span class="aps-permission-dot" aria-hidden="true"></span>${t("غير مربوطة")}</span>
                        </div>
                    </div>
                    <div class="aps-actions">
                        ${uiButton({
                            label: t("إنشاء وربط WhatsApp"),
                            variant: "primary",
                            className: "aps-whatsapp-create",
                        })}
                    </div>
                `;
            }
            const session = snapshot.session || {};
            const working = Boolean(snapshot.working);
            const rows = [
                [t("الحالة"), statusLabel(session.status)],
                [t("الاسم"), session.name],
                [t("رقم الجلسة"), session.phone],
                [t("اسم العرض"), session.push_name],
            ];
            if (session.last_error) rows.push([t("آخر خطأ"), session.last_error]);
            return `
                <div class="aps-section-head">
                    <div class="aps-section-copy">
                        <span class="aps-section-accent" aria-hidden="true"></span>
                        <div class="aps-section-titles">
                            <span class="aps-section-kicker">${t("تكامل خارجي")}</span>
                            <h3>${t("جلسة WhatsApp")}</h3>
                            <div class="aps-section-desc">${working ? t("الجلسة متصلة ويمكن إرسال رسائل الزبائن.") : esc(snapshot.reason || t("الجلسة غير متصلة."))}</div>
                        </div>
                    </div>
                    <div class="aps-section-tools">
                        <span class="aps-permission ${working ? "" : "readonly"}">
                            <span class="aps-permission-dot" aria-hidden="true"></span>${working ? t("تعمل") : t("لا تعمل")}
                        </span>
                    </div>
                </div>
                <div class="aps-values">${rows.map(([label, value]) => rowHtml({ label, value })).join("")}</div>
                ${working ? "" : `
                    <div class="aps-actions">
                        ${uiButton({
                            label: t("إعادة اتصال"),
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
