(() => {
    "use strict";

    if (window.AlmdinaPlanContextActionsUX) return;

    const STYLE_ID = "dco-plan-context-actions-css-v5";
    const LEGACY_STYLE_IDS = Object.freeze([
        "dco-plan-context-actions-css",
        "dco-plan-context-actions-css-v2",
        "dco-plan-context-actions-css-v3",
        "dco-plan-context-actions-css-v4",
    ]);
    const HOST_CLASS = "dco-plan-context-actions-host";
    const TAB_ROWS = Object.freeze({
        System: "system_draft",
        Custom: "uploaded_draft",
        BoardEditor: "board_editor_draft",
        Approved: "approved",
    });

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function can(frm, capability) {
        const owner = permissions();
        if (!owner) return false;
        if (typeof owner.canDocument === "function") {
            return Boolean(owner.canDocument(frm, capability));
        }
        return typeof owner.can === "function" && Boolean(owner.can(capability));
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function canMutateCurrentStage(frm) {
        const context = documentContext();
        if (context && typeof context.canMutateCurrentStage === "function") {
            return Boolean(context.canMutateCurrentStage(frm));
        }
        return Boolean(frm && frm.__almdina_actor_holds_stage_role);
    }

    function stateOwner() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function snapshot(frm) {
        const owner = stateOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function workspaceData(frm) {
        const state = snapshot(frm);
        const keeper = window.AlmdinaWorkspaceKeepPaint;
        if (keeper && typeof keeper.presentationData === "function") {
            return keeper.presentationData(state);
        }
        return state && state.status === "ready" ? state.data : null;
    }

    function workspaceCapabilities(frm) {
        return (workspaceData(frm) && workspaceData(frm).capabilities) || {};
    }

    function isEditing(frm) {
        const editor = window.AlmdinaPlanEditSessionUX;
        return Boolean(editor && typeof editor.isEditing === "function" && editor.isEditing(frm));
    }

    function activeTab(frm) {
        return String(frm.__almdina_active_plan_tab || "System");
    }

    function rowForTab(frm, tab = activeTab(frm)) {
        const data = workspaceData(frm);
        const plans = (data && data.plans) || {};
        return plans[TAB_ROWS[tab]] || null;
    }

    function parsePlan(row) {
        if (!row || !row.snapshot_json) return null;
        if (typeof row.snapshot_json === "object") return row.snapshot_json;
        try {
            return JSON.parse(row.snapshot_json || "{}");
        } catch (error) {
            return null;
        }
    }

    function rowHasPlan(row) {
        const plan = parsePlan(row);
        return Boolean(plan && Array.isArray(plan.sheets) && plan.sheets.length);
    }

    function isHistoricalRow(frm, row) {
        if (!row) return false;
        if (row.display_context) return row.display_context === "historical";
        const status = String(row.status || "");
        if (status === "Cancelled" || status === "Superseded") return true;
        if (status === "Approved") {
            return String(row.name || "") !== String((workspaceData(frm) || {}).approved_plan || "");
        }
        return status !== "Draft";
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        return String(message == null ? "" : message);
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    function uiButton(options) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.button !== "function") {
            throw new Error("AlmdinaUi.button is required for DCO plan context actions");
        }
        return ui.button(options);
    }

    function sourceLabel(tab) {
        if (tab === "Custom") return translate("Uploaded plan");
        if (tab === "Approved") return translate("Approved plan");
        if (tab === "BoardEditor") return translate("Edited plan");
        return translate("System plan");
    }

    function approveLabel(frm, tab) {
        const hasApproved = Boolean(String((workspaceData(frm) || {}).approved_plan || "").trim());
        if (!hasApproved) {
            if (tab === "Custom") return translate("Approve the uploaded plan");
            if (tab === "BoardEditor") return translate("Approve the edited plan");
            return translate("Approve the system plan");
        }
        if (tab === "Custom") {
            return translate("Replace the approved plan with the uploaded plan");
        }
        if (tab === "BoardEditor") {
            return translate("Replace the approved plan with the edited plan");
        }
        return translate("Replace the approved plan with the system plan");
    }

    function planMetrics(row) {
        const totals = (row && row.totals) || {};
        return {
            boards: Number(totals.required_boards || 0),
        };
    }

    function hasOperationalAccess(frm) {
        const routed = Boolean(String((frm.doc && frm.doc.production_path) || "").trim());
        // A delivered order is immutable even if stale stage context still exists.
        if (String((frm.doc && frm.doc.status) || "").trim() === "Delivered") return false;
        return !routed || canMutateCurrentStage(frm);
    }

    function hasApproveCapability(frm) {
        const caps = workspaceCapabilities(frm);
        return Boolean(caps.approve && can(frm, "approve_dxf"));
    }

    function approveDenialReason(frm, tab, row) {
        // Authorized operators get an explicit reason. Missing capability stays
        // silent and follows the same hide/disable policy as System/Uploaded.
        if (tab === "Approved" || !hasApproveCapability(frm)) return "";
        if (isEditing(frm)) {
            return translate("Save or cancel the plan settings edit before approval.");
        }
        if (!hasOperationalAccess(frm)) {
            const context = documentContext();
            const stageReason = context && typeof context.stageMutationBlockReason === "function"
                ? context.stageMutationBlockReason(frm)
                : "";
            const reason = stageReason
                || (String((frm.doc && frm.doc.status) || "").trim() === "Delivered"
                    ? "This delivered order can no longer change cutting plan approval."
                    : "Approval is unavailable in the current production stage.");
            return translate(reason);
        }
        if (!rowHasPlan(row)) {
            return tab === "BoardEditor"
                ? translate("There is no edited board-editor plan ready to approve.")
                : translate("There is no valid plan to approve in the current state.");
        }
        if (String(row.status || "") !== "Draft") {
            return translate("Only a draft cutting plan can be approved.");
        }
        if (row.manufacturing_blocked === true || row.can_approve === false) {
            const code = String(row.manufacturing_block_reason || "").trim();
            if (code === "board_editor_plan_not_ready") {
                return translate(
                    "This edited plan is not ready for approval or DXF export yet. Fix validation issues, then re-apply the layout."
                );
            }
            return translate("This edited plan cannot be approved or exported for a specific manufacturing reason.");
        }
        if (!row.validation || row.validation.status !== "Valid") {
            return translate("The cutting plan failed geometric validation and cannot be approved.");
        }
        if (row.validation.needs_recalculation) {
            return tab === "BoardEditor"
                ? translate("The order data changed. Re-apply the board-editor layout before approving the edited plan.")
                : tab === "Custom"
                    ? translate("The order data changed. Upload a new DXF that matches the current measurements, then approve the plan.")
                    : translate("Recalculate the cutting plan and review the new result before approval.");
        }
        return "";
    }

    function canApprove(frm, tab, row) {
        if (!hasApproveCapability(frm)) return false;
        if (row && row.can_approve === false) return false;
        if (row && row.manufacturing_blocked === true) return false;
        return Boolean(
            tab !== "Approved"
            && !isEditing(frm)
            && rowHasPlan(row)
            && hasOperationalAccess(frm)
            && String(row.status || "") === "Draft"
            && row.validation
            && row.validation.status === "Valid"
            && !row.validation.needs_recalculation
        );
    }

    function canCancelApproval(frm, tab) {
        const data = workspaceData(frm) || {};
        const caps = workspaceCapabilities(frm);
        return Boolean(
            tab === "Approved"
            && String(data.approved_plan || "").trim()
            && !isEditing(frm)
            && caps.approve
            && can(frm, "approve_dxf")
            && hasOperationalAccess(frm)
        );
    }

    function canPrint(frm, row) {
        const caps = workspaceCapabilities(frm);
        return Boolean(
            !isEditing(frm)
            && rowHasPlan(row)
            && caps.print
            && can(frm, "print_cutting_plan")
        );
    }

    function canOpenBoardEditor(frm, row) {
        const caps = workspaceCapabilities(frm);
        const tab = activeTab(frm);
        const tabCapability = tab === "Custom"
            ? "view_uploaded_cutting_plan"
            : tab === "Approved"
                ? "view_approved_cutting_plan"
                : "view_system_cutting_plan";
        const tabCapOk = tab === "Custom"
            ? caps.view_uploaded
            : tab === "Approved"
                ? caps.view_approved
                : caps.view_system;
        // Board Editor tab opens the selected Board Editor plan identity explicitly.
        const identityOk = tab === "BoardEditor"
            ? Boolean(row && String(row.name || "").trim() && rowHasPlan(row) && caps.view_system)
            : Boolean(
                row
                && String(row.name || "").trim()
                && rowHasPlan(row)
                && can(frm, tabCapability)
                && tabCapOk
            );
        return Boolean(
            !isEditing(frm)
            && identityOk
            && can(frm, "view_cutting_plan")
            && can(frm, "use_board_editor")
        );
    }

    let openBoardEditorGuardUntil = 0;

    function boardEditorAppPath(orderName, planName, options) {
        const segments = ["board-editor", String(orderName || "").trim(), String(planName || "").trim()];
        if (options && options.sourceOnly) segments.push("source");
        return `/app/${segments.map((part) => encodeURIComponent(part)).join("/")}`;
    }

    function boardEditorHref(orderName, planName, options) {
        const path = boardEditorAppPath(orderName, planName, options);
        if (window.frappe && frappe.urllib && typeof frappe.urllib.get_full_url === "function") {
            return frappe.urllib.get_full_url(path);
        }
        const origin = String((window.location && window.location.origin) || "").replace(/\/$/, "");
        return origin ? `${origin}${path}` : path;
    }

    function runOpenBoardEditor(frm, event) {
        const row = rowForTab(frm);
        if (!canOpenBoardEditor(frm, row)) {
            if (event && typeof event.preventDefault === "function") event.preventDefault();
            return false;
        }
        const orderName = String((frm.doc && frm.doc.name) || "").trim();
        // Prefer the selected row identity. For Edited plans that is the Board
        // Editor Cutting Plan itself; otherwise the visible source plan.
        const planName = String((row && row.name) || "").trim();
        if (!orderName || !planName) {
            if (event && typeof event.preventDefault === "function") event.preventDefault();
            return false;
        }
        const now = Date.now();
        if (now < openBoardEditorGuardUntil) {
            if (event && typeof event.preventDefault === "function") event.preventDefault();
            return false;
        }
        openBoardEditorGuardUntil = now + 500;
        const href = boardEditorHref(orderName, planName);
        // Keep the order form tab untouched: never frappe.set_route here.
        if (event && event.currentTarget && event.currentTarget.tagName === "A") {
            event.currentTarget.setAttribute("href", href);
            return true;
        }
        if (typeof window.open === "function") {
            const opened = window.open(href, "_blank", "noopener,noreferrer");
            if (opened) {
                try { opened.opener = null; } catch (err) { /* ignore */ }
            }
        }
        return true;
    }

    function canExport(frm, row) {
        const caps = workspaceCapabilities(frm);
        if (row && row.can_export === false) return false;
        if (row && row.manufacturing_blocked === true) return false;
        const archiveOnly = isHistoricalRow(frm, row)
            && String((row && row.source_type) || "") === "Uploaded DXF"
            && hasOriginalDxfFile(row)
            && preferOriginalUpload(frm, row);
        return Boolean(
            !isEditing(frm)
            && (!isHistoricalRow(frm, row) || archiveOnly)
            && (archiveOnly || rowHasPlan(row))
            && caps.export_dxf
            && can(frm, "export_dxf")
        );
    }

    function uploadedFile(frm) {
        const data = workspaceData(frm) || {};
        const uploaded = data.plans && data.plans.uploaded_draft;
        return String((uploaded && uploaded.dxf && uploaded.dxf.file) || "").trim();
    }

    function canUpload(frm) {
        const caps = workspaceCapabilities(frm);
        const replacing = Boolean(uploadedFile(frm));
        return Boolean(
            !isEditing(frm)
            && hasOperationalAccess(frm)
            && (replacing ? caps.replace_dxf : caps.upload_dxf)
            && can(frm, replacing ? "replace_dxf" : "upload_dxf")
        );
    }

    function toolIcon(kind) {
        const icons = {
            grid: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3.5" y="3.5" width="7" height="7" rx="1.2"></rect><rect x="13.5" y="3.5" width="7" height="7" rx="1.2"></rect><rect x="3.5" y="13.5" width="7" height="7" rx="1.2"></rect><rect x="13.5" y="13.5" width="7" height="7" rx="1.2"></rect></svg>',
            upload: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 16V5"></path><path d="M8 9l4-4 4 4"></path><path d="M5 19h14"></path></svg>',
            download: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 5v11"></path><path d="M8 12l4 4 4-4"></path><path d="M5 19h14"></path></svg>',
            printer: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 8V4h10v4"></path><path d="M7 16H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"></path><path d="M7 14h10v6H7z"></path></svg>',
            check: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 12.5l4.2 4.2L19 7"></path></svg>',
        };
        return icons[kind] || "";
    }

    function iconToolButton(options = {}) {
        const className = String(options.className || "").trim();
        const label = String(options.label || "").trim();
        const href = String(options.href || "").trim();
        const icon = toolIcon(options.icon);
        const disabled = options.disabled === true;
        const title = esc(label);
        if (href) {
            return `<a class="btn btn-default btn-sm dco-plan-tool-btn ${className}" href="${esc(href)}" target="_blank" rel="noopener noreferrer" title="${title}" aria-label="${title}"><span class="dco-plan-tool-btn__icon" aria-hidden="true">${icon}</span><span class="dco-plan-tool-btn__label">${esc(label)}</span></a>`;
        }
        return `<button type="button" class="btn btn-default btn-sm dco-plan-tool-btn ${className}"${disabled ? " disabled" : ""} title="${title}" aria-label="${title}"><span class="dco-plan-tool-btn__icon" aria-hidden="true">${icon}</span><span class="dco-plan-tool-btn__label">${esc(label)}</span></button>`;
    }

    function approveShortLabel(frm, tab) {
        const hasApproved = Boolean(String((workspaceData(frm) || {}).approved_plan || "").trim());
        return hasApproved ? translate("Replace") : translate("Approve");
    }

    function approveActionButton(frm, tab, disabled = false) {
        const full = approveLabel(frm, tab);
        const shortLabel = approveShortLabel(frm, tab);
        const markup = uiButton({
            label: "",
            variant: "success",
            size: "btn-sm",
            className: "dco-plan-context-approve",
            disabled: Boolean(disabled),
            attrs: {
                title: full,
                "aria-label": full,
            },
        });
        return markup.replace(
            "</button>",
            `<span class="dco-plan-context-approve__icon" aria-hidden="true">${toolIcon("check")}</span><span class="dco-plan-context-approve__label">${esc(shortLabel)}</span></button>`
        );
    }

    function installStyles() {
        LEGACY_STYLE_IDS.forEach((id) => {
            const legacy = document.getElementById(id);
            if (legacy) legacy.remove();
        });
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .${HOST_CLASS} {
                margin: 0;
                width: auto;
                min-width: 0;
                flex: 0 0 auto;
                direction: inherit;
            }
            .dco-plan-workspace-chrome {
                display:flex;
                flex-direction:column;
                gap:8px;
                width:100%;
                margin:0 0 var(--dco-section-stack-gap, 8px);
                box-sizing:border-box;
            }
            .dco-plan-workspace-title-row {
                display:flex;
                flex-wrap:wrap;
                align-items:center;
                gap:0;
                min-width:0;
            }
            .dco-plan-workspace-title {
                margin:8px 0 0 !important;
                font-size:15px !important;
                font-weight:850 !important;
                line-height:1.3 !important;
                color:var(--alm-text-strong, #101828) !important;
            }
            .dco-plan-workspace-title-meta {
                display:flex;
                flex-wrap:wrap;
                align-items:center;
                gap:6px 8px;
                width:100%;
                min-width:0;
            }
            .dco-plan-workspace-settings-slot {
                display:inline-flex;
                flex-wrap:wrap;
                align-items:center;
                gap:6px;
                flex:1 1 auto;
                min-width:0;
            }
            .dco-plan-workspace-meta-end {
                display:inline-flex;
                flex-wrap:wrap;
                align-items:center;
                justify-content:flex-end;
                gap:6px;
                margin-inline-start:auto;
                min-width:0;
            }
            .dco-plan-workspace-coverage-slot,
            .dco-plan-workspace-boards-slot,
            .dco-plan-workspace-status-meta {
                display:inline-flex;
                flex-wrap:wrap;
                align-items:center;
                gap:6px;
                min-width:0;
            }
            .dco-plan-workspace-control-row {
                display:flex;
                flex-wrap:wrap;
                align-items:center;
                gap:8px 12px;
                width:100%;
                min-width:0;
            }
            .dco-plan-workspace-control-row > .dco-plan-tabs {
                flex:1 1 14rem;
                min-width:0;
                margin:0 !important;
            }
            .dco-plan-context-bar {
                width:auto;
                max-width:100%;
                box-sizing:border-box;
                display:flex;
                align-items:center;
                justify-content:flex-end;
                gap:8px;
                flex-wrap:wrap;
                padding:0;
                border:0;
                border-radius:0;
                background:transparent;
                box-shadow:none;
            }
            .dco-plan-context-primary {
                display:flex;
                align-items:center;
                justify-content:flex-end;
                gap:6px;
                flex-wrap:wrap;
                flex:0 1 auto;
                min-width:0;
                width:auto;
            }
            .dco-plan-context-tools {
                display:inline-flex;
                align-items:center;
                gap:4px;
                flex-wrap:wrap;
            }
            .dco-plan-context-chip {
                display:inline-flex;
                align-items:center;
                min-height:26px;
                padding:3px 9px;
                border-radius:999px;
                background:var(--alm-surface-muted, #f4f6f8);
                border:1px solid var(--alm-card-border, var(--border-color,#e2e8f0));
                color:var(--alm-text-muted, var(--text-muted,#5f6b78));
                font-size:11px;
                font-weight:700;
                white-space:nowrap;
            }
            .dco-plan-context-chip.is-boards {
                margin-inline-start: 0;
                min-height:26px;
                padding:3px 10px;
                border-radius:999px;
                border:0;
                background:var(--alm-accent-soft, color-mix(in srgb, var(--alm-accent, #2563eb) 12%, transparent));
                color:var(--alm-accent, #2563eb);
                font-weight:800;
                gap:5px;
                box-shadow:none;
                cursor:default;
                pointer-events:none;
            }
            .dco-plan-context-boards-value {
                font-size:13px;
                line-height:1;
                font-weight:850;
            }
            .dco-plan-context-boards-label {
                font-size:11px;
                font-weight:750;
            }
            .dco-plan-context-chip.is-approved {
                background:var(--alm-success-soft, #ecfdf3);
                color:var(--alm-success, #166534);
                border-color:color-mix(in srgb, var(--alm-success, #166534) 28%, transparent);
            }
            .dco-plan-context-chip.is-blocked {
                max-width:min(100%, 42rem);
                white-space:normal;
                background:var(--alm-warning-soft, #fff7ed);
                color:var(--alm-warning-ink, #9a3412);
                border-color:color-mix(in srgb, var(--alm-warning-ink, #9a3412) 22%, transparent);
            }
            .dco-plan-context-bar .btn {
                min-height:36px;
                border-radius:var(--alm-radius-sm, 9px);
                font-weight:750;
                box-shadow:none;
            }
            .dco-plan-tool-btn {
                width:36px !important;
                min-width:36px !important;
                height:36px !important;
                min-height:36px !important;
                padding:0 !important;
                display:inline-flex !important;
                align-items:center !important;
                justify-content:center !important;
                border:1px solid var(--alm-card-border, #e4e8ee) !important;
                border-radius:var(--alm-radius-button, 8px) !important;
                background:var(--alm-surface-muted, #f4f6f8) !important;
                color:var(--alm-text-strong, #101828) !important;
            }
            .dco-plan-tool-btn:hover,
            .dco-plan-tool-btn:focus-visible {
                border-color:color-mix(in srgb, var(--alm-primary, #172033) 35%, transparent) !important;
                background:var(--alm-card, #fff) !important;
                color:var(--alm-primary, #172033) !important;
                outline:none;
                box-shadow:0 0 0 2px color-mix(in srgb, var(--alm-primary, #172033) 14%, transparent);
            }
            .dco-plan-tool-btn__icon {
                display:inline-flex;
                width:16px;
                height:16px;
                line-height:0;
            }
            .dco-plan-tool-btn__icon svg {
                display:block;
                width:16px;
                height:16px;
                fill:none;
                stroke:currentColor;
                stroke-width:1.8;
                stroke-linecap:round;
                stroke-linejoin:round;
                pointer-events:none;
            }
            .dco-plan-tool-btn__label {
                position:absolute;
                width:1px;
                height:1px;
                padding:0;
                margin:-1px;
                overflow:hidden;
                clip:rect(0,0,0,0);
                white-space:nowrap;
                border:0;
            }
            .dco-plan-context-primary .dco-plan-context-approve,
            .dco-plan-context-primary .dco-plan-context-cancel,
            .dco-plan-context-primary .alm-btn-success.dco-plan-context-approve {
                display:inline-flex;
                align-items:center;
                justify-content:center;
                gap:6px;
                flex:0 0 auto;
                min-width:0;
                min-height:36px;
                padding-inline:12px;
                text-align:center;
                line-height:1.2;
                white-space:nowrap;
            }
            .dco-plan-context-approve__icon {
                display:inline-flex;
                width:14px;
                height:14px;
                line-height:0;
            }
            .dco-plan-context-approve__icon svg {
                display:block;
                width:14px;
                height:14px;
                fill:none;
                stroke:currentColor;
                stroke-width:2;
                stroke-linecap:round;
                stroke-linejoin:round;
                pointer-events:none;
            }
            .dco-plan-context-cancel {
                margin-inline-start:8px;
                color:var(--alm-danger, #b42318);
                border-color:color-mix(in srgb, var(--alm-danger, #b42318) 35%, transparent);
                background:var(--alm-card, #fff);
            }
            .dco-plan-context-cancel:hover {
                background:var(--alm-danger-soft, #fff5f4);
                border-color:color-mix(in srgb, var(--alm-danger, #b42318) 55%, transparent);
            }
            [data-fieldname="plan_control_actions"] .dco-plan-document-actions,
            [data-fieldname="plan_control_actions"] .dco-approve-cutting-plan {
                display:none;
            }
            [data-fieldname="plan_control_actions"]:has(.dco-plan-settings-editor) {
                display:block;
            }
            @media (max-width:900px) {
                .dco-plan-workspace-control-row {
                    align-items:stretch;
                }
                .dco-plan-workspace-control-row > .dco-plan-tabs,
                .${HOST_CLASS},
                .dco-plan-context-bar,
                .dco-plan-context-primary {
                    width:100%;
                    justify-content:flex-start;
                }
                .dco-plan-workspace-meta-end {
                    margin-inline-start:0;
                    width:100%;
                    justify-content:flex-start;
                }
            }
            @media (max-width:767px) {
                .dco-plan-tool-btn {
                    width:40px !important;
                    min-width:40px !important;
                    height:40px !important;
                    min-height:40px !important;
                }
                .dco-plan-context-chip.is-boards {
                    margin-inline-start: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function syncLegacyActionSurface(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;
        const data = workspaceData(frm);
        const system = data && data.plans && data.plans.system_draft;
        const hasSystemDraft = Boolean(system && String(system.status || "") === "Draft");
        field.$wrapper.toggle(Boolean(isEditing(frm) || (data && !hasSystemDraft)));
    }

    function hostFor(frm) {
        const field = frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const wrapper = field && field.$wrapper;
        return wrapper && wrapper.length
            ? wrapper.find(`.${HOST_CLASS}`).first()
            : $();
    }

    async function refreshWorkspace(frm) {
        const owner = stateOwner();
        if (owner && typeof owner.load === "function") {
            await owner.load(frm, { force: true });
        }
        const adapter = window.AlmdinaPlanWorkspacePresenterAdapter;
        if (adapter && typeof adapter.project === "function") adapter.project(frm);
        const tabs = window.AlmdinaPlanTabsUX;
        if (tabs && typeof tabs.renderDualTabs === "function") tabs.renderDualTabs(frm);
    }

    async function runApproval(frm) {
        const controls = window.AlmdinaPlanControlsUX;
        if (!controls || typeof controls.runApproval !== "function") {
            frappe.msgprint(translate("Could not load the cutting plan approval command. Reload the page and try again."));
            return false;
        }
        return controls.runApproval(frm);
    }

    async function runCancelApproval(frm) {
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!api || typeof api.cancelApproval !== "function") {
            frappe.msgprint(translate("Could not load the command that cancels cutting plan approval. Reload the page and try again."));
            return false;
        }
        return new Promise((resolve) => {
            frappe.confirm(
                translate("The current production plan approval will be cancelled and kept in the revision history. The old plan will not become an editable draft. Do you want to continue?"),
                async () => {
                    try {
                        await api.cancelApproval(frm.doc.name);
                        frm.__almdina_active_plan_tab = "System";
                        await refreshWorkspace(frm);
                        frappe.show_alert({
                            message: translate("Cutting plan approval was cancelled and its history was kept."),
                            indicator: "green",
                        }, 5);
                        resolve(true);
                    } catch (error) {
                        console.error("Cutting plan approval cancellation failed", error);
                        resolve(false);
                    }
                },
                () => resolve(false)
            );
        });
    }

    function runPrint(frm) {
        const tabs = window.AlmdinaPlanTabsUX;
        if (!tabs || typeof tabs.printActivePlan !== "function") return false;
        tabs.printActivePlan(frm);
        return true;
    }

    function runExport(frm) {
        if (!frappe.almdina || typeof frappe.almdina.export_order_dxf !== "function") {
            frappe.msgprint(translate("Could not load the secure DXF export service."));
            return false;
        }
        const row = rowForTab(frm);
        return frappe.almdina.export_order_dxf(frm.doc.name, activeTab(frm), {
            archiveOnly: isHistoricalRow(frm, row),
            hasOriginalFile: hasOriginalDxfFile(row),
            originalIsManufacturingReady: originalIsManufacturingReady(row),
            preferOriginalUpload: preferOriginalUpload(frm, row),
            frm,
        });
    }

    function runUpload(frm) {
        if (!frappe.almdina || typeof frappe.almdina.upload_production_dxf !== "function") {
            frappe.msgprint(translate("Could not load the secure DXF upload service."));
            return false;
        }
        return frappe.almdina.upload_production_dxf(frm);
    }

    function primaryActionHtml(frm, tab, row) {
        if (tab === "Approved") {
            return `
                ${canCancelApproval(frm, tab)
                    ? uiButton({
                        label: translate("Cancel plan approval"),
                        variant: "secondary",
                        size: "btn-sm",
                        className: "dco-plan-context-cancel",
                        attrs: {
                            title: translate("Cancel plan approval"),
                            "aria-label": translate("Cancel plan approval"),
                        },
                    })
                    : ""}
            `;
        }
        const allowed = canApprove(frm, tab, row);
        if (allowed) {
            return approveActionButton(frm, tab, false);
        }
        // Capability holders see why approval is closed. Users without approve
        // capability keep the historical empty/silent surface.
        if (!hasApproveCapability(frm)) return "";
        if (!rowHasPlan(row) && tab !== "BoardEditor") return "";
        const reason = approveDenialReason(frm, tab, row);
        if (!reason) {
            return approveActionButton(frm, tab, true);
        }
        return `
            <span class="dco-plan-context-chip is-blocked" role="status">${esc(reason)}</span>
            ${rowHasPlan(row) ? approveActionButton(frm, tab, true) : ""}
        `;
    }

    function statusMetaHtml(frm, tab) {
        if (tab !== "Approved") return "";
        return `<span class="dco-plan-context-chip is-approved" role="status">${esc(translate("Plan approved for production"))}</span>`;
    }

    function hasOriginalDxfFile(row) {
        return Boolean(row && row.dxf && String(row.dxf.file || "").trim());
    }

    function originalIsManufacturingReady(row) {
        if (!hasOriginalDxfFile(row)) return false;
        const status = String((row.dxf && row.dxf.saw_center_status) || "Unknown").trim();
        if (status === "Absent") return false;
        return status === "Present" || status === "Legacy" || status === "Unknown";
    }

    function preferOriginalUpload(frm, row) {
        if (!row || !row.dxf) return true;
        if (Object.prototype.hasOwnProperty.call(row.dxf, "prefer_original_upload")) {
            return row.dxf.prefer_original_upload !== false;
        }
        // Fallback before workspace payload carries the server contract: only
        // the current approved upload with Absent saw centers regenerates.
        const approvedName = String((workspaceData(frm) || {}).approved_plan || "").trim();
        const isCurrentApproval = (
            String(row.status || "") === "Approved"
            && approvedName
            && String(row.name || "") === approvedName
        );
        if (isCurrentApproval && !originalIsManufacturingReady(row)) return false;
        return true;
    }

    function exportLabel(tab, row) {
        if (tab === "Custom" || (tab === "Approved" && hasOriginalDxfFile(row))) {
            return translate("Download uploaded DXF");
        }
        return translate("Export DXF");
    }

    function toolsHtml(frm, row) {
        const tab = activeTab(frm);
        const orderName = String((frm.doc && frm.doc.name) || "").trim();
        const planName = String((row && row.name) || "").trim();
        const boardEditor = canOpenBoardEditor(frm, row) && orderName && planName
            ? iconToolButton({
                className: "dco-open-board-editor",
                label: translate("Open board editor"),
                icon: "grid",
                href: boardEditorAppPath(orderName, planName),
            })
            : "";
        const print = canPrint(frm, row)
            ? iconToolButton({
                className: "dco-print-cutting-plan",
                label: translate("Print"),
                icon: "printer",
            })
            : "";
        const exportDxf = canExport(frm, row)
            ? iconToolButton({
                className: "dco-export-dxf",
                label: exportLabel(tab, row),
                icon: "download",
            })
            : "";
        // Upload is not an edit action for Board Editor copies.
        const upload = (tab !== "BoardEditor" && canUpload(frm))
            ? iconToolButton({
                className: "dco-upload-dxf-plan",
                label: uploadedFile(frm) ? translate("Replace the uploaded plan") : translate("Upload a DXF plan"),
                icon: "upload",
            })
            : "";
        return `${boardEditor}${upload}${exportDxf}${print}`;
    }

    function ensureMetaSlots(meta) {
        let settingsSlot = meta.querySelector(".dco-plan-workspace-settings-slot")
            || meta.querySelector('[data-role="settings-slot"]');
        let metaEnd = meta.querySelector(".dco-plan-workspace-meta-end")
            || meta.querySelector('[data-role="meta-end"]');
        let coverageSlot = meta.querySelector('[data-role="coverage-meta"]');
        let boardsSlot = meta.querySelector('[data-role="boards-meta"]');
        let statusSlot = meta.querySelector('[data-role="status-meta"]');

        if (!settingsSlot || !metaEnd || !coverageSlot || !boardsSlot || !statusSlot) {
            const existingSettings = settingsSlot;
            const existingCoverage = coverageSlot && coverageSlot.innerHTML
                ? coverageSlot.innerHTML
                : "";
            meta.innerHTML = "";
            settingsSlot = existingSettings || document.createElement("div");
            settingsSlot.className = "dco-plan-workspace-settings-slot";
            settingsSlot.setAttribute("data-role", "settings-slot");
            meta.appendChild(settingsSlot);

            metaEnd = document.createElement("div");
            metaEnd.className = "dco-plan-workspace-meta-end";
            metaEnd.setAttribute("data-role", "meta-end");
            meta.appendChild(metaEnd);

            coverageSlot = document.createElement("div");
            coverageSlot.className = "dco-plan-workspace-coverage-slot";
            coverageSlot.setAttribute("data-role", "coverage-meta");
            if (existingCoverage) coverageSlot.innerHTML = existingCoverage;
            metaEnd.appendChild(coverageSlot);

            boardsSlot = document.createElement("div");
            boardsSlot.className = "dco-plan-workspace-boards-slot";
            boardsSlot.setAttribute("data-role", "boards-meta");
            metaEnd.appendChild(boardsSlot);

            statusSlot = document.createElement("div");
            statusSlot.className = "dco-plan-workspace-status-meta";
            statusSlot.setAttribute("data-role", "status-meta");
            metaEnd.appendChild(statusSlot);
        }

        return { settingsSlot, coverageSlot, boardsSlot, statusSlot };
    }

    function syncWorkspaceMeta(frm, boardsChip, statusChip) {
        const root = formRoot(frm);
        const meta = root && root.querySelector
            ? root.querySelector(".dco-plan-workspace-title-meta")
            : null;
        if (!meta) return;

        const slots = ensureMetaSlots(meta);
        slots.boardsSlot.innerHTML = boardsChip || "";
        slots.statusSlot.innerHTML = statusChip || "";
        const settingsOwner = window.AlmdinaPlanSettingsSummaryUX;
        if (settingsOwner && typeof settingsOwner.schedule === "function") {
            settingsOwner.schedule(frm);
        }
        const contentOwner = window.AlmdinaPlanContentUX;
        if (contentOwner && typeof contentOwner.relocateSpecialCoverage === "function") {
            contentOwner.relocateSpecialCoverage(frm);
        }
    }

    function formRoot(frm) {
        const wrapper = frm && frm.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function render(frm, host) {
        installStyles();
        syncLegacyActionSurface(frm);
        const target = host && host.jquery ? host : $(host || []);
        if (!target.length) return false;

        const data = workspaceData(frm);
        if (!data) {
            target.empty();
            syncWorkspaceMeta(frm, "", "");
            return false;
        }

        const editing = isEditing(frm);
        if (editing) {
            target.empty();
            syncWorkspaceMeta(frm, "", "");
            return true;
        }

        const tab = activeTab(frm);
        const row = rowForTab(frm, tab);
        const metrics = planMetrics(row);
        const boardsChip = rowHasPlan(row)
            ? `<span class="dco-plan-context-chip is-boards" role="status" aria-label="${esc(translate("{0} sheets", [metrics.boards]))}"><span class="dco-plan-context-boards-value" style="direction:ltr;">${esc(metrics.boards)}</span><span class="dco-plan-context-boards-label">${esc(translate("Sheets"))}</span></span>`
            : `<span class="dco-plan-context-chip is-boards" role="status">${esc(sourceLabel(tab))}</span>`;
        const statusChip = statusMetaHtml(frm, tab);
        const inlineTools = toolsHtml(frm, row);

        // Tools stay compact next to approval. Boards/status chips live in the
        // workspace title meta so the board gallery can start sooner.
        // data-almdina-context-tools marks a completed normal-mode paint so surface
        // recovery can detect a wiped host even when every tool gate is false.
        target.html(`
            <div class="almdina-ui dco-plan-context-bar" dir="${esc(uiDirection())}" data-active-plan-source="${esc(tab)}" data-almdina-context-tools="1">
                <div class="dco-plan-context-primary">
                    ${primaryActionHtml(frm, tab, row)}
                    <div class="dco-plan-context-tools">${inlineTools}</div>
                </div>
            </div>
        `);
        syncWorkspaceMeta(frm, boardsChip, statusChip);

        target.find(".dco-plan-context-approve").off("click").on("click", () => runApproval(frm));
        target.find(".dco-plan-context-cancel").off("click").on("click", () => runCancelApproval(frm));
        target.find(".dco-open-board-editor").off("click").on("click", (event) => {
            runOpenBoardEditor(frm, event);
        });
        target.find(".dco-print-cutting-plan").off("click").on("click", () => runPrint(frm));
        target.find(".dco-export-dxf").off("click").on("click", () => runExport(frm));
        target.find(".dco-upload-dxf-plan").off("click").on("click", () => runUpload(frm));
        return true;
    }

    function refresh(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        syncLegacyActionSurface(frm);
        const host = hostFor(frm);
        if (host.length) return render(frm, host);

        // Host is recreated with tabs. Ask the tab owner to rebuild once when the
        // Plan surface should be visible but the context host is missing.
        const tabs = window.AlmdinaPlanTabsUX;
        if (
            tabs
            && typeof tabs.shouldShowPlanTabs === "function"
            && tabs.shouldShowPlanTabs(frm)
            && typeof tabs.afterRender === "function"
        ) {
            return Boolean(tabs.afterRender(frm));
        }
        return false;
    }

    frappe.ui.form.on("Door Cutting Order", {
        almdina_edit_session_changed(frm) { refresh(frm); },
        refresh_plan_controls(frm) { refresh(frm); },
    });

    [
        "almdina:plan-workspace-updated",
        "almdina:plan-selection-changed",
        "almdina:stage-context-ready",
        "almdina:permissions-updated",
    ].forEach((eventName) => {
        window.addEventListener(eventName, (event) => {
            const frm = eventName === "almdina:stage-context-ready"
                || eventName === "almdina:plan-selection-changed"
                ? event.detail && event.detail.frm
                : window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order" && frm === window.cur_frm) {
                refresh(frm);
            }
        });
    });

    window.AlmdinaPlanContextActionsUX = Object.freeze({
        activeTab,
        rowForTab,
        canApprove,
        canOpenBoardEditor,
        approveDenialReason,
        boardEditorAppPath,
        boardEditorHref,
        render,
        refresh,
        runApproval,
        runCancelApproval,
        runOpenBoardEditor,
        runPrint,
        runExport,
        runUpload,
        syncLegacyActionSurface,
    });
})();
