(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsViewModel) return;

    function create(options = {}) {
        const translate = options.translate;
        if (typeof translate !== "function") {
            throw new Error("Production Settings view-model translator is unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);

        function values(current = {}) {
            return current.values || current || {};
        }

        function sectionEditable(current, section) {
            return Boolean(
                current
                && current.permissions
                && current.permissions.sections
                && current.permissions.sections[section]
                && current.permissions.sections[section].editable
            );
        }

        function yesNo(value) {
            return Number(value || 0) ? t("نعم") : t("لا");
        }

        function display(value, fallback = "—") {
            return value === undefined || value === null || value === "" ? fallback : value;
        }

        function catalogLabel(current, catalogName, value) {
            const normalized = String(value || "").trim();
            if (!normalized) return "—";
            const catalog = Array.isArray(current && current[catalogName])
                ? current[catalogName]
                : [];
            const entry = catalog.find(item => String(item && item.id || "").trim() === normalized);
            return entry ? String(entry.label || entry.id || normalized) : normalized;
        }

        function section(key, title, description, rows, current) {
            return {
                key,
                title,
                description,
                editable: sectionEditable(current, key),
                rows: rows.map(([label, value, multiline = false]) => ({
                    label,
                    value: display(value),
                    multiline,
                })),
            };
        }

        function sections(current = {}) {
            const source = values(current);
            return [
                section("cutting", t("القص والمحسّن"), t("الهندسة الافتراضية وخوارزمية التوزيع وحدود البحث."), [
                    [t("Kerf الافتراضي (مم)"), source.default_kerf_mm],
                    [t("هامش التشذيب (مم)"), source.default_trim_margin_mm],
                    [t("الخوارزمية"), t(catalogLabel(current, "optimization_catalog", source.default_packing_mode))],
                    [t("نوع آلة القص"), t(catalogLabel(current, "machine_type_catalog", source.default_cutting_machine_type))],
                    [t("مهلة التحسين (ث)"), source.default_optimization_time_limit_sec],
                    [t("حد القطع للبحث الأمثل"), source.optimal_search_piece_limit],
                ], current),
                section("costing", t("التكلفة الافتراضية"), t("أجرة القص ورسوم الدرف الخاصة وهوامشها الافتراضية."), [
                    [t("أجرة القص / لوح"), `${display(source.default_cutting_cost_per_board_usd)} USD`],
                    [t("رسم التصميم الخاص"), `${display(source.default_special_design_fee_usd)} USD`],
                    [t("رسم CNC الخاص"), `${display(source.default_special_cnc_fee_usd)} USD`],
                    [t("رسم القشاط اليدوي"), `${display(source.default_special_manual_edge_fee_usd)} USD`],
                    [t("هامش الدرف الخاصة"), `${display(source.default_special_margin_percent)}%`],
                ], current),
                section("extra_addons", t("إضافات الدرف Extra"), t("أسعار بيع ثابتة لكل درفة. يحفظ الطلب نسخة السعر وقت إنشائه ولا تتأثر الطلبات القديمة لاحقًا."), [
                    [t("Double / درفة"), `${display(source.default_extra_double_unit_price_usd)} USD`],
                    [t("أجرة دبل كامل الدرفة"), `${display(source.default_extra_full_door_double_unit_price_usd)} USD`],
                    [t("Liner / درفة"), `${display(source.default_extra_liner_unit_price_usd)} USD`],
                    [t("فرزة ظهر / درفة"), `${display(source.default_extra_back_groove_unit_price_usd)} USD`],
                    [t("تفريغ مسكة مخفية / درفة"), `${display(source.default_extra_recessed_handle_cutout_unit_price_usd)} USD`],
                ], current),
                section("production", t("ضوابط الإنتاج"), t("يمكن ترك المسار الافتراضي فارغًا وبناء المسارات من شاشة إدارة المسارات. عند إرسال الطلب للإنتاج يجب اختيار مسار فعلي."), [
                    [t("مسار الإنتاج الافتراضي"), source.default_production_routing || t("غير محدد")],
                    [t("تجاوز تسلسل المراحل"), source.allow_stage_override ? t("مسموح") : t("غير مسموح")],
                    [t("اعتماد قطع غير موزعة"), source.allow_unplaced_approval ? t("مسموح") : t("غير مسموح")],
                ], current),
                section("print_identity", t("هوية أوراق الطباعة"), t("تظهر هذه البيانات تلقائيًا في طباعة القياسات وخطة القص وفاتورة الزبون."), [
                    [t("اسم المعمل"), source.print_factory_name],
                    [t("لمحة عن المعمل"), source.print_factory_description],
                    [t("العنوان"), source.print_factory_address],
                    [t("أرقام التواصل"), source.print_factory_contacts || "—", true],
                ], current),
            ];
        }

        function legacy(current = {}) {
            const source = current.legacy_values || {};
            if (!source || typeof source !== "object") return [];
            return [
                [t("التحكم القديم بالمخزون"), yesNo(source.enforce_stock_control)],
                [t("المستودع الافتراضي القديم"), display(source.default_warehouse)],
                [t("حجز المخزون عند الاعتماد"), yesNo(source.reserve_stock_on_approval)],
                [t("نقطة استهلاك المخزون"), display(source.stock_consumption_point)],
                [t("تفضيل بقايا الألواح قبل الألواح الكاملة"), yesNo(source.prefer_remnants_before_full_boards)],
                [t("أدنى عرض للبقايا (مم)"), display(source.min_remnant_width_mm)],
                [t("أدنى طول للبقايا (مم)"), display(source.min_remnant_length_mm)],
                [t("أدنى مساحة للبقايا (م²)"), display(source.min_remnant_area_m2)],
                [t("سياسة تكلفة البقايا"), display(source.remnant_cost_policy)],
                [t("سعر البقايا / م²"), `${display(source.remnant_rate_usd_per_m2)} USD`],
            ].map(([label, value]) => ({ label, value }));
        }

        function page(current = {}) {
            return {
                sections: sections(current),
                legacy: legacy(current),
                hasLegacy: Boolean(current.legacy_values && typeof current.legacy_values === "object"),
            };
        }

        return Object.freeze({
            values,
            sectionEditable,
            yesNo,
            display,
            catalogLabel,
            sections,
            legacy,
            page,
        });
    }

    window.AlmdinaFactoryProductionSettingsViewModel = Object.freeze({ create });
})();
