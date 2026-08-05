from __future__ import annotations

import frappe


EDGE_BANDING_TYPES = (
    {"name":"قشاط 2سم عادي","english":"2cm Regular Edge","width":2,"finish":"Regular","method":"Machine","rate":0.5},
    {"name":"قشاط 4سم عادي","english":"4cm Regular Edge","width":4,"finish":"Regular","method":"Machine","rate":1.0},
    {"name":"قشاط 2سم لميع","english":"2cm Glossy Edge","width":2,"finish":"Glossy","method":"Machine","rate":1.0},
    {"name":"قشاط 4سم لميع","english":"4cm Glossy Edge","width":4,"finish":"Glossy","method":"Machine","rate":2.0},
    {"name":"قشاط 2سم عادي يدوي","english":"2cm Regular Manual Edge","width":2,"finish":"Regular","method":"Manual","rate":1.0},
    {"name":"قشاط 4سم عادي يدوي","english":"4cm Regular Manual Edge","width":4,"finish":"Regular","method":"Manual","rate":2.0},
    {"name":"قشاط 2سم ذهبي","english":"2cm Golden Edge","width":2,"finish":"Golden","method":"Machine","rate":1.25},
    {"name":"قشاط 4سم ذهبي","english":"4cm Golden Edge","width":4,"finish":"Golden","method":"Machine","rate":2.5},
    {"name":"قشاط 2سم ذهبي يدوي","english":"2cm Golden Manual Edge","width":2,"finish":"Golden","method":"Manual","rate":2.5},
    {"name":"قشاط 4سم ذهبي يدوي","english":"4cm Golden Manual Edge","width":4,"finish":"Golden","method":"Manual","rate":5.0},
    {"name":"قشاط 2سم لميع يدوي","english":"2cm Glossy Manual Edge","width":2,"finish":"Glossy","method":"Manual","rate":2.0},
    {"name":"قشاط 4سم لميع يدوي","english":"4cm Glossy Manual Edge","width":4,"finish":"Glossy","method":"Manual","rate":4.0},
)

ROLES = (
    "Order Entry",
    "Cutting Operator",
    "Edge Operator",
    "Production Manager",
    "Accounts Management",
    "عامل رسم",
    "عامل شريون",
    "عامل CNC",
    "عامل تقشيط",
)

# Convenience records used only by explicit administrative seed commands.
OPERATOR_USERS = (
    {"email": "drawing@almdina.local", "first_name": "عامل", "last_name": "رسم", "profile": "drawing_operator"},
    {"email": "sharyoun@almdina.local", "first_name": "عامل", "last_name": "شريون", "profile": "sharyoun_operator"},
    {"email": "cnc@almdina.local", "first_name": "عامل", "last_name": "CNC", "profile": "cnc_operator"},
    {"email": "taqsheet@almdina.local", "first_name": "عامل", "last_name": "تقشيط", "profile": "sanding_operator"},
)

ORDER_ENTRY_USERS = (
    {
        "email": "orders@almdina.local",
        "first_name": "موظف",
        "last_name": "الطلبات",
        "profile": "order_entry",
    },
)

DEFAULT_ROUTING_NAME = "MDF Cutting Baseline v1"


def sync_setup() -> None:
    seed_roles()
    seed_edge_banding_types()
    seed_default_routing()
    seed_settings_defaults()
    sync_plan_recalculation_state()
    sync_dual_plan_json_backfill()
    sync_order_board_descriptions()
    sync_plan_board_descriptions()
    sync_replacement_board_descriptions()


def after_install() -> None:
    sync_setup()


def after_migrate() -> None:
    sync_setup()


def seed_roles() -> None:
    for role_name in ROLES:
        if not frappe.db.exists("Role", role_name):
            frappe.get_doc({"doctype":"Role","role_name":role_name}).insert(ignore_permissions=True)


def sync_replacement_board_descriptions() -> None:
    """Backfill only missing free-text identity on historical replacements."""

    if not frappe.db.exists("DocType", "Replacement Piece"):
        return
    frappe.db.sql(
        """
        update `tabReplacement Piece` replacement
        inner join `tabDoor Cutting Order` order_doc
            on order_doc.name = replacement.door_cutting_order
        set replacement.board_description = order_doc.board_description
        where coalesce(replacement.board_description, '') = ''
          and coalesce(order_doc.board_description, '') != ''
        """
    )


def sync_order_board_descriptions() -> None:
    """Backfill free-text identity and dimensions on historical orders."""

    if not frappe.db.exists("DocType", "Door Cutting Order"):
        return
    frappe.db.sql(
        """
        update `tabDoor Cutting Order`
        set board_description = board_item
        where coalesce(board_description, '') = ''
          and coalesce(board_item, '') != ''
        """
    )
    frappe.db.sql(
        """
        update `tabDoor Cutting Order`
        set
            board_length_cm = case
                when coalesce(board_length_cm, 0) <= 0
                    then coalesce(nullif(full_board_length_mm, 0), 2440) / 10
                else board_length_cm
            end,
            board_width_cm = case
                when coalesce(board_width_cm, 0) <= 0
                    then coalesce(nullif(full_board_width_mm, 0), 1220) / 10
                else board_width_cm
            end
        """
    )


