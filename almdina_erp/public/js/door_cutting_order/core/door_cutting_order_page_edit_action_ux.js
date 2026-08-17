(() => {
    "use strict";

    if (window.AlmdinaPageEditActionUX) return;

    const TAB_KIND = Object.freeze({
        order_tab: "order",
        results_tab: "plan",
        cost_tab: "cost",
    });
    const EDIT_LABELS = Object.freeze({
        order: "تعديل الطلب",
        plan: "تعديل خطة القص",
        cost: "تعديل التكلفة",
    });
    const SAVE_LABEL = "حفظ";
    const CANCEL_LABEL = "إلغاء";
    const CANCEL_CLASS = "dco-context-edit-cancel";
    const STYLE_ID = "dco-context-edit-action-css";
    const OBSERVER_KEY = "__almdinaPageEditActionObserver";
    const TAB_LISTENER_KEY = "__almdinaPageEditTabListenerInstalled";
    const BUSY_KEY = "__almdinaPageEditActionBusy";
    const MODE_KEY = "__almdinaPageEditActionMode";

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function permissionsResolved() {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions
            && typeof permissions.version === "function"
            && permissions.version() > 0
        );
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        $("head").append(`
            <style id="${STYLE_ID}">
                /* The edit action belongs to the active page tab, never to one
                   internal card. Keep the legacy plan toolbar out of the visual
                   hierarchy while its session/state API remains the owner. */
                .dco-plan-settings-edit-toolbar { display:none !important; }
                .page-actions .${CANCEL_CLASS} {
                    margin-inline-end:6px;
                    min-height:30px;
                    font-weight:700;
                }
            </style>
        `);
    }

    function formRoot(frm) {
        const wrapper = frm && frm.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function pageRoot(frm) {
        const wrapper = frm && frm.page && frm.page.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function pageActions(frm) {
        const root = pageRoot(frm);
        return root && root.querySelector ? root.querySelector(".page-actions") : null;
    }

    function primaryAction(frm) {
        const actions = pageActions(frm);
        return actions && actions.querySelector
            ? actions.querySelector(".primary-action")
            : null;
    }

    function currentTabFieldname(frm) {
        // Frappe v16 exposes the user-selected tab through Form.get_active_tab().
        // Layout.current_tab is only the layout construction cursor and may point
        // at a hidden/later Tab Break (for example cost_tab) while the user is
        // visibly on results_tab. Never use it as interaction state.
        const activeTab = frm && typeof frm.get_active_tab === "function"
            ? frm.get_active_tab()
            : null;
        const native = String(
            activeTab
            && activeTab.df
            && activeTab.df.fieldname
            || ""
        );
        if (TAB_KIND[native]) return native;

        const root = formRoot(frm);
        if (!root || !root.querySelector) return "order_tab";
        for (const fieldname of Object.keys(TAB_KIND)) {
            const node = root.querySelector(`[data-fieldname="${fieldname}"]`);
            const nav = node && (node.closest("li,.nav-item") || node);
            const link = nav && nav.querySelector
                ? nav.querySelector(".nav-link")
                : null;
            if (
                (nav && nav.classList && nav.classList.contains("active"))
                || (link && link.classList && link.classList.contains("active"))
                || (link && link.getAttribute("aria-selected") === "true")
            ) {
                return fieldname;
            }
        }
        return "order_tab";
    }

    function activeKind(frm) {
        return TAB_KIND[currentTabFieldname(frm)] || "order";
    }

    function orderApi() {
        return window.AlmdinaOrderRevisionUX || null;
    }

    function planApi() {
        return window.AlmdinaPlanEditSessionUX || null;
    }

    function costApi() {
        return window.AlmdinaCostEditSessionUX || null;
    }

    function apiFor(kind) {
        if (kind === "plan") return planApi();
        if (kind === "cost") return costApi();
        return orderApi();
    }

    function canEdit(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (kind === "plan" && typeof api.canEditPlanSettings === "function") {
            return Boolean(api.canEditPlanSettings(frm));
        }
        if (kind === "cost" && typeof api.canEditCostSettings === "function") {
            return Boolean(api.canEditCostSettings(frm));
        }
        if (kind === "order" && typeof api.canOfferEditSession === "function") {
            return Boolean(api.canOfferEditSession(frm));
        }
        return false;
    }

    function isEditing(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (kind === "order" && typeof api.captureEditSessionPresence === "function") {
            return Boolean(api.captureEditSessionPresence(frm));
        }
        return typeof api.isEditing === "function" && Boolean(api.isEditing(frm));
    }

    function activeEditingKind(frm) {
        return ["order", "plan", "cost"].find((kind) => isEditing(frm, kind)) || null;
    }

    function clearCancel(frm) {
        const actions = pageActions(frm);
        if (!actions || !actions.querySelectorAll) return;
        actions.querySelectorAll(`.${CANCEL_CLASS}`).forEach((button) => button.remove());
    }

    function setCancel(frm, handler, disabled = false) {
        clearCancel(frm);
        const actions = pageActions(frm);
        const primary = primaryAction(frm);
        if (!actions || !primary) return;
        const button = document.createElement("button");
        button.type = "button";
        button.className = `btn btn-default btn-sm ${CANCEL_CLASS}`;
        button.textContent = __(CANCEL_LABEL);
        button.disabled = Boolean(disabled);
        button.addEventListener("click", handler);
        actions.insertBefore(button, primary);
    }

    function primaryLabel(frm) {
        const button = primaryAction(frm);
        return String(button && button.textContent || "").replace(/\s+/g, " ").trim();
    }

    function clearPrimary(frm) {
        clearCancel(frm);
        frm[MODE_KEY] = "none";
        if (typeof frm.disable_save === "function") frm.disable_save();
        if (frm.page && typeof frm.page.clear_primary_action === "function") {
            frm.page.clear_primary_action();
        }
    }

    function setPrimary(frm, mode, label, handler, options = {}) {
        const busy = Boolean(frm[BUSY_KEY]);
        const desired = __(label);
        const current = primaryAction(frm);
        const same = Boolean(
            current
            && frm[MODE_KEY] === mode
            && primaryLabel(frm) === desired
            && current.getAttribute("data-almdina-context-edit-mode") === mode
        );

        if (!options.nativeSave) {
            if (typeof frm.disable_save === "function") frm.disable_save();
        } else {
            frm.save_disabled = false;
        }

        if (!same && frm.page && typeof frm.page.set_primary_action === "function") {
            frm.page.set_primary_action(desired, handler);
        }
        const button = primaryAction(frm);
        if (button) {
            button.setAttribute("data-almdina-context-edit-mode", mode);
            button.disabled = busy;
            button.setAttribute("aria-disabled", busy ? "true" : "false");
        }
        frm[MODE_KEY] = mode;
    }

    async function cancelOrder(frm) {
        const api = orderApi();
        if (!api || !isEditing(frm, "order")) return false;
        if (typeof api.lockEditSession === "function") {
            api.lockEditSession(frm, { silent: true });
        }
        await frm.reload_doc();
        return true;
    }

    function startFor(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (activeEditingKind(frm)) return false;
        if (kind === "order" && typeof api.enterEditSession === "function") {
            return api.enterEditSession(frm);
        }
        return typeof api.startEditing === "function" ? api.startEditing(frm) : false;
    }

    function saveFor(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (kind === "order" && typeof api.commitEditSession === "function") {
            return api.commitEditSession(frm);
        }
        return typeof api.saveEditing === "function" ? api.saveEditing(frm) : false;
    }

    function cancelFor(frm, kind) {
        const api = apiFor(kind);
        if (!api) return false;
        if (kind === "order") return cancelOrder(frm);
        return typeof api.cancelEditing === "function" ? api.cancelEditing(frm) : false;
    }

    async function runAction(frm, callback) {
        if (!frm || frm[BUSY_KEY]) return false;
        frm[BUSY_KEY] = true;
        sync(frm);
        try {
            await Promise.resolve(callback());
            return true;
        } finally {
            frm[BUSY_KEY] = false;
            schedule(frm);
        }
    }

    function sync(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order" || !frm.page) return false;
        installStyles();

        if (frm.is_new && frm.is_new()) {
            clearCancel(frm);
            frm[MODE_KEY] = "new";
            return true;
        }

        const editingKind = activeEditingKind(frm);
        const kind = editingKind || activeKind(frm);

        if (editingKind) {
            setPrimary(
                frm,
                `${kind}-save`,
                SAVE_LABEL,
                () => runAction(frm, () => saveFor(frm, kind)),
                { nativeSave: kind === "order" }
            );
            setCancel(
                frm,
                () => runAction(frm, () => cancelFor(frm, kind)),
                Boolean(frm[BUSY_KEY])
            );
            return true;
        }

        clearCancel(frm);
        if (!permissionsResolved() || !canEdit(frm, kind)) {
            clearPrimary(frm);
            return true;
        }

        setPrimary(
            frm,
            `${kind}-edit`,
            EDIT_LABELS[kind],
            () => runAction(frm, () => startFor(frm, kind))
        );
        return true;
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "page-context-edit-action", () => sync(frm));
            return;
        }
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) sync(frm);
        });
    }

    function tabFieldFromEventTarget(target) {
        if (!target || !target.closest) return "";
        const node = target.closest(
            '[data-fieldname="order_tab"],'
            + '[data-fieldname="results_tab"],'
            + '[data-fieldname="cost_tab"]'
        );
        if (!node) return "";
        const nav = node.closest("li,.nav-item");
        if (!nav && !node.classList.contains("nav-link")) return "";
        return String(node.getAttribute("data-fieldname") || "");
    }

    function installTabListener(frm) {
        const root = formRoot(frm);
        if (!root || root[TAB_LISTENER_KEY]) return;
        root.addEventListener("click", (event) => {
            const targetField = tabFieldFromEventTarget(event.target);
            if (!targetField) return;
            const currentField = currentTabFieldname(frm);
            const editingKind = activeEditingKind(frm);
            if (editingKind && targetField !== currentField) {
                event.preventDefault();
                event.stopImmediatePropagation();
                frappe.msgprint(__("احفظ أو ألغِ التعديل الحالي قبل الانتقال إلى قسم آخر."));
                return;
            }
            window.requestAnimationFrame(() => schedule(frm));
        }, true);
        root[TAB_LISTENER_KEY] = true;
    }

    function installPageActionObserver(frm) {
        const actions = pageActions(frm);
        if (!actions || frm[OBSERVER_KEY]) return;
        const observer = new MutationObserver(() => {
            if (frm[BUSY_KEY]) return;
            const mode = String(frm[MODE_KEY] || "");
            const button = primaryAction(frm);
            const owned = Boolean(
                button
                && button.getAttribute("data-almdina-context-edit-mode") === mode
            );
            if (!owned) schedule(frm);
        });
        observer.observe(actions, { childList: true, subtree: true });
        frm[OBSERVER_KEY] = observer;
        const context = documentContext();
        if (context && typeof context.registerObserver === "function") {
            context.registerObserver(frm, "page-context-edit-action-observer", observer);
        }
    }

    function refresh(frm) {
        installStyles();
        installTabListener(frm);
        installPageActionObserver(frm);
        schedule(frm);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
        refresh_plan_controls(frm) { schedule(frm); },
    });

    [
        "almdina:permissions-updated",
        "almdina:stage-context-ready",
        "almdina:surfaces-settled",
    ].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    window.AlmdinaPageEditActionUX = Object.freeze({
        activeKind,
        activeEditingKind,
        canEdit,
        isEditing,
        sync,
        schedule,
    });
})();
