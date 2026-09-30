(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);

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
        if (document.getElementById("dco-fast-save-css")) return;
        $("head").append(`
            <style id="dco-fast-save-css">
                .dco-plan-stale-banner {
                    display:flex;
                    align-items:center;
                    gap:8px;
                    padding:6px 10px;
                    margin:0 0 6px;
                    border:1px solid #f0c36d;
                    border-radius:8px;
                    background:#fff8e6;
                    color:#6f4b00;
                    font-size:10.5px;
                    line-height:1.35;
                    font-weight:750;
                    white-space:nowrap;
                    overflow:hidden;
                    text-overflow:ellipsis;
                }
                .dco-plan-stale-banner.is-calculating {
                    border-color:color-mix(in srgb, var(--alm-primary, #172033) 32%, transparent);
                    background:color-mix(in srgb, var(--alm-primary, #172033) 8%, transparent);
                    color:#1d4f7a;
                }
                .dco-plan-stale-banner.is-stalled {
                    border-color:rgba(190,125,25,.4);
                    background:#fff3d8;
                }
                .dco-plan-stale-banner .icon {
                    flex:0 0 auto;
                    font-size:14px;
                    line-height:1;
                }
                .dco-plan-stale-banner .dco-plan-stale-copy {
                    min-width:0;
                    overflow:hidden;
                    text-overflow:ellipsis;
                    white-space:nowrap;
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
            frappe.msgprint(__("تعذر تثبيت تعديلات القياسات قبل حساب خطة القص. افتح الطلب للتعديل ثم حاول مرة أخرى."));
            return false;
        }

        const editPolicy = window.frappe && frappe.almdina;
        if (!editPolicy || typeof editPolicy.persistOrderEditCheckpoint !== "function") {
            frappe.msgprint(__("تعذر تثبيت تعديلات القياسات قبل حساب خطة القص. أعد تحميل الصفحة ثم حاول مرة أخرى."));
            return false;
        }

        frappe.show_alert({
            message: __("يتم حفظ تعديلات القياسات أولًا حتى لا تفقد عند إعادة حساب خطة القص."),
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

    function clearStaleBanners(wrapper) {
        wrapper.find(".dco-plan-stale-banner").remove();
        wrapper.find(".dco-plan-settings-editor__stale-copy").each(function resetCopy() {
            const node = $(this);
            node.text("").attr("hidden", "hidden");
        });
        wrapper.find(".dco-plan-settings-editor__action-bar")
            .removeClass("is-stale is-calculating is-stalled");
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
            const title = stalled
                ? __("حساب خطة القص ما زال في الانتظار")
                : __("جاري إعادة حساب خطة القص والتكلفة في الخلفية");
            const body = stalled
                ? __("الحفظ تم بنجاح، لكن العامل الخلفي لم يبدأ بعد. يمكنك متابعة العمل أو استخدام زر إعادة الحساب اليدوي.")
                : __("يمكنك متابعة العمل على الطلب. ستتحدث خطة القص والتكلفة تلقائيًا عند اكتمال الحساب.");
            const message = stalled ? title : `${title} — ${body}`;
            if (inEditLayout && renderEditActionBar(frm, wrapper, {
                calculating: true,
                stalled,
                message,
                editLayout: true,
            })) {
                return;
            }
            wrapper.prepend(`
                <div class="dco-plan-stale-banner is-calculating${stalled ? " is-stalled" : ""}" role="status" aria-live="polite">
                    <span class="icon">⏳</span>
                    <span class="dco-plan-stale-copy">${frappe.utils.escape_html(message)}</span>
                </div>`);
            return;
        }

        const stale = planIsStale(frm);
        if (inEditLayout) {
            const staleLine = stale
                ? __("⚡ تحتاج إعادة حساب")
                : "";
            renderEditActionBar(frm, wrapper, {
                stale,
                message: staleLine,
                editLayout: true,
            });
            if (stale) wrapper.find(".dco-plan-dirty-note").addClass("is-visible");
            return;
        }

        if (!stale) return;

        const staleLine = __("خطة القص تحتاج إعادة حساب — اضغط «إعادة الحساب بالإعدادات الحالية» بعد الانتهاء.");
        wrapper.prepend(`
            <div class="dco-plan-stale-banner">
                <span class="icon">⚡</span>
                <span class="dco-plan-stale-copy">${frappe.utils.escape_html(staleLine)}</span>
            </div>`);
        wrapper.find(".dco-plan-dirty-note").addClass("is-visible");
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
