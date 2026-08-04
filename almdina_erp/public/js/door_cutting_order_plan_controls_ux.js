(() => {
    "use strict";

    const ADVANCED_MODES = [
        { value: "Auto Pro", label: "أفضل توزيع متقدم" },
        { value: "Deep Search", label: "بحث معمق" },
        { value: "Optimal Search", label: "بحث أمثل" },
    ];

    const DUPLICATED_ACTIONS = [
        ".dco-auto-pro-plan",
        ".dco-deep-plan",
        ".dco-optimal-plan",
        ".dco-algorithm-palette",
    ].join(",");

    function installStyles() {
        if (document.getElementById("dco-simple-plan-controls-css")) return;
        $("head").append(`
            <style id="dco-simple-plan-controls-css">
                [data-fieldname="plan_control_actions"] .dco-plan-actions {
                    display:flex !important;
                    align-items:center !important;
                    justify-content:flex-start !important;
                    gap:8px !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-document-actions {
                    display:flex !important;
                    align-items:center !important;
                    gap:8px !important;
                    flex-wrap:wrap !important;
                }
                [data-fieldname="plan_control_actions"] .dco-recalculate-plan {
                    min-width:230px;
                    min-height:40px !important;
                    font-weight:850 !important;
                    border-radius:10px !important;
                }
                [data-fieldname="plan_control_actions"] .dco-print-cutting-plan,
                [data-fieldname="plan_control_actions"] .dco-export-dxf {
                    min-height:36px !important;
                    border-radius:10px !important;
                    font-weight:800 !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-actions-title {
                    margin-bottom:10px !important;
                }
                @media (max-width:560px) {
                    [data-fieldname="plan_control_actions"] .dco-recalculate-plan {
                        width:100%;
                        min-width:0;
                    }
                    [data-fieldname="plan_control_actions"] .dco-print-cutting-plan,
                    [data-fieldname="plan_control_actions"] .dco-export-dxf {
                        width:100%;
                    }
                }
            </style>
        `);
    }

    function ensureAdvancedModes(frm) {
        const field = frm.fields_dict && frm.fields_dict.packing_mode;
        if (!field) return;

        const options = String(field.df.options || "")
            .split("\n")
            .map((value) => value.trim())
            .filter(Boolean);

        let changed = false;
        ADVANCED_MODES.forEach(({ value }) => {
            if (!options.includes(value)) {
                options.push(value);
                changed = true;
            }
        });

        if (changed) {
            field.df.options = options.join("\n");
            if (typeof field.set_options === "function") {
                field.set_options(options);
            } else if (typeof field.refresh === "function") {
                field.refresh();
            }
        }

        const input = field.$input && field.$input.length ? field.$input : field.$wrapper.find("select");
        if (!input || !input.length) return;

        ADVANCED_MODES.forEach(({ value, label }) => {
            let option = input.find("option").filter(function matchValue() {
                return this.value === value;
            }).first();
            if (!option.length) {
                input.append($("<option>", { value, text: label }));
                option = input.find("option").filter(function matchInsertedValue() {
                    return this.value === value;
                }).first();
            }
            option.text(label);
        });

        input.val(frm.doc.packing_mode || "Auto");
    }

    function simplifyActions(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;

        field.$wrapper.find(DUPLICATED_ACTIONS).remove();

        const recalculate = field.$wrapper.find(".dco-recalculate-plan").first();
        if (recalculate.length) {
            recalculate.text("إعادة الحساب بالإعدادات الحالية");
            recalculate.attr("title", "إعادة حساب خطة القص باستخدام طريقة الترتيب والماكينة والهامش المحددة حاليًا");
        }
    }

    function apply(frm) {
        installStyles();
        ensureAdvancedModes(frm);
        simplifyActions(frm);
    }

    function observeActions(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        const node = field && field.$wrapper && field.$wrapper[0];
        if (!node || frm.__dcoSimplePlanControlsObserver) return;

        frm.__dcoSimplePlanControlsObserver = new MutationObserver(() => {
            requestAnimationFrame(() => simplifyActions(frm));
        });
        frm.__dcoSimplePlanControlsObserver.observe(node, { childList: true, subtree: true });
    }

    function refresh(frm) {
        apply(frm);
        observeActions(frm);
        requestAnimationFrame(() => apply(frm));
        setTimeout(() => apply(frm), 0);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        packing_mode(frm) { refresh(frm); },
    });
})();
