"""Create ten Draft nesting orders on the local site1.local bench.

Development data only. The script refuses every site other than site1.local,
does not approve a price or a cutting plan, and does not send mail.

Run from the bench::

    cd /Users/macbook/frappe-v16/sites
    ../env/bin/python ../apps/almdina_erp/scripts/create_nesting_test_orders.py
"""

from __future__ import annotations

import json
import os
import sys
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
MACHINE_TYPE = "CNC Router"
OPTIMIZATION_MODE = "auto_pro"
TIME_LIMIT_SEC = 10.0
GLASS_MARGIN_MM = 100.0  # 10 cm, stored in the millimetre field


def _corner(
    piece_type: str,
    length_cm: float,
    width_cm: float,
    cut_width_cm: float,
    cut_length_cm: float,
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
        "clipped_corner_width_cm": cut_width_cm,
        "clipped_corner_length_cm": cut_length_cm,
    }


def _regular(
    length_cm: float,
    width_cm: float,
    qty: int,
    allow_rotation: int = 0,
) -> dict[str, object]:
    return {
        "piece_type": "Regular",
        "length_cm": length_cm,
        "width_cm": width_cm,
        "qty": qty,
        "allow_rotation": allow_rotation,
    }


CASES: list[dict[str, object]] = [
    {
        "code": "TEST-NEST-01",
        "title": "درفة L واحدة — توجيه التجويف للداخل",
        "mirror": 0,
        "rows": [
            _corner("L-Shaped Corner", 50, 50, 20, 20, 1, 1),
            _regular(12, 12, 1),
        ],
    },
    {
        "code": "TEST-NEST-02",
        "title": "درفتان L مع دوران 180 دون انعكاس",
        "mirror": 0,
        "rows": [
            _corner("L-Shaped Corner", 50, 50, 20, 20, 2, 1),
            _regular(12, 12, 1),
        ],
    },
    {
        "code": "TEST-NEST-03",
        "title": "درفتان L مع انعكاس ودون دوران",
        "mirror": 1,
        "rows": [
            _corner("L-Shaped Corner", 50, 50, 20, 20, 2, 0),
            _regular(12, 12, 1),
        ],
    },
    {
        "code": "TEST-NEST-04",
        "title": "درفتان L دون دوران ودون انعكاس",
        "mirror": 0,
        "rows": [
            _corner("L-Shaped Corner", 50, 50, 20, 20, 2, 0),
        ],
    },
    {
        "code": "TEST-NEST-05",
        "title": "ثلاث درفات L — زوج ودرفة منفردة",
        "mirror": 0,
        "rows": [
            _corner("L-Shaped Corner", 45, 45, 15, 15, 3, 1),
            _regular(10, 10, 1),
        ],
    },
    {
        "code": "TEST-NEST-06",
        "title": "أربع درفات L وتعشيق رباعي",
        "mirror": 1,
        "rows": [
            _corner("L-Shaped Corner", 40, 40, 15, 15, 4, 1),
            _regular(12, 12, 1),
        ],
    },
    {
        "code": "TEST-NEST-07",
        "title": "أربع L متطابقة ودرفة L خامسة مختلفة",
        "mirror": 1,
        "rows": [
            _corner("L-Shaped Corner", 40, 40, 15, 15, 4, 1),
            _corner("L-Shaped Corner", 60, 50, 20, 15, 1, 1),
        ],
    },
    {
        "code": "TEST-NEST-08",
        "title": "ست درفات L متطابقة",
        "mirror": 1,
        "rows": [
            _corner("L-Shaped Corner", 40, 40, 15, 15, 6, 1),
            _regular(12, 12, 1),
        ],
    },
    {
        "code": "TEST-NEST-09",
        "title": "أربع زوايا كسر ودرفة داخلية",
        "mirror": 1,
        "rows": [
            _corner("Clipped Corner", 45, 45, 15, 15, 4, 1),
            _regular(10, 10, 1, 1),
        ],
    },
    {
        "code": "TEST-NEST-10",
        "title": "استغلال فتحة البلور",
        "mirror": 1,
        "rows": [
            {
                "piece_type": "Glass",
                "length_cm": 100,
                "width_cm": 80,
                "qty": 1,
                "allow_rotation": 0,
                "glass_margin_mm": GLASS_MARGIN_MM,
            },
            _regular(25, 25, 1),
            _regular(20, 20, 1),
            _corner("L-Shaped Corner", 20, 20, 8, 8, 1, 1),
        ],
    },
]


