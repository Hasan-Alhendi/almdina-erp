frappe.pages["factory-plan-archive"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        context: "almdina_erp.almdina_erp.services.archive_service.get_archive_context",
        archive: "almdina_erp.almdina_erp.services.archive_service.archive_approved_plan_pdf",
    });
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("أرشيف خطط القص المعتمدة"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");
    let rows = [];
    let requestId = 0;

    injectStyles();
    page.set_primary_action(__("تحديث"), load, "refresh");
    if (window.AlmdinaPageRevisit) window.AlmdinaPageRevisit.refreshOnRevisit(wrapper, load);
    load();

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function injectStyles() {
        if (document.getElementById("almdina-plan-archive-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-plan-archive-style";
        style.textContent = `
            .apa-shell{direction:rtl;display:grid;gap:12px}.apa-hero{padding:18px;border:1px solid var(--border-color,#e5e7eb);border-radius:15px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f8fafb))}.apa-hero h3{margin:0 0 6px;font-size:19px;font-weight:800}.apa-hero p{margin:0;color:var(--text-muted,#667085);line-height:1.8}.apa-tools{display:flex;gap:10px;align-items:center}.apa-search{width:100%;min-height:42px;border:1px solid var(--border-color,#d8dee4);border-radius:10px;padding:8px 12px;background:var(--control-bg,#fff);color:var(--text-color,#1f2937)}.apa-list{display:grid;gap:10px}.apa-card{padding:14px;border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff);display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center}.apa-title{font-size:15px;font-weight:800}.apa-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.apa-chip{padding:5px 9px;border-radius:999px;background:var(--subtle-fg,#f5f7f9);font-size:11px;font-weight:700}.apa-card .btn{min-height:40px;border-radius:9px;font-weight:700}.apa-result{margin-top:10px;padding:11px;border-radius:10px;background:#eaf8ef;color:#166534;font-size:12px}.apa-empty{padding:32px;text-align:center;border:1px dashed var(--border-color,#d8dee4);border-radius:14px;color:var(--text-muted,#667085);background:var(--subtle-fg,#fafafa)}@media(max-width:700px){.apa-card{grid-template-columns:1fr}.apa-card .btn{width:100%}}
        `;
        document.head.appendChild(style);
    }

    function loading(message) {
        $body.html(`<div class="apa-shell"><div class="apa-empty">${esc(message)}</div></div>`);
    }

    function load() {
        const activeRequest = ++requestId;
        loading(__("جاري تحميل الطلبات ذات الخطط المعتمدة..."));
        return frappe.call({ method: METHODS.context, freeze: false }).then(response => {
            if (activeRequest !== requestId) return;
            rows = (response.message && response.message.orders) || [];
            render();
        }).catch(error => {
            if (activeRequest !== requestId) return;
            loading(error && error.message ? error.message : __("تعذر تحميل أرشيف الخطط."));
        });
    }

    function render() {
        $body.html(`
            <div class="apa-shell">
                <section class="apa-hero">
                    <h3>${__("نسخة رسمية ثابتة لكل خطة معتمدة")}</h3>
                    <p>${__("ينشئ الأرشيف ملف PDF خاصًا محفوظًا مع الطلب. إذا كان الملف موجودًا مسبقًا فلن يتم إنشاء نسخة مكررة.")}</p>
                </section>
                <div class="apa-tools"><input class="apa-search" type="search" placeholder="${__("ابحث برقم الطلب أو اسم الزبون...")}"></div>
                <section class="apa-list"></section>
            </div>
        `);
        $body.find(".apa-search").on("input", renderRows);
        renderRows();
    }

    function renderRows() {
        const query = String($body.find(".apa-search").val() || "").trim().toLowerCase();
        const filtered = rows.filter(row =>
            !query || [row.name, row.customer, row.approved_plan]
                .some(value => String(value || "").toLowerCase().includes(query))
        );
        const html = filtered.map(row => `
            <article class="apa-card" data-order="${esc(row.name)}">
                <div>
                    <div class="apa-title"><a href="/app/door-cutting-order/${encodeURIComponent(row.name)}">${esc(row.name)}</a></div>
                    <div class="text-muted" style="margin-top:3px">${esc(row.customer || "—")}</div>
                    <div class="apa-meta">
                        <span class="apa-chip">${__("التاريخ")}: ${esc(row.order_date || "")}</span>
                        <span class="apa-chip">${__("النسخة")}: ${esc(row.revision || 1)}</span>
                        <span class="apa-chip">${__("الخطة")}: ${esc(row.approved_plan || "")}</span>
                        <span class="apa-chip">${esc(__(row.status || ""))}</span>
                    </div>
                    <div class="apa-result" style="display:none"></div>
                </div>
                <button type="button" class="btn btn-primary apa-archive">${__("أرشفة PDF الرسمي")}</button>
            </article>
        `).join("");
        $body.find(".apa-list").html(
            html || `<div class="apa-empty">${__("لا توجد طلبات مطابقة ذات خطة معتمدة.")}</div>`
        );
        bindArchiveButtons();
    }

    function bindArchiveButtons() {
        $body.find(".apa-archive").on("click", function () {
            const $card = $(this).closest(".apa-card");
            const orderName = String($card.data("order") || "");
            const $result = $card.find(".apa-result");
            frappe.confirm(
                __("هل تريد إنشاء أو استرجاع النسخة الرسمية المعتمدة لهذا الطلب؟"),
                () => frappe.call({
                    method: METHODS.archive,
                    args: { order_name: orderName },
                    freeze: true,
                    freeze_message: __("جاري إنشاء ملف PDF الرسمي..."),
                }).then(response => {
                    const data = response.message || {};
                    const link = data.file_url
                        ? `<a class="btn btn-default btn-sm" href="${esc(data.file_url)}" target="_blank" rel="noopener">${__("فتح الملف المؤرشف")}</a>`
                        : "";
                    $result.show().html(`
                        <b>${data.already_archived ? __("الملف موجود مسبقًا.") : __("تمت أرشفة الملف بنجاح.")}</b>
                        <div style="margin-top:7px">${link}</div>
                    `);
                })
            );
        });
    }
};
