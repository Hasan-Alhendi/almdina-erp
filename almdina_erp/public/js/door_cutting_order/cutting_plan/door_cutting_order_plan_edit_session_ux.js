(() => {
    "use strict";

    if (window.AlmdinaPlanEditSessionUX) return;

    const PLAN_SETTING_FIELDS = Object.freeze([
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ]);
    const PLAN_SETTING_SPECS = Object.freeze([
        Object.freeze({
            fieldname: "kerf_mm",
            label: "سماكة شفرة القص (مم)",
            shortLabel: "الشفرة",
            fieldtype: "Float",
            min: 0,
            step: "0.1",
            suffix: "مم",
        }),
        Object.freeze({
            fieldname: "trim_margin_mm",
            label: "هامش تشذيب اللوح",
            shortLabel: "التشذيب",
            fieldtype: "Float",
            min: 0,
            step: "0.1",
            suffix: "مم",
        }),
        Object.freeze({
            fieldname: "packing_mode",
            label: "خوارزمية توزيع القطع",
            shortLabel: "الخوارزمية",
            fieldtype: "Select",
            catalog: "optimization_catalog",
        }),
        Object.freeze({
            fieldname: "cutting_machine_type",
            label: "نوع آلة القص",
            shortLabel: "الآلة",
            fieldtype: "Select",
            catalog: "machine_type_catalog",
        }),
        Object.freeze({
            fieldname: "optimization_time_limit_sec",
            label: "مهلة التحسين",
            shortLabel: "المهلة",
            fieldtype: "Float",
            min: 0,
            step: "1",
            suffix: "ث",
        }),
    ]);
    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const ACTIVE_ROUTED_STATUSES = new Set([
        "At Sharyoun",
        "At Drawing",
        "At CNC",
        "At Sanding",
    ]);
    const BLOCKED_PLAN_ACTIONS = [
        // Preview/recalculation remains active while editing; all operations that
        // depend on a persisted plan stay suspended until Save/Cancel.
        ".dco-approve-cutting-plan",
        ".dco-print-cutting-plan",
        ".dco-export-dxf",
        ".dco-upload-dxf-plan",
    ].join(",");
    const ORIGINAL_DISABLED_ATTR = "data-almdina-plan-edit-original-disabled";
    const PHASE_DISABLED_ATTR = "data-almdina-plan-phase-original-disabled";
    const EDITOR_SELECTOR = ".dco-plan-settings-editor";
    const STYLE_ID = "almdina-plan-settings-editor-style-v4";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function stateOwner() {
        return window.AlmdinaPlanWorkspaceState || null;
    }

    function storeFor(frm) {
        const owner = stateOwner();
        return owner && typeof owner.storeFor === "function" ? owner.storeFor(frm) : null;
    }

    function workspaceSnapshot(frm) {
        const store = storeFor(frm);
        return store ? store.snapshot() : null;
    }

    function workspaceData(frm) {
        const state = workspaceSnapshot(frm);
        return state && state.status === "ready" && state.data ? state.data : null;
    }

    function catalogOptions(frm, catalogName, selectedValue) {
        const data = workspaceData(frm);
        const catalog = data && Array.isArray(data[catalogName]) ? data[catalogName] : [];
        const options = catalog
            .map((entry) => ({
                value: String(entry && entry.id || "").trim(),
                label: String(entry && entry.label || entry && entry.id || "").trim(),
                available: entry && entry.available !== false,
            }))
            .filter((entry) => entry.value);

        const selected = String(selectedValue ?? "").trim();
        if (selected && !options.some((entry) => entry.value === selected)) {
            options.push({
                value: selected,
                label: selected,
                available: true,
                compatibility: true,
            });
        }
        return options;
    }

    function planSettingSpecs(frm, values = {}) {
        return PLAN_SETTING_SPECS.map((spec) => {
            if (spec.fieldtype !== "Select") return spec;
            return {
                ...spec,
                options: catalogOptions(frm, spec.catalog, values[spec.fieldname]),
            };
        });
    }

    function approvedPlanName(frm) {
        const state = workspaceSnapshot(frm);
        if (!state || state.status !== "ready" || !state.data) return null;
        return String(state.data.approved_plan || "").trim();
    }

    function presenterAdapter() {
        return window.AlmdinaPlanWorkspacePresenterAdapter || null;
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function hasActiveProductionStage(frm) {
        return Boolean(String(
            (frm && frm.doc && frm.doc.current_production_stage) || ""
        ).trim());
    }

    function hasProductionRoute(frm) {
        return Boolean(
            hasActiveProductionStage(frm)
            || String((frm && frm.doc && frm.doc.production_path) || "").trim()
        );
    }

    function hasActiveRoutedLifecycle(frm) {
        if (hasActiveProductionStage(frm)) return true;
        const status = String((frm && frm.doc && frm.doc.status) || "").trim();
        return ACTIVE_ROUTED_STATUSES.has(status);
    }

    function isDrawingStage(frm) {
        if (!frm || !frm.doc) return false;
        const status = String(frm.doc.status || "").trim();
        const stageType = String(
            frm.__almdina_stage_type
            || (frm.__almdina_stage_context && frm.__almdina_stage_context.active_stage_type)
            || ""
        ).trim();
        return status === "At Drawing" || stageType === "Drawing";
    }

    function lifecycleAllowsEdit(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (frm.is_new && frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if ((frm.doc.revision_state || "Current") === "Superseded") return false;

        const approved = approvedPlanName(frm);
        if (approved === null) return false;

        const status = String(frm.doc.status || "Draft").trim();
        if (status === "Draft" && !hasActiveProductionStage(frm)) return true;

        if (approved && !isDrawingStage(frm)) return false;

        if (hasProductionRoute(frm)) return hasActiveRoutedLifecycle(frm);
        return DRAFT_LIKE.has(status);
    }

    function canEditPlanSettings(frm) {
        return Boolean(can(frm, "edit_optimizer_settings") && lifecycleAllowsEdit(frm));
    }

    function isEditing(frm) {
        const state = workspaceSnapshot(frm);
        return Boolean(state && state.editing);
    }

    function planSettingsMayWrite() {
        // Plan settings are edited only through the canonical Cutting Plan workspace.
        // Retired DCO plan fields must never be restored as mutable controls.
        return false;
    }

    function activeSettings(frm) {
        const adapter = presenterAdapter();
        if (adapter && typeof adapter.activeSettings === "function") {
            return adapter.activeSettings(frm);
        }
        const owner = stateOwner();
        const active = owner && typeof owner.activePlan === "function"
            ? owner.activePlan(frm, "System")
            : null;
        return active && active.settings ? { ...active.settings } : null;
    }

    function signalEditChanged(frm) {
        if (frm && typeof frm.trigger === "function") {
            frm.trigger("almdina_edit_session_changed");
        }
    }

    function refreshFieldAccess(frm) {
        const adapter = window.AlmdinaPlanFieldAccessAdapter;
        if (adapter && typeof adapter.apply === "function") adapter.apply(frm);
    }

    function actionSurface(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const wrapper = field && field.$wrapper;
        return wrapper && wrapper.length ? wrapper : null;
    }

    function planPhase(frm) {
        const coordinator = window.AlmdinaDcoEditSessionCoordinator;
        const state = coordinator && typeof coordinator.snapshot === "function"
            ? coordinator.snapshot(frm)
            : null;
        return state && state.activeKind === "plan" ? state.phase : null;
    }

    function draftCanChange(frm) {
        const coordinator = window.AlmdinaDcoEditSessionCoordinator;
        if (coordinator && typeof coordinator.snapshot === "function") {
            const state = coordinator.snapshot(frm);
            return state.activeKind === "plan" && state.phase === "editing";
        }
        return isEditing(frm);
    }

    function syncPhaseLocks(frm) {
        const wrapper = actionSurface(frm);
        if (!wrapper) return;
        const phase = planPhase(frm);
        const locked = phase === "starting" || phase === "saving" || phase === "cancelling";
        wrapper.find("[data-almdina-plan-setting], .dco-recalculate-plan").each((_, element) => {
            const control = $(element);
            if (locked) {
                if (control.attr(PHASE_DISABLED_ATTR) === undefined) {
                    control.attr(PHASE_DISABLED_ATTR, control.prop("disabled") ? "1" : "0");
                }
                control.prop("disabled", true).attr("aria-disabled", "true");
            } else {
                const original = control.attr(PHASE_DISABLED_ATTR);
                if (original === undefined) return;
                control.prop("disabled", original === "1")
                    .attr("aria-disabled", original === "1" ? "true" : "false")
                    .removeAttr(PHASE_DISABLED_ATTR);
            }
        });
    }

    function setPlanActionsSuspended(frm, suspended) {
        const wrapper = actionSurface(frm);
        if (!wrapper) return;
        wrapper.find(BLOCKED_PLAN_ACTIONS).each((_, element) => {
            const button = $(element);
            if (suspended) {
                if (button.attr(ORIGINAL_DISABLED_ATTR) === undefined) {
                    button.attr(ORIGINAL_DISABLED_ATTR, button.prop("disabled") ? "1" : "0");
                }
                button.prop("disabled", true).attr("aria-disabled", "true");
                return;
            }
            const original = button.attr(ORIGINAL_DISABLED_ATTR);
            if (original === undefined) return;
            button.prop("disabled", original === "1");
            button.attr("aria-disabled", original === "1" ? "true" : "false");
            button.removeAttr(ORIGINAL_DISABLED_ATTR);
        });
    }

    function translate(value) {
        const text = String(value ?? "");
        return typeof __ === "function" ? __(text) : text;
    }

    function escapeHtml(value) {
        if (frappe.utils && typeof frappe.utils.escape_html === "function") {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function installEditorStyles() {
        ["almdina-plan-settings-editor-style", STYLE_ID].forEach((id) => {
            if (id === STYLE_ID) return;
            const legacy = document.getElementById(id);
            if (legacy) legacy.remove();
        });
        let style = document.getElementById(STYLE_ID);
        if (!style) {
            style = document.createElement("style");
            style.id = STYLE_ID;
            document.head.appendChild(style);
        }
        style.textContent = `
            .dco-plan-settings-editor {
                margin: 0;
                padding: 6px 12px;
                border: 1px solid var(--alm-card-border, #e4e8ee);
                border-radius: var(--alm-radius-sm, 10px);
                background: var(--alm-card, #fff);
                box-shadow: none;
                direction: rtl;
                overflow: visible;
                width: 100%;
                box-sizing: border-box;
            }
            .dco-plan-settings-editor__sheet {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: 8px;
                width: 100%;
                border: 0;
                border-radius: 0;
                background: transparent;
                overflow-x: auto;
                box-shadow: none;
            }
            .dco-plan-settings-editor__settings-row {
                display: flex;
                flex: 1 1 auto;
                flex-wrap: nowrap;
                align-items: center;
                gap: 6px;
                padding: 0;
                min-width: 0;
            }
            .dco-plan-settings-editor__lead {
                display: none;
            }
            .dco-plan-settings-editor__icon {
                display: none;
            }
            .dco-plan-settings-editor__icon svg {
                width: 16px;
                height: 16px;
                display: block;
            }
            .dco-plan-settings-editor__grid {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: 6px;
                flex: 1 1 auto;
                min-width: 0;
                padding: 0;
            }
            .dco-plan-settings-editor__field {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                min-width: 0;
                min-height: 0;
                padding: 0;
                border: 0;
                border-radius: 0;
                background: transparent;
                box-shadow: none;
            }
            .dco-plan-settings-editor__field:first-child {
                padding-inline-start: 0;
            }
            .dco-plan-settings-editor__field label {
                margin: 0;
                margin-bottom: 0;
                font-size: 11px;
                font-weight: 700;
                color: var(--text-muted, #667085);
                white-space: nowrap;
            }
            .dco-plan-settings-editor__input-wrap {
                position: relative;
                flex: 0 1 auto;
                min-width: 0;
            }
            .dco-plan-settings-editor .form-control {
                width: auto;
                min-width: 3.25em;
                max-width: 9.5em;
                min-height: 28px;
                height: 28px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 700;
                border: 1px solid var(--border-color, #d0d5dd);
                border-radius: var(--alm-radius-button, 8px);
                background: var(--alm-card, #fff);
                box-shadow: none;
                text-align: start;
                color: var(--text-color, #1f272e);
            }
            .dco-plan-settings-editor select.form-control {
                min-width: 7em;
                max-width: 10.5em;
                padding-inline-end: 22px;
            }
            .dco-plan-settings-editor .form-control:focus {
                outline: none;
                border-color: var(--alm-accent, #2563eb);
                box-shadow: 0 0 0 2px color-mix(in srgb, var(--alm-accent, #2563eb) 16%, transparent);
            }
            .dco-plan-settings-editor__input-wrap.has-suffix .form-control {
                padding-inline-start: 26px;
                padding-inline-end: 8px;
            }
            .dco-plan-settings-editor__suffix {
                position: absolute;
                inset-inline-start: 8px;
                inset-inline-end: auto;
                top: 50%;
                transform: translateY(-50%);
                pointer-events: none;
                color: var(--text-muted, #667085);
                font-size: 10px;
                font-weight: 700;
            }
            .dco-plan-settings-editor__footer {
                flex: 0 0 auto;
                margin: 0;
                margin-inline-start: auto;
            }
            .dco-plan-settings-editor__action-bar,
            .dco-plan-settings-editor__action-bar.is-edit-layout,
            .dco-plan-settings-editor__action-bar.is-stale,
            .dco-plan-settings-editor__action-bar.is-calculating {
                display: flex;
                flex-direction: row;
                align-items: center;
                justify-content: flex-start;
                gap: 8px;
                padding: 0;
                border: 0;
                background: transparent;
                color: var(--alm-warning, #b45309);
                direction: ltr;
            }
            .dco-plan-settings-editor__stale-copy {
                flex: 0 1 auto;
                margin: 0;
                padding: 6px 12px;
                border: 1px solid #f0c36d;
                border-radius: 999px;
                background: var(--alm-warning-bg, #fff7e8);
                color: var(--alm-warning, #b45309);
                font-size: 12px;
                font-weight: 800;
                line-height: 1.4;
                white-space: nowrap;
            }
            .dco-plan-settings-editor__stale-copy[hidden] {
                display: none !important;
            }
            .dco-plan-settings-editor__recalc-slot {
                flex: 0 0 auto;
            }
            .dco-plan-settings-editor__recalc-btn.btn::before {
                content: "↻";
                margin-inline-end: 6px;
                font-size: 13px;
                line-height: 1;
            }
            .dco-plan-settings-editor__recalc-btn.btn {
                min-height: 36px;
                height: 36px;
                padding: 0 12px;
                line-height: 1;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 800;
                border-color: var(--alm-accent, #2563eb);
                background: var(--alm-accent, #2563eb);
                color: var(--alm-on-primary, #fff);
                white-space: nowrap;
                box-shadow: 0 3px 8px color-mix(in srgb, var(--alm-accent, #2563eb) 24%, transparent);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .dco-plan-settings-editor__recalc-btn.btn:disabled {
                opacity: 0.55;
            }
            [data-fieldname="plan_control_actions"]:has(.dco-plan-settings-editor) .dco-plan-actions-shell,
            [data-fieldname="plan_control_actions"]:has(.dco-plan-settings-editor) > .dco-plan-stale-banner {
                display: none !important;
            }
            @media (max-width: 575px) {
                .dco-plan-settings-editor__settings-row {
                    flex-direction: column;
                    align-items: stretch;
                }
                .dco-plan-settings-editor__footer {
                    margin-inline-start: 0;
                    width: 100%;
                }
                .dco-plan-settings-editor__action-bar {
                    flex-wrap: wrap;
                }
                .dco-plan-settings-editor__recalc-slot .btn {
                    width: 100%;
                }
            }
        `;
    }

    function selectOptions(spec, value) {
        return (spec.options || []).map((option) => {
            const selected = String(option.value) === String(value ?? "") ? " selected" : "";
            const disabled = option.available === false ? " disabled" : "";
            const suffix = option.available === false ? " — غير متاح حاليًا" : "";
            return `<option value="${escapeHtml(option.value)}"${selected}${disabled}>${escapeHtml(translate(option.label))}${escapeHtml(translate(suffix))}</option>`;
        }).join("");
    }

    function fieldMarkup(spec, value) {
        const fieldname = escapeHtml(spec.fieldname);
        const label = escapeHtml(translate(spec.shortLabel || spec.label));
        if (spec.fieldtype === "Select") {
            return `
                <div class="dco-plan-settings-editor__field" data-fieldname="${fieldname}">
                    <label for="dco-plan-setting-${fieldname}">${label}:</label>
                    <div class="dco-plan-settings-editor__input-wrap">
                        <select id="dco-plan-setting-${fieldname}" class="form-control" data-almdina-plan-setting="${fieldname}">
                            ${selectOptions(spec, value)}
                        </select>
                    </div>
                </div>
            `;
        }
        const suffix = spec.suffix ? escapeHtml(translate(spec.suffix)) : "";
        const inputClass = suffix ? "dco-plan-settings-editor__input-wrap has-suffix" : "dco-plan-settings-editor__input-wrap";
        return `
            <div class="dco-plan-settings-editor__field" data-fieldname="${fieldname}">
                <label for="dco-plan-setting-${fieldname}">${label}:</label>
                <div class="${inputClass}">
                    <input
                        id="dco-plan-setting-${fieldname}"
                        class="form-control"
                        type="number"
                        inputmode="decimal"
                        min="${escapeHtml(spec.min ?? 0)}"
                        step="${escapeHtml(spec.step || "any")}"
                        value="${escapeHtml(value ?? "")}"
                        data-almdina-plan-setting="${fieldname}"
                    >
                    ${suffix ? `<span class="dco-plan-settings-editor__suffix">${suffix}</span>` : ""}
                </div>
            </div>
        `;
    }

    function editorHost(frm) {
        return actionSurface(frm);
    }

    function markEditorDirty(host, dirty) {
        if (!host || !host.length) return;
        host.children(EDITOR_SELECTOR).first().toggleClass("is-dirty", Boolean(dirty));
    }

    function patchFromControl(store, control, frm) {
        if (!draftCanChange(frm)) return;
        const input = $(control);
        const fieldname = String(input.attr("data-almdina-plan-setting") || "");
        if (!PLAN_SETTING_FIELDS.includes(fieldname)) return;
        const state = store.snapshot();
        const spec = planSettingSpecs(frm, state && state.draft || {})
            .find((entry) => entry.fieldname === fieldname);
        if (!spec) return;
        const raw = input.val();
        const value = spec.fieldtype === "Float"
            ? (String(raw ?? "").trim() === "" ? null : Number(raw))
            : String(raw ?? "");
        store.patchDraft({ [fieldname]: value });
    }

    function preserveRecalculateButton(host) {
        const button = host.find(".dco-recalculate-plan").first();
        if (!button.length) return;
        const shell = host.children(".dco-plan-actions-shell").first();
        const target = shell.find(".dco-plan-actions").first();
        if (target.length) {
            target.append(button);
            return;
        }
        if (shell.length) {
            shell.append(button);
            return;
        }
        host.append(button);
    }

    function mountDraftControls(frm) {
        const store = storeFor(frm);
        const state = store && store.snapshot();
        const host = editorHost(frm);
        if (!store || !state || !state.editing || !host) return false;

        installEditorStyles();
        preserveRecalculateButton(host);
        host.children(EDITOR_SELECTOR).remove();
        const specs = planSettingSpecs(frm, state.draft || {});
        const fields = specs
            .map((spec) => fieldMarkup(spec, (state.draft || {})[spec.fieldname]))
            .join("");
        host.prepend(`
            <section class="dco-plan-settings-editor${state.dirty ? " is-dirty" : ""}" aria-label="${escapeHtml(translate("إعدادات خطة القص"))}">
                <div class="dco-plan-settings-editor__sheet">
                    <div class="dco-plan-settings-editor__settings-row">
                        <div class="dco-plan-settings-editor__lead">
                            <span class="dco-plan-settings-editor__icon" aria-hidden="true"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4.5h3.2M8.2 4.5h5.3M2.5 11.5h5.3M10.3 11.5h3.2"/><circle cx="7" cy="4.5" r="1.6"/><circle cx="9.2" cy="11.5" r="1.6"/></svg></span>
                            <span class="dco-plan-settings-editor__lead-text">${escapeHtml(translate("إعدادات القص"))}</span>
                        </div>
                        <div class="dco-plan-settings-editor__grid">${fields}</div>
                    </div>
                    <div class="dco-plan-settings-editor__footer">
                        <div class="dco-plan-settings-editor__action-bar is-edit-layout">
                            <div class="dco-plan-settings-editor__recalc-slot" data-role="recalc"></div>
                            <p class="dco-plan-settings-editor__stale-copy" data-role="stale" hidden></p>
                        </div>
                    </div>
                </div>
            </section>
        `);
        const editor = host.children(EDITOR_SELECTOR).first();
        editor.find("[data-almdina-plan-setting]")
            .off("input.almdinaPlanEdit change.almdinaPlanEdit")
            .on("input.almdinaPlanEdit change.almdinaPlanEdit", function onSettingChanged() {
                if (!draftCanChange(frm)) return;
                patchFromControl(store, this, frm);
                const current = store.snapshot();
                markEditorDirty(host, Boolean(current && current.dirty));
            });
        return true;
    }

    function syncEditorChrome(frm) {
        const host = editorHost(frm);
        if (!host || !isEditing(frm)) return;
        const editor = host.children(EDITOR_SELECTOR).first();
        if (!editor.length) return;

        const recalcSlot = editor.find('[data-role="recalc"]').first();
        const button = host.find(".dco-recalculate-plan").first();
        if (button.length && recalcSlot.length && !button.parent().is(recalcSlot)) {
            recalcSlot.append(button);
            button.addClass("dco-plan-settings-editor__recalc-btn");
        }

        const controls = window.AlmdinaPlanControlsUX;
        if (controls && typeof controls.refresh === "function") {
            controls.refresh(frm);
        } else if (button.length && typeof button.prop === "function") {
            button.prop("disabled", false);
        }

        const fastSave = window.AlmdinaFastSaveUX;
        if (fastSave && typeof fastSave.renderStaleState === "function") {
            fastSave.renderStaleState(frm);
        }
    }

    function unmountDraftControls(frm) {
        const wrapper = actionSurface(frm);
        if (wrapper) wrapper.children(EDITOR_SELECTOR).remove();
    }

    function focusDraftControl(frm, fieldname) {
        const host = editorHost(frm);
        if (!host) return false;
        const control = host.find(`[data-almdina-plan-setting="${fieldname}"]`).first();
        if (!control.length) return false;
        control.trigger("focus");
        if (control.is("input") && control[0] && typeof control[0].select === "function") {
            control[0].select();
        }
        return true;
    }

    function validateDraft(draft, frm = window.cur_frm) {
        const values = draft || {};
        for (const spec of planSettingSpecs(frm, values)) {
            const value = values[spec.fieldname];
            if (spec.fieldtype === "Select") {
                const normalized = String(value ?? "").trim();
                const selected = (spec.options || []).find((option) => option.value === normalized);
                if (!normalized || !selected || selected.available === false) {
                    return translate("يجب تحديد قيمة صالحة للحقل «{0}».").replace("{0}", translate(spec.label));
                }
                continue;
            }
            if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) {
                return translate("القيمة المدخلة في «{0}» غير صالحة.").replace("{0}", translate(spec.label));
            }
            if (Number(value) < Number(spec.min || 0)) {
                return translate("لا يمكن أن تكون قيمة «{0}» سالبة.").replace("{0}", translate(spec.label));
            }
        }
        return "";
    }

    function projectCurrent(frm) {
        const adapter = presenterAdapter();
        if (adapter && typeof adapter.project === "function") adapter.project(frm);
    }

    async function ensureLoaded(frm) {
        const owner = stateOwner();
        const state = workspaceSnapshot(frm);
        if (state && state.status === "ready") return state;
        if (!owner || typeof owner.load !== "function") return state;
        return owner.load(frm);
    }

    function sessionIsCurrent(frm, sessionContext) {
        if (!sessionContext) return window.cur_frm === frm;
        const coordinator = editSessionCoordinator();
        return Boolean(
            coordinator
            && typeof coordinator.isSessionCurrent === "function"
            && coordinator.isSessionCurrent(frm, sessionContext)
        );
    }

    function scheduleSessionFocus(frm, sessionContext, fieldname) {
        const context = documentContext();
        const focus = () => {
            if (sessionIsCurrent(frm, sessionContext)) focusDraftControl(frm, fieldname);
        };
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "plan-edit-session-focus", focus);
            return;
        }
        focus();
    }

    async function startEditing(frm, sessionContext = null) {
        if (!can(frm, "edit_optimizer_settings")) {
            frappe.msgprint(translate("لا تملك صلاحية تعديل إعدادات خطة القص."));
            return false;
        }
        if (frm.is_dirty && frm.is_dirty()) {
            frappe.msgprint(translate("احفظ أو ألغِ تعديلات الطلب الحالية قبل فتح تعديل إعدادات خطة القص."));
            return false;
        }

        await ensureLoaded(frm);
        if (!sessionIsCurrent(frm, sessionContext)) return false;
        if (!lifecycleAllowsEdit(frm)) {
            frappe.msgprint(translate("حالة الطلب الحالية لا تسمح بتعديل إعدادات خطة القص."));
            return false;
        }

        const store = storeFor(frm);
        const seed = activeSettings(frm);
        if (!store || !seed) {
            frappe.msgprint(translate("لا توجد خطة قص قابلة لتعديل الإعدادات حاليًا."));
            return false;
        }
        store.beginEdit(seed);
        refreshFieldAccess(frm);
        setPlanActionsSuspended(frm, true);
        signalEditChanged(frm);
        schedule(frm);
        scheduleSessionFocus(frm, sessionContext, "kerf_mm");
        return true;
    }

    async function cancelEditing(frm, sessionContext = null) {
        if (!sessionIsCurrent(frm, sessionContext)) return false;
        if (!isEditing(frm)) return false;
        const store = storeFor(frm);
        if (store) store.cancelEdit();
        unmountDraftControls(frm);
        setPlanActionsSuspended(frm, false);
        projectCurrent(frm);
        refreshFieldAccess(frm);
        signalEditChanged(frm);
        return true;
    }

    async function saveEditing(frm, sessionContext = null) {
        if (!sessionIsCurrent(frm, sessionContext)) return false;
        if (!isEditing(frm)) return false;
        if (!canEditPlanSettings(frm)) {
            await cancelEditing(frm, sessionContext);
            if (!sessionIsCurrent(frm, sessionContext)) return false;
            frappe.msgprint(translate("لم تعد حالة الطلب الحالية تسمح لك بتعديل إعدادات خطة القص."));
            return false;
        }

        const store = storeFor(frm);
        const state = store && store.snapshot();
        const api = window.AlmdinaPlanWorkspaceAPI;
        if (!store || !state || !api || typeof api.saveSettings !== "function") return false;

        const validationMessage = validateDraft(state.draft || {}, frm);
        if (validationMessage) {
            frappe.msgprint(validationMessage);
            const specs = planSettingSpecs(frm, state.draft || {});
            focusDraftControl(
                frm,
                specs.find((spec) => {
                    const value = (state.draft || {})[spec.fieldname];
                    if (spec.fieldtype === "Select") {
                        const selected = (spec.options || []).find(
                            (option) => option.value === String(value ?? "").trim()
                        );
                        return !selected || selected.available === false;
                    }
                    return value === null || value === undefined || value === ""
                        || !Number.isFinite(Number(value)) || Number(value) < Number(spec.min || 0);
                })?.fieldname || "kerf_mm"
            );
            return false;
        }

        if (state.dirty) {
            await api.saveSettings(frm.doc.name, state.draft || {});
            if (!sessionIsCurrent(frm, sessionContext)) return false;
        }

        unmountDraftControls(frm);
        setPlanActionsSuspended(frm, false);
        const owner = stateOwner();
        if (owner && typeof owner.load === "function") {
            await owner.load(frm, { force: true });
            if (!sessionIsCurrent(frm, sessionContext)) return false;
        } else {
            store.cancelEdit();
        }
        projectCurrent(frm);
        refreshFieldAccess(frm);
        signalEditChanged(frm);
        frappe.show_alert({
            message: translate("تم حفظ إعدادات خطة القص. أعد الحساب لتحديث النتيجة."),
            indicator: "green",
        }, 5);
        return true;
    }

    function syncEditPageScope(frm) {
        if (typeof document === "undefined" || !document.body || !document.body.classList) return;
        document.body.classList.toggle("dco-plan-settings-edit-active", Boolean(isEditing(frm)));
    }

    function sync(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        syncEditPageScope(frm);
        const visual = window.AlmdinaPlanCostWorkspaceVisualUX;
        if (visual && typeof visual.refresh === "function") {
            visual.refresh(frm);
        }
        if (["starting", "saving", "cancelling"].includes(planPhase(frm))) {
            syncPhaseLocks(frm);
            return;
        }
        if (isEditing(frm) && !canEditPlanSettings(frm)) {
            const coordinator = editSessionCoordinator();
            if (coordinator && typeof coordinator.activeKind === "function" && coordinator.activeKind(frm) === "plan") {
                coordinator.cancel(frm, "plan");
                return;
            }
            const store = storeFor(frm);
            if (store) store.cancelEdit();
            unmountDraftControls(frm);
            setPlanActionsSuspended(frm, false);
            refreshFieldAccess(frm);
            signalEditChanged(frm);
            return;
        }
        if (isEditing(frm)) {
            refreshFieldAccess(frm);
            mountDraftControls(frm);
            syncEditorChrome(frm);
            setPlanActionsSuspended(frm, true);
            syncPhaseLocks(frm);
            return;
        }
        syncPhaseLocks(frm);
        unmountDraftControls(frm);
        setPlanActionsSuspended(frm, false);
        projectCurrent(frm);
        refreshFieldAccess(frm);
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "plan-settings-edit-session", () => sync(frm));
            return;
        }
        // The DocumentContext is the normal runtime scheduler. Keep the
        // compatibility fallback synchronous so an unowned RAF cannot run
        // against a recycled form/session.
        if (window.cur_frm === frm) sync(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
    });

    [
        "almdina:permissions-updated",
        "almdina:stage-context-ready",
        "almdina:surfaces-settled",
        "almdina:plan-workspace-updated",
    ].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    function editSessionCoordinator() {
        return window.AlmdinaDcoEditSessionCoordinator || null;
    }

    function coordinated(command, frm, fallback) {
        const coordinator = editSessionCoordinator();
        if (!coordinator || typeof coordinator[command] !== "function") return fallback(frm);
        return coordinator[command](frm, "plan");
    }

    const coordinator = editSessionCoordinator();
    if (coordinator && typeof coordinator.register === "function") {
        coordinator.register("plan", {
            canStart: canEditPlanSettings,
            start: startEditing,
            save: saveEditing,
            cancel: cancelEditing,
            isDirty(frm) {
                const state = workspaceSnapshot(frm);
                return Boolean(state && state.dirty);
            },
        });
    }

    window.AlmdinaPlanEditSessionUX = Object.freeze({
        PLAN_SETTING_FIELDS,
        PLAN_SETTING_SPECS,
        planSettingSpecs,
        canEditPlanSettings,
        isEditing,
        planSettingsMayWrite,
        startEditing: frm => coordinated("start", frm, startEditing),
        cancelEditing: frm => coordinated("cancel", frm, cancelEditing),
        saveEditing: frm => coordinated("save", frm, saveEditing),
        validateDraft,
        draftCanChange,
        syncPhaseLocks,
        schedule,
    });
})();
