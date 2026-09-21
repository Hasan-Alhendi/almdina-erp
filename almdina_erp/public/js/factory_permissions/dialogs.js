(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsDialogs) return;

    function create(options = {}) {
        const translate = options.translate;
        const ownTransient = options.ownTransient;
        const isCurrentGeneration = options.isCurrentGeneration;
        const showMessage = options.showMessage;
        const previewExternal = options.previewExternal;
        const getMaxBytes = options.getMaxBytes;
        const getSelectedRole = options.getSelectedRole;
        const previewImport = options.previewImport;
        const isActive = options.isActive;
        if (
            typeof translate !== "function"
            || typeof ownTransient !== "function"
            || typeof isCurrentGeneration !== "function"
            || typeof showMessage !== "function"
            || typeof previewExternal !== "function"
            || typeof getMaxBytes !== "function"
            || typeof getSelectedRole !== "function"
            || typeof previewImport !== "function"
            || typeof isActive !== "function"
        ) {
            throw new Error("Factory permissions dialog dependencies are unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);

        function extractAttachLocalFile(attachField) {
            if (!attachField) return null;
            const input = attachField.$input && attachField.$input[0];
            if (input && input.files && input.files[0]) return input.files[0];
            if (attachField.file && attachField.file.files && attachField.file.files[0]) {
                return attachField.file.files[0];
            }
            return null;
        }

        function fetchAttachPayload(fileUrl) {
            return fetch(String(fileUrl || ""), { credentials: "same-origin" }).then(response => {
                if (!response.ok) throw new Error("fetch failed");
                return response.text();
            });
        }

        function processImportPayload(payload, generation) {
            if (!isCurrentGeneration(generation)) return;
            const maxBytes = getMaxBytes();
            const normalized = String(payload || "");
            if (normalized.length > maxBytes) {
                showMessage({
                    title: t("ملف كبير جدًا"),
                    message: t("حجم ملف الصلاحيات يتجاوز الحد المسموح."),
                    indicator: "red",
                });
                return;
            }
            try {
                const parsed = JSON.parse(normalized);
                if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("not-object");
            } catch (error) {
                showMessage({
                    title: t("ملف JSON غير صالح"),
                    message: t("تعذر قراءة الملف ككائن JSON صحيح. لم يتم تغيير أي صلاحية."),
                    indicator: "red",
                });
                return;
            }
            previewExternal(
                () => previewImport(getSelectedRole(), normalized, {
                    freeze: true,
                    freezeMessage: t("جاري التحقق من الصلاحيات..."),
                }),
                t("تم التحقق من الملف وتحميله للمعاينة فقط. لن يتغير الدور قبل الحفظ.")
            );
        }

        function processImportFile(file, generation) {
            if (!isCurrentGeneration(generation) || !file) return;
            const maxBytes = getMaxBytes();
            if (file.size > maxBytes) {
                showMessage({
                    title: t("ملف كبير جدًا"),
                    message: t("حجم ملف الصلاحيات يتجاوز الحد المسموح."),
                    indicator: "red",
                });
                return;
            }
            const reader = new FileReader();
            reader.onload = () => {
                if (!isCurrentGeneration(generation)) return;
                processImportPayload(String(reader.result || ""), generation);
            };
            reader.onerror = () => {
                if (!isCurrentGeneration(generation)) return;
                showMessage({
                    title: t("تعذر قراءة الملف"),
                    message: t("لم يتمكن المتصفح من قراءة ملف الصلاحيات."),
                    indicator: "red",
                });
            };
            reader.readAsText(file, "utf-8");
        }

        function openImportDialog(generation) {
            if (!isActive() || !getSelectedRole() || !isCurrentGeneration(generation)) return null;
            const dialog = ownTransient(new frappe.ui.Dialog({
                title: t("استيراد JSON"),
                fields: [{
                    fieldname: "permissions_file",
                    fieldtype: "Attach",
                    label: t("ملف الصلاحيات"),
                    reqd: 1,
                    description: t("الاستيراد يحمّل الصلاحيات للمعاينة فقط؛ الحفظ يبقى خطوة مستقلة."),
                }],
                primary_action_label: t("معاينة"),
                primary_action(values) {
                    if (!isCurrentGeneration(generation)) return;
                    const attachField = dialog.fields_dict.permissions_file;
                    const localFile = extractAttachLocalFile(attachField);
                    if (localFile) {
                        processImportFile(localFile, generation);
                        dialog.hide();
                        return;
                    }
                    const fileUrl = values && values.permissions_file;
                    if (!fileUrl) {
                        frappe.show_alert({
                            message: t("اختر ملف JSON أولاً."),
                            indicator: "orange",
                        });
                        return;
                    }
                    fetchAttachPayload(fileUrl).then(payload => {
                        if (!isCurrentGeneration(generation)) return;
                        processImportPayload(payload, generation);
                        dialog.hide();
                    }).catch(() => {
                        if (!isCurrentGeneration(generation)) return;
                        showMessage({
                            title: t("تعذر قراءة الملف"),
                            message: t("لم يتمكن المتصفح من قراءة ملف الصلاحيات."),
                            indicator: "red",
                        });
                    });
                },
            }));
            if (dialog.$wrapper) {
                dialog.$wrapper.one("hidden.bs.modal", () => {
                    if (typeof options.releaseTransient === "function") options.releaseTransient(dialog);
                });
            }
            dialog.show();
            return dialog;
        }

        return Object.freeze({
            openImportDialog(generation) {
                if (generation === null || generation === undefined) return null;
                return openImportDialog(generation);
            },
        });
    }

    window.AlmdinaFactoryPermissionsDialogs = Object.freeze({ create });
})();
