(() => {
    "use strict";

    if (window.AlmdinaFinalPriceApprovalUX) return;

    const APPROVING_KEY = "__almdinaFinalPriceApproving";
    const CANCELLING_KEY = "__almdinaFinalPriceCancelling";
    const BOUND_KEY = "__almdinaFinalPriceApprovalBound";
    const TOAST_KEY = "__almdinaFinalPriceInvalidationToast";
    const PRIOR_STATUS_KEY = "__almdinaPriorPriceApprovalStatus";
    const APPROVE_DIALOG_KEY = "__almdinaFinalPriceApproveDialog";
    const CANCEL_DIALOG_KEY = "__almdinaFinalPriceCancelDialog";
    const NOTE_MAX = 500;
    const STATUS_APPROVED = "Approved";
    const STATUS_UNAPPROVED = "Unapproved";
    const INVALIDATION_TOAST =
        "The price approval for this order has been cancelled";

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    function esc(value) {
        if (window.frappe && frappe.utils && typeof frappe.utils.escape_html === "function") {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function stateOwner() {
        return window.AlmdinaCostWorkspaceState || null;
    }

    function api() {
        return window.AlmdinaCostWorkspaceAPI || null;
    }

    function snapshot(frm) {
        const owner = stateOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function keepPaint() {
        return window.AlmdinaWorkspaceKeepPaint || null;
    }

    function presentationData(frm) {
        const state = snapshot(frm);
        const keeper = keepPaint();
        if (keeper && typeof keeper.presentationData === "function") {
            return keeper.presentationData(state);
        }
        return state && state.status === "ready" ? state.data : null;
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (frm && typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, capability));
        }
        return typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function hasApproveCapability(frm) {
        return can(frm, "approve_final_price");
    }

    function hasCancelCapability(frm) {
        return can(frm, "cancel_final_price_approval");
    }

    function canSeeInvalidationToast(frm) {
        return hasApproveCapability(frm) || hasCancelCapability(frm);
    }

    function syncFormPriceApprovalFields(frm, status, approvalName) {
        if (!frm || !frm.doc) return;
        const nextStatus = normalizeStatus(status);
        const nextLink = approvalName ? String(approvalName).trim() || null : null;
        frm.doc.price_approval_status = nextStatus;
        frm.doc.current_price_approval = nextLink;
        if (typeof frm.refresh_field === "function") {
            frm.refresh_field("price_approval_status");
            frm.refresh_field("current_price_approval");
        }
    }

    function notifyAutoInvalidation(frm, options = {}) {
        if (!frm || !frm.doc) return false;
        if (!canSeeInvalidationToast(frm)) return false;
        const orderName = String(frm.doc.name || "").trim();
        const signalOrder = options.orderName != null
            ? String(options.orderName || "").trim()
            : orderName;
        if (!orderName || !signalOrder || signalOrder !== orderName) return false;
        if (options.docToken && !documentStillCurrent(frm, options.docToken)) {
            return false;
        }
        if (options.signal === false) return false;
        const toastToken = `${orderName}::${options.generation || captureDocument(frm).generation || 0}`;
        if (frm[TOAST_KEY] === toastToken) return false;
        frm[TOAST_KEY] = toastToken;
        if (window.frappe && typeof frappe.show_alert === "function") {
            frappe.show_alert({
                message: translate(INVALIDATION_TOAST),
                indicator: "orange",
            }, 6);
        }
        return true;
    }

    function capturePriorPriceApprovalStatus(frm) {
        if (!frm || !frm.doc) return;
        frm[PRIOR_STATUS_KEY] = normalizeStatus(frm.doc.price_approval_status);
    }

    function afterOrderSave(frm) {
        if (!frm || !frm.doc) return false;
        const prior = normalizeStatus(frm[PRIOR_STATUS_KEY]);
        const current = normalizeStatus(frm.doc.price_approval_status);
        frm[PRIOR_STATUS_KEY] = current;
        const response = window.frappe && frappe.response ? frappe.response : null;
        const flagged = Boolean(
            response
            && (
                response.final_price_approval_invalidated
                || (response.message && response.message.final_price_approval_invalidated)
            )
        );
        const responseOrder = response
            && (response.final_price_approval_order
                || (response.message && response.message.final_price_approval_order));
        if (flagged) {
            return notifyAutoInvalidation(frm, {
                signal: true,
                orderName: responseOrder || frm.doc.name,
            });
        }
        if (prior === STATUS_APPROVED && current === STATUS_UNAPPROVED) {
            return notifyAutoInvalidation(frm, { signal: true });
        }
        return false;
    }

    function consumeInvalidationSignal(frm, payload, docToken) {
        if (!payload || !payload.final_price_approval_invalidated) return false;
        syncFormPriceApprovalFields(frm, STATUS_UNAPPROVED, null);
        return notifyAutoInvalidation(frm, {
            signal: true,
            orderName: payload.order_name || (frm.doc && frm.doc.name),
            docToken,
        });
    }

    function normalizeStatus(value) {
        return String(value || "").trim() === STATUS_APPROVED
            ? STATUS_APPROVED
            : STATUS_UNAPPROVED;
    }

    function captureDocument(frm) {
        const context = documentContext();
        if (context && typeof context.capture === "function") {
            return context.capture(frm);
        }
        return Object.freeze({
            identity: `${frm && frm.doctype || ""}::${frm && frm.doc && frm.doc.name || ""}`,
            generation: 0,
        });
    }

    function documentStillCurrent(frm, token) {
        const context = documentContext();
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, token);
        }
        return Boolean(window.cur_frm === frm);
    }

    function hasUnsavedChanges(frm) {
        if (frm && typeof frm.is_dirty === "function" && frm.is_dirty()) return true;
        const coordinator = window.AlmdinaDcoEditSessionCoordinator;
        if (coordinator && typeof coordinator.activeKind === "function" && coordinator.activeKind(frm)) {
            return true;
        }
        const state = snapshot(frm);
        if (state && (state.editing || state.dirty)) return true;
        return false;
    }

    function isBusy(frm) {
        return Boolean(frm && (frm[APPROVING_KEY] || frm[CANCELLING_KEY]));
    }

    function actionsTrusted(frm) {
        if (isBusy(frm)) return false;
        if (hasUnsavedChanges(frm)) return false;
        const state = snapshot(frm);
        if (!state || state.status !== "ready" || !state.data) return false;
        if (state.freshness === "stale") return false;
        return true;
    }

    function formatApprovedOn(value) {
        const text = String(value || "").trim();
        if (!text) return "";
        if (window.frappe && frappe.datetime && typeof frappe.datetime.str_to_user === "function") {
            try {
                return frappe.datetime.str_to_user(text);
            } catch (_error) {
                return text;
            }
        }
        return text;
    }

    function formatMoney(amount, currency) {
        const number = Number(amount);
        const safe = Number.isFinite(number) ? number : 0;
        const formatted = safe.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        const code = String(currency || "USD").trim() || "USD";
        return `${code} ${formatted}`;
    }

    function approvalNoteText(approval) {
        if (!approval) return "";
        return String(approval.approval_note || "").trim();
    }

    function costRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper) return null;
        if (typeof wrapper.get === "function") return wrapper.get(0) || null;
        return wrapper[0] || (typeof wrapper.querySelector === "function" ? wrapper : null);
    }

    function hideDialog(frm, key) {
        const dialog = frm && frm[key];
        if (!dialog) return;
        try {
            if (typeof dialog.hide === "function") dialog.hide();
        } catch (_error) {
            // Dialog may already be disposed after navigation.
        }
        frm[key] = null;
    }

    function disposeDialogs(frm) {
        hideDialog(frm, APPROVE_DIALOG_KEY);
        hideDialog(frm, CANCEL_DIALOG_KEY);
    }

    function renderActionButton(options) {
        const {
            variant,
            className,
            label,
            disabled,
            attrs,
        } = options;
        if (window.AlmdinaUi && typeof window.AlmdinaUi.button === "function") {
            return window.AlmdinaUi.button({
                variant,
                size: "btn-sm",
                className,
                label,
                disabled,
                attrs,
            });
        }
        const variantClass = variant === "primary"
            ? "alm-btn-primary"
            : (variant === "danger" ? "alm-btn-danger" : "alm-btn-secondary");
        const attrHtml = Object.entries(attrs || {})
            .map(([key, value]) => `${key}="${esc(value)}"`)
            .join(" ");
        return `<button type="button"
            class="btn ${variantClass} btn-sm ${esc(className || "")}"
            ${disabled ? "disabled" : ""}
            ${attrHtml}>
            ${esc(label)}
        </button>`;
    }

    function panelHtml(frm) {
        const data = presentationData(frm);
        if (!data) {
            return `<div class="dco-price-approval-panel is-pending-data" data-price-approval-panel>
                <div class="dco-price-approval-copy">
                    <div class="dco-price-approval-status">
                        <span class="dco-price-approval-label">${esc(translate("Price approval status"))}</span>
                        <span class="dco-price-approval-badge is-unknown">${esc(translate("Updating…"))}</span>
                    </div>
                </div>
            </div>`;
        }

        const status = normalizeStatus(data.price_approval_status);
        const approved = status === STATUS_APPROVED;
        const badgeClass = approved ? "is-approved" : "is-unapproved";
        const badgeLabel = approved ? translate("Approved") : translate("Unapproved");
        const approval = data.price_approval || null;
        const meta = [];
        if (approved && approval) {
            const who = String(approval.approved_by || "").trim();
            const when = formatApprovedOn(approval.approved_on);
            if (who && when) {
                meta.push(translate("Approved by {0} on {1}", [who, when]));
            } else if (who) {
                meta.push(translate("Approved by {0}", [who]));
            } else if (when) {
                meta.push(translate("Approved on {0}", [when]));
            }
        }

        const note = approved ? approvalNoteText(approval) : "";
        let noteHtml = "";
        if (note) {
            const long = note.length > 120 || note.includes("\n");
            noteHtml = `<div class="dco-price-approval-note" data-approval-note>
                <span class="dco-price-approval-note-label">${esc(translate("Approval note"))}</span>
                <div class="dco-price-approval-note-text${long ? " is-collapsed" : ""}"
                    data-approval-note-text>${esc(note)}</div>
                ${long ? `<button type="button" class="dco-price-approval-note-more"
                    data-expand-approval-note>${esc(translate("Show more"))}</button>` : ""}
            </div>`;
        }

        let actionHtml = "";
        const trusted = actionsTrusted(frm);
        const busyApprove = Boolean(frm && frm[APPROVING_KEY]);
        const busyCancel = Boolean(frm && frm[CANCELLING_KEY]);

        if (!approved && hasApproveCapability(frm)) {
            const canApprove = Boolean(data.can_approve_final_price) && trusted;
            const blocker = data.final_price_approval_blocker;
            const title = canApprove
                ? translate("Approve final price")
                : String(
                    (blocker && blocker.message)
                    || translate("The final price is not ready to approve yet.")
                );
            actionHtml = renderActionButton({
                variant: "primary",
                className: `dco-approve-final-price${busyApprove ? " is-loading" : ""}`,
                label: busyApprove ? translate("Approving…") : translate("Approve final price"),
                disabled: !(canApprove && !busyApprove),
                attrs: {
                    "data-approve-final-price": "",
                    title,
                    "aria-disabled": canApprove && !busyApprove ? "false" : "true",
                },
            });
            if (!canApprove && blocker && blocker.message && trusted) {
                actionHtml += `<small class="dco-price-approval-blocker">${esc(blocker.message)}</small>`;
            }
        } else if (approved && hasCancelCapability(frm)) {
            const canCancel = Boolean(data.can_cancel_final_price_approval) && trusted;
            const blocker = data.final_price_cancellation_blocker;
            const title = canCancel
                ? translate("Cancel final price approval")
                : String(
                    (blocker && blocker.message)
                    || translate("There is no active final-price approval to cancel.")
                );
            actionHtml = renderActionButton({
                variant: "secondary",
                className: `dco-cancel-final-price${busyCancel ? " is-loading" : ""}`,
                label: busyCancel
                    ? translate("Cancelling…")
                    : translate("Cancel final price approval"),
                disabled: !(canCancel && !busyCancel),
                attrs: {
                    "data-cancel-final-price": "",
                    title,
                    "aria-disabled": canCancel && !busyCancel ? "false" : "true",
                },
            });
            if (!canCancel && blocker && blocker.message && trusted) {
                actionHtml += `<small class="dco-price-approval-blocker">${esc(blocker.message)}</small>`;
            }
        }

        return `<div class="dco-price-approval-panel ${approved ? "is-approved" : "is-unapproved"}" data-price-approval-panel>
            <div class="dco-price-approval-copy">
                <div class="dco-price-approval-status">
                    <span class="dco-price-approval-label">${esc(translate("Price approval status"))}</span>
                    <span class="dco-price-approval-badge ${badgeClass}">
                        ${approved ? `<span class="dco-price-approval-icon" aria-hidden="true">✓</span>` : ""}
                        ${esc(badgeLabel)}
                    </span>
                </div>
                ${meta.length ? `<small class="dco-price-approval-meta">${esc(meta.join(" · "))}</small>` : ""}
                ${noteHtml}
            </div>
            ${actionHtml}
        </div>`;
    }

    function ensureStyles() {
        if (document.getElementById("dco-final-price-approval-style")) return;
        const style = document.createElement("style");
        style.id = "dco-final-price-approval-style";
        style.textContent = `
            .dco-price-approval-panel{display:flex;align-items:center;flex-wrap:wrap;gap:8px;min-width:0}
            .dco-price-approval-copy{display:flex;flex-direction:column;align-items:flex-start;gap:4px;min-width:0;max-width:min(280px,100%)}
            .dco-price-approval-status{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
            .dco-price-approval-label{font-size:11px;font-weight:800;color:var(--text-muted,#687481)}
            .dco-price-approval-badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:800;border:1px solid var(--alm-card-border,#e4e8ee);background:var(--alm-surface-muted,#f4f6f8);color:var(--alm-text-strong,#101828)}
            .dco-price-approval-badge.is-approved{border-color:color-mix(in srgb, var(--alm-success,#15803d) 35%, var(--alm-card,#ffffff));background:color-mix(in srgb, var(--alm-success,#15803d) 10%, var(--alm-card,#ffffff));color:var(--alm-success,#15803d)}
            .dco-price-approval-badge.is-unapproved{border-color:color-mix(in srgb, var(--alm-warning,#b45309) 30%, var(--alm-card,#ffffff));background:var(--alm-warning-bg,#fff7e8);color:var(--alm-warning,#b45309)}
            .dco-price-approval-badge.is-unknown{opacity:.72}
            .dco-price-approval-icon{font-weight:900;line-height:1}
            .dco-price-approval-meta,.dco-price-approval-blocker{display:block;max-width:100%;font-size:10px;font-weight:700;color:var(--text-muted,#687481);line-height:1.45}
            .dco-price-approval-note{display:flex;flex-direction:column;align-items:flex-start;gap:2px;max-width:100%;margin-top:2px}
            .dco-price-approval-note-label{font-size:10px;font-weight:800;color:var(--text-muted,#687481)}
            .dco-price-approval-note-text{font-size:11px;font-weight:600;color:var(--text-color,#1f272e);line-height:1.45;white-space:pre-wrap;word-break:break-word;max-width:100%}
            .dco-price-approval-note-text.is-collapsed{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}
            .dco-price-approval-note-more{appearance:none;border:0;background:transparent;padding:0;margin:0;font-size:10px;font-weight:800;color:var(--alm-primary,#172033);cursor:pointer;text-decoration:underline}
            .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary,
            .dco-invoice-total-card .dco-cancel-final-price.alm-btn-secondary{
                box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;
                min-width:var(--alm-min-width-button-compact,96px);min-height:unset;height:auto;
                padding-block:var(--alm-padding-button-compact-y,8px);padding-inline:var(--alm-padding-button-compact-x,18px);
                border-radius:var(--alm-radius-button,999px);
                font-size:var(--alm-font-size-sm,12px);font-weight:var(--alm-font-weight-heavy,800);line-height:1.2;
                box-shadow:none;flex:0 0 auto;white-space:nowrap
            }
            .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary{
                border:1px solid var(--alm-primary,#172033);background:var(--alm-primary,#172033);color:var(--alm-on-primary,#fff)
            }
            .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary:hover:not(:disabled){
                background:var(--alm-primary-hover,#0f1624);border-color:var(--alm-primary-hover,#0f1624);color:var(--alm-on-primary,#fff)
            }
            .dco-invoice-total-card .dco-cancel-final-price.alm-btn-secondary{
                border:1px solid color-mix(in srgb, var(--alm-warning,#b45309) 45%, var(--alm-card-border,#e4e8ee));
                background:color-mix(in srgb, var(--alm-warning,#b45309) 8%, var(--alm-card,#fff));
                color:var(--alm-warning,#b45309)
            }
            .dco-invoice-total-card .dco-cancel-final-price.alm-btn-secondary:hover:not(:disabled){
                background:color-mix(in srgb, var(--alm-warning,#b45309) 14%, var(--alm-card,#fff));
                border-color:color-mix(in srgb, var(--alm-warning,#b45309) 55%, var(--alm-card-border,#e4e8ee))
            }
            .dco-invoice-total-card .dco-approve-final-price:focus-visible,
            .dco-invoice-total-card .dco-cancel-final-price:focus-visible{
                outline:none;box-shadow:0 0 0 3px color-mix(in srgb, var(--alm-primary, #172033) 18%, transparent)
            }
            .dco-invoice-total-card .dco-approve-final-price:disabled,
            .dco-invoice-total-card .dco-cancel-final-price:disabled,
            .dco-invoice-total-card .dco-approve-final-price.is-loading,
            .dco-invoice-total-card .dco-cancel-final-price.is-loading{
                opacity:.55;cursor:not-allowed;box-shadow:none
            }
            .dco-final-price-approve-dialog .modal-dialog{max-width:min(480px,calc(100vw - 24px))}
            .dco-final-price-approve-dialog .dco-approve-amount-summary{
                display:flex;flex-direction:column;gap:4px;margin-bottom:10px;padding:10px 12px;
                border:1px solid var(--alm-card-border,#e4e8ee);border-radius:12px;
                background:color-mix(in srgb, var(--alm-primary,#172033) 4%, var(--alm-card,#fff))
            }
            .dco-final-price-approve-dialog .dco-approve-amount-summary strong{
                font-size:18px;font-weight:900;color:var(--text-color,#1f272e);direction:ltr;text-align:start
            }
            .dco-final-price-approve-dialog .dco-approve-amount-summary span,
            .dco-final-price-approve-dialog .dco-approve-note-hint{
                font-size:11px;font-weight:700;color:var(--text-muted,#687481)
            }
            .dco-final-price-approve-dialog textarea[data-fieldname="approval_note"]{
                min-height:4.5em;max-height:6.5em;resize:vertical
            }
            .dco-final-price-approve-dialog .dco-approve-note-counter{
                display:block;margin-top:4px;font-size:10px;font-weight:700;color:var(--text-muted,#687481);text-align:end
            }
            .dco-final-price-approve-dialog .dco-approve-note-counter.is-limit{color:var(--alm-danger,#b91c1c)}
            @media(max-width:560px){
                .dco-price-approval-panel{flex:1 1 auto}
                .dco-invoice-total-card .dco-approve-final-price,
                .dco-invoice-total-card .dco-cancel-final-price{flex:0 1 auto}
            }
        `;
        document.head.appendChild(style);
    }

    function wrapTotalCardStructure(card) {
        if (!card || card.querySelector("[data-price-approval-panel]")) return card;
        const label = document.createElement("div");
        label.className = "dco-invoice-total-label";
        const end = document.createElement("div");
        end.className = "dco-invoice-total-end";
        while (card.firstChild) {
            const child = card.firstChild;
            if (child.nodeType === 1 && child.tagName === "B") {
                child.classList.add("dco-invoice-total-amount");
                end.appendChild(child);
            } else {
                label.appendChild(child);
            }
        }
        const panel = document.createElement("div");
        panel.className = "dco-price-approval-slot";
        panel.setAttribute("data-price-approval-panel", "");
        end.insertBefore(panel, end.firstChild);
        card.appendChild(label);
        card.appendChild(end);
        return card;
    }

    function reconcile(frm) {
        ensureStyles();
        if (frm && window.cur_frm && window.cur_frm !== frm) {
            disposeDialogs(frm);
        }
        const root = costRoot(frm);
        if (!root || typeof root.querySelector !== "function") return false;
        const card = root.querySelector(".dco-invoice-total-card");
        if (!card) return false;
        wrapTotalCardStructure(card);
        const panel = card.querySelector("[data-price-approval-panel]");
        if (!panel) return false;
        panel.outerHTML = panelHtml(frm);
        bind(frm);
        return true;
    }

    function errorMessage(error, fallback) {
        if (!error) return fallback;
        if (typeof error === "string" && error.trim()) return error;
        const message = error.message
            || (error._server_messages && String(error._server_messages))
            || (error.exc && String(error.exc).split("\n")[0]);
        if (message && String(message).trim()) {
            try {
                const parsed = JSON.parse(String(message));
                if (Array.isArray(parsed) && parsed.length) {
                    const first = typeof parsed[0] === "string" ? JSON.parse(parsed[0]) : parsed[0];
                    if (first && first.message) return String(first.message);
                }
            } catch (_error) {
                return String(message);
            }
            return String(message);
        }
        return fallback;
    }

    function isStaleTokenError(error) {
        const text = String(errorMessage(error, "") || "").toLowerCase();
        return text.includes("price basis")
            || text.includes("basis changed")
            || text.includes("أساس السعر")
            || text.includes("تغيّر");
    }

    function isStaleApprovalError(error) {
        const text = String(errorMessage(error, "") || "").toLowerCase();
        return text.includes("approval changed")
            || text.includes("refresh and review before cancelling")
            || text.includes("تغيّر اعتماد السعر")
            || text.includes("approval_changed");
    }

    async function reloadSnapshot(frm, { force = true } = {}) {
        const owner = stateOwner();
        if (!owner || typeof owner.load !== "function") return null;
        return owner.load(frm, { force });
    }

    function syncEditSession(frm) {
        const editSession = window.AlmdinaCostEditSessionUX;
        if (editSession && typeof editSession.sync === "function") {
            editSession.sync(frm);
        }
    }

    function mergeApprovalIntoStore(frm, result) {
        const owner = stateOwner();
        const state = snapshot(frm);
        if (!owner || typeof owner.commit !== "function" || !state || !state.data || !result) {
            return null;
        }
        syncFormPriceApprovalFields(
            frm,
            result.price_approval_status || STATUS_APPROVED,
            result.current_price_approval || null
        );
        const note = result.approval_note != null
            ? String(result.approval_note || "").trim() || null
            : null;
        return owner.commit(frm, {
            ...state.data,
            price_approval_status: result.price_approval_status || STATUS_APPROVED,
            current_price_approval: result.current_price_approval || null,
            price_basis_token: result.price_basis_token || state.data.price_basis_token || null,
            can_approve_final_price: false,
            can_cancel_final_price_approval: Boolean(
                state.data.can_cancel_final_price_approval
            ) || hasCancelCapability(frm),
            can_edit_cost_settings: state.data.can_edit_cost_settings,
            final_price_approval_blocker: null,
            final_price_cancellation_blocker: null,
            price_approval: {
                name: result.current_price_approval || null,
                approved_amount_usd: result.approved_amount_usd,
                currency: result.currency,
                cutting_plan: result.cutting_plan,
                approved_by: result.approved_by,
                approved_on: result.approved_on,
                approval_note: note,
                validity_status: "Active",
                fingerprint_formula_version: result.fingerprint_formula_version,
            },
        });
    }

    function mergeCancellationIntoStore(frm, result) {
        const owner = stateOwner();
        const state = snapshot(frm);
        if (!owner || typeof owner.commit !== "function" || !state || !state.data || !result) {
            return null;
        }
        syncFormPriceApprovalFields(frm, STATUS_UNAPPROVED, null);
        return owner.commit(frm, {
            ...state.data,
            price_approval_status: result.price_approval_status || STATUS_UNAPPROVED,
            current_price_approval: null,
            price_approval: null,
            can_approve_final_price: Boolean(result.can_approve_final_price),
            can_cancel_final_price_approval: Boolean(result.can_cancel_final_price_approval),
            final_price_approval_blocker: result.final_price_approval_blocker || null,
            final_price_cancellation_blocker: result.final_price_cancellation_blocker || null,
            can_edit_cost_settings: state.data.can_edit_cost_settings,
        });
    }

    function readDialogNote(dialog) {
        if (!dialog) return "";
        if (typeof dialog.get_value === "function") {
            return String(dialog.get_value("approval_note") || "");
        }
        const values = typeof dialog.get_values === "function" ? dialog.get_values() : null;
        return String((values && values.approval_note) || "");
    }

    function updateNoteCounter(dialog) {
        if (!dialog || !dialog.$wrapper) return;
        const field = dialog.fields_dict && dialog.fields_dict.approval_note;
        const control = field && field.$wrapper;
        if (!control || !control.length) return;
        let counter = control.find(".dco-approve-note-counter")[0];
        if (!counter) {
            counter = document.createElement("small");
            counter.className = "dco-approve-note-counter";
            control.append(counter);
        }
        const length = readDialogNote(dialog).length;
        counter.textContent = translate("{0} / {1}", [String(length), String(NOTE_MAX)]);
        counter.classList.toggle("is-limit", length >= NOTE_MAX);
    }

    function openApproveDialog(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (!hasApproveCapability(frm)) return false;
        if (isBusy(frm)) return false;
        if (frm[APPROVE_DIALOG_KEY]) return false;

        if (hasUnsavedChanges(frm)) {
            frappe.msgprint({
                title: translate("Unsaved changes"),
                message: translate("Save or cancel unsaved changes before approving the final price."),
                indicator: "orange",
            });
            return false;
        }

        const state = snapshot(frm);
        const data = state && state.status === "ready" ? state.data : null;
        const orderName = String(frm.doc.name || "").trim();
        const token = data && data.price_basis_token ? String(data.price_basis_token) : "";
        if (!orderName || !token || !data || !data.can_approve_final_price) {
            frappe.msgprint({
                title: translate("Final price not ready"),
                message: translate("The final price is not ready to approve yet."),
                indicator: "orange",
            });
            return false;
        }

        if (!window.frappe || !frappe.ui || typeof frappe.ui.Dialog !== "function") {
            return false;
        }

        const docToken = captureDocument(frm);
        const amountLabel = formatMoney(
            data.invoice_preview_total_usd,
            (data.price_approval && data.price_approval.currency) || data.currency || "USD"
        );
        const session = {
            orderName,
            token,
            docToken,
            amountLabel,
            draftNote: "",
        };

        const dialog = new frappe.ui.Dialog({
            title: translate("Approve final price"),
            size: "small",
            fields: [
                {
                    fieldtype: "HTML",
                    fieldname: "amount_summary",
                    options: `<div class="dco-approve-amount-summary">
                        <span>${esc(translate("Final invoice total"))}</span>
                        <strong data-approve-amount>${esc(amountLabel)}</strong>
                    </div>`,
                },
                {
                    fieldtype: "Small Text",
                    fieldname: "approval_note",
                    label: `${translate("Approval note")} (${translate("Optional")})`,
                    placeholder: translate("Add a note linked to this price approval…"),
                    description: translate("The note is saved with the approval record."),
                    maxlength: NOTE_MAX,
                },
            ],
            primary_action_label: translate("Confirm approval"),
            primary_action() {
                return confirmApproveFromDialog(frm, dialog, session);
            },
            secondary_action_label: translate("Cancel"),
            secondary_action() {
                dialog.hide();
            },
        });

        dialog.$wrapper.addClass("dco-final-price-approve-dialog");
        dialog.onhide = () => {
            if (frm[APPROVE_DIALOG_KEY] === dialog) {
                frm[APPROVE_DIALOG_KEY] = null;
            }
        };
        frm[APPROVE_DIALOG_KEY] = dialog;
        dialog.show();
        updateNoteCounter(dialog);

        const noteField = dialog.fields_dict && dialog.fields_dict.approval_note;
        const input = noteField && noteField.$input;
        if (input && input.length) {
            input.attr("maxlength", String(NOTE_MAX));
            input.attr("rows", "3");
            input.on("input", () => {
                session.draftNote = readDialogNote(dialog);
                if (session.draftNote.length > NOTE_MAX) {
                    dialog.set_value("approval_note", session.draftNote.slice(0, NOTE_MAX));
                    session.draftNote = readDialogNote(dialog);
                }
                updateNoteCounter(dialog);
            });
        }
        return true;
    }

    async function confirmApproveFromDialog(frm, dialog, session) {
        if (!frm || !dialog || !session) return false;
        if (!documentStillCurrent(frm, session.docToken)) {
            dialog.hide();
            return false;
        }
        if (frm[APPROVING_KEY] || frm[CANCELLING_KEY]) return false;
        if (hasUnsavedChanges(frm)) {
            frappe.msgprint({
                title: translate("Unsaved changes"),
                message: translate("Save or cancel unsaved changes before approving the final price."),
                indicator: "orange",
            });
            return false;
        }

        const note = readDialogNote(dialog);
        session.draftNote = note;
        if (note.length > NOTE_MAX) {
            frappe.msgprint({
                title: translate("Approval note"),
                message: translate("Approval note cannot exceed 500 characters."),
                indicator: "orange",
            });
            return false;
        }

        const transport = api();
        if (!transport || typeof transport.approveFinalPrice !== "function") return false;

        frm[APPROVING_KEY] = true;
        dialog.disable_primary_button && dialog.disable_primary_button();
        if (dialog.get_primary_btn) {
            dialog.get_primary_btn().prop("disabled", true).text(translate("Approving…"));
        }
        reconcile(frm);

        try {
            const result = await transport.approveFinalPrice(
                session.orderName,
                session.token,
                note
            );
            if (!documentStillCurrent(frm, session.docToken)) return false;
            hideDialog(frm, APPROVE_DIALOG_KEY);
            mergeApprovalIntoStore(frm, result);
            try {
                await reloadSnapshot(frm, { force: true });
            } catch (reloadError) {
                if (!documentStillCurrent(frm, session.docToken)) return false;
                console.error("Cost snapshot reload failed after final-price approval", reloadError);
                frappe.msgprint({
                    title: translate("Final price approved"),
                    message: translate("The final price was approved, but the cost data could not be refreshed. Open the Cost tab again to load the latest status."),
                    indicator: "orange",
                });
            }
            if (!documentStillCurrent(frm, session.docToken)) return false;
            reconcile(frm);
            syncEditSession(frm);
            if (window.frappe && typeof frappe.show_alert === "function") {
                frappe.show_alert({
                    message: translate("Final price approved"),
                    indicator: "green",
                }, 5);
            }
            return true;
        } catch (error) {
            if (!documentStillCurrent(frm, session.docToken)) return false;
            if (typeof dialog.set_value === "function") {
                dialog.set_value("approval_note", session.draftNote || note);
            }
            updateNoteCounter(dialog);
            if (isStaleTokenError(error)) {
                try {
                    await reloadSnapshot(frm, { force: true });
                } catch (reloadError) {
                    console.error("Cost snapshot reload failed after stale token", reloadError);
                }
                if (!documentStillCurrent(frm, session.docToken)) return false;
                const refreshed = presentationData(frm);
                if (refreshed && refreshed.price_basis_token) {
                    session.token = String(refreshed.price_basis_token);
                    session.amountLabel = formatMoney(
                        refreshed.invoice_preview_total_usd,
                        (refreshed.price_approval && refreshed.price_approval.currency)
                            || refreshed.currency
                            || "USD"
                    );
                    const amountNode = dialog.$wrapper
                        && dialog.$wrapper.find("[data-approve-amount]")[0];
                    if (amountNode) amountNode.textContent = session.amountLabel;
                }
                frappe.msgprint({
                    title: translate("Price changed"),
                    message: translate("The price basis changed. Review the total, then approve again."),
                    indicator: "orange",
                });
                reconcile(frm);
                return false;
            }
            frappe.msgprint({
                title: translate("Could not approve the final price"),
                message: errorMessage(error, translate("Could not approve the final price.")),
                indicator: "red",
            });
            return false;
        } finally {
            if (documentStillCurrent(frm, session.docToken)) {
                frm[APPROVING_KEY] = false;
                if (frm[APPROVE_DIALOG_KEY] === dialog && dialog.get_primary_btn) {
                    dialog.get_primary_btn()
                        .prop("disabled", false)
                        .text(translate("Confirm approval"));
                }
                reconcile(frm);
            } else if (frm) {
                frm[APPROVING_KEY] = false;
            }
        }
    }

    function openCancelDialog(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (!hasCancelCapability(frm)) return false;
        if (isBusy(frm)) return false;
        if (frm[CANCEL_DIALOG_KEY]) return false;

        if (hasUnsavedChanges(frm)) {
            frappe.msgprint({
                title: translate("Unsaved changes"),
                message: translate("Save or cancel unsaved changes before cancelling the final price approval."),
                indicator: "orange",
            });
            return false;
        }

        const state = snapshot(frm);
        const data = state && state.status === "ready" ? state.data : null;
        const orderName = String(frm.doc.name || "").trim();
        const approvalName = data && (
            data.current_price_approval
            || (data.price_approval && data.price_approval.name)
        );
        const expected = String(approvalName || "").trim();
        if (!orderName || !expected || !data || !data.can_cancel_final_price_approval) {
            const blocker = data && data.final_price_cancellation_blocker;
            frappe.msgprint({
                title: translate("Cancel final price approval"),
                message: String(
                    (blocker && blocker.message)
                    || translate("There is no active final-price approval to cancel.")
                ),
                indicator: "orange",
            });
            return false;
        }

        if (!window.frappe || !frappe.ui || typeof frappe.ui.Dialog !== "function") {
            return false;
        }

        const docToken = captureDocument(frm);
        const session = { orderName, expected, docToken };
        const dialog = new frappe.ui.Dialog({
            title: translate("Cancel final price approval"),
            size: "small",
            fields: [
                {
                    fieldtype: "HTML",
                    fieldname: "cancel_copy",
                    options: `<p>${esc(translate("Do you want to cancel the final price approval for this order? Order details and prices will stay the same."))}</p>`,
                },
            ],
            primary_action_label: translate("Cancel final price approval"),
            primary_action() {
                return confirmCancelFromDialog(frm, dialog, session);
            },
            secondary_action_label: translate("Go back"),
            secondary_action() {
                dialog.hide();
            },
        });
        dialog.onhide = () => {
            if (frm[CANCEL_DIALOG_KEY] === dialog) {
                frm[CANCEL_DIALOG_KEY] = null;
            }
        };
        frm[CANCEL_DIALOG_KEY] = dialog;
        dialog.show();
        return true;
    }

    async function confirmCancelFromDialog(frm, dialog, session) {
        if (!frm || !dialog || !session) return false;
        if (!documentStillCurrent(frm, session.docToken)) {
            dialog.hide();
            return false;
        }
        if (frm[CANCELLING_KEY] || frm[APPROVING_KEY]) return false;
        if (hasUnsavedChanges(frm)) {
            frappe.msgprint({
                title: translate("Unsaved changes"),
                message: translate("Save or cancel unsaved changes before cancelling the final price approval."),
                indicator: "orange",
            });
            return false;
        }

        const transport = api();
        if (!transport || typeof transport.cancelFinalPriceApproval !== "function") {
            return false;
        }

        frm[CANCELLING_KEY] = true;
        if (dialog.get_primary_btn) {
            dialog.get_primary_btn().prop("disabled", true).text(translate("Cancelling…"));
        }
        reconcile(frm);

        try {
            const result = await transport.cancelFinalPriceApproval(
                session.orderName,
                session.expected
            );
            if (!documentStillCurrent(frm, session.docToken)) return false;
            hideDialog(frm, CANCEL_DIALOG_KEY);
            // Manual cancel must not raise the auto-invalidation toast.
            if (result && result.final_price_approval_invalidated) {
                result.final_price_approval_invalidated = false;
            }
            mergeCancellationIntoStore(frm, result);
            try {
                await reloadSnapshot(frm, { force: true });
            } catch (reloadError) {
                if (!documentStillCurrent(frm, session.docToken)) return false;
                console.error("Cost snapshot reload failed after final-price cancel", reloadError);
            }
            if (!documentStillCurrent(frm, session.docToken)) return false;
            reconcile(frm);
            syncEditSession(frm);
            if (window.frappe && typeof frappe.show_alert === "function") {
                frappe.show_alert({
                    message: translate("Final price approval cancelled"),
                    indicator: "orange",
                }, 5);
            }
            return true;
        } catch (error) {
            if (!documentStillCurrent(frm, session.docToken)) return false;
            if (isStaleApprovalError(error)) {
                try {
                    await reloadSnapshot(frm, { force: true });
                } catch (reloadError) {
                    console.error("Cost snapshot reload failed after stale cancel", reloadError);
                }
                if (!documentStillCurrent(frm, session.docToken)) return false;
                hideDialog(frm, CANCEL_DIALOG_KEY);
                frappe.msgprint({
                    title: translate("Cancel final price approval"),
                    message: translate("The price approval changed since this page was loaded. Refresh and review before cancelling."),
                    indicator: "orange",
                });
                reconcile(frm);
                return false;
            }
            frappe.msgprint({
                title: translate("Could not cancel the final price approval"),
                message: errorMessage(
                    error,
                    translate("Could not cancel the final price approval.")
                ),
                indicator: "red",
            });
            return false;
        } finally {
            if (documentStillCurrent(frm, session.docToken)) {
                frm[CANCELLING_KEY] = false;
                if (frm[CANCEL_DIALOG_KEY] === dialog && dialog.get_primary_btn) {
                    dialog.get_primary_btn()
                        .prop("disabled", false)
                        .text(translate("Cancel final price approval"));
                }
                reconcile(frm);
            } else if (frm) {
                frm[CANCELLING_KEY] = false;
            }
        }
    }

    /** Opens the approve dialog; kept as `approve` for existing callers/tests. */
    function approve(frm) {
        return openApproveDialog(frm);
    }

    function cancel(frm) {
        return openCancelDialog(frm);
    }

    function bind(frm) {
        const root = costRoot(frm);
        if (!root || root[BOUND_KEY]) return;
        root[BOUND_KEY] = true;
        root.addEventListener("click", (event) => {
            const live = window.cur_frm;
            if (!live || live.doctype !== "Door Cutting Order") return;

            const expand = event.target && event.target.closest
                ? event.target.closest("[data-expand-approval-note]")
                : null;
            if (expand && root.contains(expand)) {
                event.preventDefault();
                const noteRoot = expand.closest("[data-approval-note]");
                const text = noteRoot && noteRoot.querySelector("[data-approval-note-text]");
                if (text) {
                    text.classList.remove("is-collapsed");
                    expand.remove();
                }
                return;
            }

            const approveBtn = event.target && event.target.closest
                ? event.target.closest("[data-approve-final-price]")
                : null;
            if (approveBtn && root.contains(approveBtn)) {
                event.preventDefault();
                openApproveDialog(live);
                return;
            }

            const cancelBtn = event.target && event.target.closest
                ? event.target.closest("[data-cancel-final-price]")
                : null;
            if (cancelBtn && root.contains(cancelBtn)) {
                event.preventDefault();
                openCancelDialog(live);
            }
        });
    }

    window.AlmdinaFinalPriceApprovalUX = Object.freeze({
        reconcile,
        approve,
        cancel,
        openApproveDialog,
        openCancelDialog,
        hasApproveCapability,
        hasCancelCapability,
        canSeeInvalidationToast,
        hasUnsavedChanges,
        actionsTrusted,
        panelHtml,
        notifyAutoInvalidation,
        consumeInvalidationSignal,
        syncFormPriceApprovalFields,
        afterOrderSave,
        capturePriorPriceApprovalStatus,
        disposeDialogs,
        NOTE_MAX,
    });
})();
