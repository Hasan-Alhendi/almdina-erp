(() => {
    "use strict";

    const DRAFT_LIKE = new Set(["Draft", "Pending Review", "Rejected"]);
    const TERMINAL = new Set(["Delivered", "Cancelled"]);
    const EDIT_LABEL = __("تعديل");
    const SAVE_LABEL = __("حفظ");
    const CONFIRM_EDIT_LABEL = __("اعتماد التعديل"); // legacy label removed from UI; kept for cleanup
    const ORDER_INPUT_FIELDS = [
        "customer",
        "order_date",
        "external_reference",
        "order_notes",
        "board_description",
        "board_length_cm",
        "board_width_cm",
        "default_edge_type",
        "edge_color",
        "cutting_cost_per_board_usd",
        "board_rate_usd",
        "kerf_mm",
        "trim_margin_mm",
    ];
    // Cut geometry follows the order edit session only — never optimizer tuning.
    const ORDER_CUT_GEOMETRY_FIELDS = [
        "kerf_mm",
        "trim_margin_mm",
    ];

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

    function revisionState(frm) {
        return (frm && frm.doc && frm.doc.revision_state) || "Current";
    }

    function sessionStore() {
        frappe.provide("frappe.almdina");
        if (!frappe.almdina._orderEditSessions) {
            frappe.almdina._orderEditSessions = Object.create(null);
        }
        return frappe.almdina._orderEditSessions;
    }

    function sessionEntry(name) {
        if (!name) return null;
        const store = sessionStore();
        const raw = store[name];
        if (!raw) return null;
        if (raw === true) {
            store[name] = { active: true, recalculated: false };
            return store[name];
        }
        return raw;
    }

    function currentOrderRouteName() {
        const route = (typeof frappe.get_route === "function" && frappe.get_route()) || [];
        if (route[0] !== "Form" || route[1] !== "Door Cutting Order" || !route[2]) {
            return null;
        }
        return route.slice(2).join("/");
    }

    function cachedOrderForm() {
        const page =
            frappe.views
            && frappe.views.formview
            && frappe.views.formview["Door Cutting Order"];
        return (page && page.frm) || null;
    }

    function isEditSessionActive(frm) {
        if (!frm || !frm.doc) return false;
        if (frm.is_new()) return true;
        // After leaving the form, the cached Form object must stay locked even if
        // a stale store entry still exists until the next hydrate pass.
        if (frm.__almdina_edit_session_abandoned) return false;
        if (frm.__almdina_edit_session) {
            const sessionOrder = frm.__almdina_edit_session_order;
            if (sessionOrder && sessionOrder !== frm.doc.name) return false;
            return true;
        }
        const entry = sessionEntry(frm.doc.name);
        return Boolean(entry && entry.active && entry.sticky);
    }

    function setEditSession(frm, active, options = {}) {
        if (!frm) return;
        const enabled = Boolean(active);
        frm.__almdina_edit_session = enabled;
        const name = frm.doc && frm.doc.name;
        if (enabled) {
            frm.__almdina_edit_session_abandoned = false;
            frm.__almdina_edit_session_order = name || null;
        } else {
            frm.__almdina_edit_session_order = null;
        }
        if (!name || frm.is_new()) {
            if (!enabled) {
                frm.__almdina_recalc_after_edit = false;
            }
            return;
        }
        if (enabled) {
            let recalculated = false;
            if (options.resetRecalc === true) {
                recalculated = false;
            } else if (options.recalculated === true) {
                recalculated = true;
            } else {
                const previous = sessionEntry(name);
                recalculated = Boolean(previous && previous.recalculated);
            }
            const previous = sessionEntry(name);
            sessionStore()[name] = {
                active: true,
                recalculated,
                // sticky survives one in-form save/reload only (plan checkpoint).
                sticky: options.sticky === true || Boolean(previous && previous.sticky),
            };
            frm.__almdina_recalc_after_edit = recalculated;
        } else {
            delete sessionStore()[name];
            frm.__almdina_recalc_after_edit = false;
        }
    }

    function abandonStoredEditSession(name, frm = null) {
        if (!name) return;
        delete sessionStore()[name];
        const targets = [];
        if (frm) targets.push(frm);
        const cached = cachedOrderForm();
        if (cached && targets.indexOf(cached) === -1) targets.push(cached);
        targets.forEach(target => {
            const sameDoc =
                (target.doc && target.doc.name === name)
                || target.docname === name
                || target.__almdina_edit_session_order === name;
            if (!sameDoc) return;
            target.__almdina_edit_session = false;
            target.__almdina_edit_session_order = null;
            target.__almdina_recalc_after_edit = false;
            target.__almdina_edit_session_abandoned = true;
        });
    }

    function shouldPreserveEditSessionAcrossNavigation(frm) {
        // In-form save/reload (plan checkpoint) must keep the session.
        // Leaving the form / switching documents must not.
        return Boolean(frm && frm.__almdina_preserve_edit_session_after_save);
    }

    function markEditSessionSticky(frm) {
        if (!frm || !frm.doc || !frm.doc.name || frm.is_new()) return;
        // Checkpoint sticky must never *open* an edit session. It only preserves
        // one that the user already started with «تعديل».
        if (
            !frm.__almdina_edit_session
            || frm.__almdina_edit_session_abandoned
            || frm.__almdina_edit_session_order !== frm.doc.name
        ) {
            return;
        }
        const entry = sessionEntry(frm.doc.name) || {
            active: true,
            recalculated: Boolean(frm.__almdina_recalc_after_edit),
        };
        entry.active = true;
        entry.sticky = true;
        entry.recalculated = Boolean(
            entry.recalculated || frm.__almdina_recalc_after_edit
        );
        sessionStore()[frm.doc.name] = entry;
        frm.__almdina_edit_session = true;
        frm.__almdina_edit_session_order = frm.doc.name;
        frm.__almdina_edit_session_abandoned = false;
    }

    function ensureLockedPrimaryAction(frm) {
        if (!frm || frm.is_new()) return;
        frm.__almdina_edit_session = false;
        frm.__almdina_edit_session_order = null;
        frm.__almdina_edit_session_abandoned = false;
        frm.__almdina_recalc_after_edit = false;
        const name = frm.doc && frm.doc.name;
        if (name) delete sessionStore()[name];
        applyEditableFields(frm);
        schedulePrimaryActionSync(frm);
    }

    function captureEditSessionPresence(frm) {
        return Boolean(
            frm
            && frm.doc
            && frm.__almdina_edit_session
            && !frm.__almdina_edit_session_abandoned
            && frm.__almdina_edit_session_order === frm.doc.name
        );
    }

    function restorePrimaryAfterPlanEngine(frm, wasEditing) {
        if (!frm) return;
        if (wasEditing) {
            schedulePrimaryActionSync(frm);
            return;
        }
        ensureLockedPrimaryAction(frm);
    }

    function hydrateEditSession(frm) {
        if (!frm || !frm.doc) return;
        if (frm.is_new()) {
            frm.__almdina_edit_session = true;
            frm.__almdina_edit_session_order = null;
            frm.__almdina_edit_session_abandoned = false;
            return;
        }

        const name = frm.doc.name;
        const entry = sessionEntry(name);

        // One-shot restore after an in-form checkpoint save/reload.
        if (entry && entry.active && entry.sticky) {
            frm.__almdina_edit_session = true;
            frm.__almdina_edit_session_order = name;
            frm.__almdina_edit_session_abandoned = false;
            frm.__almdina_recalc_after_edit = Boolean(entry.recalculated);
            entry.sticky = false;
            sessionStore()[name] = entry;
            return;
        }

        // Re-entry after leave: always start locked, even if the Form object was cached.
        if (frm.__almdina_edit_session_abandoned) {
            frm.__almdina_edit_session = false;
            frm.__almdina_edit_session_order = null;
            frm.__almdina_recalc_after_edit = false;
            delete sessionStore()[name];
            return;
        }

        // Same visit (user pressed تعديل and has not left this order).
        if (
            frm.__almdina_edit_session
            && frm.__almdina_edit_session_order === name
        ) {
            if (entry && entry.active) {
                frm.__almdina_recalc_after_edit = Boolean(entry.recalculated);
            }
            return;
        }

        frm.__almdina_edit_session = false;
        frm.__almdina_edit_session_order = null;
        frm.__almdina_recalc_after_edit = false;
        delete sessionStore()[name];
    }

    function abandonEditSessionsNotOnRoute() {
        const currentName = currentOrderRouteName();
        const frm = window.cur_frm;
        const preserving =
            Boolean(currentName)
            && frm
            && frm.doctype === "Door Cutting Order"
            && frm.doc
            && frm.doc.name === currentName
            && shouldPreserveEditSessionAcrossNavigation(frm);

        const store = sessionStore();
        Object.keys(store).forEach(name => {
            if (name === currentName) {
                if (preserving) return;
                if (store[name] && store[name].sticky) return;
                if (
                    frm
                    && frm.doc
                    && frm.doc.name === name
                    && frm.__almdina_edit_session
                    && !frm.__almdina_edit_session_abandoned
                ) {
                    return;
                }
                delete store[name];
                return;
            }
            abandonStoredEditSession(
                name,
                frm && frm.doc && frm.doc.name === name ? frm : null
            );
        });

        if (!currentName) {
            const cached = cachedOrderForm();
            if (!cached) return;
            const name = (cached.doc && cached.doc.name) || cached.docname;
            if (name) abandonStoredEditSession(name, cached);
        }
    }

    function installEditSessionAbandonGuard() {
        frappe.provide("frappe.almdina");
        if (frappe.almdina._editSessionAbandonGuardV2) return;
        frappe.almdina._editSessionAbandonGuardV2 = true;

        const syncFromRoute = () => abandonEditSessionsNotOnRoute();

        if (frappe.router && typeof frappe.router.on === "function") {
            frappe.router.on("change", syncFromRoute);
        }
        $(document).on("page-change", syncFromRoute);
        window.setTimeout(syncFromRoute, 0);

        $(document).on("form-unload", (_event, frm) => {
            if (!frm || frm.doctype !== "Door Cutting Order" || frm.is_new()) return;
            if (shouldPreserveEditSessionAcrossNavigation(frm)) return;
            const name = (frm.doc && frm.doc.name) || frm.docname;
            if (!name) return;
            abandonStoredEditSession(name, frm);
        });
    }

    function markEditSessionRecalculated(frm) {
        if (!frm || !frm.doc || !frm.doc.name || !isEditSessionActive(frm)) return;
        frm.__almdina_recalc_after_edit = true;
        const entry = sessionEntry(frm.doc.name) || { active: true, recalculated: false };
        entry.active = true;
        entry.recalculated = true;
        sessionStore()[frm.doc.name] = entry;
    }

    function invalidateEditSessionRecalculation(frm) {
        if (!frm || !isEditSessionActive(frm)) return;
        frm.__almdina_recalc_after_edit = false;
        frm.doc.plan_needs_recalculation = 1;
        const name = frm.doc && frm.doc.name;
        if (!name) return;
        const entry = sessionEntry(name) || { active: true, recalculated: false };
        entry.active = true;
        entry.recalculated = false;
        sessionStore()[name] = entry;
    }

    function editSessionRecalculated(frm) {
        if (frm && frm.__almdina_recalc_after_edit) return true;
        const entry = frm && frm.doc && sessionEntry(frm.doc.name);
        return Boolean(entry && entry.recalculated);
    }

    function canOfferEditSession(frm) {
        if (!frm || !frm.doc || frm.is_new()) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if (revisionState(frm) === "Superseded") return false;
        if (!can(frm, "edit_order")) return false;
        // In-place editing is Draft-only; other states need return-to-draft or a revision.
        return (frm.doc.status || "Draft") === "Draft";
    }

    function orderCanEdit(frm) {
        if (!frm || !frm.doc || Number(frm.doc.docstatus || 0) !== 0) return false;
        if (frm.is_new()) return can(frm, "create_order");
        return canOfferEditSession(frm) && isEditSessionActive(frm);
    }

    function canCreateRevision(frm) {
        if (!frm || frm.is_new() || !can(frm, "create_order_revision")) return false;
        const status = frm.doc.status || "Draft";
        if (DRAFT_LIKE.has(status) || TERMINAL.has(status)) return false;
        return revisionState(frm) !== "Superseded";
    }

    function installEditPolicy() {
        frappe.provide("frappe.almdina");
        frappe.almdina.orderCanEdit = orderCanEdit;
        frappe.almdina.isOrderEditSessionActive = isEditSessionActive;
        frappe.almdina.canOfferOrderEditSession = canOfferEditSession;
        frappe.almdina.markOrderEditSessionRecalculated = markEditSessionRecalculated;
        frappe.almdina.invalidateOrderEditSessionRecalculation = invalidateEditSessionRecalculation;
        frappe.almdina.lockOrderEditSession = lockEditSession;
        frappe.almdina.persistOrderEditCheckpoint = persistOrderEditCheckpoint;
    }

    function applyEditableFields(frm) {
        const editable = orderCanEdit(frm);
        frm.toggle_enable(ORDER_INPUT_FIELDS, editable);
        // Explicit read_only so kerf/trim never stay open after leaving optimizer
        // field control; they unlock only inside an active edit session.
        const desiredReadOnly = editable ? 0 : 1;
        ORDER_CUT_GEOMETRY_FIELDS.forEach((fieldname) => {
            const field = frm.fields_dict && frm.fields_dict[fieldname];
            if (!field || !field.df) return;
            if (Number(field.df.read_only || 0) !== desiredReadOnly) {
                frm.set_df_property(fieldname, "read_only", desiredReadOnly);
            }
        });
        syncPrimaryAction(frm);
    }

    function syncPrimaryAction(frm) {
        if (!frm || !frm.page) return;

        if (frm.is_new()) {
            frm.save_disabled = false;
            if (frm.toolbar && typeof frm.toolbar.set_primary_action === "function") {
                frm.toolbar.set_primary_action();
            } else if (typeof frm.enable_save === "function") {
                frm.enable_save();
            }
            return;
        }

        if (orderCanEdit(frm)) {
            frm.save_disabled = false;
            if (frm.toolbar) frm.toolbar.current_status = null;
            frm.page.clear_primary_action();
            frm.page.set_primary_action(SAVE_LABEL, () => commitEditSession(frm));
            return;
        }

        if (canOfferEditSession(frm)) {
            // Use disable_save() so Frappe's dirty/toolbar handlers cannot flip the
            // primary action back to native «حفظ» after plan recalculation.
            if (typeof frm.disable_save === "function") {
                frm.disable_save();
            } else {
                frm.save_disabled = true;
                frm.page.clear_primary_action();
            }
            if (frm.toolbar) frm.toolbar.current_status = null;
            frm.page.set_primary_action(EDIT_LABEL, () => enterEditSession(frm));
            return;
        }

        if (typeof frm.disable_save === "function") {
            frm.disable_save();
        } else {
            frm.save_disabled = true;
            frm.page.clear_primary_action();
        }
    }

    function schedulePrimaryActionSync(frm) {
        syncPrimaryAction(frm);
        window.requestAnimationFrame(() => syncPrimaryAction(frm));
        window.setTimeout(() => syncPrimaryAction(frm), 0);
        window.setTimeout(() => syncPrimaryAction(frm), 120);
        window.setTimeout(() => syncPrimaryAction(frm), 400);
    }

    function removeEditSessionButtons(frm) {
        frm.remove_custom_button(EDIT_LABEL);
        frm.remove_custom_button(CONFIRM_EDIT_LABEL);
        frm.remove_custom_button(EDIT_LABEL, __("دورة الطلب"));
        frm.remove_custom_button(CONFIRM_EDIT_LABEL, __("دورة الطلب"));
        frm.remove_custom_button(__("تعديل الطلب"));
        frm.remove_custom_button(__("تعديل الطلب"), __("دورة الطلب"));
        frm.remove_custom_button(SAVE_LABEL);
        frm.remove_custom_button(SAVE_LABEL, __("دورة الطلب"));
    }

    function refreshDependentUx(frm) {
        const field = frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        if (field && field.$wrapper) {
            field.$wrapper._dcoForceHtmlReplace = true;
        }
        if (typeof frm.trigger === "function") {
            frm.trigger("almdina_edit_session_changed");
            frm.trigger("refresh_plan_controls");
        }
        if (field && field.$wrapper) {
            field.$wrapper._dcoForceHtmlReplace = true;
        }
        if (
            window.AlmdinaDoorCuttingFastEntry
            && typeof window.AlmdinaDoorCuttingFastEntry.render === "function"
        ) {
            window.AlmdinaDoorCuttingFastEntry.render(frm);
        }
        if (window.AlmdinaDoorCuttingPlanUX && typeof window.AlmdinaDoorCuttingPlanUX.refresh === "function") {
            window.AlmdinaDoorCuttingPlanUX.refresh(frm);
        }
    }

    function enterEditSession(frm) {
        if (!canOfferEditSession(frm)) {
            frappe.msgprint(__("يمكن تعديل الطلب فقط وهو في حالة المسودة."));
            return;
        }
        setEditSession(frm, true, { resetRecalc: true });
        frm.doc.plan_needs_recalculation = 1;
        frm.__almdina_recalc_after_edit = false;
        applyEditableFields(frm);
        installEditSessionButtons(frm);
        schedulePrimaryActionSync(frm);
        refreshDependentUx(frm);
        frappe.show_alert({
            message: __("وضع التعديل مفعّل. عدّل الدرف والحقول، ثم اضغط «حفظ» لاعتماد التعديل وإعادة قفل الحقول."),
            indicator: "blue",
        }, 6);
    }

    function activateEditSessionQuietly(frm) {
        if (!frm || frm.is_new() || isEditSessionActive(frm)) {
            schedulePrimaryActionSync(frm);
            return Boolean(isEditSessionActive(frm));
        }
        if (!canOfferEditSession(frm)) return false;
        setEditSession(frm, true, { resetRecalc: false });
        applyEditableFields(frm);
        installEditSessionButtons(frm);
        schedulePrimaryActionSync(frm);
        refreshDependentUx(frm);
        return true;
    }

    function lockEditSession(frm, options = {}) {
        if (!frm || !isEditSessionActive(frm) || frm.is_new()) return false;
        setEditSession(frm, false);
        applyEditableFields(frm);
        installEditSessionButtons(frm);
        schedulePrimaryActionSync(frm);
        refreshDependentUx(frm);
        if (options.silent !== true) {
            frappe.show_alert({
                message: __("تم حفظ التعديل وإعادة قفل الحقول. اعتماد الطلب/الخطة للإنتاج يتم بزر منفصل إن لزم."),
                indicator: "green",
            }, 6);
        }
        return true;
    }

    async function flushPendingCostPriceEdits(frm) {
        const costUx = window.AlmdinaCostPermissionsUX;
        if (!costUx || typeof costUx.flushPendingPriceEdits !== "function") {
            return false;
        }
        return Boolean(await costUx.flushPendingPriceEdits(frm));
    }

    async function commitEditSession(frm) {
        if (!frm || frm.is_new()) {
            if (frm && typeof frm.save === "function") return frm.save();
            return;
        }
        if (!isEditSessionActive(frm)) {
            // Never call bare frm.save() on a clean doc — Frappe shows
            // "No changes in document" and confuses price/API workflows.
            if (frm.is_dirty && frm.is_dirty() && typeof frm.save === "function") {
                try {
                    await flushPendingCostPriceEdits(frm);
                } catch (error) {
                    console.error("Failed to flush pending piece prices", error);
                    return;
                }
                if (frm.is_dirty && frm.is_dirty()) {
                    return frm.save();
                }
            }
            return;
        }

        try {
            await flushPendingCostPriceEdits(frm);
        } catch (error) {
            console.error("Failed to flush pending piece prices", error);
            return;
        }

        // Price-only edits are persisted by the pricing APIs. Avoid frm.save()
        // when nothing else is dirty — that was causing the Save error.
        if (frm.is_dirty && frm.is_dirty()) {
            frm.__almdina_lock_after_save = true;
            return frm.save();
        }
        lockEditSession(frm);
    }

    async function persistOrderEditCheckpoint(frm) {
        if (!frm || frm.is_new() || !orderCanEdit(frm)) return false;
        if (!(frm.is_dirty && frm.is_dirty())) return true;
        if (typeof frm.save !== "function") return false;

        // Plan recalculation needs current piece rows in the database, but this
        // automatic checkpoint must not mean "finish editing". The ordinary Save
        // button still locks the session; only this explicit internal checkpoint
        // preserves it across the save/reload cycle.
        await flushPendingCostPriceEdits(frm);
        if (!(frm.is_dirty && frm.is_dirty())) return true;
        markEditSessionSticky(frm);
        frm.__almdina_preserve_edit_session_after_save = true;
        try {
            await frm.save();
        } finally {
            frm.__almdina_preserve_edit_session_after_save = false;
        }
        return !(frm.is_dirty && frm.is_dirty());
    }

    function confirmEditSession(frm) {
        return lockEditSession(frm);
    }

    function installEditSessionButtons(frm) {
        removeEditSessionButtons(frm);
    }

    function renderRevisionState(frm) {
        const state = revisionState(frm);
        if (state === "Pending Activation") {
            frm.set_intro(
                __("هذه نسخة تعديل غير مفعّلة. يمكن تجهيزها ومراجعتها، لكنها لن تُرسل للإنتاج قبل اعتمادها واستبدال النسخة السابقة بأمان."),
                "orange"
            );
            return;
        }
        if (state === "Superseded") {
            frm.set_intro(
                __("هذه نسخة تاريخية تم استبدالها بنسخة أحدث، وهي للقراءة والتوثيق فقط."),
                "red"
            );
            return;
        }
        if (frm.doc.revision_of) {
            frm.set_intro(
                __("هذه هي النسخة الحالية ضمن سلسلة مراجعات الطلب."),
                "green"
            );
            return;
        }
        if (
            canOfferEditSession(frm)
            && !isEditSessionActive(frm)
            && !DRAFT_LIKE.has(frm.doc.status || "Draft")
        ) {
            frm.set_intro(
                __("الحقول مقفلة. اضغط «تعديل» لفتح الحقول، ثم «حفظ» لاعتماد التعديل وإعادة القفل."),
                "blue"
            );
        }
    }

    function createRevision(frm, reason = "") {
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision",
            args: {
                order_name: frm.doc.name,
                reason: String(reason || "").trim(),
            },
            freeze: true,
            freeze_message: __("جاري إنشاء نسخة تعديل مستقلة..."),
        }).then(response => {
            const data = response.message || {};
            if (!data.name) return;
            frappe.show_alert({
                message: data.already_exists
                    ? __("توجد نسخة تعديل مرتبطة بهذا الطلب.")
                    : __("تم إنشاء نسخة مسودة مع الحفاظ على الطلب والخطة الأصلية."),
                indicator: data.already_exists ? "orange" : "green",
            }, 6);
            frappe.set_route("Form", "Door Cutting Order", data.name);
        });
    }

    function openRevision(frm) {
        frappe.prompt(
            [{
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("سبب إنشاء نسخة التعديل (اختياري)"),
                description: __("ينشئ مستندًا مسودة مستقلاً دون تعديل الطلب الحالي مباشرة."),
                reqd: 0,
            }],
            values => createRevision(frm, values.reason),
            __("إنشاء نسخة تعديل"),
            __("إنشاء النسخة المسودة")
        );
    }

    installEditPolicy();
    installEditSessionAbandonGuard();
    frappe.almdina.openOrderRevisionDialog = openRevision;
    frappe.almdina.createOrderRevision = createRevision;

    frappe.ui.form.on("Door Cutting Order", {
        onload(frm) {
            hydrateEditSession(frm);
        },
        after_save(frm) {
            const preserveSession = Boolean(frm.__almdina_preserve_edit_session_after_save);
            frm.__almdina_preserve_edit_session_after_save = false;
            if (preserveSession && isEditSessionActive(frm)) {
                frm.__almdina_lock_after_save = false;
                markEditSessionSticky(frm);
                applyEditableFields(frm);
                schedulePrimaryActionSync(frm);
                requestAnimationFrame(() => refreshDependentUx(frm));
                return;
            }

            const shouldLock = Boolean(frm.__almdina_lock_after_save)
                || (isEditSessionActive(frm) && !frm.is_new() && canOfferEditSession(frm));
            frm.__almdina_lock_after_save = false;
            if (shouldLock && isEditSessionActive(frm)) {
                lockEditSession(frm);
            }
        },
        refresh(frm) {
            const leftEdit = Boolean(frm.__almdina_edit_session_abandoned);
            const wasEditable = isEditSessionActive(frm);
            hydrateEditSession(frm);
            const editable = isEditSessionActive(frm);

            applyEditableFields(frm);
            renderRevisionState(frm);
            removeEditSessionButtons(frm);

            frm.remove_custom_button(__("إنشاء نسخة تعديل"), __("دورة الطلب"));

            if (frm.doc.revision_of) {
                frm.add_custom_button(__("فتح الطلب الأصلي"), () => {
                    frappe.set_route("Form", "Door Cutting Order", frm.doc.revision_of);
                }, __("دورة الطلب"));
            }

            if (frm.doc.superseded_by) {
                frm.add_custom_button(__("فتح نسخة التعديل"), () => {
                    frappe.set_route("Form", "Door Cutting Order", frm.doc.superseded_by);
                }, __("دورة الطلب"));
                schedulePrimaryActionSync(frm);
                if (editable || wasEditable || leftEdit) {
                    requestAnimationFrame(() => refreshDependentUx(frm));
                }
                return;
            }

            installEditSessionButtons(frm);
            schedulePrimaryActionSync(frm);

            if (canCreateRevision(frm) && !canOfferEditSession(frm)) {
                frm.add_custom_button(
                    __("إنشاء نسخة تعديل"),
                    () => openRevision(frm),
                    __("دورة الطلب")
                );
            }

            // Re-sync grids when entering/leaving edit mode, including re-entry after back.
            if (editable || wasEditable || leftEdit) {
                requestAnimationFrame(() => refreshDependentUx(frm));
            }
        },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        if (!canOfferEditSession(frm)) {
            setEditSession(frm, false);
        }
        applyEditableFields(frm);
        installEditSessionButtons(frm);
        schedulePrimaryActionSync(frm);
    });

    window.AlmdinaOrderRevisionUX = Object.freeze({
        canCreateRevision,
        canOfferEditSession,
        createRevision,
        applyImmutableFields: applyEditableFields,
        isEditableDraft: orderCanEdit,
        isEditSessionActive,
        markEditSessionRecalculated,
        invalidateEditSessionRecalculation,
        markEditSessionSticky,
        persistOrderEditCheckpoint,
        openRevision,
        enterEditSession,
        activateEditSessionQuietly,
        confirmEditSession,
        lockEditSession,
        commitEditSession,
        syncPrimaryAction,
        schedulePrimaryActionSync,
        captureEditSessionPresence,
        restorePrimaryAfterPlanEngine,
        ensureLockedPrimaryAction,
        abandonStoredEditSession,
    });
})();