def sync_plan_board_descriptions() -> None:
    """Backfill free-text board identity on historical plan snapshots."""

    if not frappe.db.exists("DocType", "Cutting Plan"):
        return
    frappe.db.sql(
        """
        update `tabCutting Plan` plan
        inner join `tabDoor Cutting Order` order_doc
            on order_doc.name = plan.door_cutting_order
        set plan.board_description = order_doc.board_description
        where coalesce(plan.board_description, '') = ''
          and coalesce(order_doc.board_description, '') != ''
        """
    )
    frappe.db.sql(
        """
        update `tabCutting Plan Source` source
        inner join `tabCutting Plan` plan
            on plan.name = source.parent
           and source.parenttype = 'Cutting Plan'
        set source.board_description = plan.board_description
        where coalesce(source.board_description, '') = ''
          and coalesce(plan.board_description, '') != ''
        """
    )


def _require_explicit_password(password: str | None) -> str:
    password = str(password or "")
    if not password:
        frappe.throw(
            "Pass password explicitly. Almdina ERP does not store a default user password in source code."
        )
    return password


def _seed_users(rows: tuple[dict, ...], password: str | None) -> list[str]:
    from almdina_erp.almdina_erp.application.security.provision_user import provision_user

    seed_roles()
    password = _require_explicit_password(password)
    results: list[str] = []
    for row in rows:
        result = provision_user(
            email=row["email"],
            profile=row["profile"],
            first_name=row["first_name"],
            last_name=row.get("last_name", ""),
            temporary_password=password,
        )
        action = "created" if result["created"] else "updated"
        results.append(f"{action}:{row['email']}")
    frappe.db.commit()
    return results


def seed_operator_users(password: str | None = None) -> list[str]:
    """Explicitly create the four shop-floor users with a runtime password."""

    return _seed_users(OPERATOR_USERS, password)


def seed_order_entry_users(password: str | None = None) -> list[str]:
    """Explicitly create the order-entry user with a runtime password."""

    return _seed_users(ORDER_ENTRY_USERS, password)


def seed_edge_banding_types() -> None:
    for row in EDGE_BANDING_TYPES:
        if frappe.db.exists("Edge Banding Type", row["name"]):
            doc = frappe.get_doc("Edge Banding Type", row["name"])
        else:
            doc = frappe.new_doc("Edge Banding Type")
            doc.edge_type_name = row["name"]
        doc.english_name = row["english"]
        doc.width_cm = row["width"]
        doc.finish_type = row["finish"]
        doc.application_method = row["method"]
        doc.rate_usd_per_meter = row["rate"]
        doc.disabled = 0
        doc.save(ignore_permissions=True)


def seed_default_routing() -> None:
    if frappe.db.exists("Production Routing", DEFAULT_ROUTING_NAME):
        return
    routing = frappe.new_doc("Production Routing")
    routing.routing_name = DEFAULT_ROUTING_NAME
    routing.disabled = 0
    routing.append("stages", {"sequence":10,"stage_type":"Review / Preparation","department_label":"مراجعة وتجهيز","operational_role":"Production Manager","required":1,"auto_complete_if_not_applicable":1})
    routing.append("stages", {"sequence":20,"stage_type":"Cutting","department_label":"قص","operational_role":"Cutting Operator","required":1,"auto_complete_if_not_applicable":0})
    routing.append("stages", {"sequence":30,"stage_type":"Edge Banding","department_label":"قشاط","operational_role":"Edge Operator","required":1,"auto_complete_if_not_applicable":1})
    routing.insert(ignore_permissions=True)


def seed_settings_defaults() -> None:
    settings = frappe.get_single("Almdina ERP Settings")
    changed = False
    defaults = {
        "default_kerf_mm": 3,
        "default_trim_margin_mm": 5,
        "default_cutting_cost_per_board_usd": 1,
        "default_packing_mode": "Auto Pro",
        "default_cutting_machine_type": "Auto",
        "default_optimization_time_limit_sec": 10,
        "optimal_search_piece_limit": 40,
        "default_production_routing": DEFAULT_ROUTING_NAME,
        "min_remnant_width_mm": 300,
        "min_remnant_length_mm": 300,
        "min_remnant_area_m2": 0.09,
    }
    for fieldname, value in defaults.items():
        if settings.get(fieldname) in (None, ""):
            settings.set(fieldname, value)
            changed = True
    # Inventory, reservations, consumption and remnant reuse are intentionally
    # outside the current product. Force old sites onto the same safe boundary
    # while leaving their historical database rows untouched.
    for fieldname, value in {
        "enforce_stock_control": 0,
        "default_warehouse": None,
        "reserve_stock_on_approval": 0,
        "prefer_remnants_before_full_boards": 0,
    }.items():
        if settings.meta.has_field(fieldname) and settings.get(fieldname) != value:
            settings.set(fieldname, value)
            changed = True
    if changed:
        settings.save(ignore_permissions=True)


def sync_plan_recalculation_state() -> None:
    """Keep existing valid plans usable after adding the fast-save freshness flag."""
    try:
        if not frappe.db.table_exists("Door Cutting Order"):
            return
        if not frappe.db.has_column("Door Cutting Order", "plan_needs_recalculation"):
            return
        frappe.db.sql(
            """
            update `tabDoor Cutting Order`
               set plan_needs_recalculation = case
                    when coalesce(cutting_plan_json, '') <> '' then 0
                    else 1
               end
            """
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Almdina plan freshness backfill")


def sync_dual_plan_json_backfill() -> None:
    """Copy existing cutting plans into system_plan_json after the dual-plan fields land."""
    try:
        if not frappe.db.table_exists("Door Cutting Order"):
            return
        if not frappe.db.has_column("Door Cutting Order", "system_plan_json"):
            return
        frappe.db.sql(
            """
            update `tabDoor Cutting Order`
               set system_plan_json = cutting_plan_json
             where coalesce(system_plan_json, '') = ''
               and coalesce(cutting_plan_json, '') <> ''
            """
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Almdina dual-plan JSON backfill")
