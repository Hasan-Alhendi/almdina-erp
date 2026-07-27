from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role
from almdina_erp.almdina_erp.services.production_service import (
	_log_event,
	_required_piece_qty,
	sync_order_status,
)


SHOP_FLOOR_STAGE_TYPES = ("Sharyoun", "Drawing", "CNC", "Sanding")

PATH_SEQUENCE: dict[str, tuple[str, ...]] = {
	"Sharyoun": ("Sharyoun", "Sanding"),
	"Drawing": ("Drawing", "CNC", "Sanding"),
}

STAGE_ROLE: dict[str, str] = {
	"Sharyoun": "عامل شريون",
	"Drawing": "عامل رسم",
	"CNC": "عامل CNC",
	"Sanding": "عامل تقشيط",
}

STAGE_DEPARTMENT: dict[str, str] = {
	"Sharyoun": "شريون",
	"Drawing": "رسم",
	"CNC": "CNC",
	"Sanding": "تقشيط",
}

STAGE_ORDER_STATUS: dict[str, str] = {
	"Sharyoun": "At Sharyoun",
	"Drawing": "At Drawing",
	"CNC": "At CNC",
	"Sanding": "At Sanding",
}

DEPARTMENT_STATUS_MAP: dict[str, str] = {
	"Pending": "بحاجة للعمل",
	"In Progress": "قيد العمل",
	"Paused": "قيد العمل",
	"Completed": "مكتمل",
}

CUTTING_LIKE_STAGES = {"Sharyoun", "CNC", "Cutting"}

SHOP_FLOOR_ROLES = tuple(STAGE_ROLE.values())
DISPATCH_ROLES = ("Order Entry", "Production Manager")
ADMIN_ROLES = ("Order Entry", "Production Manager", "System Manager")


def _is_admin() -> bool:
	roles = set(frappe.get_roles())
	return bool(roles.intersection({"System Manager", "Production Manager", "Order Entry"}))


def _require_shop_floor_or_admin(*roles: str) -> None:
	require_any_role(*roles, "Production Manager", "System Manager")


def _assert_user_has_role(user: str, role: str) -> None:
	if not user:
		frappe.throw(_("Select a worker."))
	if not frappe.db.exists("User", user) or not cint(frappe.db.get_value("User", user, "enabled")):
		frappe.throw(_("User {0} is not an enabled system user.").format(user))
	user_roles = set(frappe.get_roles(user))
	if role not in user_roles and "System Manager" not in user_roles:
		frappe.throw(_("User {0} does not have role {1}.").format(user, role))


def _path_sequence(path: str) -> tuple[str, ...]:
	sequence = PATH_SEQUENCE.get(path)
	if not sequence:
		frappe.throw(_("Invalid production path: {0}").format(path))
	return sequence


def _next_stage_type(path: str, current_stage_type: str) -> str | None:
	sequence = _path_sequence(path)
	try:
		idx = sequence.index(current_stage_type)
	except ValueError:
		frappe.throw(_("Stage {0} is not part of path {1}.").format(current_stage_type, path))
	if idx + 1 >= len(sequence):
		return None
	return sequence[idx + 1]


def _sequence_for_stage(path: str, stage_type: str) -> int:
	return (_path_sequence(path).index(stage_type) + 1) * 10


def _set_order_tracking(
	order_name: str,
	*,
	path: str | None = None,
	stage: Any | None = None,
	status: str | None = None,
	department: str | None = None,
	assignee: str | None = None,
	department_status: str | None = None,
	clear_stage: bool = False,
) -> None:
	values: dict[str, Any] = {}
	if path is not None:
		values["production_path"] = path
	if status is not None:
		values["status"] = status
	if department is not None:
		values["current_department"] = department
	if assignee is not None:
		values["current_assignee"] = assignee
	if department_status is not None:
		values["department_status"] = department_status
	if clear_stage:
		values["current_production_stage"] = None
	elif stage is not None:
		values["current_production_stage"] = stage.name
		values["current_department"] = STAGE_DEPARTMENT.get(stage.stage_type, values.get("current_department"))
		values["current_assignee"] = stage.assigned_to
		values["department_status"] = DEPARTMENT_STATUS_MAP.get(stage.status, values.get("department_status"))
		values["status"] = STAGE_ORDER_STATUS.get(stage.stage_type, values.get("status"))
	if values:
		frappe.db.set_value("Door Cutting Order", order_name, values, update_modified=True)


def _create_stage(order_name: str, stage_type: str, assignee: str, sequence: int) -> Any:
	stage = frappe.new_doc("Production Stage")
	stage.door_cutting_order = order_name
	stage.sequence = sequence
	stage.stage_type = stage_type
	stage.status = "Pending"
	stage.assigned_to = assignee
	stage.insert(ignore_permissions=True)
	_log_event(
		stage,
		"Created",
		{"sequence": sequence, "assigned_to": assignee, "shop_floor": True},
	)
	return stage


def _require_stage_assignee_or_admin(stage: Any) -> None:
	roles = set(frappe.get_roles())
	if roles.intersection({"System Manager", "Production Manager"}):
		return
	expected_role = STAGE_ROLE.get(stage.stage_type)
	if expected_role:
		require_any_role(expected_role)
	if stage.assigned_to and stage.assigned_to != frappe.session.user:
		frappe.throw(_("This stage is assigned to another worker."))


def _maybe_consume_stock(order_name: str, stage_type: str, trigger: str) -> None:
	if stage_type not in CUTTING_LIKE_STAGES:
		return
	if not frappe.db.get_value("Door Cutting Order", order_name, "approved_plan"):
		return
	from almdina_erp.almdina_erp.services.stock_service import consume_planned_material_if_due

	consume_planned_material_if_due(order_name, trigger=trigger)


