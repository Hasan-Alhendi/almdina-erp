from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.application.security.navigation_context import build_navigation_context
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    CUSTOMER_BOT_PHONE_ACCESS_DOCTYPE,
    CUSTOMER_BOT_PHONE_REQUEST_DOCTYPE,
    CUSTOMER_BOT_SETTINGS_DOCTYPE,
    CUTTING_PLAN_DOCTYPE,
    FACTORY_SETTINGS_CAPABILITIES,
    WORKFORCE_CAPABILITIES,
    Capability,
    normalize_capabilities,
)


CATEGORY_ORDER = (
    "order",
    "costing",
    "documents",
    "cutting_plan",
    "drawing",
    "production",
    "shop_floor",
    "control_center",
    "workforce",
    "factory_settings",
    "customer_bot",
    "master_data",
    "administration",
)

CATEGORY_PRESENTATION: dict[str, dict[str, str]] = {
    "order": {"label": "Orders", "description": "Create, review, approve, and manage the lifecycle of an order.", "icon": "file-text"},
    "costing": {"label": "Costing and pricing", "description": "View costs, edit cost settings, and approve internal prices.", "icon": "accounting"},
    "documents": {"label": "Documents and printing", "description": "Print measurements, the customer invoice, and the confidential internal report.", "icon": "printer"},
    "cutting_plan": {"label": "Cutting plan", "description": "View the plan tabs (system / uploaded / approved), calculate plans, edit optimizer settings, approve plans, and print them.", "icon": "organization"},
    "drawing": {"label": "Drawing and DXF", "description": "Special drawing, plus exporting, uploading, and replacing DXF files.", "icon": "image-view"},
    "production": {"label": "Production and assignment", "description": "Dispatch orders, start stages, hand them off, revert them, and reassign them.", "icon": "tool"},
    "shop_floor": {"label": "Production floor", "description": "Additional view permissions within the Production floor, without granting access or any production actions by themselves.", "icon": "list"},
    "control_center": {"label": "Control center and quality", "description": "Archive plans, view and record production incidents, and manage replacement pieces.", "icon": "dashboard"},
    "workforce": {"label": "Users and workforce", "description": "View, create, edit, and enable factory accounts, and manage their roles.", "icon": "users"},
    "factory_settings": {"label": "Factory settings", "description": "View and edit cutting, costing, production, printing, WhatsApp, and backup settings, each section independently.", "icon": "setting-gear"},
    "customer_bot": {"label": "Customer bot", "description": "Inbound webhook ingestion for the customer bot, plus the retired additional-phone grants that no longer open follow-up.", "icon": "comment"},
    "master_data": {"label": "Master data", "description": "Manage production routings and edge banding types, with separate view, create, edit, and delete permissions.", "icon": "database"},
    "administration": {"label": "Permission management", "description": "Edit the permission matrix for all roles.", "icon": "lock"},
}


def _presentation(label: str, description: str, risk: str = "normal") -> dict[str, str]:
    return {"label": label, "description": description, "risk": risk}


