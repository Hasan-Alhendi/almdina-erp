(() => {
    "use strict";

    const ROOT_CLASS = "ebt-form-active";
    const LIST_ROUTE = ["List", "Edge Banding Type"];
    const ENGLISH_PLACEHOLDER = "e.g. PVC Edge Banding White Matt 1mm";

    const LABELS = Object.freeze({
        edge_type_name: "اسم نوع القشاط",
        english_name: "الاسم الإنجليزي (اختياري)",
        width_cm: "العرض (سم)",
        thickness_mm: "سماكة القشاط (مم)",
        rate_usd_per_meter: "سعر المتر بالدولار",
        disabled: "موقوف (إيقاف هذا النوع مؤقتاً)",
    });

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

    function icon(name, size) {
        if (frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, size || "sm");
        }
        return "";
    }

    function pageTitle(frm) {
        if (frm.is_new()) {
            return __("إضافة وتحديد نوع قشاط جديد");
        }
        const name = String(frm.doc.edge_type_name || frm.doc.name || "").trim();
        return name ? __("تعديل نوع القشاط: {0}", [name]) : __("تعديل نوع القشاط");
    }

    function pageSubtitle() {
        return __(
            "عرّف اسم القشاط، مقاساته، وسعر المتر. تُستخدم هذه البيانات تلقائياً في طلبات القص والتسعير."
        );
    }

    function calloutHtml() {
        return `
            <span class="ebt-form-callout-icon" aria-hidden="true">${icon("info-circle", "sm")}</span>
            <div>
                <strong>${__("قاعدة احتساب الخصم الآلي:")}</strong>
                ${__(
                    "يُخصم من قياس القص مقدار سماكة القشاط عن كل طرف محدد. عند تفعيل طرفين متقابلين يُخصم ضعف السماكة."
                )}
            </div>`;
    }

    function footerButtonsHtml(frm) {
        const saveDisabled = frm.is_read_only() ? " disabled" : "";
        const saveLabel = esc(__("حفظ التغييرات"));
        const cancelLabel = esc(__("إلغاء والتراجع"));
        const saveIcon = icon("tick", "sm");
        return `
            <button type="button" class="btn alm-btn-secondary ebt-footer-cancel">${cancelLabel}</button>
            <button type="button" class="btn alm-btn-primary ebt-footer-save"${saveDisabled}>
                <span class="ebt-footer-save-icon" aria-hidden="true">${saveIcon}</span>
                ${saveLabel}
            </button>`;
    }

    function relocateField(frm, fieldname, host) {
        const field = frm.fields_dict[fieldname];
        if (!field || !field.$wrapper || !host || !host.length) return;
        if (!field.$wrapper.parent().is(host)) {
            host.append(field.$wrapper);
        }
    }

    function hideLeftoverFormSections(frm) {
        frm.layout.wrapper
            .find(".form-page > .form-section")
            .each(function hideSection() {
                const section = $(this);
                const hasVisibleControl = section.find(".frappe-control").filter(function filterControl() {
                    return !$(this).hasClass("hide-control") && $(this).css("display") !== "none";
                }).length;
                if (!hasVisibleControl) {
                    section.addClass("hide ebt-form-section-empty");
                }
            });
    }

    function relocateAllFields(frm, shell) {
        relocateField(frm, "edge_type_name", shell.find('[data-ebt-slot="names"]'));
        relocateField(frm, "english_name", shell.find('[data-ebt-slot="names"]'));
        relocateField(frm, "width_cm", shell.find('[data-ebt-slot="metrics"]'));
        relocateField(frm, "thickness_mm", shell.find('[data-ebt-slot="metrics"]'));
        relocateField(frm, "rate_usd_per_meter", shell.find('[data-ebt-slot="metrics"]'));
        relocateField(frm, "disabled", shell.find('[data-ebt-slot="disabled"]'));
        hideLeftoverFormSections(frm);
    }

    function ensureShell(frm) {
        if (frm._ebtShell && frm._ebtShell.length) {
            return frm._ebtShell;
        }
        const shell = $(`
            <div class="ebt-form-page almdina-ui">
                <div class="ebt-form-card">
                    <header class="ebt-form-hero">
                        <span class="ebt-form-hero-icon" aria-hidden="true"></span>
                        <div>
                            <h2 class="ebt-form-hero-title"></h2>
                            <p class="ebt-form-hero-subtitle"></p>
                        </div>
                    </header>
                    <div class="ebt-form-callout"></div>
                    <div class="ebt-form-fields">
                        <div class="ebt-form-grid ebt-form-grid--2" data-ebt-slot="names"></div>
                        <div class="ebt-form-grid ebt-form-grid--3" data-ebt-slot="metrics"></div>
                        <div class="ebt-form-disabled-row" data-ebt-slot="disabled"></div>
                    </div>
                    <footer class="ebt-form-footer"></footer>
                </div>
            </div>
        `);
        const formPage = frm.layout.wrapper.find(".form-page").first();
        if (formPage.length) {
            formPage.prepend(shell);
        } else {
            frm.layout.wrapper.prepend(shell);
        }
        frm._ebtShell = shell;
        return shell;
    }

    function bindFooterActions(frm, shell) {
        if (shell.data("ebt-actions-bound") === "1") return;
        shell.on("click", ".ebt-footer-save", () => {
            if (frm.is_read_only()) return;
            frm.save();
        });
        shell.on("click", ".ebt-footer-cancel", () => {
            frappe.set_route(...LIST_ROUTE);
        });
        shell.data("ebt-actions-bound", "1");
    }

    function configurePageActions(frm) {
        if (!frm.page) return;
        frm.page.page_head && frm.page.page_head.addClass("ebt-form-page-head");
        frm.page.btn_secondary && frm.page.btn_secondary.removeClass("hide");

        if (frm.is_read_only()) {
            frm.page.set_primary_action(__("عودة للقائمة"), () => frappe.set_route(...LIST_ROUTE), "reply");
            frm.page.clear_secondary_action();
            return;
        }

        frm.page.set_primary_action(__("حفظ القشاط"), () => frm.save(), "save");
        frm.page.set_secondary_action(__("إلغاء وعودة"), () => frappe.set_route(...LIST_ROUTE), "left");
    }

    function applyLabels(frm) {
        frm.set_df_property("english_name", "placeholder", ENGLISH_PLACEHOLDER);
        if (!isArabic()) return;
        Object.entries(LABELS).forEach(([fieldname, label]) => {
            if (frm.fields_dict[fieldname]) {
                frm.set_df_property(fieldname, "label", label);
            }
        });
        frm.set_df_property("thickness_mm", "description", "");
    }

    function renderShell(frm) {
        document.body.classList.add(ROOT_CLASS);
        frm.$wrapper && frm.$wrapper.addClass("ebt-form-root");
        applyLabels(frm);
        frm.set_intro("");

        const shell = ensureShell(frm);
        shell.find(".ebt-form-hero-icon").html(icon(frm.is_new() ? "add" : "edit", "md"));
        shell.find(".ebt-form-hero-title").text(pageTitle(frm));
        shell.find(".ebt-form-hero-subtitle").text(pageSubtitle());
        shell.find(".ebt-form-callout").html(calloutHtml());
        shell.find(".ebt-form-summary").remove();
        shell.find(".ebt-form-footer").html(footerButtonsHtml(frm));

        bindFooterActions(frm, shell);
        relocateAllFields(frm, shell);
        configurePageActions(frm);
    }

    function scheduleApply(frm) {
        renderShell(frm);
        requestAnimationFrame(() => {
            renderShell(frm);
        });
        setTimeout(() => {
            configurePageActions(frm);
            if (frm._ebtShell) {
                relocateAllFields(frm, frm._ebtShell);
            }
        }, 0);
    }

    function bindLifecycle() {
        if (frappe.router && frappe.router.__ebtFormUxBound) return;
        if (!frappe.router) return;
        frappe.router.__ebtFormUxBound = true;
        frappe.router.on("change", () => {
            const route = frappe.get_route() || [];
            if (route[0] !== "Form" || route[1] !== "Edge Banding Type") {
                document.body.classList.remove(ROOT_CLASS);
            }
        });

        $(document).on("form-refresh", (_event, frm) => {
            if (!frm || frm.doctype !== "Edge Banding Type") return;
            setTimeout(() => scheduleApply(frm), 0);
        });
    }

    function apply(frm) {
        if (!frm || frm.doctype !== "Edge Banding Type") return;
        bindLifecycle();
        scheduleApply(frm);
    }

    frappe.ui.form.on("Edge Banding Type", {
        onload_post_render(frm) {
            apply(frm);
        },
        refresh(frm) {
            apply(frm);
        },
    });
})();
