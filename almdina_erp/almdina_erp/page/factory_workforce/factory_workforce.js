frappe.pages["factory-workforce"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("المستخدمون والقوى العاملة"),
        single_column: true,
    });
    new AlmdinaWorkforceConsole(page, wrapper);
};

class AlmdinaWorkforceConsole {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.$main = $(wrapper).find(".layout-main-section");
        this.state = {
            users: [],
            availableUsers: [],
            roles: [],
            permissions: {},
            summary: {},
            search: "",
            enabled: "all",
        };
        this.requestId = 0;
        this.searchTimer = null;
        this.installStyles();
        this.buildToolbar();
        this.load();
    }

    installStyles() {
        if (document.getElementById("almdina-workforce-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-workforce-style";
        style.textContent = `
            .aw-shell{direction:rtl;display:grid;gap:18px;padding-bottom:30px}.aw-toolbar{display:grid;grid-template-columns:minmax(220px,1fr) 180px auto;gap:10px;align-items:end;padding:14px;background:var(--fg-color,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:14px;position:sticky;top:58px;z-index:12;box-shadow:0 4px 16px rgba(0,0,0,.04)}.aw-field label{display:block;font-weight:700;font-size:12px;color:var(--text-muted,#6b7280);margin-bottom:6px}.aw-field input,.aw-field select{width:100%;min-height:42px;border:1px solid var(--border-color,#dfe3e8);border-radius:10px;padding:8px 12px;background:var(--control-bg,#fff)}.aw-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.aw-stat{background:var(--fg-color,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:14px;padding:14px}.aw-stat span{display:block;color:var(--text-muted,#6b7280);font-size:12px;font-weight:700}.aw-stat b{display:block;font-size:25px;margin-top:5px}.aw-section{display:grid;gap:12px}.aw-section-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;padding:2px 2px 0}.aw-section-title{margin:0;font-size:18px;font-weight:800}.aw-section-copy{margin:5px 0 0;color:var(--text-muted,#6b7280);font-size:13px;line-height:1.7}.aw-section-count{display:inline-flex;align-items:center;justify-content:center;min-width:34px;min-height:30px;padding:4px 10px;border-radius:999px;background:var(--subtle-fg,#f4f5f6);font-size:12px;font-weight:800}.aw-list{display:grid;gap:12px}.aw-card{background:var(--fg-color,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:16px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,.035)}.aw-card.is-available{border-style:dashed;background:linear-gradient(180deg,var(--fg-color,#fff),var(--subtle-fg,#fafafa))}.aw-card-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.aw-name{font-size:17px;font-weight:800;margin:0}.aw-email{direction:ltr;text-align:right;color:var(--text-muted,#6b7280);font-size:13px;margin-top:3px}.aw-badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.aw-badge{display:inline-flex;align-items:center;min-height:28px;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:700;background:var(--subtle-fg,#f4f5f6)}.aw-badge.is-enabled{background:#e8f7ee;color:#18794e}.aw-badge.is-disabled{background:#fdecec;color:#b42318}.aw-badge.is-warning{background:#fff4d6;color:#8a5b00}.aw-badge.is-neutral{background:#f2f4f7;color:#475467}.aw-role{background:#eef5ff;color:#285b9a}.aw-details{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid var(--border-color,#edf0f2)}.aw-detail span{display:block;color:var(--text-muted,#6b7280);font-size:11px;font-weight:700}.aw-detail b{display:block;margin-top:4px;font-size:13px;overflow-wrap:anywhere}.aw-scope-note{margin-top:12px;padding:10px 12px;border-radius:10px;background:var(--subtle-fg,#f7f7f8);color:var(--text-muted,#667085);font-size:12px;line-height:1.65}.aw-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.aw-actions .btn{min-height:38px;border-radius:9px;font-weight:700}.aw-empty{padding:42px 18px;text-align:center;border:1px dashed var(--border-color,#d7dde3);border-radius:16px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}.aw-loading{padding:46px;text-align:center;color:var(--text-muted,#6b7280)}.aw-error{padding:22px;border:1px solid #f5b7b1;background:#fff5f4;color:#9f2d20;border-radius:14px}.aw-audit{display:grid;gap:8px;max-height:430px;overflow:auto}.aw-audit-item{border:1px solid var(--border-color,#e5e7eb);border-radius:12px;padding:11px}.aw-audit-title{display:flex;justify-content:space-between;gap:10px;font-weight:800}.aw-audit-meta{font-size:12px;color:var(--text-muted,#6b7280);margin-top:5px}.aw-audit-summary{margin-top:7px;font-size:13px}@media(max-width:900px){.aw-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.aw-details{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.aw-toolbar{position:static;grid-template-columns:1fr}.aw-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.aw-section-head{display:block}.aw-section-count{margin-top:8px}.aw-card-head{display:block}.aw-details{grid-template-columns:1fr 1fr}.aw-actions .btn{flex:1 1 calc(50% - 8px)}}
        `;
        document.head.appendChild(style);
    }

    buildToolbar() {
        this.page.set_primary_action(__("إنشاء مستخدم جديد"), () => this.openCreateDialog(), "add");
        this.page.add_inner_button(__("تحديث"), () => this.load(), null, "refresh");
        this.renderLoading();
    }

    escape(value) {
        const text = value === null || value === undefined ? "" : String(value);
        return frappe.utils && frappe.utils.escape_html ? frappe.utils.escape_html(text) : $("<div>").text(text).html();
    }

    can(capability) { return this.state.permissions[capability] === true; }

    actionAllowed(user, action) {
        return Boolean(user && user.actions && user.actions[action] && user.actions[action].allowed === true);
    }

    call(method, args = {}, freezeMessage = "") {
        return frappe.call({ method: `almdina_erp.almdina_erp.services.workforce_service.${method}`, args, freeze: Boolean(freezeMessage), freeze_message: freezeMessage }).then(response => response.message || {});
    }

    renderLoading() { this.$main.html(`<div class="aw-loading">${__("جاري تحميل مستخدمي المعمل...")}</div>`); }
    renderError(message) { this.$main.html(`<div class="aw-error" dir="rtl"><b>${__("تعذر تحميل إدارة المستخدمين")}</b><div style="margin-top:6px">${this.escape(message || __("حدث خطأ غير متوقع."))}</div></div>`); }

    load() {
        const requestId = ++this.requestId;
        if (!this.state.users.length && !this.state.availableUsers.length) this.renderLoading();
        return this.call("get_workforce_console", { search: this.state.search, enabled: this.state.enabled, limit: 150 }).then(data => {
            if (requestId !== this.requestId) return;
            this.state.users = Array.isArray(data.users) ? data.users : [];
            this.state.availableUsers = Array.isArray(data.available_users) ? data.available_users : [];
            this.state.roles = Array.isArray(data.roles) ? data.roles : [];
            this.state.permissions = data.permissions || {};
            this.state.summary = data.summary || {};
            this.page.btn_primary && this.page.btn_primary.toggle(this.can("create_users"));
            this.render();
        }).catch(error => {
            if (requestId !== this.requestId) return;
            this.renderError(error && error.message ? error.message : __("تعذر تحميل البيانات."));
        });
    }

    render() {
        this.$main.html(`<div class="aw-shell">${this.toolbarHtml()}${this.summaryHtml()}${this.workforceSectionHtml()}${this.availableUsersSectionHtml()}</div>`);
        this.bindToolbar();
        this.bindUserActions();
    }

    toolbarHtml() {
        return `<div class="aw-toolbar"><div class="aw-field"><label>${__("بحث بالاسم أو البريد")}</label><input class="aw-search" type="search" value="${this.escape(this.state.search)}" placeholder="${__("اكتب للبحث...")}"></div><div class="aw-field"><label>${__("حالة الحساب")}</label><select class="aw-enabled-filter"><option value="all" ${this.state.enabled === "all" ? "selected" : ""}>${__("الكل")}</option><option value="1" ${this.state.enabled === "1" ? "selected" : ""}>${__("مفعّل")}</option><option value="0" ${this.state.enabled === "0" ? "selected" : ""}>${__("معطّل")}</option></select></div><button type="button" class="btn btn-default aw-refresh">${__("تحديث القائمة")}</button></div>`;
    }

    summaryHtml() {
        const summary = this.state.summary || {};
        const cards = [[__("إجمالي حسابات المعمل"), summary.total || 0], [__("الحسابات المفعلة"), summary.enabled || 0], [__("الحسابات المعطلة"), summary.disabled || 0], [__("المراحل النشطة المسندة"), summary.active_assignments || 0]];
        return `<div class="aw-summary">${cards.map(item => `<div class="aw-stat"><span>${item[0]}</span><b>${this.escape(item[1])}</b></div>`).join("")}</div>`;
    }

    workforceSectionHtml() {
        return `<section class="aw-section"><div class="aw-section-head"><div><h2 class="aw-section-title">${__("مستخدمو المعمل")}</h2><p class="aw-section-copy">${__("الحسابات التي تم ضمها إلى Almdina ويمكن إدارة أدوارها وصلاحياتها من هنا.")}</p></div><span class="aw-section-count">${this.escape(this.state.users.length)}</span></div><div class="aw-list">${this.usersHtml()}</div></section>`;
    }

    availableUsersSectionHtml() {
        if (!this.can("create_users")) return "";
        return `<section class="aw-section"><div class="aw-section-head"><div><h2 class="aw-section-title">${__("مستخدمون غير مضافين إلى المعمل")}</h2><p class="aw-section-copy">${__("حسابات System User الموجودة في Frappe ولم تُضم بعد إلى نطاق Almdina.")}</p></div><span class="aw-section-count">${this.escape(this.state.availableUsers.length)}</span></div><div class="aw-list">${this.availableUsersHtml()}</div></section>`;
    }

    usersHtml() {
        if (!this.state.users.length) return `<div class="aw-empty">${__("لا يوجد مستخدمون في المعمل مطابقون للبحث الحالي.")}</div>`;
        return this.state.users.map(user => this.userCardHtml(user)).join("");
    }

    availableUsersHtml() {
        if (!this.state.availableUsers.length) return `<div class="aw-empty">${__("لا توجد حسابات System User خارج المعمل مطابقة للبحث الحالي.")}</div>`;
        return this.state.availableUsers.map(user => this.availableUserCardHtml(user)).join("");
    }

    userCardHtml(user) {
        const active = Number(user.active_assignments || 0);
        const roles = Array.isArray(user.roles) ? user.roles : [];
        const canEdit = this.actionAllowed(user, "edit") || this.actionAllowed(user, "assign_roles");
        const buttons = [];
        if (canEdit) buttons.push(`<button class="btn btn-default aw-edit" data-user="${this.escape(user.email)}">${__("تعديل")}</button>`);
        if (this.actionAllowed(user, "reset_password")) buttons.push(`<button class="btn btn-default aw-password" data-user="${this.escape(user.email)}">${__("كلمة مرور مؤقتة")}</button>`);
        if (this.actionAllowed(user, "disable")) buttons.push(`<button class="btn btn-danger aw-toggle" data-enabled="0" data-user="${this.escape(user.email)}">${__("تعطيل")}</button>`);
        if (this.actionAllowed(user, "enable")) buttons.push(`<button class="btn btn-primary aw-toggle" data-enabled="1" data-user="${this.escape(user.email)}">${__("تفعيل")}</button>`);
        buttons.push(`<button class="btn btn-default aw-audit-open" data-user="${this.escape(user.email)}">${__("سجل التغييرات")}</button>`);
        const roleBadges = roles.length ? roles.map(role => `<span class="aw-badge aw-role">${this.escape(role)}</span>`).join("") : `<span class="aw-badge">${__("بدون أدوار مخصصة")}</span>`;
        return `<article class="aw-card"><div class="aw-card-head"><div><h3 class="aw-name">${this.escape(user.full_name || user.email)}</h3><div class="aw-email">${this.escape(user.email)}</div><div class="aw-badges"><span class="aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}">${user.enabled ? __("مفعّل") : __("معطّل")}</span>${active ? `<span class="aw-badge is-warning">${__("مراحل نشطة")}: ${active}</span>` : ""}</div><div class="aw-badges">${roleBadges}</div></div></div><div class="aw-details"><div class="aw-detail"><span>${__("اللغة")}</span><b>${user.language === "en" ? "English" : "العربية"}</b></div><div class="aw-detail"><span>${__("مساحة العمل")}</span><b>${this.escape(user.default_workspace || "—")}</b></div><div class="aw-detail"><span>${__("آخر نشاط")}</span><b>${this.escape(user.last_active || "—")}</b></div></div>${active && this.can("disable_users") ? `<div class="text-muted" style="margin-top:10px;font-size:12px">${__("يجب إعادة إسناد المراحل النشطة قبل تعطيل المستخدم أو تغيير أدواره.")}</div>` : ""}<div class="aw-actions">${buttons.join("")}</div></article>`;
    }

    availableUserCardHtml(user) {
        const source = user.default_app ? user.default_app : __("بدون تطبيق افتراضي");
        return `<article class="aw-card is-available"><div class="aw-card-head"><div><h3 class="aw-name">${this.escape(user.full_name || user.email)}</h3><div class="aw-email">${this.escape(user.email)}</div><div class="aw-badges"><span class="aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}">${user.enabled ? __("مفعّل") : __("معطّل")}</span><span class="aw-badge is-neutral">${__("خارج المعمل")}</span></div></div></div><div class="aw-details"><div class="aw-detail"><span>${__("التطبيق الحالي")}</span><b>${this.escape(source)}</b></div><div class="aw-detail"><span>${__("مساحة العمل")}</span><b>${this.escape(user.default_workspace || "—")}</b></div><div class="aw-detail"><span>${__("آخر نشاط")}</span><b>${this.escape(user.last_active || "—")}</b></div></div><div class="aw-scope-note">${__("إضافته إلى المعمل لا تمنحه أي دور أو صلاحية تشغيلية تلقائيًا. بعد الإضافة يمكنك اختيار أدوار المعمل له بشكل صريح.")}</div><div class="aw-actions"><button class="btn btn-primary aw-adopt-user" data-user="${this.escape(user.email)}">${__("إضافة إلى المعمل")}</button></div></article>`;
    }

    bindToolbar() {
        this.$main.find(".aw-search").on("input", event => { clearTimeout(this.searchTimer); this.searchTimer = setTimeout(() => { this.state.search = String(event.target.value || "").trim(); this.load(); }, 350); });
        this.$main.find(".aw-enabled-filter").on("change", event => { this.state.enabled = String(event.target.value || "all"); this.load(); });
        this.$main.find(".aw-refresh").on("click", () => this.load());
    }

    findUser(email) { return this.state.users.find(user => user.email === email) || null; }
    findAvailableUser(email) { return this.state.availableUsers.find(user => user.email === email) || null; }

    bindUserActions() {
        this.$main.find(".aw-edit").on("click", event => this.openEditDialog(this.findUser(event.currentTarget.dataset.user)));
        this.$main.find(".aw-password").on("click", event => this.openPasswordDialog(this.findUser(event.currentTarget.dataset.user)));
        this.$main.find(".aw-toggle").on("click", event => this.toggleUser(this.findUser(event.currentTarget.dataset.user), event.currentTarget.dataset.enabled === "1"));
        this.$main.find(".aw-audit-open").on("click", event => this.openAudit(this.findUser(event.currentTarget.dataset.user)));
        this.$main.find(".aw-adopt-user").on("click", event => this.adoptUser(this.findAvailableUser(event.currentTarget.dataset.user)));
    }

    adoptUser(user) {
        if (!user || !this.can("create_users")) return;
        frappe.confirm(
            __("سيتم إضافة الحساب {0} إلى نطاق المعمل بدون منحه أي دور أو صلاحية تشغيلية تلقائيًا. هل تريد المتابعة؟", [user.email]),
            () => {
                this.call("adopt_workforce_user", { user: user.email }, __("جاري إضافة المستخدم إلى المعمل...")).then(() => {
                    frappe.show_alert({ message: __("تمت إضافة المستخدم إلى المعمل. يمكنك الآن تعيين أدواره."), indicator: "green" });
                    return this.load();
                });
            }
        );
    }

    roleField(defaultValue = [], readOnly = false) {
        return { fieldname: "roles", fieldtype: "MultiSelectList", label: __("الأدوار"), description: __("اختر دورًا واحدًا أو أكثر. الصلاحيات تأتي من مصفوفة كل دور."), default: defaultValue, read_only: readOnly ? 1 : 0, get_data: txt => { const query = String(txt || "").toLowerCase(); return this.state.roles.filter(role => String(role.name || "").toLowerCase().includes(query)).map(role => ({ value: role.name, description: role.desk_access ? __("وصول Desk") : __("دور بدون Desk") })); } };
    }

    openCreateDialog() {
        if (!this.can("create_users")) return;
        const canAssignRoles = this.can("assign_user_roles");
        const dialog = new frappe.ui.Dialog({
            title: __("إضافة مستخدم للمعمل"),
            fields: [
                { fieldname: "email", fieldtype: "Data", label: __("البريد الإلكتروني"), options: "Email", reqd: 1 },
                { fieldname: "first_name", fieldtype: "Data", label: __("الاسم"), reqd: 1 },
                { fieldname: "last_name", fieldtype: "Data", label: __("الكنية") },
                { fieldname: "language", fieldtype: "Select", label: __("اللغة"), options: ["ar", "en"], default: "ar", reqd: 1 },
                this.roleField([], !canAssignRoles),
                { fieldname: "temporary_password", fieldtype: "Password", label: __("كلمة مرور مؤقتة"), reqd: 1, description: __("10 محارف على الأقل وتحتوي حرفًا ورقمًا.") },
            ],
            primary_action_label: __("إنشاء المستخدم"),
            primary_action: values => {
                const payload = { ...values, roles: canAssignRoles ? (values.roles || []) : [] };
                this.call("create_workforce_user", { data: payload }, __("جاري إنشاء المستخدم...")).then(() => { dialog.hide(); frappe.show_alert({ message: __("تم إنشاء المستخدم."), indicator: "green" }); this.load(); });
            },
        });
        dialog.show();
    }

    openEditDialog(user) {
        if (!user) return;
        const canEdit = this.actionAllowed(user, "edit");
        const canAssignRoles = this.actionAllowed(user, "assign_roles");
        const fields = [];
        if (canEdit) fields.push({ fieldname: "first_name", fieldtype: "Data", label: __("الاسم"), reqd: 1, default: user.first_name || "" }, { fieldname: "last_name", fieldtype: "Data", label: __("الكنية"), default: user.last_name || "" }, { fieldname: "language", fieldtype: "Select", label: __("اللغة"), options: ["ar", "en"], default: user.language || "ar", reqd: 1 });
        if (canAssignRoles) fields.push(this.roleField(user.roles || [], false));
        if (!fields.length) return;
        const dialog = new frappe.ui.Dialog({
            title: __("تعديل المستخدم {0}", [user.email]), fields,
            primary_action_label: __("حفظ"),
            primary_action: values => {
                const payload = {};
                if (canEdit) { payload.first_name = values.first_name; payload.last_name = values.last_name; payload.language = values.language; }
                if (canAssignRoles) payload.roles = values.roles || [];
                this.call("update_workforce_user", { user: user.email, data: payload }, __("جاري حفظ المستخدم...")).then(() => { dialog.hide(); frappe.show_alert({ message: __("تم تحديث المستخدم."), indicator: "green" }); this.load(); });
            },
        });
        dialog.show();
    }

    openPasswordDialog(user) {
        if (!user || !this.actionAllowed(user, "reset_password")) return;
        const dialog = new frappe.ui.Dialog({ title: __("تعيين كلمة مرور مؤقتة"), fields: [{ fieldname: "temporary_password", fieldtype: "Password", label: __("كلمة المرور المؤقتة"), reqd: 1 }], primary_action_label: __("حفظ كلمة المرور"), primary_action: values => this.call("reset_workforce_password", { user: user.email, temporary_password: values.temporary_password }, __("جاري تحديث كلمة المرور...")).then(() => { dialog.hide(); frappe.show_alert({ message: __("تم تحديث كلمة المرور دون تسجيل قيمتها."), indicator: "green" }); }) });
        dialog.show();
    }

    toggleUser(user, enabled) {
        if (!user) return;
        const label = enabled ? __("تفعيل") : __("تعطيل");
        frappe.confirm(__("هل تريد {0} المستخدم {1}؟", [label, user.email]), () => { this.call("set_workforce_user_enabled", { user: user.email, enabled: enabled ? 1 : 0 }, __("جاري تحديث الحساب...")).then(() => { frappe.show_alert({ message: __("تم تحديث حالة المستخدم."), indicator: "green" }); this.load(); }); });
    }

    openAudit(user) {
        if (!user) return;
        this.call("get_workforce_user_audit", { user: user.email, limit: 30 }, __("جاري تحميل السجل...")).then(data => {
            const events = Array.isArray(data.events) ? data.events : [];
            const dialog = new frappe.ui.Dialog({ title: __("سجل تغييرات {0}", [user.email]), fields: [{ fieldname: "audit", fieldtype: "HTML" }], size: "large" });
            dialog.fields_dict.audit.$wrapper.html(`<div class="aw-audit" dir="rtl">${events.map(event => `<div class="aw-audit-item"><div class="aw-audit-title"><span>${this.escape(event.action || "")}</span><span>${this.escape(event.changed_on || "")}</span></div><div class="aw-audit-meta">${this.escape(event.changed_by || "")}${event.changed_fields ? ` · ${this.escape(event.changed_fields)}` : ""}</div><div class="aw-audit-summary">${this.escape(event.summary || "")}</div></div>`).join("") || `<div class="aw-empty">${__("لا توجد تغييرات مسجلة.")}</div>`}</div>`);
            dialog.show();
        });
    }
}
