(() => {
    "use strict";

    if (window.AlmdinaFactoryWorkforceDialogs) return;

    function create(options = {}) {
        const translate = options.translate;
        if (typeof translate !== "function") {
            throw new Error("Factory workforce dialog translator is unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);
        const ownedSurfaces = new Map();
        const drafts = new Map();

        function rememberDraft(surface, draftKey) {
            if (!draftKey || !surface || typeof surface.get_values !== "function") return;
            const values = surface.get_values(true);
            if (values && typeof values === "object") drafts.set(draftKey, { ...values });
        }

        function own(surface, draftKey = "") {
            if (surface && typeof surface.hide === "function") {
                const key = String(draftKey || "");
                if (key) {
                    for (const [previous, previousKey] of ownedSurfaces) {
                        if (previousKey !== key) continue;
                        rememberDraft(previous, previousKey);
                        ownedSurfaces.delete(previous);
                        previous.hide();
                    }
                }
                ownedSurfaces.set(surface, key);
            }
            return surface;
        }

        function restoreDraft(surface, draftKey) {
            if (!drafts.has(draftKey) || !surface || typeof surface.set_values !== "function") return;
            surface.set_values(drafts.get(draftKey));
        }

        function complete(surface, draftKey) {
            drafts.delete(draftKey);
            if (!ownedSurfaces.has(surface)) return;
            ownedSurfaces.delete(surface);
            surface.hide();
        }

        function deactivate() {
            for (const [surface, draftKey] of ownedSurfaces) {
                rememberDraft(surface, draftKey);
                surface.hide();
            }
            ownedSurfaces.clear();
        }

        function dispose() {
            deactivate();
            drafts.clear();
        }

        function roleField(defaultValue = [], readOnly = false, roleOptions = () => []) {
            return {
                fieldname: "roles",
                fieldtype: "MultiSelectList",
                label: t("Roles"),
                description: t("Select the required roles and permissions. The login page comes from the Home Page on the Role in Frappe and is not determined by the Almdina system."),
                default: defaultValue,
                read_only: readOnly ? 1 : 0,
                get_data: txt => roleOptions(txt),
            };
        }

        function validateRoleSelection(roles, validator) {
            if (typeof validator !== "function") return true;
            const result = validator(roles || []);
            if (!result || result.ok !== false) return true;
            own(frappe.msgprint({
                title: t("Login page conflict"),
                message: result.message || t("Selected roles have different login pages."),
                indicator: "orange",
            }));
            return false;
        }

        function languageChoices(languages, current) {
            const rows = [];
            const seen = new Set();
            (languages || []).forEach(language => {
                const code = String(language && language.code || "").trim();
                if (!code || seen.has(code)) return;
                seen.add(code);
                rows.push({
                    value: code,
                    label: String(language.name || code),
                });
            });
            const selected = String(current || "").trim();
            if (selected && !seen.has(selected)) {
                rows.push({ value: selected, label: selected });
            }
            return rows;
        }

        function languageField(languages, current) {
            const options = languageChoices(languages, current);
            const codes = options.map(option => option.value);
            const fallback = codes.includes("ar") ? "ar" : (codes[0] || "ar");
            const selected = String(current || "").trim();
            return {
                fieldname: "language",
                fieldtype: "Select",
                label: t("Language"),
                options,
                default: codes.includes(selected) ? selected : fallback,
                reqd: 1,
            };
        }

        function openCreate(config = {}) {
            const canAssignRoles = config.canAssignRoles === true;
            const draftKey = "create";
            const dialog = own(new frappe.ui.Dialog({
                title: t("Add user to factory"),
                fields: [
                    { fieldname: "email", fieldtype: "Data", label: t("Email"), options: "Email", reqd: 1 },
                    { fieldname: "first_name", fieldtype: "Data", label: t("Name"), reqd: 1 },
                    { fieldname: "last_name", fieldtype: "Data", label: t("Last name") },
                    languageField(config.languages, ""),
                    roleField([], !canAssignRoles, config.roleOptions),
                    { fieldname: "temporary_password", fieldtype: "Password", label: t("Temporary password"), reqd: 1, description: t("At least 10 characters, including a letter and a number.") },
                ],
                primary_action_label: t("Create user"),
                primary_action: values => {
                    const roles = canAssignRoles ? (values.roles || []) : [];
                    if (!validateRoleSelection(roles, config.validateRoles)) return false;
                    const payload = { ...values, roles };
                    return Promise.resolve(config.onSubmit && config.onSubmit(payload)).then(() => {
                        complete(dialog, draftKey);
                    }).catch(error => {
                        if (!ownedSurfaces.has(dialog)) return null;
                        throw error;
                    });
                },
            }), draftKey);
            restoreDraft(dialog, draftKey);
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
                    { fieldname: "first_name", fieldtype: "Data", label: t("Name"), reqd: 1, default: user.first_name || "" },
                    { fieldname: "last_name", fieldtype: "Data", label: t("Last name"), default: user.last_name || "" },
                    languageField(config.languages, user.language || "ar")
                );
            }
            if (canAssignRoles) fields.push(roleField(user.roles || [], false, config.roleOptions));
            if (!fields.length) return null;

            const draftKey = `edit:${user.email}`;
            const dialog = own(new frappe.ui.Dialog({
                title: t("Edit user {0}", [user.email]),
                fields,
                primary_action_label: t("Save"),
                primary_action: values => {
                    if (canAssignRoles && !validateRoleSelection(values.roles || [], config.validateRoles)) return false;
                    const payload = {};
                    if (canEdit) {
                        payload.first_name = values.first_name;
                        payload.last_name = values.last_name;
                        payload.language = values.language;
                    }
                    if (canAssignRoles) payload.roles = values.roles || [];
                    return Promise.resolve(config.onSubmit && config.onSubmit(payload)).then(() => {
                        complete(dialog, draftKey);
                    }).catch(error => {
                        if (!ownedSurfaces.has(dialog)) return null;
                        throw error;
                    });
                },
            }), draftKey);
            restoreDraft(dialog, draftKey);
            dialog.show();
            return dialog;
        }

        function openPassword(config = {}) {
            const user = config.user;
            if (!user) return null;
            const draftKey = `password:${user.email}`;
            const dialog = own(new frappe.ui.Dialog({
                title: t("Set temporary password"),
                fields: [{ fieldname: "temporary_password", fieldtype: "Password", label: t("Temporary password"), reqd: 1 }],
                primary_action_label: t("Save password"),
                primary_action: values => Promise.resolve(
                    config.onSubmit && config.onSubmit(values.temporary_password)
                ).then(() => {
                    complete(dialog, draftKey);
                }).catch(error => {
                    if (!ownedSurfaces.has(dialog)) return null;
                    throw error;
                }),
            }), draftKey);
            restoreDraft(dialog, draftKey);
            dialog.show();
            return dialog;
        }

        function confirmToggle(config = {}) {
            const user = config.user;
            if (!user) return false;
            const label = config.enabled ? t("Enable") : t("Disable");
            own(frappe.confirm(
                t("Do you want to {0} user {1}?", [label, user.email]),
                () => config.onConfirm && config.onConfirm()
            ));
            return true;
        }

        function confirmAdopt(config = {}) {
            const user = config.user;
            if (!user) return false;
            own(frappe.confirm(
                t("Account {0} will be added to the factory scope without automatically granting any role or operational permission, and without changing Default Workspace or Default App in Frappe. Do you want to continue?", [user.email]),
                () => config.onConfirm && config.onConfirm()
            ));
            return true;
        }

        function openAudit(config = {}) {
            const user = config.user;
            if (!user) return null;
            const dialog = own(new frappe.ui.Dialog({
                title: t("Change log for {0}", [user.email]),
                fields: [{ fieldname: "audit", fieldtype: "HTML" }],
                size: "large",
            }));
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
            deactivate,
            dispose,
        });
    }

    window.AlmdinaFactoryWorkforceDialogs = Object.freeze({ create });
})();
