(() => {
    "use strict";

    if (window.AlmdinaCostPageLayoutUX) return;

    const STYLE_ID = "dco-cost-page-layout-ux-v2";
    const COST_API_FLAG = "__almdinaCostPageLayoutUX";
    const INTERNAL_REPORT_CLASS = "dco-secure-print-internal-cost-report";

    function costWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        return field && field.$wrapper ? field.$wrapper : $();
    }

    function sectionByTitle(wrapper, title) {
        return wrapper.find(".dco-cost-section").filter(function matchSection() {
            const heading = $(this).children(".dco-cost-section-title").find("h4").first();
            return heading.length && heading.text().trim() === title;
        }).first();
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .${INTERNAL_REPORT_CLASS}{display:none!important}
            .dco-cost-actions-bar:empty{display:none!important}
            .dco-cost-invoice-section>.dco-cost-section-title{align-items:center;gap:14px}
            .dco-cost-invoice-heading{display:grid;gap:3px;min-width:0;flex:1}
            .dco-cost-invoice-heading>h4{margin:0}
            .dco-cost-invoice-heading>span{display:block;max-width:100%;text-align:right}
            .dco-cost-invoice-actions{display:flex;align-items:center;justify-content:flex-start;gap:7px;flex:0 0 auto;margin-inline-start:auto}
            .dco-cost-invoice-actions .btn{width:auto!important;min-height:32px;padding:6px 12px;border-radius:9px;font-size:11px;font-weight:850;white-space:nowrap;box-shadow:none}
            .dco-cost-measurements-section>.dco-cost-section-title{cursor:default}
            .dco-cost-measurements-section.is-collapsed>:not(.dco-cost-section-title){display:none!important}
            .dco-cost-measurements-title{display:flex;align-items:center;justify-content:space-between;gap:12px;overflow:hidden}
            .dco-cost-measurements-title-main{display:flex;align-items:center;gap:8px;min-width:max-content;flex:0 0 auto;white-space:nowrap;isolation:isolate}
            .dco-cost-measurements-title-main h4{margin:0;white-space:nowrap;flex:0 0 auto;position:relative;z-index:1}
            .dco-cost-measurements-section>.dco-cost-measurements-title>span{min-width:0;flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
            .dco-cost-measurements-toggle{display:inline-grid;place-items:center;width:26px;height:26px;min-width:26px;max-width:26px;flex:0 0 26px;padding:0;overflow:hidden;position:relative;border:1px solid var(--border-color,#dfe4e8);border-radius:7px;background:var(--card-bg,#fff);color:var(--text-muted,#66727d);cursor:pointer;transition:background-color .15s ease,border-color .15s ease,color .15s ease;font-size:0;line-height:1;user-select:none}
            .dco-cost-measurements-toggle::before,.dco-cost-measurements-toggle::after{content:none!important;display:none!important}
            .dco-cost-measurements-toggle:hover{background:var(--subtle-fg,#f3f5f7);color:var(--text-color,#26313b)}
            .dco-cost-measurements-toggle:focus-visible{outline:2px solid var(--primary,#2490ef);outline-offset:2px}
            .dco-cost-measurements-toggle-icon{display:block!important;font-size:17px!important;line-height:1!important;transform:rotate(0deg);transition:transform .16s ease}
            .dco-cost-measurements-toggle[aria-expanded="true"] .dco-cost-measurements-toggle-icon{transform:rotate(180deg)}
            .dco-cost-measurements-toggle-label{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
            @media(max-width:760px){
                .dco-cost-invoice-section>.dco-cost-section-title{display:flex!important;flex-direction:row!important;align-items:center!important}
                .dco-cost-invoice-actions{margin-inline-start:0}
                .dco-cost-invoice-actions .btn{padding:6px 9px;font-size:10px}
                .dco-cost-measurements-title{display:flex!important;flex-direction:row!important;align-items:center!important}
            }
        `;
        document.head.appendChild(style);
    }

    function measurementExpanded(frm) {
        if (frm.__almdina_cost_measurements_expanded === undefined) {
            frm.__almdina_cost_measurements_expanded = false;
        }
        return Boolean(frm.__almdina_cost_measurements_expanded);
    }

    function applyMeasurementState(frm, section, control) {
        const expanded = measurementExpanded(frm);
        section.toggleClass("is-collapsed", !expanded);
        control.attr("aria-expanded", expanded ? "true" : "false");
        control.find(".dco-cost-measurements-toggle-label").text(
            expanded ? __("طي جدول قياسات الطلب") : __("عرض جدول قياسات الطلب")
        );
    }

    function toggleMeasurements(frm, section, control) {
        frm.__almdina_cost_measurements_expanded = !measurementExpanded(frm);
        applyMeasurementState(frm, section, control);
    }

    function ensureMeasurementToggle(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper.length) return false;
        const section = sectionByTitle(wrapper, "جدول قياسات الطلب");
        if (!section.length) return false;

        section.addClass("dco-cost-measurements-section");
        const header = section.children(".dco-cost-section-title").first();
        if (!header.length) return false;
        header.addClass("dco-cost-measurements-title");

        let main = header.children(".dco-cost-measurements-title-main").first();
        if (!main.length) {
            main = $('<div class="dco-cost-measurements-title-main"></div>');
            const heading = header.children("h4").first();
            if (heading.length) {
                heading.before(main);
                main.append(heading);
            } else {
                header.prepend(main);
            }
        }

        let control = main.children(".dco-cost-measurements-toggle").first();
        if (!control.length) {
            control = $('<span class="dco-cost-measurements-toggle" role="button" tabindex="0"><span class="dco-cost-measurements-toggle-icon" aria-hidden="true">⌄</span><span class="dco-cost-measurements-toggle-label"></span></span>');
            main.prepend(control);
        }
        control
            .off("click.almdinaCostMeasurements keydown.almdinaCostMeasurements")
            .on("click.almdinaCostMeasurements", event => {
                event.preventDefault();
                event.stopPropagation();
                toggleMeasurements(frm, section, control);
            })
            .on("keydown.almdinaCostMeasurements", event => {
                if (event.key !== "Enter" && event.key !== " ") return;
                event.preventDefault();
                event.stopPropagation();
                toggleMeasurements(frm, section, control);
            });
        applyMeasurementState(frm, section, control);
        return true;
    }

    function moveInvoiceActions(frm) {
        const wrapper = costWrapper(frm);
        if (!wrapper.length) return false;
        const section = wrapper.find(".dco-cost-invoice-section").first();
        const header = section.children(".dco-cost-section-title").first();
        if (!header.length) return false;

        let heading = header.children(".dco-cost-invoice-heading").first();
        if (!heading.length) {
            heading = $('<div class="dco-cost-invoice-heading"></div>');
            const title = header.children("h4").first();
            const subtitle = header.children("span").first();
            header.prepend(heading);
            if (title.length) heading.append(title);
            if (subtitle.length) heading.append(subtitle);
        }

        let actions = wrapper.find(".dco-cost-actions").first();
        if (!actions.length) {
            actions = $('<div class="dco-cost-actions"></div>');
        }
        actions.addClass("dco-cost-invoice-actions");
        header.append(actions);
        wrapper.find(".dco-cost-actions-bar").each(function removeEmptyBar() {
            if (!$(this).find(".dco-cost-actions").length) $(this).remove();
        });
        return true;
    }

    function enhance(frm) {
        if (!frm) return false;
        installStyles();
        const measurementReady = ensureMeasurementToggle(frm);
        const actionsReady = moveInvoiceActions(frm);
        return measurementReady || actionsReady;
    }

    function wrapCostPresenter() {
        const original = window.AlmdinaOrderCostUX;
        if (!original || original[COST_API_FLAG] || typeof original.render !== "function") return false;

        const enhanced = {
            ...original,
            [COST_API_FLAG]: true,
            render(frm) {
                const result = original.render(frm);
                enhance(frm);
                requestAnimationFrame(() => enhance(frm));
                return result;
            },
        };
        if (typeof original.refreshInvoiceSection === "function") {
            enhanced.refreshInvoiceSection = function refreshInvoiceSection(frm) {
                const result = original.refreshInvoiceSection(frm);
                enhance(frm);
                requestAnimationFrame(() => enhance(frm));
                return result;
            };
        }
        window.AlmdinaOrderCostUX = Object.freeze(enhanced);
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
    });

    wrapCostPresenter();
    const current = window.cur_frm;
    if (current && current.doctype === "Door Cutting Order") {
        requestAnimationFrame(() => install(current));
    }

    window.AlmdinaCostPageLayoutUX = Object.freeze({
        enhance,
        install,
    });
})();