CAPABILITY_PRESENTATION: dict[str, dict[str, str]] = {
    Capability.VIEW_ORDERS: _presentation("View orders", "View the orders you are allowed to see and open their basic details."),
    Capability.VIEW_ALL_ORDERS: _presentation("View all orders", "Bypass the assignment scope and view the orders of all workers. Grant to authorized management only.", "critical"),
    Capability.CREATE_ORDER: _presentation("Create order", "Create new cutting orders."),
    Capability.EDIT_ORDER: _presentation("Edit order", "Enable edit mode on an order only while it is a draft. After dispatch to production, use return to draft or an edit revision.", "sensitive"),
    Capability.CREATE_ORDER_REVISION: _presentation("Create edit revision", "Create a new revision while leaving the historical order unchanged.", "sensitive"),
    Capability.SUBMIT_ORDER: _presentation("Submit for review (retired)", "Retired. The order is dispatched directly to production without going through review."),
    Capability.APPROVE_ORDER: _presentation("Approve order (retired)", "Retired. Use 'Dispatch to production' directly. Cutting plan approval remains a separate permission.", "critical"),
    Capability.REJECT_ORDER: _presentation("Reject order", "Reject an order stuck in the legacy review queue and send it back for editing.", "critical"),
    Capability.CANCEL_ORDER: _presentation("Cancel order", "Cancel the order according to lifecycle rules.", "critical"),
    Capability.RESUME_CANCELLED_ORDER: _presentation(
        "Resume cancelled order",
        "Return a cancelled order to the production stage it was cancelled from, without resetting the routing or returning it to draft.",
        "critical",
    ),
    Capability.ADD_INTERNAL_NOTE: _presentation(
        "Add internal note",
        "Add collaborative notes on the order and its linked customer without editing the order or entering the save and revision cycle.",
    ),
    Capability.MANAGE_IMPORTANT_NOTE: _presentation(
        "Set important note",
        "Select or clear the order's current important note; it appears directly in the order list and on the mobile card.",
        "sensitive",
    ),
    Capability.VIEW_COSTS: _presentation("View costs", "View protected cost, price, and profitability data.", "sensitive"),
    Capability.EDIT_COST_SETTINGS: _presentation("Edit cost settings", "Edit the board price and cutting fee, and recalculate the cost.", "critical"),
    Capability.EDIT_SPECIAL_PRICE: _presentation("Edit approved price", "Change the price of a special door leaf after it was previously approved.", "critical"),
    Capability.APPROVE_SPECIAL_PRICE: _presentation("Approve special price", "Approve the final price of special door leaves.", "critical"),
    Capability.APPROVE_FINAL_PRICE: _presentation(
        "Approve final price",
        "Approve the final order price, record the approval data, and lock cost settings.",
        "critical",
    ),
    Capability.CANCEL_FINAL_PRICE_APPROVAL: _presentation(
        "Cancel final price approval",
        "Cancel the order's final price approval while keeping the approval record and its details.",
        "critical",
    ),
    Capability.PRINT_MEASUREMENTS: _presentation("Print measurements", "Print the measurements document without any prices."),
    Capability.PRINT_CUSTOMER_INVOICE: _presentation("Print customer invoice", "Print the customer's financial document without internal data.", "sensitive"),
    Capability.PRINT_INTERNAL_COST_REPORT: _presentation("Print internal cost report", "Print the confidential report that includes operating cost and profitability.", "critical"),
    Capability.VIEW_CUTTING_PLAN: _presentation("View cutting plan section", "Show the cutting results tab. Grant the tab permissions below to control which plans can be viewed."),
    Capability.VIEW_SYSTEM_CUTTING_PLAN: _presentation("View system plan", "View the tab for the cutting plan calculated by the system."),
    Capability.VIEW_UPLOADED_CUTTING_PLAN: _presentation("View uploaded plan", "View the tab for the uploaded cutting plan (DXF / custom)."),
    Capability.VIEW_APPROVED_CUTTING_PLAN: _presentation("View approved plan", "View the tab for the plan approved for production."),
    Capability.RECALCULATE_PLAN: _presentation("Recalculate plan", "Rerun the engine that distributes pieces across boards.", "sensitive"),
    Capability.EDIT_OPTIMIZER_SETTINGS: _presentation(
        "Edit cutting algorithm",
        "Change the cutting algorithm offered by the system, the margins, kerf, and search settings, then recalculate and view the result in 'System plan'. This permission is fully independent of 'Edit order': whoever can edit an order cannot change the algorithm without it.",
        "sensitive",
    ),
    Capability.PRINT_CUTTING_PLAN: _presentation("Print cutting plan", "Print the plan you are authorized to view."),
    Capability.SET_OFFCUT_EXECUTION_OWNER: _presentation(
        "Set source and execution of shortage pieces",
        "Allows setting whether the shortage offcut comes from the factory or from the customer, and whether it is executed at the factory or at the customer's site, within permitted cases only.",
        "sensitive",
    ),
    Capability.APPROVE_DXF: _presentation("Approve cutting plan", "Approve the current system plan or the uploaded DXF plan as the final source for production after reviewing it.", "critical"),
    Capability.VIEW_DRAWING_WORKSPACE: _presentation("Open drawing workspace", "Show the special drawing tools and the DXF plan."),
    Capability.EDIT_SPECIAL_DRAWING: _presentation("Edit special drawing", "Edit the geometry and notes of special door leaves.", "sensitive"),
    Capability.EXPORT_DXF: _presentation("Export DXF", "Export the production drawing in DXF format.", "sensitive"),
    Capability.UPLOAD_DXF: _presentation("Upload DXF cutting plan", "Upload a cutting plan as a DXF file, with validation before it is approved. Intended for the drawing worker.", "sensitive"),
    Capability.REPLACE_DXF: _presentation("Replace DXF cutting plan", "Replace the previously uploaded DXF file after validation. Intended for the drawing worker.", "critical"),
    Capability.DISPATCH_ORDER: _presentation("Dispatch order to production", "Choose the production routing and the first worker, and create the stages."),
    Capability.START_ASSIGNED_STAGE: _presentation("Start assigned stage", "Start the current stage when it is assigned to the same user."),
    Capability.HANDOFF_ASSIGNED_STAGE: _presentation("Hand off assigned stage", "Finish the stage and send the order to the next worker."),
    Capability.REVERT_DEPARTMENT: _presentation("Revert order to a previous department", "Return the order to a previous stage or department with an audit trail.", "critical"),
    Capability.RETURN_ORDER_TO_DRAFT: _presentation("Return order to draft", "Return the same order to draft after cancelling the active production stages, without creating a new revision.", "critical"),
    Capability.MARK_DELIVERED: _presentation("Confirm delivery", "Change the order status to Delivered.", "critical"),
    Capability.REASSIGN_WORKER: _presentation("Change worker", "Reassign the current stage to another qualified worker.", "sensitive"),
    Capability.VIEW_SHOP_FLOOR_HISTORY: _presentation(
        "View completed orders history",
        "View completed orders that already fall within the user's scope. Does not grant access to the Production floor, nor any action or additional order scope.",
    ),
    Capability.ARCHIVE_APPROVED_PLAN: _presentation("Archive approved plan", "Generate and save an official PDF of the approved plan.", "sensitive"),
    Capability.VIEW_USERS: _presentation("View factory users", "View Almdina accounts only, along with their status and assigned roles."),
    Capability.CREATE_USERS: _presentation("Create user", "Create a new system account for the factory with a temporary password.", "critical"),
    Capability.EDIT_USERS: _presentation("Edit user details", "Edit the name, language, and non-financial account details.", "sensitive"),
    Capability.ASSIGN_USER_ROLES: _presentation("Assign roles to user", "Add or remove system roles on an Almdina user account.", "critical"),
    Capability.ENABLE_USERS: _presentation("Enable user", "Re-enable a disabled factory account.", "critical"),
    Capability.DISABLE_USERS: _presentation("Disable user", "Disable an account after confirming there are no active production stages.", "critical"),
    Capability.RESET_USER_PASSWORD: _presentation("Reset password", "Set a new temporary password without displaying it or storing it in the log.", "critical"),
    Capability.VIEW_FACTORY_SETTINGS: _presentation("View factory settings", "View cutting settings, costing, production controls, print sheet identity, and WhatsApp messages, without editing or linking a session."),
    Capability.EDIT_FACTORY_CUTTING_DEFAULTS: _presentation("Edit cutting defaults", "Edit kerf, margin, algorithm, machine type, and search limits.", "sensitive"),
    Capability.EDIT_FACTORY_COST_DEFAULTS: _presentation("Edit cost defaults", "Edit the cutting fee, special door leaf charges, and their margins.", "critical"),
    Capability.EDIT_FACTORY_PRODUCTION_CONTROLS: _presentation("Edit production controls", "Edit the default routing and sensitive operational exceptions.", "critical"),
    Capability.EDIT_FACTORY_PRINT_IDENTITY: _presentation("Edit print identity", "Edit the factory name, tagline, address, and contact numbers shown on printed sheets. Does not include WhatsApp messages or session linking.", "sensitive"),
    Capability.MANAGE_WHATSAPP_SESSION: _presentation("Manage WhatsApp session", "View the factory session status, create it, link it via QR code, and reconnect. Does not grant message editing or sending customer files.", "critical"),
    Capability.EDIT_WHATSAPP_MESSAGES: _presentation("Edit WhatsApp messages", "Edit the texts for measurements, measurement changes, the invoice, and stage completion in the factory settings. Does not grant session creation or file sending.", "sensitive"),
    Capability.MANAGE_CUSTOMER_BOT_ACCESS: _presentation(
        "Manage customer bot access (retired)",
        "Retired. Additional phone linking is no longer part of the customer bot. Holding this grant does not open the historical records or authorize a decision.",
        "critical",
    ),
    Capability.MANAGE_CUSTOMER_BOT_SETTINGS: _presentation(
        "Manage customer bot settings",
        "Edit the customer bot texts, preview them with sample data, publish them, and turn the bot on or off. Does not connect WhatsApp, send messages, or open customers and orders.",
        "sensitive",
    ),
    Capability.INGEST_CUSTOMER_BOT_INBOUND: _presentation(
        "Ingest customer bot inbound events",
        "Accept authenticated OpenWA webhook deliveries for the configured customer-bot connection. Does not edit bot texts, manage the factory WhatsApp session, or send replies.",
        "critical",
    ),
    Capability.MANAGE_BACKUPS: _presentation("Manage backups", "Configure scheduling, retention, and the SSH connection, create manual backups, and view their log. Does not grant restore.", "critical"),
    Capability.RESTORE_BACKUPS: _presentation("Restore backups", "Start a destructive restore after explicit confirmation and an automatic safety backup. Does not grant editing backup settings.", "critical"),
    Capability.VIEW_PRODUCTION_ROUTINGS: _presentation("View production routings", "View production routings and their stage sequence."),
    Capability.CREATE_PRODUCTION_ROUTINGS: _presentation("Create production routing", "Create a new production routing.", "sensitive"),
    Capability.EDIT_PRODUCTION_ROUTINGS: _presentation("Edit production routings", "Edit the stage order or disable the routing.", "critical"),
    Capability.DELETE_PRODUCTION_ROUTINGS: _presentation("Delete production routing", "Delete a routing that is unused and not set as the default.", "critical"),
    Capability.VIEW_EDGE_BANDING_TYPES: _presentation("View edge banding types", "View edge banding types with their thickness, price, and status."),
    Capability.CREATE_EDGE_BANDING_TYPES: _presentation("Create edge banding type", "Add a new edge banding type.", "sensitive"),
    Capability.EDIT_EDGE_BANDING_TYPES: _presentation("Edit edge banding types", "Edit the thickness, price, and properties, or disable the type.", "critical"),
    Capability.DELETE_EDGE_BANDING_TYPES: _presentation("Delete edge banding type", "Delete a type that is not used in any order or piece.", "critical"),
    Capability.VIEW_CUSTOMERS: _presentation("View customers", "View the customer list and manage it from the master data workspace, and select the customer on orders."),
    Capability.CREATE_CUSTOMERS: _presentation("Create customer", "Add a new customer from the customer list or from the selection field on the order.", "sensitive"),
    Capability.EDIT_CUSTOMERS: _presentation("Edit customers", "Edit the existing customer details.", "sensitive"),
    Capability.DELETE_CUSTOMERS: _presentation("Delete customer", "Delete a customer who is not linked to any saved orders.", "critical"),
    Capability.MANAGE_PERMISSIONS: _presentation("Permission management", "Edit the permission matrix for all roles.", "critical"),
}