def _bench_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _geometry_review() -> list[str]:
    """Confirm the requested sizes can express each scenario. Sizes stay unchanged."""

    from almdina_erp.almdina_erp.domain.orders.piece_policy import validate_glass_opening

    kerf_cm = KERF_MM / 10
    notes = [
        "لم تُغيّر مقاسات الدرفات. هامش البلور 10 سم يُحفظ في الحقل بالمليمتر: 100 مم.",
    ]
    single_void = 20 - (2 * kerf_cm)
    notes.append(
        f"TEST-NEST-01: فراغ التجويف بعد Kerf من الجهتين {single_void:.1f} سم، والدرفة 12×12 أصغر منه."
    )
    quad_void = (15 * 2) - kerf_cm
    notes.append(
        f"TEST-NEST-06/08/09: فراغ الرباعي بعد Kerf {quad_void:.1f} سم، ويستوعب 12×12 و10×10."
    )
    notes.append(
        "TEST-NEST-02/03/05: درفتا 50×50 بتجويف 20×20، أو 45×45 بتجويف 15×15، أصغر من اللوح 244×122."
    )
    notes.append(
        "TEST-NEST-07: المجموعة 40×40 بتجويف 15×15 منفصلة عن الدرفة 60×50 بتجويف 20×15."
    )
    opening = validate_glass_opening(
        outer_width_cm=80,
        outer_length_cm=100,
        glass_margin_mm=GLASS_MARGIN_MM,
    )
    notes.append(
        "TEST-NEST-10: فتحة البلور "
        f"{float(opening.opening_width_mm) / 10:.0f}×{float(opening.opening_length_mm) / 10:.0f} سم "
        "بعد هامش 10 سم، وتستوعب 25×25 و20×20 وL 20×20."
    )
    return notes


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
        return str(existing[0])
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
    fallback = frappe.get_all(
        "Edge Banding Type",
        filters={"disabled": 0},
        pluck="name",
        limit=1,
    )
    if not fallback:
        raise SystemExit("لا يوجد نوع قشاط صالح على موقع التطوير.")
    return str(fallback[0])


def _existing_orders() -> dict[str, str]:
    import frappe

    rows = frappe.get_all(
        "Door Cutting Order",
        filters={"order_notes": ["like", "TEST-NEST-%"]},
        fields=["name", "order_notes"],
        limit=50,
    )
    found: dict[str, str] = {}
    for row in rows:
        code = str(row.order_notes or "").splitlines()[0].strip()
        found.setdefault(code, str(row.name))
    return found


def _expected_copies(case: dict[str, object]) -> int:
    return sum(int(row["qty"]) for row in case["rows"])  # type: ignore[index]


