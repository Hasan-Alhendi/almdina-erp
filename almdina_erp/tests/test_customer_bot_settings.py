"""Customer-bot settings, template rendering, and preview isolation.

Storage permissions are proved separately on a development site. This module
does not open a site, a socket, or a customer document.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import unittest

from almdina_erp.almdina_erp.application.customer_bot.handle_conversation import (
    handle_customer_conversation,
)
from almdina_erp.almdina_erp.application.customer_bot.preview_conversation import (
    PREVIEW_SCENARIOS,
    preview_customer_bot_turn,
)
from almdina_erp.almdina_erp.application.customer_bot.read_runtime import (
    next_acceptance_epoch,
    read_customer_bot_runtime,
)
from almdina_erp.almdina_erp.application.customer_bot.settings_commands import (
    CustomerBotSettingsConflict,
    CustomerBotSettingsInvalid,
    CustomerBotSettingsSnapshot,
    publish_customer_bot_texts,
    save_customer_bot_draft,
    set_customer_bot_enabled,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    standard_permission_projection,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotMessage,
    BotMessageKey,
    BotService,
    service_for_menu_digit,
)
from almdina_erp.almdina_erp.domain.customer_bot.message_defaults import default_texts
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import (
    MENU_ENTRIES,
    CustomerTextRenderError,
    catalog_keys,
    composed_main_menu,
    render_customer_lines,
    validate_texts,
)
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import PublicOrderStatus
from almdina_erp.almdina_erp.domain.security.authorization import (
    FACTORY_SETTINGS_CAPABILITIES,
    Capability,
)
from almdina_erp.almdina_erp.domain.security.factory_settings import (
    decide_settings_update,
    expand_factory_settings_capabilities,
    settings_context,
)
from almdina_erp.patches.v1_0.install_customer_bot_settings import _merge_texts


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
ACTOR = "employee@example.com"
WHEN = "2026-10-19 09:00:00"


class _Store:
    def __init__(self, snapshot: CustomerBotSettingsSnapshot) -> None:
        self.snapshot = snapshot
        self.writes: list[object] = []

    def load(self) -> CustomerBotSettingsSnapshot:
        return self.snapshot

    def save_draft(self, texts, expected_revision, actor, modified):
        self.writes.append("draft")
        if expected_revision != self.snapshot.revision:
            return None
        self.snapshot = replace(
            self.snapshot,
            draft=dict(texts),
            revision=expected_revision + 1,
            modified=modified,
            modified_by=actor,
        )
        return self.snapshot

    def publish(self, texts, expected_revision, actor, modified):
        self.writes.append("publish")
        if expected_revision != self.snapshot.revision:
            return None
        copied = dict(texts)
        self.snapshot = replace(
            self.snapshot,
            draft=copied,
            published=copied,
            revision=expected_revision + 1,
            published_on=modified,
            published_by=actor,
            modified=modified,
            modified_by=actor,
        )
        return self.snapshot

    def set_enabled(self, enabled, expected_revision, actor, modified):
        self.writes.append(("enabled", enabled))
        if expected_revision != self.snapshot.revision:
            return None
        self.snapshot = replace(
            self.snapshot,
            enabled=enabled,
            acceptance_epoch=next_acceptance_epoch(
                self.snapshot.enabled,
                self.snapshot.acceptance_epoch,
                enabled,
            ),
            revision=expected_revision + 1,
            modified=modified,
            modified_by=actor,
        )
        return self.snapshot


def _snapshot(**changes) -> CustomerBotSettingsSnapshot:
    base = CustomerBotSettingsSnapshot(
        enabled=False,
        revision=1,
        draft=default_texts(),
        published=default_texts(),
        published_on=WHEN,
        published_by="Administrator",
        modified=WHEN,
        modified_by="Administrator",
    )
    return replace(base, **changes)


class CustomerBotTemplateTests(unittest.TestCase):
    def test_defaults_are_valid_and_the_menu_keeps_fixed_digits(self) -> None:
        self.assertEqual(validate_texts(default_texts()), ())
        menu = composed_main_menu(default_texts())
        self.assertEqual(
            [line.split("- ", 1)[0] for line in menu.splitlines()],
            ["1", "2", "3", "4"],
        )
        for digit, service_id in MENU_ENTRIES:
            self.assertEqual(service_for_menu_digit(digit), service_id)
        self.assertNotIn(BotMessageKey.MAIN_MENU, catalog_keys())

    def test_catalog_upgrade_preserves_custom_texts_and_adds_only_new_keys(self) -> None:
        old = {
            BotMessageKey.WELCOME: "ترحيب مخصص",
            BotMessageKey.ORDER_STATUS: "حالة مخصصة {order_name}: {public_status}",
        }
        merged = _merge_texts(old, default_texts())
        self.assertEqual(merged[BotMessageKey.WELCOME], old[BotMessageKey.WELCOME])
        self.assertEqual(merged[BotMessageKey.ORDER_STATUS], old[BotMessageKey.ORDER_STATUS])
        self.assertEqual(merged[BotMessageKey.FINAL_PRICE], default_texts()[BotMessageKey.FINAL_PRICE])
        self.assertEqual(
            merged[BotMessageKey.MEASUREMENTS],
            default_texts()[BotMessageKey.MEASUREMENTS],
        )
        self.assertIn("{order_name}", merged[BotMessageKey.MEASUREMENTS])
        self.assertNotIn("{amount}", merged[BotMessageKey.MEASUREMENTS])
        self.assertEqual(set(merged), set(default_texts()))
        self.assertEqual(_merge_texts(merged, default_texts()), merged)

    def test_catalog_covers_engine_messages_services_and_statuses(self) -> None:
        message_keys = {
            value
            for name, value in vars(BotMessageKey).items()
            if name.isupper() and isinstance(value, str)
        }
        services = {
            value
            for name, value in vars(BotService).items()
            if name.isupper() and isinstance(value, str)
        }
        statuses = {
            value
            for name, value in vars(PublicOrderStatus).items()
            if name.isupper() and isinstance(value, str)
        }
        editable = set(catalog_keys())
        self.assertEqual(message_keys - {BotMessageKey.MAIN_MENU}, {
            key for key in editable if "." not in key
        })
        self.assertTrue({f"service_title.{service_id}" for service_id in services} <= editable)
        self.assertTrue({f"status_label.{status}" for status in statuses} <= editable)

    def test_renderer_uses_allowed_fields_and_keeps_the_stored_order_name(self) -> None:
        lines = render_customer_lines(
            default_texts(),
            (
                BotMessage(
                    BotMessageKey.ORDER_STATUS,
                    (
                        ("order_name", "DCO-2026-00021"),
                        ("public_status", PublicOrderStatus.AWAITING_START),
                    ),
                ),
            ),
        )
        self.assertEqual(lines, ("DCO-2026-00021: بانتظار بدء العمل.",))
        self.assertNotIn("awaiting_start", lines[0])

    def test_service_placeholder_inserts_the_title_not_the_internal_id(self) -> None:
        texts = dict(default_texts())
        texts[BotMessageKey.SERVICE_UNAVAILABLE] = "{service_id} {order_name}"
        lines = render_customer_lines(
            texts,
            (
                BotMessage(
                    BotMessageKey.SERVICE_UNAVAILABLE,
                    (("service_id", BotService.FINAL_COST), ("order_name", "DCO-2026-00021")),
                ),
            ),
        )
        self.assertEqual(lines, ("لمعرفة تكلفة طلب DCO-2026-00021",))
        self.assertNotIn("final_cost", lines[0])

    def test_unknown_and_unsafe_placeholders_are_rejected_without_truncation(self) -> None:
        too_long = "ا" * 501
        cases = {
            "Hello {customer.name}": "invalid_syntax",
            "Hello {items[0]}": "invalid_syntax",
            "Hello {{order_name}}": "invalid_syntax",
            "Hello {order_name}": "unknown_variable",
            "Hello ${name}": "invalid_syntax",
            "Hello {upper(order_name)}": "invalid_syntax",
            "Hello {order_name": "invalid_syntax",
            too_long: "too_long",
            "   ": "empty",
        }
        for text, code in cases.items():
            texts = dict(default_texts())
            texts[BotMessageKey.WELCOME] = text
            issues = validate_texts(texts)
            self.assertEqual(issues[0].code, code, text)
            self.assertEqual(texts[BotMessageKey.WELCOME], text)

    def test_html_stays_plain_text_and_a_customer_failure_hides_the_key(self) -> None:
        texts = dict(default_texts())
        texts[BotMessageKey.WELCOME] = "<script>alert(1)</script>"
        self.assertEqual(
            render_customer_lines(texts, (BotMessage(BotMessageKey.WELCOME),)),
            ("<script>alert(1)</script>",),
        )
        with self.assertRaises(CustomerTextRenderError) as caught:
            render_customer_lines(
                default_texts(),
                (
                    BotMessage(BotMessageKey.WELCOME),
                    BotMessage(
                        BotMessageKey.ORDER_STATUS,
                        (("order_name", "DCO-1"), ("public_status", "secret")),
                    ),
                ),
            )
        self.assertEqual(str(caught.exception), "Customer bot text could not be rendered.")
        self.assertNotIn("order_status", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("Traceback", str(caught.exception))

    def test_no_current_orders_instruction_is_rendered_once(self) -> None:
        opened = preview_customer_bot_turn(default_texts(), "no_orders", "مرحبا", None, NOW)
        waiting = preview_customer_bot_turn(
            default_texts(),
            "no_orders",
            "1",
            opened.state,
            NOW + timedelta(seconds=1),
        )
        rendered = "\n".join(waiting.lines)
        self.assertEqual(rendered.count("أدخل"), 1)
        self.assertIn("لا توجد طلبات غير مسلّمة", rendered)

    def test_preview_uses_the_engine_and_does_not_invent_a_completed_service(self) -> None:
        seen = {}

        def engine(*args):
            seen["enabled"] = args[2].enabled
            return handle_customer_conversation(*args)

        unknown = preview_customer_bot_turn(
            default_texts(), "unknown_number", "مرحبا", None, NOW, engine=engine
        )
        self.assertTrue(seen["enabled"])
        self.assertIn("غير مسجل", "\n".join(unknown.lines))
        opened = preview_customer_bot_turn(default_texts(), "one_order", "مرحبا", None, NOW)
        unavailable = preview_customer_bot_turn(
            default_texts(),
            "one_order",
            "2",
            opened.state,
            NOW + timedelta(seconds=1),
        )
        rendered = "\n".join(unavailable.lines)
        self.assertIn("غير متاحة حالياً", rendered)
        self.assertNotIn("PDF", rendered)
        delivered = preview_customer_bot_turn(
            default_texts(), "delivered_order", "مرحبا", None, NOW
        )
        waiting = preview_customer_bot_turn(
            default_texts(),
            "delivered_order",
            "1",
            delivered.state,
            NOW + timedelta(seconds=1),
        )
        selected = preview_customer_bot_turn(
            default_texts(),
            "delivered_order",
            "PREVIEW-DCO-DELIVERED",
            waiting.state,
            NOW + timedelta(seconds=2),
        )
        self.assertIn("PREVIEW-DCO-DELIVERED", "\n".join(selected.lines))
        self.assertIn("تم التسليم", "\n".join(selected.lines))

    def test_preview_module_has_no_site_or_network_access(self) -> None:
        source = (
            ROOT / "almdina_erp" / "application" / "customer_bot" / "preview_conversation.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("frappe", "socket", "urllib", "httpx", "requests", "get_all", "whitelist"):
            self.assertNotIn(forbidden, source)
        self.assertEqual(
            PREVIEW_SCENARIOS,
            (
                "unknown_number",
                "no_orders",
                "one_order",
                "many_orders",
                "delivered_order",
                "cancelled_order",
            ),
        )


class CustomerBotSettingsCommandTests(unittest.TestCase):
    def test_draft_save_does_not_change_published_or_enabled(self) -> None:
        store = _Store(_snapshot())
        texts = dict(default_texts())
        texts[BotMessageKey.WELCOME] = "أهلاً بك"
        saved = save_customer_bot_draft(store, texts, 1, ACTOR, WHEN)
        self.assertEqual(saved.draft[BotMessageKey.WELCOME], "أهلاً بك")
        self.assertEqual(saved.published, default_texts())
        self.assertFalse(saved.enabled)
        self.assertEqual(saved.acceptance_epoch, 0)
        self.assertEqual(store.writes, ["draft"])

    def test_publish_replaces_the_published_copy_without_enabling(self) -> None:
        store = _Store(_snapshot())
        texts = dict(default_texts())
        texts[BotMessageKey.WELCOME] = "أهلاً بك"
        saved = publish_customer_bot_texts(store, texts, 1, ACTOR, WHEN)
        self.assertEqual(saved.published[BotMessageKey.WELCOME], "أهلاً بك")
        self.assertEqual(saved.draft, saved.published)
        self.assertFalse(saved.enabled)
        self.assertEqual(store.writes, ["publish"])

    def test_invalid_publish_leaves_the_published_copy(self) -> None:
        store = _Store(_snapshot())
        texts = dict(default_texts())
        texts[BotMessageKey.WELCOME] = "Hello {customer.name}"
        with self.assertRaises(CustomerBotSettingsInvalid):
            publish_customer_bot_texts(store, texts, 1, ACTOR, WHEN)
        self.assertEqual(store.snapshot.published, default_texts())
        self.assertEqual(store.writes, [])

    def test_a_stale_revision_is_not_written(self) -> None:
        store = _Store(_snapshot(revision=4))
        with self.assertRaises(CustomerBotSettingsConflict):
            save_customer_bot_draft(store, default_texts(), 3, ACTOR, WHEN)
        self.assertEqual(store.snapshot.revision, 4)

    def test_disable_allows_an_invalid_draft_and_enable_requires_published_text(self) -> None:
        invalid = {"welcome": "{nope}"}
        disabled = _Store(_snapshot(enabled=True, draft=invalid))
        saved = set_customer_bot_enabled(disabled, False, 1, ACTOR, WHEN)
        self.assertFalse(saved.enabled)
        self.assertEqual(saved.acceptance_epoch, 1)
        self.assertEqual(saved.draft, invalid)
        enabled = set_customer_bot_enabled(disabled, True, saved.revision, ACTOR, WHEN)
        self.assertTrue(enabled.enabled)
        self.assertEqual(enabled.acceptance_epoch, 1)
        blocked = _Store(_snapshot(published={}))
        with self.assertRaises(CustomerBotSettingsInvalid):
            set_customer_bot_enabled(blocked, True, 1, ACTOR, WHEN)
        self.assertEqual(blocked.writes, [])
        self.assertFalse(blocked.snapshot.enabled)

    def test_runtime_reads_the_current_switch_each_time(self) -> None:
        store = _Store(_snapshot(enabled=False))
        self.assertFalse(read_customer_bot_runtime(store).accepting_messages)
        store.snapshot = replace(store.snapshot, enabled=True)
        self.assertTrue(read_customer_bot_runtime(store).accepting_messages)
        store.snapshot = replace(store.snapshot, published={})
        runtime = read_customer_bot_runtime(store)
        self.assertTrue(runtime.enabled)
        self.assertFalse(runtime.accepting_messages)
        self.assertIsNone(runtime.published)
        self.assertEqual(runtime.acceptance_epoch, 0)


class CustomerBotSettingsAccessTests(unittest.TestCase):
    def test_the_settings_capability_opens_only_its_section(self) -> None:
        expanded = expand_factory_settings_capabilities({Capability.MANAGE_CUSTOMER_BOT_SETTINGS})
        context = settings_context(expanded)
        self.assertIn(Capability.VIEW_FACTORY_SETTINGS, expanded)
        self.assertTrue(context["can_view"])
        self.assertTrue(context["can_manage_customer_bot_settings"])
        self.assertFalse(context["can_manage_whatsapp_session"])
        self.assertFalse(context["can_manage_backups"])
        self.assertFalse(context["can_restore_backups"])
        self.assertFalse(any(section["editable"] for section in context["sections"].values()))
        whatsapp = expand_factory_settings_capabilities(
            {Capability.MANAGE_WHATSAPP_SESSION, Capability.EDIT_WHATSAPP_MESSAGES}
        )
        self.assertNotIn(Capability.MANAGE_CUSTOMER_BOT_SETTINGS, whatsapp)
        self.assertFalse(settings_context(whatsapp)["can_manage_customer_bot_settings"])
        self.assertNotIn(Capability.MANAGE_CUSTOMER_BOT_ACCESS, FACTORY_SETTINGS_CAPABILITIES)
        decision = decide_settings_update(
            {Capability.MANAGE_CUSTOMER_BOT_SETTINGS},
            {"draft_texts": "{}"},
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "unknown_fields")
        projection = standard_permission_projection(
            "Customer Bot Settings",
            {Capability.MANAGE_CUSTOMER_BOT_SETTINGS: True},
        )
        self.assertEqual(
            projection,
            {"read": False, "select": False, "create": False, "write": False, "delete": False},
        )

    def test_endpoints_and_panel_stay_inside_their_owners(self) -> None:
        service = (ROOT / "almdina_erp" / "services" / "customer_bot_settings_service.py").read_text(
            encoding="utf-8"
        )
        panel = (ROOT / "public" / "js" / "factory_production_settings" / "customer_bot_panel.js").read_text(
            encoding="utf-8"
        )
        api = (ROOT / "public" / "js" / "factory_production_settings" / "api.js").read_text(encoding="utf-8")
        self.assertIn('methods=["POST"]', service)
        import frappe

        from almdina_erp.almdina_erp.services.customer_bot_settings_service import (
            get_customer_bot_settings,
        )

        allowed = frappe.allowed_http_methods_for_whitelisted_func[get_customer_bot_settings]
        self.assertIn("POST", allowed)
        self.assertNotIn("allow_guest", service)
        self.assertNotIn("webhook", service)
        self.assertNotIn("System Manager", service)
        self.assertIn(
            "The bot connection to WhatsApp is not active yet. These settings prepare its behavior when the link is complete.",
            panel,
        )
        for scenario in PREVIEW_SCENARIOS:
            self.assertIn(scenario, panel)
        self.assertNotIn("frappe.call(", panel)
        for endpoint in (
            "get_customer_bot_settings",
            "save_customer_bot_draft",
            "publish_customer_bot_texts",
            "set_customer_bot_enabled",
            "preview_customer_bot",
        ):
            self.assertIn(endpoint, api)
            self.assertNotIn(endpoint, panel)
        patch = (ROOT / "patches" / "v1_0" / "install_customer_bot_settings.py").read_text(encoding="utf-8")
        self.assertIn("tabSingles", patch)
        self.assertNotIn("frappe.db.exists", patch)
        self.assertIn('"enabled": 0', patch)

    def test_new_layers_do_not_import_frappe(self) -> None:
        files = (
            "almdina_erp/domain/customer_bot/message_templates.py",
            "almdina_erp/domain/customer_bot/message_defaults.py",
            "almdina_erp/application/customer_bot/settings_commands.py",
            "almdina_erp/application/customer_bot/preview_conversation.py",
            "almdina_erp/application/customer_bot/read_runtime.py",
            "almdina_erp/application/customer_bot/measurements_service.py",
        )
        for relative in files:
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("import frappe", source)
            self.assertNotIn("whatsapp", source.lower())


if __name__ == "__main__":
    unittest.main()
