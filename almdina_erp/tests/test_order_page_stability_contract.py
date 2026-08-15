from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js"


def source(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


class TestOrderPageStabilityContract(unittest.TestCase):
    def test_status_strip_has_one_renderer(self) -> None:
        operator = source("door_cutting_order_operator_ux.js")
        production = source("shop_floor_order_ux.js")

        self.assertNotIn("fields_dict.operator_status_strip", operator)
        self.assertIn("fields_dict.operator_status_strip", production)
        self.assertIn("_almdinaTrackingStripHtml", production)

    def test_measurement_editor_preserves_identical_dom(self) -> None:
        operator = source("door_cutting_order_operator_ux.js")

        self.assertIn("root._dcoFastEntryHtml !== html", operator)
        self.assertIn("root._dcoFastEntryHtml = html", operator)
        self.assertIn("_dcoForceHtmlReplace", operator)
        self.assertIn("renderStableHtml(", operator)

    def test_revision_is_the_only_save_edit_owner(self) -> None:
        production = source("shop_floor_order_ux.js")
        revision = source("door_cutting_order_revision_ux.js")

        presentation = production.split("function applyShopFloorPresentation", 1)[1].split(
            "function openDispatchDialog", 1
        )[0]
        self.assertNotIn("frm.enable_save(", presentation)
        self.assertNotIn("frm.disable_save(", presentation)
        self.assertIn("setPrimaryActionMode", revision)
        self.assertIn('"edit-pending"', revision)
        self.assertIn("canShowEditAction", revision)
        self.assertIn("requestEditSession", revision)
        show_edit = revision.split("function canShowEditAction", 1)[1].split(
            "function primaryActionLabel", 1
        )[0]
        self.assertIn('(frm.doc.status || "Draft") !== "Draft"', show_edit)
        scheduler = revision.split("function schedulePrimaryActionSync", 1)[1].split(
            "function removeEditSessionButtons", 1
        )[0]
        self.assertNotIn("setTimeout", scheduler)

    def test_permission_request_has_one_form_owner(self) -> None:
        permission_context = source("permission_context.js")
        production = source("shop_floor_order_ux.js")
        duplicate_guard = permission_context.split(
            "if (window.AlmdinaPermissions)", 1
        )[1].split("return;", 1)[0]
        recovery = production.split("function recoverProductionActions", 1)[1].split(
            'frappe.ui.form.on("Door Cutting Order"', 1
        )[0]

        self.assertNotIn("AlmdinaPermissions.refresh()", duplicate_guard)
        self.assertNotIn("permissions.refresh()", recovery)

    def test_header_actions_are_physically_anchored_left(self) -> None:
        toolbar = source("door_cutting_order_toolbar_stability_ux.js")

        self.assertIn("@media(min-width:992px)", toolbar)
        self.assertIn("position:fixed!important", toolbar)
        self.assertIn("--dco-viewport-left-compensation", toolbar)
        self.assertIn("function anchorActionsToViewportLeft", toolbar)
        self.assertIn("Math.min(...visibleLefts)", toolbar)
        self.assertIn('!node.closest(".dropdown-menu")', toolbar)
        self.assertIn("16 - actualLeft", toolbar)
        self.assertIn("right:auto!important", toolbar)
        self.assertIn("top:10px!important", toolbar)
        self.assertNotIn("dco-primary-action-pending", toolbar)

    def test_plan_recovery_does_not_destroy_ready_html(self) -> None:
        bootstrap = source("door_cutting_order_plan_surface_bootstrap.js")

        self.assertIn("if (metadataChanged && typeof field.refresh", bootstrap)
        self.assertIn("__almdinaPlanSurfaceSignature", bootstrap)
        self.assertIn("permissionVersion() <= 0", bootstrap)

    def test_permission_field_metadata_is_updated_only_when_changed(self) -> None:
        costs = source("door_cutting_order_cost_permissions_ux.js")

        self.assertIn('field.df.options !== "costing_currency"', costs)
        self.assertIn("Number(field.df.hidden || 0) !== hidden", costs)
        self.assertIn("Number(field.df.read_only || 0) !== readOnly", costs)


if __name__ == "__main__":
    unittest.main()