def _maybe_register_remnants(order_name: str, stage_type: str) -> dict[str, Any] | None:
	if stage_type not in CUTTING_LIKE_STAGES:
		return None
	if not frappe.db.get_value("Door Cutting Order", order_name, "approved_plan"):
		return None
	from almdina_erp.almdina_erp.services.remnant_service import register_plan_remnants

	return register_plan_remnants(order_name)


def get_users_for_role(role: str) -> list[dict[str, str]]:
	rows = frappe.db.sql(
		"""
		select u.name, u.full_name
		from `tabUser` u
		inner join `tabHas Role` hr on hr.parent = u.name
		where hr.role = %s
			and u.enabled = 1
			and u.user_type = 'System User'
			and u.name not in ('Guest', 'Administrator')
		order by u.full_name asc
		""",
		role,
		as_dict=True,
	)
	return [{"name": row.name, "full_name": row.full_name or row.name} for row in rows]


@frappe.whitelist()
def get_dispatch_options() -> dict[str, Any]:
	require_any_role(*DISPATCH_ROLES)
	return {
		"paths": [
			{"value": "Sharyoun", "label": _("Sharyoun (simple cutting)"), "first_role": STAGE_ROLE["Sharyoun"]},
			{"value": "Drawing", "label": _("Drawing → CNC"), "first_role": STAGE_ROLE["Drawing"]},
		],
		"workers": {
			"Sharyoun": get_users_for_role(STAGE_ROLE["Sharyoun"]),
			"Drawing": get_users_for_role(STAGE_ROLE["Drawing"]),
			"CNC": get_users_for_role(STAGE_ROLE["CNC"]),
			"Sanding": get_users_for_role(STAGE_ROLE["Sanding"]),
		},
	}


@frappe.whitelist()
def get_handoff_workers(stage_name: str) -> list[dict[str, str]]:
	stage = frappe.get_doc("Production Stage", stage_name)
	_require_stage_assignee_or_admin(stage)
	order_path = frappe.db.get_value("Door Cutting Order", stage.door_cutting_order, "production_path")
	next_type = _next_stage_type(order_path, stage.stage_type)
	if not next_type:
		return []
	return get_users_for_role(STAGE_ROLE[next_type])


def assert_order_ready_for_dispatch(order: Any) -> None:
	if order.production_path or order.current_production_stage:
		frappe.throw(_("Order {0} is already dispatched.").format(order.name))
	if order.status not in {"Draft", "Rejected", "Approved"}:
		frappe.throw(_("Only draft or rejected orders can be sent to production."))
	if not order.cutting_plan_json:
		frappe.throw(_("Calculate a cutting plan before sending the order to production."))
	if cint(order.plan_needs_recalculation):
		frappe.throw(_("Recalculate the cutting plan before sending the order to production."))
	order.ensure_special_shapes_documented()


@frappe.whitelist()
def dispatch_order(order_name: str, path: str, assignee: str) -> dict[str, Any]:
	require_any_role(*DISPATCH_ROLES)
	order = frappe.get_doc("Door Cutting Order", order_name)
	assert_order_ready_for_dispatch(order)

	sequence = _path_sequence(path)
	first_stage_type = sequence[0]
	_assert_user_has_role(assignee, STAGE_ROLE[first_stage_type])

	# Cancel any leftover non-shop-floor pending stages so dispatch owns the flow.
	legacy = frappe.get_all(
		"Production Stage",
		filters={
			"door_cutting_order": order_name,
			"status": ["in", ["Pending", "In Progress", "Paused"]],
		},
		fields=["name", "piece_label", "stage_type"],
	)
	for row in legacy:
		if row.piece_label:
			continue
		if row.stage_type in SHOP_FLOOR_STAGE_TYPES:
			continue
		frappe.db.set_value("Production Stage", row.name, "status", "Cancelled", update_modified=True)

	stage = _create_stage(order_name, first_stage_type, assignee, _sequence_for_stage(path, first_stage_type))
	_set_order_tracking(order_name, path=path, stage=stage)
	_log_event(stage, "Created", {"path": path, "assignee": assignee, "shop_floor_dispatch": True})

	return {
		"name": order_name,
		"production_path": path,
		"stage": stage.name,
		"status": STAGE_ORDER_STATUS[first_stage_type],
		"current_assignee": assignee,
		"department_status": "بحاجة للعمل",
	}


@frappe.whitelist()
def start_my_stage(stage_name: str) -> dict[str, Any]:
	stage = frappe.get_doc("Production Stage", stage_name)
	_require_stage_assignee_or_admin(stage)
	if stage.status != "Pending":
		frappe.throw(_("Only a stage that needs work can be started."))

	_maybe_consume_stock(stage.door_cutting_order, stage.stage_type, "Cutting Start")

	stage.started_by = frappe.session.user
	stage.start_time = now_datetime()
	stage.status = "In Progress"
	if not stage.assigned_to:
		stage.assigned_to = frappe.session.user
	stage.save(ignore_permissions=True)
	_log_event(stage, "Start", {"assigned_to": stage.assigned_to, "shop_floor": True})
	_set_order_tracking(stage.door_cutting_order, stage=stage)
	return {
		"stage": stage.name,
		"status": stage.status,
		"order_status": frappe.db.get_value("Door Cutting Order", stage.door_cutting_order, "status"),
		"department_status": "قيد العمل",
	}


