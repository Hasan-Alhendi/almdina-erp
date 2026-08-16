(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsRenderer) return;

    function create(options = {}) {
        const $main = options.$main;
        const esc = options.escapeHtml;
        const translate = options.translate;
        if (!$main || typeof esc !== "function" || typeof translate !== "function") {
            throw new Error("Factory permissions renderer dependencies are unavailable");
        }

        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);

        function renderShell() {
            $main.html(`
                <div class="apc-shell">
                    <header class="apc-hero">
                        <div class="apc-hero-copy">
                            <div class="apc-eyebrow">${t("إدارة الصلاحيات")}</div>
                            <h2>${t("مصفوفة صلاحيات Almdina")}</h2>
                            <p>${t("اختر الدور ثم امنحه الصلاحيات يدويًا من الصفر. لا توجد قوالب جاهزة ولا صلاحيات تلقائية. يمكن نقل مصفوفة موجودة عبر JSON بعد معاينتها، ولن يتم الحفظ تلقائيًا.")}</p>
                        </div>
                        <div class="apc-actor text-muted" aria-label="${t("المستخدم الحالي")}"></div>
                    </header>

                    <div class="apc-toolbar">
                        <section class="apc-panel apc-role-panel">
                            <div class="apc-panel-title-row">
                                <div>
                                    <div class="apc-panel-kicker">${t("الدور النشط")}</div>
                                    <div class="apc-panel-title">${t("اختر الدور")}</div>
                                </div>
                            </div>
                            <div class="apc-role-combo">
                                <div class="apc-role-combo-control">
                                    <input type="text" class="apc-role-picker" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="apc-role-menu" autocomplete="off" placeholder="${t("ابحث واختر دورًا...")}">
                                    <button type="button" class="apc-role-toggle" aria-label="${t("فتح قائمة الأدوار")}" tabindex="-1">⌄</button>
                                </div>
                                <div class="apc-role-menu" id="apc-role-menu" role="listbox" hidden></div>
                            </div>
                        </section>

                        <section class="apc-panel apc-transfer-panel">
                            <div class="apc-panel-title-row">
                                <div>
                                    <div class="apc-panel-kicker">${t("نقل آمن")}</div>
                                    <div class="apc-panel-title">${t("نقل مصفوفة الصلاحيات")}</div>
                                </div>
                            </div>
                            <div class="apc-transfer-tools">
                                <button type="button" class="btn btn-default apc-export">${t("تصدير JSON")}</button>
                                <button type="button" class="btn btn-default apc-import">${t("استيراد JSON")}</button>
                            </div>
                            <div class="apc-helper-text">${t("الاستيراد يحمّل الصلاحيات للمعاينة فقط؛ الحفظ يبقى خطوة مستقلة.")}</div>
                            <input type="file" class="apc-import-file" accept="application/json,.json" hidden>
                        </section>

                        <section class="apc-panel apc-summary-panel">
                            <div class="apc-panel-title-row">
                                <div>
                                    <div class="apc-panel-kicker">${t("نظرة سريعة")}</div>
                                    <div class="apc-panel-title">${t("ملخص الصلاحيات")}</div>
                                </div>
                                <button type="button" class="btn btn-default apc-bulk-toggle apc-select-all-global">${t("تحديد الكل للكل")}</button>
                            </div>
                            <div class="apc-stats">
                                <div class="apc-stat apc-stat-total"><strong class="apc-total-count">0</strong><span>${t("إجمالي")}</span></div>
                                <div class="apc-stat apc-stat-enabled"><strong class="apc-enabled-count">0</strong><span>${t("مفعلة")}</span></div>
                                <div class="apc-stat apc-stat-critical"><strong class="apc-critical-count">0</strong><span>${t("حرجة")}</span></div>
                                <div class="apc-stat apc-stat-change"><strong class="apc-change-count">0</strong><span>${t("تغييرات")}</span></div>
                            </div>
                        </section>
                    </div>

                    <div class="apc-loading apc-empty" role="status" aria-live="polite">${t("جاري تحميل مصفوفة الصلاحيات...")}</div>
                    <div class="apc-content" style="display:none">
                        <main class="apc-groups"></main>
                        <aside class="apc-side" aria-label="${t("تفاصيل الصلاحيات")}">
                            <div class="apc-panel apc-impact-panel"></div>
                            <div class="apc-panel apc-audit-panel"></div>
                        </aside>
                    </div>
                </div>
                <div class="apc-savebar" style="display:none" role="region" aria-label="${t("حفظ تغييرات الصلاحيات")}">
                    <div class="apc-savebar-inner">
                        <div class="apc-dirty" role="status" aria-live="polite" aria-atomic="true">${t("لا توجد تغييرات غير محفوظة")}</div>
                        <div class="apc-save-actions">
                            <button type="button" class="btn btn-default apc-reset">${t("تراجع")}</button>
                            <button type="button" class="btn btn-primary apc-save">${t("حفظ الصلاحيات")}</button>
                        </div>
                    </div>
                </div>
            `);
        }

        function renderActor(actor = {}) {
            const name = actor.full_name || actor.user || "";
            const user = actor.user || "";
            $main.find(".apc-actor").html(`
                <div class="apc-actor-icon" aria-hidden="true">●</div>
                <div class="apc-actor-copy">
                    <span class="apc-actor-label">${t("المستخدم الحالي")}</span>
                    <strong class="apc-actor-name">${esc(name)}</strong>
                    <span class="apc-actor-email">${esc(user)}</span>
                </div>
            `);
        }

        function renderRoleMenu(roles) {
            const $menu = $main.find(".apc-role-menu");
            if (!roles.length) {
                $menu.html(`<div class="apc-role-no-results">${t("لا يوجد دور مطابق للبحث.")}</div>`);
                return;
            }
            $menu.html(roles.map(role => (
                `<button type="button" class="apc-role-option ${role.selected ? "is-selected" : ""}" role="option" aria-selected="${role.selected ? "true" : "false"}" data-role="${esc(role.name)}"><span class="apc-role-option-name">${esc(role.name)}</span>${role.deskAccess ? "" : `<small>${t("بدون Desk")}</small>`}</button>`
            )).join(""));
        }

        function setRolePickerValue(value) {
            $main.find(".apc-role-picker").val(value || "");
        }

        function openRoleMenu() {
            $main.find(".apc-role-menu").prop("hidden", false);
            $main.find(".apc-role-picker").attr("aria-expanded", "true");
        }

        function closeRoleMenu(restoreSelection = false, selectedRole = "") {
            $main.find(".apc-role-menu").prop("hidden", true);
            $main.find(".apc-role-picker").attr("aria-expanded", "false");
            if (restoreSelection && selectedRole) setRolePickerValue(selectedRole);
        }

        function showRoleLoading(message) {
            $main.find(".apc-content,.apc-savebar").hide();
            $main.find(".apc-loading").show().text(message);
        }

        function showLoaded() {
            $main.find(".apc-loading").hide();
            $main.find(".apc-content,.apc-savebar").show();
        }

        function renderPermissionGroups(groups) {
            $main.find(".apc-groups").html(groups.map(group => `
                <section class="apc-group" data-group="${esc(group.key)}">
                    <div class="apc-group-head">
                        <div class="apc-group-copy">
                            <h4>${esc(group.label)}<span class="apc-group-count">${group.count}</span></h4>
                            <p>${esc(group.description)}</p>
                        </div>
                        <button type="button" class="btn btn-default apc-bulk-toggle apc-select-all-group" data-group="${esc(group.key)}">${t("تحديد الكل")}</button>
                    </div>
                    <div class="apc-group-body">${group.capabilities.map(renderCapability).join("")}</div>
                </section>
            `).join("") || `<div class="apc-empty">${t("لا توجد صلاحيات مسجلة.")}</div>`);
        }

        function renderCapability(capability) {
            const badges = capability.badges.map(badge => (
                `<span class="apc-badge ${esc(badge.kind)}">${esc(badge.label)}</span>`
            )).join("");
            return `
                <label class="apc-capability">
                    <span class="apc-switch">
                        <input type="checkbox" class="apc-capability-input" data-capability="${esc(capability.key)}" aria-label="${esc(capability.label)}" ${capability.checked ? "checked" : ""}>
                        <span class="apc-slider"></span>
                    </span>
                    <span class="apc-capability-copy">
                        <span class="apc-capability-title">${esc(capability.label)}</span>
                        <span class="apc-capability-description">${esc(capability.description)}</span>
                    </span>
                    <span class="apc-badges">${badges}</span>
                </label>
            `;
        }

        function syncCheckboxes(working) {
            $main.find(".apc-capability-input").each(function () {
                const key = String($(this).attr("data-capability") || "");
                $(this).prop("checked", working && working[key] === true);
            });
        }

        function syncBulkControls(model) {
            const groups = new Map((model.groups || []).map(group => [group.key, group.allEnabled]));
            $main.find(".apc-select-all-group").each(function () {
                const allEnabled = groups.get(String($(this).attr("data-group") || "")) === true;
                $(this)
                    .toggleClass("is-all", allEnabled)
                    .attr("aria-pressed", allEnabled ? "true" : "false")
                    .text(allEnabled ? t("إلغاء تحديد الكل") : t("تحديد الكل"));
            });
            const allEnabled = model.globalAllEnabled === true;
            $main.find(".apc-select-all-global")
                .toggleClass("is-all", allEnabled)
                .attr("aria-pressed", allEnabled ? "true" : "false")
                .text(allEnabled ? t("إلغاء تحديد الكل للكل") : t("تحديد الكل للكل"));
        }

        function renderImpact(model) {
            const warning = model.warning ? `<div class="apc-warning">${esc(model.warning)}</div>` : "";
            const source = model.source ? `<div class="apc-source">${esc(model.source)}</div>` : "";
            $main.find(".apc-impact-panel").html(`
                <div class="apc-panel-title-row">
                    <div>
                        <div class="apc-panel-kicker">${t("قبل الحفظ")}</div>
                        <div class="apc-panel-title">${t("أثر الصلاحيات")}</div>
                    </div>
                </div>
                ${warning}${source}
                <div class="apc-impact-section"><strong>${t("الواجهة الافتراضية")}</strong><div class="apc-impact-value">${esc(model.home)}</div></div>
                <div class="apc-impact-section"><strong>${t("مساحات العمل")}</strong><div class="apc-chip-row">${model.workspaces.map(item => `<span class="apc-chip">${esc(item)}</span>`).join("") || `<span class="apc-muted">${t("لا شيء")}</span>`}</div></div>
                <div class="apc-impact-section"><strong>${t("الأقسام الظاهرة")}</strong><div class="apc-chip-row">${model.sections.map(item => `<span class="apc-chip">${esc(item)}</span>`).join("") || `<span class="apc-muted">${t("لا شيء")}</span>`}</div></div>
                <div class="apc-impact-section apc-impact-changes"><strong>${t("التغييرات")}</strong><div>${model.changes.map(change => `<div class="apc-change"><span>${esc(change.label)}</span><span>${esc(change.action)}</span></div>`).join("") || `<div class="apc-muted">${t("لا توجد تغييرات.")}</div>`}</div></div>
            `);
        }

        function renderAudit(rows) {
            $main.find(".apc-audit-panel").html(`
                <div class="apc-panel-title-row">
                    <div>
                        <div class="apc-panel-kicker">${t("سجل النشاط")}</div>
                        <div class="apc-panel-title">${t("آخر التغييرات المحفوظة")}</div>
                    </div>
                </div>
                <div class="apc-audit-list">${rows.map(row => `<div class="apc-audit-item"><strong class="apc-audit-user">${esc(row.changedBy)}</strong><div class="apc-audit-time">${esc(row.changedOn)}</div><div class="apc-audit-change">${esc(row.changedCapabilities)}</div></div>`).join("") || `<div class="apc-muted">${t("لا يوجد سجل بعد.")}</div>`}</div>
            `);
        }

        function updateStats(stats) {
            $main.find(".apc-total-count").text(stats.total);
            $main.find(".apc-enabled-count").text(stats.enabled);
            $main.find(".apc-critical-count").text(stats.critical);
            $main.find(".apc-change-count").text(stats.changes);
        }

        function syncDirtyState(model) {
            $main.find(".apc-dirty")
                .toggleClass("is-dirty", model.dirty)
                .text(model.dirty ? t("لديك تغييرات غير محفوظة") : t("لا توجد تغييرات غير محفوظة"));
            $main.find(".apc-save").prop("disabled", !model.dirty || model.saving);
            $main.find(".apc-reset").prop("disabled", !model.dirty || model.saving);
            $main.find(".apc-capability-input,.apc-role-picker,.apc-role-toggle,.apc-bulk-toggle,.apc-export,.apc-import")
                .prop("disabled", model.saving);
            updateStats(model.stats);
        }

        function showEmpty(message) {
            $main.find(".apc-loading").show().text(message);
            $main.find(".apc-content,.apc-savebar").hide();
        }

        function downloadJson(filename, documentData) {
            const blob = new Blob([JSON.stringify(documentData || {}, null, 2)], { type: "application/json;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        }

        return Object.freeze({
            renderShell,
            renderActor,
            renderRoleMenu,
            setRolePickerValue,
            openRoleMenu,
            closeRoleMenu,
            showRoleLoading,
            showLoaded,
            renderPermissionGroups,
            syncCheckboxes,
            syncBulkControls,
            renderImpact,
            renderAudit,
            syncDirtyState,
            showEmpty,
            downloadJson,
        });
    }

    window.AlmdinaFactoryPermissionsRenderer = Object.freeze({ create });
})();