_COST_VIEW_ACTIONS = frozenset({
    Capability.EDIT_COST_SETTINGS,
    Capability.EDIT_SPECIAL_PRICE,
    Capability.APPROVE_SPECIAL_PRICE,
    Capability.APPROVE_FINAL_PRICE,
    Capability.CANCEL_FINAL_PRICE_APPROVAL,
    Capability.PRINT_INTERNAL_COST_REPORT,
})
_PLAN_VIEW_ACTIONS = frozenset({
    Capability.RECALCULATE_PLAN,
    Capability.EDIT_OPTIMIZER_SETTINGS,
    Capability.PRINT_CUTTING_PLAN,
    Capability.APPROVE_DXF,
})
_PLAN_TAB_VIEW_ACTIONS = frozenset({
    Capability.VIEW_SYSTEM_CUTTING_PLAN,
    Capability.VIEW_UPLOADED_CUTTING_PLAN,
    Capability.VIEW_APPROVED_CUTTING_PLAN,
})
_DRAWING_VIEW_ACTIONS = frozenset({
    Capability.EDIT_SPECIAL_DRAWING,
    Capability.EXPORT_DXF,
    Capability.UPLOAD_DXF,
    Capability.REPLACE_DXF,
})
_WORKFORCE_ACTIONS = frozenset(WORKFORCE_CAPABILITIES.difference({Capability.VIEW_USERS}))
_FACTORY_SECTION_EDITS = frozenset(FACTORY_SETTINGS_CAPABILITIES.difference({Capability.VIEW_FACTORY_SETTINGS}))
_ROUTING_ACTIONS = frozenset({
    Capability.CREATE_PRODUCTION_ROUTINGS,
    Capability.EDIT_PRODUCTION_ROUTINGS,
    Capability.DELETE_PRODUCTION_ROUTINGS,
})
_EDGE_ACTIONS = frozenset({
    Capability.CREATE_EDGE_BANDING_TYPES,
    Capability.EDIT_EDGE_BANDING_TYPES,
    Capability.DELETE_EDGE_BANDING_TYPES,
})
_CUSTOMER_ACTIONS = frozenset({
    Capability.CREATE_CUSTOMERS,
    Capability.EDIT_CUSTOMERS,
    Capability.DELETE_CUSTOMERS,
})
_ORDER_INPUT_ACTIONS = frozenset({
    Capability.CREATE_ORDER,
    Capability.EDIT_ORDER,
    Capability.CREATE_ORDER_REVISION,
})


