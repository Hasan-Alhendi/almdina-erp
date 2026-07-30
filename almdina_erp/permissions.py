from __future__ import annotations

import frappe

SHOP_FLOOR_ROLES = ("عامل رسم", "عامل شريون", "عامل CNC", "عامل تقشيط")
ADMIN_ROLES = (
	"System Manager",
	"Production Manager",
	"Order Entry",
	"Accounts Management",
)
SHOP_FLOOR_WORKSPACE = "Shop Floor"
SHOP_FLOOR_PAGE = "shop-floor-inbox"

ORDER_ENTRY_ROLE = "Order Entry"
ORDER_ENTRY_WORKSPACE = "Almdina ERP"

# Roles that make the order-entry account a full factory manager.
FACTORY_MANAGER_ROLES = (
	"Order Entry",
	"Production Manager",
	"Accounts Management",
	"Cutting Operator",
	"Edge Operator",
)

# Keep only Almdina ERP module visible; block everything else for operators.
ALLOWED_MODULES_FOR_SHOP_FLOOR = ("Almdina ERP",)

# Customer selection still depends on ERPNext Selling; factory screens stay
# inside the Almdina application.
ALLOWED_MODULES_FOR_ORDER_ENTRY = (
	"Almdina ERP",
	"Selling",
	"Setup",
	"Accounts",
)

# Only the Almdina desktop icons are surfaced to the factory manager.
ORDER_ENTRY_ICON_MODULES = ("Almdina ERP",)


def _is_shop_floor_only() -> bool:
	roles = set(frappe.get_roles())
	if roles.intersection(ADMIN_ROLES):
		return False
	return bool(roles.intersection(SHOP_FLOOR_ROLES))


def _user_is_shop_floor(user: str) -> bool:
	roles = set(frappe.get_roles(user))
	if roles.intersection(ADMIN_ROLES):
		return False
	return bool(roles.intersection(SHOP_FLOOR_ROLES))


def _is_order_entry_only(user: str | None = None) -> bool:
	"""Order-entry clerk: creates orders, but sees only the Almdina factory app."""
	roles = set(frappe.get_roles(user) if user else frappe.get_roles())
	if roles.intersection({"System Manager", "Administrator"}):
		return False
	return ORDER_ENTRY_ROLE in roles


def door_cutting_order_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	if not _user_is_shop_floor(user):
		return ""
	return (
		"`tabDoor Cutting Order`.name in ("
		" select distinct door_cutting_order from `tabProduction Stage`"
		f" where assigned_to = {frappe.db.escape(user)}"
		" and stage_type in ('Sharyoun','Drawing','CNC','Sanding')"
		")"
	)


def production_stage_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	if not _user_is_shop_floor(user):
		return ""
	return f"`tabProduction Stage`.assigned_to = {frappe.db.escape(user)}"


def cutting_plan_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	if not _user_is_shop_floor(user):
		return ""
	return (
		"`tabCutting Plan`.door_cutting_order in ("
		" select distinct door_cutting_order from `tabProduction Stage`"
		f" where assigned_to = {frappe.db.escape(user)}"
		" and stage_type in ('Sharyoun','Drawing','CNC','Sanding')"
		")"
	)


def apply_shop_floor_user_restrictions(user: str | None = None) -> None:
	"""Block non-factory modules and pin default workspace for a shop-floor user."""
	user = user or frappe.session.user
	if user in {"Guest", "Administrator"}:
		return
	if not _user_is_shop_floor(user):
		return

	doc = frappe.get_doc("User", user)
	all_modules = frappe.get_all("Module Def", pluck="name")
	blocked = [m for m in all_modules if m not in ALLOWED_MODULES_FOR_SHOP_FLOOR]

	changed = False
	existing = {row.module for row in (doc.block_modules or [])}
	desired = set(blocked)
	if existing != desired:
		doc.set("block_modules", [])
		for module in sorted(desired):
			doc.append("block_modules", {"module": module})
		changed = True

	if doc.default_workspace != SHOP_FLOOR_WORKSPACE and frappe.db.exists("Workspace", SHOP_FLOOR_WORKSPACE):
		doc.default_workspace = SHOP_FLOOR_WORKSPACE
		changed = True

	if changed:
		doc.flags.ignore_permissions = True
		doc.flags.ignore_password_policy = True
		doc.save(ignore_permissions=True)
		frappe.db.commit()


