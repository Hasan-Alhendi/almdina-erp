"""Disposable fixtures for the isolated Phase 1B Frappe Desk job only."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import erpnext
import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_membership import MEMBERSHIP_FIELD


EXPECTED = {"frappe": "16.17.5", "erpnext": "16.17.0"}


def _versions() -> dict[str, str]:
    versions = {"frappe": frappe.__version__, "erpnext": erpnext.__version__}
    if versions != EXPECTED:
        raise RuntimeError(f"Pinned P0 runtime required: {EXPECTED}; found {versions}")
    return versions


def _leaf(doctype: str, name_field: str, parent_field: str, suffix: str) -> str:
    name = frappe.db.get_value(doctype, {"is_group": 0}, "name")
    if name:
        return str(name)
    root = frappe.db.get_value(doctype, {"is_group": 1}, "name")
    if not root:
        root = frappe.get_doc(
            {"doctype": doctype, name_field: f"P0 root {suffix}", "is_group": 1}
        ).insert(ignore_permissions=True).name
    return str(
        frappe.get_doc(
            {
                "doctype": doctype,
                name_field: f"P0 leaf {suffix}",
                parent_field: root,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True).name
    )


def prepare() -> dict[str, object]:
    frappe.set_user("Administrator")
    versions = _versions()
    if not frappe.is_setup_complete():
        suffix = uuid4().hex[:8]
        setup_complete(
            {
                "language": "English", "lang": "en", "country": "United States",
                "currency": "USD", "timezone": "UTC",
                "company_name": f"P0 Isolated {suffix}",
                "company_abbr": f"P{suffix[:6]}",
                "chart_of_accounts": "Standard", "fy_start_date": "2026-01-01",
                "fy_end_date": "2026-12-31", "domain": "Manufacturing",
                "setup_demo": 0,
            }
        )
        frappe.db.commit()
        frappe.clear_cache()
    if not frappe.is_setup_complete():
        raise RuntimeError("Frappe Setup Wizard did not complete")

    suffix = uuid4().hex[:10]
    group = frappe.db.get_single_value("Selling Settings", "customer_group")
    if group and frappe.db.get_value("Customer Group", group, "is_group") != 0:
        group = None
    territory = frappe.db.get_single_value("Selling Settings", "territory")
    if territory and frappe.db.get_value("Territory", territory, "is_group") != 0:
        territory = None
    customer = frappe.get_doc(
        {
            "doctype": "Customer", "customer_name": f"P0 Isolated {suffix}",
            "customer_type": "Individual",
            "customer_group": group or _leaf("Customer Group", "customer_group_name", "parent_customer_group", suffix),
            "territory": territory or _leaf("Territory", "territory_name", "parent_territory", suffix),
        }
    ).insert(ignore_permissions=True)
    edge = frappe.get_doc(
        {
            "doctype": "Edge Banding Type", "edge_type_name": f"P0 {suffix}",
            "english_name": f"P0 {suffix}", "width_cm": 2,
            "thickness_mm": 1, "rate_usd_per_meter": 1,
        }
    ).insert(ignore_permissions=True)

    orders = {}
    for label, board, width, length, rate in (
        ("A", "P0 أبيض", 42, 81, 11),
        ("B", "P0 أسود", 57, 93, 19),
    ):
        doc = frappe.get_doc(
            {
                "doctype": "Door Cutting Order", "customer": customer.name,
                "board_description": board, "board_length_cm": 244,
                "board_width_cm": 122, "default_edge_type": edge.name,
                "edge_color": f"P0 edge {label}", "kerf_mm": 5,
                "trim_margin_mm": 5, "optimization_time_limit_sec": 10,
                "board_rate_usd": rate, "cutting_cost_per_board_usd": 2,
                "pieces": [
                    {"piece_type": "Regular", "width_cm": width,
                     "length_cm": length, "qty": 1}
                ],
            }
        ).insert(ignore_permissions=True)
        orders[label] = {
            "name": str(doc.name), "board": board,
            "piece_name": str(doc.pieces[0].name),
            "width_cm": width, "length_cm": length,
        }
    if orders["A"]["piece_name"] == orders["B"]["piece_name"]:
        raise AssertionError("Frappe generated duplicate child names")

    # Administrator can pass document-level checks while its boot route catalog
    # omits this DocType. Use a disposable, explicitly granted factory role.
    administrator = {
        "metadata": bool(frappe.db.exists("DocType", "Door Cutting Order")),
        "has_read": bool(frappe.has_permission("Door Cutting Order", "read", user="Administrator")),
        "can_read_route": "Door Cutting Order" in frappe.get_user().get_can_read(),
    }
    role = frappe.get_doc({"doctype": "Role", "role_name": f"P0 Desk {suffix}",
                           "desk_access": 1}).insert(ignore_permissions=True)
    ProjectedPermissionMatrixRepository().save_role_states({str(role.name): {
        Capability.VIEW_ORDERS: True,
        Capability.VIEW_ALL_ORDERS: True,
        Capability.CREATE_ORDER: True,
        Capability.EDIT_ORDER: True,
        Capability.VIEW_COSTS: True,
        Capability.VIEW_CUTTING_PLAN: True,
        Capability.VIEW_SYSTEM_CUTTING_PLAN: True,
        Capability.VIEW_UPLOADED_CUTTING_PLAN: True,
        Capability.VIEW_APPROVED_CUTTING_PLAN: True,
        Capability.EDIT_OPTIMIZER_SETTINGS: True,
        Capability.RECALCULATE_PLAN: True,
        Capability.EDIT_COST_SETTINGS: True,
        Capability.UPLOAD_DXF: True,
        Capability.APPROVE_DXF: True,
        Capability.SET_OFFCUT_EXECUTION_OWNER: True,
        Capability.PRINT_CUTTING_PLAN: True,
        Capability.VIEW_CUSTOMERS: True,
        Capability.VIEW_EDGE_BANDING_TYPES: True,
    }})
    email = f"p0-desk-{suffix}@example.com"
    password = uuid4().hex
    frappe.get_doc({"doctype": "User", "email": email, "first_name": "P0 Desk",
                    "user_type": "System User", "enabled": 1, "send_welcome_email": 0,
                    "new_password": password, MEMBERSHIP_FIELD: 1,
                    "roles": [{"role": str(role.name)}]}).insert(ignore_permissions=True)
    frappe.clear_cache(user=email)
    frappe.clear_cache(doctype="Door Cutting Order")
    frappe.set_user(email)
    test_user = {
        "metadata": bool(frappe.db.exists("DocType", "Door Cutting Order")),
        "has_read": bool(frappe.has_permission("Door Cutting Order", "read", user=email)),
        "can_read_route": "Door Cutting Order" in frappe.get_user().get_can_read(),
        "can_read_customer": "Customer" in frappe.get_user().get_can_read(),
    }
    if not all(test_user.values()):
        raise AssertionError(f"Isolated user cannot enter real DCO Form: {test_user}; Administrator: {administrator}")
    frappe.set_user("Administrator")
    frappe.db.commit()
    destination = os.environ.get("P0_FIXTURE_PATH")
    if not destination:
        raise RuntimeError("P0_FIXTURE_PATH is required in the isolated CI job")
    fixture = {"versions": versions, "customer": str(customer.name),
               "edge_type": str(edge.name), "orders": orders,
               "recovery_board": f"P0 Recovery {suffix}",
               "user": email, "password": password, "role": str(role.name),
               "route_preflight": {"administrator": administrator, "test_user": test_user}}
    Path(destination).write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    return {"versions": versions, "orders": orders,
            "route_preflight": fixture["route_preflight"]}


def cleanup() -> None:
    """Best effort disposal of records created by this job, never user records."""
    path = os.environ.get("P0_FIXTURE_PATH")
    if not path or not Path(path).is_file():
        return
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    frappe.set_user("Administrator")
    for name in frappe.get_all("Door Cutting Order",
                               filters={"board_description": fixture["recovery_board"]},
                               pluck="name"):
        for plan_name in frappe.get_all("Cutting Plan",
                                        filters={"door_cutting_order": name}, pluck="name"):
            frappe.delete_doc("Cutting Plan", plan_name, force=True,
                              ignore_permissions=True)
        frappe.delete_doc("Door Cutting Order", name, force=True,
                          ignore_permissions=True)
    for row in fixture["orders"].values():
        for plan_name in frappe.get_all("Cutting Plan",
                                        filters={"door_cutting_order": row["name"]},
                                        pluck="name"):
            for file_name in frappe.get_all("File",
                                            filters={"attached_to_doctype": "Cutting Plan",
                                                     "attached_to_name": plan_name}, pluck="name"):
                frappe.delete_doc("File", file_name, force=True, ignore_permissions=True)
            frappe.delete_doc("Cutting Plan", plan_name, force=True,
                              ignore_permissions=True)
        frappe.delete_doc("Door Cutting Order", row["name"], force=True,
                          ignore_permissions=True)
    for key in ("multi_order", "offcut_order"):
        extra_order = fixture.get(key) or {}
        if not extra_order.get("name"):
            continue
        for plan_name in frappe.get_all("Cutting Plan",
                                        filters={"door_cutting_order": extra_order["name"]},
                                        pluck="name"):
            for file_name in frappe.get_all("File",
                                            filters={"attached_to_doctype": "Cutting Plan",
                                                     "attached_to_name": plan_name}, pluck="name"):
                frappe.delete_doc("File", file_name, force=True, ignore_permissions=True)
            frappe.delete_doc("Cutting Plan", plan_name, force=True,
                              ignore_permissions=True)
        for file_name in frappe.get_all("File",
                                        filters={"attached_to_doctype": "Door Cutting Order",
                                                 "attached_to_name": extra_order["name"]}, pluck="name"):
            frappe.delete_doc("File", file_name, force=True, ignore_permissions=True)
        frappe.delete_doc("Door Cutting Order", extra_order["name"], force=True,
                          ignore_permissions=True)
    staged_file = fixture.get("offcut_staged_file")
    if staged_file and frappe.db.exists("File", staged_file):
        frappe.delete_doc("File", staged_file, force=True, ignore_permissions=True)
    if "prior_liner_price" in fixture:
        frappe.db.set_single_value("Almdina ERP Settings",
                                   "default_extra_liner_unit_price_usd",
                                   fixture["prior_liner_price"])
    frappe.delete_doc("Customer", fixture["customer"], force=True,
                      ignore_permissions=True)
    frappe.delete_doc("Edge Banding Type", fixture["edge_type"], force=True,
                      ignore_permissions=True)
    frappe.delete_doc("User", fixture["user"], force=True,
                      ignore_permissions=True)
    frappe.delete_doc("Role", fixture["role"], force=True,
                      ignore_permissions=True)
    frappe.db.commit()


def audit_db() -> dict[str, object]:
    """Read committed rows in a fresh bench process, independent of Desk cache."""
    path = os.environ.get("P0_FIXTURE_PATH")
    if not path or not Path(path).is_file():
        return {"status": "NOT_TESTED", "reason": "fixture unavailable"}
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    frappe.set_user("Administrator")
    rows = {}
    for label, expected in fixture["orders"].items():
        order = frappe.get_doc("Door Cutting Order", expected["name"])
        rows[label] = {"name": order.name, "board": order.board_description,
                       "modified": str(order.modified),
                       "pieces": [{"name": piece.name, "width_cm": piece.width_cm,
                                   "length_cm": piece.length_cm} for piece in order.pieces]}
    recovered_names = frappe.get_all("Door Cutting Order",
                                     filters={"board_description": fixture.get("recovery_board")},
                                     pluck="name")
    recovered = []
    for name in recovered_names:
        doc = frappe.get_doc("Door Cutting Order", name)
        recovered.append({"name": name, "board": doc.board_description,
                          "customer": doc.customer,
                          "piece_widths_cm": [piece.width_cm for piece in doc.pieces]})
    result = {"status": "OBSERVED", "rows": rows,
              "distinct_child_names": rows["A"]["pieces"][0]["name"] != rows["B"]["pieces"][0]["name"],
              "recovery_saved_names": recovered_names,
              "recovery_saved_rows": recovered}
    recovery_evidence = Path(os.environ.get("P0_EVIDENCE_DIR") or "") / "recovery-intersection.json"
    if recovery_evidence.is_file():
        native = json.loads(recovery_evidence.read_text(encoding="utf-8")).get("native_save") or {}
        if native.get("ok"):
            matches = [row for row in recovered if row["name"] == native["name"]]
            result["recovery_db_verified"] = bool(
                len(matches) == 1 and matches[0]["board"] == fixture["recovery_board"]
                and matches[0]["customer"] == fixture["customer"]
                and 31 in matches[0]["piece_widths_cm"]
            )
            if not result["recovery_db_verified"]:
                raise AssertionError(f"NEW Native Save did not persist its owned fields: {matches}")
            edit_evidence = json.loads(recovery_evidence.read_text(encoding="utf-8"))
            if edit_evidence.get("plan_saved") and edit_evidence.get("cost_saved"):
                order = frappe.get_doc("Door Cutting Order", native["name"])
                plan_name = edit_evidence["plan_saved"]["plan"]
                plan = frappe.get_doc("Cutting Plan", plan_name)
                result["post_save_edit"] = {
                    "order_name": order.name, "plan_name": plan.name,
                    "plan_order_name": plan.door_cutting_order,
                    "source": plan.source_type, "revision": plan.revision,
                    "kerf": float(plan.kerf_mm or 0),
                    "board_rate": float(plan.board_rate_usd or 0),
                    "piece_widths_cm": [piece.width_cm for piece in order.pieces],
                }
                expected_kerf = float(edit_evidence["plan_saved"]["kerf"])
                expected_rate = float(edit_evidence["cost_saved"]["board_rate"])
                result["post_save_edit_db_verified"] = bool(
                    result["post_save_edit"]["kerf"] == expected_kerf
                    and result["post_save_edit"]["board_rate"] == expected_rate
                    and plan.door_cutting_order == order.name
                    and plan.source_type == "System"
                    and 31 in result["post_save_edit"]["piece_widths_cm"]
                )
                if not result["post_save_edit_db_verified"]:
                    raise AssertionError(f"Post-save Plan/Cost not persisted: {result['post_save_edit']}")
    extra_evidence = Path(os.environ.get("P0_EVIDENCE_DIR") or "") / "recovery-extras.json"
    if extra_evidence.is_file():
        browser = json.loads(extra_evidence.read_text(encoding="utf-8"))
        saved = browser.get("native_save") or {}
        if saved.get("status") == "settled" and saved.get("name"):
            doc = frappe.get_doc("Door Cutting Order", saved["name"])
            expected = browser["expected"]
            actual = {}
            for piece in doc.pieces:
                if piece.notes not in expected:
                    continue
                actual[piece.notes] = {"name": piece.name, **{
                    field: piece.get(field) for field in expected[piece.notes]
                }}
            result["recovery_extra_rows"] = {"order": doc.name, "rows": actual}
            result["recovery_extra_db_verified"] = bool(
                doc.board_description == fixture["recovery_board"]
                and doc.customer == fixture["customer"]
                and len(actual) == len(expected)
                and len({row["name"] for row in actual.values()}) == len(expected)
                and all(all(actual[note].get(field) == value for field, value in fields.items())
                        for note, fields in expected.items() if note in actual)
                and not any(piece.notes in expected for piece in
                            frappe.get_doc("Door Cutting Order", fixture["orders"]["B"]["name"]).pieces)
            )
            if not result["recovery_extra_db_verified"]:
                raise AssertionError(f"NEW Extra fields did not persist in the owned rows: {actual}")
    evidence_dir = os.environ.get("P0_EVIDENCE_DIR")
    if evidence_dir:
        Path(evidence_dir).mkdir(parents=True, exist_ok=True)
        (Path(evidence_dir) / "database-audit.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def prepare_saved_plan() -> dict[str, object]:
    """Persist distinct real System plans for A and B on this disposable site."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text(encoding="utf-8"))
    frappe.set_user("Administrator")
    before_reset = audit_db()
    directory = Path(os.environ["P0_EVIDENCE_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "post-save-before-print-reset.json").write_text(
        json.dumps(before_reset, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep the print experiment's B visibly black, after preserving the
    # independent proof that the controlled Native Save had committed white.
    frappe.db.set_value("Door Cutting Order", fixture["orders"]["B"]["name"],
                        "board_description", fixture["orders"]["B"]["board"])
    frappe.db.commit()
    from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
        recalculate_system_plan,
    )

    summaries = {}
    for label in ("A", "B"):
        order = frappe.get_doc("Door Cutting Order", fixture["orders"][label]["name"])
        result = recalculate_system_plan(order)
        frappe.db.commit()
        plan = frappe.get_doc("Cutting Plan", result["cutting_plan"])
        snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
        summary = {"order_name": order.name, "name": plan.name,
                   "revision": int(plan.revision or 0),
                   "board": plan.board_description,
                   "sheet_count": len(snapshot.get("sheets") or []),
                   "first_piece": ((snapshot.get("sheets") or [{}])[0].get("pieces") or [{}])[0]}
        if not summary["sheet_count"]:
            raise AssertionError(f"Saved System plan has no printable sheets: {summary}")
        summaries[label] = summary
    (directory / "saved-plan-fixture.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {key: {field: value for field, value in summary.items() if field != "first_piece"}
            for key, summary in summaries.items()}


def prepare_approved_plan() -> dict[str, object]:
    """Approve B's real saved System row under the disposable role's capability."""
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text(encoding="utf-8"))
    from almdina_erp.almdina_erp.services.cutting_plan_command_service import approve_order_plan

    frappe.set_user(fixture["user"])
    order = frappe.get_doc("Door Cutting Order", fixture["orders"]["B"]["name"])
    result = approve_order_plan(order, "System")
    frappe.db.commit()
    approved = frappe.get_doc("Cutting Plan", result["cutting_plan"])
    evidence = {"order_name": order.name, "plan_name": approved.name,
                "revision": int(approved.revision or 0), "source": approved.source_type,
                "status": approved.status, "board": approved.board_description,
                "sheets": len((frappe.parse_json(approved.snapshot_json or "{}") or {}).get("sheets") or [])}
    destination = Path(os.environ["P0_EVIDENCE_DIR"]) / "approved-plan-fixture.json"
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def prepare_custom_dxf_plan() -> dict[str, object]:
    """Stage an actual private DXF and import it through the authorized command."""
    from tempfile import NamedTemporaryFile

    import ezdxf
    from frappe.utils.file_manager import save_file

    from almdina_erp.almdina_erp.services.dxf_import_service import (
        CUT_PATH_LAYER, SHEET_OUTLINE_LAYER,
    )
    from almdina_erp.almdina_erp.services.shop_floor_dxf_service import upload_production_dxf

    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text(encoding="utf-8"))
    order_name = fixture["orders"]["A"]["name"]
    frappe.set_user("Administrator")
    # This disposable Draft has no dispatched stage. Assign it to the drawing
    # department; the real endpoint still checks the role capability and stage
    # assignment policy as the fixture user.
    frappe.db.set_value("Door Cutting Order", order_name, "current_department", "رسم")
    drawing = ezdxf.new("R2010")
    model = drawing.modelspace()
    for points, layer in (
        (((0, 0), (1220, 0), (1220, 2440), (0, 2440)), SHEET_OUTLINE_LAYER),
        (((10, 10), (430, 10), (430, 820), (10, 820)), CUT_PATH_LAYER),
    ):
        for start, end in zip(points, (*points[1:], points[0])):
            model.add_line(start, end, dxfattribs={"layer": layer})
    with NamedTemporaryFile(suffix=".dxf") as staged:
        drawing.saveas(staged.name)
        raw = Path(staged.name).read_bytes()
    file_doc = save_file(f"p0-{order_name}.dxf", raw, None, None, is_private=1)
    frappe.db.commit()
    frappe.set_user(fixture["user"])
    result = upload_production_dxf(order_name, file_doc.file_url)
    frappe.db.commit()
    plan = frappe.get_doc("Cutting Plan", result["cutting_plan"])
    evidence = {"order_name": order_name, "plan_name": plan.name,
                "revision": int(plan.revision or 0), "source": plan.source_type,
                "status": plan.status, "board": plan.board_description,
                "sheets": len((frappe.parse_json(plan.snapshot_json or "{}") or {}).get("sheets") or [])}
    (Path(os.environ["P0_EVIDENCE_DIR"]) / "custom-plan-fixture.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def prepare_multiboard_extra_plan() -> dict[str, object]:
    """Persist several real System sheets with a liner requirement on one order."""
    fixture_path = Path(os.environ["P0_FIXTURE_PATH"])
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    frappe.set_user("Administrator")
    fixture["prior_liner_price"] = frappe.db.get_single_value(
        "Almdina ERP Settings", "default_extra_liner_unit_price_usd") or 0
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    frappe.db.set_single_value("Almdina ERP Settings",
                               "default_extra_liner_unit_price_usd", 3)
    order = frappe.get_doc({
        "doctype": "Door Cutting Order", "customer": fixture["customer"],
        "board_description": "P0 متعدد", "board_length_cm": 244,
        "board_width_cm": 122, "default_edge_type": fixture["edge_type"],
        "edge_color": "P0 multi edge",
        "kerf_mm": 5, "trim_margin_mm": 5,
        "optimization_time_limit_sec": 10, "board_rate_usd": 11,
        "cutting_cost_per_board_usd": 2,
        "pieces": [{"piece_type": "Regular", "width_cm": 42,
                    "length_cm": 81, "qty": 24, "extra_liner": 1,
                    "liner_reference_side": "edge_width_top",
                    "liner_offset_cm": 0, "liner_width_cm": 1.8}],
    }).insert(ignore_permissions=True)
    fixture["multi_order"] = {"name": order.name, "board": order.board_description}
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    from almdina_erp.almdina_erp.services.cutting_plan_command_service import recalculate_system_plan

    result = recalculate_system_plan(order)
    frappe.db.commit()
    plan = frappe.get_doc("Cutting Plan", result["cutting_plan"])
    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    evidence = {"order_name": order.name, "plan_name": plan.name,
                "revision": int(plan.revision or 0), "source": plan.source_type,
                "status": plan.status, "board": plan.board_description,
                "sheets": len(snapshot.get("sheets") or [])}
    if evidence["sheets"] < 2:
        raise AssertionError(f"Real persisted fixture did not generate several boards: {evidence}")
    (Path(os.environ["P0_EVIDENCE_DIR"]) / "multi-plan-fixture.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def prepare_saved_offcut_plan() -> dict[str, object]:
    """Import a genuine OFFCUT contour and classify its production owner."""
    from tempfile import NamedTemporaryFile

    import ezdxf
    from frappe.utils.file_manager import save_file

    from almdina_erp.almdina_erp.services.dxf_import_service import (
        OFFCUT_LAYER, SHEET_OUTLINE_LAYER,
    )
    from almdina_erp.almdina_erp.services.shop_floor_dxf_service import upload_production_dxf
    from almdina_erp.almdina_erp.services.offcut_service import set_offcut_execution_owner

    fixture_path = Path(os.environ["P0_FIXTURE_PATH"])
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    frappe.set_user("Administrator")
    order = frappe.get_doc({
        "doctype": "Door Cutting Order", "customer": fixture["customer"],
        "board_description": "P0 فضلة من المعمل", "board_length_cm": 244,
        "board_width_cm": 122, "default_edge_type": fixture["edge_type"],
        "edge_color": "P0 offcut edge",
        "kerf_mm": 5, "trim_margin_mm": 5,
        "optimization_time_limit_sec": 10, "board_rate_usd": 11,
        "cutting_cost_per_board_usd": 2, "current_department": "رسم",
        "pieces": [{"piece_type": "Regular", "width_cm": 42,
                    "length_cm": 81, "qty": 1}],
    }).insert(ignore_permissions=True)
    fixture["offcut_order"] = {"name": order.name, "board": order.board_description}
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    drawing = ezdxf.new("R2010")
    model = drawing.modelspace()
    for points, layer in (
        (((0, 0), (1220, 0), (1220, 2440), (0, 2440)), SHEET_OUTLINE_LAYER),
        (((10, 10), (430, 10), (430, 820), (10, 820)), OFFCUT_LAYER),
    ):
        for start, end in zip(points, (*points[1:], points[0])):
            model.add_line(start, end, dxfattribs={"layer": layer})
    with NamedTemporaryFile(suffix=".dxf") as staged:
        drawing.saveas(staged.name)
        raw = Path(staged.name).read_bytes()
    # The real upload command requires a private *unattached* staging File;
    # successful import reattaches it to the Cutting Plan for cleanup.
    file_doc = save_file(f"p0-offcut-{order.name}.dxf", raw,
                         None, None, is_private=1)
    fixture["offcut_staged_file"] = file_doc.name
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    frappe.db.commit()
    frappe.set_user(fixture["user"])
    uploaded = upload_production_dxf(order.name, file_doc.file_url)
    plan = frappe.get_doc("Cutting Plan", uploaded["cutting_plan"])
    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    offcut = [piece for sheet in snapshot.get("sheets") or []
              for piece in sheet.get("pieces") or []
              if piece.get("resource_kind") == "OFFCUT"]
    if len(offcut) != 1:
        raise AssertionError(f"Real DXF OFFCUT contour was not classified: {offcut}")
    set_offcut_execution_owner(plan.name, [{
        "piece_instance_id": offcut[0]["piece_instance_id"],
        "business_state": "FACTORY_FACTORY",
    }])
    frappe.db.commit()
    plan.reload()
    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    persisted_offcuts = [piece for sheet in snapshot.get("sheets") or []
                         for piece in sheet.get("pieces") or []
                         if piece.get("resource_kind") == "OFFCUT"]
    if len(persisted_offcuts) != 1:
        raise AssertionError(f"Saved OFFCUT identity changed: {persisted_offcuts}")
    owned_piece = persisted_offcuts[0]
    evidence = {"order_name": order.name, "plan_name": plan.name,
                "revision": int(plan.revision or 0), "source": plan.source_type,
                "status": plan.status, "board": plan.board_description,
                "sheets": len(snapshot.get("sheets") or []),
                "offcut_kind": owned_piece.get("resource_kind"),
                "offcut_source": owned_piece.get("offcut_source_party"),
                "offcut_execution": owned_piece.get("offcut_execution_party")}
    if (evidence["offcut_kind"], evidence["offcut_source"], evidence["offcut_execution"]) != (
        "OFFCUT", "FACTORY", "FACTORY"
    ):
        raise AssertionError(f"Saved OFFCUT classification differs: {evidence}")
    (Path(os.environ["P0_EVIDENCE_DIR"]) / "offcut-plan-fixture.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence
