(() => {
    "use strict";

    if (window.AlmdinaFactoryWorkforceDialogs) return;

    function create(options = {}) {
        const translate = options.translate;
        if (typeof translate !== "function") {
            throw new Error("Factory workforce dialog translator is unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);

        function roleField(defaultValue = [], readOnly = false, roleOptions = () => []) {
            return {
                fieldname: "roles",
                fieldtype: "MultiSelectList",
                label: t("الأدوار"),
                description: t("اختر الأدوار والصلاحيات المطلوبة. صفحة الدخول تأتي من Home Page في Role داخل Frappe ولا يحددها نظام Almdina."),
                default: defaultValue,
                read_only: readOnly ? 1 : 0,
                get_data: txt => roleOptions(txt),
            };
        }

        function validateRoleSelection(roles, validator) {
            if (typeof validator !== "function") return true;
            const result = validator(roles || []);
            if (!result || result.ok !== false) return true;
            frappe.msgprint({
                title: t("تعارض في صفحة الدخول"),
                message: result.message || t("الأدوار المحددة تحتوي صفحات دخول مختلفة."),
                indicator: "orange",
            });
            return false;
        }

        function openCreate(config = {}) {
            const canAssignRoles = config.canAssignRoles === true;
            const dialog = new frappe.ui.Dialog({
                title: t("إضافة مستخدم للمعمل"),
                fields: [
                    { fieldname: "email", fieldtype: "Data", label: t("البريد الإلكتروني"), options: "Email", reqd: 1 },
                    { fieldname: "first_name", fieldtype: "Data", label: t("الاسم"), reqd: 1 },
                    { fieldname: "last_name", fieldtype: "Data", label: t("الكنية") },
                    { fieldname: "language", fieldtype: "Select", label: t("اللغة"), options: ["ar", "en"], default: "ar", reqd: 1 },
                    roleField([], !canAssignRoles, config.roleOptions),
                    { fieldname: "temporary_password", fieldtype: "Password", label: t("كلمة مرور مؤقتة"), reqd: 1, description: t("10 محارف على الأقل وتحتوي حرفًا ورقمًا.") },
                ],
                primary_action_label: t("إنشاء المستخدم"),
                primary_action: values => {
                    const roles = canAssignRoles ? (values.roles || []) : [];
                    if (!validateRoleSelection(roles, config.validateRoles)) return false;
                    const payload = { ...values, roles };
                    return Promise.resolve(config.onSubmit && config.onSubmit(payload)).then(() => dialog.hide());
                },
            });
            dialog.show();
            return dialog;
        }

        function openEdit(config = {}) {
            const user = config.user;
            if (!user) return null;
            const canEdit = config.canEdit === true;
            const canAssignRoles = config.canAssignRoles === true;
            const fields = [];
            if (canEdit) {
                fields.push(
                    { fieldname: "first_name", fieldtype: "Data", label: t("الاسم"), reqd: 1, default: user.first_name || "" },
                    { fieldname: "last_name", fieldtype: "Data", label: t("الكنية"), default: user.last_name || "" },
                    { fieldname: "language", fieldtype: "Select", label: t("اللغة"), options: ["ar", "en"], default: user.language || "ar", reqd: 1 }
                );
            }
            if (canAssignRoles) fields.push(roleField(user.roles || [], false, config.roleOptions));
            if (!fields.length) return null;

            const dialog = new frappe.ui.Dialog({
                title: t("تعديل المستخدم {0}", [user.email]),
                fields,
                primary_action_label: t("حفظ"),
                primary_action: values => {
                    if (canAssignRoles && !validateRoleSelection(values.roles || [], config.validateRoles)) return false;
                    const payload = {};
                    if (canEdit) {
                        payload.first_name = values.first_name;
                        payload.last_name = values.last_name;
                        payload.language = values.language;
                    }
                    if (canAssignRoles) payload.roles = values.roles || [];
                    return Promise.resolve(config.onSubmit && config.onSubmit(payload)).then(() => dialog.hide());
                },
            });
            dialog.show();
            return dialog;
        }

        function openPassword(config = {}) {
            const user = config.user;
            if (!user) return null;
            const dialog = new frappe.ui.Dialog({
                title: t("تعيين كلمة مرور مؤقتة"),
                fields: [{ fieldname: "temporary_password", fieldtype: "Password", label: t("كلمة المرور المؤقتة"), reqd: 1 }],
                primary_action_label: t("حفظ كلمة المرور"),
                primary_action: values => Promise.resolve(
                    config.onSubmit && config.onSubmit(values.temporary_password)
                ).then(() => dialog.hide()),
            });
            dialog.show();
            return dialog;
        }

        function confirmToggle(config = {}) {
            const user = config.user;
            if (!user) return false;
            const label = config.enabled ? t("تفعيل") : t("تعطيل");
            frappe.confirm(
                t("هل تريد {0} المستخدم {1}؟", [label, user.email]),
                () => config.onConfirm && config.onConfirm()
            );
            return true;
        }

        function confirmAdopt(config = {}) {
            const user = config.user;
            if (!user) return false;
            frappe.confirm(
                t("سيتم إضافة الحساب {0} إلى نطاق المعمل بدون منحه أي دور أو صلاحية تشغيلية تلقائيًا، وبدون تغيير Default Workspace أو Default App في Frappe. هل تريد المتابعة؟", [user.email]),
                () => config.onConfirm && config.onConfirm()
            );
            return true;
        }

        function openAudit(config = {}) {
            const user = config.user;
            if (!user) return null;
            const dialog = new frappe.ui.Dialog({
                title: t("سجل تغييرات {0}", [user.email]),
                fields: [{ fieldname: "audit", fieldtype: "HTML" }],
                size: "large",
            });
            dialog.fields_dict.audit.$wrapper.html(String(config.html || ""));
            dialog.show();
            return dialog;
        }

        function showAlert(message, indicator = "green") {
            frappe.show_alert({ message, indicator });
        }

        return Object.freeze({
            roleField,
            openCreate,
            openEdit,
            openPassword,
            confirmToggle,
            confirmAdopt,
            openAudit,
            showAlert,
        });
    }

    window.AlmdinaFactoryWorkforceDialogs = Object.freeze({ create });
})();
