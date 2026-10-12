from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = ROOT / "public" / "js"
LOCALE_JS = PUBLIC_JS / "almdina_locale.js"
PRINT_PRESENTER = (
    PUBLIC_JS
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_print_presenter.js"
)
NOTES_UI = (
    PUBLIC_JS / "notes" / "notes_panel.js",
    PUBLIC_JS / "notes" / "notes_dco_list_integration.js",
)
NESTED_TRANSLATION = re.compile(r"\bt\s*\(\s*__\s*\(")
STORED_VALUE_TRANSLATION = re.compile(r"(?:value|options)\s*:\s*(?:__|t)\s*\(")
ARABIC_TEXT = re.compile(r"[\u0600-\u06FF]")
# Stored quote phrases matched for compatibility. They are not displayed as UI.
PRINT_COMPATIBILITY_ARABIC = (
    "من القشاط الافتراضي",
    "يتضمن أطرافًا مخصصة",
)


class TestActiveUiHasNoLanguageTextBranches(unittest.TestCase):
    def test_is_arabic_is_not_used_to_choose_interface_text(self) -> None:
        offenders = []
        for path in PUBLIC_JS.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            if "function isArabic" in text or "isArabic()" in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_dom_text_replacement_file_stays_removed(self) -> None:
        self.assertFalse((PUBLIC_JS / "arabic_operator_ui.js").exists())

    def test_javascript_does_not_wrap_translation_calls_or_stored_values(self) -> None:
        offenders = []
        for path in PUBLIC_JS.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            relative = str(path.relative_to(ROOT))
            if NESTED_TRANSLATION.search(text):
                offenders.append(relative + ": t(__())")
            if STORED_VALUE_TRANSLATION.search(text):
                offenders.append(relative + ": translated stored value")
        self.assertEqual(offenders, [])

    def test_locale_foundation_translates_inside_functions_and_keeps_official_codes(self) -> None:
        source = LOCALE_JS.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^(?:const|let|var)\s+\w+\s*=\s*__\(", source, re.M))
        official = source.split("function officialLanguageCode(", 1)[1].split("function ", 1)[0]
        self.assertNotIn("toLowerCase", official)
        self.assertNotIn('.toLowerCase().replace(/_/g, "-")', source)

    def test_browser_print_presenter_keeps_arabic_only_as_compatibility_values(self) -> None:
        leftovers = []
        for number, line in enumerate(PRINT_PRESENTER.read_text(encoding="utf-8").splitlines(), start=1):
            if not ARABIC_TEXT.search(line):
                continue
            visible = line
            for phrase in PRINT_COMPATIBILITY_ARABIC:
                visible = visible.replace(phrase, "")
            visible = visible.replace("،", "")
            if ARABIC_TEXT.search(visible):
                leftovers.append(f"{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_notes_ui_has_no_direct_arabic_literals(self) -> None:
        leftovers = []
        for path in NOTES_UI:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if ARABIC_TEXT.search(line):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_important_note_column_label_ignores_doctype_text(self) -> None:
        source = (PUBLIC_JS / "notes" / "notes_dco_list_integration.js").read_text(encoding="utf-8")
        self.assertNotIn("important.df.label ||", source)
        self.assertIn('label: __("Important note")', source)

    def test_workspace_navigation_visible_copy_uses_english_message_ids(self) -> None:
        home = (PUBLIC_JS / "almdina_workspace_home_ux.js").read_text(encoding="utf-8")
        title = home.split("const WORKSPACE_PAGE_TITLE", 1)[1].split("const ROOT_CLASS", 1)[0]
        sections = home.split("const SECTION_BY_BLOCK_ID", 1)[1].split("const SHORTCUT_BLOCK_TO_LINK", 1)[0]
        self.assertIsNone(ARABIC_TEXT.search(title))
        self.assertIsNone(ARABIC_TEXT.search(sections))
        self.assertIn("Factory management", title)
        self.assertIn("title:", sections)

        presentation = (PUBLIC_JS / "almdina_shortcut_presentation.js").read_text(encoding="utf-8")
        catalog = presentation.split("const SHORTCUT_BY_LINK_TO", 1)[1].split("const LABEL_TO_LINK_TO", 1)[0]
        compatibility = presentation.split("const LABEL_TO_LINK_TO", 1)[1].split(
            "const SHORTCUT_PRESENTATION", 1
        )[0]
        self.assertIsNone(ARABIC_TEXT.search(catalog))
        self.assertIn("label:", catalog)
        self.assertIsNotNone(ARABIC_TEXT.search(compatibility))

        shell = (PUBLIC_JS / "shared_shell.js").read_text(encoding="utf-8")
        self.assertIn('__("You do not have permission to access this section.")', shell)
        self.assertNotIn("لا تملك صلاحية الوصول إلى هذا القسم", shell)

    def test_special_shape_documentation_visible_copy_uses_english_message_ids(self) -> None:
        paths = (
            PUBLIC_JS / "special_shape_documentation" / "application" / "templates.js",
            PUBLIC_JS / "special_shape_documentation" / "presentation" / "workspace_shell.js",
            PUBLIC_JS / "special_shape_documentation" / "presentation" / "workspace_controller.js",
            PUBLIC_JS / "door_cutting_order" / "drawing" / "special_shape_facade.js",
            ROOT / "almdina_erp" / "page" / "door_drawing" / "door_drawing.js",
            ROOT / "almdina_erp" / "services" / "special_shape_workspace_service.py",
            ROOT / "almdina_erp" / "services" / "special_shape_drawing_validation_service.py",
        )
        leftovers = []
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if ARABIC_TEXT.search(line):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_order_entry_visible_copy_uses_english_message_ids(self) -> None:
        paths = (
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "door_cutting_order_order_tab_layout_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "door_cutting_order_cutting_machine_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "door_cutting_order_whatsapp_delivery_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "measurements" / "door_cutting_order_measurement_actions_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "measurements" / "door_cutting_order_measurement_toolbar_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_edge_color_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_multi_edge_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_edge_profile_controls_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_edge_profile_double_click_guard.js",
        )
        allowed = ("مشرحة", "لون القشاط")
        leftovers = []
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                visible = line
                for phrase in allowed:
                    visible = visible.replace(phrase, "")
                if ARABIC_TEXT.search(visible):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_plan_settings_visible_copy_uses_english_message_ids(self) -> None:
        paths = (
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_edit_session_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_settings_summary_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_fast_save_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_workspace_api.js",
        )
        leftovers = []
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if ARABIC_TEXT.search(line):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_plan_preview_visible_copy_uses_english_message_ids(self) -> None:
        paths = (
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_preview_session.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_preview_presenter.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_preview_edit_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_controls_ux.js",
        )
        leftovers = []
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if ARABIC_TEXT.search(line):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_plan_output_visible_copy_uses_english_message_ids(self) -> None:
        """Compatibility leftovers are data or legacy detectors, not visible UI copy."""
        paths = (
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_cutting_plan_renderer.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_drawing_approval_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_drawing_plan_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_board_presenter.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_content_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_context_actions_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_source_presentation.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_surface_bootstrap.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_tabs_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_workspace_presenter_adapter.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "door_cutting_order_text_board_plan_ux.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "secure_dxf_export.js",
            PUBLIC_JS / "door_cutting_order" / "cutting_plan" / "secure_dxf_upload.js",
        )
        # Historical department value, production DXF text, and labels used only to remove or detect old UI.
        allowed = (
            "رسم",
            "دبل القشاط",
            "دبل كامل",
            "الرسم / DXF",
            "دورة الطلب",
            "تصدير DXF",
            "تصدير DXF للرسم",
            "تصدير DXF للتعديل",
            "تصدير DXF لأوتوكاد",
            "تنزيل DXF المرفوع",
            "تنزيل DXF للإنتاج",
            "رفع ملف DXF",
            "استبدال ملف DXF",
            "اعتماد الرسم",
            "إعادة اعتماد الرسم",
            "طباعة خطة القص",
            "تصدير",
            "تنزيل",
            "الطلب:",
            "الزبون:",
            "اللوح:",
            "الصنف:",
            "مقاس اللوح الكامل",
            "سماكة القص",
            "طريقة الترتيب:",
        )
        leftovers = []
        ordered = tuple(sorted(allowed, key=len, reverse=True))
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                visible = line
                for phrase in ordered:
                    visible = visible.replace(phrase, "")
                if ARABIC_TEXT.search(visible):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_cost_invoice_visible_copy_uses_english_message_ids(self) -> None:
        """Compatibility leftovers match historical stored addon descriptions only."""
        paths = (
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_compact_pricing_ux.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_cost_edit_session_ux.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_cost_offcut_assignment_ux.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_cost_page_layout_ux.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_cost_permissions_ux.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_cost_presenter.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_cost_workspace_api.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_cost_workspace_presenter_adapter.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_cost_workspace_state.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_customer_invoice_addon_summary.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_customer_invoice_toolbar_ux.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_financial_documents_ux.js",
            PUBLIC_JS / "door_cutting_order" / "costing" / "door_cutting_order_multi_edge_documents_ux.js",
        )
        allowed = (
            "تفريغ مسكة مخفية",
            "حفر مسكة غطس",
            "مسكة غطس",
            "لاينر",
            "إضافة",
            "درفة",
            "رقم",
        )
        leftovers = []
        ordered = tuple(sorted(allowed, key=len, reverse=True))
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                visible = line
                for phrase in ordered:
                    visible = visible.replace(phrase, "")
                if ARABIC_TEXT.search(visible):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

        self.assertEqual(leftovers, [])

    def test_operational_shell_visible_copy_uses_english_message_ids(self) -> None:
        """Legacy cleanup labels and stored department values stay raw; visible UI uses English IDs."""
        paths = (
            PUBLIC_JS / "door_cutting_order" / "core" / "order_lifecycle.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_revision_ux.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_toolbar_stability_ux.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_page_edit_action_ux.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_action_permission_guard.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_form_sidebar_controller.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_workspace_freshness_ux.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_workspace_asset_status_ux.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_document_context.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_tab_edit_lifecycle_guard.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_plan_cost_workspace_visual_ux.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_save_render_performance_ux.js",
            PUBLIC_JS / "door_cutting_order" / "core" / "door_cutting_order_workspace_store.js",
            PUBLIC_JS / "door_cutting_order" / "list_view" / "door_cutting_order_list.js",
            PUBLIC_JS / "door_cutting_order" / "recovery" / "presentation" / "door_cutting_order_local_checkpoint.js",
        )
        allowed = (
            "دورة الطلب",
            "إرسال للمراجعة",
            "اعتماد الطلب",
            "اعتماد التعديل",
            "تعديل الطلب",
            "نسخ الطلب",
            "إنشاء نسخة تعديل",
            "إلغاء تخصيص قشاط الدرف",
            "إلغاء تخصيص قشاط الدرفة",
            "إلغاء تخصيص القشاط",
            "طباعة جدول القياسات",
            "طباعة القياسات",
            "طباعة خطة القص",
            "طباعة فاتورة الزبون",
            "تصدير DXF لأوتوكاد",
            "تصدير DXF",
            "تصدير",
            "تنزيل DXF المرفوع",
            "تصدير DXF للرسم",
            "تصدير DXF للتعديل",
            "تنزيل DXF للإنتاج",
            "رفع ملف DXF",
            "استبدال ملف DXF",
            "اعتماد الرسم",
            "إعادة اعتماد الرسم",
            "الرسم / DXF",
            "طباعة",
            "إرسال للإنتاج",
            "إلغاء الطلب",
            "استئناف الطلب",
            "إعادة حساب خطة القص",
            "إعادة للمسودة",
            "إرجاع لمرحلة سابقة",
            "عرض",
            "صالة الإنتاج",
            "الملاحظات",
            "بحث",
            "صلاحية",
            "رقم الطلب",
            "قيد العمل",
            "تم التسليم",
            "جاهز للتسليم",
            "تسليم",
        )
        leftovers = []
        ordered = tuple(sorted(allowed, key=len, reverse=True))
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                visible = line
                for phrase in ordered:
                    visible = visible.replace(phrase, "")
                if ARABIC_TEXT.search(visible):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_operational_shell_avoids_hardcoded_dir_and_translated_label_rtl(self) -> None:
        """Translated surfaces inherit direction; only the Order ID link may force LTR."""
        list_js = (
            PUBLIC_JS / "door_cutting_order" / "list_view" / "door_cutting_order_list.js"
        ).read_text(encoding="utf-8")
        self.assertNotRegex(list_js, r'\bdir\s*=\s*["\']rtl["\']')
        self.assertNotRegex(list_js, r'\bdir\s*=\s*["\']ltr["\']')
        self.assertIn('dir="${escapeHtml(uiDirection())}"', list_js)

        mobile_css = (ROOT / "public" / "css" / "door_cutting_order_mobile_list.css").read_text(
            encoding="utf-8"
        )
        order_row = mobile_css.split(".dco-card-order-row {", 1)[1].split("}", 1)[0]
        order_label = mobile_css.split(".dco-card-order-label {", 1)[1].split("}", 1)[0]
        order_link = mobile_css.split(".dco-card-order-link {", 1)[1].split("}", 1)[0]
        self.assertNotRegex(order_row, r"direction\s*:\s*(?:rtl|ltr)")
        self.assertRegex(order_label, r"direction\s*:\s*inherit")
        self.assertNotRegex(order_label, r"direction\s*:\s*rtl")
        self.assertRegex(order_link, r"direction\s*:\s*ltr")
        self.assertRegex(order_link, r"text-align\s*:\s*start")
        self.assertNotRegex(order_link, r"text-align\s*:\s*left")
        self.assertNotRegex(mobile_css, r"\.dco-card-order-label\s*\{[^}]*direction\s*:\s*rtl", re.S)

    def test_bidirectional_layout_uses_inherited_direction_and_logical_alignment(self) -> None:
        styles = (
            PUBLIC_JS
            / "door_cutting_order"
            / "cutting_plan"
            / "door_cutting_order_plan_content_styles.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("direction:rtl", styles.replace(" ", ""))
        self.assertNotIn("direction:ltr", styles.replace(" ", ""))
        for selector in (
            ".dco-plan-meta-strip",
            ".dco-margin-policy-alert",
            ".dco-uploaded-plan-mismatch-banner",
            ".dco-board-original-edges",
            ".dco-board-focus__dialog",
        ):
            self.assertIn(selector, styles)
            self.assertIn("direction:inherit", styles)

        for relative in (
            "door_cutting_order_multi_edge_documents_ux.js",
            "door_cutting_order_cost_page_layout_ux.js",
        ):
            source = (PUBLIC_JS / "door_cutting_order" / "costing" / relative).read_text(encoding="utf-8")
            self.assertNotRegex(source, r"text-align:\s*(?:right|left)\b")
        edge_styles = (
            PUBLIC_JS
            / "door_cutting_order"
            / "costing"
            / "door_cutting_order_multi_edge_documents_ux.js"
        ).read_text(encoding="utf-8")
        self.assertIn(".dco-cost-table--invoice td:nth-last-child(-n+2){direction:ltr", edge_styles)


if __name__ == "__main__":
    unittest.main()