def _insert_order(case: dict[str, object], customer: str, edge_type: str) -> str:
    import frappe

    order = frappe.get_doc(
        {
            "doctype": "Door Cutting Order",
            "customer": customer,
            "order_notes": f"{case['code']}\n{case['title']}",
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


def _verify_order(name: str, case: dict[str, object], edge_type: str) -> list[str]:
    import frappe

    order = frappe.get_doc("Door Cutting Order", name)
    problems: list[str] = []
    if order.status != "Draft" or int(order.docstatus or 0) != 0:
        problems.append("الطلب ليس Draft")
    if order.approved_plan or order.price_approval_status != "Unapproved":
        problems.append("الطلب معتمد سعرياً أو له خطة معتمدة")
    if float(order.board_length_cm) != BOARD_LENGTH_CM or float(order.board_width_cm) != BOARD_WIDTH_CM:
        problems.append("مقاس اللوح مختلف")
    if int(order.allow_piece_mirroring or 0) != int(case["mirror"]):
        problems.append("إعداد الانعكاس مختلف")
    if order.default_edge_type != edge_type:
        problems.append("نوع القشاط مختلف")
    rows = list(order.pieces or [])
    expected_rows = case["rows"]
    if len(rows) != len(expected_rows):  # type: ignore[arg-type]
        problems.append(f"عدد الأسطر {len(rows)} بدل {len(expected_rows)}")  # type: ignore[arg-type]
        return problems
    copies = 0
    for saved, expected in zip(rows, expected_rows, strict=True):  # type: ignore[arg-type]
        copies += int(saved.qty or 0)
        for field in ("piece_type", "qty", "allow_rotation", "length_cm", "width_cm"):
            if field not in expected:
                continue
            if str(saved.get(field)) != str(expected[field]) and float(saved.get(field) or 0) != float(
                expected[field]
            ):
                problems.append(f"{field} مختلف في {saved.piece_type}")
        if expected.get("piece_type") in {"L-Shaped Corner", "Clipped Corner"}:
            if saved.clipped_corner_position != "Top Right":
                problems.append("موضع الزاوية مختلف")
            if float(saved.clipped_corner_width_cm or 0) != float(expected["clipped_corner_width_cm"]):
                problems.append("عرض التجويف أو الكسر مختلف")
            if float(saved.clipped_corner_length_cm or 0) != float(expected["clipped_corner_length_cm"]):
                problems.append("طول التجويف أو الكسر مختلف")
        if expected.get("piece_type") == "Glass" and float(saved.glass_margin_mm or 0) != GLASS_MARGIN_MM:
            problems.append("هامش البلور مختلف")
        if abs(float(saved.cut_width_cm or 0) - float(saved.width_cm or 0)) > 0.001:
            problems.append("قص العرض تغيّر بسبب قشاط غير مطلوب")
        if abs(float(saved.cut_length_cm or 0) - float(saved.length_cm or 0)) > 0.001:
            problems.append("قص الطول تغيّر بسبب قشاط غير مطلوب")
    if copies != _expected_copies(case):
        problems.append("إجمالي النسخ مختلف")
    visible = frappe.get_list(
        "Door Cutting Order",
        filters={"name": name},
        fields=["name", "status", "order_notes"],
        limit=1,
    )
    if not visible:
        problems.append("الطلب لا يظهر في استعلام القائمة")
    return problems


def _snapshot(plan: object) -> dict:
    raw = getattr(plan, "snapshot_json", None) or ""
    if not raw:
        return {}
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else {}


def _placed(snapshot: dict) -> list[dict]:
    return [
        piece
        for sheet in snapshot.get("sheets") or []
        for piece in sheet.get("pieces") or []
        if isinstance(piece, dict)
    ]


def _calculate(name: str) -> dict[str, object]:
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
    if not existing:
        return {"ok": False, "summary": "لم تُنشأ خطة مسودة"}
    plan = frappe.get_doc("Cutting Plan", existing[0])
    order.reload()
    if order.approved_plan or plan.status != "Draft" or order.price_approval_status != "Unapproved":
        return {"ok": False, "summary": "الحساب غيّر حالة الاعتماد"}
    snapshot = _snapshot(plan)
    placed = _placed(snapshot)
    unplaced = snapshot.get("unplaced") or []
    diagnostics = snapshot.get("shape_nesting_diagnostics") or {}
    glass = snapshot.get("glass_nesting_diagnostics") or {}
    hosted = [
        piece for piece in placed if piece.get("glass_host_piece_id") not in (None, "")
    ]
    mirrors = [
        piece
        for piece in placed
        if piece.get("mirrored") or piece.get("corner_mirrored") or piece.get("placement_mirrored")
    ]
    turns = [
        int(piece.get("corner_rotation_quarter_turns") or 0)
        for piece in placed
        if piece.get("piece_type") in {"L-Shaped Corner", "Clipped Corner"}
    ]
    angles = [
        piece.get("placement_rotation_deg")
        for piece in placed
        if piece.get("placement_rotation_deg") not in (None, "", 0, 0.0)
    ]
    complete = (
        plan.validation_status == "Valid"
        and not unplaced
        and len(placed) == sum(int(row.qty or 0) for row in order.pieces)
    )
    parts = [
        f"التحقق {plan.validation_status}",
        f"موضوعة {len(placed)}",
        f"ألواح {plan.required_boards}",
        f"Kerf {plan.kerf_mm} مم",
        f"تشذيب {plan.trim_margin_mm} مم",
        f"آلة {plan.machine_type}",
        f"وضع {plan.optimization_mode}",
    ]
    if reused:
        parts.append("أُعيد استخدام الخطة المحسوبة")
    if diagnostics:
        parts.append(
            "تعشيق الأشكال "
            f"{diagnostics.get('outcome')} تشكيل {diagnostics.get('formations')} "
            f"ضيوف {diagnostics.get('void_guests')}"
        )
    if glass:
        parts.append(f"تشخيص البلور {glass.get('outcome') or glass}")
    if hosted:
        parts.append(f"داخل فتحة البلور {len(hosted)}")
    if mirrors:
        parts.append(f"انعكاسات {len(mirrors)}")
    if turns:
        parts.append(f"دورات الزوايا {turns}")
    if angles:
        parts.append(f"دوران غير ربعي {angles}")
    if plan.validation_errors:
        parts.append(str(plan.validation_errors).replace("\n", " | "))
    if unplaced:
        parts.append(f"غير موضوعة {len(unplaced)}")
    return {"ok": complete, "summary": "؛ ".join(parts)}


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
        for line in _geometry_review():
            print(line, flush=True)
        customer = _customer()
        edge_type = _edge_type()
        print(f"customer={customer}", flush=True)
        print(f"edge_type={edge_type}", flush=True)
        existing = _existing_orders()
        report: list[dict[str, object]] = []
        for case in CASES:
            code = str(case["code"])
            print(f"start {code}", flush=True)
            created = False
            name = existing.get(code, "")
            problems: list[str] = []
            summary = ""
            try:
                if not name:
                    name = _insert_order(case, customer, edge_type)
                    created = True
                    frappe.db.commit()
                problems = _verify_order(name, case, edge_type)
                if problems:
                    frappe.db.commit()
                    summary = "فشل التحقق: " + "؛ ".join(problems)
                    calculated = False
                else:
                    outcome = _calculate(name)
                    frappe.db.commit()
                    calculated = bool(outcome["ok"])
                    summary = str(outcome["summary"])
            except Exception as error:  # noqa: BLE001 - one failed order must not stop the rest
                frappe.db.rollback()
                calculated = False
                summary = f"{type(error).__name__}: {error}"
                print(traceback.format_exc(), flush=True)
            report.append(
                {
                    "code": code,
                    "order": name,
                    "created": created,
                    "copies": _expected_copies(case),
                    "calculated": calculated,
                    "problems": problems,
                    "summary": summary,
                }
            )
            print(json.dumps(report[-1], ensure_ascii=False), flush=True)
        print("REPORT")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        frappe.destroy()


if __name__ == "__main__":
    sys.exit(main())
