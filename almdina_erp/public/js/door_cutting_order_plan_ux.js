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

    function parsePlan(frm) {
        try {
            return typeof frm.doc.cutting_plan_json === "object"
                ? (frm.doc.cutting_plan_json || {})
                : JSON.parse(frm.doc.cutting_plan_json || "{}");
        } catch (error) {
            return {};
        }
    }

    function modeDescription(mode) {
        const descriptions = {
            "Auto": "سريع: يقارن الخوارزميات الأساسية ويختار أفضل نتيجة مباشرة.",
            "Auto Pro": "متقدم: يجرب الخوارزميات مع ترتيبات متعددة للقطع ثم يجري تحسينًا محليًا للنتيجة.",
            "Deep Search": "بحث معمق: يبدأ من Auto Pro ثم يجري مئات المحاولات المحكومة ضمن المهلة المحددة.",
            "Optimal Search": "بحث أمثل: يستخدم CP-SAT للحالات المناسبة لإثبات أقل عدد ألواح عند الوصول إلى OPTIMAL، مع أفضل حل ضمن المهلة كبديل.",
        };
        return descriptions[mode] || "اختيار يدوي لخوارزمية ترتيب محددة.";
    }

    function machineDescription(machine) {
        if (machine === "Panel Saw") {
            return "منشار ألواح: يقيّد البحث التلقائي بخطط Guillotine القابلة للتنفيذ كسلسلة قصات مستقيمة.";
        }
        if (machine === "CNC Router") {
            return "راوتر CNC: يسمح بخطط Nesting غير Guillotine للحصول على حرية أكبر في التوزيع.";
        }
        return "تلقائي: لا يفرض قيد ماكينة خاص. اختر نوع الماكينة الفعلي للحصول على تقييم أدق.";
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
                .dco-plan-card .sub {
                    display:block;
                    font-size:10px;
                    line-height:1.45;
                    opacity:.72;
                    margin-top:5px;
                }
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
                    opacity:.78;
                    line-height:1.65;
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
                .dco-solver-badge {
                    display:inline-flex;
                    align-items:center;
                    border-radius:999px;
                    padding:3px 8px;
                    font-size:10px;
                    font-weight:800;
                    background:rgba(36,144,239,.11);
                    color:var(--primary,#2490ef);
                    margin-top:4px;
                }
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

        const plan = parsePlan(frm);
        const metrics = plan.industrial_metrics || {};
        const mode = __(frm.doc.packing_mode || "Auto Pro");
        const applied = frm.doc.packing_method || "لم يتم الحساب بعد";
        const machine = __(frm.doc.cutting_machine_type || "Auto");
        const usableW = Math.max(0, Number(frm.doc.full_board_width_mm || 0) - Number(frm.doc.trim_margin_mm || 0) * 2);
        const usableL = Math.max(0, Number(frm.doc.full_board_length_mm || 0) - Number(frm.doc.trim_margin_mm || 0) * 2);
        const boardSize = usableW && usableL ? `${num(usableW,0)} × ${num(usableL,0)} مم` : "—";
        const boards = Number(frm.doc.required_boards || 0);
        const waste = Number(frm.doc.waste_percent || 0);
        const reusable = Number(metrics.largest_reusable_free_area_m2 || 0);
        const cuts = Number(metrics.estimated_cut_count || 0);
        const attempts = Number(plan.attempts || 0);
        const elapsed = Number(plan.search_elapsed_sec || plan.solver_wall_time_sec || 0);
        const solver = plan.solver_status || "";

        field.$wrapper.html(`
            <div class="dco-plan-intro">
                <div class="dco-plan-card">
                    <span class="label">مستوى التحسين</span>
                    <span class="value small">${esc(mode)}</span>
                    <span class="sub">${esc(modeDescription(frm.doc.packing_mode || "Auto Pro"))}</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">نوع ماكينة القص</span>
                    <span class="value small">${esc(machine)}</span>
                    <span class="sub">${esc(machineDescription(frm.doc.cutting_machine_type || "Auto"))}</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">الطريقة التي استخدمها المحرك</span>
                    <span class="value small">${esc(applied)}</span>
                    ${solver ? `<span class="dco-solver-badge">${esc(solver)}</span>` : ""}
                </div>
                <div class="dco-plan-card">
                    <span class="label">المساحة المتاحة داخل اللوح بعد الهامش</span>
                    <span class="value">${esc(boardSize)}</span>
                    <span class="sub">Kerf ${num(frm.doc.kerf_mm,1)} مم · Trim ${num(frm.doc.trim_margin_mm,1)} مم</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">النتيجة الحالية</span>
                    <span class="value">${boards} لوح · هدر ${num(waste,2)}%</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">جودة البقايا</span>
                    <span class="value">${num(reusable,3)} م²</span>
                    <span class="sub">أكبر مستطيل بقايا قابل لإعادة الاستخدام وفق حدود المعمل.</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">سهولة التنفيذ</span>
                    <span class="value">${cuts} خط قص تقديري</span>
                    <span class="sub">${num(Number(metrics.estimated_cut_length_cm || 0) / 100,2)} متر قص تقريبي · ${Number(metrics.rotation_count || 0)} تدوير</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">جهد البحث</span>
                    <span class="value">${attempts} محاولة</span>
                    <span class="sub">${elapsed ? `${num(elapsed,2)} ثانية` : "حساب مباشر"}</span>
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
                <button type="button" class="btn btn-default btn-sm dco-auto-pro-plan" ${canEdit ? "" : "disabled"}>
                    أفضل توزيع متقدم
                </button>
                <button type="button" class="btn btn-default btn-sm dco-deep-plan" ${canEdit ? "" : "disabled"}>
                    بحث معمق
                </button>
                <button type="button" class="btn btn-default btn-sm dco-optimal-plan" ${canEdit ? "" : "disabled"}>
                    بحث أمثل
                </button>
                <div class="dco-plan-dirty-note">تم تغيير إعدادات الخطة. اضغط «إعادة حساب خطة القص» لتطبيقها على الرسم والنتائج.</div>
                <div class="dco-plan-note">
                    ${canEdit
                        ? "كل ما يتعلق بتغيير خطة القص أصبح هنا. Auto Pro هو الخيار اليومي الموصى به؛ البحث المعمق يعطي وقتًا إضافيًا لتحسين الترتيب؛ والبحث الأمثل يستخدم Solver للحالات المناسبة وقد يثبت أن عدد الألواح هو الحد الأدنى."
                        : "هذه الخطة مرتبطة بطلب معتمد أو دخل الإنتاج؛ القيم المعتمدة محفوظة تاريخيًا ولا يمكن إعادة حسابها في مكانها."}
                </div>
            </div>
        `);

        field.$wrapper.find(".dco-recalculate-plan").on("click", () => recalculate(frm));
        field.$wrapper.find(".dco-auto-pro-plan").on("click", async () => {
            if (!canEdit) return;
            await frm.set_value("packing_mode", "Auto Pro");
            await recalculate(frm);
        });
        field.$wrapper.find(".dco-deep-plan").on("click", async () => {
            if (!canEdit) return;
            await frm.set_value("packing_mode", "Deep Search");
            await recalculate(frm);
        });
        field.$wrapper.find(".dco-optimal-plan").on("click", async () => {
            if (!canEdit) return;
            await frm.set_value("packing_mode", "Optimal Search");
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

        const buttons = $(frm.wrapper).find(".dco-recalculate-plan,.dco-auto-pro-plan,.dco-deep-plan,.dco-optimal-plan");
        buttons.prop("disabled", true);
        const mode = frm.doc.packing_mode || "Auto Pro";
        const message = mode === "Optimal Search"
            ? "جاري البحث الأمثل عن أقل عدد ألواح..."
            : mode === "Deep Search"
                ? "جاري البحث المعمق عن أفضل توزيع..."
                : "جاري إعادة حساب أفضل توزيع للقطع...";
        frappe.dom.freeze(message);
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
            $(frm.wrapper).find(".dco-recalculate-plan,.dco-auto-pro-plan,.dco-deep-plan,.dco-optimal-plan").prop("disabled", !editable(frm));
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
        ["packing_mode", "cutting_machine_type", "kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"].forEach(fieldname => {
            frm.set_df_property(fieldname, "read_only", readOnly);
        });
        frm.toggle_display("optimization_time_limit_sec", ["Deep Search", "Optimal Search"].includes(frm.doc.packing_mode));
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
        packing_mode(frm) { applyReadOnlyState(frm); markPending(frm); },
        cutting_machine_type(frm) { markPending(frm); },
        kerf_mm(frm) { markPending(frm); },
        trim_margin_mm(frm) { markPending(frm); },
        optimization_time_limit_sec(frm) { markPending(frm); },
    });
})();
