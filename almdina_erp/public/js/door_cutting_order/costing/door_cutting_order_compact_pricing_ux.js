(() => {
    "use strict";

    if (window.AlmdinaCompactPricingUX) return;

    const STYLE_ID = "dco-compact-pricing-ux-v1";
    const PRESENTER_FLAG = "__almdinaCompactPricingUX";

    function costWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper ? field.$wrapper : $();
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-compact-pricing-section>.dco-cost-section-title{padding:9px 12px}
            .dco-compact-pricing-section>.dco-cost-section-title span{
                display:inline-flex;align-items:center;min-height:23px;padding:3px 8px;border-radius:999px;
                background:var(--subtle-fg,#f3f5f7);font-size:9.5px;font-weight:800;white-space:nowrap;
            }
            .dco-compact-pricing-section .dco-special-price-list{gap:6px;padding:8px 10px}
            .dco-compact-pricing-section .dco-special-price-card{
                grid-template-columns:minmax(230px,1.4fr) minmax(280px,1fr) auto!important;
                align-items:center;gap:10px;padding:7px 9px;min-height:56px;border-radius:10px;box-shadow:none;
            }
            .dco-compact-pricing-section .dco-special-price-card.is-unpriced{
                border-color:rgba(190,125,25,.32);background:rgba(190,125,25,.025);
            }
            .dco-compact-pricing-section .dco-special-price-id{
                display:flex;align-items:center;flex-wrap:wrap;gap:6px;min-width:0;
                font-size:12.5px;font-weight:900;line-height:1.35;letter-spacing:0;
            }
            .dco-compact-pricing-section .dco-special-price-id small{
                display:inline-flex!important;align-items:center;margin:0!important;padding:2px 7px;border-radius:999px;
                background:var(--subtle-fg,#f3f5f7);font-size:9.5px!important;font-weight:750!important;
                color:var(--text-muted,#687481)!important;white-space:nowrap;
            }
            .dco-compact-pricing-section .dco-special-price-id + .dco-special-price-cell{display:none!important}
            .dco-compact-pricing-section .dco-special-price-card>.dco-special-price-cell{
                display:grid;grid-template-columns:auto minmax(92px,120px) auto;align-items:center;justify-content:end;
                gap:7px;min-width:0;padding:0;background:transparent;border-radius:0;
            }
            .dco-compact-pricing-section .dco-special-price-card>.dco-special-price-cell>span{
                display:inline!important;margin:0!important;font-size:9.5px!important;font-weight:750;
                color:var(--text-muted,#687481);white-space:nowrap;
            }
            .dco-compact-pricing-section .dco-inline-price-input{
                width:100%;max-width:120px!important;min-height:30px;padding:5px 7px!important;border-radius:8px;
                font-size:12px!important;
            }
            .dco-compact-pricing-section .dco-special-price-card>.dco-special-price-cell.is-unpriced>small{
                display:inline-flex!important;align-items:center;margin:0!important;padding:3px 7px;border-radius:999px;
                background:#fff3d8;color:#875812!important;font-size:9px!important;font-weight:900;white-space:nowrap;
            }
            .dco-compact-pricing-section .dco-special-price-card>.dco-special-price-cell:not(.is-unpriced)::after{
                content:"✓ مسعّر";display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;
                background:rgba(31,130,82,.1);color:#14653d;font-size:9px;font-weight:900;white-space:nowrap;
            }
            .dco-compact-pricing-section .dco-special-price-actions{
                display:flex;flex-direction:row;align-items:center;gap:5px;min-width:0;
            }
            .dco-compact-pricing-section .dco-special-price-actions .btn{
                width:auto!important;min-height:30px;padding:4px 9px;border-radius:8px;font-size:10px;font-weight:800;white-space:nowrap;
            }
            .dco-compact-pricing-section .dco-special-price-note{
                grid-column:1/3;min-width:0;margin-top:-2px;font-size:9.5px;line-height:1.35;
                color:var(--text-muted,#687481);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
            }
            @media(max-width:900px){
                .dco-compact-pricing-section .dco-special-price-card{
                    grid-template-columns:minmax(0,1fr) auto!important;min-height:0;
                }
                .dco-compact-pricing-section .dco-special-price-card>.dco-special-price-cell{
                    grid-column:1/-1;grid-template-columns:auto minmax(92px,1fr) auto;justify-content:stretch;
                }
                .dco-compact-pricing-section .dco-special-price-note{grid-column:1/-1}
            }
            @media(max-width:560px){
                .dco-compact-pricing-section>.dco-cost-section-title{align-items:flex-start;flex-wrap:wrap}
                .dco-compact-pricing-section>.dco-cost-section-title span{white-space:normal}
                .dco-compact-pricing-section .dco-special-price-card{grid-template-columns:1fr!important}
                .dco-compact-pricing-section .dco-special-price-actions{grid-column:1}
                .dco-compact-pricing-section .dco-special-price-card>.dco-special-price-cell{
                    grid-column:1;grid-template-columns:1fr minmax(84px,110px);
                }
                .dco-compact-pricing-section .dco-special-price-card>.dco-special-price-cell.is-unpriced>small,
                .dco-compact-pricing-section .dco-special-price-card>.dco-special-price-cell:not(.is-unpriced)::after{
                    grid-column:1/-1;justify-self:start;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function isUnpriced(card) {
        return Boolean(card && card.querySelector(".dco-special-price-cell.is-unpriced"));
    }

    function compactList(list) {
        const cards = $(list).children(".dco-special-price-card").get();
        cards.forEach((card, index) => {
            card.dataset.compactOriginalIndex = String(index);
            const pending = isUnpriced(card);
            card.classList.toggle("is-unpriced", pending);
            card.classList.toggle("is-priced", !pending);
            const note = card.querySelector(".dco-special-price-note");
            if (note && note.textContent.trim()) note.title = note.textContent.trim();
        });
        cards.sort((left, right) => {
            const attention = Number(isUnpriced(right)) - Number(isUnpriced(left));
            if (attention) return attention;
            return Number(left.dataset.compactOriginalIndex) - Number(right.dataset.compactOriginalIndex);
        });
        cards.forEach(card => list.appendChild(card));
        return {
            total: cards.length,
            unpriced: cards.filter(isUnpriced).length,
        };
    }

    function enhanceSection(section) {
        const list = section.querySelector(".dco-special-price-list");
        if (!list) return false;
        section.classList.add("dco-compact-pricing-section");
        const stats = compactList(list);
        const header = section.querySelector(":scope > .dco-cost-section-title");
        const subtitle = header && header.querySelector("span");
        if (subtitle) {
            subtitle.textContent = stats.unpriced
                ? `${stats.unpriced} غير مسعّرة من ${stats.total}`
                : `تم تسعير ${stats.total}`;
            subtitle.setAttribute("aria-live", "polite");
        }
        return true;
    }

    function enhance(frm) {
        installStyles();
        const wrapper = costWrapper(frm);
        if (!wrapper.length) return false;
        let enhanced = false;
        wrapper.find(".dco-special-price-list").each(function compactPricingList() {
            const section = this.closest(".dco-cost-section");
            if (section) enhanced = enhanceSection(section) || enhanced;
        });
        return enhanced;
    }

    function wrapCostPresenter() {
        const original = window.AlmdinaOrderCostUX;
        if (!original || original[PRESENTER_FLAG] || typeof original.render !== "function") return false;

        const wrapped = {
            ...original,
            [PRESENTER_FLAG]: true,
            render(frm) {
                const result = original.render(frm);
                enhance(frm);
                requestAnimationFrame(() => enhance(frm));
                return result;
            },
        };
        if (typeof original.refreshInvoiceSection === "function") {
            wrapped.refreshInvoiceSection = function refreshInvoiceSection(frm) {
                const result = original.refreshInvoiceSection(frm);
                enhance(frm);
                requestAnimationFrame(() => enhance(frm));
                return result;
            };
        }
        window.AlmdinaOrderCostUX = Object.freeze(wrapped);
        return true;
    }

    function install(frm) {
        wrapCostPresenter();
        if (!frm) return false;
        enhance(frm);
        requestAnimationFrame(() => enhance(frm));
        return true;
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { install(frm); },
        refresh(frm) { install(frm); },
        almdina_edit_session_changed(frm) { install(frm); },
    });

    wrapCostPresenter();
    const current = window.cur_frm;
    if (current && current.doctype === "Door Cutting Order") {
        requestAnimationFrame(() => install(current));
    }

    window.AlmdinaCompactPricingUX = Object.freeze({
        enhance,
        install,
    });
})();