def normalize_capability_state(raw: Mapping[str, Any] | None) -> dict[str, bool]:
    """Normalize a role matrix and enforce cross-capability dependencies."""

    supplied = {str(key): value for key, value in dict(raw or {}).items()}
    unknown = set(supplied).difference(ALL_CAPABILITIES)
    if unknown:
        raise ValueError(f"Unknown capabilities: {', '.join(sorted(unknown))}")

    state = {
        capability: supplied.get(capability) is True
        for capability in sorted(ALL_CAPABILITIES)
    }
    if state[Capability.EDIT_OPTIMIZER_SETTINGS]:
        state[Capability.RECALCULATE_PLAN] = True
    if state[Capability.RECALCULATE_PLAN]:
        state[Capability.VIEW_SYSTEM_CUTTING_PLAN] = True

    # History is read-only Shop Floor visibility. It is deliberately excluded
    # from transactional dependencies so granting it alone cannot promote
    # VIEW_ORDERS or widen native Door Cutting Order scope.
    transactional_actions = {
        capability
        for capability, enabled in state.items()
        if enabled
        and CAPABILITY_CATALOG[capability].applies_to in {"Door Cutting Order", CUTTING_PLAN_DOCTYPE}
        and capability not in {
            Capability.VIEW_ORDERS,
            Capability.VIEW_SHOP_FLOOR_HISTORY,
        }
    }
    if transactional_actions:
        state[Capability.VIEW_ORDERS] = True
    if any(state[capability] for capability in _COST_VIEW_ACTIONS):
        state[Capability.VIEW_COSTS] = True
    if any(state[capability] for capability in _PLAN_VIEW_ACTIONS):
        state[Capability.VIEW_CUTTING_PLAN] = True
    if any(state[capability] for capability in _PLAN_TAB_VIEW_ACTIONS):
        state[Capability.VIEW_CUTTING_PLAN] = True
    if any(state[capability] for capability in _DRAWING_VIEW_ACTIONS):
        state[Capability.VIEW_DRAWING_WORKSPACE] = True
    if state[Capability.ARCHIVE_APPROVED_PLAN]:
        state[Capability.VIEW_CUTTING_PLAN] = True
        state[Capability.VIEW_APPROVED_CUTTING_PLAN] = True
        state[Capability.PRINT_CUTTING_PLAN] = True
    if state[Capability.VIEW_CUTTING_PLAN]:
        granular_supplied = any(key in supplied for key in _PLAN_TAB_VIEW_ACTIONS)
        if not granular_supplied:
            for capability in _PLAN_TAB_VIEW_ACTIONS:
                state[capability] = True
        elif not any(state[capability] for capability in _PLAN_TAB_VIEW_ACTIONS):
            state[Capability.VIEW_SYSTEM_CUTTING_PLAN] = True
    if any(state[capability] for capability in _WORKFORCE_ACTIONS):
        state[Capability.VIEW_USERS] = True
    if any(state[capability] for capability in _FACTORY_SECTION_EDITS):
        state[Capability.VIEW_FACTORY_SETTINGS] = True
    if state[Capability.EDIT_FACTORY_PRODUCTION_CONTROLS]:
        state[Capability.VIEW_PRODUCTION_ROUTINGS] = True
    if any(state[capability] for capability in _ROUTING_ACTIONS):
        state[Capability.VIEW_PRODUCTION_ROUTINGS] = True
    if any(state[capability] for capability in _EDGE_ACTIONS):
        state[Capability.VIEW_EDGE_BANDING_TYPES] = True
    if any(state[capability] for capability in _CUSTOMER_ACTIONS):
        state[Capability.VIEW_CUSTOMERS] = True
    if any(state[capability] for capability in _ORDER_INPUT_ACTIONS):
        state[Capability.VIEW_CUSTOMERS] = True
        state[Capability.VIEW_EDGE_BANDING_TYPES] = True
    return state