def apply_order_entry_user_restrictions(user: str | None = None) -> None:
	"""Grant the full factory-manager role set and keep the Desk on the Almdina app."""
	user = user or frappe.session.user
	if user in {"Guest", "Administrator"}:
		return
	if not _is_order_entry_only(user):
		return

	doc = frappe.get_doc("User", user)
	all_modules = frappe.get_all("Module Def", pluck="name")
	desired = {m for m in all_modules if m not in ALLOWED_MODULES_FOR_ORDER_ENTRY}

	changed = False
	current_roles = {row.role for row in (doc.roles or [])}
	for role in FACTORY_MANAGER_ROLES:
		if role not in current_roles and frappe.db.exists("Role", role):
			doc.append("roles", {"role": role})
			changed = True

	existing = {row.module for row in (doc.block_modules or [])}
	if existing != desired:
		doc.set("block_modules", [])
		for module in sorted(desired):
			doc.append("block_modules", {"module": module})
		changed = True

	if doc.default_workspace != ORDER_ENTRY_WORKSPACE and frappe.db.exists("Workspace", ORDER_ENTRY_WORKSPACE):
		doc.default_workspace = ORDER_ENTRY_WORKSPACE
		changed = True

	if doc.default_app != "almdina_erp":
		doc.default_app = "almdina_erp"
		changed = True

	if changed:
		doc.flags.ignore_permissions = True
		doc.flags.ignore_password_policy = True
		doc.save(ignore_permissions=True)
		frappe.db.commit()


def _boot_order_entry(bootinfo) -> None:
	"""Flag the session so the Desk keeps only the Almdina factory app visible.

	`apps_data` is assembled after extend_bootinfo runs, so the apps screen itself is
	trimmed client-side in order_entry_desk.js using this flag.
	"""
	try:
		apply_order_entry_user_restrictions(frappe.session.user)
	except Exception:
		frappe.log_error(title="almdina order entry user restrictions")

	bootinfo["almdina_order_entry_only"] = 1
	bootinfo["almdina_allowed_apps"] = ["almdina_erp"]

	module_map = bootinfo.get("module_wise_workspaces")
	if isinstance(module_map, dict):
		bootinfo["module_wise_workspaces"] = {
			k: v for k, v in module_map.items() if k in ORDER_ENTRY_ICON_MODULES
		}

	# Required framework modules stay available while only Almdina workspaces are
	# listed in the sidebar.
	allowed_workspaces = set()
	workspaces = bootinfo.get("workspaces")
	if isinstance(workspaces, dict):
		pages = workspaces.get("pages")
		if isinstance(pages, list):
			kept = [
				p
				for p in pages
				if not isinstance(p, dict)
				or p.get("module") in ORDER_ENTRY_ICON_MODULES
				or p.get("app") == "almdina_erp"
				or p.get("for_user") == frappe.session.user
			]
			if kept:
				workspaces["pages"] = kept
				pages = kept
		for page in pages or []:
			if isinstance(page, dict):
				allowed_workspaces.add(page.get("name"))
				allowed_workspaces.add(page.get("title"))

	icons = bootinfo.get("desktop_icons")
	if isinstance(icons, list) and allowed_workspaces:
		bootinfo["desktop_icons"] = [
			i
			for i in icons
			if isinstance(i, dict)
			and (i.get("module_name") in allowed_workspaces or i.get("label") in allowed_workspaces)
		]


