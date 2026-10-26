(() => {
    "use strict";

    if (window.AlmdinaWorkspaceFreshnessUX) return;

    const STYLE_ID = "dco-workspace-freshness-ux-v1";
    const BANNER_CLASS = "dco-workspace-freshness-banner";

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
                text = text.split("{" + index + "}").join(String(value));
            });
        }
        return text;
    }

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function costOwner() {
        return window.AlmdinaCostWorkspaceState || null;
    }

    function costState(frm) {
        const owner = costOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function previewState(frm) {
        const owner = window.AlmdinaPlanPreviewSession;
        return owner && typeof owner.snapshot === "function"
            ? owner.snapshot(frm)
            : null;
    }

    function costWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper && field.$wrapper.length ? field.$wrapper : null;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .${BANNER_CLASS}{
                display:flex;align-items:flex-start;gap:10px;margin:0 0 12px;padding:11px 13px;
                border:1px solid rgba(190,125,25,.34);border-radius:12px;background:rgba(190,125,25,.085);
                color:#77500f;font-size:11px;font-weight:750;line-height:1.65;
            }
            .${BANNER_CLASS}.is-preview{
                border-color:color-mix(in srgb, var(--alm-primary, #172033) 28%, transparent);background:color-mix(in srgb, var(--alm-primary, #172033) 6%, transparent);color:var(--text-color,#26313b);
            }
            .${BANNER_CLASS}.is-calculating{
                border-color:color-mix(in srgb, var(--alm-primary, #172033) 32%, transparent);background:color-mix(in srgb, var(--alm-primary, #172033) 8%, transparent);color:#1d4f7a;
            }
            .${BANNER_CLASS} strong{display:block;margin-bottom:2px;font-size:12px;font-weight:900}
            .${BANNER_CLASS} .dco-freshness-icon{font-size:17px;line-height:1.25}
            [data-fieldname="order_cost_invoice_html"][data-almdina-cost-freshness="stale"] .dco-cost-section,
            [data-fieldname="order_cost_invoice_html"][data-almdina-cost-freshness="stale"] .dco-cost-table-wrap{
                opacity:.72;
            }
            [data-fieldname="order_cost_invoice_html"][data-almdina-cost-freshness="stale"] .dco-invoice-total-card{
                position:relative;border-color:rgba(190,125,25,.42)!important;background:rgba(190,125,25,.055)!important;
            }
            [data-fieldname="order_cost_invoice_html"][data-almdina-cost-freshness="stale"] .dco-invoice-total-card b{
                display:none!important;
            }
            [data-fieldname="order_cost_invoice_html"][data-almdina-cost-freshness="stale"] .dco-invoice-total-card::after{
                content:attr(data-dco-pending-update);display:inline-flex;align-items:center;min-height:32px;padding:5px 10px;
                border-radius:999px;background:#fff3d8;color:#875812;font-size:11px;font-weight:900;
            }
            .dco-special-price-card.is-basis-stale{
                border-color:rgba(190,125,25,.48)!important;background:rgba(190,125,25,.045)!important;
            }
            .dco-special-price-card.is-basis-stale .dco-inline-price-input{
                text-decoration:line-through;color:#8a6a34!important;
            }
            .dco-special-price-basis-stale-note{
                grid-column:1/-1;padding:8px 10px;border-radius:9px;background:#fff3d8;color:#77500f;
                font-size:10px;font-weight:800;line-height:1.55;
            }
            @media(max-width:560px){
                .${BANNER_CLASS}{font-size:10.5px;padding:10px 11px}
            }
        `;
        document.head.appendChild(style);
    }

    function staleMessage(reason) {
        if (reason === "special_price_basis_changed") {
            return {
                title: translate("The special door pricing basis changed"),
                body: translate("The measurement, quantity, or piece type changed. The previous approved price is no longer valid and will not be treated as a current value. Save the order to keep the change, then enter the new price."),
            };
        }
        if (reason === "plan_recalculation_required") {
            const job = window.AlmdinaPlanRecalculationJob;
            const frm = window.cur_frm;
            if (job && frm && typeof job.isActive === "function" && job.isActive(frm)) {
                const state = typeof job.snapshot === "function" ? job.snapshot(frm) : null;
                if (state && state.stalled) {
                    return {
                        title: translate("The cost calculation is still waiting"),
                        body: translate("The measurements were saved. Board and cutting costs will update when the background worker starts or after a manual recalculation."),
                    };
                }
                return {
                    title: translate("Recalculating the cutting plan and cost in the background"),
                    body: translate("The changes were saved. Board and cutting costs are not final until the automatic calculation finishes."),
                };
            }
            return {
                title: translate("The cost is waiting for the new cutting plan"),
                body: translate("Saved changes affect piece placement. Board and cutting costs are not final until the cutting plan is recalculated and the new result is saved."),
            };
        }
        if (reason === "plan_changed") {
            return {
                title: translate("Synchronizing the cost"),
                body: translate("The saved cutting plan changed. The cost is being updated from the server copy."),
            };
        }
        return {
            title: translate("The cost data needs an update"),
            body: translate("Data that affects the cost changed. Previous values are shown as context only and are not final until they are saved and refreshed."),
        };
    }

    function money(value) {
        const number = Number(value || 0);
        if (!Number.isFinite(number)) return "0.00";
        return number.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function previewMessage(state) {
        if (!state || !["ready", "saving"].includes(state.status) || !state.payload) return null;
        const summary = state.payload.summary || {};
        const totals = summary.totals || {};
        const cost = summary.cost || {};
        const boards = Number(totals.required_boards || 0);
        const expected = money(cost.total_cost_usd);
        return {
            title: state.status === "saving"
                ? translate("The cutting plan preview is being applied")
                : translate("There is an unsaved plan preview"),
            body: translate("The official cost below belongs to the saved plan. The current preview uses {0} boards and its expected cost is $ {1}. Save the cutting plan to apply these values.", [String(boards), expected]),
        };
    }

    function renderCostBanner(frm, state) {
        const wrapper = costWrapper(frm);
        if (!wrapper) return;
        wrapper.attr("data-almdina-cost-freshness", String(state && state.freshness || "unknown"));
        const pendingLabel = state && state.freshness === "stale" ? translate("Waiting for update") : "";
        wrapper.find(".dco-invoice-total-card").each(function markPending() {
            const card = $(this);
            if (pendingLabel) card.attr("data-dco-pending-update", pendingLabel);
            else card.removeAttr("data-dco-pending-update");
        });
        wrapper.children(`.${BANNER_CLASS}`).remove();

        if (state && state.freshness === "stale") {
            const copy = staleMessage(state.staleReason);
            const calculating = Boolean(
                window.AlmdinaPlanRecalculationJob
                && typeof window.AlmdinaPlanRecalculationJob.isActive === "function"
                && window.AlmdinaPlanRecalculationJob.isActive(frm)
            );
            wrapper.prepend(`
                <div class="${BANNER_CLASS}${calculating ? " is-calculating" : ""}" role="status" aria-live="polite">
                    <span class="dco-freshness-icon" aria-hidden="true">${calculating ? "⏳" : "⚠"}</span>
                    <div><strong>${frappe.utils.escape_html(copy.title)}</strong>${frappe.utils.escape_html(copy.body)}</div>
                </div>
            `);
            return;
        }

        const preview = previewMessage(previewState(frm));
        if (!preview) return;
        wrapper.prepend(`
            <div class="${BANNER_CLASS} is-preview" role="status" aria-live="polite">
                <span class="dco-freshness-icon" aria-hidden="true">◉</span>
                <div><strong>${frappe.utils.escape_html(preview.title)}</strong>${frappe.utils.escape_html(preview.body)}</div>
            </div>
        `);
    }

    function markSpecialPriceBasisStale(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper) return;
        wrapper.find(".dco-special-price-basis-stale-note").remove();
        wrapper.find(".dco-special-price-card.is-basis-stale").removeClass("is-basis-stale");

        (frm.doc.pieces || []).forEach((piece) => {
            if (!piece || !piece.__almdina_special_price_basis_stale) return;
            const rowName = String(piece.name || "").replace(/"/g, "\\\"");
            const card = wrapper.find(`.dco-special-price-card[data-special-row="${rowName}"]`).first();
            if (!card.length) return;

            card.addClass("is-basis-stale");
            const input = card.find('.dco-inline-price-input[data-price-kind="special"]').first();
            if (input.length) {
                input.val("");
                input.prop("disabled", true);
                input.attr("readonly", "readonly");
            }
            const previous = Number(piece.special_shape_custom_unit_price_usd || 0);
            const previousText = previous > 0
                ? ` ${translate("Previous price")}: $${money(previous)} — `
                : " ";
            card.append(`
                <div class="dco-special-price-basis-stale-note">
                    ${frappe.utils.escape_html(previousText + translate("It is no longer valid after the pricing basis changed, and it will not be used as a final value."))}
                </div>
            `);
        });
    }

    function protectFinancialActions(frm, state) {
        const wrapper = costWrapper(frm);
        if (!wrapper) return;
        const stale = Boolean(state && state.freshness === "stale");
        const buttons = wrapper.find(".dco-print-customer-invoice, .dco-secure-print-customer-invoice, .dco-whatsapp-send-invoice");
        buttons.each(function syncButton() {
            const button = $(this);
            if (stale) {
                button.attr("data-almdina-freshness-disabled", "1");
                button.prop("disabled", true);
                button.attr("aria-disabled", "true");
                button.attr("title", translate("Update the cost before printing a final invoice."));
                return;
            }
            if (button.attr("data-almdina-freshness-disabled") === "1") {
                button.removeAttr("data-almdina-freshness-disabled");
                button.prop("disabled", false);
                button.attr("aria-disabled", "false");
                button.removeAttr("title");
            }
        });
    }

    function refresh(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return false;
        installStyles();
        const state = costState(frm);
        renderCostBanner(frm, state);
        markSpecialPriceBasisStale(frm);
        protectFinancialActions(frm, state);
        return true;
    }

    function schedule(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const context = documentContext();
        const run = () => refresh(frm);
        if (context && typeof context.scheduleFrame === "function") {
            context.scheduleFrame(frm, "workspace-freshness-ux", run);
            return;
        }
        window.requestAnimationFrame(() => {
            if (window.cur_frm === frm) run();
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
    });

    [
        "almdina:workspace-freshness-changed",
        "almdina:cost-workspace-updated",
        "almdina:plan-preview-updated",
        "almdina:plan-recalculation-updated",
        "almdina:surfaces-settled",
    ].forEach((eventName) => {
        window.addEventListener(eventName, () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") schedule(frm);
        });
    });

    window.AlmdinaWorkspaceFreshnessUX = Object.freeze({
        refresh,
        schedule,
        staleMessage,
        previewMessage,
    });
})();