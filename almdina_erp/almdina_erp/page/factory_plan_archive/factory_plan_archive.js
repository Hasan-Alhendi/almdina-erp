frappe.pages["factory-plan-archive"].on_page_load = function (wrapper) {
    "use strict";

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

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }


    const METHODS = Object.freeze({
        context: "almdina_erp.almdina_erp.services.archive_service.get_archive_context",
        archive: "almdina_erp.almdina_erp.services.archive_service.archive_approved_plan_pdf",
    });
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: translate("Approved cutting plans archive"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");
    let rows = [];
    let requestId = 0;
    let searchControl = null;

    injectStyles();
    page.set_primary_action(translate("Refresh"), load, "refresh");
    if (window.AlmdinaPageRevisit) window.AlmdinaPageRevisit.refreshOnRevisit(wrapper, load);
    load();

    frappe.pages["factory-plan-archive"].on_page_hide = function () {
        disposeControls();
    };

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function uiButton(options = {}) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.button !== "function") {
            throw new Error("AlmdinaUi.button is required for factory plan archive rendering");
        }
        return ui.button(options);
    }

    function uiControl(options = {}) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.control !== "function") {
            throw new Error("AlmdinaUi.control is required for factory plan archive rendering");
        }
        return ui.control(options);
    }

    function disposeControls() {
        if (searchControl) {
            searchControl.dispose();
            searchControl = null;
        }
    }

    function injectStyles() {
        if (document.getElementById("almdina-plan-archive-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-plan-archive-style";
        style.textContent = `
            .apa-shell{display:grid;gap:12px}.apa-hero{padding:18px;border:1px solid var(--border-color,#e5e7eb);border-radius:15px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f8fafb))}.apa-hero h3{margin:0 0 6px;font-size:19px;font-weight:800}.apa-hero p{margin:0;color:var(--text-muted,#667085);line-height:1.8}.apa-tools{display:flex;gap:10px;align-items:center}.apa-list{display:grid;gap:10px}.apa-card{padding:14px;border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff);display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center}.apa-title{font-size:15px;font-weight:800}.apa-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.apa-chip{padding:5px 9px;border-radius:999px;background:var(--subtle-fg,#f5f7f9);font-size:11px;font-weight:700}.apa-card .btn{min-height:40px;border-radius:9px;font-weight:700}.apa-result{margin-top:10px;padding:11px;border-radius:10px;background:#eaf8ef;color:#166534;font-size:12px}.apa-empty{padding:32px;text-align:center;border:1px dashed var(--border-color,#d8dee4);border-radius:14px;color:var(--text-muted,#667085);background:var(--subtle-fg,#fafafa)}@media(max-width:700px){.apa-card{grid-template-columns:1fr}.apa-card .btn{width:100%}}
        `;
        document.head.appendChild(style);
    }

    function loading(message) {
        disposeControls();
        $body.html(`<div class="almdina-ui apa-shell alm-page alm-page--admin" dir="${uiDirection()}"><div class="apa-empty">${esc(message)}</div></div>`);
    }

    function load() {
        const activeRequest = ++requestId;
        loading(translate("Loading orders with approved plans..."));
        return frappe.call({ method: METHODS.context, freeze: false }).then(response => {
            if (activeRequest !== requestId) return;
            rows = (response.message && response.message.orders) || [];
            render();
        }).catch(error => {
            if (activeRequest !== requestId) return;
            loading(error && error.message ? error.message : translate("Could not load the plans archive."));
        });
    }

    function mountSearchControl() {
        disposeControls();
        searchControl = uiControl({
            parent: $body.find(".apa-tools"),
            fieldname: "search",
            fieldtype: "Data",
            label: translate("Search"),
            placeholder: translate("Search by order number or customer name..."),
            className: "apa-search-control",
            onChange: renderRows,
        });
    }

    function render() {
        $body.html(`
            <div class="almdina-ui apa-shell alm-page alm-page--admin" dir="${uiDirection()}">
                <section class="apa-hero">
                    <h3>${translate("Fixed official copy for each approved plan")}</h3>
                    <p>${translate("The archive creates a private PDF file saved with the order. If the file already exists, no duplicate copy will be created.")}</p>
                </section>
                <div class="apa-tools"></div>
                <section class="apa-list"></section>
            </div>
        `);
        mountSearchControl();
        renderRows();
    }

    function currentSearchQuery() {
        if (!searchControl) return "";
        return String(searchControl.getValue() || "").trim().toLowerCase();
    }

    function renderRows() {
        const query = currentSearchQuery();
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
                        <span class="apa-chip">${translate("Date")}: ${esc(row.order_date || "")}</span>
                        <span class="apa-chip">${translate("Backup copy")}: ${esc(row.revision || 1)}</span>
                        <span class="apa-chip">${translate("Plan")}: ${esc(row.approved_plan || "")}</span>
                        <span class="apa-chip">${esc(translate(row.status || ""))}</span>
                    </div>
                    <div class="apa-result" style="display:none"></div>
                </div>
                ${uiButton({
                    label: translate("Archive official PDF"),
                    variant: "primary",
                    className: "apa-archive",
                })}
            </article>
        `).join("");
        $body.find(".apa-list").html(
            html || `<div class="apa-empty">${translate("No matching orders with an approved plan.")}</div>`
        );
        bindArchiveButtons();
    }

    function bindArchiveButtons() {
        $body.find(".apa-archive").on("click", function () {
            const $card = $(this).closest(".apa-card");
            const orderName = String($card.data("order") || "");
            const $result = $card.find(".apa-result");
            frappe.confirm(
                translate("Do you want to create or retrieve the official approved copy for this order?"),
                () => frappe.call({
                    method: METHODS.archive,
                    args: { order_name: orderName },
                    freeze: true,
                    freeze_message: translate("Creating official PDF file..."),
                }).then(response => {
                    const data = response.message || {};
                    const link = data.file_url
                        ? `<a class="btn btn-default btn-sm" href="${esc(data.file_url)}" target="_blank" rel="noopener">${translate("Open archived file")}</a>`
                        : "";
                    $result.show().html(`
                        <b>${data.already_archived ? translate("File already exists.") : translate("File archived successfully.")}</b>
                        <div style="margin-top:7px">${link}</div>
                    `);
                })
            );
        });
    }
};