@frappe.whitelist()
def handoff_to_next(stage_name: str, next_assignee: str | None = None) -> dict[str, Any]:
	stage = frappe.get_doc("Production Stage", stage_name)
	_require_stage_assignee_or_admin(stage)
	if stage.status not in {"In Progress", "Paused"}:
		frappe.throw(_("Start the stage before sending it to the next department."))

	order = frappe.get_doc("Door Cutting Order", stage.door_cutting_order)
	path = order.production_path
	if not path:
		frappe.throw(_("Order has no production path."))

	if stage.stage_type == "Drawing":
		dxf_status = order.drawing_dxf_status or "None"
		if dxf_status != "Approved by Drawing":
			frappe.throw(_("Approve the production DXF before sending the order to CNC."))

	next_type = _next_stage_type(path, stage.stage_type)

	if stage.status == "Paused":
		from almdina_erp.almdina_erp.services.production_service import _close_open_pause

		_close_open_pause(stage, frappe.session.user)

	finish_time = now_datetime()
	stage.finish_time = finish_time
	stage.finished_by = frappe.session.user
	stage.status = "Completed"
	stage.completed_qty = _required_piece_qty(stage.door_cutting_order)
	if stage.start_time:
		total_seconds = max(0, cint(time_diff_in_seconds(finish_time, stage.start_time)))
		stage.actual_working_seconds = max(0, total_seconds - cint(stage.paused_seconds))
	stage.save(ignore_permissions=True)

	remnants = _maybe_register_remnants(stage.door_cutting_order, stage.stage_type)
	_maybe_consume_stock(stage.door_cutting_order, stage.stage_type, "Cutting Finish")
	_log_event(
		stage,
		"Finish",
		{"shop_floor": True, "handoff": True, "next_stage_type": next_type, "remnants": remnants or {}},
	)

	if not next_type:
		_set_order_tracking(
			stage.door_cutting_order,
			status="Ready for Delivery",
			department="جاهز للتسليم",
			assignee="",
			department_status="مكتمل",
			clear_stage=True,
		)
		return {
			"stage": stage.name,
			"status": "Completed",
			"order_status": "Ready for Delivery",
			"ready_for_delivery": True,
		}

	if not next_assignee:
		frappe.throw(_("Select the next worker."))
	_assert_user_has_role(next_assignee, STAGE_ROLE[next_type])

	next_stage = _create_stage(
		stage.door_cutting_order,
		next_type,
		next_assignee,
		_sequence_for_stage(path, next_type),
	)
	_set_order_tracking(stage.door_cutting_order, stage=next_stage)
	_log_event(next_stage, "Created", {"from_stage": stage.name, "assignee": next_assignee, "shop_floor_handoff": True})

	return {
		"stage": stage.name,
		"status": "Completed",
		"next_stage": next_stage.name,
		"next_stage_type": next_type,
		"order_status": STAGE_ORDER_STATUS[next_type],
		"ready_for_delivery": False,
	}


@frappe.whitelist()
def mark_delivered(order_name: str) -> dict[str, Any]:
	require_any_role(*ADMIN_ROLES)
	status = frappe.db.get_value("Door Cutting Order", order_name, "status")
	if status != "Ready for Delivery":
		frappe.throw(_("Only orders ready for delivery can be marked as delivered."))
	_set_order_tracking(
		order_name,
		status="Delivered",
		department="تم التسليم",
		assignee="",
		department_status="مكتمل",
		clear_stage=True,
	)
	return {"name": order_name, "status": "Delivered"}


@frappe.whitelist()
def revert_department(order_name: str, target_stage: str | None = None, target_stage_type: str | None = None) -> dict[str, Any]:
	require_any_role("Production Manager", "System Manager", "Order Entry")
	order = frappe.get_doc("Door Cutting Order", order_name)
	if order.status == "Delivered":
		frappe.throw(_("Delivered orders cannot be reverted."))
	if not order.production_path:
		frappe.throw(_("Order is not on the shop-floor path."))

	stage_type = _resolve_revert_stage_type(target_stage_type or target_stage)
	candidates = frappe.get_all(
		"Production Stage",
		filters={
			"door_cutting_order": order_name,
			"stage_type": stage_type,
		},
		fields=["name", "piece_label", "sequence"],
		order_by="sequence asc",
	)
	stage_name = next((row.name for row in candidates if not row.piece_label), None)
	if not stage_name and target_stage and frappe.db.exists("Production Stage", target_stage):
		# Legacy callers may still pass a Production Stage name.
		stage_name = target_stage
	if not stage_name:
		frappe.throw(_("No shop-floor stage found for {0}.").format(_(stage_type or target_stage or "")))

	stage = frappe.get_doc("Production Stage", stage_name)
	if stage.door_cutting_order != order_name:
		frappe.throw(_("Stage does not belong to this order."))
	if stage.stage_type not in SHOP_FLOOR_STAGE_TYPES:
		frappe.throw(_("Only shop-floor stages can be reverted to."))

	later = frappe.get_all(
		"Production Stage",
		filters={
			"door_cutting_order": order_name,
			"sequence": [">", stage.sequence],
		},
		fields=["name", "piece_label"],
	)
	for row in later:
		if row.piece_label:
			continue
		doc = frappe.get_doc("Production Stage", row.name)
		doc.status = "Cancelled"
		doc.save(ignore_permissions=True)
		_log_event(doc, "Cancel", {"reason": "Reverted to earlier stage", "target": stage.stage_type})

	stage.status = "Pending"
	stage.started_by = None
	stage.start_time = None
	stage.finished_by = None
	stage.finish_time = None
	stage.actual_working_seconds = 0
	stage.paused_seconds = 0
	stage.completed_qty = 0
	stage.pauses = []
	stage.save(ignore_permissions=True)
	_log_event(stage, "Override", {"reopened": True, "shop_floor_revert": True})
	_set_order_tracking(order_name, stage=stage)

	return {
		"name": order_name,
		"stage": stage.name,
		"stage_type": stage.stage_type,
		"status": STAGE_ORDER_STATUS[stage.stage_type],
		"department_status": "بحاجة للعمل",
	}


