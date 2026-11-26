(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);

    function translateCopy(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        return String(message == null ? "" : message);
    }

    function editable(frm) {
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0 && EDITABLE_STATUSES.has(frm.doc.status || "Draft");
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    async function validateCurrentPlanInputs(frm) {
        const boardUX = window.AlmdinaBoardTextUX;
        if (boardUX && typeof boardUX.syncInputs === "function") {
            await boardUX.syncInputs(frm);
        }
        if (!boardUX || !boardUX.canCalculatePlan(frm)) return false;
        return true;
    }

    function installStyles() {
        if (document.getElementById("dco-fast-save-css-v2")) return;
        const legacy = document.getElementById("dco-fast-save-css");
        if (legacy && legacy.parentNode) legacy.parentNode.removeChild(legacy);
        $("head").append(`
            <style id="dco-fast-save-css-v2">
                .dco-plan-stale-banner.dco-plan-recalc-action-bar {
                    display:flex;
                    flex-wrap:wrap;
                    align-items:center;
                    justify-content:flex-start;
                    gap:8px 12px;
                    padding:6px 10px;
                    margin:0 0 6px;
                    border:1px solid var(--alm-status-warning-border, rgba(180, 83, 9, 0.24));
                    border-radius:var(--alm-radius-sm, 10px);
                    background:var(--alm-warning-bg, #fff7e8);
                    color:var(--alm-warning, #b45309);
                    font-size:var(--alm-font-size-sm, 12px);
                    line-height:var(--alm-line-height-tight, 1.35);
                    font-weight:var(--alm-font-weight-semibold, 600);
                    white-space:normal;
                    overflow:hidden;
                    box-sizing:border-box;
                    width:100%;
                    max-width:100%;
                }
                .dco-plan-stale-banner.is-calculating,
                .dco-plan-stale-banner.is-stalled {
                    border-color:var(--alm-status-warning-border, rgba(180, 83, 9, 0.28));
                    background:var(--alm-warning-bg, #fff7e8);
                    color:var(--alm-warning, #b45309);
                }
                .dco-plan-recalc-action-bar__lead {
                    display:flex;
                    align-items:center;
                    gap:8px;
                    min-width:0;
                    flex:1 1 12rem;
                }
                .dco-plan-recalc-action-bar__icon {
                    flex:0 0 auto;
                    display:inline-flex;
                    align-items:center;
                    justify-content:center;
                    width:1.15rem;
                    font-size:13px;
                    line-height:1;
                    color:inherit;
                }
                .dco-plan-recalc-action-bar__text {
                    display:flex;
                    flex-direction:column;
                    gap:1px;
                    min-width:0;
                    text-align:start;
                }
                .dco-plan-recalc-action-bar__title,
                .dco-plan-stale-banner .dco-plan-stale-copy {
                    min-width:0;
                    font-size:var(--alm-font-size-sm, 12px);
                    font-weight:var(--alm-font-weight-heavy, 800);
                    line-height:1.3;
                    color:var(--alm-warning, #b45309);
                    white-space:normal;
                }
                .dco-plan-recalc-action-bar__body {
                    font-size:11px;
                    font-weight:var(--alm-font-weight-semibold, 600);
                    line-height:1.35;
                    color:color-mix(in srgb, var(--alm-warning, #b45309) 82%, #000);
                    white-space:normal;
                }
                .dco-plan-recalc-action-bar__action {
                    display:flex;
                    align-items:center;
                    justify-content:flex-end;
                    flex:0 0 auto;
                    margin-inline-start:auto;
                    min-width:0;
                }
                .dco-plan-recalc-action-bar__action:empty {
                    display:none;
                }
                .dco-plan-recalc-action-bar .dco-plan-calculate-host {
                    margin:0 !important;
                    padding:0 !important;
                    width:auto !important;
                }
                @media (max-width:560px) {
                    .dco-plan-recalc-action-bar__action {
                        flex:1 1 100%;
                        justify-content:stretch;
                        margin-inline-start:0;
                    }
                    .dco-plan-recalc-action-bar .dco-plan-calculate-host {
                        width:100% !important;
                    }
                }
            </style>
        `);
    }

    function planIsStale(frm) {
        return Number(frm.doc.plan_needs_recalculation || 0) === 1 || !frm.doc.cutting_plan_json;
    }

    function invalidateEditSessionRecalculation(frm) {
        if (
            window.frappe
            && frappe.almdina
            && typeof frappe.almdina.invalidateOrderEditSessionRecalculation === "function"
        ) {
            frappe.almdina.invalidateOrderEditSessionRecalculation(frm);
        }
    }

    function markPlanStale(frm) {
        if (!frm || !frm.doc || frm.doc.approved_plan) return;
        frm.doc.plan_needs_recalculation = 1;
        invalidateEditSessionRecalculation(frm);
        renderStaleState(frm);
    }

    function markOrderInputPlanStale(frm) {
        if (!editable(frm)) return;
        // Recalculation receives optimizer values explicitly, while piece rows and
        // board inputs are loaded by the server from the persisted order. Track
        // only the latter so plan-only users never inherit order-edit requirements.
        frm.__almdina_pending_order_input_persistence = true;
        markPlanStale(frm);
    }

    function markOptimizerPlanStale(frm) {
        if (!can(frm, "edit_optimizer_settings")) return;
        // Optimizer values, including kerf and trim, are sent explicitly through
        // the focused recalculation command. They must never request a broad
        // Door Cutting Order save checkpoint from a plan-only user.
        markPlanStale(frm);
    }

    async function persistPendingOrderInputs(frm) {
        if (!frm || !frm.__almdina_pending_order_input_persistence) return true;
        const fastEntry = window.AlmdinaDoorCuttingFastEntry;
        if (fastEntry && typeof fastEntry.flush === "function") fastEntry.flush(frm);
        const dirty = Boolean(frm.is_dirty && frm.is_dirty());
        if (!dirty) {
            frm.__almdina_pending_order_input_persistence = false;
            return true;
        }
        if (!editable(frm)) {
            frappe.msgprint(translateCopy("Could not persist the measurement changes before calculating the cutting plan. Open the order for editing and try again."));
            return false;
        }

        const editPolicy = window.frappe && frappe.almdina;
        if (!editPolicy || typeof editPolicy.persistOrderEditCheckpoint !== "function") {
            frappe.msgprint(translateCopy("Could not persist the measurement changes before calculating the cutting plan. Reload the page and try again."));
            return false;
        }

        frappe.show_alert({
            message: translateCopy("Measurement changes are saved first so they are not lost when the cutting plan is recalculated."),
            indicator: "blue",
        }, 4);

        const saved = Boolean(await editPolicy.persistOrderEditCheckpoint(frm));
        if (saved) frm.__almdina_pending_order_input_persistence = false;
        return saved;
    }

    function backgroundJob(frm) {
        const owner = window.AlmdinaPlanRecalculationJob;
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function jobIsActive(frm) {
        const owner = window.AlmdinaPlanRecalculationJob;
        return Boolean(owner && typeof owner.isActive === "function" && owner.isActive(frm));
    }

    function planSettingsEditing(frm) {
        const owner = window.AlmdinaPlanEditSessionUX;
        return Boolean(owner && typeof owner.isEditing === "function" && owner.isEditing(frm));
    }

    function preserveCalculateHost(wrapper) {
        const host = wrapper.find(".dco-plan-calculate-host").first();
        if (!host.length) return;
        // Keep the single owned recalculate button alive across banner rebuilds.
        if (!host.parent().is(wrapper)) {
            wrapper.append(host);
        }
    }

    function clearStaleBanners(wrapper) {
        preserveCalculateHost(wrapper);
        wrapper.find(".dco-plan-stale-banner").remove();
        wrapper.find(".dco-plan-settings-editor__stale-copy").each(function resetCopy() {
            const node = $(this);
            node.text("").attr("hidden", "hidden");
        });
        wrapper.find(".dco-plan-settings-editor__action-bar")
            .removeClass("is-stale is-calculating is-stalled");
    }

    function hasSystemDraftPlan(frm) {
        const owner = window.AlmdinaPlanWorkspaceState;
        if (!owner || typeof owner.snapshot !== "function") return Boolean(frm.doc.cutting_plan_json);
        const state = owner.snapshot(frm);
        const plans = state && state.data && state.data.plans;
        const row = plans && plans.system_draft;
        if (!row) return false;
        if (typeof owner.isCurrentDraftRow === "function") {
            return Boolean(owner.isCurrentDraftRow(row));
        }
        return String(row.status || "") === "Draft";
    }

    function canRequestRecalculation(frm) {
        const controls = window.AlmdinaPlanControlsUX;
        if (controls && typeof controls.canCalculate === "function") {
            return Boolean(controls.canCalculate(frm));
        }
        return can(frm, "recalculate_plan");
    }

    function recalculationBlockReason(frm) {
        const controls = window.AlmdinaPlanControlsUX;
        if (controls && typeof controls.recalculationDisabledReason === "function") {
            // Controls already return stable English message ids for localization.
            return String(controls.recalculationDisabledReason(frm) || "").trim();
        }
        if (!can(frm, "recalculate_plan")) {
            return "You need the “Recalculate plan” permission to run the engine.";
        }
        return "";
    }

    function staleActionCopy(frm) {
        const firstPlan = !hasSystemDraftPlan(frm);
        const allowed = canRequestRecalculation(frm);
        const blocked = recalculationBlockReason(frm);

        if (firstPlan) {
            return {
                title: translateCopy("The cutting plan has not been calculated yet"),
                body: allowed
                    ? translateCopy("Start with “Calculate the cutting plan” using the current settings.")
                    : translateCopy(blocked || "You need the “Recalculate plan” permission to run the engine."),
            };
        }

        if (allowed) {
            return {
                title: translateCopy("The cutting plan needs recalculation"),
                body: translateCopy("Finish your changes, then recalculate with the current settings."),
            };
        }

        return {
            title: translateCopy("The cutting plan needs recalculation"),
            body: translateCopy(
                blocked
                || "Press “Edit” to try new settings, then recalculate to preview."
            ),
        };
    }

    function renderRecalcActionBar(wrapper, options = {}) {
        const title = String(options.title || "").trim();
        const body = String(options.body || "").trim();
        const icon = options.icon || "⚡";
        const classes = ["dco-plan-stale-banner", "dco-plan-recalc-action-bar"]
            .concat(options.extraClass ? [options.extraClass] : [])
            .join(" ");
        const bodyHtml = body
            ? `<span class="dco-plan-recalc-action-bar__body">${frappe.utils.escape_html(body)}</span>`
            : "";
        wrapper.prepend(`
            <div class="${classes}" role="status" aria-live="polite">
                <div class="dco-plan-recalc-action-bar__lead">
                    <span class="dco-plan-recalc-action-bar__icon" aria-hidden="true">${icon}</span>
                    <div class="dco-plan-recalc-action-bar__text">
                        <span class="dco-plan-recalc-action-bar__title dco-plan-stale-copy">${frappe.utils.escape_html(title)}</span>
                        ${bodyHtml}
                    </div>
                </div>
                <div class="dco-plan-recalc-action-bar__action" data-role="stale-recalc-slot"></div>
            </div>`);
    }

    function syncOwnedRecalculateButton(frm) {
        const controls = window.AlmdinaPlanControlsUX;
        if (controls && typeof controls.syncRecalculateButton === "function") {
            controls.syncRecalculateButton(frm);
        }
    }

    function renderEditActionBar(frm, wrapper, options = {}) {
        const editor = wrapper.find(".dco-plan-settings-editor").first();
        if (!editor.length) return false;

        const actionBar = editor.find(".dco-plan-settings-editor__action-bar").first();
        const copy = editor.find('[data-role="stale"]').first();
        if (!actionBar.length || !copy.length) return false;

        actionBar.removeClass("is-stale is-calculating is-stalled is-edit-layout");
        if (options.editLayout) {
            actionBar.addClass("is-edit-layout");
        }
        if (options.calculating) {
            actionBar.addClass(`is-calculating${options.stalled ? " is-stalled" : ""}`);
        } else         if (options.stale) {
            actionBar.addClass("is-stale");
        } else if (options.editLayout) {
            actionBar.addClass("is-stale");
        }

        if (options.message) {
            copy.text(options.message).removeAttr("hidden");
        } else {
            copy.text("").attr("hidden", "hidden");
        }
        return true;
    }

    function renderStaleState(frm) {
        installStyles();
        const planActions = frm.fields_dict && frm.fields_dict.plan_control_actions;
        if (!planActions || !planActions.$wrapper) return;

        const wrapper = planActions.$wrapper;
        clearStaleBanners(wrapper);

        const inEditLayout = planSettingsEditing(frm)
            && wrapper.find(".dco-plan-settings-editor").length;

        const job = backgroundJob(frm);
        if (jobIsActive(frm)) {
            const stalled = Boolean(job && job.stalled);
            const title = translateCopy(stalled
                ? "Cutting plan calculation is still waiting"
                : "Recalculating the cutting plan and cost in the background");
            const body = translateCopy(stalled
                ? "The save succeeded, but the background worker has not started yet. You can keep working or use manual recalculation."
                : "You can keep working on the order. The cutting plan and cost will update automatically when the calculation finishes.");
            if (inEditLayout && renderEditActionBar(frm, wrapper, {
                calculating: true,
                stalled,
                message: stalled ? title : translateCopy("{0} — {1}", [title, body]),
                editLayout: true,
            })) {
                syncOwnedRecalculateButton(frm);
                return;
            }
            renderRecalcActionBar(wrapper, {
                title,
                body,
                icon: "⏳",
                extraClass: `is-calculating${stalled ? " is-stalled" : ""}`,
            });
            syncOwnedRecalculateButton(frm);
            return;
        }

        const stale = planIsStale(frm);
        if (inEditLayout) {
            const staleLine = stale
                ? translateCopy("⚡ Recalculation needed")
                : "";
            renderEditActionBar(frm, wrapper, {
                stale,
                message: staleLine,
                editLayout: true,
            });
            if (stale) wrapper.find(".dco-plan-dirty-note").addClass("is-visible");
            syncOwnedRecalculateButton(frm);
            return;
        }

        if (!stale) {
            syncOwnedRecalculateButton(frm);
            return;
        }

        const copy = staleActionCopy(frm);
        renderRecalcActionBar(wrapper, {
            title: copy.title,
            body: copy.body,
            icon: "⚡",
        });
        wrapper.find(".dco-plan-dirty-note").addClass("is-visible");
        syncOwnedRecalculateButton(frm);
    }

    function schedule(frm) {
        installStyles();
        renderStaleState(frm);
        requestAnimationFrame(() => renderStaleState(frm));
        setTimeout(() => renderStaleState(frm), 180);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        after_save(frm) {
            if (!(frm.is_dirty && frm.is_dirty())) {
                frm.__almdina_pending_order_input_persistence = false;
            }
            schedule(frm);
        },
        board_description(frm) { markOrderInputPlanStale(frm); },
        board_length_cm(frm) { markOrderInputPlanStale(frm); },
        board_width_cm(frm) { markOrderInputPlanStale(frm); },
        default_edge_type(frm) { markOrderInputPlanStale(frm); },
        allow_piece_mirroring(frm) { markOrderInputPlanStale(frm); },
        kerf_mm(frm) { markOptimizerPlanStale(frm); },
        trim_margin_mm(frm) { markOptimizerPlanStale(frm); },
        packing_mode(frm) { markOptimizerPlanStale(frm); },
        cutting_machine_type(frm) { markOptimizerPlanStale(frm); },
        optimization_time_limit_sec(frm) { markOptimizerPlanStale(frm); },
        pieces_add(frm) { markOrderInputPlanStale(frm); },
        pieces_remove(frm) { markOrderInputPlanStale(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        width_cm(frm) { markOrderInputPlanStale(frm); },
        length_cm(frm) { markOrderInputPlanStale(frm); },
        qty(frm) { markOrderInputPlanStale(frm); },
        piece_type(frm) { markOrderInputPlanStale(frm); },
        allow_rotation(frm) { markOrderInputPlanStale(frm); },
        edge_long_right(frm) { markOrderInputPlanStale(frm); },
        edge_long_left(frm) { markOrderInputPlanStale(frm); },
        edge_width_top(frm) { markOrderInputPlanStale(frm); },
        edge_width_bottom(frm) { markOrderInputPlanStale(frm); },
        edge_break(frm) { markOrderInputPlanStale(frm); },
        edge_break_only(frm) { markOrderInputPlanStale(frm); },
        edge_long_right_type_override(frm) { markOrderInputPlanStale(frm); },
        edge_long_left_type_override(frm) { markOrderInputPlanStale(frm); },
        edge_width_top_type_override(frm) { markOrderInputPlanStale(frm); },
        edge_width_bottom_type_override(frm) { markOrderInputPlanStale(frm); },
    });

    window.addEventListener("almdina:plan-recalculation-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
    });

    window.AlmdinaFastSaveUX = Object.freeze({
        planIsStale,
        markOrderInputPlanStale,
        markOptimizerPlanStale,
        persistPendingOrderInputs,
        renderStaleState,
        validateCurrentPlanInputs,
    });
})();
