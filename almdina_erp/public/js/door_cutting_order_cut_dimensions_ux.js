(() => {
    "use strict";

    const STYLE_ID = "dco-cut-dimensions-css";

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function rootFor(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function moduleApi() {
        return window.AlmdinaMultiEdgeBanding || null;
    }

    function format(value) {
        const api = moduleApi();
        return api ? api.format(value) : String(value || 0);
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table .dco-col-cut-size{width:122px!important;min-width:122px!important;max-width:122px!important;text-align:center;padding-inline:4px!important}
            .dco-cut-size-card{min-height:48px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;border:1px solid rgba(36,144,239,.22);border-radius:9px;background:rgba(36,144,239,.05);padding:4px;line-height:1.15}
            .dco-cut-size-card.is-unchanged{border-color:var(--border-color,#dfe3e8);background:var(--subtle-fg,#f8f9fa)}
            .dco-cut-size-card.is-warning{border-color:rgba(217,119,6,.38);background:rgba(245,158,11,.09)}
            .dco-cut-size-value{direction:ltr;font-size:12px;font-weight:900;font-variant-numeric:tabular-nums;white-space:nowrap}
            .dco-cut-size-meta{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-muted,#6c7680);font-size:8.7px}
            .dco-cut-rule-hint{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:3px 8px;background:rgba(36,144,239,.08);color:var(--text-color,#36414c);font-weight:700}
            @media(max-width:900px){.dco-fast-table .dco-col-cut-size{width:112px!important;min-width:112px!important;max-width:112px!important}.dco-cut-size-value{font-size:11px}}
        `;
        document.head.appendChild(style);
    }

    function metadata(result) {
        if (result.missingType) return isArabic() ? "اختر القشاط الافتراضي" : "Select default edge";
        if (result.unknownType) return isArabic() ? "تحميل بيانات القشاط…" : "Loading edge data…";
        const parts = [];
        if (result.widthDeductionMm) {
            parts.push(isArabic()
                ? `خصم ${format(result.widthDeductionMm)} مم عرض`
                : `${format(result.widthDeductionMm)} mm width`);
        }
        if (result.lengthDeductionMm) {
            parts.push(isArabic()
                ? `خصم ${format(result.lengthDeductionMm)} مم طول`
                : `${format(result.lengthDeductionMm)} mm length`);
        }
        return parts.length ? parts.join(" · ") : (isArabic() ? "بدون خصم" : "No deduction");
    }

    function tooltip(result) {
        const finalSize = `${format(result.finalWidth)} × ${format(result.finalLength)}`;
        const cutSize = `${format(result.cutWidth)} × ${format(result.cutLength)}`;
        const profiles = result.selectedSides.map(item => {
            const mode = item.custom ? (isArabic() ? "مخصص" : "custom") : (isArabic() ? "افتراضي" : "default");
            return `${item.type || "—"} (${format(item.thickness)} mm, ${mode})`;
        });
        return isArabic()
            ? `القياس النهائي: ${finalSize} سم | قياس القص: ${cutSize} سم${profiles.length ? ` | ${profiles.join(" | ")}` : ""}`
            : `Finished: ${finalSize} cm | Cut: ${cutSize} cm${profiles.length ? ` | ${profiles.join(" | ")}` : ""}`;
    }

    function renderCell(frm, tr, cell) {
        const api = moduleApi();
        if (!api) return;
        const row = rowByName(frm, tr.dataset.rowName || "");
        if (!row) {
            cell.innerHTML = '<div class="dco-cut-size-card is-unchanged"><span class="dco-cut-size-value">—</span><span class="dco-cut-size-meta">بدون قياس</span></div>';
            return;
        }
        const result = api.calculate(frm, row);
        const warning = result.missingType || result.unknownType || !result.valid;
        const unchanged = !result.selectedSides.length;
        const label = result.valid ? `${format(result.cutWidth)} × ${format(result.cutLength)}` : "—";
        const meta = metadata(result);
        const title = tooltip(result);
        const signature = JSON.stringify([label, meta, title, warning, unchanged]);
        if (cell.dataset.cutSignature === signature) return;
        cell.dataset.cutSignature = signature;
        cell.innerHTML = `
            <div class="dco-cut-size-card ${warning ? "is-warning" : ""} ${unchanged ? "is-unchanged" : ""}" title="${esc(title)}">
                <span class="dco-cut-size-value">${esc(label)}</span>
                <span class="dco-cut-size-meta">${esc(meta)}</span>
            </div>`;
    }

    function ensureHeader(root) {
        const edgeHeader = root.querySelector(".dco-fast-table thead th.dco-col-edge-type");
        if (!edgeHeader) return;
        let header = root.querySelector(".dco-fast-table thead th.dco-col-cut-size");
        if (!header) {
            header = document.createElement("th");
            header.className = "dco-col-cut-size";
            edgeHeader.insertAdjacentElement("afterend", header);
        }
        header.textContent = isArabic() ? "مقاس القص" : "Cut size";
        header.title = isArabic()
            ? "القياس النهائي بعد خصم سماكة القشاط الفعلية لكل ضلع"
            : "Finished size after deducting the effective thickness of each side";
    }

    function ensureRows(frm, root) {
        root.querySelectorAll(".dco-fast-table tbody tr[data-row-name]").forEach(tr => {
            const edgeCell = tr.querySelector(":scope > td.dco-col-edge-type");
            if (!edgeCell) return;
            let cell = tr.querySelector(":scope > td.dco-col-cut-size");
            if (!cell) {
                cell = document.createElement("td");
                cell.className = "dco-col-cut-size";
                edgeCell.insertAdjacentElement("afterend", cell);
            }
            renderCell(frm, tr, cell);
        });
    }

    function ensureHelp(root) {
        const help = root.querySelector(".dco-fast-help");
        if (!help || help.querySelector(".dco-cut-rule-hint")) return;
        const hint = document.createElement("span");
        hint.className = "dco-cut-rule-hint";
        hint.textContent = isArabic()
            ? "المدخل نهائي ← الخصم حسب سماكة كل ضلع"
            : "Finished input → deduction follows each side";
        help.appendChild(hint);
    }

    function bind(frm, root) {
        if (root._dcoSideCutPreviewBound) return;
        root._dcoSideCutPreviewBound = true;
        let queued = false;
        const scheduleApply = () => {
            if (queued) return;
            queued = true;
            requestAnimationFrame(() => {
                queued = false;
                apply(frm);
            });
        };
        root.addEventListener("input", scheduleApply);
        root.addEventListener("change", scheduleApply);
        root.addEventListener("click", scheduleApply);
        root.addEventListener("dco:side-edge-change", scheduleApply);
        const observer = new MutationObserver(scheduleApply);
        observer.observe(root, { childList: true, subtree: true });
        root._dcoSideCutPreviewObserver = observer;
    }

    function apply(frm) {
        installStyles();
        const root = rootFor(frm);
        if (!root || !moduleApi()) return;
        ensureHeader(root);
        ensureRows(frm, root);
        ensureHelp(root);
        bind(frm, root);
    }

    function schedule(frm) {
        apply(frm);
        requestAnimationFrame(() => apply(frm));
        setTimeout(() => apply(frm), 160);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        default_edge_type(frm) { schedule(frm); },
    });

    frappe.ui.form.on("Door Cutting Order Detail", {
        width_cm(frm) { schedule(frm); },
        length_cm(frm) { schedule(frm); },
        edge_long_right_type_override(frm) { schedule(frm); },
        edge_long_left_type_override(frm) { schedule(frm); },
        edge_width_top_type_override(frm) { schedule(frm); },
        edge_width_bottom_type_override(frm) { schedule(frm); },
        edge_long_right(frm) { schedule(frm); },
        edge_long_left(frm) { schedule(frm); },
        edge_width_top(frm) { schedule(frm); },
        edge_width_bottom(frm) { schedule(frm); },
    });
})();
