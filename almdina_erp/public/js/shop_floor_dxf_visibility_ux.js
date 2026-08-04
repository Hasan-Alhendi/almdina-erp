(() => {
    "use strict";

    if (window.__almdinaShopFloorDxfVisibilityLoaded) return;
    window.__almdinaShopFloorDxfVisibilityLoaded = true;

    const DETAIL_METHOD =
        "almdina_erp.almdina_erp.services.shop_floor_query_service.get_order_shop_floor_detail";
    const DXF_CAPABILITIES = Object.freeze([
        "view_drawing_workspace",
        "export_dxf",
        "upload_dxf",
        "replace_dxf",
        "approve_dxf",
    ]);
    let scheduled = false;

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function isShopFloorRoute() {
        const route = String((frappe.get_route_str && frappe.get_route_str()) || "").toLowerCase();
        return route.includes("shop-floor-inbox");
    }

    function authorized(detail) {
        const capabilities = detail && detail.document_capabilities;
        return Boolean(
            capabilities
            && DXF_CAPABILITIES.some(capability => capabilities[capability] === true)
        );
    }

    function injectLink(card, detail) {
        if (!card || !detail || !detail.production_dxf || !authorized(detail)) return;
        if (card.querySelector(".almdina-sf-authorized-dxf")) return;

        const actions = card.querySelector(".almdina-sf-actions");
        const pieces = card.querySelector(".almdina-sf-pieces-wrap, .almdina-sf-empty");
        const block = document.createElement("div");
        block.className = "almdina-sf-authorized-dxf";
        block.style.marginBottom = "10px";
        block.innerHTML = `
            <a class="btn btn-default" href="${esc(detail.production_dxf)}" target="_blank" rel="noopener">
                ${__("تنزيل DXF الإنتاج")}
            </a>
            <span class="text-muted"> · ${esc(__(detail.drawing_dxf_status || ""))}</span>`;

        if (actions && actions.nextSibling) {
            actions.parentNode.insertBefore(block, actions.nextSibling);
        } else if (pieces) {
            pieces.parentNode.insertBefore(block, pieces);
        } else {
            card.appendChild(block);
        }
    }

    function hydrateCard(card) {
        if (!card || card.dataset.almdinaDxfHydrating === "1") return;
        if (card.querySelector(".almdina-sf-authorized-dxf")) return;

        const heading = card.querySelector(".almdina-sf-detail-title");
        const orderName = String(heading && heading.textContent || "").trim();
        if (!orderName) return;

        card.dataset.almdinaDxfHydrating = "1";
        frappe.call({
            method: DETAIL_METHOD,
            args: { order_name: orderName },
            freeze: false,
        }).then(response => {
            const detail = response.message || {};
            const currentHeading = String(
                card.querySelector(".almdina-sf-detail-title")?.textContent || ""
            ).trim();
            if (currentHeading !== orderName) return;
            injectLink(card, detail);
        }).catch(error => {
            if (error && error.exc_type !== "PermissionError") {
                console.debug("Could not refresh authorized DXF link", error);
            }
        }).finally(() => {
            delete card.dataset.almdinaDxfHydrating;
        });
    }

    function apply() {
        scheduled = false;
        if (!window.frappe || !isShopFloorRoute()) return;
        document
            .querySelectorAll(".shop-floor-detail > .frappe-card")
            .forEach(hydrateCard);
    }

    function schedule() {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(apply);
    }

    const observer = new MutationObserver(schedule);
    observer.observe(document.documentElement, { childList: true, subtree: true });

    if (window.jQuery) {
        window.jQuery(document).on("app_ready.almdinaDxfVisibility", schedule);
    }
    if (frappe.router) frappe.router.on("change", schedule);
})();
