(() => {
    "use strict";

    if (window.AlmdinaWorkspaceFreshnessUX) return;

    const STYLE_ID = "dco-workspace-freshness-ux-v1";
    const BANNER_CLASS = "dco-workspace-freshness-banner";

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
                content:"بانتظار التحديث";display:inline-flex;align-items:center;min-height:32px;padding:5px 10px;
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
                title: __("تغيّر أساس تسعير درفة خاصة"),
                body: __("تم تغيير القياس أو العدد أو نوع القطعة. السعر المعتمد السابق لم يعد صالحًا، ولن يُعامل كقيمة حالية. احفظ الطلب لتثبيت التغيير ثم أدخل السعر الجديد."),
            };
        }
        if (reason === "plan_recalculation_required") {
            return {
                title: __("التكلفة بانتظار خطة القص الجديدة"),
                body: __("تم حفظ تغييرات تؤثر على توزيع القطع. تكلفة الألواح والقص لن تعتبر نهائية حتى إعادة حساب خطة القص وحفظ النتيجة الجديدة."),
            };
        }
        if (reason === "plan_changed") {
            return {
                title: __("جاري مزامنة التكلفة"),
                body: __("تم تغيير خطة القص المحفوظة. يتم تحديث التكلفة من النسخة المعتمدة على الخادم."),
            };
        }
        return {
            title: __("بيانات التكلفة تحتاج تحديثًا"),
            body: __("تم تغيير بيانات تؤثر على التكلفة. القيم السابقة معروضة كسياق فقط ولا تعتبر نهائية حتى الحفظ والتحديث."),
        };
    }

    function renderCostBanner(frm, state) {
        const wrapper = costWrapper(frm);
        if (!wrapper) return;
        wrapper.attr("data-almdina-cost-freshness", String(state && state.freshness || "unknown"));
        wrapper.children(`.${BANNER_CLASS}`).remove();
        if (!state || state.freshness !== "stale") return;

        const copy = staleMessage(state.staleReason);
        wrapper.prepend(`
            <div class="${BANNER_CLASS}" role="status" aria-live="polite">
                <span class="dco-freshness-icon" aria-hidden="true">⚠</span>
                <div><strong>${frappe.utils.escape_html(copy.title)}</strong>${frappe.utils.escape_html(copy.body)}</div>
            </div>
        `);
    }

    function money(value) {
        const number = Number(value || 0);
        if (!Number.isFinite(number)) return "0.00";
        return number.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
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
                ? ` ${__("السعر السابق")}: $${money(previous)} — `
                : " ";
            card.append(`
                <div class="dco-special-price-basis-stale-note">
                    ${frappe.utils.escape_html(previousText + __("لم يعد صالحًا بعد تغيير أساس التسعير، ولن يدخل كقيمة نهائية."))}
                </div>
            `);
        });
    }

    function protectFinancialActions(frm, state) {
        const wrapper = costWrapper(frm);
        if (!wrapper) return;
        const stale = Boolean(state && state.freshness === "stale");
        const buttons = wrapper.find(".dco-print-customer-invoice, .dco-secure-print-customer-invoice");
        buttons.each(function syncButton() {
            const button = $(this);
            if (stale) {
                button.attr("data-almdina-freshness-disabled", "1");
                button.prop("disabled", true);
                button.attr("aria-disabled", "true");
                button.attr("title", __("حدّث التكلفة أولًا قبل طباعة فاتورة نهائية."));
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
    });
})();