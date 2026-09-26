from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js"
SETTINGS = PUBLIC / "factory_production_settings"
DELIVERY = (
    PUBLIC
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_whatsapp_delivery_ux.js"
)
PANEL = SETTINGS / "whatsapp_panel.js"
INVOICE_TOOLBAR = (
    PUBLIC
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_customer_invoice_toolbar_ux.js"
)
API = SETTINGS / "api.js"
RENDERER = SETTINGS / "renderer.js"
DIALOGS = SETTINGS / "dialogs.js"
CONTROLLER = SETTINGS / "controller.js"


class WhatsAppFrontendContractTests(unittest.TestCase):
    def test_openwa_secrets_never_reach_javascript(self) -> None:
        offenders = []
        for path in PUBLIC.rglob("*.js"):
            source = path.read_text(encoding="utf-8")
            for marker in ("OPENWA_API_KEY", "X-API-Key", "X-API-KEY"):
                if marker in source:
                    offenders.append(f"{path.relative_to(ROOT)}:{marker}")
        self.assertEqual(offenders, [])

    def test_whatsapp_settings_panel_polls_qr_every_five_seconds(self) -> None:
        panel = PANEL.read_text(encoding="utf-8")
        self.assertIn("const QR_INTERVAL_MS = 5000;", panel)
        self.assertIn("window.setInterval(tick, QR_INTERVAL_MS)", panel)
        self.assertIn("function stopPoll(", panel)
        self.assertIn("function closeQr(", panel)
        self.assertIn("onHide: stopPoll", panel)
        self.assertIn("api.getWhatsAppQr", panel)
        refresh_fn = panel.split("function refresh()", 1)[1].split("function create()", 1)[0]
        create_fn = panel.split("function create()", 1)[1].split("function reconnect()", 1)[0]
        reconnect_fn = panel.split("function reconnect()", 1)[1].split("function deactivate()", 1)[0]
        self.assertNotIn("maybeOpenQr(snapshot)", refresh_fn)
        self.assertIn("maybeOpenQr(snapshot)", create_fn)
        self.assertIn("maybeOpenQr(snapshot)", reconnect_fn)
        self.assertIn("api.createWhatsAppSession", panel)
        self.assertIn("api.reconnectWhatsAppSession", panel)

    def test_whatsapp_qr_dialog_only_renders_data_image_urls(self) -> None:
        dialogs = DIALOGS.read_text(encoding="utf-8")
        self.assertIn("function openQr(", dialogs)
        self.assertIn('source.indexOf("data:image/") === 0', dialogs)
        self.assertIn("يُحدَّث الرمز كل 5 ثوانٍ", dialogs)
        qr_block = dialogs.split("function openQr(", 1)[1]
        self.assertIn("${escapeHtml(", qr_block)
        self.assertNotIn("${esc(", qr_block)

    def test_whatsapp_card_is_live_and_not_a_settings_section(self) -> None:
        renderer = RENDERER.read_text(encoding="utf-8")
        controller = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("data-whatsapp-root", renderer)
        self.assertIn("إنشاء وربط WhatsApp", renderer)
        self.assertIn("إعادة اتصال", renderer)
        self.assertIn("whatsapp.refresh", controller)
        self.assertIn("viewModel.canManageWhatsAppSession(state.current)", controller)
        self.assertIn("model.canManageWhatsAppSession", renderer)
        self.assertNotIn("production_settings_service", controller)

    def test_section_save_refreshes_the_whatsapp_card(self) -> None:
        controller = CONTROLLER.read_text(encoding="utf-8")
        render_fn = controller.split("function render()", 1)[1].split("function load()", 1)[0]
        self.assertIn("renderer.render(viewModel.page(state.current))", render_fn)
        self.assertIn("whatsapp.refresh", render_fn)
        save_fn = controller.split("function openSectionDialog", 1)[1].split(
            "function openAudit", 1
        )[0]
        self.assertIn("store.apply(data || {});", save_fn)
        self.assertIn("render();", save_fn)

    def test_whatsapp_rpc_stays_in_settings_api_adapter(self) -> None:
        api = API.read_text(encoding="utf-8")
        panel = PANEL.read_text(encoding="utf-8")
        self.assertIn('const WHATSAPP = "almdina_erp.almdina_erp.services.whatsapp_service";', api)
        self.assertIn("${WHATSAPP}.get_whatsapp_session", api)
        self.assertIn("${WHATSAPP}.create_whatsapp_session", api)
        self.assertNotIn("whatsapp_service", panel)
        self.assertNotIn("frappe.call(", panel)

    def test_order_save_offer_is_explicit_order_tab_or_first_save(self) -> None:
        source = DELIVERY.read_text(encoding="utf-8")
        self.assertIn('coordinator.decorate("order"', source)
        self.assertIn("before_save(frm)", source)
        self.assertIn("frm.is_new()", source)
        self.assertIn("after_save(frm)", source)
        self.assertIn("هل تريد إرسال ملف القياسات للزبون؟", source)
        self.assertIn("هل تريد إرسال تعديلات القياسات للزبون؟", source)
        self.assertIn("إرسال القياسات عبر واتساب", source)
        self.assertIn("إرسال تعديلات القياسات عبر واتساب", source)
        self.assertIn("احفظ الطلب أولاً ثم أرسل جدول القياسات.", source)
        self.assertIn("dco-whatsapp-send-measurements", source)
        self.assertIn("canOfferEditSession", source)
        self.assertIn("offerFromButton", source)
        self.assertIn("syncSendButton", source)
        self.assertIn("لن يتم إرسال رسالة واتساب لأن الجلسة غير متصلة.", source)
        self.assertIn("get_whatsapp_delivery_status", source)
        self.assertIn("send_order_measurements", source)
        self.assertIn("amendment: isAmendmentContext(frm) ? 1 : 0", source)
        self.assertIn("CHECKPOINT_KEY", source)
        self.assertIn("print_measurements", source)
        self.assertNotIn("dco-fast-entry-toolbar", source)
        self.assertNotIn("OPENWA_API_KEY", source)
        self.assertNotIn("X-API-Key", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("printMeasurementsHtml", source)
        self.assertNotIn("Door Cutting Measurements", source)

    def test_cost_tab_invoice_send_confirms_then_uses_server_invoice_rpc(self) -> None:
        source = INVOICE_TOOLBAR.read_text(encoding="utf-8")
        self.assertIn("إرسال الفاتورة عبر واتساب", source)
        self.assertIn("هل تريد إرسال الفاتورة للزبون؟", source)
        self.assertIn("dco-whatsapp-send-invoice", source)
        self.assertIn("frappe.confirm(INVOICE_CONFIRM_MESSAGE", source)
        self.assertIn("send_order_invoice", source)
        self.assertIn("get_whatsapp_delivery_status", source)
        self.assertIn('can(frm, "print_customer_invoice")', source)
        self.assertNotIn("print_measurements", source)
        self.assertNotIn("OPENWA_API_KEY", source)
        self.assertNotIn("X-API-Key", source)
        self.assertNotIn("get_customer_invoice_document", source)

    def test_factory_settings_has_a_dedicated_whatsapp_messages_section(self) -> None:
        view_model = (PUBLIC / "factory_production_settings" / "view_model.js").read_text(
            encoding="utf-8"
        )
        dialogs = (PUBLIC / "factory_production_settings" / "dialogs.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('section("whatsapp_messages"', view_model)
        self.assertIn("رسائل واتساب", view_model)
        self.assertIn("whatsapp_measurements_text", view_model)
        self.assertIn("whatsapp_measurement_amendments_text", view_model)
        self.assertIn("رسالة تعديلات القياسات", view_model)
        self.assertIn("whatsapp_measurement_amendments_text", dialogs)
        self.assertIn("whatsapp_invoice_text", dialogs)
        self.assertIn('section === "whatsapp_messages"', dialogs)
        self.assertIn("{order_name}", view_model)
        self.assertIn("{stage_label}", view_model)
        self.assertIn("whatsapp_stage_message_rows", view_model)
        self.assertIn("whatsapp_stage_messages", dialogs)
        self.assertIn("function stageMessageFieldname(", dialogs)
        self.assertIn("function fieldInputValue(", dialogs)
        self.assertIn("field.$input.val()", dialogs)
        self.assertIn("dialog.set_values(nextValues)", dialogs)
        self.assertIn("current.permissions.can_manage_whatsapp_session", view_model)
        self.assertNotIn(
            't("تُرسل قبل ملف PDF لجدول القياسات. استخدم {order_name} لرقم الطلب.")',
            dialogs,
        )

    def test_permission_guard_hides_whatsapp_send_without_print_capability(self) -> None:
        guard = (
            PUBLIC
            / "door_cutting_order"
            / "core"
            / "door_cutting_order_action_permission_guard.js"
        ).read_text(encoding="utf-8")
        self.assertIn('const WHATSAPP_SEND_SELECTOR = ".dco-whatsapp-send-measurements";', guard)
        self.assertIn('const WHATSAPP_INVOICE_SELECTOR = ".dco-whatsapp-send-invoice";', guard)
        self.assertIn("hideUnlessAllowed(pageRoot(frm), WHATSAPP_SEND_SELECTOR, allowed)", guard)
        self.assertIn(
            "hideUnlessAllowed(formRoot(frm), WHATSAPP_INVOICE_SELECTOR, canSendInvoice)",
            guard,
        )

    def test_bound_session_id_stays_hidden_from_the_browser(self) -> None:
        settings = json.loads(
            (
                ROOT
                / "almdina_erp"
                / "doctype"
                / "almdina_erp_settings"
                / "almdina_erp_settings.json"
            ).read_text(encoding="utf-8")
        )
        fields = {row["fieldname"]: row for row in settings["fields"]}
        self.assertEqual(fields["whatsapp_session_id"].get("hidden"), 1)
        self.assertEqual(fields["whatsapp_session_name"].get("hidden"), 1)
        self.assertIn("whatsapp_session_id", settings["field_order"])
        self.assertIn("whatsapp_session_name", settings["field_order"])
        service = (
            ROOT / "almdina_erp" / "services" / "production_settings_service.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("whatsapp_session_id", service)
        self.assertNotIn("whatsapp_session_name", service)
        offenders = []
        for path in PUBLIC.rglob("*.js"):
            source = path.read_text(encoding="utf-8")
            if "whatsapp_session_id" in source or "whatsapp_session_name" in source:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_shop_floor_handoff_sends_stage_whatsapp_without_blocking(self) -> None:
        commands = (
            ROOT / "almdina_erp" / "services" / "shop_floor_commands.py"
        ).read_text(encoding="utf-8")
        inbox = (PUBLIC / "shop_floor_inbox" / "controller.js").read_text(encoding="utf-8")
        dialogs = (PUBLIC / "shop_floor_inbox" / "dialogs.js").read_text(encoding="utf-8")
        self.assertIn("def _stage_completion_whatsapp_context(", commands)
        self.assertIn("notify_stage_completion", commands)
        self.assertIn("payload[\"whatsapp\"]", commands)
        self.assertIn("data.whatsapp", inbox)
        self.assertIn("dialogs.whatsapp(data.whatsapp, generation)", inbox)
        self.assertIn("whatsapp(result, generation)", dialogs)


if __name__ == "__main__":
    unittest.main()
