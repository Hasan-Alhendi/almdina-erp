(() => {
    "use strict";

    if (window.AlmdinaFinalPriceApprovalUX) return;

    const APPROVING_KEY = "__almdinaFinalPriceApproving";
    const BOUND_KEY = "__almdinaFinalPriceApprovalBound";
    const STATUS_APPROVED = "Approved";
    const STATUS_UNAPPROVED = "Unapproved";

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

    function actionsTrusted(frm) {
        if (frm && frm[APPROVING_KEY]) return false;
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

    function costRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper) return null;
        if (typeof wrapper.get === "function") return wrapper.get(0) || null;
        return wrapper[0] || (typeof wrapper.querySelector === "function" ? wrapper : null);
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

        let actionHtml = "";
        if (!approved && hasApproveCapability(frm)) {
            const trusted = actionsTrusted(frm);
            const canApprove = Boolean(data.can_approve_final_price) && trusted;
            const blocker = data.final_price_approval_blocker;
            const title = canApprove
                ? translate("Approve final price")
                : String(
                    (blocker && blocker.message)
                    || translate("The final price is not ready to approve yet.")
                );
            const busy = Boolean(frm && frm[APPROVING_KEY]);
            if (window.AlmdinaUi && typeof window.AlmdinaUi.button === "function") {
                actionHtml = window.AlmdinaUi.button({
                    variant: "primary",
                    size: "btn-sm",
                    className: `dco-approve-final-price${busy ? " is-loading" : ""}`,
                    label: busy ? translate("Approving…") : translate("Approve final price"),
                    disabled: !(canApprove && !busy),
                    attrs: {
                        "data-approve-final-price": "",
                        title,
                        "aria-disabled": canApprove && !busy ? "false" : "true",
                    },
                });
            } else {
                actionHtml = `<button type="button"
                    class="btn alm-btn-primary btn-sm dco-approve-final-price${busy ? " is-loading" : ""}"
                    data-approve-final-price
                    ${canApprove && !busy ? "" : "disabled"}
                    title="${esc(title)}"
                    aria-disabled="${canApprove && !busy ? "false" : "true"}">
                    ${busy ? esc(translate("Approving…")) : esc(translate("Approve final price"))}
                </button>`;
            }
            if (!canApprove && blocker && blocker.message && trusted) {
                actionHtml += `<small class="dco-price-approval-blocker">${esc(blocker.message)}</small>`;
            }
        }

        const lockNote = approved
            ? `<small class="dco-price-approval-lock-note">${esc(translate("Cost settings are locked because the final price is approved."))}</small>`
            : "";

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
                ${lockNote}
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
            .dco-price-approval-copy{display:flex;flex-direction:column;align-items:flex-start;gap:4px;min-width:0}
            .dco-price-approval-status{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
            .dco-price-approval-label{font-size:11px;font-weight:800;color:var(--text-muted,#687481)}
            .dco-price-approval-badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:800;border:1px solid var(--alm-card-border,#e4e8ee);background:var(--alm-surface-muted,#f4f6f8);color:var(--alm-text-strong,#101828)}
            .dco-price-approval-badge.is-approved{border-color:color-mix(in srgb, var(--alm-success,#15803d) 35%, var(--alm-card,#ffffff));background:color-mix(in srgb, var(--alm-success,#15803d) 10%, var(--alm-card,#ffffff));color:var(--alm-success,#15803d)}
            .dco-price-approval-badge.is-unapproved{border-color:color-mix(in srgb, var(--alm-warning,#b45309) 30%, var(--alm-card,#ffffff));background:var(--alm-warning-bg,#fff7e8);color:var(--alm-warning,#b45309)}
            .dco-price-approval-badge.is-unknown{opacity:.72}
            .dco-price-approval-icon{font-weight:900;line-height:1}
            .dco-price-approval-meta,.dco-price-approval-lock-note,.dco-price-approval-blocker{display:block;max-width:220px;font-size:10px;font-weight:700;color:var(--text-muted,#687481);line-height:1.45}
            .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary{
                box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;
                min-width:var(--alm-min-width-button-compact,96px);min-height:unset;height:auto;
                padding-block:var(--alm-padding-button-compact-y,8px);padding-inline:var(--alm-padding-button-compact-x,18px);
                border-radius:var(--alm-radius-button,999px);border:1px solid var(--alm-primary,#172033);
                background:var(--alm-primary,#172033);color:var(--alm-on-primary,#fff);
                font-size:var(--alm-font-size-sm,12px);font-weight:var(--alm-font-weight-heavy,800);line-height:1.2;
                box-shadow:none;flex:0 0 auto;white-space:nowrap
            }
            .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary:hover:not(:disabled){
                background:var(--alm-primary-hover,#0f1624);border-color:var(--alm-primary-hover,#0f1624);color:var(--alm-on-primary,#fff)
            }
            .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary:focus-visible{
                outline:none;box-shadow:0 0 0 3px color-mix(in srgb, var(--alm-primary, #172033) 18%, transparent)
            }
            .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary:disabled,
            .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary.is-loading{
                opacity:.55;cursor:not-allowed;box-shadow:none
            }
            @media(max-width:560px){
                .dco-price-approval-panel{flex:1 1 auto}
                .dco-invoice-total-card .dco-approve-final-price.alm-btn-primary{flex:0 1 auto}
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

    async function reloadSnapshot(frm, { force = true } = {}) {
        const owner = stateOwner();
        if (!owner || typeof owner.load !== "function") return null;
        return owner.load(frm, { force });
    }

    function mergeApprovalIntoStore(frm, result) {
        const owner = stateOwner();
        const state = snapshot(frm);
        if (!owner || typeof owner.commit !== "function" || !state || !state.data || !result) {
            return null;
        }
        return owner.commit(frm, {
            ...state.data,
            price_approval_status: result.price_approval_status || STATUS_APPROVED,
            current_price_approval: result.current_price_approval || null,
            price_basis_token: result.price_basis_token || state.data.price_basis_token || null,
            can_approve_final_price: false,
            can_edit_cost_settings: false,
            final_price_approval_blocker: null,
            price_approval: {
                name: result.current_price_approval || null,
                approved_amount_usd: result.approved_amount_usd,
                currency: result.currency,
                cutting_plan: result.cutting_plan,
                approved_by: result.approved_by,
                approved_on: result.approved_on,
                validity_status: "Active",
                fingerprint_formula_version: result.fingerprint_formula_version,
            },
        });
    }

    async function approve(frm) {
        if (!frm || !frm.doc || frm.doctype !== "Door Cutting Order") return false;
        if (!hasApproveCapability(frm)) return false;
        if (frm[APPROVING_KEY]) return false;

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

        const docToken = captureDocument(frm);
        const transport = api();
        if (!transport || typeof transport.approveFinalPrice !== "function") return false;

        frm[APPROVING_KEY] = true;
        reconcile(frm);
        try {
            const result = await transport.approveFinalPrice(orderName, token);
            if (!documentStillCurrent(frm, docToken)) return false;
            mergeApprovalIntoStore(frm, result);
            try {
                await reloadSnapshot(frm, { force: true });
            } catch (reloadError) {
                if (!documentStillCurrent(frm, docToken)) return false;
                console.error("Cost snapshot reload failed after final-price approval", reloadError);
                frappe.msgprint({
                    title: translate("Final price approved"),
                    message: translate("The final price was approved, but the cost data could not be refreshed. Open the Cost tab again to load the latest status."),
                    indicator: "orange",
                });
            }
            if (!documentStillCurrent(frm, docToken)) return false;
            reconcile(frm);
            const editSession = window.AlmdinaCostEditSessionUX;
            if (editSession && typeof editSession.sync === "function") {
                editSession.sync(frm);
            }
            return true;
        } catch (error) {
            if (!documentStillCurrent(frm, docToken)) return false;
            if (isStaleTokenError(error)) {
                try {
                    await reloadSnapshot(frm, { force: true });
                } catch (reloadError) {
                    console.error("Cost snapshot reload failed after stale token", reloadError);
                }
                if (!documentStillCurrent(frm, docToken)) return false;
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
            if (documentStillCurrent(frm, docToken)) {
                frm[APPROVING_KEY] = false;
                reconcile(frm);
            } else if (frm) {
                frm[APPROVING_KEY] = false;
            }
        }
    }

    function bind(frm) {
        const root = costRoot(frm);
        if (!root || root[BOUND_KEY]) return;
        root[BOUND_KEY] = true;
        root.addEventListener("click", (event) => {
            const target = event.target && event.target.closest
                ? event.target.closest("[data-approve-final-price]")
                : null;
            if (!target || !root.contains(target)) return;
            event.preventDefault();
            const live = window.cur_frm;
            if (!live || live.doctype !== "Door Cutting Order") return;
            approve(live);
        });
    }

    window.AlmdinaFinalPriceApprovalUX = Object.freeze({
        reconcile,
        approve,
        hasApproveCapability,
        hasUnsavedChanges,
        actionsTrusted,
        panelHtml,
    });
})();
