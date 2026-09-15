(() => {
    "use strict";

    if (window.AlmdinaCostWorkspacePresenterAdapter) return;

    function stateOwner() {
        return window.AlmdinaCostWorkspaceState || null;
    }

    function snapshot(frm) {
        const owner = stateOwner();
        return owner && typeof owner.snapshot === "function" ? owner.snapshot(frm) : null;
    }

    function data(frm) {
        const state = snapshot(frm);
        return state && state.status === "ready" ? state.data : null;
    }

    function canView(frm) {
        const owner = stateOwner();
        return Boolean(owner && typeof owner.canView === "function" && owner.canView(frm));
    }

    function ready(frm) {
        const state = snapshot(frm);
        return Boolean(state && state.status === "ready" && state.data);
    }

    function number(value) {
        const parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function money(value) {
        return number(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function projectOrder(frm, orderSnapshot) {
        if (!frm || !frm.doc || !orderSnapshot) return;
        Object.entries(orderSnapshot).forEach(([fieldname, value]) => {
            frm.doc[fieldname] = value;
        });
        const editor = window.AlmdinaWorkspaceFieldEditor;
        if (editor && typeof editor.project === "function") {
            editor.project(frm, orderSnapshot, [
                "board_rate_usd",
                "cutting_cost_per_board_usd",
            ]);
        }
    }

    function projectPieces(frm, pieceSnapshots) {
        if (!frm || !frm.doc || !Array.isArray(frm.doc.pieces)) return;
        const byName = new Map(
            (pieceSnapshots || [])
                .filter((row) => row && row.name)
                .map((row) => [row.name, row])
        );
        frm.doc.pieces.forEach((piece) => {
            const financial = byName.get(piece && piece.name);
            if (!financial) return;
            // Inline special/clipped prices are a short-lived Cost-tab draft.
            // An asynchronous read snapshot may be older than the value the user
            // just typed, so never project over a pending draft. Save/Cancel clears
            // this marker and then reloads the authoritative snapshot normally.
            if (piece && piece.__almdina_pending_price_edit) return;
            Object.entries(financial).forEach(([fieldname, value]) => {
                if (fieldname === "name") return;
                piece[fieldname] = value;
            });
        });
    }

    function project(frm) {
        const payload = data(frm);
        if (!payload) return false;
        // Transitional read-only view projection for the existing presenter.
        // The Cost workspace store remains authoritative; no DCO persistence is used.
        projectOrder(frm, payload.order || {});
        projectPieces(frm, payload.pieces || []);
        return true;
    }

    function pendingMessage(frm) {
        const state = snapshot(frm);
        if (state && state.status === "error") {
            return __("تعذر تحميل بيانات التكلفة. أعد المحاولة.");
        }
        return __("جاري تحميل بيانات التكلفة...");
    }

    function renderPending(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper || !wrapper.length) return false;
        wrapper.html(`
            <div class="dco-cost-shell">
                <div class="dco-cost-empty">${frappe.utils.escape_html(pendingMessage(frm))}</div>
            </div>
        `);
        // Rendering is intentionally side-effect free. Form/document lifecycle
        // hooks own workspace loading through AlmdinaCostWorkspaceState.schedule().
        return true;
    }

    function previewLines(frm) {
        const payload = data(frm);
        if (!payload || !Array.isArray(payload.invoice_preview_lines)) return null;
        const pending = new Set(payload.pending_factory_price_labels || []);
        return payload.invoice_preview_lines.map((line) => {
            const description = String((line && line.description) || "");
            const isPending = pending.has(description);
            return {
                type: line.type,
                description,
                quantity: number(line.quantity),
                unit: line.unit || "",
                rate: isPending ? null : number(line.rate_usd),
                amount: isPending ? 0 : number(line.amount_usd),
                pending: isPending,
                note: isPending
                    ? __("بانتظار إدخال السعر الخاص الشامل")
                    : (line.note || ""),
            };
        });
    }

    function previewTotal(frm) {
        const payload = data(frm);
        if (!payload || payload.invoice_preview_total_usd === undefined) return null;
        return number(payload.invoice_preview_total_usd);
    }

    function pendingFactoryPriceLabels(frm) {
        const payload = data(frm);
        return payload && Array.isArray(payload.pending_factory_price_labels)
            ? payload.pending_factory_price_labels.filter(Boolean)
            : [];
    }

    function selectorValue(value) {
        const raw = String(value || "");
        if (window.CSS && typeof window.CSS.escape === "function") {
            return window.CSS.escape(raw);
        }
        return raw.replace(/["\\]/g, "\\$&");
    }

    function costRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.order_cost_invoice_html;
        const wrapper = field && field.$wrapper;
        if (!wrapper) return null;
        if (typeof wrapper.get === "function") return wrapper.get(0) || null;
        if (wrapper[0]) return wrapper[0];
        return typeof wrapper.querySelector === "function" ? wrapper : null;
    }

    function reconcileNonFactoryPricingCards(frm) {
        const payload = data(frm);
        const root = costRoot(frm);
        if (!payload || !root || typeof root.querySelectorAll !== "function") return;
        (payload.pieces || []).forEach((piece) => {
            if (!piece || piece.factory_execution_qty === undefined || !piece.name) return;
            const hidden = number(piece.factory_execution_qty) <= 0;
            const key = selectorValue(piece.name);
            root.querySelectorAll(
                `[data-special-row="${key}"], [data-cut-corner-row="${key}"]`
            ).forEach((card) => {
                card.hidden = hidden;
            });
        });
    }

    function reconcileInvoiceTotalCard(frm) {
        const total = previewTotal(frm);
        if (total === null) return;
        const root = costRoot(frm);
        const card = root && typeof root.querySelector === "function"
            ? root.querySelector(".dco-invoice-total-card")
            : null;
        if (!card) return;

        const pending = pendingFactoryPriceLabels(frm);
        card.classList.toggle("is-pending", pending.length > 0);
        if (pending.length) {
            card.innerHTML = `
                <span>${__("الإجمالي الحالي قبل الأسعار غير المسعرة")}
                    <small>${__("لا يعتبر إجماليًا نهائيًا حتى تسعير: {0}").replace("{0}", pending.map(esc).join("، "))}</small>
                </span>
                <b>$ ${money(total)}</b>
            `;
            return;
        }
        card.innerHTML = `
            <span>${__("الإجمالي النهائي للفاتورة")}</span>
            <b>$ ${money(total)}</b>
        `;
    }

    function reconcileRenderedCommercialProjection(frm) {
        reconcileNonFactoryPricingCards(frm);
        reconcileInvoiceTotalCard(frm);
    }

    function reconcileActiveCostEditSession(frm) {
        const editSession = window.AlmdinaCostEditSessionUX;
        if (!editSession || typeof editSession.sync !== "function") return false;
        if (
            typeof editSession.isEditing === "function"
            && !editSession.isEditing(frm)
        ) {
            return false;
        }
        // A full presenter render replaces the stable OFFCUT input node. When a
        // Cost edit session is active, synchronously re-bind the current draft to
        // that new node before control returns to any asynchronous caller.
        editSession.sync(frm);
        return true;
    }

    function install() {
        const legacy = window.AlmdinaOrderCostUX;
        if (!legacy || legacy.__a52WorkspaceOwned) return false;
        const wrapped = {
            ...legacy,
            __a52WorkspaceOwned: true,
            render(frm) {
                if (canView(frm) && !ready(frm)) return renderPending(frm);
                if (ready(frm)) project(frm);
                const result = legacy.render(frm);
                if (ready(frm)) reconcileRenderedCommercialProjection(frm);
                reconcileActiveCostEditSession(frm);
                return result;
            },
            refreshInvoiceSection(frm) {
                if (canView(frm) && !ready(frm)) return renderPending(frm);
                if (ready(frm)) project(frm);
                const result = legacy.refreshInvoiceSection(frm);
                if (ready(frm)) reconcileRenderedCommercialProjection(frm);
                return result;
            },
            invoiceLines(frm) {
                if (canView(frm) && !ready(frm)) return [];
                if (ready(frm)) {
                    project(frm);
                    const lines = previewLines(frm);
                    if (lines) return lines;
                }
                return legacy.invoiceLines(frm);
            },
            invoiceTotal(frm) {
                if (canView(frm) && !ready(frm)) return 0;
                if (ready(frm)) {
                    project(frm);
                    const total = previewTotal(frm);
                    if (total !== null) return total;
                }
                return legacy.invoiceTotal(frm);
            },
            quoteTotal(frm) {
                if (canView(frm) && !ready(frm)) return 0;
                if (ready(frm)) {
                    project(frm);
                    const total = previewTotal(frm);
                    if (total !== null) return total;
                }
                return legacy.quoteTotal(frm);
            },
        };
        window.AlmdinaOrderCostUX = Object.freeze(wrapped);
        return true;
    }

    function reconcilePermissionActions(frm) {
        const permissionUx = window.AlmdinaCostPermissionsUX;
        if (!permissionUx) return false;
        if (typeof permissionUx.reconcileRenderedActions === "function") {
            return permissionUx.reconcileRenderedActions(frm);
        }
        return false;
    }

    function refreshCurrent() {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const presenter = window.AlmdinaOrderCostUX;
        if (presenter && typeof presenter.render === "function") presenter.render(frm);
        // Rendering is synchronous. Apply permissions directly to the markup that
        // was just produced instead of starting a timer-based second render pass.
        reconcilePermissionActions(frm);
    }

    window.addEventListener("almdina:cost-workspace-updated", refreshCurrent);

    window.AlmdinaCostWorkspacePresenterAdapter = Object.freeze({
        install,
        project,
        ready,
        reconcilePermissionActions,
    });

    install();
})();
