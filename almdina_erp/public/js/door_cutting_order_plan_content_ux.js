(() => {
    "use strict";

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function localizePlanSections(frm) {
        if (!isArabic()) return;
        const labels = {
            cut_geometry_section: "إعدادات تنفيذ القص",
            optimizer_section: "محرك خطة القص",
            plan_result_section: "نتيجة الخطة الحالية",
            plan_section: "توزيع القطع على الألواح",
            totals_section: "تفاصيل الحساب والتكلفة",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            if (frm.fields_dict[fieldname]) frm.set_df_property(fieldname, "label", label);
        });
    }

    function cleanRenderedPlan(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;

        root.querySelectorAll(".dco-cutting-plan").forEach(planRoot => {
            const heading = planRoot.querySelector(":scope > h2");
            if (heading) heading.remove();

            planRoot.querySelectorAll(":scope > .dco-summary-grid, :scope > .dco-piece-groups").forEach(el => el.remove());

            [...planRoot.children].forEach(child => {
                if (!(child instanceof HTMLElement)) return;
                if (child.classList.contains("dco-sheet-card")) return;
                if (child.classList.contains("dco-summary-grid")) return;
                const text = (child.textContent || "").replace(/\s+/g, " ").trim();
                const isDuplicatedHeader =
                    (text.includes("الطلب:") && (text.includes("الزبون:") || text.includes("اللوح:") || text.includes("الصنف:"))) ||
                    (text.includes("مقاس اللوح الكامل") && text.includes("سماكة القص"));
                const isMethodDuplicate = text.startsWith("طريقة الترتيب:") || text.includes("طريقة الترتيب:");
                if (isDuplicatedHeader || isMethodDuplicate) child.remove();
            });
        });
    }

    function installObserver(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root || root._dcoPlanContentObserver) return;

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                cleanRenderedPlan(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoPlanContentObserver = observer;
    }

    function apply(frm) {
        localizePlanSections(frm);
        cleanRenderedPlan(frm);
        installObserver(frm);
        requestAnimationFrame(() => cleanRenderedPlan(frm));
        window.setTimeout(() => cleanRenderedPlan(frm), 500);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { apply(frm); },
        refresh(frm) { apply(frm); },
        cutting_plan_json(frm) { apply(frm); },
    });
})();
