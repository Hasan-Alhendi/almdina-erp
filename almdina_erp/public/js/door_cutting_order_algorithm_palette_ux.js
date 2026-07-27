(() => {
    "use strict";

    const ALGORITHM_GROUPS = [
        {
            key: "smart",
            label: "الاختيارات الذكية",
            hint: "خيارات يومية تقارن أكثر من طريقة تلقائيًا.",
            modes: [
                { value: "Auto", label: "تلقائي سريع", description: "مقارنة سريعة بين الخوارزميات الأساسية." },
                { value: "Auto Pro", label: "أفضل توزيع متقدم", description: "الخيار الموصى به للاستخدام اليومي." },
                { value: "Deep Search", label: "بحث معمق", description: "محاولات أكثر ضمن المهلة المحددة." },
                { value: "Optimal Search", label: "بحث أمثل", description: "Solver للحالات المناسبة مع أفضل حل صالح." },
            ],
        },
        {
            key: "maxrects",
            label: "المستطيلات القصوى",
            hint: "مرنة ومناسبة غالبًا لماكينات CNC والتوزيع الحر.",
            modes: [
                { value: "MaxRects Best Short Side", label: "أفضل ضلع قصير" },
                { value: "MaxRects Best Area", label: "أفضل مساحة" },
                { value: "MaxRects Bottom Left", label: "من أسفل اليسار" },
                { value: "MaxRects Contact Point", label: "أكبر تلامس" },
                { value: "MaxRects Width", label: "حسب العرض" },
                { value: "MaxRects Length", label: "حسب الطول" },
            ],
        },
        {
            key: "shelf",
            label: "الصفوف",
            hint: "ترتيب واضح على صفوف متتابعة وسهل القراءة في المعمل.",
            modes: [
                { value: "Shelf Horizontal", label: "صفوف أفقية" },
                { value: "Shelf Vertical", label: "صفوف عمودية" },
                { value: "Shelf First Fit", label: "أول مكان مناسب" },
                { value: "Shelf Next Fit", label: "المكان التالي المناسب" },
            ],
        },
        {
            key: "guillotine",
            label: "القص المتتابع",
            hint: "أنسب للمنشار اللوحي عندما يجب أن تكون القصات ممتدة ومتتابعة.",
            modes: [
                { value: "Guillotine Short Axis", label: "المحور القصير" },
                { value: "Guillotine Long Axis", label: "المحور الطويل" },
                { value: "Guillotine Best Area Fit", label: "أفضل مساحة" },
                { value: "Guillotine Best Short Side Fit", label: "أفضل ضلع قصير" },
                { value: "Guillotine Best Long Side Fit", label: "أفضل ضلع طويل" },
            ],
        },
        {
            key: "skyline",
            label: "خط الأفق",
            hint: "يبني التوزيع فوق الحافة الحرة الحالية للوح.",
            modes: [
                { value: "Skyline Bottom Left", label: "من أسفل اليسار" },
                { value: "Skyline Best Fit", label: "أفضل ملاءمة" },
            ],
        },
    ];

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function canEdit(frm) {
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0 && ["Draft", "Pending Review", "Rejected"].includes(frm.doc.status || "Draft");
    }

    function installStyles() {
        if (document.getElementById("dco-algorithm-palette-css")) return;
        $("head").append(`
            <style id="dco-algorithm-palette-css">
                .dco-algorithm-palette {
                    width:100%;
                    margin-top:10px;
                    border:1px solid var(--border-color,#dfe3e8);
                    border-radius:12px;
                    background:var(--fg-color,#fff);
                    overflow:hidden;
                }
                .dco-algorithm-palette-toggle {
                    width:100%;
                    min-height:42px;
                    display:flex;
                    align-items:center;
                    justify-content:space-between;
                    gap:12px;
                    padding:9px 12px;
                    border:0;
                    background:transparent;
                    color:var(--text-color,#1f2937);
                    text-align:start;
                    cursor:pointer;
                }
                .dco-algorithm-palette-toggle:hover {
                    background:var(--subtle-fg,#f8fafc);
                }
                .dco-algorithm-palette-toggle:focus-visible,
                .dco-algorithm-choice:focus-visible,
                .dco-algorithm-search:focus-visible {
                    outline:2px solid var(--primary,#2490ef);
                    outline-offset:2px;
                }
                .dco-algorithm-palette-title {
                    display:flex;
                    flex-direction:column;
                    gap:2px;
                    min-width:0;
                }
                .dco-algorithm-palette-title strong {
                    font-size:12px;
                    font-weight:850;
                }
                .dco-algorithm-palette-title small {
                    font-size:10px;
                    opacity:.68;
                    white-space:normal;
                    line-height:1.45;
                }
                .dco-algorithm-palette-chevron {
                    flex:0 0 auto;
                    width:25px;
                    height:25px;
                    display:grid;
                    place-items:center;
                    border-radius:8px;
                    background:var(--subtle-fg,#f1f5f9);
                    font-size:14px;
                    transition:transform .18s ease;
                }
                .dco-algorithm-palette.is-open .dco-algorithm-palette-chevron {
                    transform:rotate(180deg);
                }
                .dco-algorithm-palette-body {
                    display:none;
                    padding:0 11px 11px;
                    border-top:1px solid var(--border-color,#e2e8f0);
                }
                .dco-algorithm-palette.is-open .dco-algorithm-palette-body {
                    display:block;
                }
                .dco-algorithm-search-wrap {
                    position:relative;
                    padding:10px 0;
                }
                .dco-algorithm-search {
                    width:100%;
                    height:36px;
                    border:1px solid var(--border-color,#dfe3e8);
                    border-radius:9px;
                    padding:6px 10px;
                    background:var(--control-bg,var(--fg-color,#fff));
                    color:var(--text-color,#1f2937);
                    font-size:11px;
                }
                .dco-algorithm-groups {
                    display:grid;
                    grid-template-columns:repeat(2,minmax(0,1fr));
                    gap:9px;
                }
                .dco-algorithm-group {
                    min-width:0;
                    padding:9px;
                    border:1px solid var(--border-color,#e2e8f0);
                    border-radius:10px;
                    background:var(--subtle-fg,#f8fafc);
                }
                .dco-algorithm-group-head {
                    margin-bottom:7px;
                }
                .dco-algorithm-group-head strong {
                    display:block;
                    font-size:11px;
                    font-weight:850;
                }
                .dco-algorithm-group-head small {
                    display:block;
                    margin-top:2px;
                    font-size:9px;
                    line-height:1.45;
                    opacity:.65;
                }
                .dco-algorithm-choices {
                    display:grid;
                    grid-template-columns:repeat(2,minmax(0,1fr));
                    gap:6px;
                }
                .dco-algorithm-choice {
                    min-width:0;
                    min-height:34px;
                    display:flex;
                    align-items:center;
                    justify-content:space-between;
                    gap:7px;
                    padding:6px 8px;
                    border:1px solid var(--border-color,#d7dde5);
                    border-radius:8px;
                    background:var(--fg-color,#fff);
                    color:var(--text-color,#1f2937);
                    font-size:10px;
                    font-weight:750;
                    line-height:1.35;
                    text-align:start;
                    cursor:pointer;
                    transition:border-color .15s ease,box-shadow .15s ease,transform .15s ease;
                }
                .dco-algorithm-choice:hover:not(:disabled) {
                    border-color:var(--primary,#2490ef);
                    box-shadow:0 3px 9px rgba(36,144,239,.10);
                    transform:translateY(-1px);
                }
                .dco-algorithm-choice.is-active {
                    border-color:var(--primary,#2490ef);
                    background:rgba(36,144,239,.09);
                    color:var(--primary,#2490ef);
                    box-shadow:inset 0 0 0 1px rgba(36,144,239,.08);
                }
                .dco-algorithm-choice:disabled {
                    cursor:not-allowed;
                    opacity:.55;
                }
                .dco-algorithm-check {
                    flex:0 0 auto;
                    width:17px;
                    height:17px;
                    display:grid;
                    place-items:center;
                    border-radius:50%;
                    background:var(--subtle-fg,#eef2f7);
                    font-size:10px;
                    opacity:.72;
                }
                .dco-algorithm-choice.is-active .dco-algorithm-check {
                    background:var(--primary,#2490ef);
                    color:#fff;
                    opacity:1;
                }
                .dco-algorithm-empty {
                    display:none;
                    padding:15px 8px 5px;
                    text-align:center;
                    font-size:11px;
                    opacity:.68;
                }
                .dco-algorithm-empty.is-visible { display:block; }
                .dco-algorithm-help {
                    margin-top:9px;
                    padding-top:8px;
                    border-top:1px dashed var(--border-color,#dfe3e8);
                    font-size:9px;
                    line-height:1.55;
                    opacity:.68;
                }
                @media (max-width:1100px) {
                    .dco-algorithm-groups { grid-template-columns:1fr; }
                }
                @media (max-width:560px) {
                    .dco-algorithm-choices { grid-template-columns:1fr; }
                    .dco-algorithm-palette-title small { display:none; }
                }
            </style>
        `);
    }

    function normalize(value) {
        return String(value || "")
            .toLocaleLowerCase("ar")
            .replace(/[أإآ]/g, "ا")
            .replace(/ى/g, "ي")
            .replace(/ة/g, "ه")
            .trim();
    }

    function groupHtml(group, currentMode, enabled) {
        const buttons = group.modes.map((mode) => {
            const active = mode.value === currentMode;
            const searchable = `${group.label} ${mode.label} ${mode.value} ${mode.description || ""}`;
            return `
                <button type="button"
                    class="dco-algorithm-choice${active ? " is-active" : ""}"
                    data-algorithm-mode="${esc(mode.value)}"
                    data-algorithm-search="${esc(normalize(searchable))}"
                    title="${esc(mode.description || `${group.label} - ${mode.label}`)}"
                    aria-pressed="${active ? "true" : "false"}"
                    ${enabled ? "" : "disabled"}>
                    <span>${esc(mode.label)}</span>
                    <span class="dco-algorithm-check" aria-hidden="true">${active ? "✓" : "›"}</span>
                </button>
            `;
        }).join("");
        return `
            <section class="dco-algorithm-group" data-algorithm-group="${esc(group.key)}">
                <div class="dco-algorithm-group-head">
                    <strong>${esc(group.label)}</strong>
                    <small>${esc(group.hint)}</small>
                </div>
                <div class="dco-algorithm-choices">${buttons}</div>
            </section>
        `;
    }

    function paletteHtml(frm) {
        const currentMode = frm.doc.packing_mode || "Auto Pro";
        const enabled = canEdit(frm);
        const open = Boolean(frm.__almdina_algorithm_palette_open);
        return `
            <div class="dco-algorithm-palette${open ? " is-open" : ""}">
                <button type="button" class="dco-algorithm-palette-toggle" aria-expanded="${open ? "true" : "false"}">
                    <span class="dco-algorithm-palette-title">
                        <strong>قائمة جميع خوارزميات الترتيب</strong>
                        <small>الخوارزمية الحالية: ${esc(currentMode)} · افتح القائمة للاختيار والتشغيل مباشرة.</small>
                    </span>
                    <span class="dco-algorithm-palette-chevron" aria-hidden="true">⌄</span>
                </button>
                <div class="dco-algorithm-palette-body">
                    <div class="dco-algorithm-search-wrap">
                        <input type="search" class="dco-algorithm-search" placeholder="ابحث باسم الخوارزمية..." autocomplete="off" aria-label="البحث في خوارزميات الترتيب">
                    </div>
                    <div class="dco-algorithm-groups">
                        ${ALGORITHM_GROUPS.map((group) => groupHtml(group, currentMode, enabled)).join("")}
                    </div>
                    <div class="dco-algorithm-empty">لا توجد خوارزمية مطابقة للبحث.</div>
                    <div class="dco-algorithm-help">
                        الضغط على أي خوارزمية يحددها ويعيد حساب الخطة مباشرة. زر «إعادة الحساب بالإعدادات الحالية» يبقى متاحًا لتطبيق تغييرات الماكينة والهامش وعرض القص دون تغيير الخوارزمية.
                    </div>
                </div>
            </div>
        `;
    }

    function applySearch($palette, query) {
        const needle = normalize(query);
        let visibleCount = 0;
        $palette.find(".dco-algorithm-group").each(function filterGroup() {
            const $group = $(this);
            let groupVisible = 0;
            $group.find(".dco-algorithm-choice").each(function filterChoice() {
                const $choice = $(this);
                const matches = !needle || String($choice.attr("data-algorithm-search") || "").includes(needle);
                $choice.toggle(matches);
                if (matches) groupVisible += 1;
            });
            $group.toggle(groupVisible > 0);
            visibleCount += groupVisible;
        });
        $palette.find(".dco-algorithm-empty").toggleClass("is-visible", visibleCount === 0);
    }

    async function selectAndRecalculate(frm, mode, $palette) {
        if (!canEdit(frm)) return;
        frm.__almdina_algorithm_palette_open = true;
        $palette.find(".dco-algorithm-choice").prop("disabled", true);
        try {
            if (frm.doc.packing_mode !== mode) {
                await frm.set_value("packing_mode", mode);
            }
            requestAnimationFrame(() => {
                const field = frm.fields_dict.plan_control_actions;
                const $recalculate = field && field.$wrapper
                    ? field.$wrapper.find(".dco-recalculate-plan").first()
                    : $();
                if ($recalculate.length && !$recalculate.prop("disabled")) {
                    $recalculate.trigger("click");
                }
            });
        } catch (error) {
            console.error("Failed to select cutting algorithm", error);
            $palette.find(".dco-algorithm-choice").prop("disabled", !canEdit(frm));
            throw error;
        }
    }

    function bindPalette(frm, $palette) {
        $palette.find(".dco-algorithm-palette-toggle").on("click", () => {
            frm.__almdina_algorithm_palette_open = !frm.__almdina_algorithm_palette_open;
            $palette.toggleClass("is-open", frm.__almdina_algorithm_palette_open);
            $palette.find(".dco-algorithm-palette-toggle").attr("aria-expanded", frm.__almdina_algorithm_palette_open ? "true" : "false");
            if (frm.__almdina_algorithm_palette_open) {
                requestAnimationFrame(() => $palette.find(".dco-algorithm-search").trigger("focus"));
            }
        });
        $palette.find(".dco-algorithm-search").on("input", function onSearch() {
            applySearch($palette, $(this).val());
        });
        $palette.find(".dco-algorithm-choice").on("click", function onAlgorithmClick() {
            selectAndRecalculate(frm, $(this).attr("data-algorithm-mode"), $palette);
        });
    }

    function renderPalette(frm) {
        installStyles();
        const field = frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;
        const $shell = field.$wrapper.find(".dco-plan-actions-shell").first();
        const $actions = $shell.find(".dco-plan-actions").first();
        if (!$shell.length || !$actions.length) return;
        $shell.find(".dco-algorithm-palette").remove();
        const $palette = $(paletteHtml(frm));
        $actions.after($palette);
        bindPalette(frm, $palette);
    }

    function scheduleRender(frm) {
        requestAnimationFrame(() => renderPalette(frm));
        setTimeout(() => renderPalette(frm), 0);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { scheduleRender(frm); },
        refresh(frm) { scheduleRender(frm); },
        packing_mode(frm) { scheduleRender(frm); },
        cutting_machine_type(frm) { scheduleRender(frm); },
    });
})();
