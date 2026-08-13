(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions &&
            (
                typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, capability)
                    : permissions.can(capability)
            )
        );
    }

    function documentContext() {
        return window.AlmdinaDocumentContext;
    }

    function holdsStageOperationalRole(frm) {
        const context = documentContext();
        if (context && typeof context.holdsStageOperationalRole === "function") {
            return context.holdsStageOperationalRole(frm);
        }
        return Boolean(frm && frm.__almdina_actor_holds_stage_role);
    }

    function canMutateCurrentStage(frm) {
        const context = documentContext();
        if (context && typeof context.canMutateCurrentStage === "function") {
            return context.canMutateCurrentStage(frm);
        }
        return holdsStageOperationalRole(frm);
    }

    function stageMutationBlockReason(frm) {
        const context = documentContext();
        if (context && typeof context.stageMutationBlockReason === "function") {
            return context.stageMutationBlockReason(frm) || "";
        }
        return "";
    }

    function isStageContextPending(frm) {
        const context = documentContext();
        if (context && typeof context.isStageContextPending === "function") {
            return context.isStageContextPending(frm);
        }
        return false;
    }

    function hasUploadCapability(frm) {
        if (!frm || frm.is_new()) return false;
        return Boolean(frm.doc.production_dxf)
            ? can(frm, "replace_dxf")
            : can(frm, "upload_dxf");
    }

    function canUseDocumentPlanActions(frm) {
        // Any worker may run the plan commands their capabilities grant while the
        // order sits on a stage whose operational role they hold. Once it leaves
        // those stages the surface becomes view-only.
        return Boolean(frm && frm.doc) && canMutateCurrentStage(frm);
    }

    function canUploadDxf(frm) {
        return canUseDocumentPlanActions(frm) && hasUploadCapability(frm);
    }

    function canPrintCuttingPlan(frm) {
        if (!can(frm, "print_cutting_plan")) return false;
        // Printing is read-only, so a pre-production order needs no stage role.
        if (!String(frm.doc.production_path || "").trim()) return true;
        return canUseDocumentPlanActions(frm);
    }

    function canExportDxf(frm) {
        if (!canUseDocumentPlanActions(frm)) return false;
        return frappe.almdina && typeof frappe.almdina.can_export_dxf === "function"
            ? Boolean(frappe.almdina.can_export_dxf(frm))
            : can(frm, "export_dxf");
    }

    function canTuneCuttingAlgorithm(frm) {
        const context = documentContext();
        if (context && typeof context.canTuneCuttingAlgorithm === "function") {
            return context.canTuneCuttingAlgorithm(frm);
        }
        if (!frm || frm.is_new() || frm.doc.approved_plan) return false;
        if (!canMutateCurrentStage(frm)) return false;
        if (frm.doc.current_production_stage) return true;
        return EDITABLE_STATUSES.has(frm.doc.status || "Draft");
    }

    function canOperatePlanEngine(frm) {
        // The plan engine answers to its own capability plus where the order
        // stands. It never waits for an order edit session.
        return canTuneCuttingAlgorithm(frm) && can(frm, "recalculate_plan");
    }

    function canRecalculatePlan(frm) {
        return canOperatePlanEngine(frm);
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
            "Auto": "مقارنة سريعة بين الخوارزميات الأساسية.",
            "Auto Pro": "الخيار اليومي الموصى به: محاولات متعددة وتحسين محلي للنتيجة.",
            "Deep Search": "بحث أوسع ضمن المهلة المحددة للحصول على توزيع أفضل.",
            "Optimal Search": "بحث Solver للحالات المناسبة مع الاحتفاظ بأفضل حل صالح ضمن المهلة.",
        };
        return descriptions[mode] || "اختيار يدوي لخوارزمية ترتيب محددة.";
    }

    function installStyles() {
        if (document.getElementById("dco-plan-ux-css")) return;
        $("head").append(`
            <style id="dco-plan-ux-css">
                .dco-plan-section-card {
                    border:1px solid var(--border-color,#dfe3e8) !important;
                    border-radius:16px !important;
                    margin:12px 0 !important;
                    background:var(--card-bg,var(--fg-color,#fff)) !important;
                    box-shadow:0 5px 18px rgba(15,23,42,.045);
                    overflow:hidden;
                }
                .dco-plan-section-card > .section-head,
                .dco-plan-section-card .section-head {
                    padding-top:14px !important;
                }
                .dco-plan-section-card .section-body {
                    padding-bottom:12px !important;
                }
                .dco-cut-settings-card {
                    border-inline-start:4px solid #64748b !important;
                    background:linear-gradient(180deg,rgba(100,116,139,.035),transparent 42%) !important;
                }
                .dco-optimizer-card {
                    border-inline-start:4px solid var(--primary,#2490ef) !important;
                    background:linear-gradient(180deg,rgba(36,144,239,.045),transparent 46%) !important;
                }
                .dco-result-card {
                    border-inline-start:4px solid #10b981 !important;
                }
                .dco-layout-card {
                    border-inline-start:4px solid #0f172a !important;
                }
                .dco-plan-section-card .control-label {
                    font-weight:750;
                    color:var(--text-color,#1f2937);
                }
                .dco-plan-section-card .form-control,
                .dco-plan-section-card .input-with-feedback {
                    border-radius:10px !important;
                    min-height:38px;
                }
                .dco-plan-intro {
                    display:grid;
                    grid-template-columns:repeat(4,minmax(0,1fr));
                    gap:10px;
                    margin:2px 0 4px;
                }
                .dco-plan-card {
                    border:1px solid var(--border-color,#dfe3e8);
                    background:var(--subtle-fg,#f8f9fa);
                    border-radius:13px;
                    padding:12px 14px;
                    min-height:92px;
                    position:relative;
                    overflow:hidden;
                }
                .dco-plan-card::after {
                    content:"";
                    position:absolute;
                    inset-inline-end:-18px;
                    top:-18px;
                    width:58px;
                    height:58px;
                    border-radius:50%;
                    background:rgba(36,144,239,.045);
                }
                .dco-plan-card .label {
                    display:block;
                    font-size:11px;
                    opacity:.7;
                    margin-bottom:6px;
                    font-weight:700;
                }
                .dco-plan-card .value {
                    display:block;
                    font-size:16px;
                    line-height:1.45;
                    font-weight:850;
                    position:relative;
                    z-index:1;
                }
                .dco-plan-card .value.small { font-size:12px; }
                .dco-plan-card .sub {
                    display:block;
                    font-size:10px;
                    line-height:1.55;
                    opacity:.72;
                    margin-top:6px;
                    position:relative;
                    z-index:1;
                }
                .dco-plan-actions-shell {
                    margin-top:8px;
                    padding:12px;
                    border:1px solid var(--border-color,#dfe3e8);
                    border-radius:13px;
                    background:rgba(248,250,252,.72);
                }
                .dco-plan-actions-title {
                    display:flex;
                    align-items:center;
                    justify-content:space-between;
                    gap:10px;
                    margin-bottom:9px;
                    flex-wrap:wrap;
                }
                .dco-plan-actions-title strong { font-size:12px; }
                .dco-plan-mode-hint {
                    font-size:10px;
                    opacity:.7;
                    line-height:1.5;
                }
                .dco-plan-actions {
                    display:flex;
                    gap:8px;
                    flex-wrap:wrap;
                    align-items:center;
                }
                .dco-plan-actions .btn {
                    border-radius:9px;
                    font-weight:750;
                    min-height:34px;
                    padding-inline:13px;
                }
                .dco-plan-actions .dco-recalculate-plan {
                    box-shadow:0 4px 10px rgba(36,144,239,.16);
                }
                .dco-plan-document-actions {
                    display:flex;
                    gap:8px;
                    flex-wrap:wrap;
                    align-items:center;
                    margin-top:10px;
                    padding-top:10px;
                    border-top:1px dashed var(--border-color,#dfe3e8);
                }
                .dco-plan-document-actions .btn {
                    border-radius:9px;
                    font-weight:750;
                    min-height:34px;
                    padding-inline:13px;
                }
                .dco-plan-note {
                    width:100%;
                    font-size:10px;
                    opacity:.72;
                    line-height:1.6;
                    margin-top:9px;
                    padding-top:8px;
                    border-top:1px dashed var(--border-color,#dfe3e8);
                }
                .dco-plan-dirty-note {
                    display:none;
                    width:100%;
                    padding:8px 10px;
                    border-radius:9px;
                    background:#fff7df;
                    color:#7a5200;
                    border:1px solid #f1d58c;
                    font-size:11px;
                    font-weight:750;
                    margin-bottom:8px;
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
                    margin-top:5px;
                }
                [data-fieldname="cutting_plan_html"] .dco-cutting-plan {
                    padding:2px 0 4px !important;
                    background:transparent !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-sheet-card {
                    border:1px solid var(--border-color,#cbd5e1) !important;
                    border-radius:15px !important;
                    padding:12px !important;
                    margin:12px 0 !important;
                    box-shadow:0 5px 18px rgba(15,23,42,.055);
                    background:var(--card-bg,#fff) !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-sheet-title {
                    padding:2px 2px 10px;
                    border-bottom:1px solid var(--border-color,#e2e8f0);
                    margin-bottom:12px !important;
                    align-items:center;
                    flex-wrap:wrap;
                }
                [data-fieldname="cutting_plan_html"] .dco-sheet-board {
                    border-radius:8px;
                    box-shadow:inset 0 0 0 1px rgba(15,23,42,.05);
                }
                @media (max-width:900px) {
                    .dco-plan-intro { grid-template-columns:repeat(2,minmax(0,1fr)); }
                }
                @media (max-width:560px) {
                    .dco-plan-intro { grid-template-columns:1fr; }
                    .dco-plan-actions .btn { width:100%; }
                    .dco-plan-actions-shell { padding:10px; }
                }
            </style>
        `);
    }

    function sectionElement(frm, fieldname) {
        const field = frm.fields_dict[fieldname];
        if (!field || !field.$wrapper) return $();
        const $closest = field.$wrapper.closest(".form-section");
        return $closest.length ? $closest : field.$wrapper;
    }

    function decorateSections(frm) {
        const groups = [
            ["cut_geometry_section", "dco-plan-section-card dco-cut-settings-card"],
            ["optimizer_section", "dco-plan-section-card dco-optimizer-card"],
            ["plan_result_section", "dco-plan-section-card dco-result-card"],
            ["plan_section", "dco-plan-section-card dco-layout-card"],
        ];
        groups.forEach(([fieldname, classes]) => {
            const $section = sectionElement(frm, fieldname);
            if ($section.length) $section.addClass(classes);
        });
    }

    function renderSummary(frm) {
        const field = frm.fields_dict.plan_controls_intro;
        if (!field || !field.$wrapper) return;
        if (field.df && Number(field.df.hidden || 0) === 1) {
            field.$wrapper.empty();
            return;
        }

        const plan = parsePlan(frm);
        const metrics = plan.industrial_metrics || {};
        const applied = frm.doc.packing_method || "لم يتم الحساب بعد";
        const boards = Number(frm.doc.required_boards || 0);
        const waste = Number(frm.doc.waste_percent || 0);
        const reusable = Number(metrics.largest_reusable_free_area_m2 || 0);
        const cuts = Number(metrics.estimated_cut_count || 0);
        const cutLengthM = Number(metrics.estimated_cut_length_cm || 0) / 100;
        const rotations = Number(metrics.rotation_count || 0);
        const attempts = Number(plan.attempts || 0);
        const elapsed = Number(plan.search_elapsed_sec || plan.solver_wall_time_sec || 0);
        const solver = plan.solver_status || "";

        field.$wrapper.html(`
            <div class="dco-plan-intro">
                <div class="dco-plan-card">
                    <span class="label">النتيجة الحالية</span>
                    <span class="value">${boards} لوح · هدر ${num(waste,2)}%</span>
                    <span class="sub">النتيجة المباشرة بعد تطبيق إعدادات خطة القص الحالية.</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">الطريقة الفعلية المختارة</span>
                    <span class="value small">${esc(applied)}</span>
                    ${solver ? `<span class="dco-solver-badge">${esc(solver)}</span>` : ""}
                </div>
                <div class="dco-plan-card">
                    <span class="label">أكبر مساحة فارغة</span>
                    <span class="value">${num(reusable,3)} م²</span>
                    <span class="sub">أكبر مستطيل فارغ داخل اللوح بعد توزيع القطع.</span>
                </div>
                <div class="dco-plan-card">
                    <span class="label">سهولة التنفيذ</span>
                    <span class="value">${cuts} خط قص</span>
                    <span class="sub">${num(cutLengthM,2)} م تقريبًا · ${rotations} تدوير · ${attempts} محاولة${elapsed ? ` · ${num(elapsed,2)} ث` : ""}</span>
                </div>
            </div>
        `);
    }

    function printCuttingPlan(frm) {
        if (!canPrintCuttingPlan(frm)) {
            frappe.msgprint("ليست لديك صلاحية طباعة خطة القص.");
            return;
        }
        if (window.AlmdinaPlanTabsUX && typeof window.AlmdinaPlanTabsUX.printActivePlan === "function") {
            window.AlmdinaPlanTabsUX.printActivePlan(frm);
            return;
        }
        if (window.AlmdinaCuttingPlanRender && typeof window.AlmdinaCuttingPlanRender.print === "function") {
            window.AlmdinaCuttingPlanRender.print(frm);
            return;
        }
        if (window.AlmdinaDrawingPlanUX && typeof window.AlmdinaDrawingPlanUX.printActivePlan === "function") {
            window.AlmdinaDrawingPlanUX.printActivePlan(frm);
            return;
        }
        frappe.msgprint("تعذر تجهيز طباعة خطة القص.");
    }

    function exportCuttingPlanDxf(frm) {
        if (!canExportDxf(frm)) {
            frappe.msgprint(__(
                stageMutationBlockReason(frm) || "ليست لديك صلاحية تصدير DXF."
            ));
            return;
        }
        if (frappe.almdina && typeof frappe.almdina.export_order_dxf === "function") {
            return frappe.almdina.export_order_dxf(frm.doc.name);
        }
        frappe.msgprint("تعذر تشغيل مصدر DXF الآمن.");
        return null;
    }

    function uploadCuttingPlanDxf(frm) {
        if (!canUploadDxf(frm)) {
            frappe.msgprint(__(
                stageMutationBlockReason(frm)
                || "ليست لديك صلاحية رفع خطة القص كملف DXF."
            ));
            return;
        }
        if (frappe.almdina && typeof frappe.almdina.upload_production_dxf === "function") {
            frappe.almdina.upload_production_dxf(frm);
            return;
        }
        if (frm.is_new()) {
            frappe.msgprint(__("احفظ الطلب قبل رفع ملف DXF."));
            return;
        }
        const replacing = Boolean(frm.doc.production_dxf);
        new frappe.ui.FileUploader({
            doctype: "Door Cutting Order",
            docname: frm.doc.name,
            folder: "Home/Attachments",
            is_private: 1,
            restrictions: { allowed_file_types: [".dxf"], max_file_size: 10 * 1024 * 1024 },
            on_success(file) {
                frappe.call({
                    method: "almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf",
                    args: { order_name: frm.doc.name, file_url: file.file_url },
                    freeze: true,
                    freeze_message: __("جاري التحقق من ملف DXF وتطبيق الخطة..."),
                }).then(() => {
                    frappe.show_alert({
                        message: replacing
                            ? __("تم استبدال ملف DXF والتحقق منه.")
                            : __("تم رفع ملف DXF والتحقق منه."),
                        indicator: "green",
                    }, 5);
                    return frm.reload_doc();
                });
            },
        });
    }

    function documentActionsHtml(frm) {
        const printAllowed = canPrintCuttingPlan(frm);
        const exportAllowed = canExportDxf(frm);
        const uploadAllowed = canUploadDxf(frm);
        const blockReason = stageMutationBlockReason(frm);
        if (!printAllowed && !exportAllowed && !uploadAllowed && !blockReason) return "";
        return `
            <div class="dco-plan-document-actions">
                ${printAllowed
                    ? `<button type="button" class="btn btn-default btn-sm dco-print-cutting-plan">طباعة خطة القص</button>`
                    : ""}
                ${exportAllowed
                    ? `<button type="button" class="btn btn-default btn-sm dco-export-dxf">تصدير DXF لأوتوكاد</button>`
                    : ""}
                ${uploadAllowed
                    ? `<button type="button" class="btn btn-default btn-sm dco-upload-dxf-plan">${Boolean(frm.doc.production_dxf) ? "استبدال خطة القص DXF" : "رفع خطة قص كملف DXF"}</button>`
                    : ""}
            </div>
            ${blockReason
                ? `<div class="text-muted" style="font-size:12px;margin-top:8px;">${esc(__(blockReason))}</div>`
                : ""}
        `;
    }

    function renderActions(frm) {
        const field = frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;
        const mayMutate = canRecalculatePlan(frm);
        const mode = frm.doc.packing_mode || "Auto Pro";
        const blockReason = stageMutationBlockReason(frm);

        if (!mayMutate) {
            field.$wrapper.html(`
                <div class="dco-plan-actions-shell">
                    <div class="dco-plan-actions-title">
                        <strong>أوامر خطة القص</strong>
                        <span class="dco-plan-mode-hint">${esc(modeDescription(mode))}</span>
                    </div>
                    ${documentActionsHtml(frm)}
                    <div class="dco-plan-note">
                        ${blockReason
                            ? esc(__(blockReason))
                            : "الحقول مقفلة. اضغط «تعديل» قبل إعادة الحساب. بعد بدء القص تبقى الخطة التاريخية ثابتة."}
                    </div>
                </div>
            `);
            field.$wrapper.find(".dco-print-cutting-plan").on("click", () => printCuttingPlan(frm));
            field.$wrapper.find(".dco-export-dxf").on("click", () => exportCuttingPlanDxf(frm));
            field.$wrapper.find(".dco-upload-dxf-plan").on("click", () => uploadCuttingPlanDxf(frm));
            return;
        }

        field.$wrapper.html(`
            <div class="dco-plan-actions-shell">
                <div class="dco-plan-dirty-note">تم تغيير أحد إعدادات الخطة. أعد الحساب لتطبيق التغيير على الرسم والنتائج.</div>
                <div class="dco-plan-actions-title">
                    <strong>أوامر خطة القص</strong>
                    <span class="dco-plan-mode-hint">${esc(modeDescription(mode))}</span>
                </div>
                <div class="dco-plan-actions">
                    <button type="button" class="btn btn-primary btn-sm dco-recalculate-plan">
                        إعادة الحساب بالإعدادات الحالية
                    </button>
                    <button type="button" class="btn btn-default btn-sm dco-auto-pro-plan">
                        أفضل توزيع متقدم
                    </button>
                    <button type="button" class="btn btn-default btn-sm dco-deep-plan">
                        بحث معمق
                    </button>
                    <button type="button" class="btn btn-default btn-sm dco-optimal-plan">
                        بحث أمثل
                    </button>
                </div>
                ${documentActionsHtml(frm)}
                <div class="dco-plan-note">
                    غيّر طريقة ترتيب القطع من نفس المجموعة، ثم نفّذ الحساب مباشرة. إعادة الحساب تحدّث النتائج فقط ولا تعتمد الطلب.
                </div>
            </div>
        `);

        field.$wrapper.find(".dco-recalculate-plan").on("click", () => recalculate(frm));
        field.$wrapper.find(".dco-auto-pro-plan").on("click", async () => {
            if (!mayMutate) return;
            await frm.set_value("packing_mode", "Auto Pro");
            await recalculate(frm);
        });
        field.$wrapper.find(".dco-deep-plan").on("click", async () => {
            if (!mayMutate) return;
            await frm.set_value("packing_mode", "Deep Search");
            await recalculate(frm);
        });
        field.$wrapper.find(".dco-optimal-plan").on("click", async () => {
            if (!mayMutate) return;
            await frm.set_value("packing_mode", "Optimal Search");
            await recalculate(frm);
        });
        field.$wrapper.find(".dco-print-cutting-plan").on("click", () => printCuttingPlan(frm));
        field.$wrapper.find(".dco-export-dxf").on("click", () => exportCuttingPlanDxf(frm));
        field.$wrapper.find(".dco-upload-dxf-plan").on("click", () => uploadCuttingPlanDxf(frm));
    }

    async function recalculate(frm) {
        if (!canRecalculatePlan(frm)) {
            const reason = stageMutationBlockReason(frm);
            frappe.msgprint(reason || "فعّل وضع «تعديل» أولًا لإعادة حساب الخطة. إعادة الحساب لا تعتمد الطلب.");
            return;
        }

        const revisionUx = window.AlmdinaOrderRevisionUX;
        const wasEditing = Boolean(
            revisionUx && typeof revisionUx.captureEditSessionPresence === "function"
                ? revisionUx.captureEditSessionPresence(frm)
                : frm.__almdina_edit_session
        );

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
            const controls = window.AlmdinaPlanControlsUX;
            if (controls && typeof controls.runRecalculation === "function") {
                await controls.runRecalculation(frm);
            } else if (!window.AlmdinaBoardTextUX || !window.AlmdinaBoardTextUX.canCalculatePlan(frm)) {
                frappe.msgprint("أدخل صنف اللوح ومقاساته وقياسًا واحدًا صحيحًا على الأقل قبل حساب خطة القص.");
            } else {
                if (frm.is_dirty && frm.is_dirty()) {
                    await frm.save();
                }
                frappe.show_alert({ message: "تم تحديث خطة القص والنتائج", indicator: "green" }, 3);
            }
            renderSummary(frm);
            renderActions(frm);
            if (revisionUx && typeof revisionUx.restorePrimaryAfterPlanEngine === "function") {
                revisionUx.restorePrimaryAfterPlanEngine(frm, wasEditing);
            }
        } catch (error) {
            console.error("Failed to recalculate cutting plan", error);
            throw error;
        } finally {
            frappe.dom.unfreeze();
            buttons.prop("disabled", !canRecalculatePlan(frm));
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
        // The controls module remains the only owner of optimizer field access.
        if (!frm.fields_dict || !frm.fields_dict["packing_mode"]) return;
        const controls = window.AlmdinaPlanControlsUX;
        if (controls && typeof controls.applyOptimizerFieldAccess === "function") {
            controls.applyOptimizerFieldAccess(frm);
        }
    }

    function refreshPlanUX(frm) {
        installStyles();
        applyReadOnlyState(frm);
        decorateSections(frm);
        renderSummary(frm);
        renderActions(frm);
        return true;
    }

    function schedulePlanUX(frm) {
        const context = documentContext();
        const token = context && typeof context.capture === "function"
            ? context.capture(frm)
            : null;
        const run = () => {
            if (!context || context.isCurrent(frm, token)) {
                return refreshPlanUX(frm);
            }
            return false;
        };
        if (context && typeof context.ensureStageContext === "function") {
            return context.ensureStageContext(frm).then(run);
        }
        return Promise.resolve(run());
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedulePlanUX(frm); },
        refresh(frm) { schedulePlanUX(frm); },
        almdina_edit_session_changed(frm) { schedulePlanUX(frm); },
        refresh_plan_controls(frm) { schedulePlanUX(frm); },
        packing_mode(frm) { applyReadOnlyState(frm); renderActions(frm); markPending(frm); },
        cutting_machine_type(frm) { markPending(frm); },
        kerf_mm(frm) { markPending(frm); },
        trim_margin_mm(frm) { markPending(frm); },
        optimization_time_limit_sec(frm) { markPending(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        schedulePlanUX(frm);
    });

    window.addEventListener("almdina:stage-context-ready", (event) => {
        const frm = event.detail && event.detail.frm;
        if (frm && frm === window.cur_frm) schedulePlanUX(frm);
    });

    window.AlmdinaDoorCuttingPlanUX = Object.assign(
        window.AlmdinaDoorCuttingPlanUX || {},
        { refresh: schedulePlanUX }
    );
})();