def boot_session(bootinfo) -> None:
	"""Limit Desk navigation for pure shop-floor operators."""
	if _is_order_entry_only():
		_boot_order_entry(bootinfo)
		return

	if not _is_shop_floor_only():
		return

	# Ensure module blocks exist (idempotent).
	try:
		apply_shop_floor_user_restrictions(frappe.session.user)
	except Exception:
		frappe.log_error(title="almdina shop floor user restrictions")

	bootinfo["almdina_shop_floor_only"] = 1
	bootinfo["almdina_shop_floor_home"] = SHOP_FLOOR_PAGE
	bootinfo["almdina_allowed_pages"] = [SHOP_FLOOR_PAGE]
	bootinfo["default_route"] = f"/app/{SHOP_FLOOR_PAGE}"
	bootinfo["home_page"] = SHOP_FLOOR_PAGE

	# Keep only Shop Floor workspace pages.
	workspaces = bootinfo.get("workspaces")
	if isinstance(workspaces, dict) and workspaces.get("pages"):
		pages = [
			p
			for p in workspaces["pages"]
			if (p.get("name") if isinstance(p, dict) else p) == SHOP_FLOOR_WORKSPACE
		]
		if not pages:
			# Fallback: keep any page titled Shop Floor / صالة الإنتاج
			pages = [
				p
				for p in workspaces["pages"]
				if isinstance(p, dict)
				and str(p.get("title") or p.get("label") or "") in {SHOP_FLOOR_WORKSPACE, "صالة الإنتاج"}
			]
		workspaces["pages"] = pages
		bootinfo["workspaces"] = workspaces
		bootinfo["allowed_workspaces"] = pages

	# Empty workspace sidebar for operators — navigation is the custom bottom tabs.
	bootinfo["workspace_sidebar_item"] = {}
	bootinfo["sidebar_pages"] = []
	bootinfo["allowed_pages"] = [SHOP_FLOOR_PAGE]

	# App switcher / desktop apps: Almdina only
	app_data = bootinfo.get("app_data")
	if isinstance(app_data, list):
		trimmed = []
		for app in app_data:
			if not isinstance(app, dict):
				continue
			name = app.get("app_name") or app.get("name")
			if name != "almdina_erp":
				continue
			app = dict(app)
			app["workspaces"] = [SHOP_FLOOR_WORKSPACE]
			app["app_route"] = f"/app/{SHOP_FLOOR_PAGE}"
			app["modules"] = list(ALLOWED_MODULES_FOR_SHOP_FLOOR)
			trimmed.append(app)
		bootinfo["app_data"] = trimmed

	# No desktop icons for operators
	bootinfo["desktop_icons"] = []

	module_map = bootinfo.get("module_wise_workspaces")
	if isinstance(module_map, dict):
		bootinfo["module_wise_workspaces"] = {
			k: [w for w in (v or []) if w == SHOP_FLOOR_WORKSPACE]
			for k, v in module_map.items()
			if k in ALLOWED_MODULES_FOR_SHOP_FLOOR
		}


def extend_bootinfo(bootinfo=None) -> None:
	"""Second-pass filter after sessions.get() adds apps_data."""
	if not bootinfo:
		return

	if bootinfo.get("almdina_order_entry_only") or _is_order_entry_only():
		bootinfo["almdina_order_entry_only"] = 1
		bootinfo["almdina_allowed_apps"] = ["almdina_erp"]
		return

	if not bootinfo.get("almdina_shop_floor_only"):
		if not _is_shop_floor_only():
			return
		bootinfo["almdina_shop_floor_only"] = 1

	apps_data = bootinfo.get("apps_data")
	if isinstance(apps_data, dict):
		apps = apps_data.get("apps") or []
		apps_data["apps"] = [
			a
			for a in apps
			if (a.get("name") if isinstance(a, dict) else a) == "almdina_erp"
		]
		apps_data["default_path"] = f"/app/{SHOP_FLOOR_PAGE}"
		bootinfo["apps_data"] = apps_data

	# Strip leftover sidebar / workspace payloads again after session assembly.
	bootinfo["workspace_sidebar_item"] = {}
	bootinfo["desktop_icons"] = []
	bootinfo["home_page"] = SHOP_FLOOR_PAGE
	bootinfo["default_route"] = f"/app/{SHOP_FLOOR_PAGE}"
