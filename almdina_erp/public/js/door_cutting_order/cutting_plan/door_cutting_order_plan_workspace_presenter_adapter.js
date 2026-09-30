(() => {
    "use strict";

    if (window.AlmdinaPlanWorkspacePresenterAdapter) return;

    function stateOwner() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function snapshot(frm) {
        const owner = stateOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function keepPaint() {
        return window.AlmdinaWorkspaceKeepPaint || null;
    }

    function data(frm) {
        const state = snapshot(frm);
        const keeper = keepPaint();
        if (keeper && typeof keeper.presentationData === "function") {
            return keeper.presentationData(state);
        }
        return state && state.status === "ready" ? state.data : null;
    }

    function canPresent(frm) {
        return Boolean(data(frm));
    }

    function ensureLoad(frm) {
        const owner = stateOwner();
        if (!owner || typeof owner.load !== "function") return Promise.resolve(null);
        return Promise.resolve(owner.load(frm)).catch(() => null);
    }

    function planRow(frm, tab) {
        const owner = stateOwner();
        return owner && typeof owner.planForTab === "function"
            ? owner.planForTab(frm, tab)
            : null;
    }

    function activeRow(frm) {
        const owner = stateOwner();
        return owner && typeof owner.displayedPlan === "function"
            ? owner.displayedPlan(frm)
            : null;
    }

    function presentationAssignments(row) {
        const offcut = row && row.offcut;
        const assignments = offcut && Array.isArray(offcut.assignments)
            ? offcut.assignments
            : [];
        return assignments.map(assignment => ({ ...assignment }));
    }

    function attachPresentationMetadata(plan, row) {
        if (!plan || typeof plan !== "object") return null;
        // Keep the canonical plan JSON serializable exactly as before. OFFCUT
        // labels belong to this transient read projection only, so attach them as
        // non-enumerable metadata on a shallow clone rather than extending the
        // persisted/signed snapshot shape.
        const projected = { ...plan };
        Object.defineProperty(projected, "__offcut_assignments", {
            value: presentationAssignments(row),
            enumerable: false,
            configurable: false,
            writable: false,
        });
        return projected;
    }

    function parseSnapshot(row) {
        if (!row) return null;
        const raw = row.snapshot_json;
        if (!raw) return null;
        if (typeof raw === "object") {
            return attachPresentationMetadata(raw, row);
        }
        try {
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object"
                ? attachPresentationMetadata(parsed, row)
                : null;
        } catch (error) {
            return null;
        }
    }

    function getPlanForTab(frm, tab) {
        return parseSnapshot(planRow(frm, tab));
    }

    function displayedPlanForTab(frm, tab) {
        const owner = stateOwner();
        return owner && typeof owner.displayedPlanForTab === "function"
            ? parseSnapshot(owner.displayedPlanForTab(frm, tab))
            : getPlanForTab(frm, tab);
    }

    function hasPlan(frm, tab) {
        const row = planRow(frm, tab);
        const plan = parseSnapshot(row);
        return Boolean(row && plan && Array.isArray(plan.sheets) && plan.sheets.length);
    }

    function hasApprovedPlan(frm) {
        const payload = data(frm);
        return Boolean(payload && String(payload.approved_plan || "").trim());
    }

    function sourceLabel(row) {
        return row && row.source_type === "Uploaded DXF" ? "Custom" : "System";
    }

    function activeSettings(frm) {
        const payload = data(frm);
        const editable = payload && payload.editable_settings;
        if (editable) return { ...editable };
        const row = activeRow(frm);
        return row && row.settings ? { ...row.settings } : null;
    }

    function legacySummaryProjection(row) {
        if (!row) return {};
        const totals = row.totals || {};
        const quality = row.quality || {};
        const validation = row.validation || {};
        const engine = row.engine || {};
        return {
            required_boards: Number(totals.required_boards || 0),
            used_area_m2: Number(totals.used_area_m2 || 0),
            total_source_area_m2: Number(totals.total_source_area_m2 || 0),
            waste_area_m2: Number(totals.waste_area_m2 || 0),
            waste_percent: Number(totals.waste_percent || 0),
            estimated_cut_count: Number(quality.estimated_cut_count || 0),
            estimated_cut_length_m: Number(quality.estimated_cut_length_m || 0),
            largest_reusable_free_area_m2: Number(quality.largest_reusable_free_area_m2 || 0),
            rotation_count: Number(quality.rotation_count || 0),
            packing_method: engine.method_label || engine.method_key || "",
            plan_needs_recalculation: validation.needs_recalculation ? 1 : 0,
        };
    }

    function previewOwnsSystemDisplay(frm) {
        const preview = window.AlmdinaPlanPreviewSession;
        if (!preview) return false;
        if (typeof preview.displayedPreviewRow === "function" && preview.displayedPreviewRow(frm)) {
            return true;
        }
        if (typeof preview.snapshot !== "function") return false;
        const state = preview.snapshot(frm);
        const status = String((state && state.status) || "idle");
        return status === "previewing" || status === "ready" || status === "saving";
    }

    function project(frm) {
        if (!frm || !frm.doc) return false;
        const payload = data(frm);
        if (!payload) return false;

        const systemRow = planRow(frm, "System");
        const customRow = planRow(frm, "Custom");
        const approvedRow = planRow(frm, "Approved");
        const currentRow = activeRow(frm);
        const systemPlan = parseSnapshot(systemRow);
        const customPlan = parseSnapshot(customRow);
        const approvedPlan = parseSnapshot(approvedRow);
        const displayedSystem = displayedPlanForTab(frm, "System");

        // Transitional read-only projection for legacy renderers. The source of
        // truth is the Plan workspace store; these assignments never save DCO.
        // While a preview owns System display, keep cutting_plan_json aligned with
        // the displayed projection so legacy readers cannot resurrect canonical
        // geometry over the preview the operator is reviewing.
        frm.doc.system_plan_json = systemPlan;
        frm.doc.cutting_plan_json = previewOwnsSystemDisplay(frm)
            ? (displayedSystem || systemPlan || parseSnapshot(currentRow))
            : (systemPlan || parseSnapshot(currentRow));
        frm.doc.custom_plan_json = customPlan;
        frm.doc.production_dxf = customRow && customRow.dxf ? customRow.dxf.file || null : null;
        const currentApproved = String(payload.approved_plan || "").trim();
        frm.doc.approved_plan = currentApproved || null;
        frm.doc.approved_plan_source = currentApproved ? sourceLabel(approvedRow) : null;
        frm.__almdina_approved_plan_snapshot = currentApproved ? approvedPlan : null;
        frm.__almdina_approved_plan_order = frm.doc.name;

        const editor = window.AlmdinaWorkspaceFieldEditor;
        if (editor && typeof editor.project === "function") {
            const settings = activeSettings(frm);
            if (settings) {
                editor.project(frm, settings, [
                    "packing_mode",
                    "cutting_machine_type",
                    "kerf_mm",
                    "trim_margin_mm",
                    "optimization_time_limit_sec",
                ]);
            }
            editor.project(frm, legacySummaryProjection(currentRow));
        }
        return true;
    }

    function pendingMessage(frm) {
        const state = snapshot(frm);
        if (state && state.status === "error") {
            return __("تعذر تحميل خطة القص. أعد المحاولة.");
        }
        return __("جاري تحميل خطة القص...");
    }

    function clearLegacySummary(frm) {
        const intro = frm && frm.fields_dict && frm.fields_dict.plan_controls_intro;
        const wrapper = intro && intro.$wrapper;
        if (!wrapper || !wrapper.length) return;
        wrapper.html(`
            <div class="dco-plan-workspace-state" style="padding:12px;text-align:center;color:var(--text-muted,#687481);">
                ${frappe.utils.escape_html(pendingMessage(frm))}
            </div>
        `);
    }

    function planLayoutWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.cutting_plan_html;
        return field && field.$wrapper && field.$wrapper.length ? field.$wrapper : null;
    }

    function hasMountedPlanSurface(frm) {
        const wrapper = planLayoutWrapper(frm);
        if (!wrapper) return false;
        return Boolean(
            (typeof wrapper.find === "function" && wrapper.find(".dco-plan-tab-content").length)
            || (typeof wrapper.find === "function" && wrapper.find(".dco-plan-context-actions-host").length)
        );
    }

    function syncBusy(frm) {
        const keeper = keepPaint();
        const wrapper = planLayoutWrapper(frm);
        if (!keeper || typeof keeper.markBusy !== "function" || !wrapper) return;
        keeper.markBusy(wrapper, keeper.isPresentationBusy(snapshot(frm)));
    }

    function renderPending(frm) {
        // Keep-last-paint: a reload that still owns retained workspace data must
        // not erase mounted tabs/context actions. First load / hard empty still
        // use the pending placeholder.
        if (canPresent(frm) && hasMountedPlanSurface(frm)) {
            syncBusy(frm);
            return true;
        }
        clearLegacySummary(frm);
        const wrapper = planLayoutWrapper(frm);
        if (!wrapper) return false;
        const orderName = String(frm && frm.doc && frm.doc.name || "");
        wrapper
            .attr("data-almdina-order", orderName)
            .html(`
                <div class="dco-plan-workspace-state" data-almdina-order="${frappe.utils.escape_html(orderName)}" style="padding:18px;text-align:center;color:var(--text-muted,#687481);border:1px dashed var(--border-color,#ccd3da);border-radius:12px;background:var(--subtle-fg,#fafafa);">
                    ${frappe.utils.escape_html(pendingMessage(frm))}
                </div>
            `);
        // Rendering is intentionally side-effect free. Form/document lifecycle
        // hooks own workspace loading through AlmdinaPlanWorkspaceState.schedule().
        return true;
    }

    function ready(frm) {
        const state = snapshot(frm);
        return Boolean(state && state.status === "ready" && state.data);
    }

    function paintPlanSurface(frm, legacyPainter) {
        project(frm);
        const painted = legacyPainter(frm);
        syncBusy(frm);
        return painted;
    }

    function install() {
        const legacy = window.AlmdinaPlanTabsUX;
        if (!legacy || legacy.__a52WorkspaceOwned) return false;

        const wrapped = {
            ...legacy,
            __a52WorkspaceOwned: true,
            hasCustomPlan(frm) {
                return hasPlan(frm, "Custom");
            },
            hasApprovedPlan,
            getPlanForTab,
            displayedPlanForTab,
            ensureApprovedPlanLoaded(frm) {
                return ensureLoad(frm).then(() => getPlanForTab(frm, "Approved"));
            },
            renderDualTabs(frm) {
                if (canPresent(frm)) {
                    return paintPlanSurface(frm, () => legacy.renderDualTabs(frm));
                }
                return renderPending(frm);
            },
            printActivePlan(frm) {
                if (!ready(frm)) {
                    ensureLoad(frm);
                    frappe.msgprint(__("انتظر حتى يكتمل تحميل خطة القص ثم أعد الطباعة."));
                    return false;
                }
                project(frm);
                return legacy.printActivePlan(frm);
            },
            afterRender(frm) {
                if (canPresent(frm)) {
                    return paintPlanSurface(frm, () => legacy.afterRender(frm));
                }
                return renderPending(frm);
            },
        };
        // This compatibility facade is intentionally decoratable. The later
        // action-permission guard wraps printActivePlan with the print capability
        // check. Freezing this object here caused a strict-mode TypeError on every
        // permission/DOM refresh and could interrupt the rest of the DCO UI cycle.
        window.AlmdinaPlanTabsUX = wrapped;
        return true;
    }

    function refreshCurrent() {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const tabs = window.AlmdinaPlanTabsUX;
        if (tabs && typeof tabs.renderDualTabs === "function" && tabs.shouldShowPlanTabs(frm)) {
            tabs.renderDualTabs(frm);
        }
    }

    window.addEventListener("almdina:plan-workspace-updated", refreshCurrent);

    window.AlmdinaPlanWorkspacePresenterAdapter = Object.freeze({
        install,
        project,
        parseSnapshot,
        getPlanForTab,
        hasApprovedPlan,
        activeSettings,
        ready,
        canPresent,
        renderPending,
    });

    install();
})();