def _resolve_revert_stage_type(value: str | None) -> str:
	raw = str(value or "").strip()
	if not raw:
		frappe.throw(_("Select a stage to revert to."))
	if raw in SHOP_FLOOR_STAGE_TYPES:
		return raw
	# Accept Arabic department labels from the UI select.
	for stage_type, label in STAGE_DEPARTMENT.items():
		if raw == label or raw == _(label) or raw == _(stage_type):
			return stage_type
	# Legacy Production Stage name fallback is handled by the caller.
	return raw


@frappe.whitelist()
def return_order_to_draft(order_name: str) -> dict[str, Any]:
	"""Order Entry may reopen a dispatched order as Draft for full re-editing."""
	require_any_role(*DISPATCH_ROLES)
	order = frappe.get_doc("Door Cutting Order", order_name)
	order.check_permission("write")
	if order.status in {"Draft", "Rejected"}:
		frappe.throw(_("Order is already editable as a draft."))
	if order.status in {"Delivered", "Cancelled"}:
		frappe.throw(_("Delivered or cancelled orders cannot return to draft."))

	stages = frappe.get_all(
		"Production Stage",
		filters={
			"door_cutting_order": order_name,
			"status": ["in", ["Pending", "In Progress", "Paused", "Completed"]],
			"stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
		},
		fields=["name", "piece_label"],
	)
	for row in stages:
		if row.piece_label:
			continue
		doc = frappe.get_doc("Production Stage", row.name)
		doc.status = "Cancelled"
		doc.save(ignore_permissions=True)
		_log_event(doc, "Cancel", {"reason": "Returned to draft", "shop_floor": True})

	frappe.db.set_value(
		"Door Cutting Order",
		order_name,
		{
			"status": "Draft",
			"approved_plan": None,
			"production_path": None,
			"current_department": None,
			"current_assignee": None,
			"department_status": None,
			"current_production_stage": None,
			"drawing_dxf_status": "None",
			"production_dxf": None,
		},
		update_modified=True,
	)
	return {"name": order_name, "status": "Draft"}


@frappe.whitelist()
def get_revert_targets(order_name: str) -> list[dict[str, Any]]:
	require_any_role(*ADMIN_ROLES)
	status = frappe.db.get_value("Door Cutting Order", order_name, "status")
	if status == "Delivered":
		return []
	rows = frappe.get_all(
		"Production Stage",
		filters={
			"door_cutting_order": order_name,
			"stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
			"status": ["in", ["Completed", "In Progress", "Paused", "Pending"]],
		},
		fields=["name", "stage_type", "status", "sequence", "assigned_to", "piece_label"],
		order_by="sequence asc",
	)
	targets = []
	seen = set()
	for row in rows:
		if row.piece_label or row.stage_type in seen:
			continue
		seen.add(row.stage_type)
		targets.append(
			{
				"name": row.name,
				"stage_type": row.stage_type,
				"label": STAGE_DEPARTMENT.get(row.stage_type, row.stage_type),
				"status": row.status,
				"sequence": row.sequence,
				"assigned_to": row.assigned_to,
			}
		)
	return targets


