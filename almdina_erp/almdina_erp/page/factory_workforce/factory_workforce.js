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
            .aw-shell{direction:rtl;display:grid;gap:16px;padding-bottom:30px}
            .aw-toolbar{display:grid;grid-template-columns:minmax(220px,1fr) 180px auto;gap:10px;align-items:end;padding:14px;background:var(--fg-color,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:14px;position:sticky;top:58px;z-index:12;box-shadow:0 4px 16px rgba(0,0,0,.04)}
            .aw-field label{display:block;font-weight:700;font-size:12px;color:var(--text-muted,#6b7280);margin-bottom:6px}.aw-field input,.aw-field select{width:100%;min-height:42px;border:1px solid var(--border-color,#dfe3e8);border-radius:10px;padding:8px 12px;background:var(--control-bg,#fff)}
            .aw-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.aw-stat{background:var(--fg-color,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:14px;padding:14px}.aw-stat span{display:block;color:var(--text-muted,#6b7280);font-size:12px;font-weight:700}.aw-stat b{display:block;font-size:25px;margin-top:5px}
            .aw-list{display:grid;gap:12px}.aw-card{background:var(--fg-color,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:16px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,.035)}.aw-card-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.aw-name{font-size:17px;font-weight:800;margin:0}.aw-email{direction:ltr;text-align:right;color:var(--text-muted,#6b7280);font-size:13px;margin-top:3px}.aw-badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.aw-badge{display:inline-flex;align-items:center;min-height:28px;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:700;background:var(--subtle-fg,#f4f5f6)}.aw-badge.is-enabled{background:#e8f7ee;color:#18794e}.aw-badge.is-disabled{background:#fdecec;color:#b42318}.aw-badge.is-warning{background:#fff4d6;color:#8a5b00}.aw-badge.is-role{background:#edf4ff;color:#245ea8}
            .aw-details{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid var(--border-color,#edf0f2)}.aw-detail span{display:block;color:var(--text-muted,#6b7280);font-size:11px;font-weight:700}.aw-detail b{display:block;margin-top:4px;font-size:13px;overflow-wrap:anywhere}.aw-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.aw-actions .btn{min-height:38px;border-radius:9px;font-weight:700}.aw-empty{padding:42px 18px;text-align:center;border:1px dashed var(--border-color,#d7dde3);border-radius:16px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}
            .aw-loading{padding:46px;text-align:center;color:var(--text-muted,#6b7280)}.aw-error{padding:22px;border:1px solid #f5b7b1;background:#fff5f4;color:#9f2d20;border-radius:14px}.aw-audit{display:grid;gap:8px;max-height:430px;overflow:auto}.aw-audit-item{border:1px solid var(--border-color,#e5e7eb);border-radius:12px;padding:11px}.aw-audit-title{display:flex;justify-content:space-between;gap:10px;font-weight:800}.aw-audit-meta{font-size:12px;color:var(--text-muted,#6b7280);margin-top:5px}.aw-audit-summary{margin-top:7px;font-size:13px}
            @media(max-width:900px){.aw-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.aw-details{grid-template-columns:repeat(2,minmax(0,1fr))}}
            @media(max-width:600px){.aw-toolbar{position:static;grid-template-columns:1fr}.aw-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.aw-card-head{display:block}.aw-details{grid-template-columns:1fr 1fr}.aw-actions .btn{flex:1 1 calc(50% - 8px)}}
        `;
        document.head.appendChild(style);
    }

    buildToolbar() {
        this.page.set_primary_action(__("إضافة مستخدم"), () => this.openCreateDialog(), "add");
        this.page.add_inner_button(__("تحديث"), () => this.load(), null, "refresh");
        this.renderLoading();
    }

    escape(value) {
        const text = value === null || value === undefined ? "" : String(value);
        return frappe.utils && frappe.utils.escape_html
            ? frappe.utils.escape_html(text)
            : $("<div>").text(text).html();
    }

    can(capability) {
        return this.state.permissions[capability] === true;
    }

    actionAllowed(user, action) {
        return Boolean(
            user &&
            user.actions &&
            user.actions[action] &&
            user.actions[action].allowed === true
        );
    }

    canAssignRoles(user) {
        return this.actionAllowed(user, "assign_roles");
    }

    roleOptions(txt = "") {
        const query = String(txt || "").trim().toLowerCase();
        return this.state.roles
            .filter(role => {
                if (!query) return true;
                return [role.name, role.label, role.description]
                    .some(value => String(value || "").toLowerCase().includes(query));
            })
            .map(role => ({
                value: role.name,
                description: role.description || role.label || role.name,
            }));
    }

    call(method, args = {}, freezeMessage = "") {
        return frappe.call({
            method: `almdina_erp.almdina_erp.services.workforce_service.${method}`,
            args,
            freeze: Boolean(freezeMessage),
            freeze_message: freezeMessage,
        }).then(response => response.message || {});
    }

    renderLoading() {
        this.$main.html(`<div class="aw-loading">${__("جاري تحميل مستخدمي المعمل...")}</div>`);
    }

    renderError(message) {
        this.$main.html(`
            <div class="aw-error" dir="rtl">
                <b>${__("تعذر تحميل إدارة المستخدمين")}</b>
                <div style="margin-top:6px">${this.escape(message || __("حدث خطأ غير متوقع."))}</div>
            </div>
        `);
    }

    load() {
        const requestId = ++this.requestId;
        if (!this.state.users.length) this.renderLoading();
        return this.call("get_workforce_console", {
            search: this.state.search,
            enabled: this.state.enabled,
            limit: 150,
        }).then(data => {
            if (requestId !== this.requestId) return;
            this.state.users = Array.isArray(data.users) ? data.users : [];
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
        this.$main.html(`
            <div class="aw-shell">
                ${this.toolbarHtml()}
                ${this.summaryHtml()}
                <div class="aw-list">${this.usersHtml()}</div>
            </div>
        `);
        this.bindToolbar();
        this.bindUserActions();
    }

    toolbarHtml() {
        return `
            <div class="aw-toolbar">
                <div class="aw-field">
                    <label>${__("بحث بالاسم أو البريد")}</label>
                    <input class="aw-search" type="search" value="${this.escape(this.state.search)}" placeholder="${__("اكتب للبحث...")}">
                </div>
                <div class="aw-field">
                    <label>${__("حالة الحساب")}</label>
                    <select class="aw-enabled-filter">
                        <option value="all" ${this.state.enabled === "all" ? "selected" : ""}>${__("الكل")}</option>
                        <option value="1" ${this.state.enabled === "1" ? "selected" : ""}>${__("مفعّل")}</option>
                        <option value="0" ${this.state.enabled === "0" ? "selected" : ""}>${__("معطّل")}</option>
                    </select>
                </div>
                <button type="button" class="btn btn-default aw-refresh">${__("تحديث القائمة")}</button>
            </div>
        `;
    }

    summaryHtml() {
        const summary = this.state.summary || {};
        const cards = [
            [__("إجمالي الحسابات"), summary.total || 0],
            [__("الحسابات المفعلة"), summary.enabled || 0],
            [__("الحسابات المعطلة"), summary.disabled || 0],
            [__("المراحل النشطة المسندة"), summary.active_assignments || 0],
        ];
        return `<div class="aw-summary">${cards.map(item => `
            <div class="aw-stat"><span>${item[0]}</span><b>${this.escape(item[1])}</b></div>
        `).join("")}</div>`;
    }

    usersHtml() {
        if (!this.state.users.length) {
            return `<div class="aw-empty">${__("لا يوجد مستخدمون مطابقون للبحث الحالي.")}</div>`;
        }
        return this.state.users.map(user => this.userCardHtml(user)).join("");
    }

    roleBadges(user) {
        const roles = Array.isArray(user.workforce_roles) ? user.workforce_roles : [];
        if (!roles.length) {
            return `<span class="aw-badge is-warning">${__("دون دور تشغيلي")}</span>`;
        }
        return roles.map(role => `<span class="aw-badge is-role">${this.escape(role)}</span>`).join("");
    }

    userCardHtml(user) {
        const active = Number(user.active_assignments || 0);
        const canEdit = this.actionAllowed(user, "edit") || this.canAssignRoles(user);
        const buttons = [];
        if (canEdit) buttons.push(`<button class="btn btn-default aw-edit" data-user="${this.escape(user.email)}">${__("تعديل")}</button>`);
        if (this.actionAllowed(user, "reset_password")) buttons.push(`<button class="btn btn-default aw-password" data-user="${this.escape(user.email)}">${__("كلمة مرور مؤقتة")}</button>`);
        if (this.actionAllowed(user, "disable")) buttons.push(`<button class="btn btn-danger aw-toggle" data-enabled="0" data-user="${this.escape(user.email)}">${__("تعطيل")}</button>`);
        if (this.actionAllowed(user, "enable")) buttons.push(`<button class="btn btn-primary aw-toggle" data-enabled="1" data-user="${this.escape(user.email)}">${__("تفعيل")}</button>`);
        buttons.push(`<button class="btn btn-default aw-audit-open" data-user="${this.escape(user.email)}">${__("سجل التغييرات")}</button>`);

        return `
            <article class="aw-card" data-user-card="${this.escape(user.email)}">
                <div class="aw-card-head">
                    <div>
                        <h3 class="aw-name">${this.escape(user.full_name || user.email)}</h3>
                        <div class="aw-email">${this.escape(user.email)}</div>
                        <div class="aw-badges">
                            <span class="aw-badge ${user.enabled ? "is-enabled" : "is-disabled"}">${user.enabled ? __("مفعّل") : __("معطّل")}</span>
                            ${this.roleBadges(user)}
                            ${active ? `<span class="aw-badge is-warning">${__("مراحل نشطة")}: ${active}</span>` : ""}
                        </div>
                    </div>
                </div>
                <div class="aw-details">
                    <div class="aw-detail"><span>${__("اللغة")}</span><b>${user.language === "en" ? "English" : "العربية"}</b></div>
                    <div class="aw-detail"><span>${__("مساحة العمل")}</span><b>${this.escape(user.default_workspace || "—")}</b></div>
                    <div class="aw-detail"><span>${__("آخر نشاط")}</span><b>${this.escape(user.last_active || "—")}</b></div>
                </div>
                ${active && this.can("disable_users") ? `<div class="text-muted" style="margin-top:10px;font-size:12px">${__("يجب إعادة إسناد المراحل النشطة قبل تغيير أدوار هذا المستخدم أو تعطيله.")}</div>` : ""}
                <div class="aw-actions">${buttons.join("")}</div>
            </article>
        `;
    }

    bindToolbar() {
        const $search = this.$main.find(".aw-search");
        $search.on("input", event => {
            clearTimeout(this.searchTimer);
            this.searchTimer = setTimeout(() => {
                this.state.search = String(event.target.value || "").trim();
                this.load();
            }, 350);
        });
        this.$main.find(".aw-enabled-filter").on("change", event => {
            this.state.enabled = String(event.target.value || "all");
            this.load();
        });
        this.$main.find(".aw-refresh").on("click", () => this.load());
    }

    findUser(email) {
        return this.state.users.find(user => user.email === email) || null;
    }

    bindUserActions() {
        this.$main.find(".aw-edit").on("click", event => this.openEditDialog(this.findUser(event.currentTarget.dataset.user)));
        this.$main.find(".aw-password").on("click", event => this.openPasswordDialog(this.findUser(event.currentTarget.dataset.user)));
        this.$main.find(".aw-toggle").on("click", event => this.toggleUser(
            this.findUser(event.currentTarget.dataset.user),
            event.currentTarget.dataset.enabled === "1"
        ));
        this.$main.find(".aw-audit-open").on("click", event => this.openAudit(this.findUser(event.currentTarget.dataset.user)));
    }

    rolesField({required = false} = {}) {
        return {
            fieldname:"roles",
            fieldtype:"MultiSelectList",
            label:__("الأدوار"),
            reqd:required ? 1 : 0,
            get_data:txt => this.roleOptions(txt),
            description:__("اختر دورًا واحدًا أو عدة أدوار. الأدوار التقنية الأخرى الموجودة على الحساب ستبقى محفوظة."),
        };
    }

    openCreateDialog() {
        if (!this.can("create_users")) return;
        const dialog = new frappe.ui.Dialog({
            title: __("إضافة مستخدم للمعمل"),
            fields: [
                {fieldname:"first_name",fieldtype:"Data",label:__("الاسم الأول"),reqd:1},
                {fieldname:"last_name",fieldtype:"Data",label:__("الاسم الأخير")},
                {fieldname:"email",fieldtype:"Data",label:__("البريد الإلكتروني"),options:"Email",reqd:1},
                this.rolesField({required:true}),
                {fieldname:"language",fieldtype:"Select",label:__("اللغة"),options:"ar\nen",default:"ar",reqd:1},
                {fieldname:"temporary_password",fieldtype:"Password",label:__("كلمة المرور المؤقتة"),description:__("10 محارف على الأقل، وتحتوي حرفًا ورقمًا."),reqd:1},
            ],
            primary_action_label: __("إنشاء الحساب"),
            primary_action: values => {
                dialog.get_primary_btn().prop("disabled", true);
                this.call("create_workforce_user", {data: values}, __("جاري إنشاء الحساب...")).then(() => {
                    dialog.hide();
                    frappe.show_alert({message:__("تم إنشاء مستخدم المعمل."),indicator:"green"});
                    this.load();
                }).finally(() => dialog.get_primary_btn().prop("disabled", false));
            },
        });
        dialog.show();
    }

    openEditDialog(user) {
        if (!user) return;
        const canIdentity = this.actionAllowed(user, "edit");
        const canRoles = this.canAssignRoles(user);
        const fields = [
            {fieldname:"email",fieldtype:"Data",label:__("البريد الإلكتروني"),default:user.email,read_only:1},
        ];
        if (canIdentity) {
            fields.push(
                {fieldname:"first_name",fieldtype:"Data",label:__("الاسم الأول"),default:user.first_name,reqd:1},
                {fieldname:"last_name",fieldtype:"Data",label:__("الاسم الأخير"),default:user.last_name},
                {fieldname:"language",fieldtype:"Select",label:__("اللغة"),options:"ar\nen",default:user.language || "ar",reqd:1}
            );
        }
        if (canRoles) fields.push(this.rolesField({required:true}));
        const dialog = new frappe.ui.Dialog({
            title: `${__("تعديل المستخدم")}: ${user.full_name || user.email}`,
            fields,
            primary_action_label: __("حفظ التعديلات"),
            primary_action: values => {
                const data = {};
                if (canIdentity) {
                    data.first_name = values.first_name;
                    data.last_name = values.last_name;
                    data.language = values.language;
                }
                if (canRoles) data.roles = values.roles;
                dialog.get_primary_btn().prop("disabled", true);
                this.call("update_workforce_user", {user:user.email,data}, __("جاري حفظ المستخدم...")).then(() => {
                    dialog.hide();
                    frappe.show_alert({message:__("تم حفظ بيانات المستخدم."),indicator:"green"});
                    this.load();
                }).finally(() => dialog.get_primary_btn().prop("disabled", false));
            },
        });
        dialog.show();
        if (canRoles) {
            dialog.set_value("roles", Array.isArray(user.workforce_roles) ? user.workforce_roles : []);
        }
    }

    openPasswordDialog(user) {
        if (!user || !this.actionAllowed(user, "reset_password")) return;
        frappe.prompt(
            [{
                fieldname:"temporary_password",
                fieldtype:"Password",
                label:__("كلمة المرور المؤقتة الجديدة"),
                description:__("لن تظهر كلمة المرور في سجل التغييرات."),
                reqd:1,
            }],
            values => this.call("reset_workforce_password", {
                user:user.email,
                temporary_password:values.temporary_password,
            }, __("جاري تحديث كلمة المرور...")).then(() => {
                frappe.show_alert({message:__("تم تعيين كلمة المرور المؤقتة."),indicator:"green"});
            }),
            __("إعادة كلمة المرور"),
            __("تعيين")
        );
    }

    toggleUser(user, enabled) {
        if (!user) return;
        const action = enabled ? "enable" : "disable";
        if (!this.actionAllowed(user, action)) return;
        const message = enabled
            ? __("هل تريد تفعيل هذا الحساب؟")
            : __("سيتم تعطيل الحساب ومنع استخدامه. هل تريد المتابعة؟");
        frappe.confirm(message, () => {
            this.call("set_workforce_user_enabled", {
                user:user.email,
                enabled:enabled ? 1 : 0,
            }, enabled ? __("جاري تفعيل الحساب...") : __("جاري تعطيل الحساب...")).then(() => {
                frappe.show_alert({message:enabled ? __("تم تفعيل الحساب.") : __("تم تعطيل الحساب."),indicator:"green"});
                this.load();
            });
        });
    }

    openAudit(user) {
        if (!user) return;
        const dialog = new frappe.ui.Dialog({
            title: `${__("سجل تغييرات المستخدم")}: ${user.full_name || user.email}`,
            size: "large",
            fields: [{fieldname:"audit_html",fieldtype:"HTML"}],
        });
        dialog.fields_dict.audit_html.$wrapper.html(`<div class="aw-loading">${__("جاري تحميل السجل...")}</div>`);
        dialog.show();
        this.call("get_workforce_user_audit", {user:user.email,limit:50}).then(data => {
            const events = Array.isArray(data.events) ? data.events : [];
            const html = events.length ? `<div class="aw-audit">${events.map(event => `
                <div class="aw-audit-item">
                    <div class="aw-audit-title"><span>${this.escape(event.action)}</span><span>${this.escape(event.changed_on)}</span></div>
                    <div class="aw-audit-meta">${__("بواسطة")}: ${this.escape(event.changed_by)}${event.changed_fields ? ` · ${__("الحقول")}: ${this.escape(event.changed_fields)}` : ""}</div>
                    <div class="aw-audit-summary">${this.escape(event.summary || "")}</div>
                </div>
            `).join("")}</div>` : `<div class="aw-empty">${__("لا توجد تغييرات مسجلة لهذا المستخدم.")}</div>`;
            dialog.fields_dict.audit_html.$wrapper.html(html);
        }).catch(error => {
            dialog.fields_dict.audit_html.$wrapper.html(`<div class="aw-error">${this.escape(error && error.message ? error.message : __("تعذر تحميل السجل."))}</div>`);
        });
    }
}
