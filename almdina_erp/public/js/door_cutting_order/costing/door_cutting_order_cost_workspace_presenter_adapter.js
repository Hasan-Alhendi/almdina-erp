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

    function ensureLoad(frm) {
        const owner = stateOwner();
        if (!owner || typeof owner.load !== "function") return Promise.resolve(null);
        return Promise.resolve(owner.load(frm)).catch(() => null);
    }

    function ready(frm) {
        const state = snapshot(frm);
        return Boolean(state && state.status === "ready" && state.data);
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
        ensureLoad(frm);
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
                return legacy.render(frm);
            },
            refreshInvoiceSection(frm) {
                if (canView(frm) && !ready(frm)) return renderPending(frm);
                if (ready(frm)) project(frm);
                return legacy.refreshInvoiceSection(frm);
            },
            invoiceLines(frm) {
                if (canView(frm) && !ready(frm)) {
                    ensureLoad(frm);
                    return [];
                }
                if (ready(frm)) project(frm);
                return legacy.invoiceLines(frm);
            },
            invoiceTotal(frm) {
                if (canView(frm) && !ready(frm)) {
                    ensureLoad(frm);
                    return 0;
                }
                if (ready(frm)) project(frm);
                return legacy.invoiceTotal(frm);
            },
            quoteTotal(frm) {
                if (canView(frm) && !ready(frm)) {
                    ensureLoad(frm);
                    return 0;
                }
                if (ready(frm)) project(frm);
                return legacy.quoteTotal(frm);
            },
        };
        window.AlmdinaOrderCostUX = Object.freeze(wrapped);
        return true;
    }

    function reconcilePermissionActions(frm) {
        const permissionUx = window.AlmdinaCostPermissionsUX;
        if (!permissionUx || typeof permissionUx.apply !== "function") return;
        window.setTimeout(() => {
            if (window.cur_frm !== frm || frm.doctype !== "Door Cutting Order") return;
            permissionUx.apply(frm);
        }, 0);
    }

    function refreshCurrent() {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        const presenter = window.AlmdinaOrderCostUX;
        if (presenter && typeof presenter.render === "function") presenter.render(frm);
        // The presenter renders inline price inputs fail-closed (disabled/readonly).
        // Reconcile the permission-owned actions after every asynchronous workspace
        // refresh so an authorized active edit session does not get visually locked
        // again when a financial snapshot arrives.
        reconcilePermissionActions(frm);
    }

    window.addEventListener("almdina:cost-workspace-updated", refreshCurrent);

    window.AlmdinaCostWorkspacePresenterAdapter = Object.freeze({
        install,
        project,
        ready,
    });

    install();
})();
