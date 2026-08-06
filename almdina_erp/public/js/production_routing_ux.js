(() => {
    "use strict";

    const ROLE_METHOD = "almdina_erp.almdina_erp.services.master_data_service.get_eligible_routing_roles";
    const STAGE_LABELS = Object.freeze({
        Sharyoun: "شريون",
        Drawing: "رسم",
        CNC: "CNC",
        Sanding: "تقشيط",
        Cutting: "قص",
        "Edge Banding": "قشاط",
        "Review / Preparation": "مراجعة وتجهيز",
        Drilling: "تثقيب",
        Assembly: "تجميع",
        "Quality Check": "فحص الجودة",
        Packing: "تغليف",
    });

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function normalizeRoles(values) {
        const source = Array.isArray(values) ? values : values ? [values] : [];
        const roles = [];
        const seen = new Set();
        source.forEach(value => {
            const role = String(
                typeof value === "object" && value !== null
                    ? value.value || value.name || ""
                    : value || ""
            ).trim();
            if (!role || seen.has(role)) return;
            seen.add(role);
            roles.push(role);
        });
        return roles;
    }

    function rowRoles(row) {
        const raw = String(row.eligible_roles_json || "").trim();
        if (raw) {
            try {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) return normalizeRoles(parsed);
            } catch (error) {
                // The server remains authoritative and will reject malformed JSON.
            }
        }
        return normalizeRoles(row.operational_role);
    }

    function nextSequence(frm) {
        return Math.max(
            0,
            ...(frm.doc.stages || []).map(row => Number(row.sequence || 0))
        ) + 10;
    }

    function routePreviewRows(frm) {
        return (frm.doc.stages || [])
            .slice()
            .sort((left, right) => Number(left.sequence || 0) - Number(right.sequence || 0))
            .filter(row => Number(row.required || 0))
            .map(row => ({
                label: row.department_label || row.stage_type,
                roles: rowRoles(row),
            }));
    }

    function routePreviewHtml(frm) {
        const rows = routePreviewRows(frm);
        if (!rows.length) return "";
        return `
            <div dir="rtl" style="display:grid;gap:10px">
                ${rows.map((row, index) => `
                    <div style="display:grid;grid-template-columns:34px minmax(0,1fr);gap:10px;align-items:start;padding:12px;border:1px solid var(--border-color,#e5e7eb);border-radius:12px;background:var(--fg-color,#fff)">
                        <div style="display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:var(--primary,#2490ef);color:#fff;font-weight:800">${index + 1}</div>
                        <div>
                            <div style="font-size:15px;font-weight:800">${esc(row.label)}</div>
                            <div style="margin-top:5px;color:var(--text-muted,#6b7280);font-size:12px;line-height:1.7">
                                ${row.roles.length
                                    ? `${__("الأدوار المؤهلة")}: ${row.roles.map(esc).join("، ")}`
                                    : `<span style="color:#b42318">${__("لم تُحدد أدوار لهذه المرحلة")}</span>`}
                            </div>
                        </div>
                    </div>
                `).join("")}
            </div>
        `;
    }

    function roleOptions(roles, txt = "") {
        const query = String(txt || "").trim().toLowerCase();
        return roles
            .filter(role => {
                if (!query) return true;
                return [role.name, role.description]
                    .some(value => String(value || "").toLowerCase().includes(query));
            })
            .map(role => ({
                value: role.name,
                description: role.description || role.name,
            }));
    }

    function loadEligibleRoles() {
        return frappe.call({
            method: ROLE_METHOD,
            args: {search: ""},
            freeze: true,
            freeze_message: __("جاري تحميل الأدوار المؤهلة..."),
        }).then(response => Array.isArray(response.message) ? response.message : []);
    }

    function setRowRoles(frm, cdt, cdn, roles) {
        const normalized = normalizeRoles(roles);
        return Promise.all([
            frappe.model.set_value(cdt, cdn, "eligible_roles_json", JSON.stringify(normalized)),
            frappe.model.set_value(cdt, cdn, "eligible_roles_display", normalized.join("، ")),
            frappe.model.set_value(cdt, cdn, "operational_role", normalized[0] || ""),
        ]).then(() => frm.refresh_field("stages"));
    }

    function openRolePicker(frm, cdt, cdn) {
        const row = locals[cdt] && locals[cdt][cdn];
        if (!row) return;

        loadEligibleRoles().then(roles => {
            if (!roles.length) {
                frappe.msgprint({
                    title: __("لا توجد أدوار مؤهلة"),
                    indicator: "orange",
                    message: __("أنشئ دورًا مفعّلًا من إدارة الأدوار أولًا، ثم امنحه صلاحيات بدء المرحلة وتسليمها."),
                });
                return;
            }
            const dialog = new frappe.ui.Dialog({
                title: `${__("أدوار المرحلة")}: ${row.department_label || row.stage_type || "—"}`,
                size: "large",
                fields: [
                    {
                        fieldname: "guidance",
                        fieldtype: "HTML",
                        options: `
                            <div dir="rtl" style="padding:12px 14px;margin-bottom:8px;border:1px solid #b9dcf7;border-radius:12px;background:#edf7ff;line-height:1.8">
                                <b>${__("اختر دورًا واحدًا أو عدة أدوار")}</b><br>
                                <span>${__("سيظهر للإسناد فقط المستخدم المفعّل الذي يملك أحد هذه الأدوار، ويملك أيضًا صلاحيتي بدء المرحلة وتسليمها.")}</span>
                            </div>
                        `,
                    },
                    {
                        fieldname: "roles",
                        fieldtype: "MultiSelectList",
                        label: __("الأدوار المؤهلة"),
                        reqd: Number(row.required || 0) ? 1 : 0,
                        get_data: txt => roleOptions(roles, txt),
                        description: __("لا يعتمد النظام على اسم المرحلة أو اسم دور ثابت داخل الكود."),
                    },
                ],
                primary_action_label: __("اعتماد الأدوار"),
                primary_action: values => {
                    const selected = normalizeRoles(values.roles);
                    if (Number(row.required || 0) && !selected.length) {
                        frappe.msgprint(__("اختر دورًا واحدًا على الأقل للمرحلة المطلوبة."));
                        return;
                    }
                    dialog.get_primary_btn().prop("disabled", true);
                    setRowRoles(frm, cdt, cdn, selected)
                        .then(() => {
                            dialog.hide();
                            frappe.show_alert({
                                message: __("تم تحديث الأدوار المؤهلة للمرحلة."),
                                indicator: "green",
                            });
                        })
                        .finally(() => dialog.get_primary_btn().prop("disabled", false));
                },
            });
            dialog.show();
            dialog.set_value("roles", rowRoles(row));
        });
    }

    frappe.ui.form.on("Production Routing", {
        refresh(frm) {
            frm.set_intro(
                __("رتّب المراحل وحدد لكل مرحلة دورًا واحدًا أو عدة أدوار مؤهلة. لا يستطيع استلام المرحلة إلا مستخدم مفعّل يملك أحد الأدوار وصلاحيات التنفيذ اللازمة. تعديل المسار المستخدم في طلب نشط محمي تلقائيًا."),
                "blue"
            );
            if (!frm.is_new() && routePreviewRows(frm).length) {
                frm.add_custom_button(__("معاينة المسار"), () => {
                    frappe.msgprint({
                        title: __("سير الطلب والأدوار المؤهلة"),
                        indicator: "blue",
                        message: routePreviewHtml(frm),
                        wide: true,
                    });
                });
            }
        },
        validate(frm) {
            const missing = (frm.doc.stages || []).filter(
                row => Number(row.required || 0) && !rowRoles(row).length
            );
            if (missing.length) {
                frappe.throw(
                    __("حدد الأدوار المؤهلة للمراحل المطلوبة: {0}", [
                        missing.map(row => row.department_label || row.stage_type).join("، "),
                    ])
                );
            }
        },
    });

    frappe.ui.form.on("Production Routing Stage", {
        stages_add(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row.sequence) {
                frappe.model.set_value(cdt, cdn, "sequence", nextSequence(frm));
            }
            if (row.required === undefined || row.required === null) {
                frappe.model.set_value(cdt, cdn, "required", 1);
            }
        },
        stage_type(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            const label = STAGE_LABELS[String(row.stage_type || "").trim()];
            if (label && !row.department_label) {
                frappe.model.set_value(cdt, cdn, "department_label", label);
            }
        },
        configure_roles(frm, cdt, cdn) {
            openRolePicker(frm, cdt, cdn);
        },
        required(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!Number(row.required || 0) && !rowRoles(row).length) {
                setRowRoles(frm, cdt, cdn, []);
            }
        },
    });
})();