def _filter_active_shop_floor_stages(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Hide stale stage rows that are no longer the order's current production stage."""
	if not stages:
		return []
	order_names = list({row.get("door_cutting_order") for row in stages if row.get("door_cutting_order")})
	if not order_names:
		return stages
	current_by_order = {
		row.name: row.current_production_stage
		for row in frappe.get_all(
			"Door Cutting Order",
			filters={"name": ["in", order_names]},
			fields=["name", "current_production_stage"],
		)
	}
	kept: list[dict[str, Any]] = []
	for stage in stages:
		order_name = stage.get("door_cutting_order")
		current = current_by_order.get(order_name)
		if current and stage.get("name") != current:
			continue
		kept.append(stage)
	return kept


def _active_stage_snapshot(order: Any) -> dict[str, Any]:
	stage_name = getattr(order, "current_production_stage", None) or (
		order.get("current_production_stage") if isinstance(order, dict) else None
	)
	if not stage_name:
		return {
			"active_stage_name": None,
			"active_stage_status": None,
			"active_stage_type": None,
			"can_start_stage": False,
			"can_handoff_stage": False,
			"can_handoff_to": None,
		}
	stage_row = frappe.db.get_value(
		"Production Stage",
		stage_name,
		["name", "status", "stage_type"],
		as_dict=True,
	)
	if not stage_row:
		return {
			"active_stage_name": stage_name,
			"active_stage_status": None,
			"active_stage_type": None,
			"can_start_stage": False,
			"can_handoff_stage": False,
			"can_handoff_to": None,
		}
	production_path = getattr(order, "production_path", None) or (
		order.get("production_path") if isinstance(order, dict) else None
	)
	stage_status = stage_row.status
	return {
		"active_stage_name": stage_row.name,
		"active_stage_status": stage_status,
		"active_stage_type": stage_row.stage_type,
		"can_start_stage": stage_status == "Pending",
		"can_handoff_stage": stage_status in {"In Progress", "Paused"},
		"can_handoff_to": _next_stage_type(production_path or "", stage_row.stage_type)
		if production_path
		else None,
	}


@frappe.whitelist()
def get_my_inbox() -> list[dict[str, Any]]:
	user = frappe.session.user
	if user in {"Guest"}:
		frappe.throw(_("Login required."), frappe.PermissionError)

	filters: dict[str, Any] = {
		"status": ["in", ["Pending", "In Progress", "Paused"]],
		"stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
	}
	if not _is_admin():
		filters["assigned_to"] = user

	stages = frappe.get_all(
		"Production Stage",
		filters=filters,
		fields=[
			"name",
			"door_cutting_order",
			"stage_type",
			"status",
			"assigned_to",
			"sequence",
			"modified",
		],
		order_by="modified desc",
	)
	return _enrich_stage_rows(_filter_active_shop_floor_stages(stages))


@frappe.whitelist()
def get_my_archive() -> list[dict[str, Any]]:
	user = frappe.session.user
	filters: dict[str, Any] = {
		"status": "Completed",
		"stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
	}
	if not _is_admin():
		filters["assigned_to"] = user

	stages = frappe.get_all(
		"Production Stage",
		filters=filters,
		fields=[
			"name",
			"door_cutting_order",
			"stage_type",
			"status",
			"assigned_to",
			"sequence",
			"finish_time",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=100,
	)
	return _enrich_stage_rows(stages)


def _parse_plan_snapshot(order: Any, plan_source: str | None = None) -> dict[str, Any]:
	"""Load the approved/order cutting plan snapshot used for shop-floor rendering."""
	if plan_source == "System":
		from almdina_erp.almdina_erp.services.dual_plan_fields import get_system_plan_json

		raw = getattr(order, "system_plan_json", None) or (
			order.get("system_plan_json") if isinstance(order, dict) else None
		)
		if not raw:
			raw = get_system_plan_json(order)
		if raw:
			parsed = frappe.parse_json(raw) or {}
			if parsed:
				return parsed
		return {}
	if plan_source == "Custom":
		from almdina_erp.almdina_erp.services.dual_plan_fields import get_custom_plan_json

		raw = getattr(order, "custom_plan_json", None) or (
			order.get("custom_plan_json") if isinstance(order, dict) else None
		)
		if not raw:
			raw = get_custom_plan_json(order)
		if raw:
			parsed = frappe.parse_json(raw) or {}
			if parsed:
				return parsed
		return {}

	snapshot = None
	approved_plan = getattr(order, "approved_plan", None) or (
		order.get("approved_plan") if isinstance(order, dict) else None
	)
	if approved_plan:
		raw = frappe.db.get_value("Cutting Plan", approved_plan, "snapshot_json")
		if raw:
			snapshot = frappe.parse_json(raw) or {}
	if not snapshot:
		raw = getattr(order, "cutting_plan_json", None) or (
			order.get("cutting_plan_json") if isinstance(order, dict) else None
		)
		if raw:
			snapshot = frappe.parse_json(raw) or {}
	return snapshot if isinstance(snapshot, dict) else {}


def _user_can_view_dual_plans() -> bool:
	roles = set(frappe.get_roles())
	return bool(
		roles.intersection({"Order Entry", "Production Manager", "System Manager", "عامل رسم"})
	)


def _active_plan_source_for_viewer(order: Any) -> str:
	if _user_can_view_dual_plans():
		return (getattr(order, "approved_plan_source", None) or "System") if order.approved_plan else "System"
	return getattr(order, "approved_plan_source", None) or "System"


def _plan_snapshot_bundle(order: Any) -> dict[str, Any]:
	system_snapshot = _parse_plan_snapshot(order, "System")
	custom_snapshot = _parse_plan_snapshot(order, "Custom")
	active_source = _active_plan_source_for_viewer(order)
	active_snapshot = custom_snapshot if active_source == "Custom" and custom_snapshot.get("sheets") else system_snapshot
	if order.approved_plan and not _user_can_view_dual_plans():
		active_snapshot = _parse_plan_snapshot(order)
	return {
		"system_plan_json": frappe.as_json(system_snapshot) if system_snapshot else "",
		"custom_plan_json": frappe.as_json(custom_snapshot) if custom_snapshot.get("sheets") else "",
		"approved_plan_source": getattr(order, "approved_plan_source", None) or "System",
		"active_plan_source": active_source,
		"system_plan_html": _render_shop_floor_plan_html(
			order_name=order.name,
			customer=order.customer,
			snapshot=system_snapshot,
		),
		"custom_plan_html": _render_shop_floor_plan_html(
			order_name=order.name,
			customer=order.customer,
			snapshot=custom_snapshot,
		) if custom_snapshot.get("sheets") else "",
		"active_plan_html": _render_shop_floor_plan_html(
			order_name=order.name,
			customer=order.customer,
			snapshot=active_snapshot,
		),
		"show_dual_tabs": _user_can_view_dual_plans(),
	}


def _fmt_cm(value: Any) -> str:
	try:
		n = float(value or 0)
	except (TypeError, ValueError):
		return ""
	if n == int(n):
		return str(int(n))
	return f"{n:.1f}".rstrip("0").rstrip(".")


def _chip(label: str, checked: bool) -> str:
	cls = "is-checked" if checked else ""
	mark = "✓ " if checked else ""
	return (
		f'<span class="dco-check-toggle {cls}" style="min-height:28px;border:1px solid #ccd3da;border-radius:8px;'
		f'padding:3px 6px;font-size:11px;display:inline-flex;align-items:center;justify-content:center;'
		f'background:{"#2490ef" if checked else "#fff"};color:{"#fff" if checked else "#334"};'
		f'font-weight:{"800" if checked else "400"};opacity:{"1" if checked else ".55"}">'
		f"{mark}{frappe.utils.escape_html(label)}</span>"
	)


def _render_shop_floor_pieces_html(order: Any) -> str:
	"""Read-only pieces / edge table for shop-floor operators."""
	rows = list(getattr(order, "pieces", None) or [])
	if not rows:
		return ""

	default_edge = getattr(order, "default_edge_type", None) or ""
	body_rows = []
	for idx, row in enumerate(rows, start=1):
		edge_type = (row.edge_type or "").strip() or default_edge or _("القشاط الرئيسي")
		allow_rotation = cint(row.allow_rotation)
		body_rows.append(
			"<tr>"
			f'<td style="text-align:center;font-weight:800">{idx}</td>'
			f'<td style="text-align:center;direction:ltr">{_fmt_cm(row.width_cm)}</td>'
			f'<td style="text-align:center;direction:ltr">{_fmt_cm(row.length_cm)}</td>'
			f'<td style="text-align:center">{cint(row.qty)}</td>'
			f'<td style="text-align:center">{_chip("↻", allow_rotation)}</td>'
			'<td><div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px">'
			f'{_chip(_("طول يمين"), cint(row.edge_long_right))}'
			f'{_chip(_("طول يسار"), cint(row.edge_long_left))}'
			f'{_chip(_("عرض أعلى"), cint(row.edge_width_top))}'
			f'{_chip(_("عرض أسفل"), cint(row.edge_width_bottom))}'
			"</div></td>"
			f'<td style="text-align:center">{frappe.utils.escape_html(str(edge_type))}</td>'
			"</tr>"
		)

	return (
		'<div class="dco-fast-entry-shell" style="direction:rtl;border:1px solid #dfe3e8;border-radius:14px;'
		'overflow:hidden;background:#fff;margin-bottom:14px">'
		'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;'
		'padding:10px 12px;background:#f8f9fa;border-bottom:1px solid #dfe3e8;font-size:12px">'
		f"<b>{_('قائمة القطع والقشاط')}</b>"
		f'<span style="font-weight:700;opacity:.75">{_("الطلب للعرض فقط")}</span>'
		"</div>"
		'<div style="overflow:auto;-webkit-overflow-scrolling:touch;max-height:55vh">'
		'<table style="width:100%;min-width:640px;border-collapse:separate;border-spacing:0">'
		"<thead><tr>"
		'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">#</th>'
		f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{_("العرض (سم)")}</th>'
		f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{_("الطول (سم)")}</th>'
		f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{_("العدد")}</th>'
		f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{_("تدوير")}</th>'
		f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{_("جهات القشاط")}</th>'
		f'<th style="position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3e8;padding:8px 5px;font-size:12px;text-align:center">{_("نوع القشاط")}</th>'
		"</tr></thead>"
		f"<tbody>{''.join(body_rows)}</tbody>"
		"</table></div></div>"
	)


def _render_piece_edge_lines(piece: dict[str, Any]) -> str:
	"""Red edge-banding marks on a placed piece (same mapping as admin plan renderer)."""
	rotated = bool(piece.get("rotated"))
	if not rotated:
		left = 1 if piece.get("edge_long_left") else 0
		right = 1 if piece.get("edge_long_right") else 0
		top = 1 if piece.get("edge_width_top") else 0
		bottom = 1 if piece.get("edge_width_bottom") else 0
	else:
		# 90° clockwise — preserve physical edge meaning.
		top = 1 if piece.get("edge_long_left") else 0
		bottom = 1 if piece.get("edge_long_right") else 0
		right = 1 if piece.get("edge_width_top") else 0
		left = 1 if piece.get("edge_width_bottom") else 0

	color = "#d00000"
	thickness = "3px"
	inset = "3px"
	edge_line_percent = 66.666
	edge_line_start = (100 - edge_line_percent) / 2
	parts: list[str] = []
	common = 'class="dco-edge-line" style="position:absolute;z-index:3;'
	if left:
		parts.append(
			f'<span {common}left:{inset};top:{edge_line_start}%;height:{edge_line_percent}%;'
			f'border-left:{thickness} solid {color};"></span>'
		)
	if right:
		parts.append(
			f'<span {common}right:{inset};top:{edge_line_start}%;height:{edge_line_percent}%;'
			f'border-right:{thickness} solid {color};"></span>'
		)
	if top:
		parts.append(
			f'<span {common}top:{inset};left:{edge_line_start}%;width:{edge_line_percent}%;'
			f'border-top:{thickness} solid {color};"></span>'
		)
	if bottom:
		parts.append(
			f'<span {common}bottom:{inset};left:{edge_line_start}%;width:{edge_line_percent}%;'
			f'border-bottom:{thickness} solid {color};"></span>'
		)
	return "".join(parts)


def _render_shop_floor_plan_html(
	*,
	order_name: str,
	customer: str | None,
	snapshot: dict[str, Any],
) -> str:
	"""Simplified cutting-plan drawings for operators (no kerf/cost technical strip)."""
	sheets = snapshot.get("sheets") or []
	if not sheets:
		return ""

	def num(value: Any) -> float:
		try:
			return float(value or 0)
		except (TypeError, ValueError):
			return 0.0

	board_w = num(snapshot.get("usable_board_width_cm")) or num(snapshot.get("full_board_width_cm")) or 1
	board_h = num(snapshot.get("usable_board_length_cm")) or num(snapshot.get("full_board_length_cm")) or 1
	board_width_px = 560
	board_height_px = max(260, int(round(board_width_px * (board_h / board_w))))

	parts = [
		'<div class="dco-cutting-plan" style="font-family:Arial,Tahoma,sans-serif;direction:rtl;color:#111;background:#fff;">',
		f'<h2 style="margin:0 0 10px 0;font-size:18px;">{_("خطة القص")}</h2>',
		(
			'<div style="line-height:1.7;margin-bottom:12px;font-size:13px;">'
			f"<b>{_('الطلب')}:</b> {frappe.utils.escape_html(order_name or '')} &nbsp; | &nbsp; "
			f"<b>{_('الزبون')}:</b> {frappe.utils.escape_html(customer or '')}"
			"</div>"
		),
	]

	for sheet in sheets:
		pieces = sheet.get("pieces") or []
		sheet_no = sheet.get("sheet_no") or ""
		parts.append(
			'<div class="dco-sheet-card" style="border:1px solid #bbb;border-radius:10px;padding:10px;margin:14px 0;background:#fff;">'
			f'<div style="margin-bottom:8px;font-size:13px;font-weight:bold;">{_("اللوح")} {frappe.utils.escape_html(str(sheet_no))}'
			f' &nbsp; | &nbsp; {_("عدد القطع")}: {len(pieces)}</div>'
			f'<div style="position:relative;direction:ltr;width:{board_width_px}px;height:{board_height_px}px;max-width:100%;'
			'border:2px solid #111;background:linear-gradient(90deg,rgba(0,0,0,0.05) 1px,transparent 1px),'
			'linear-gradient(rgba(0,0,0,0.05) 1px,transparent 1px),#fff;background-size:32px 32px;overflow:hidden;margin:0 auto;">'
		)
		for piece in pieces:
			left = (num(piece.get("x")) / board_w) * 100
			top = (num(piece.get("y")) / board_h) * 100
			width = (num(piece.get("w")) / board_w) * 100
			height = (num(piece.get("h")) / board_h) * 100
			label = piece.get("label") or piece.get("piece_label") or ""
			ow = num(piece.get("original_w")) or num(piece.get("w"))
			oh = num(piece.get("original_h")) or num(piece.get("h"))
			edge_html = _render_piece_edge_lines(piece)
			parts.append(
				f'<div class="dco-piece" style="position:absolute;left:{left}%;top:{top}%;width:{width}%;height:{height}%;'
				"border:1px solid #111;background:#e4f5ff;color:#111;overflow:hidden;padding:2px;font-size:10px;"
				'line-height:1.2;text-align:center;box-sizing:border-box;display:flex;align-items:center;justify-content:center;">'
				f"{edge_html}"
				f'<div class="dco-piece-label" style="position:relative;z-index:4;direction:ltr;text-align:center;">'
				f"<b>{frappe.utils.escape_html(str(label))}</b><br>"
				f"<span>{round(ow, 1)}*{round(oh, 1)} سم</span></div>"
				"</div>"
			)
		parts.append("</div></div>")

	parts.append("</div>")
	return "".join(parts)


def _enrich_stage_rows(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
	if not stages:
		return []
	order_names = list({row.door_cutting_order for row in stages})
	orders = {
		row.name: row
		for row in frappe.get_all(
			"Door Cutting Order",
			filters={"name": ["in", order_names]},
			fields=[
				"name",
				"customer",
				"order_date",
				"status",
				"production_path",
				"current_department",
				"department_status",
				"approved_plan",
				"production_dxf",
				"drawing_dxf_status",
				"revision",
			],
		)
	}
	out = []
	for stage in stages:
		order = orders.get(stage.door_cutting_order) or {}
		out.append(
			{
				**stage,
				"customer": order.get("customer"),
				"order_date": order.get("order_date"),
				"order_status": order.get("status"),
				"production_path": order.get("production_path"),
				"current_department": order.get("current_department"),
				"department_status": order.get("department_status") or DEPARTMENT_STATUS_MAP.get(stage.status),
				"approved_plan": order.get("approved_plan"),
				"production_dxf": order.get("production_dxf"),
				"drawing_dxf_status": order.get("drawing_dxf_status"),
				"revision": order.get("revision"),
				"department_label": STAGE_DEPARTMENT.get(stage.stage_type, stage.stage_type),
				"can_handoff_to": _next_stage_type(order.get("production_path") or "", stage.stage_type)
				if order.get("production_path")
				else None,
			}
		)
	return out


@frappe.whitelist()
def get_order_shop_floor_detail(order_name: str) -> dict[str, Any]:
	order = frappe.get_doc("Door Cutting Order", order_name)
	_assert_can_view_order(order)
	stages = frappe.get_all(
		"Production Stage",
		filters={
			"door_cutting_order": order_name,
			"stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
		},
		fields=["name", "stage_type", "status", "assigned_to", "sequence", "start_time", "finish_time", "piece_label"],
		order_by="sequence asc",
	)
	stages = [row for row in stages if not row.piece_label]
	plan_bundle = _plan_snapshot_bundle(order)
	pieces_html = _render_shop_floor_pieces_html(order)
	current_stage_type = None
	stage_snapshot = _active_stage_snapshot(order)
	current_stage_type = stage_snapshot.get("active_stage_type")
	can_recalculate_drawing_plan = bool(
		order.production_path == "Drawing"
		and not order.approved_plan
		and (current_stage_type == "Drawing" or order.status == "At Drawing")
	)
	return {
		"name": order.name,
		"customer": order.customer,
		"status": order.status,
		"production_path": order.production_path,
		"current_department": order.current_department,
		"current_assignee": order.current_assignee,
		"department_status": order.department_status,
		"current_production_stage": order.current_production_stage,
		"active_stage_name": stage_snapshot.get("active_stage_name"),
		"active_stage_status": stage_snapshot.get("active_stage_status"),
		"can_start_stage": stage_snapshot.get("can_start_stage"),
		"can_handoff_stage": stage_snapshot.get("can_handoff_stage"),
		"can_handoff_to": stage_snapshot.get("can_handoff_to"),
		"approved_plan": order.approved_plan,
		"pieces_html": pieces_html,
		"cutting_plan_html": plan_bundle["active_plan_html"],
		"system_plan_html": plan_bundle["system_plan_html"],
		"custom_plan_html": plan_bundle["custom_plan_html"],
		"system_plan_json": plan_bundle["system_plan_json"],
		"custom_plan_json": plan_bundle["custom_plan_json"],
		"approved_plan_source": plan_bundle["approved_plan_source"],
		"active_plan_source": plan_bundle["active_plan_source"],
		"show_dual_tabs": plan_bundle["show_dual_tabs"],
		"packing_mode": order.packing_mode,
		"kerf_mm": order.kerf_mm,
		"trim_margin_mm": order.trim_margin_mm,
		"cutting_machine_type": order.cutting_machine_type,
		"current_stage_type": current_stage_type,
		"can_recalculate_drawing_plan": can_recalculate_drawing_plan,
		"production_dxf": order.production_dxf,
		"drawing_dxf_status": order.drawing_dxf_status,
		"stages": stages,
	}


def _assert_can_view_order(order: Any) -> None:
	if _is_admin():
		return
	user = frappe.session.user
	assigned = frappe.db.exists(
		"Production Stage",
		{"door_cutting_order": order.name, "assigned_to": user, "stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)]},
	)
	if not assigned:
		frappe.throw(_("Not permitted to view this order."), frappe.PermissionError)


@frappe.whitelist()
def mark_dxf_exported(order_name: str) -> dict[str, Any]:
	require_any_role("عامل رسم", "Production Manager", "System Manager")
	_assert_order_at_drawing(order_name)
	current = frappe.db.get_value("Door Cutting Order", order_name, "drawing_dxf_status") or "None"
	if current in {"None", "Exported"}:
		frappe.db.set_value("Door Cutting Order", order_name, "drawing_dxf_status", "Exported", update_modified=True)
	return {"name": order_name, "drawing_dxf_status": frappe.db.get_value("Door Cutting Order", order_name, "drawing_dxf_status")}


@frappe.whitelist()
def upload_production_dxf(order_name: str, file_url: str) -> dict[str, Any]:
	require_any_role("عامل رسم", "Production Manager", "System Manager")
	_assert_order_at_drawing(order_name)
	if not file_url:
		frappe.throw(_("Attach a DXF file."))
	if not str(file_url).lower().endswith(".dxf"):
		frappe.throw(_("Production file must be a .dxf attachment."))
	order = frappe.get_doc("Door Cutting Order", order_name)
	from almdina_erp.almdina_erp.services.dxf_import_service import parse_production_dxf, validate_imported_plan

	custom_snapshot = parse_production_dxf(file_url, order)
	validation = validate_imported_plan(custom_snapshot, order)
	if not validation.get("is_valid"):
		frappe.throw(_("Imported DXF plan is invalid:\n{0}").format("\n".join(validation.get("errors") or [])))
	from almdina_erp.almdina_erp.services.dual_plan_fields import has_dual_plan_field

	update_values: dict[str, Any] = {
		"production_dxf": file_url,
		"drawing_dxf_status": "Uploaded",
	}
	if has_dual_plan_field("custom_plan_json"):
		update_values["custom_plan_json"] = frappe.as_json(custom_snapshot)
	frappe.db.set_value(
		"Door Cutting Order",
		order_name,
		update_values,
		update_modified=True,
	)
	return {
		"name": order_name,
		"production_dxf": file_url,
		"drawing_dxf_status": "Uploaded",
		"custom_plan_json": frappe.as_json(custom_snapshot),
	}


@frappe.whitelist()
def recalculate_drawing_plan(
	order_name: str,
	packing_mode: str | None = None,
	cutting_machine_type: str | None = None,
	kerf_mm: float | None = None,
	trim_margin_mm: float | None = None,
) -> dict[str, Any]:
	"""Recalculate the system cutting plan for drawing operators without full order edit."""
	require_any_role("عامل رسم", "Production Manager", "System Manager")
	_assert_order_at_drawing(order_name)
	order = frappe.get_doc("Door Cutting Order", order_name)
	order.check_permission("read")
	if order.approved_plan:
		frappe.throw(_("This order already has a locked cutting plan."))

	if packing_mode:
		order.packing_mode = packing_mode
	if cutting_machine_type:
		order.cutting_machine_type = cutting_machine_type
	if kerf_mm is not None:
		order.kerf_mm = kerf_mm
	if trim_margin_mm is not None:
		order.trim_margin_mm = trim_margin_mm

	order.flags.force_cutting_plan_recalculation = True
	order.save(ignore_permissions=True)

	from almdina_erp.almdina_erp.api import _serialize_order_preview

	return _serialize_order_preview(order)


@frappe.whitelist()
def approve_production_dxf(order_name: str) -> dict[str, Any]:
	require_any_role("عامل رسم", "Production Manager", "System Manager")
	_assert_order_at_drawing(order_name)
	from almdina_erp.almdina_erp.services.cutting_plan_service import lock_cutting_plan

	return lock_cutting_plan(order_name, plan_source="Custom")


def _assert_order_at_drawing(order_name: str) -> None:
	from almdina_erp.almdina_erp.services.order_edit_policy import is_order_at_drawing_stage

	row = frappe.db.get_value(
		"Door Cutting Order",
		order_name,
		["name", "status", "production_path", "current_production_stage"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Order not found."))
	if not is_order_at_drawing_stage(row):
		frappe.throw(_("DXF actions are only available while the order is at Drawing."))


# Keep sync_order_status import used by callers that finish legacy stages after shop-floor work.
__all__ = [
	"assert_order_ready_for_dispatch",
	"dispatch_order",
	"start_my_stage",
	"handoff_to_next",
	"mark_delivered",
	"revert_department",
	"return_order_to_draft",
	"get_my_inbox",
	"get_my_archive",
	"sync_order_status",
	"recalculate_drawing_plan",
]
