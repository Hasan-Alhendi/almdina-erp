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

    function wrapCall(legacy, method) {
        return function workspaceOwnedCostPresenter(frm, ...args) {
            project(frm);
            return legacy[method](frm, ...args);
        };
    }

    function install() {
        const legacy = window.AlmdinaOrderCostUX;
        if (!legacy || legacy.__a52WorkspaceOwned) return false;
        const wrapped = {
            ...legacy,
            __a52WorkspaceOwned: true,
        };
        [
            "render",
            "refreshInvoiceSection",
            "invoiceLines",
            "invoiceTotal",
            "quoteTotal",
        ].forEach((method) => {
            if (typeof legacy[method] === "function") wrapped[method] = wrapCall(legacy, method);
        });
        window.AlmdinaOrderCostUX = Object.freeze(wrapped);
        return true;
    }

    function refreshCurrent() {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") return;
        project(frm);
        const presenter = window.AlmdinaOrderCostUX;
        if (presenter && typeof presenter.render === "function") presenter.render(frm);
    }

    window.addEventListener("almdina:cost-workspace-updated", refreshCurrent);

    window.AlmdinaCostWorkspacePresenterAdapter = Object.freeze({
        install,
        project,
    });

    install();
})();
