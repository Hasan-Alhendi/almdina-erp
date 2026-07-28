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

    function applyLabels(frm) {
        if (!isArabic() || !frm.fields_dict.thickness_mm) return;
        frm.set_df_property("thickness_mm", "label", "سماكة القشاط (مم)");
        frm.set_df_property(
            "thickness_mm",
            "description",
            "السماكة التي تُخصم من قياس القص لكل طرف قشاط محدد. مثال: قشاط 1 مم يُخصم 1 مم عن كل طرف."
        );
    }

    function addPreview(frm) {
        const field = frm.fields_dict.thickness_mm;
        if (!field || !field.$wrapper) return;
        const thickness = Number(frm.doc.thickness_mm || 0);
        const text = isArabic()
            ? `طرف واحد: خصم ${thickness || 0} مم — طرفان متقابلان: خصم ${(thickness || 0) * 2} مم`
            : `One side: deduct ${thickness || 0} mm — two opposite sides: deduct ${(thickness || 0) * 2} mm`;
        field.$wrapper.attr("title", text);
    }

    function apply(frm) {
        applyLabels(frm);
        addPreview(frm);
    }

    frappe.ui.form.on("Edge Banding Type", {
        onload_post_render(frm) { apply(frm); },
        refresh(frm) { apply(frm); },
        thickness_mm(frm) { addPreview(frm); },
    });
})();