def standard_permission_projection(
    doctype: str,
    state: Mapping[str, Any] | None,
) -> dict[str, bool]:
    """Project business grants onto standard Frappe permission columns."""

    normalized = normalize_capability_state(state)
    if doctype == "Door Cutting Order":
        can_read = normalized[Capability.VIEW_ORDERS]
        return {
            "read": can_read,
            "select": can_read,
            "create": normalized[Capability.CREATE_ORDER],
            "write": normalized[Capability.EDIT_ORDER],
            "delete": False,
        }
    if doctype == CUTTING_PLAN_DOCTYPE:
        can_read = normalized[Capability.VIEW_CUTTING_PLAN]
        return {
            "read": can_read,
            "select": can_read,
            "create": False,
            "write": False,
            "delete": False,
        }
    if doctype == "Almdina ERP Settings":
        can_read_settings = (
            normalized[Capability.VIEW_FACTORY_SETTINGS]
            or any(normalized[value] for value in _FACTORY_SECTION_EDITS)
        )
        return {"read": can_read_settings, "select": can_read_settings, "create": False, "write": False, "delete": False}
    if doctype == "Production Routing":
        can_read = normalized[Capability.VIEW_PRODUCTION_ROUTINGS]
        return {"read": can_read, "select": can_read, "create": normalized[Capability.CREATE_PRODUCTION_ROUTINGS], "write": normalized[Capability.EDIT_PRODUCTION_ROUTINGS], "delete": normalized[Capability.DELETE_PRODUCTION_ROUTINGS]}
    if doctype == "Customer":
        can_read = normalized[Capability.VIEW_CUSTOMERS]
        return {"read": can_read, "select": can_read, "create": normalized[Capability.CREATE_CUSTOMERS], "write": normalized[Capability.EDIT_CUSTOMERS], "delete": normalized[Capability.DELETE_CUSTOMERS]}
    if doctype == "Edge Banding Type":
        can_read = normalized[Capability.VIEW_EDGE_BANDING_TYPES]
        return {"read": can_read, "select": can_read, "create": normalized[Capability.CREATE_EDGE_BANDING_TYPES], "write": normalized[Capability.EDIT_EDGE_BANDING_TYPES], "delete": normalized[Capability.DELETE_EDGE_BANDING_TYPES]}
    if doctype in {
        CUSTOMER_BOT_PHONE_ACCESS_DOCTYPE,
        CUSTOMER_BOT_PHONE_REQUEST_DOCTYPE,
        CUSTOMER_BOT_SETTINGS_DOCTYPE,
    }:
        return {"read": False, "select": False, "create": False, "write": False, "delete": False}
    enabled = any(
        normalized[capability]
        for capability, definition in CAPABILITY_CATALOG.items()
        if definition.applies_to == doctype
    )
    return {"read": enabled, "select": enabled, "create": False, "write": False, "delete": False}


