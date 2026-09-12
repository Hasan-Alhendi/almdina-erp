from __future__ import annotations

import json
from pathlib import Path

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CAPABILITY_PRESENTATION,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.services.cutting_plan_workspace_query_service import (
    _plan_row,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_UX = ROOT / "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js"


def _row(snapshot):
    return _plan_row(
        {
            "name": "CP-176",
            "source_type": "Uploaded DXF",
            "revision": 1,
            "status": "Draft",
            "required_boards": 0,
        },
        json.dumps(snapshot),
    )


def test_read_model_has_no_offcut_surface_data_without_offcut():
    row = _row({
        "sheets": [{
            "sheet_no": 1,
            "resource_kind": "FULL_BOARD",
            "pieces": [{"piece_instance_id": "row:1", "resource_kind": "FULL_BOARD"}],
        }]
    })

    assert row["offcut"]["count"] == 0
    assert row["offcut"]["assignments"] == []
    assert all(item["count"] == 0 for item in row["offcut"]["summary"])


def test_read_model_projects_business_state_labels_and_exact_summary():
    states = [
        ("CUSTOMER", "FACTORY"),
        ("CUSTOMER", "FACTORY"),
        ("CUSTOMER", "CUSTOMER"),
        ("FACTORY", "FACTORY"),
        ("FACTORY", "FACTORY"),
        ("UNASSIGNED", "UNASSIGNED"),
    ]
    row = _row({
        "sheets": [{
            "sheet_no": 3,
            "resource_kind": "OFFCUT",
            "pieces": [
                {
                    "piece_instance_id": f"row:{index}",
                    "label": f"1.{index}",
                    "resource_kind": "OFFCUT",
                    "offcut_source_party": source,
                    "offcut_execution_party": execution,
                }
                for index, (source, execution) in enumerate(states, start=1)
            ],
        }]
    })

    assert row["offcut"]["count"] == 6
    assert [item["count"] for item in row["offcut"]["summary"]] == [2, 1, 2, 1]
    assert [item["business_state"] for item in row["offcut"]["assignments"]] == [
        "CUSTOMER_FACTORY",
        "CUSTOMER_FACTORY",
        "CUSTOMER_CUSTOMER",
        "FACTORY_FACTORY",
        "FACTORY_FACTORY",
        "UNASSIGNED",
    ]
    assert len(row["offcut"]["state_options"]) == 4


def test_frontend_uses_one_business_state_selector_and_hides_empty_surface():
    source = PLAN_UX.read_text(encoding="utf-8")

    assert 'if (!assignments.length) return "";' in source
    assert "dco-offcut-business-state" in source
    assert "dco-offcut-source" not in source
    assert "dco-offcut-execution" not in source
    assert "FACTORY_CUSTOMER" not in source
    assert "resource_kind: \"OFFCUT\"" not in source
    assert "offcut_price_usd" not in source
    assert "dco-offcut-price" not in source
    assert "تحديد مصدر وتنفيذ قطع النقص" in source
    assert "dco-apply-offcut-bulk" in source


def test_factory_permission_presentation_matches_jira_contract():
    presentation = CAPABILITY_PRESENTATION[Capability.SET_OFFCUT_EXECUTION_OWNER]

    assert presentation["label"] == "تحديد مصدر وتنفيذ قطع النقص"
    assert presentation["description"] == (
        "يسمح بتحديد ما إذا كانت فضلة النقص من المعمل أو من الزبون، "
        "وتحديد ما إذا كان تنفيذها في المعمل أو عند الزبون، ضمن الحالات المسموحة فقط."
    )
