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

    function rootFor(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-fast-table th.dco-col-cut-size,
            .dco-fast-table td.dco-col-cut-size{
                display:none!important
            }
            .dco-cut-rule-hint{
                display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:3px 8px;
                background:rgba(36,144,239,.08);color:var(--text-color,#36414c);font-weight:700
            }
        `;
        document.head.appendChild(style);
    }

    function removeCutSizeColumn(root) {
        root.querySelectorAll(".dco-fast-table th.dco-col-cut-size,.dco-fast-table td.dco-col-cut-size")
            .forEach(element => element.remove());
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
        if (root._dcoCutColumnRemovalBound) return;
        root._dcoCutColumnRemovalBound = true;
        let queued = false;
        const scheduleApply = () => {
            if (queued) return;
            queued = true;
            requestAnimationFrame(() => {
                queued = false;
                apply(frm);
            });
        };
        const observer = new MutationObserver(scheduleApply);
        observer.observe(root, { childList: true, subtree: true });
        root._dcoCutColumnRemovalObserver = observer;
    }

    function apply(frm) {
        installStyles();
        const root = rootFor(frm);
        if (!root) return;
        removeCutSizeColumn(root);
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
