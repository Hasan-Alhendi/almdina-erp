"""Exploratory P3/P4 targets; intentionally excluded from the P0 passing gate.

Run explicitly with pytest to observe the current gap. These are independently
constructed synthetic cases, not reproductions of customer orders 108/154.
"""

import pytest

from almdina_erp.almdina_erp.domain.cutting.optimizer import optimize_plan
from almdina_erp.tests.test_optimizer_p0_safety import SETTINGS, SHAPE_CASES, _requested


@pytest.mark.parametrize("name", SHAPE_CASES)
def test_current_optimizer_finds_proven_one_board_shape_layout(name):
    pieces, (width, height) = _requested(name)
    plan = optimize_plan(
        pieces, width, height, SETTINGS["kerf_cm"],
        selected_mode=SETTINGS["selected_mode"],
        machine_type=SETTINGS["machine_type"],
        time_limit_sec=SETTINGS["time_limit_sec"],
    )
    assert not plan["unplaced"]
    assert len(plan["sheets"]) == 1, f"{name}: current plan needs {len(plan['sheets'])} boards"
