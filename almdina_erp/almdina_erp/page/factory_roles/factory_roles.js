frappe.pages["factory-roles"].on_page_load = function (wrapper) {
    "use strict";

    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("إدارة الأدوار"),
        single_column: true,
    });

    new AlmdinaRoleConsole(page, wrapper);
};

class AlmdinaRoleConsole {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.$main = $(wrapper).find(".layout-main-section");
        this.state = {
            roles: [],
            summary: {},
            search: "",
            enabled: "all",
        };
        this.requestId = 0;
        this.searchTimer = null;
        this.busy = false;
        this.installStyles();
        this.buildPageActions();
        this.renderLoading();
        this.load();
    }

    can(capability) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && typeof permissions.can === "function"
            && permissions.can(capability)
        );
    }

    installStyles() {
        if (document.getElementById("almdina-role-console-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-role-console-style";
        style.textContent = `
            .arc-shell{direction:rtl;display:grid;gap:14px;padding-bottom:34px}
            .arc-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:20px;border:1px solid var(--border-color,#e5e7eb);border-radius:18px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f7f9fb))}
            .arc-hero h2{margin:0 0 7px;font-size:21px;font-weight:850}.arc-hero p{max-width:760px;margin:0;color:var(--text-muted,#667085);font-size:13px;line-height:1.9}.arc-flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:300px;justify-content:flex-end}.arc-step{display:inline-flex;align-items:center;min-height:30px;padding:5px 9px;border-radius:999px;background:var(--fg-color,#fff);border:1px solid var(--border-color,#e5e7eb);font-size:11px;font-weight:800}.arc-arrow{color:var(--text-muted,#98a2b3)}
            .arc-toolbar{position:sticky;top:58px;z-index:12;display:grid;grid-template-columns:minmax(240px,1fr) 180px auto;gap:10px;align-items:end;padding:13px;border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff);box-shadow:0 5px 18px rgba(0,0,0,.045)}
            .arc-field label{display:block;margin-bottom:6px;color:var(--text-muted,#667085);font-size:11px;font-weight:800}.arc-field input,.arc-field select{width:100%;min-height:42px;padding:8px 11px;border:1px solid var(--border-color,#d7dde3);border-radius:10px;background:var(--control-bg,#fff);color:var(--text-color,#1f2937);outline:none}.arc-field input:focus,.arc-field select:focus{border-color:var(--primary,#2490ef);box-shadow:0 0 0 2px rgba(36,144,239,.12)}.arc-refresh{min-height:42px;border-radius:10px;font-weight:750}
            .arc-summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px}.arc-stat{min-width:0;padding:13px;border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff)}.arc-stat span{display:block;min-height:30px;color:var(--text-muted,#667085);font-size:11px;font-weight:750;line-height:1.45}.arc-stat b{display:block;margin-top:3px;font-size:24px;line-height:1.2;overflow:hidden;text-overflow:ellipsis}
            .arc-table-wrap{overflow:auto;border:1px solid var(--border-color,#e5e7eb);border-radius:16px;background:var(--fg-color,#fff)}.arc-table{width:100%;min-width:1060px;border-collapse:separate;border-spacing:0}.arc-table th{position:sticky;top:0;z-index:2;padding:11px 12px;background:var(--subtle-fg,#f7f9fb);border-bottom:1px solid var(--border-color,#e5e7eb);color:var(--text-muted,#667085);font-size:11px;font-weight:850;text-align:right;white-space:nowrap}.arc-table td{padding:13px 12px;border-bottom:1px solid var(--border-color,#edf0f2);vertical-align:middle;font-size:12px}.arc-table tbody tr:last-child td{border-bottom:0}.arc-table tbody tr:hover{background:var(--subtle-fg,#fafbfc)}
            .arc-role-name{font-size:14px;font-weight:850;overflow-wrap:anywhere}.arc-description{max-width:300px;color:var(--text-muted,#667085);line-height:1.55}.arc-count{display:inline-flex;align-items:center;justify-content:center;min-width:32px;min-height:28px;padding:3px 8px;border-radius:9px;background:var(--subtle-fg,#f2f4f7);font-weight:800}.arc-count.has-value{background:#fff3d6;color:#8a5b00}
            .arc-badges{display:flex;flex-wrap:wrap;gap:5px}.arc-badge{display:inline-flex;align-items:center;min-height:26px;padding:3px 8px;border-radius:999px;font-size:10px;font-weight:850;background:var(--subtle-fg,#f2f4f7)}.arc-badge.enabled{background:#e8f7ee;color:#18794e}.arc-badge.disabled{background:#fdecec;color:#b42318}.arc-badge.custom{background:#edf5ff;color:#175cd3}.arc-badge.standard{background:#f2f4f7;color:#475467}
            .arc-actions{display:flex;flex-wrap:wrap;gap:6px;min-width:255px}.arc-actions .btn{min-height:34px;padding:6px 9px;border-radius:8px;font-size:11px;font-weight:750}.arc-actions .btn-danger{background:#fff5f4;color:#b42318;border-color:#f6c8c4}.arc-actions .btn-danger:hover{background:#fee4e2}.arc-read-only{display:inline-flex;align-items:center;min-height:32px;padding:5px 9px;border-radius:8px;background:var(--subtle-fg,#f2f4f7);color:var(--text-muted,#667085);font-size:11px;font-weight:750}
            .arc-mobile-list{display:none;gap:10px}.arc-card{padding:14px;border:1px solid var(--border-color,#e5e7eb);border-radius:15px;background:var(--fg-color,#fff)}.arc-card-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.arc-card-description{margin-top:7px;color:var(--text-muted,#667085);font-size:12px;line-height:1.65}.arc-card-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:12px;padding-top:10px;border-top:1px solid var(--border-color,#edf0f2)}.arc-card-metric{padding:8px;border-radius:9px;background:var(--subtle-fg,#f7f9fb)}.arc-card-metric span{display:block;color:var(--text-muted,#667085);font-size:10px;font-weight:750}.arc-card-metric b{display:block;margin-top:3px;font-size:14px}.arc-card .arc-actions{margin-top:12px;min-width:0}
            .arc-empty,.arc-loading{padding:44px 18px;text-align:center;border:1px dashed var(--border-color,#d7dde3);border-radius:16px;color:var(--text-muted,#667085);background:var(--subtle-fg,#fafafa)}.arc-error{padding:18px;border:1px solid #f3b7b2;border-radius:14px;background:#fff5f4;color:#9f2d20;line-height:1.7}
            .arc-usage-warning{margin-top:10px;padding:9px 10px;border-radius:10px;background:#fff8e7;color:#7a4b00;font-size:11px;line-height:1.6}.arc-audit{display:grid;gap:8px;max-height:450px;overflow:auto}.arc-audit-item{padding:11px;border:1px solid var(--border-color,#e5e7eb);border-radius:11px}.arc-audit-head{display:flex;justify-content:space-between;gap:10px;font-weight:850}.arc-audit-meta{margin-top:4px;color:var(--text-muted,#667085);font-size:11px}.arc-audit-summary{margin-top:7px;font-size:12px;line-height:1.6}
            @media(max-width:1180px){.arc-summary{grid-template-columns:repeat(3,minmax(0,1fr))}.arc-hero{display:block}.arc-flow{margin-top:13px;justify-content:flex-start}}
            @media(max-width:760px){.arc-toolbar{position:static;grid-template-columns:1fr}.arc-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.arc-table-wrap{display:none}.arc-mobile-list{display:grid}.arc-flow{min-width:0}.arc-hero{padding:16px}.arc-actions .btn{flex:1 1 calc(50% - 6px)}}
            @media(max-width:420px){.arc-summary{grid-template-columns:1fr 1fr}.arc-stat{padding:11px}.arc-card-grid{grid-template-columns:1fr 1fr}}
        `;
        document.head.appendChild(style);
    }

    buildPageActions() {
        if (this.can("create_roles")) {
            this.page.set_primary_action(__("إنشاء دور"), () => this.openCreateDialog(), "add");
        }
        if (this.can("manage_permissions")) {
            this.page.add_inner_button(
                __("إدارة الصلاحيات"),
                () => frappe.set_route("factory-permissions"),
                null,
                "lock"
            );
        }
        this.page.add_inner_button(__("تحديث"), () => this.load(), null, "refresh");
    }

    escape(value) {
        const text = value === null || value === undefined ? "" : String(value);
        return frappe.utils && frappe.utils.escape_html
            ? frappe.utils.escape_html(text)
            : $("<div>").text(text).html();
    }

    call(method, args = {}, freezeMessage = "") {
        return frappe.call({
            method: `almdina_erp.almdina_erp.services.role_management_service.${method}`,
            args,
            freeze: Boolean(freezeMessage),
            freeze_message: freezeMessage,
        }).then(response => response.message || {});
    }

    renderLoading() {
        this.$main.html(`<div class="arc-loading" dir="rtl">${__("جاري تحميل الأدوار واستخداماتها...")}</div>`);
    }

    renderError(error) {
        const message = error && error.message ? error.message : __("حدث خطأ غير متوقع.");
        this.$main.html(`
            <div class="arc-error" dir="rtl">
                <b>${__("تعذر فتح إدارة الأدوار")}</b>
                <div style="margin-top:6px">${this.escape(message)}</div>
            </div>
        `);
    }

    load() {
        const requestId = ++this.requestId;
        if (!this.state.roles.length) this.renderLoading();
        return this.call("get_role_console", {
            search: this.state.search,
            enabled: this.state.enabled,
            limit: 200,
        }).then(data => {
            if (requestId !== this.requestId) return;
            this.state.roles = Array.isArray(data.roles) ? data.roles : [];
            this.state.summary = data.summary || {};
            this.render();
        }).catch(error => {
            if (requestId !== this.requestId) return;
            this.renderError(error);
        });
    }

    render() {
        this.$main.html(`
            <div class="arc-shell">
                ${this.heroHtml()}
                ${this.toolbarHtml()}
                ${this.summaryHtml()}
                ${this.rolesHtml()}
            </div>
        `);
        this.bindToolbar();
        this.bindRoleActions();
    }

    heroHtml() {
        return `
            <section class="arc-hero">
                <div>
                    <h2>${__("أدوار ديناميكية من الصفر")}</h2>
                    <p>${__("أنشئ دورًا فارغًا، ثم امنحه الصلاحيات التي يحتاجها فقط، وبعد ذلك أسنده إلى مستخدم أو أكثر. إنشاء الدور هنا لا يمنحه أي صلاحية تلقائية.")}</p>
                </div>
                <div class="arc-flow" aria-label="${__("تسلسل الإعداد")}">
                    <span class="arc-step">1. ${__("إنشاء دور")}</span><span class="arc-arrow">←</span>
                    <span class="arc-step">2. ${__("منح الصلاحيات")}</span><span class="arc-arrow">←</span>
                    <span class="arc-step">3. ${__("إسناده للمستخدم")}</span>
                </div>
            </section>
        `;
    }

    toolbarHtml() {
        return `
            <section class="arc-toolbar">
                <div class="arc-field">
                    <label>${__("البحث في الأدوار")}</label>
                    <input class="arc-search" type="search" value="${this.escape(this.state.search)}" placeholder="${__("اكتب اسم الدور...")}">
                </div>
                <div class="arc-field">
                    <label>${__("حالة الدور")}</label>
                    <select class="arc-enabled-filter">
                        <option value="all" ${this.state.enabled === "all" ? "selected" : ""}>${__("الكل")}</option>
                        <option value="1" ${this.state.enabled === "1" ? "selected" : ""}>${__("مفعّل")}</option>
                        <option value="0" ${this.state.enabled === "0" ? "selected" : ""}>${__("معطّل")}</option>
                    </select>
                </div>
                <button type="button" class="btn btn-default arc-refresh">${__("تحديث القائمة")}</button>
            </section>
        `;
    }

    summaryHtml() {
        const summary = this.state.summary || {};
        const cards = [
            [__("إجمالي الأدوار"), summary.total || 0],
            [__("الأدوار المفعلة"), summary.enabled || 0],
            [__("الأدوار المعطلة"), summary.disabled || 0],
            [__("إسنادات المستخدمين"), summary.assigned_users || 0],
            [__("صفوف الصلاحيات"), summary.permission_rows || 0],
            [__("مراجع الإنتاج"), summary.production_references || 0],
        ];
        return `<section class="arc-summary">${cards.map(card => `
            <div class="arc-stat"><span>${card[0]}</span><b>${this.escape(card[1])}</b></div>
        `).join("")}</section>`;
    }

    rolesHtml() {
        if (!this.state.roles.length) {
            return `<div class="arc-empty">${__("لا توجد أدوار مطابقة للبحث الحالي.")}</div>`;
        }
        return `
            <div class="arc-table-wrap">${this.desktopTableHtml()}</div>
            <div class="arc-mobile-list">${this.state.roles.map(role => this.mobileCardHtml(role)).join("")}</div>
        `;
    }

    desktopTableHtml() {
        return `
            <table class="arc-table">
                <thead><tr>
                    <th>${__("الدور")}</th>
                    <th>${__("الحالة")}</th>
                    <th>${__("المستخدمون")}</th>
                    <th>${__("الصلاحيات")}</th>
                    <th>${__("مسارات الإنتاج")}</th>
                    <th>${__("المراحل")}</th>
                    <th>${__("الإجراءات")}</th>
                </tr></thead>
                <tbody>${this.state.roles.map(role => this.tableRowHtml(role)).join("")}</tbody>
            </table>
        `;
    }

    statusBadges(role) {
        return `
            <div class="arc-badges">
                <span class="arc-badge ${role.enabled ? "enabled" : "disabled"}">${role.enabled ? __("مفعّل") : __("معطّل")}</span>
                <span class="arc-badge ${role.is_custom ? "custom" : "standard"}">${role.is_custom ? __("دور مخصص") : __("دور نظامي")}</span>
            </div>
        `;
    }

    countHtml(value) {
        const total = Number(value || 0);
        return `<span class="arc-count ${total ? "has-value" : ""}">${this.escape(total)}</span>`;
    }

    tableRowHtml(role) {
        return `
            <tr data-role-row="${this.escape(role.name)}">
                <td><div class="arc-role-name">${this.escape(role.name)}</div><div class="arc-description">${this.escape(role.description || __("بدون وصف"))}</div></td>
                <td>${this.statusBadges(role)}</td>
                <td>${this.countHtml(role.assigned_users)}</td>
                <td>${this.countHtml(role.permission_count)}</td>
                <td>${this.countHtml(role.production_routing_references)}</td>
                <td>${this.countHtml(role.production_stage_references)}</td>
                <td>${this.actionsHtml(role)}</td>
            </tr>
        `;
    }

    mobileCardHtml(role) {
        const blocker = this.blockerText(role);
        return `
            <article class="arc-card" data-role-card="${this.escape(role.name)}">
                <div class="arc-card-head">
                    <div class="arc-role-name">${this.escape(role.name)}</div>
                    ${this.statusBadges(role)}
                </div>
                <div class="arc-card-description">${this.escape(role.description || __("بدون وصف"))}</div>
                <div class="arc-card-grid">
                    <div class="arc-card-metric"><span>${__("المستخدمون")}</span><b>${this.escape(role.assigned_users || 0)}</b></div>
                    <div class="arc-card-metric"><span>${__("الصلاحيات")}</span><b>${this.escape(role.permission_count || 0)}</b></div>
                    <div class="arc-card-metric"><span>${__("مسارات الإنتاج")}</span><b>${this.escape(role.production_routing_references || 0)}</b></div>
                    <div class="arc-card-metric"><span>${__("المراحل النشطة")}</span><b>${this.escape(role.active_stage_references || 0)}</b></div>
                </div>
                ${blocker ? `<div class="arc-usage-warning">${this.escape(blocker)}</div>` : ""}
                ${this.actionsHtml(role)}
            </article>
        `;
    }

    actionAllowed(role, action) {
        return Boolean(role && role.actions && role.actions[action] && role.actions[action].allowed === true);
    }

    blockerText(role) {
        const blockers = [];
        if (Number(role.assigned_users || 0)) blockers.push(__("مرتبط بمستخدمين"));
        if (Number(role.permission_count || 0)) blockers.push(__("يمتلك صلاحيات"));
        if (Number(role.production_routing_references || 0)) blockers.push(__("مستخدم في مسارات إنتاج"));
        if (Number(role.workflow_references || 0)) blockers.push(__("مستخدم في Workflow"));
        if (Number(role.production_stage_references || 0)) blockers.push(__("مستخدم في مراحل إنتاج محفوظة"));
        return blockers.length ? `${__("لا يمكن حذف الدور حاليًا لأنه")}: ${blockers.join("، ")}.` : "";
    }

    actionsHtml(role) {
        const buttons = [];
        if (this.can("manage_permissions")) {
            buttons.push(`<button type="button" class="btn btn-default arc-permissions" data-role="${this.escape(role.name)}">${__("الصلاحيات")}</button>`);
        }
        if (this.can("edit_roles") && this.actionAllowed(role, "edit")) {
            buttons.push(`<button type="button" class="btn btn-default arc-edit" data-role="${this.escape(role.name)}">${__("تعديل")}</button>`);
        }
        if (this.can("edit_roles") && this.actionAllowed(role, "disable")) {
            buttons.push(`<button type="button" class="btn btn-default arc-toggle" data-enabled="0" data-role="${this.escape(role.name)}">${__("تعطيل")}</button>`);
        }
        if (this.can("edit_roles") && this.actionAllowed(role, "enable")) {
            buttons.push(`<button type="button" class="btn btn-primary arc-toggle" data-enabled="1" data-role="${this.escape(role.name)}">${__("تفعيل")}</button>`);
        }
        if (this.can("delete_roles") && this.actionAllowed(role, "delete")) {
            buttons.push(`<button type="button" class="btn btn-danger arc-delete" data-role="${this.escape(role.name)}">${__("حذف")}</button>`);
        }
        if (this.can("view_roles") && role.role_uid) {
            buttons.push(`<button type="button" class="btn btn-default arc-audit-open" data-role="${this.escape(role.name)}">${__("السجل")}</button>`);
        }
        return buttons.length
            ? `<div class="arc-actions">${buttons.join("")}</div>`
            : `<span class="arc-read-only">${__("عرض فقط")}</span>`;
    }

    bindToolbar() {
        this.$main.find(".arc-search").on("input", event => {
            clearTimeout(this.searchTimer);
            this.searchTimer = setTimeout(() => {
                this.state.search = String(event.target.value || "").trim();
                this.load();
            }, 320);
        });
        this.$main.find(".arc-enabled-filter").on("change", event => {
            this.state.enabled = String(event.target.value || "all");
            this.load();
        });
        this.$main.find(".arc-refresh").on("click", () => this.load());
    }

    findRole(name) {
        return this.state.roles.find(role => role.name === name) || null;
    }

    bindRoleActions() {
        this.$main.find(".arc-edit").on("click", event => this.openEditDialog(this.findRole(event.currentTarget.dataset.role)));
        this.$main.find(".arc-toggle").on("click", event => this.toggleRole(
            this.findRole(event.currentTarget.dataset.role),
            event.currentTarget.dataset.enabled === "1"
        ));
        this.$main.find(".arc-delete").on("click", event => this.openDeleteDialog(this.findRole(event.currentTarget.dataset.role)));
        this.$main.find(".arc-audit-open").on("click", event => this.openAudit(this.findRole(event.currentTarget.dataset.role)));
        this.$main.find(".arc-permissions").on("click", event => this.openPermissions(this.findRole(event.currentTarget.dataset.role)));
    }

    openCreateDialog() {
        if (!this.can("create_roles") || this.busy) return;
        const dialog = new frappe.ui.Dialog({
            title: __("إنشاء دور جديد"),
            fields: [
                { fieldname: "name", fieldtype: "Data", label: __("اسم الدور"), reqd: 1, description: __("مثال: عامل ليزر أو مسؤول اعتماد الطلبات") },
                { fieldname: "description", fieldtype: "Small Text", label: __("وصف الدور"), description: __("اكتب مسؤولية الدور بوضوح. لن يمنح الوصف أي صلاحية.") },
                { fieldname: "notice", fieldtype: "HTML", options: `<div class="alert alert-info">${__("سيُنشأ الدور بلا أي صلاحيات. بعد الإنشاء انتقل إلى إدارة الصلاحيات وحدد ما يحتاجه يدويًا.")}</div>` },
            ],
            primary_action_label: __("إنشاء الدور"),
            primary_action: values => {
                dialog.disable_primary_action();
                this.busy = true;
                this.call("create_factory_role", { data: JSON.stringify(values) }, __("جاري إنشاء الدور الفارغ...")).then(result => {
                    dialog.hide();
                    frappe.show_alert({ message: __("تم إنشاء الدور بلا صلاحيات."), indicator: "green" }, 6);
                    return this.load().then(() => this.offerPermissionSetup(result.role));
                }).catch(error => {
                    dialog.enable_primary_action();
                    this.showErrorDialog(__("تعذر إنشاء الدور"), error);
                }).finally(() => { this.busy = false; });
            },
        });
        dialog.show();
    }

    offerPermissionSetup(role) {
        if (!role || !this.can("manage_permissions")) return;
        frappe.confirm(
            __("تم إنشاء الدور {0}. هل تريد الانتقال الآن لتحديد صلاحياته يدويًا؟", [this.escape(role.name)]),
            () => this.openPermissions(role),
        );
    }

    openEditDialog(role) {
        if (!this.can("edit_roles") || !role || !this.actionAllowed(role, "edit") || this.busy) return;
        const dialog = new frappe.ui.Dialog({
            title: __("تعديل الدور"),
            fields: [
                { fieldname: "name", fieldtype: "Data", label: __("اسم الدور"), reqd: 1, default: role.name },
                { fieldname: "description", fieldtype: "Small Text", label: __("وصف الدور"), default: role.description || "" },
                { fieldname: "usage", fieldtype: "HTML", options: this.usageHtml(role) },
            ],
            primary_action_label: __("حفظ التعديلات"),
            primary_action: values => {
                dialog.disable_primary_action();
                this.busy = true;
                this.call("update_factory_role", {
                    role: role.name,
                    data: JSON.stringify(values),
                }, __("جاري تحديث الدور ومراجعه...")).then(() => {
                    dialog.hide();
                    frappe.show_alert({ message: __("تم تحديث الدور."), indicator: "green" });
                    return this.load();
                }).catch(error => {
                    dialog.enable_primary_action();
                    this.showErrorDialog(__("تعذر تعديل الدور"), error);
                }).finally(() => { this.busy = false; });
            },
        });
        dialog.show();
    }

    usageHtml(role) {
        return `
            <div class="alert alert-light" style="line-height:1.8">
                <b>${__("الاستخدام الحالي")}</b><br>
                ${__("المستخدمون")}: ${this.escape(role.assigned_users || 0)} ·
                ${__("الصلاحيات")}: ${this.escape(role.permission_count || 0)} ·
                ${__("مسارات الإنتاج")}: ${this.escape(role.production_routing_references || 0)} ·
                ${__("المراحل")}: ${this.escape(role.production_stage_references || 0)}
            </div>
        `;
    }

    toggleRole(role, enabled) {
        if (!this.can("edit_roles") || !role || !this.actionAllowed(role, enabled ? "enable" : "disable") || this.busy) return;
        const actionLabel = enabled ? __("تفعيل") : __("تعطيل");
        const message = enabled
            ? __("هل تريد تفعيل الدور {0}؟", [this.escape(role.name)])
            : __("هل تريد تعطيل الدور {0}؟ لا يُسمح بالتعطيل أثناء ارتباطه بمستخدمين أو مسارات نشطة.", [this.escape(role.name)]);
        frappe.confirm(message, () => {
            this.busy = true;
            this.call("set_factory_role_enabled", {
                role: role.name,
                enabled: enabled ? 1 : 0,
            }, __("جاري تحديث حالة الدور...")).then(() => {
                frappe.show_alert({ message: `${actionLabel} ${__("الدور بنجاح")}.`, indicator: "green" });
                return this.load();
            }).catch(error => this.showErrorDialog(__("تعذر تحديث حالة الدور"), error))
                .finally(() => { this.busy = false; });
        });
    }

    openDeleteDialog(role) {
        if (!this.can("delete_roles") || !role || !this.actionAllowed(role, "delete") || this.busy) return;
        const dialog = new frappe.ui.Dialog({
            title: __("حذف الدور نهائيًا"),
            fields: [
                { fieldname: "warning", fieldtype: "HTML", options: `<div class="alert alert-danger"><b>${__("تنبيه")}</b><br>${__("سيتم حذف الدور الفارغ فقط. لا يمكن التراجع عن هذه العملية من الواجهة.")}</div>` },
                { fieldname: "confirmation", fieldtype: "Data", label: __("اكتب اسم الدور للتأكيد"), reqd: 1, description: `<span dir="ltr">${this.escape(role.name)}</span>` },
            ],
            primary_action_label: __("حذف الدور"),
            primary_action: values => {
                if (String(values.confirmation || "").trim() !== role.name) {
                    frappe.msgprint({ title: __("اسم غير مطابق"), message: __("اكتب اسم الدور كما هو تمامًا لتأكيد الحذف."), indicator: "orange" });
                    return;
                }
                dialog.disable_primary_action();
                this.busy = true;
                this.call("delete_factory_role", {
                    role: role.name,
                    confirm_delete: 1,
                }, __("جاري التحقق من المراجع وحذف الدور...")).then(() => {
                    dialog.hide();
                    frappe.show_alert({ message: __("تم حذف الدور الفارغ."), indicator: "green" });
                    return this.load();
                }).catch(error => {
                    dialog.enable_primary_action();
                    this.showErrorDialog(__("تعذر حذف الدور"), error);
                }).finally(() => { this.busy = false; });
            },
        });
        dialog.show();
    }

    openAudit(role) {
        if (!this.can("view_roles") || !role || !role.role_uid) return;
        this.call("get_factory_role_audit", { role: role.name, limit: 50 }, __("جاري تحميل سجل الدور...")).then(data => {
            const events = Array.isArray(data.events) ? data.events : [];
            const html = events.length
                ? events.map(event => `
                    <div class="arc-audit-item">
                        <div class="arc-audit-head"><span>${this.escape(this.auditActionLabel(event.action))}</span><span>${this.escape(event.changed_on || "")}</span></div>
                        <div class="arc-audit-meta">${__("بواسطة")}: ${this.escape(event.changed_by || "—")}${event.changed_fields ? ` · ${__("الحقول")}: ${this.escape(event.changed_fields)}` : ""}</div>
                        <div class="arc-audit-summary">${this.escape(event.summary || "")}</div>
                    </div>
                `).join("")
                : `<div class="arc-empty">${__("لا توجد تغييرات مسجلة لهذا الدور.")}</div>`;
            const dialog = new frappe.ui.Dialog({
                title: __("سجل تغييرات الدور {0}", [role.name]),
                size: "large",
                fields: [{ fieldname: "audit", fieldtype: "HTML", options: `<div class="arc-audit" dir="rtl">${html}</div>` }],
            });
            dialog.show();
        }).catch(error => this.showErrorDialog(__("تعذر تحميل سجل الدور"), error));
    }

    auditActionLabel(action) {
        const labels = {
            Created: __("إنشاء"),
            Updated: __("تعديل"),
            Enabled: __("تفعيل"),
            Disabled: __("تعطيل"),
            Deleted: __("حذف"),
        };
        return labels[action] || action || __("تغيير");
    }

    openPermissions(role) {
        if (!this.can("manage_permissions")) return;
        if (role && role.name) {
            try {
                window.sessionStorage.setItem("almdina.permission-role", role.name);
            } catch (error) {
                // Session storage is optional; permission console remains usable.
            }
        }
        frappe.set_route("factory-permissions");
    }

    showErrorDialog(title, error) {
        frappe.msgprint({
            title,
            message: this.escape(error && error.message ? error.message : __("حدث خطأ غير متوقع.")),
            indicator: "red",
        });
    }
}
