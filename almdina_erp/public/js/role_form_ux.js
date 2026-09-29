(() => {
    "use strict";

    const ROOT_CLASS = "role-form-layout-active";
    const INPUT_FIELDS = Object.freeze(["home_page", "restrict_to_domain"]);
    const CHECK_FIELDS = Object.freeze(["disabled", "is_custom", "desk_access", "two_factor_auth"]);

    function relocateField(frm, fieldname, host) {
        const field = frm.fields_dict[fieldname];
        if (!field || !field.$wrapper || !host || !host.length) return;
        if (!field.$wrapper.parent().is(host)) {
            host.append(field.$wrapper);
        }
    }

    function hideColumnBreak(frm) {
        const columnBreak = frm.fields_dict.column_break_4;
        if (columnBreak && columnBreak.$wrapper) {
            columnBreak.$wrapper.addClass("hide-control role-form-column-break-hidden");
        }
    }

    function hideEmptySections(frm) {
        frm.layout.wrapper.find(".form-page > .form-section").each(function pruneSection() {
            const section = $(this);
            if (section.find(".role-form-top-grid").length) return;
            const visibleControls = section.find(".frappe-control").filter(function filterControl() {
                const node = $(this);
                return (
                    !node.hasClass("hide-control")
                    && !node.hasClass("role-form-column-break-hidden")
                    && node.css("display") !== "none"
                );
            });
            if (!visibleControls.length) {
                section.addClass("hide role-form-section-empty");
            }
        });
    }

    function primarySection(frm) {
        const roleField = frm.fields_dict.role_name;
        if (roleField && roleField.$wrapper && roleField.$wrapper.length) {
            const section = roleField.$wrapper.closest(".form-section");
            if (section.length) return section;
        }
        return frm.layout.wrapper.find(".form-page > .form-section").first();
    }

    function columnHasVisibleControls(column) {
        return (
            column.find(".frappe-control").filter(function filterControl() {
                const node = $(this);
                return (
                    !node.hasClass("hide-control")
                    && !node.hasClass("role-form-column-break-hidden")
                    && node.css("display") !== "none"
                );
            }).length > 0
        );
    }

    function ensureGrid(frm) {
        if (frm._roleFormGrid && frm._roleFormGrid.length) {
            return frm._roleFormGrid;
        }

        const grid = $(`
            <div class="role-form-top-grid almdina-ui">
                <div class="role-form-row role-form-row--inputs" data-role-slot="inputs"></div>
                <div class="role-form-row role-form-row--checks" data-role-slot="checks"></div>
            </div>
        `);

        frm._roleFormGrid = grid;
        return grid;
    }

    function expandSectionFullWidth(frm, grid) {
        const section = primarySection(frm);
        if (!section.length) return;

        section.addClass("role-form-section-full");
        const sectionBody = section.find(".section-body").first();
        if (sectionBody.length) {
            sectionBody.append(grid);
        }

        section.find(".form-column").each(function markColumn() {
            const column = $(this);
            column.toggleClass("role-form-empty-column", !columnHasVisibleControls(column));
        });
    }

    function applyLayout(frm) {
        document.body.classList.add(ROOT_CLASS);
        frm.$wrapper && frm.$wrapper.addClass("role-form-root");

        const grid = ensureGrid(frm);
        expandSectionFullWidth(frm, grid);
        INPUT_FIELDS.forEach((fieldname) => relocateField(frm, fieldname, grid.find('[data-role-slot="inputs"]')));
        CHECK_FIELDS.forEach((fieldname) => relocateField(frm, fieldname, grid.find('[data-role-slot="checks"]')));

        hideColumnBreak(frm);
        hideEmptySections(frm);
    }

    function scheduleApply(frm) {
        applyLayout(frm);
        requestAnimationFrame(() => applyLayout(frm));
    }

    function bindLifecycle() {
        if (frappe.router && frappe.router.__roleFormUxBound) return;
        if (!frappe.router) return;
        frappe.router.__roleFormUxBound = true;
        frappe.router.on("change", () => {
            const route = frappe.get_route() || [];
            if (route[0] !== "Form" || route[1] !== "Role") {
                document.body.classList.remove(ROOT_CLASS);
            }
        });
    }

    function apply(frm) {
        if (!frm || frm.doctype !== "Role") return;
        bindLifecycle();
        scheduleApply(frm);
    }

    frappe.ui.form.on("Role", {
        onload_post_render(frm) {
            apply(frm);
        },
        refresh(frm) {
            apply(frm);
        },
    });
})();
