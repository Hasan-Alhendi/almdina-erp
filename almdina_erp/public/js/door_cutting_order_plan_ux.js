(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);

    function editable(frm) {
        return frm.doc.docstatus === 0 && EDITABLE_STATUSES.has(frm.doc.status || "Draft");
    }

    function num(value, digits = 2) {
        const n = Number(value || 0);
        return Number.isFinite(n) ? n.toFixed(digits) : (0).toFixed(digits);
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function installStyles() {
        if (document.getElementById("dco-plan-ux-css")) return;
        $("head").append(`
            <style id="dco-plan-ux-css">
                .dco-plan-intro {
                    display:grid;
                    grid-template-columns:repeat(4,minmax(0,1fr));
                    gap:10px;
                    margin:4px 0 12px;
                }
                .dco-plan-card {
                    border:1px solid var(--border-color,#dfe3e8);
                    background:var(--subtle-fg,#f8f9fa);
                    border-radius:12px;
                    padding:11px 13px;
                    min-height:70px;
                }
                .dco-plan-card .label {
                    display:block;
                    font-size:11px;
                    opacity:.72;
                    margin-bottom:5px;
                }
                .dco-plan-card .value {
                    display:block;
                    font-size:14px;
                    line-height:1.45;
                    font-weight:800;
                }
                .dco-plan-card .value.small { font-size:12px; }
                .dco-plan-actions {
                    display:flex;
                    gap:8px;
                    flex-wrap:wrap;
                    align-items:center;
                    min-height:40px;
                    padding-top:2px;
                }
                .dco-plan-actions .btn { border-radius:8px; font-weight:700; }
                .dco-plan-note {
                    width:100%;
                    font-size:11px;
                    opacity:.75;
                    line-height:1.55;
                    margin-top:2px;
                }
                .dco-plan-dirty-note {
                    display:none;
                    width:100%;
                    padding:7px 9px;
                    border-radius:8px;
                    background:#fff7df;
                    color:#7a5200;
                    border:1px solid #f1d58c;
                    font-size:11px;
                    font-weight:700;
                }
                .dco-plan-dirty-note.is-visible { display:block; }
                @media (max-width:900px) {
                    .dco-plan-intro { grid-template-columns:repeat(2,minmax(0,1fr)); }
                }
                @media (max-width:560px) {
                    .dco-plan-intro { grid-template-columns:1fr; }
                    .dco-plan-actions .btn { width:100%; }
                }
            </style>
        `);
    }

    function renderSummary(frm) {
        const field = frm.fields_dict.plan_controls_intro;
        if (!field || !field.$wrapper) return;

        const mode = __(frm.doc.packing_mode || "Auto");
        const applied = frm.doc.packing_method || "لم يتم الحساب بعد";
        const usableW = Math.max(0, Number(frm.doc.full_board_width_mm || 0) - Number(frm.doc.trim_margin_mm || 0) * 2);
        const usableL = Math.max(0, Number(frm.doc.full_board_length_mm || 0) - Number(frm.doc.trim_margin_mm || 0) * 2);
        const boardSize = usableW && usableL ? `${num(usableW,0)} × ${num(usableL,0)} مم` : "—";
        const boards = Number(frm.doc.required_boards || 0);
        const waste = Number(frm.doc.waste_percent || 0);

        field.$wrapper.html(`
            <div class="dco-plan-intro">
                <div class="dco-plan-card">
                    <span class="label">طريقة الترتيب المطلوبة</span>
                    <span class="value small">${esc(mode)}</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">الطريقة التي استخدمها المحرك</span>
                    <span class="value small">${esc(applied)}</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">المساحة المتاحة داخل اللوح بعد الهامش</span>
                    <span class="value">${esc(boardSize)}</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">النتيجة الحالية</span>
                    <span class="value">${boards} لوح · هدر ${num(waste,2)}%</span>
                </div>
            </div>
        `);
    }

    function renderActions(frm) {
        const field = frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;
        const canEdit = editable(frm);

        field.$wrapper.html(`
            <div class="dco-plan-actions">
                <button type="button" class="btn btn-primary btn-sm dco-recalculate-plan" ${canEdit ? "" : "disabled"}>
                    إعادة حساب خطة القص
                </button>
                <button type="button" class="btn btn-default btn-sm dco-auto-best-plan" ${canEdit ? "" : "disabled"}>
                    اختيار الأفضل تلقائيًا
                </button>
                <div class="dco-plan-dirty-note">تم تغيير إعدادات الخطة. اضغط «إعادة حساب خطة القص» لتطبيقها على الرسم والنتائج.</div>
                <div class="dco-plan-note">
                    ${canEdit
                        ? "يمكنك تغيير طريقة ترتيب القطع وسماكة خط المنشار وهامش تسوية الحواف من هنا مباشرة، ثم إعادة الحساب دون الرجوع إلى تبويب الطلب."
                        : "هذه الخطة مرتبطة بطلب معتمد أو دخل الإنتاج؛ القيم المعتمدة محفوظة تاريخيًا ولا يمكن إعادة حسابها في مكانها."}
                </div>
            </div>
        `);

        field.$wrapper.find(".dco-recalculate-plan").on("click", () => recalculate(frm));
        field.$wrapper.find(".dco-auto-best-plan").on("click", async () => {
            if (!canEdit) return;
            await frm.set_value("packing_mode", "Auto");
            await recalculate(frm);
        });
    }

    async function recalculate(frm) {
        if (!editable(frm)) {
            frappe.msgprint("لا يمكن إعادة حساب طلب معتمد أو دخل الإنتاج. يجب الحفاظ على الخطة المعتمدة كنسخة تاريخية ثابتة.");
            return;
        }
        if (!frm.doc.board_item || !(frm.doc.pieces || []).length) {
            frappe.msgprint("اختر اللوح وأدخل القياسات أولًا قبل حساب خطة القص.");
            return;
        }

        const buttons = $(frm.wrapper).find(".dco-recalculate-plan,.dco-auto-best-plan");
        buttons.prop("disabled", true);
        frappe.dom.freeze("جاري إعادة حساب أفضل توزيع للقطع...");
        try {
            await frm.save();
            renderSummary(frm);
            renderActions(frm);
            frappe.show_alert({ message: "تم تحديث خطة القص والنتائج", indicator: "green" }, 3);
        } catch (error) {
            console.error("Failed to recalculate cutting plan", error);
            throw error;
        } finally {
            frappe.dom.unfreeze();
            $(frm.wrapper).find(".dco-recalculate-plan,.dco-auto-best-plan").prop("disabled", !editable(frm));
        }
    }

    function markPending(frm) {
        renderSummary(frm);
        const field = frm.fields_dict.plan_control_actions;
        if (field && field.$wrapper) {
            field.$wrapper.find(".dco-plan-dirty-note").addClass("is-visible");
        }
    }

    function applyReadOnlyState(frm) {
        const readOnly = editable(frm) ? 0 : 1;
        ["packing_mode", "kerf_mm", "trim_margin_mm"].forEach(fieldname => {
            frm.set_df_property(fieldname, "read_only", readOnly);
        });
    }

    function refreshPlanUX(frm) {
        installStyles();
        applyReadOnlyState(frm);
        renderSummary(frm);
        renderActions(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refreshPlanUX(frm); },
        refresh(frm) {
            refreshPlanUX(frm);
            requestAnimationFrame(() => refreshPlanUX(frm));
        },
        packing_mode(frm) { markPending(frm); },
        kerf_mm(frm) { markPending(frm); },
        trim_margin_mm(frm) { markPending(frm); },
    });
})();
