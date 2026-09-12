(() => {
    "use strict";

    if (window.AlmdinaDoorCuttingPlanUX) return;

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

    function planWorkspaceState() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function workspaceSnapshot(frm) {
        const owner = planWorkspaceState();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function workspaceData(frm) {
        const state = workspaceSnapshot(frm);
        return state && state.status === "ready" ? state.data : null;
    }

    function activePlanRow(frm) {
        const owner = planWorkspaceState();
        return owner && typeof owner.activePlan === "function"
            ? owner.activePlan(frm, "System")
            : null;
    }

    function activeSettings(frm) {
        const state = workspaceSnapshot(frm);
        if (state && state.editing && state.draft) return state.draft;
        const row = activePlanRow(frm);
        return row && row.settings ? row.settings : {};
    }

    function approvedPlanName(frm) {
        const data = workspaceData(frm);
        return String((data && data.approved_plan) || "").trim();
    }

    function uploadedDxfFile(frm) {
        const data = workspaceData(frm);
        const uploaded = data && data.plans && data.plans.uploaded_draft;
        return String((uploaded && uploaded.dxf && uploaded.dxf.file) || "").trim();
    }

    function workspaceReady(frm) {
        return Boolean(workspaceData(frm));
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
        if (!frm || frm.is_new() || !workspaceReady(frm)) return false;
        return uploadedDxfFile(frm)
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
        if (!frm || frm.is_new()) return false;
        const context = documentContext();
        if (context && typeof context.canTuneCuttingAlgorithm === "function") {
            return context.canTuneCuttingAlgorithm(frm);
        }
        const approved = approvedPlanName(frm);
        const status = String((frm.doc && frm.doc.status) || "Draft").trim();
        const preDispatchDraft = status === "Draft"
            && !String((frm.doc && frm.doc.current_production_stage) || "").trim();
        if (approved && !preDispatchDraft && status !== "At Drawing") return false;
        if (!canMutateCurrentStage(frm)) return false;
        if (frm.doc.current_production_stage) return true;
        return EDITABLE_STATUSES.has(frm.doc.status || "Draft");
    }

    function canOperatePlanEngine(frm) {
        // The plan engine answers to its own capability plus where the order
        // stands. It never waits for an order edit session.
        return workspaceReady(frm)
            && canTuneCuttingAlgorithm(frm)
            && can(frm, "recalculate_plan");
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

    function parsePlanRow(row) {
        if (!row || !row.snapshot_json) return {};
        if (typeof row.snapshot_json === "object") return row.snapshot_json || {};
        try {
            return JSON.parse(row.snapshot_json || "{}");
        } catch (error) {
            return {};
        }
    }

    function parsePlan(frm) {
        return parsePlanRow(activePlanRow(frm));
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
                .dco-plan-section-card .section-head { padding-top:14px !important; }
                .dco-plan-section-card .section-body { padding-bottom:12px !important; }
                .dco-cut-settings-card {
                    border-inline-start:4px solid #64748b !important;
                    background:linear-gradient(180deg,rgba(100,116,139,.035),transparent 42%) !important;
                }
                .dco-optimizer-card {
                    border-inline-start:4px solid var(--primary,#2490ef) !important;
                    background:linear-gradient(180deg,rgba(36,144,239,.045),transparent 46%) !important;
                }
                .dco-result-card { border-inline-start:4px solid #10b981 !important; }
                .dco-layout-card { border-inline-start:4px solid #0f172a !important; }
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
                .dco-offcut-policy {
                    margin-top:12px;
                    padding:14px;
                    border:1px solid rgba(217,119,6,.25);
                    border-radius:13px;
                    background:linear-gradient(180deg,rgba(251,191,36,.08),rgba(255,255,255,.35));
                    direction:rtl;
                }
                .dco-offcut-policy__header {
                    display:flex;
                    align-items:flex-start;
                    justify-content:space-between;
                    gap:12px;
                    margin-bottom:10px;
                }
                .dco-offcut-policy__title { margin:0;font-size:13px;font-weight:850; }
                .dco-offcut-policy__count {
                    flex:0 0 auto;
                    padding:4px 9px;
                    border-radius:999px;
                    background:rgba(217,119,6,.12);
                    color:#92400e;
                    font-size:10px;
                    font-weight:800;
                }
                .dco-offcut-policy__summary {
                    display:grid;
                    grid-template-columns:repeat(4,minmax(0,1fr));
                    gap:8px;
                }
                .dco-offcut-summary-item {
                    padding:9px 10px;
                    border:1px solid rgba(148,163,184,.2);
                    border-radius:10px;
                    background:var(--card-bg,#fff);
                }
                .dco-offcut-summary-item span { display:block;font-size:10px;color:var(--text-muted,#64748b); }
                .dco-offcut-summary-item strong { display:block;margin-top:3px;font-size:15px; }
                .dco-offcut-policy__pieces {
                    display:grid;
                    grid-template-columns:repeat(2,minmax(0,1fr));
                    gap:6px;
                    margin-top:10px;
                }
                .dco-offcut-piece-state {
                    display:flex;
                    justify-content:space-between;
                    gap:10px;
                    padding:7px 9px;
                    border-radius:9px;
                    background:rgba(248,250,252,.82);
                    font-size:11px;
                }
                .dco-offcut-piece-state strong { white-space:nowrap; }
                .dco-offcut-piece-state span { color:var(--text-muted,#64748b);text-align:left; }
                .dco-offcut-policy__action { margin-top:11px; }
                .dco-offcut-policy__action .btn { border-radius:9px;font-weight:800; }
                .dco-offcut-editor { direction:rtl; }
                .dco-offcut-editor__bulk {
                    display:grid;
                    grid-template-columns:minmax(0,1fr) auto;
                    gap:8px;
                    margin-bottom:12px;
                    padding:10px;
                    border-radius:11px;
                    background:var(--subtle-fg,#f8fafc);
                }
                .dco-offcut-editor__rows { display:grid;gap:8px;max-height:52vh;overflow:auto; }
                .dco-offcut-editor__row {
                    display:grid;
                    grid-template-columns:minmax(90px,.55fr) minmax(220px,1.45fr);
                    gap:10px;
                    align-items:center;
                    padding:9px 10px;
                    border:1px solid var(--border-color,#e2e8f0);
                    border-radius:10px;
                }
                .dco-offcut-editor__row label { margin:0;font-size:11px;font-weight:800; }
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
                    .dco-offcut-policy__summary { grid-template-columns:repeat(2,minmax(0,1fr)); }
                }
                @media (max-width:560px) {
                    .dco-plan-intro { grid-template-columns:1fr; }
                    .dco-plan-actions .btn { width:100%; }
                    .dco-plan-actions-shell { padding:10px; }
                    .dco-offcut-policy__pieces,
                    .dco-offcut-policy__summary { grid-template-columns:1fr; }
                    .dco-offcut-editor__bulk,
                    .dco-offcut-editor__row { grid-template-columns:1fr; }
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
        if (!workspaceReady(frm)) {
            field.$wrapper.empty();
            return;
        }

        const row = activePlanRow(frm) || {};
        const plan = parsePlan(frm);
        const metrics = row.quality || plan.industrial_metrics || {};
        const totals = row.totals || {};
        const engine = row.engine || {};
        const applied = engine.method_label || engine.method_key || "لم يتم الحساب بعد";
        const boards = Number(totals.required_boards || 0);
        const waste = Number(totals.waste_percent || 0);
        const reusable = Number(metrics.largest_reusable_free_area_m2 || 0);
        const cuts = Number(metrics.estimated_cut_count || 0);
        const cutLengthM = metrics.estimated_cut_length_m !== undefined
            ? Number(metrics.estimated_cut_length_m || 0)
            : Number(metrics.estimated_cut_length_cm || 0) / 100;
        const rotations = Number(metrics.rotation_count || 0);
        const attempts = Number(engine.attempts || plan.attempts || 0);
        const elapsed = Number(engine.elapsed_sec || plan.search_elapsed_sec || plan.solver_wall_time_sec || 0);
        const solver = engine.solver_status || plan.solver_status || "";

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
            return false;
        }
        if (window.AlmdinaPlanTabsUX && typeof window.AlmdinaPlanTabsUX.printActivePlan === "function") {
            window.AlmdinaPlanTabsUX.printActivePlan(frm);
            return true;
        }
        frappe.msgprint("تعذر تجهيز طباعة خطة القص. أعد تحميل الصفحة.");
        return false;
    }

    function exportCuttingPlanDxf(frm) {
        if (!canExportDxf(frm)) {
            frappe.msgprint(__(stageMutationBlockReason(frm) || "ليست لديك صلاحية تصدير DXF."));
            return false;
        }
        if (frappe.almdina && typeof frappe.almdina.export_order_dxf === "function") {
            return frappe.almdina.export_order_dxf(frm.doc.name);
        }
        frappe.msgprint("تعذر تشغيل مصدر DXF الآمن. أعد تحميل الصفحة.");
        return false;
    }

    function uploadCuttingPlanDxf(frm) {
        if (!canUploadDxf(frm)) {
            frappe.msgprint(__(
                stageMutationBlockReason(frm)
                || "ليست لديك صلاحية رفع خطة القص كملف DXF."
            ));
            return false;
        }
        if (frappe.almdina && typeof frappe.almdina.upload_production_dxf === "function") {
            return frappe.almdina.upload_production_dxf(frm);
        }
        // Fail closed: A2.2 requires DXF to be Private + Unattached before
        // authorization and geometry validation. Never fall back to a DCO-bound
        // FileUploader or attach first and validate later.
        frappe.msgprint(__("تعذر تحميل خدمة رفع DXF الآمنة. أعد تحميل الصفحة ثم حاول مرة أخرى."));
        return false;
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
                    ? `<button type="button" class="btn btn-default btn-sm dco-upload-dxf-plan">${uploadedDxfFile(frm) ? "استبدال خطة القص DXF" : "رفع خطة قص كملف DXF"}</button>`
                    : ""}
            </div>
            ${blockReason
                ? `<div class="text-muted" style="font-size:12px;margin-top:8px;">${esc(__(blockReason))}</div>`
                : ""}
        `;
    }

    function offcutPanelHtml(frm) {
        const plan = activePlanRow(frm);
        if (!plan) return "";
        const offcut = plan.offcut || {};
        const assignments = Array.isArray(offcut.assignments) ? offcut.assignments : [];
        if (!assignments.length) return "";
        const summary = Array.isArray(offcut.summary) ? offcut.summary : [];
        const editable = can(frm, "set_offcut_execution_owner");
        return `
            <section class="dco-offcut-policy" aria-label="حالة قطع النقص">
                <div class="dco-offcut-policy__header">
                    <div>
                        <h4 class="dco-offcut-policy__title">قطع النقص</h4>
                        <div class="text-muted" style="font-size:11px;margin-top:3px;">مصدر الفضلة ومكان التنفيذ لكل قطعة فعلية.</div>
                    </div>
                    <span class="dco-offcut-policy__count">${assignments.length} قطع</span>
                </div>
                <div class="dco-offcut-policy__summary">
                    ${summary.map(item => `
                        <div class="dco-offcut-summary-item">
                            <span>${esc(item.label)}</span>
                            <strong>${Number(item.count || 0)}</strong>
                        </div>
                    `).join("")}
                </div>
                <div class="dco-offcut-policy__pieces">
                ${assignments.map(item => `
                    <div class="dco-offcut-piece-state">
                        <strong>${esc(item.piece_label || item.piece_instance_id || "قطعة")}</strong>
                        <span>${esc(item.business_state_label)}</span>
                    </div>
                `).join("")}
                </div>
                ${editable ? `
                    <div class="dco-offcut-policy__action">
                        <button type="button" class="btn btn-primary btn-sm dco-open-offcut-editor">تحديد مصدر وتنفيذ قطع النقص</button>
                    </div>
                ` : ""}
            </section>
        `;
    }

    function offcutOptionHtml(options, selected) {
        return options.map(option => `
            <option value="${esc(option.value)}" ${option.value === selected ? "selected" : ""}>
                ${esc(option.label)}
            </option>
        `).join("");
    }

    async function reloadOffcutState(frm) {
        const owner = planWorkspaceState();
        if (!owner || typeof owner.load !== "function") return false;
        if (typeof owner.invalidate === "function") {
            owner.invalidate(frm, "offcut_classification_changed");
        }
        await owner.load(frm, { force: true });
        return true;
    }

    function openOffcutEditor(frm) {
        const plan = activePlanRow(frm);
        const offcut = plan && plan.offcut ? plan.offcut : {};
        const assignments = Array.isArray(offcut.assignments) ? offcut.assignments : [];
        const options = Array.isArray(offcut.state_options) ? offcut.state_options : [];
        if (!plan || !plan.name || !assignments.length || !options.length) return false;
        if (!can(frm, "set_offcut_execution_owner")) {
            frappe.msgprint(__("لا تملك صلاحية تحديد مصدر وتنفيذ قطع النقص."));
            return false;
        }

        const dialog = new frappe.ui.Dialog({
            title: __("تحديد مصدر وتنفيذ قطع النقص"),
            size: "large",
            fields: [{ fieldtype: "HTML", fieldname: "offcut_assignment_editor" }],
            primary_action_label: __("حفظ التصنيف"),
            primary_action: async () => {
                const api = window.AlmdinaPlanWorkspaceAPI;
                if (!api || typeof api.saveOffcutAssignments !== "function") {
                    frappe.msgprint(__("تعذر تحميل أمر حفظ تصنيف قطع النقص."));
                    return;
                }
                const rows = editor.find(".dco-offcut-editor__row").map(function () {
                    const row = $(this);
                    return {
                        piece_instance_id: row.attr("data-piece-instance-id"),
                        business_state: row.find(".dco-offcut-business-state").val(),
                    };
                }).get();
                dialog.get_primary_btn().prop("disabled", true);
                try {
                    await api.saveOffcutAssignments(plan.name, rows);
                    dialog.hide();
                    await reloadOffcutState(frm);
                    frappe.show_alert({
                        message: __("تم حفظ تصنيف قطع النقص."),
                        indicator: "green",
                    }, 4);
                } finally {
                    dialog.get_primary_btn().prop("disabled", false);
                }
            },
        });
        dialog.show();

        const editor = dialog.fields_dict.offcut_assignment_editor.$wrapper;
        editor.html(`
            <div class="dco-offcut-editor">
                <div class="dco-offcut-editor__bulk">
                    <select class="form-control input-sm dco-offcut-bulk-state" aria-label="تطبيق حالة على جميع قطع النقص">
                        ${offcutOptionHtml(options, "UNASSIGNED")}
                    </select>
                    <button type="button" class="btn btn-default btn-sm dco-apply-offcut-bulk">تطبيق على الكل</button>
                </div>
                <div class="dco-offcut-editor__rows">
                    ${assignments.map(item => `
                        <div class="dco-offcut-editor__row" data-piece-instance-id="${esc(item.piece_instance_id)}">
                            <label>${esc(item.piece_label || item.piece_instance_id || "قطعة")}</label>
                            <select class="form-control input-sm dco-offcut-business-state" aria-label="حالة قطعة النقص ${esc(item.piece_label || "")}">
                                ${offcutOptionHtml(options, item.business_state)}
                            </select>
                        </div>
                    `).join("")}
                </div>
            </div>
        `);
        editor.find(".dco-apply-offcut-bulk").on("click", () => {
            const selected = editor.find(".dco-offcut-bulk-state").val();
            editor.find(".dco-offcut-business-state").val(selected);
        });
        return true;
    }

    function bindOffcutPolicy(frm, field) {
        field.$wrapper.find(".dco-open-offcut-editor").off("click").on("click", () => {
            openOffcutEditor(frm);
        });
    }

    function renderActions(frm) {
        const field = frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;
        const wrapper = field.$wrapper;
        wrapper.children(".dco-plan-actions-shell").remove();
        if (!workspaceReady(frm)) return;

        const mayMutate = canRecalculatePlan(frm);
        const settings = activeSettings(frm);
        const mode = String(settings.packing_mode || "Auto Pro");
        const blockReason = stageMutationBlockReason(frm);

        wrapper.append(`
            <div class="dco-plan-actions-shell">
                <div class="dco-plan-dirty-note">تم تغيير أحد إعدادات الخطة. أعد الحساب لتطبيق التغيير على الرسم والنتائج.</div>
                <div class="dco-plan-actions-title">
                    <strong>أوامر خطة القص</strong>
                    <span class="dco-plan-mode-hint">${esc(modeDescription(mode))}</span>
                </div>
                ${mayMutate ? `
                    <div class="dco-plan-actions">
                        <button type="button" class="btn btn-primary btn-sm dco-recalculate-plan">
                            إعادة الحساب بالإعدادات الحالية
                        </button>
                    </div>
                ` : ""}
                ${documentActionsHtml(frm)}
                ${offcutPanelHtml(frm)}
                <div class="dco-plan-note">
                    ${blockReason
                        ? esc(__(blockReason))
                        : mayMutate
                            ? "عدّل إعدادات الخطة من «تعديل خطة القص»، احفظها، ثم أعد الحساب."
                            : "إعدادات الخطة للعرض فقط في الحالة الحالية."}
                </div>
            </div>
        `);

        const shell = wrapper.children(".dco-plan-actions-shell").last();
        shell.find(".dco-recalculate-plan").on("click", () => recalculate(frm));
        shell.find(".dco-print-cutting-plan").on("click", () => printCuttingPlan(frm));
        shell.find(".dco-export-dxf").on("click", () => exportCuttingPlanDxf(frm));
        shell.find(".dco-upload-dxf-plan").on("click", () => uploadCuttingPlanDxf(frm));
        bindOffcutPolicy(frm, { $wrapper: shell });
    }

    async function recalculate(frm) {
        if (!canRecalculatePlan(frm)) {
            const reason = stageMutationBlockReason(frm);
            frappe.msgprint(reason || "إعادة حساب الخطة غير متاحة في الحالة الحالية.");
            return false;
        }

        const controls = window.AlmdinaPlanControlsUX;
        if (!controls || typeof controls.runRecalculation !== "function") {
            // Fail closed instead of falling back to frm.save()/frm.call(). Plan
            // commands are owned by PlanControls + PlanWorkspaceAPI in A5.2.
            frappe.msgprint(__("تعذر تحميل أمر إعادة حساب خطة القص. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            return false;
        }
        return controls.runRecalculation(frm);
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

    function renderWorkspacePending(frm) {
        const adapter = window.AlmdinaPlanWorkspacePresenterAdapter;
        if (adapter && typeof adapter.renderPending === "function") {
            adapter.renderPending(frm);
        } else {
            const summary = frm.fields_dict.plan_controls_intro;
            const actions = frm.fields_dict.plan_control_actions;
            if (summary && summary.$wrapper) summary.$wrapper.empty();
            if (actions && actions.$wrapper) {
                actions.$wrapper.children(".dco-plan-actions-shell").remove();
            }
        }
    }

    function refreshPlanUX(frm) {
        installStyles();
        applyReadOnlyState(frm);
        decorateSections(frm);
        if (!workspaceReady(frm)) {
            renderWorkspacePending(frm);
            return false;
        }
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

    window.addEventListener("almdina:plan-workspace-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") schedulePlanUX(frm);
    });

    window.AlmdinaDoorCuttingPlanUX = Object.freeze({
        renderActions,
        refresh: schedulePlanUX,
    });
})();
