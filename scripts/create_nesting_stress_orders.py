"""Create two large Draft nesting orders on the local site1.local bench.

Development data only. The script refuses every site other than site1.local,
does not approve a price or a cutting plan, and does not send mail. Running it
again reuses the same orders.

    cd /Users/macbook/frappe-v16/sites
    ../env/bin/python ../apps/almdina_erp/scripts/create_nesting_stress_orders.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path


SITE_NAME = "site1.local"
CUSTOMER_NAME = "عميل اختبار التعشيق TEST-NEST"
PREFERRED_EDGE = "قشاط 2سم عادي"
BOARD_LENGTH_CM = 244
BOARD_WIDTH_CM = 122
BOARD_DESCRIPTION = "لوح اختبار التعشيق 244×122"
KERF_MM = 3.0
TRIM_MM = 0.0
KERF_CM = KERF_MM / 10
MACHINE_TYPE = "CNC Router"
OPTIMIZATION_MODE = "auto_pro"
TIME_LIMIT_SEC = 15.0
POSITION_TOLERANCE_CM = 0.15

RATE_FIELDS = {
    "liner": "default_extra_liner_unit_price_usd",
    "back_groove": "default_extra_back_groove_unit_price_usd",
    "recessed_handle_cutout": "default_extra_recessed_handle_cutout_unit_price_usd",
    "double": "default_extra_double_unit_price_usd",
    "full_door_double": "default_extra_full_door_double_unit_price_usd",
}
ADDON_FIELDS = (
    "extra_liner",
    "liner_reference_side",
    "liner_offset_cm",
    "liner_width_cm",
    "liner_start_cm",
    "liner_length_cm",
    "liner_specs_json",
    "extra_back_groove",
    "back_groove_reference_side",
    "back_groove_offset_cm",
    "back_groove_width_cm",
    "back_groove_start_cm",
    "back_groove_length_cm",
    "extra_recessed_handle_cutout",
    "recessed_handle_reference_side",
    "recessed_handle_offset_cm",
    "recessed_handle_width_cm",
    "recessed_handle_start_cm",
    "recessed_handle_length_cm",
    "extra_double",
    "extra_double_reference_sides",
    "extra_full_door_double",
)


def _bench_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _polygon(width_cm: float, length_cm: float, points: list[list[float]], template: str) -> dict:
    return {
        "version": 1,
        "kind": "polygon",
        "units": "cm",
        "template": template,
        "blank_width_cm": width_cm,
        "blank_length_cm": length_cm,
        "points": points,
        "exact": True,
    }


def _special_definitions() -> list[dict[str, object]]:
    """Documented non-rectangular polygons. x is width and y is length."""

    return [
        {
            "key": "parallelogram",
            "length_cm": 50,
            "width_cm": 35,
            "template": "parallelogram",
            "points": [[0, 12], [25, 0], [35, 38], [10, 50]],
        },
        {
            "key": "crown",
            "length_cm": 45,
            "width_cm": 40,
            "template": "crown",
            "points": [[0, 18], [6, 8], [12, 0], [20, 10], [28, 0], [34, 8], [40, 18], [40, 45], [0, 45]],
        },
        {
            "key": "irregular",
            "length_cm": 40,
            "width_cm": 30,
            "template": "irregular_polygon",
            "points": [[0, 8], [10, 0], [20, 6], [30, 4], [24, 40], [12, 32], [4, 40]],
        },
        {
            "key": "parallelogram_2",
            "length_cm": 48,
            "width_cm": 32,
            "template": "parallelogram",
            "points": [[0, 14], [22, 0], [32, 34], [10, 48]],
        },
        {
            "key": "crown_2",
            "length_cm": 42,
            "width_cm": 36,
            "template": "crown",
            "points": [[0, 16], [6, 7], [12, 0], [18, 9], [24, 0], [30, 7], [36, 16], [36, 42], [0, 42]],
        },
        {
            "key": "irregular_2",
            "length_cm": 38,
            "width_cm": 28,
            "template": "irregular_polygon",
            "points": [[0, 9], [9, 0], [18, 5], [28, 3], [22, 38], [11, 30], [3, 38]],
        },
    ]


def _axis_aligned_rectangle(points: list[list[float]]) -> bool:
    if len(points) != 4:
        return False
    xs = {point[0] for point in points}
    ys = {point[1] for point in points}
    return len(xs) == 2 and len(ys) == 2


def _validated_specials() -> tuple[dict[str, dict], list[str]]:
    from almdina_erp.almdina_erp.services.special_shape_service import (
        validate_special_shape_geometry,
    )

    accepted: dict[str, dict] = {}
    notes: list[str] = []
    for item in _special_definitions():
        raw = _polygon(
            float(item["width_cm"]),
            float(item["length_cm"]),
            item["points"],  # type: ignore[arg-type]
            str(item["template"]),
        )
        try:
            normalized = validate_special_shape_geometry(
                raw,
                expected_width_cm=float(item["width_cm"]),
                expected_length_cm=float(item["length_cm"]),
            )
        except Exception as error:  # noqa: BLE001 - record one unsupported shape and continue
            notes.append(f"{item['key']}: {type(error).__name__}: {error}")
            continue
        if not normalized or _axis_aligned_rectangle(normalized["points"]):
            notes.append(f"{item['key']}: الناتج مستطيل، ولم يُستخدم.")
            continue
        accepted[str(item["key"])] = normalized
    notes.append(
        "القوس والدائرة غير مدعومين في عقد القص الحالي: kind يجب أن يكون polygon "
        "من قطع مستقيمة. لم تُنشأ درفة منحنية ولم تُستبدل بمستطيل."
    )
    return accepted, notes


def _corner(
    piece_type: str,
    length_cm: float,
    width_cm: float,
    cut_length_cm: float,
    cut_width_cm: float,
    qty: int,
    allow_rotation: int,
) -> dict[str, object]:
    return {
        "piece_type": piece_type,
        "length_cm": length_cm,
        "width_cm": width_cm,
        "qty": qty,
        "allow_rotation": allow_rotation,
        "clipped_corner_position": "Top Right",
        "clipped_corner_length_cm": cut_length_cm,
        "clipped_corner_width_cm": cut_width_cm,
    }


def _regular(length_cm: float, width_cm: float, qty: int, allow_rotation: int) -> dict[str, object]:
    return {
        "piece_type": "Regular",
        "length_cm": length_cm,
        "width_cm": width_cm,
        "qty": qty,
        "allow_rotation": allow_rotation,
    }


def _glass(length_cm: float, width_cm: float, margin_mm: float) -> dict[str, object]:
    return {
        "piece_type": "Glass",
        "length_cm": length_cm,
        "width_cm": width_cm,
        "qty": 1,
        "allow_rotation": 0,
        "glass_margin_mm": margin_mm,
    }


def _special_row(geometry: dict) -> dict[str, object]:
    return {
        "piece_type": "Special",
        "length_cm": geometry["blank_length_cm"],
        "width_cm": geometry["blank_width_cm"],
        "qty": 1,
        "allow_rotation": 0,
        "special_shape_geometry_json": json.dumps(geometry, separators=(",", ":"), ensure_ascii=True),
        "notes": f"special:{geometry['template']}",
    }


def _two_liners() -> dict[str, object]:
    from almdina_erp.almdina_erp.domain.orders.liner_specs import (
        DoorLinerSet,
        DoorLinerSpec,
        door_liner_fields,
    )

    payload = DoorLinerSet(
        enabled=True,
        width_cm=1.5,
        liners=(
            DoorLinerSpec("liner_1", "edge_long_left", 1.0, 0.0, 8.0),
            DoorLinerSpec("liner_2", "edge_width_top", 1.0, 0.0, 6.0),
        ),
    )
    return door_liner_fields(payload)


def _groove() -> dict[str, object]:
    return {
        "extra_back_groove": 1,
        "back_groove_reference_side": "edge_long_right",
        "back_groove_offset_cm": 1.2,
        "back_groove_width_cm": 0.8,
        "back_groove_start_cm": 0,
        "back_groove_length_cm": 8,
    }


def _handle() -> dict[str, object]:
    return {
        "extra_recessed_handle_cutout": 1,
        "recessed_handle_reference_side": "edge_width_bottom",
        "recessed_handle_offset_cm": 1,
        "recessed_handle_width_cm": 2,
        "recessed_handle_start_cm": 1,
        "recessed_handle_length_cm": 6,
    }


def _double_edge() -> dict[str, object]:
    from almdina_erp.almdina_erp.domain.orders.extra_addons import serialize_extra_double_sides

    return {
        "extra_double": 1,
        "extra_double_reference_sides": serialize_extra_double_sides(
            ("edge_long_left", "edge_width_top")
        ),
    }


def _full_double() -> dict[str, object]:
    return {"extra_full_door_double": 1}


def _with_addon(row: dict[str, object], addon: dict[str, object] | None) -> list[dict[str, object]]:
    qty = int(row["qty"])
    if addon is None or qty < 1:
        return [row]
    marked = dict(row)
    marked["qty"] = 1
    marked.update(addon)
    if qty == 1:
        return [marked]
    plain = dict(row)
    plain["qty"] = qty - 1
    return [marked, plain]


def _rates() -> dict[str, float]:
    import frappe

    settings = frappe.get_cached_doc("Almdina ERP Settings")
    return {code: float(getattr(settings, field, 0) or 0) for code, field in RATE_FIELDS.items()}


def _addon_for(code: str, rates: dict[str, float], skipped: list[str]) -> dict[str, object] | None:
    if rates.get(code, 0) <= 0:
        skipped.append(f"{code}: سعر الإضافة غير مضبوط في الإعدادات، ولم تُضف.")
        return None
    builders = {
        "liner": _two_liners,
        "back_groove": _groove,
        "recessed_handle_cutout": _handle,
        "double": _double_edge,
        "full_door_double": _full_double,
    }
    return builders[code]()


def _cases(specials: dict[str, dict], rates: dict[str, float]) -> tuple[list[dict[str, object]], list[str]]:
    skipped: list[str] = []
    liner = _addon_for("liner", rates, skipped)
    groove = _addon_for("back_groove", rates, skipped)
    handle = _addon_for("recessed_handle_cutout", rates, skipped)
    double = _addon_for("double", rates, skipped)
    full = _addon_for("full_door_double", rates, skipped)
    skipped.append("Special بلا أضلاع جدول، لذلك لم تُوضع عليه إضافات تشغيل.")

    def specials_for(*keys: str) -> list[dict[str, object]]:
        rows = []
        for key in keys:
            geometry = specials.get(key)
            if geometry is None:
                skipped.append(f"{key}: لم تُنشأ لأن التحقق الهندسي رفضها.")
                continue
            rows.append(_special_row(geometry))
        return rows

    first_rows: list[dict[str, object]] = [
        _corner("L-Shaped Corner", 55, 45, 20, 15, 1, 1),
        _corner("L-Shaped Corner", 48, 48, 19, 19, 2, 1),
        _corner("L-Shaped Corner", 46, 46, 16, 16, 3, 1),
        _corner("L-Shaped Corner", 40, 40, 15, 15, 4, 1),
        _corner("L-Shaped Corner", 34, 34, 12, 12, 6, 1),
        _corner("Clipped Corner", 48, 42, 14, 12, 1, 1),
        _corner("Clipped Corner", 38, 38, 12, 12, 2, 1),
        _corner("Clipped Corner", 32, 32, 10, 10, 4, 1),
        *_with_addon(_regular(20, 18, 6, 1), liner),
        _regular(12, 12, 4, 0),
        *_with_addon(_regular(12, 12, 1, 0), groove),
        *_with_addon(_regular(15, 10, 4, 1), handle),
        *_with_addon(_regular(22, 18, 4, 1), double),
        *_with_addon(_regular(30, 25, 4, 0), full),
        _regular(38, 20, 4, 1),
        _regular(60, 25, 3, 1),
        _glass(90, 70, 100),
        _glass(80, 60, 80),
        *specials_for("parallelogram", "crown", "irregular"),
    ]
    second_rows: list[dict[str, object]] = [
        _corner("L-Shaped Corner", 50, 50, 20, 20, 2, 0),
        _corner("L-Shaped Corner", 45, 45, 15, 15, 3, 0),
        _corner("L-Shaped Corner", 40, 40, 15, 15, 4, 1),
        _corner("L-Shaped Corner", 36, 36, 12, 12, 5, 1),
        _corner("L-Shaped Corner", 30, 30, 10, 10, 8, 1),
        _corner("Clipped Corner", 55, 45, 16, 10, 1, 1),
        _corner("Clipped Corner", 44, 44, 14, 14, 2, 0),
        _corner("Clipped Corner", 42, 42, 12, 12, 3, 1),
        _corner("Clipped Corner", 38, 38, 12, 12, 4, 1),
        _corner("Clipped Corner", 29, 29, 9, 9, 7, 1),
        _regular(10, 10, 7, 0),
        *_with_addon(_regular(15, 12, 6, 1), liner),
        *_with_addon(_regular(24, 18, 5, 0), groove),
        *_with_addon(_regular(35, 20, 4, 1), handle),
        *_with_addon(_regular(48, 30, 4, 0), double),
        *_with_addon(_regular(70, 25, 4, 1), full),
        _glass(100, 80, 100),
        _glass(90, 70, 80),
        *specials_for("parallelogram_2", "crown_2", "irregular_2"),
    ]
    cases = [
        {
            "code": "TEST-NEST-STRESS-01",
            "title": "اختبار تعشيق كبير — الانعكاس ممنوع",
            "mirror": 0,
            "rows": first_rows,
        },
        {
            "code": "TEST-NEST-STRESS-02",
            "title": "اختبار تعشيق كبير — الانعكاس مسموح",
            "mirror": 1,
            "rows": second_rows,
        },
    ]
    return cases, skipped


def _refuse_unless_local_site() -> None:
    import frappe

    if frappe.local.site != SITE_NAME:
        raise SystemExit(f"مرفوض: الموقع {frappe.local.site} ليس {SITE_NAME}.")
    host = str(frappe.conf.get("host_name") or "")
    lowered = host.lower()
    if "almdina-2" in lowered or "production" in lowered:
        raise SystemExit(f"مرفوض: host_name يشير إلى بيئة غير محلية ({host}).")
    db_host = str(frappe.conf.get("db_host") or "127.0.0.1")
    if db_host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit(f"مرفوض: قاعدة البيانات ليست محلية ({db_host}).")
    if not frappe.conf.get("allow_tests"):
        raise SystemExit("مرفوض: allow_tests غير مفعّل على هذا الموقع.")


def _customer() -> str:
    import frappe

    existing = frappe.get_all(
        "Customer",
        filters={"customer_name": CUSTOMER_NAME},
        pluck="name",
        limit=1,
    )
    if existing:
        customer = frappe.get_doc("Customer", existing[0])
        if customer.get("email_id") or customer.get("mobile_no"):
            raise SystemExit("مرفوض: عميل الاختبار يحمل وسيلة اتصال.")
        return str(customer.name)
    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": CUSTOMER_NAME,
            "customer_type": "Individual",
            "customer_group": "Individual",
            "territory": "Rest Of The World",
        }
    )
    customer.flags.ignore_permissions = True
    customer.insert(ignore_permissions=True)
    if customer.get("email_id") or customer.get("mobile_no"):
        raise SystemExit("مرفوض: العميل التجريبي حصل على وسيلة اتصال.")
    return str(customer.name)


def _edge_type() -> str:
    import frappe

    preferred = frappe.db.get_value(
        "Edge Banding Type",
        PREFERRED_EDGE,
        ["name", "disabled"],
        as_dict=True,
    )
    if preferred and not int(preferred.disabled or 0):
        return str(preferred.name)
    fallback = frappe.get_all("Edge Banding Type", filters={"disabled": 0}, pluck="name", limit=1)
    if not fallback:
        raise SystemExit("لا يوجد نوع قشاط صالح على موقع التطوير.")
    return str(fallback[0])


def _existing_orders() -> dict[str, str]:
    import frappe

    rows = frappe.get_all(
        "Door Cutting Order",
        filters={"order_notes": ["like", "TEST-NEST-STRESS-%"]},
        fields=["name", "order_notes"],
        limit=20,
    )
    found: dict[str, str] = {}
    for row in rows:
        code = str(row.order_notes or "").splitlines()[0].strip()
        found.setdefault(code, str(row.name))
    return found


def _copies(rows: list[dict[str, object]]) -> int:
    return sum(int(row["qty"]) for row in rows)


def _strip_addons(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    cleaned = []
    for row in rows:
        item = {key: value for key, value in row.items() if key not in ADDON_FIELDS}
        cleaned.append(item)
    return cleaned


def _insert_order(case: dict[str, object], customer: str, edge_type: str, extra_note: str) -> str:
    import frappe

    notes = f"{case['code']}\n{case['title']}"
    if extra_note:
        notes = f"{notes}\n{extra_note}"
    order = frappe.get_doc(
        {
            "doctype": "Door Cutting Order",
            "customer": customer,
            "order_notes": notes,
            "order_cutting_machine": "CNC",
            "board_description": BOARD_DESCRIPTION,
            "board_length_cm": BOARD_LENGTH_CM,
            "board_width_cm": BOARD_WIDTH_CM,
            "default_edge_type": edge_type,
            "edge_color": "اختبار",
            "allow_piece_mirroring": case["mirror"],
            "pieces": case["rows"],
        }
    )
    order.flags.ignore_permissions = True
    order.insert(ignore_permissions=True)
    return str(order.name)


def _verify_order(name: str, case: dict[str, object]) -> list[str]:
    import frappe

    order = frappe.get_doc("Door Cutting Order", name)
    problems: list[str] = []
    if order.status != "Draft" or int(order.docstatus or 0) != 0:
        problems.append("الطلب ليس Draft")
    if order.approved_plan or order.price_approval_status != "Unapproved":
        problems.append("الطلب معتمد سعرياً أو له خطة معتمدة")
    if int(order.allow_piece_mirroring or 0) != int(case["mirror"]):
        problems.append("إعداد الانعكاس مختلف")
    saved = list(order.pieces or [])
    expected = case["rows"]
    if sum(int(row.qty or 0) for row in saved) != _copies(expected):  # type: ignore[arg-type]
        problems.append(
            f"النسخ {sum(int(row.qty or 0) for row in saved)} بدل {_copies(expected)}"  # type: ignore[arg-type]
        )
    if len(saved) != len(expected):  # type: ignore[arg-type]
        problems.append(f"عدد الأسطر {len(saved)} بدل {len(expected)}")  # type: ignore[arg-type]
        return problems
    for row, source in zip(saved, expected, strict=True):  # type: ignore[arg-type]
        if str(row.piece_type or "") != str(source["piece_type"]):
            problems.append(f"النوع مختلف في سطر {row.idx}")
        for field in ("qty", "allow_rotation", "length_cm", "width_cm"):
            if abs(float(row.get(field) or 0) - float(source[field])) > 0.001:
                problems.append(f"{field} مختلف في سطر {row.idx}")
        if source["piece_type"] in {"L-Shaped Corner", "Clipped Corner"}:
            if row.clipped_corner_position != "Top Right":
                problems.append(f"موضع الزاوية مختلف في سطر {row.idx}")
            if float(row.clipped_corner_length_cm or 0) != float(source["clipped_corner_length_cm"]):
                problems.append(f"طول التجويف مختلف في سطر {row.idx}")
            if float(row.clipped_corner_width_cm or 0) != float(source["clipped_corner_width_cm"]):
                problems.append(f"عرض التجويف مختلف في سطر {row.idx}")
        if source["piece_type"] == "Glass" and float(row.glass_margin_mm or 0) != float(source["glass_margin_mm"]):
            problems.append(f"هامش البلور مختلف في سطر {row.idx}")
        if source["piece_type"] == "Special":
            stored = str(row.special_shape_geometry_json or "")
            if stored != str(source["special_shape_geometry_json"]):
                problems.append(f"هندسة Special تغيرت في سطر {row.idx}")
            payload = json.loads(stored) if stored else {}
            points = payload.get("points") or []
            if len(points) < 4 or _axis_aligned_rectangle(points):
                problems.append(f"Special في سطر {row.idx} ليست مضلعاً غير مستطيل")
    visible = frappe.get_list("Door Cutting Order", filters={"name": name}, pluck="name", limit=1)
    if not visible:
        problems.append("الطلب لا يظهر في استعلام القائمة")
    return problems


def _snapshot(plan: object) -> dict:
    raw = getattr(plan, "snapshot_json", None) or ""
    if not raw:
        return {}
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else {}


def _calculate(name: str) -> tuple[object, dict, float, bool]:
    import frappe

    from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
        recalculate_system_plan,
    )

    order = frappe.get_doc("Door Cutting Order", name)
    existing = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": name,
            "source_type": "System",
            "status": "Draft",
            "validation_status": "Valid",
            "machine_type": MACHINE_TYPE,
            "optimization_mode": OPTIMIZATION_MODE,
            "kerf_mm": KERF_MM,
            "trim_margin_mm": TRIM_MM,
        },
        pluck="name",
        order_by="modified desc",
        limit=1,
    )
    started = time.monotonic()
    reused = bool(existing)
    if not reused:
        recalculate_system_plan(
            order,
            {
                "packing_mode": OPTIMIZATION_MODE,
                "cutting_machine_type": MACHINE_TYPE,
                "kerf_mm": KERF_MM,
                "trim_margin_mm": TRIM_MM,
                "optimization_time_limit_sec": TIME_LIMIT_SEC,
            },
        )
        existing = frappe.get_all(
            "Cutting Plan",
            filters={"door_cutting_order": name, "source_type": "System", "status": "Draft"},
            pluck="name",
            order_by="modified desc",
            limit=1,
        )
    elapsed = time.monotonic() - started
    if not existing:
        raise RuntimeError("لم تُنشأ خطة مسودة")
    plan = frappe.get_doc("Cutting Plan", existing[0])
    order.reload()
    if order.approved_plan or plan.status != "Draft" or order.price_approval_status != "Unapproved":
        raise RuntimeError("الحساب غيّر حالة الاعتماد")
    return plan, _snapshot(plan), elapsed, reused


def _near(left: float, right: float) -> bool:
    return abs(left - right) <= POSITION_TOLERANCE_CM


def _same_sheet(pieces: list[dict]) -> bool:
    return len({piece.get("_sheet_no") for piece in pieces}) == 1


def _facing(piece: dict) -> str:
    from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _recorded_facing

    return _recorded_facing(piece)


def _is_quad(pieces: dict[str, dict]) -> bool:
    required = ("Bottom Right", "Bottom Left", "Top Right", "Top Left")
    if any(name not in pieces for name in required) or not _same_sheet(list(pieces.values())):
        return False
    br = pieces["Bottom Right"]
    bl = pieces["Bottom Left"]
    tr = pieces["Top Right"]
    tl = pieces["Top Left"]
    step_x = float(br["w"]) + KERF_CM
    step_y = float(br["h"]) + KERF_CM
    return (
        _near(float(bl["x"]), float(br["x"]) + step_x)
        and _near(float(bl["y"]), float(br["y"]))
        and _near(float(tr["x"]), float(br["x"]))
        and _near(float(tr["y"]), float(br["y"]) + step_y)
        and _near(float(tl["x"]), float(br["x"]) + step_x)
        and _near(float(tl["y"]), float(br["y"]) + step_y)
    )


def _is_pair(first: dict, second: dict) -> bool:
    if not _same_sheet([first, second]):
        return False
    facings = {_facing(first), _facing(second)}
    horizontal = {
        frozenset({"Bottom Right", "Bottom Left"}),
        frozenset({"Top Right", "Top Left"}),
    }
    vertical = {
        frozenset({"Bottom Right", "Top Right"}),
        frozenset({"Bottom Left", "Top Left"}),
    }
    left, right = sorted((first, second), key=lambda piece: float(piece["x"]))
    lower, upper = sorted((first, second), key=lambda piece: float(piece["y"]))
    if facings in horizontal:
        return _near(float(right["x"]), float(left["x"]) + float(left["w"]) + KERF_CM) and _near(
            float(left["y"]), float(right["y"])
        )
    if facings in vertical:
        return _near(float(upper["y"]), float(lower["y"]) + float(lower["h"]) + KERF_CM) and _near(
            float(lower["x"]), float(upper["x"])
        )
    return False


def _take_formations(members: list[dict]) -> tuple[list[list[dict]], list[list[dict]], list[dict]]:
    remaining = list(members)
    quads: list[list[dict]] = []
    while True:
        found: list[dict] | None = None
        by_facing: dict[str, list[dict]] = {}
        for piece in remaining:
            by_facing.setdefault(_facing(piece), []).append(piece)
        for br in by_facing.get("Bottom Right", []):
            for bl in by_facing.get("Bottom Left", []):
                for tr in by_facing.get("Top Right", []):
                    for tl in by_facing.get("Top Left", []):
                        chosen = [br, bl, tr, tl]
                        if len({id(piece) for piece in chosen}) < 4:
                            continue
                        if _is_quad(
                            {
                                "Bottom Right": br,
                                "Bottom Left": bl,
                                "Top Right": tr,
                                "Top Left": tl,
                            }
                        ):
                            found = chosen
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if found is None:
            break
        quads.append(found)
        used = {id(piece) for piece in found}
        remaining = [piece for piece in remaining if id(piece) not in used]

    pairs: list[list[dict]] = []
    used_pairs: set[int] = set()
    for index, first in enumerate(remaining):
        if id(first) in used_pairs:
            continue
        for second in remaining[index + 1 :]:
            if id(second) in used_pairs:
                continue
            if _is_pair(first, second):
                pairs.append([first, second])
                used_pairs.update((id(first), id(second)))
                break
    singles = [piece for piece in remaining if id(piece) not in used_pairs]
    return quads, pairs, singles


def _expected_counts(count: int) -> dict[str, int]:
    quads = count // 4
    rest = count % 4
    return {
        "quads": quads,
        "pairs": 1 if rest in {2, 3} else 0,
        "singles": 1 if rest in {1, 3} else 0,
    }


def _piece_ref(piece: dict) -> str:
    return f"{piece.get('label')}#{piece.get('id')}/لوح{piece.get('_sheet_no')}/{_facing(piece)}"


def _center_in_notch(guest: dict, host: dict) -> bool:
    from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon
    from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm

    outline = material_outline_cm(host)
    if not outline:
        return False
    center = (float(guest["x"]) + float(guest["w"]) / 2, float(guest["y"]) + float(guest["h"]) / 2)
    inside_box = (
        float(host["x"]) <= center[0] <= float(host["x"]) + float(host["w"])
        and float(host["y"]) <= center[1] <= float(host["y"]) + float(host["h"])
    )
    return inside_box and not point_in_polygon(center, outline)


def _analyze(order: object, snapshot: dict) -> dict[str, object]:
    from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
    from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
    from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
    from almdina_erp.almdina_erp.domain.cutting.shape_aware_nesting import _inward_score

    expanded = expand_piece_groups([row.as_dict() for row in order.pieces])  # type: ignore[attr-defined]
    by_id = {int(piece["id"]): piece for piece in expanded}
    placed: list[dict] = []
    for sheet in snapshot.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            if not isinstance(piece, dict):
                continue
            row = dict(piece)
            row["_sheet_no"] = sheet.get("sheet_no")
            row["_board_w"] = float(sheet.get("w") or BOARD_WIDTH_CM)
            row["_board_h"] = float(sheet.get("h") or BOARD_LENGTH_CM)
            placed.append(row)

    groups: dict[tuple, list[dict]] = {}
    for piece in placed:
        if piece.get("piece_type") not in {"L-Shaped Corner", "Clipped Corner"}:
            continue
        key = (
            piece.get("piece_type"),
            round(float(piece.get("original_w") or piece.get("w") or 0), 3),
            round(float(piece.get("original_h") or piece.get("h") or 0), 3),
            round(float(piece.get("clipped_corner_width_cm") or 0), 3),
            round(float(piece.get("clipped_corner_length_cm") or 0), 3),
        )
        groups.setdefault(key, []).append(piece)

    formations = []
    nest_ids: set[int] = set()
    for key, members in groups.items():
        quads, pairs, singles = _take_formations(members)
        expected = _expected_counts(len(members))
        actual = {"quads": len(quads), "pairs": len(pairs), "singles": len(singles)}
        single_notes = []
        for piece in singles:
            score = _inward_score(piece, float(piece["_board_w"]), float(piece["_board_h"]))
            single_notes.append(
                {
                    "id": piece.get("id"),
                    "label": piece.get("label"),
                    "sheet": piece.get("_sheet_no"),
                    "facing": _facing(piece),
                    "cavity_inward": bool(score is not None and score > 0.05),
                }
            )
        for formation in quads + pairs:
            nest_ids.update(int(piece["id"]) for piece in formation)
        kind = "L" if key[0] == "L-Shaped Corner" else "كسر"
        formations.append(
            {
                "kind": kind,
                "width_cm": key[1],
                "length_cm": key[2],
                "cut_width_cm": key[3],
                "cut_length_cm": key[4],
                "count": len(members),
                "expected": expected,
                "actual": actual,
                "matched": actual == expected,
                "quad_ids": [[_piece_ref(piece) for piece in quad] for quad in quads],
                "pair_ids": [[_piece_ref(piece) for piece in pair] for pair in pairs],
                "singles": single_notes,
            }
        )

    void_guests = []
    hosts = [piece for piece in placed if int(piece.get("id") or 0) in nest_ids]
    for guest in placed:
        guest_id = int(guest.get("id") or 0)
        if guest_id in nest_ids or guest.get("glass_host_piece_id") not in (None, ""):
            continue
        holders = [
            int(host["id"])
            for host in hosts
            if host.get("_sheet_no") == guest.get("_sheet_no") and _center_in_notch(guest, host)
        ]
        if holders:
            void_guests.append(
                {
                    "id": guest_id,
                    "label": guest.get("label"),
                    "type": guest.get("piece_type"),
                    "sheet": guest.get("_sheet_no"),
                    "host_ids": holders,
                }
            )

    glass_guests = [
        {
            "id": piece.get("id"),
            "label": piece.get("label"),
            "type": piece.get("piece_type"),
            "sheet": piece.get("_sheet_no"),
            "host_id": piece.get("glass_host_piece_id"),
            "size": f"{piece.get('w')}×{piece.get('h')}",
        }
        for piece in placed
        if piece.get("glass_host_piece_id") not in (None, "")
    ]
    specials = [piece for piece in placed if piece.get("piece_type") == "Special"]
    special_outlines = []
    for piece in specials:
        outline = material_outline_cm(piece)
        source = by_id.get(int(piece.get("id") or 0), {})
        raw = source.get("special_shape_geometry_json") or ""
        payload = json.loads(raw) if raw else {}
        special_outlines.append(
            {
                "id": piece.get("id"),
                "label": piece.get("label"),
                "template": payload.get("template"),
                "source_points": len(payload.get("points") or []),
                "placed_points": len(outline or ()),
                "outline_kept": bool(outline) and len(outline or ()) == len(payload.get("points") or []),
            }
        )
    rotations = [
        piece.get("id")
        for piece in placed
        if int(piece.get("corner_rotation_quarter_turns") or 0)
        or bool(piece.get("rotated"))
        or float(piece.get("placement_rotation_deg") or 0)
    ]
    mirrors = [
        piece.get("id")
        for piece in placed
        if piece.get("mirrored") or piece.get("corner_mirrored") or piece.get("placement_mirrored")
    ]
    board_w = float((snapshot.get("sheets") or [{}])[0].get("w") or BOARD_WIDTH_CM)
    board_h = float((snapshot.get("sheets") or [{}])[0].get("h") or BOARD_LENGTH_CM)
    geometry_errors = validate_plan(snapshot, expanded, board_w, board_h, kerf_cm=KERF_CM)
    return {
        "placed": len(placed),
        "boards": len(snapshot.get("sheets") or []),
        "unplaced": len(snapshot.get("unplaced") or []),
        "formations": formations,
        "void_guests": void_guests,
        "glass_guests": glass_guests,
        "specials": special_outlines,
        "rotation_ids": rotations,
        "mirror_ids": mirrors,
        "geometry_errors": geometry_errors,
        "search_elapsed_sec": snapshot.get("search_elapsed_sec"),
    }


def _dxf_roundtrip(snapshot: dict) -> dict[str, object]:
    import ezdxf

    from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
    from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry

    outlines = []
    missing = []
    for sheet in snapshot.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            outline = material_outline_cm(piece)
            if not outline or len(outline) < 3:
                missing.append(piece.get("id"))
                continue
            outlines.append([(point[0] * 10, point[1] * 10) for point in outline])
    document = ezdxf.new("R2010")
    for layer in ("GEOMETRY", "CUT_PATH", "TEXT"):
        document.layers.add(layer)
    modelspace = document.modelspace()
    for ring in outlines:
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "GEOMETRY"}, close=True)
        modelspace.add_lwpolyline(ring, dxfattribs={"layer": "CUT_PATH"}, close=True)
    path = ""
    try:
        handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        path = handle.name
        handle.close()
        document.saveas(path)
        loaded = read_dxf_geometry(path, relevant_layers={"GEOMETRY", "CUT_PATH"})
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
    geometry_ids = {
        segment["entity_id"]
        for segment in loaded["segments"]
        if segment["layer"] == "GEOMETRY"
    }
    cut_ids = {
        segment["entity_id"]
        for segment in loaded["segments"]
        if segment["layer"] == "CUT_PATH"
    }
    return {
        "exported_outlines": len(outlines),
        "imported_geometry": len(geometry_ids),
        "imported_cut_path": len(cut_ids),
        "missing_outlines": missing,
        "match": len(geometry_ids) == len(outlines) and len(cut_ids) == len(outlines) and not missing,
    }


def _report_order(
    case: dict[str, object],
    name: str,
    created: bool,
    addon_error: str,
    plan: object,
    analysis: dict[str, object],
    elapsed: float,
    reused: bool,
    dxf: dict[str, object],
) -> dict[str, object]:
    return {
        "code": case["code"],
        "order": name,
        "created": created,
        "pieces": _copies(case["rows"]),  # type: ignore[arg-type]
        "placed": analysis["placed"],
        "boards": getattr(plan, "required_boards", analysis["boards"]),
        "plan": getattr(plan, "name", ""),
        "validation_status": getattr(plan, "validation_status", ""),
        "validation_errors": str(getattr(plan, "validation_errors", "") or ""),
        "geometry_errors": analysis["geometry_errors"],
        "formations": analysis["formations"],
        "void_guests": analysis["void_guests"],
        "glass_guests": analysis["glass_guests"],
        "specials": analysis["specials"],
        "rotation_count": len(analysis["rotation_ids"]),  # type: ignore[arg-type]
        "mirror_count": len(analysis["mirror_ids"]),  # type: ignore[arg-type]
        "mirror_ids": analysis["mirror_ids"],
        "search_elapsed_sec": analysis["search_elapsed_sec"],
        "wall_seconds": round(elapsed, 3),
        "plan_reused": reused,
        "addon_error": addon_error,
        "dxf": dxf,
        "draft": True,
        "price_unapproved": True,
    }


def main() -> None:
    sites = _bench_root() / "sites"
    os.chdir(sites)
    import frappe

    frappe.init(site=SITE_NAME, sites_path=str(sites))
    frappe.connect()
    try:
        _refuse_unless_local_site()
        frappe.set_user("Administrator")
        frappe.flags.mute_emails = True
        frappe.flags.mute_messages = True
        specials, geometry_notes = _validated_specials()
        rates = _rates()
        cases, skipped = _cases(specials, rates)
        print("GEOMETRY", flush=True)
        for line in geometry_notes + skipped:
            print(line, flush=True)
        print(f"rates={ {key: value for key, value in rates.items()} }", flush=True)
        customer = _customer()
        edge_type = _edge_type()
        existing = _existing_orders()
        report = []
        for case in cases:
            code = str(case["code"])
            print(f"start {code} copies={_copies(case['rows'])}", flush=True)  # type: ignore[arg-type]
            created = False
            addon_error = ""
            name = existing.get(code, "")
            try:
                if not name:
                    try:
                        name = _insert_order(case, customer, edge_type, "")
                    except Exception as error:  # noqa: BLE001 - keep the order when only an add-on is rejected
                        frappe.db.rollback()
                        addon_error = f"{type(error).__name__}: {error}"[:500]
                        print(f"addon rejected: {addon_error}", flush=True)
                        case = dict(case)
                        case["rows"] = _strip_addons(case["rows"])  # type: ignore[arg-type]
                        name = _insert_order(case, customer, edge_type, f"إضافات أُزيلت: {addon_error}")
                    created = True
                    frappe.db.commit()
                problems = _verify_order(name, case)
                if problems:
                    raise RuntimeError("فشل التحقق: " + "؛ ".join(problems))
                plan, snapshot, elapsed, reused = _calculate(name)
                frappe.db.commit()
                order = frappe.get_doc("Door Cutting Order", name)
                analysis = _analyze(order, snapshot)
                dxf = _dxf_roundtrip(snapshot)
                item = _report_order(case, name, created, addon_error, plan, analysis, elapsed, reused, dxf)
            except Exception as error:  # noqa: BLE001 - report one order without losing the other
                frappe.db.rollback()
                print(traceback.format_exc(), flush=True)
                item = {
                    "code": code,
                    "order": name,
                    "created": created,
                    "error": f"{type(error).__name__}: {error}",
                    "addon_error": addon_error,
                }
            report.append(item)
            print(json.dumps({"code": code, "order": item.get("order"), "error": item.get("error", "")}, ensure_ascii=False), flush=True)
        print("REPORT")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        frappe.destroy()


if __name__ == "__main__":
    sys.exit(main())
