frappe.pages["factory-approval-queue"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        context: "almdina_erp.almdina_erp.services.approval_queue_service.get_approval_queue_context",
        list: "almdina_erp.almdina_erp.services.approval_queue_service.get_pending_review_orders",
        approve: "almdina_erp.almdina_erp.services.approval_queue_service.approve_order_safely",
        reject: "almdina_erp.almdina_erp.services.approval_queue_service.reject_order_safely",
    });
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("قائمة مراجعة الطلبات"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");
    let requestId = 0;
    let permissions = { can_approve: false, can_reject: false };
    let activation = null;
    const modalOwner = window.AlmdinaFrontend.createDialogOwner();

    injectStyles();
    page.set_primary_action(__("تحديث"), load, "refresh");
    loading();
    const pageLifecycle = window.AlmdinaPageRevisit;
    if (!pageLifecycle || typeof pageLifecycle.bindActivationLifecycle !== "function") {
        throw new Error("Almdina page lifecycle is required for Factory Approval Queue");
    }
    activation = pageLifecycle.bindActivationLifecycle(wrapper, {
        onActivate: load,
        onDeactivate: () => {
            requestId += 1;
            modalOwner.closeAll();
        },
    });
    if (activation.isActive()) load();

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function injectStyles() {
        if (document.getElementById("almdina-approval-queue-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-approval-queue-style";
        style.textContent = `
            .aaq-shell{direction:rtl;display:grid;gap:12px}.aaq-hero{padding:18px;border:1px solid var(--border-color,#e5e7eb);border-radius:15px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f8fafb))}.aaq-hero h3{margin:0 0 6px;font-size:19px;font-weight:800}.aaq-hero p{margin:0;color:var(--text-muted,#667085);line-height:1.8}.aaq-list{display:grid;gap:10px}.aaq-card{border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff);padding:14px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center}.aaq-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.aaq-title a{font-size:15px;font-weight:800}.aaq-badge{padding:3px 8px;border-radius:999px;background:#fff4d6;color:#805b00;font-size:11px;font-weight:800}.aaq-meta{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:8px;margin-top:10px}.aaq-meta div{padding:8px;border-radius:9px;background:var(--subtle-fg,#f7f9fb);font-size:12px}.aaq-meta span{display:block;color:var(--text-muted,#667085);margin-bottom:2px}.aaq-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.aaq-actions .btn{min-height:40px;border-radius:9px;font-weight:700}.aaq-empty{padding:32px;text-align:center;border:1px dashed var(--border-color,#d8dee4);border-radius:14px;color:var(--text-muted,#667085);background:var(--subtle-fg,#fafafa)}@media(max-width:900px){.aaq-card{grid-template-columns:1fr}.aaq-actions{justify-content:stretch}.aaq-actions .btn{flex:1}.aaq-meta{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.aaq-meta{grid-template-columns:1fr}.aaq-hero{padding:15px}}
        `;
        document.head.appendChild(style);
    }

    function loading() {
        $body.html(`<div class="aaq-shell"><div class="aaq-empty">${__("جاري تحميل الطلبات المنتظرة للمراجعة...")}</div></div>`);
    }

    function renderError(error) {
        const message = error && error.message
            ? error.message
            : __("تعذر تحميل قائمة مراجعة الطلبات.");
        $body.html(`<div class="aaq-shell"><div class="aaq-empty">${esc(message)}</div></div>`);
    }

    function load() {
        if (!activation || !activation.isActive()) return Promise.resolve(null);
        const activeRequest = ++requestId;
        loading();
        return Promise.all([
            frappe.call({ method: METHODS.context, freeze: false }),
            frappe.call({ method: METHODS.list, freeze: false }),
        ]).then(([contextResponse, listResponse]) => {
            if (activeRequest !== requestId || !activation.isActive()) return;
            permissions = contextResponse.message || permissions;
            render(listResponse.message || []);
        }).catch(error => {
            if (activeRequest !== requestId || !activation.isActive()) return;
            renderError(error);
        });
    }

    function render(rows) {
        const cards = rows.map(row => {
            const actions = [];
            // Order approval was retired with the review step. Reject remains so
            // leftover Pending Review rows can return for editing / dispatch.
            if (permissions.can_reject) {
                actions.push(`<button type="button" class="btn btn-default aaq-reject">${__("رفض وإعادة للتعديل")}</button>`);
            }
            actions.push(
                `<a class="btn btn-primary" href="/app/door-cutting-order/${encodeURIComponent(row.name)}">${__("فتح وإرسال للإنتاج")}</a>`
            );
            return `
                <article class="aaq-card" data-order="${esc(row.name)}">
                    <div>
                        <div class="aaq-title">
                            <a href="/app/door-cutting-order/${encodeURIComponent(row.name)}">${esc(row.name)}</a>
                            <span class="aaq-badge">${__("عالق من المراجعة القديمة")}</span>
                        </div>
                        <div class="text-muted" style="margin-top:4px">${esc(row.customer || "—")} · ${esc(row.order_date || "")}</div>
                        <div class="aaq-meta">
                            <div><span>${__("النسخة")}</span><b>${esc(row.revision || 1)}</b></div>
                            <div><span>${__("صنف اللوح")}</span><b>${esc(row.board_description || "—")}</b></div>
                            <div><span>${__("مقاس اللوح")}</span><b>${esc(row.board_length_cm || 0)} × ${esc(row.board_width_cm || 0)} ${__("سم")}</b></div>
                            <div><span>${__("الخطة")}</span><b>${esc(row.required_boards || 0)} ${__("لوح")} · ${esc(row.waste_percent || 0)}%</b></div>
                        </div>
                    </div>
                    <div class="aaq-actions">${actions.join("")}</div>
                </article>`;
        }).join("");

        $body.html(`
            <div class="aaq-shell">
                <section class="aaq-hero">
                    <h3>${__("المراجعة والاعتماد أُلغيا")}</h3>
                    <p>${__("الطلبات تُرسل مباشرة من المسودة إلى الإنتاج. هذه الصفحة تعرض فقط الطلبات العالقة من المسار القديم إن وُجدت — افتح الطلب وأرسله للإنتاج، أو ارفضه لإعادته للتعديل.")}</p>
                </section>
                ${cards ? `<section class="aaq-list">${cards}</section>` : `<div class="aaq-empty">${__("لا توجد طلبات عالقة من المراجعة القديمة.")}</div>`}
            </div>
        `);
        bindActions();
    }

    function bindActions() {
        $body.find(".aaq-reject").on("click", function () {
            const orderName = String($(this).closest(".aaq-card").data("order") || "");
            modalOwner.track(frappe.prompt(
                [{ fieldname: "reason", fieldtype: "Small Text", label: __("سبب الرفض"), reqd: 1 }],
                values => activation.isActive() ? frappe.call({
                    method: METHODS.reject,
                    args: {
                        order_name: orderName,
                        reason: String(values.reason || "").trim(),
                    },
                    freeze: true,
                    freeze_message: __("جاري إعادة الطلب للتعديل..."),
                }).then(() => {
                    if (!activation.isActive()) return null;
                    frappe.show_alert({ message: __("تم رفض الطلب وإعادته للتعديل."), indicator: "orange" });
                    return load();
                }) : null,
                __("رفض الطلب"),
                __("تأكيد الرفض")
            ));
        });
    }
};