def field_permission_projection(
    doctype: str,
    state: Mapping[str, Any] | None,
) -> dict[int, dict[str, bool]]:
    """Project sensitive cost visibility while keeping all edits command-owned."""

    normalized = normalize_capability_state(state)
    if doctype not in {"Door Cutting Order", CUTTING_PLAN_DOCTYPE}:
        return {}
    return {
        1: {
            "read": normalized[Capability.VIEW_COSTS],
            "write": False,
        }
    }


def enabled_capabilities(state: Mapping[str, Any] | None) -> frozenset[str]:
    normalized = normalize_capability_state(state)
    return normalize_capabilities(
        capability
        for capability, enabled in normalized.items()
        if enabled
    )


def capability_catalog_payload() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        category_meta = CATEGORY_PRESENTATION[category]
        capabilities = []
        for capability, definition in CAPABILITY_CATALOG.items():
            if definition.category != category:
                continue
            presentation = CAPABILITY_PRESENTATION[capability]
            capabilities.append(
                {
                    "key": capability,
                    "label": presentation["label"],
                    "description": presentation["description"],
                    "risk": presentation["risk"],
                    "permission_type": definition.permission_type,
                    "doctype": definition.applies_to,
                    "standard": not definition.custom,
                }
            )
        groups.append(
            {
                "key": category,
                "label": category_meta["label"],
                "description": category_meta["description"],
                "icon": category_meta["icon"],
                "capabilities": capabilities,
            }
        )
    return groups


def permission_impact(state: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_capability_state(state)
    granted = enabled_capabilities(normalized)
    critical = sorted(
        capability
        for capability in granted
        if CAPABILITY_PRESENTATION[capability]["risk"] == "critical"
    )
    return {
        "enabled_count": len(granted),
        "critical_count": len(critical),
        "critical_capabilities": critical,
        "navigation": build_navigation_context(granted),
    }


def changed_capabilities(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    old = normalize_capability_state(before)
    new = normalize_capability_state(after)
    changes = []
    for capability in sorted(ALL_CAPABILITIES):
        if old[capability] == new[capability]:
            continue
        presentation = CAPABILITY_PRESENTATION[capability]
        changes.append(
            {
                "key": capability,
                "label": presentation["label"],
                "risk": presentation["risk"],
                "before": old[capability],
                "after": new[capability],
            }
        )
    return changes


__all__ = [
    "CAPABILITY_PRESENTATION",
    "CATEGORY_ORDER",
    "CATEGORY_PRESENTATION",
    "capability_catalog_payload",
    "changed_capabilities",
    "enabled_capabilities",
    "field_permission_projection",
    "normalize_capability_state",
    "permission_impact",
    "standard_permission_projection",
]
