"""MariaDB proof for customer-bot settings permissions, draft, and publish.

The test rolls back its users and edits. It does not delete retired phone
rows or change the factory WhatsApp session.
"""

from __future__ import annotations

import json

import frappe
from frappe.auth import CookieManager, LoginManager
from frappe.tests.utils import FrappeTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client, set_request

from almdina_erp.almdina_erp.domain.customer_bot.message_templates import validate_texts
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_records import (
    customer_bot_settings_has_permission,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
    DOCTYPE,
    FrappeCustomerBotSettingsRepository,
    load_customer_bot_runtime,
)
from almdina_erp.almdina_erp.services.customer_bot_settings_service import (
    get_customer_bot_settings,
    preview_customer_bot,
    publish_customer_bot_texts,
    save_customer_bot_draft,
    set_customer_bot_enabled,
)
from almdina_erp.almdina_erp.services.production_settings_service import (
    get_production_settings,
    update_production_settings,
)
from almdina_erp.patches.v1_0.install_customer_bot_settings import execute as install_settings


BOT_ROLE = "Almdina Customer Bot Settings Tester"
WHATSAPP_ROLE = "Almdina WhatsApp Message Tester"
BOT_USER = "cbot-settings-tester@example.com"
WHATSAPP_USER = "cbot-whatsapp-tester@example.com"


class TestCustomerBotSettingsIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls._delete_fixtures()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        cls._delete_fixtures()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self._ensure_role(BOT_ROLE)
        self._ensure_role(WHATSAPP_ROLE)
        self._ensure_user(BOT_USER, BOT_ROLE)
        self._ensure_user(WHATSAPP_USER, WHATSAPP_ROLE)
        self._grant(BOT_ROLE, DOCTYPE, {"manage_customer_bot_settings": 1})
        self._grant(WHATSAPP_ROLE, "Almdina ERP Settings", {"edit_whatsapp_messages": 1})
        frappe.clear_cache()
        frappe.set_user("Administrator")
        self._settings_before = {
            row.field: row.value
            for row in frappe.db.sql(
                "select field, value from `tabSingles` where doctype=%s",
                (DOCTYPE,),
                as_dict=True,
            )
        }

    def tearDown(self):
        frappe.set_user("Administrator")
        for field, value in getattr(self, "_settings_before", {}).items():
            frappe.db.sql(
                "update `tabSingles` set value=%s where doctype=%s and field=%s",
                (value, DOCTYPE, field),
            )
        super().tearDown()

    def test_capability_opens_the_page_without_other_sections(self) -> None:
        phones_before = frappe.db.count("Customer Bot Phone Access")
        frappe.set_user(WHATSAPP_USER)
        with self.assertRaises(frappe.PermissionError):
            get_customer_bot_settings()
        frappe.set_user(BOT_USER)
        self.assertFalse(customer_bot_settings_has_permission(ptype="write"))
        page = get_production_settings()
        permissions = page["permissions"]
        self.assertTrue(permissions["can_view"])
        self.assertTrue(permissions["can_manage_customer_bot_settings"])
        self.assertFalse(permissions["can_manage_whatsapp_session"])
        self.assertFalse(permissions["can_manage_backups"])
        self.assertFalse(permissions["can_restore_backups"])
        self.assertFalse(any(section["editable"] for section in permissions["sections"].values()))
        with self.assertRaises(frappe.PermissionError):
            update_production_settings({"default_kerf_mm": 4})
        self.assertEqual(frappe.db.count("Customer Bot Phone Access"), phones_before)

    def test_authenticated_rpc_loads_settings_with_closed_native_docperm(self) -> None:
        frappe.set_user(BOT_USER)
        self.assertFalse(frappe.has_permission(DOCTYPE, "read", user=BOT_USER))

        response = self._rpc_as(BOT_USER, "get_customer_bot_settings")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertTrue(response.json["message"]["ok"])
        self.assertGreaterEqual(response.json["message"]["revision"], 1)

    def test_unauthorized_authenticated_rpc_is_rejected(self) -> None:
        response = self._rpc_as(WHATSAPP_USER, "get_customer_bot_settings")

        self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
        self.assertEqual(response.json["exc_type"], "PermissionError")

    @staticmethod
    def _rpc_as(user: str, method: str):
        set_request(path="/")
        frappe.local.cookie_manager = CookieManager()
        frappe.local.login_manager = LoginManager()
        frappe.local.login_manager.login_as(user)
        sid = frappe.session.sid
        return make_request(
            target=get_test_client().post,
            args=(
                f"/api/method/almdina_erp.almdina_erp.services.customer_bot_settings_service.{method}",
            ),
            kwargs={"json": {"sid": sid}, "base_url": "http://almdina.local"},
        )

    def test_draft_publish_conflict_and_switch_use_the_stored_row(self) -> None:
        frappe.set_user("Administrator")
        repository = FrappeCustomerBotSettingsRepository()
        original = repository.load()
        self.assertFalse(original.enabled)
        self.assertEqual(validate_texts(original.published), ())
        custom = dict(original.draft)
        custom["welcome"] = "أهلاً من اختبار الإعدادات"
        frappe.set_user(BOT_USER)
        saved = save_customer_bot_draft(original.revision, json.dumps(custom))
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["draft"]["welcome"], custom["welcome"])
        self.assertEqual(saved["published"]["welcome"], original.published["welcome"])
        self.assertFalse(saved["enabled"])
        rejected = publish_customer_bot_texts(
            saved["revision"],
            json.dumps({**custom, "welcome": "Hello {customer.name}"}),
        )
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["code"], "invalid_texts")
        frappe.set_user("Administrator")
        self.assertEqual(repository.load().published["welcome"], original.published["welcome"])
        frappe.set_user(BOT_USER)
        published = publish_customer_bot_texts(saved["revision"], json.dumps(custom))
        self.assertTrue(published["ok"])
        self.assertEqual(published["published"]["welcome"], custom["welcome"])
        self.assertFalse(published["enabled"])
        conflict = save_customer_bot_draft(saved["revision"], json.dumps(custom))
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["code"], "conflict")
        frappe.set_user("Administrator")
        self.assertEqual(repository.load().published["welcome"], custom["welcome"])
        frappe.db.sql(
            "update `tabSingles` set value=%s where doctype=%s and field='draft_texts'",
            ("{not-json", DOCTYPE),
        )
        frappe.set_user(BOT_USER)
        disabled = set_customer_bot_enabled(repository.load().revision, 0)
        self.assertTrue(disabled["ok"])
        self.assertFalse(disabled["enabled"])
        frappe.db.sql(
            "update `tabSingles` set value=%s where doctype=%s and field='published_texts'",
            ("{not-json", DOCTYPE),
        )
        frappe.db.sql(
            "update `tabSingles` set value='0' where doctype=%s and field='enabled'",
            (DOCTYPE,),
        )
        blocked = set_customer_bot_enabled(repository.load().revision, 1)
        self.assertFalse(blocked["ok"])
        frappe.set_user("Administrator")
        self.assertFalse(repository.load().enabled)
        runtime = load_customer_bot_runtime()
        self.assertFalse(runtime.enabled)
        self.assertFalse(runtime.accepting_messages)

    def test_preview_does_not_write_or_require_a_real_customer(self) -> None:
        frappe.set_user("Administrator")
        before = FrappeCustomerBotSettingsRepository().load()
        customers_before = frappe.db.count("Customer")
        frappe.set_user(BOT_USER)
        result = preview_customer_bot(
            source="draft",
            scenario="unknown_number",
            text="مرحبا",
            texts=json.dumps(before.draft),
        )
        self.assertTrue(result["ok"])
        self.assertIn("غير مسجل", "\n".join(result["lines"]))
        frappe.set_user("Administrator")
        after = FrappeCustomerBotSettingsRepository().load()
        self.assertEqual(after.enabled, before.enabled)
        self.assertEqual(after.revision, before.revision)
        self.assertEqual(after.published, before.published)
        self.assertEqual(frappe.db.count("Customer"), customers_before)
        install_settings()
        self.assertEqual(
            FrappeCustomerBotSettingsRepository().load().draft["welcome"],
            before.draft["welcome"],
        )

    def test_direct_document_save_is_rejected(self) -> None:
        frappe.set_user("Administrator")
        document = frappe.get_doc(DOCTYPE)
        document.enabled = 1
        with self.assertRaises(frappe.PermissionError):
            document.save()

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True
            )

    @classmethod
    def _ensure_user(cls, email: str, role: str) -> None:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": role,
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                }
            ).insert(ignore_permissions=True)
        if role not in {row.role for row in (user.roles or [])}:
            user.append("roles", {"role": role})
            user.save(ignore_permissions=True)

    @classmethod
    def _grant(cls, role: str, doctype: str, values: dict[str, int]) -> None:
        frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0})
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
                **values,
            }
        ).insert(ignore_permissions=True)

    @classmethod
    def _delete_fixtures(cls) -> None:
        for email in (BOT_USER, WHATSAPP_USER):
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, force=True, ignore_permissions=True)
        for role in (BOT_ROLE, WHATSAPP_ROLE):
            frappe.db.delete("Custom DocPerm", {"role": role})
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
