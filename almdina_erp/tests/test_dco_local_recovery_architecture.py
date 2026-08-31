from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "public" / "js" / "door_cutting_order" / "recovery"
REFERENCE = ROOT.parent / "docs" / "reference"
MANIFEST = ROOT / "frontend_assets.py"


class TestDcoLocalRecoveryArchitecture(unittest.TestCase):
    def test_recovery_assets_are_ordered_after_existing_owners(self) -> None:
        manifest = runpy.run_path(str(MANIFEST))["doctype_js"]["Door Cutting Order"]
        document_context = "public/js/door_cutting_order/core/door_cutting_order_document_context.js"
        workspace_store = "public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"
        plan_state = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"
        cost_state = "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js"
        projection = (
            "public/js/door_cutting_order/recovery/application/"
            "door_cutting_order_recovery_projection.js"
        )
        indexed_db = (
            "public/js/door_cutting_order/recovery/infrastructure/"
            "door_cutting_order_recovery_indexeddb.js"
        )
        draft_repository = (
            "public/js/door_cutting_order/recovery/infrastructure/"
            "door_cutting_order_local_draft_repository.js"
        )
        asset_repository = (
            "public/js/door_cutting_order/recovery/infrastructure/"
            "door_cutting_order_local_asset_repository.js"
        )
        recovery_api = (
            "public/js/door_cutting_order/recovery/infrastructure/"
            "door_cutting_order_recovery_api.js"
        )
        checkpoint_session = (
            "public/js/door_cutting_order/recovery/application/"
            "door_cutting_order_checkpoint_session.js"
        )
        new_recovery = (
            "public/js/door_cutting_order/recovery/application/"
            "door_cutting_order_new_recovery.js"
        )
        revision_owner = "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js"
        integration = (
            "public/js/door_cutting_order/recovery/presentation/"
            "door_cutting_order_local_checkpoint.js"
        )

        for asset in (
            projection,
            indexed_db,
            draft_repository,
            asset_repository,
            recovery_api,
            checkpoint_session,
            new_recovery,
            integration,
        ):
            self.assertEqual(manifest.count(asset), 1)
        self.assertLess(manifest.index(document_context), manifest.index(workspace_store))
        self.assertLess(manifest.index(plan_state), manifest.index(projection))
        self.assertLess(manifest.index(cost_state), manifest.index(projection))
        self.assertLess(manifest.index(projection), manifest.index(indexed_db))
        self.assertLess(manifest.index(indexed_db), manifest.index(draft_repository))
        self.assertLess(manifest.index(draft_repository), manifest.index(asset_repository))
        self.assertLess(manifest.index(asset_repository), manifest.index(recovery_api))
        self.assertLess(manifest.index(recovery_api), manifest.index(checkpoint_session))
        self.assertLess(manifest.index(checkpoint_session), manifest.index(new_recovery))
        self.assertLess(manifest.index(revision_owner), manifest.index(integration))

    def test_browser_storage_is_bounded_to_infrastructure(self) -> None:
        sources = {
            path: path.read_text(encoding="utf-8")
            for path in RECOVERY.rglob("*.js")
        }
        indexed_db_path = RECOVERY / "infrastructure" / "door_cutting_order_recovery_indexeddb.js"
        for path, source in sources.items():
            if path != indexed_db_path:
                self.assertNotIn("window.indexedDB", source)
                self.assertNotIn("indexedDB.open", source)
            self.assertNotIn("localStorage", source)
            self.assertNotIn("sessionStorage", source)

    def test_local_checkpoint_never_calls_official_save_or_guesses_readiness(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in RECOVERY.rglob("*.js")
        )
        self.assertNotIn("frm.save(", source)
        self.assertNotIn("setInterval(", source)
        self.assertNotIn("setTimeout(", source)
        self.assertIn("scheduleFrame", source)
        self.assertIn('"visibilitychange"', source)
        self.assertIn('"pagehide"', source)
        api = (
            RECOVERY
            / "infrastructure"
            / "door_cutting_order_recovery_api.js"
        ).read_text(encoding="utf-8")
        self.assertEqual(api.count("frappe.call("), 1)
        self.assertIn("reconcile_new_order_creation", api)

    def test_workspace_recovery_observes_the_existing_store_owner(self) -> None:
        integration = (
            RECOVERY
            / "presentation"
            / "door_cutting_order_local_checkpoint.js"
        ).read_text(encoding="utf-8")
        self.assertIn('typeof owner.storeFor === "function"', integration)
        self.assertIn('typeof store.subscribe !== "function"', integration)
        self.assertIn("store.subscribe((snapshot)", integration)

    def test_projection_allowlist_matches_current_doctype_fields(self) -> None:
        order = json.loads(
            (
                ROOT
                / "almdina_erp"
                / "doctype"
                / "door_cutting_order"
                / "door_cutting_order.json"
            ).read_text(encoding="utf-8")
        )
        detail = json.loads(
            (
                ROOT
                / "almdina_erp"
                / "doctype"
                / "door_cutting_order_detail"
                / "door_cutting_order_detail.json"
            ).read_text(encoding="utf-8")
        )
        order_fields = {field["fieldname"] for field in order["fields"]}
        detail_fields = {field["fieldname"] for field in detail["fields"]}
        projection = (
            RECOVERY
            / "application"
            / "door_cutting_order_recovery_projection.js"
        ).read_text(encoding="utf-8")
        header_contract = {
            "customer",
            "order_date",
            "order_notes",
            "board_description",
            "board_length_cm",
            "board_width_cm",
            "default_edge_type",
            "edge_color",
        }
        piece_contract = {
            "piece_type",
            "extra_double",
            "extra_liner",
            "extra_recessed_handle_cutout",
            "clipped_corner_position",
            "clipped_corner_width_cm",
            "clipped_corner_length_cm",
            "width_cm",
            "length_cm",
            "qty",
            "allow_rotation",
            "edge_long_right",
            "edge_long_left",
            "edge_width_top",
            "edge_width_bottom",
            "edge_long_right_type_override",
            "edge_long_left_type_override",
            "edge_width_top_type_override",
            "edge_width_bottom_type_override",
            "notes",
            "special_shape_drawing_json",
            "special_shape_geometry_json",
        }
        self.assertTrue(header_contract <= order_fields)
        self.assertTrue(piece_contract <= detail_fields)
        for fieldname in header_contract | piece_contract:
            self.assertIn(f'"{fieldname}"', projection)
        for forbidden in (
            "total_cost_usd",
            "approved_plan",
            "current_production_stage",
            "cut_width_cm",
            "edge_cost_usd",
        ):
            self.assertNotIn(f'"{forbidden}"', projection)

    def test_local_assets_are_separate_and_draft_delete_cascades(self) -> None:
        draft_repository = (
            RECOVERY
            / "infrastructure"
            / "door_cutting_order_local_draft_repository.js"
        ).read_text(encoding="utf-8")
        asset_repository = (
            RECOVERY
            / "infrastructure"
            / "door_cutting_order_local_asset_repository.js"
        ).read_text(encoding="utf-8")
        projection = (
            RECOVERY
            / "application"
            / "door_cutting_order_recovery_projection.js"
        ).read_text(encoding="utf-8")
        self.assertIn("dco_recovery_assets", (
            RECOVERY
            / "infrastructure"
            / "door_cutting_order_recovery_indexeddb.js"
        ).read_text(encoding="utf-8"))
        self.assertIn('assets.index("draft_key").getAllKeys(key)', draft_repository)
        self.assertIn("draft_not_found", asset_repository)
        self.assertIn("sha256Bytes", asset_repository)
        self.assertIn("/^blob:/i", projection)
        self.assertIn("/^data:[^,]{0,128},/i", projection)

    def test_plan_lazy_readiness_contract_remains_intact(self) -> None:
        registry = (
            ROOT
            / "public"
            / "js"
            / "door_cutting_order"
            / "core"
            / "door_cutting_order_workspace_asset_registry.js"
        ).read_text(encoding="utf-8")
        lifecycle = (
            ROOT
            / "public"
            / "js"
            / "door_cutting_order"
            / "core"
            / "door_cutting_order_workspace_activation_lifecycle.js"
        ).read_text(encoding="utf-8")
        self.assertIn("AlmdinaPlanEditSessionUX", registry)
        self.assertIn("AlmdinaPlanFieldAccessAdapter", registry)
        self.assertIn("await registry.ensureForTab(fieldname)", lifecycle)
        self.assertIn("activationStillCurrent(frm, identity, fieldname)", lifecycle)
        self.assertIn("reconcileLoadedFeature(frm, fieldname)", lifecycle)

    def test_new_recovery_is_explicit_arabic_and_hydrates_only_projection(self) -> None:
        application = (
            RECOVERY
            / "application"
            / "door_cutting_order_new_recovery.js"
        ).read_text(encoding="utf-8")
        presentation = (
            RECOVERY
            / "presentation"
            / "door_cutting_order_local_checkpoint.js"
        ).read_text(encoding="utf-8")
        for label in ("متابعة الطلب", "بدء طلب جديد", "حذف المسودة"):
            self.assertIn(label, presentation)
        self.assertIn("مسودة محلية غير محفوظة رسميًا", presentation)
        self.assertIn("session.beginRestore()", application)
        self.assertIn("session.completeRestore()", application)
        self.assertIn("hydrationPort(dco)", application)
        self.assertNotIn("frappe", application)
        self.assertNotIn("frm", application)
        self.assertIn('frappe.model.clear_table(frm.doc, "pieces")', presentation)
        self.assertIn("frappe.model.add_child(", presentation)
        self.assertIn("hydrateNewProjection", presentation)
        self.assertIn("AlmdinaDoorCuttingFastEntry", presentation)
        self.assertIn("AlmdinaFastEntryKeyboardUX", presentation)
        self.assertNotIn("AlmdinaPlanWorkspaceState", application)
        self.assertNotIn("invoice", application.lower())

    def test_first_insert_uses_native_save_with_atomic_unique_technical_token(self) -> None:
        doctype = json.loads(
            (
                ROOT
                / "almdina_erp"
                / "doctype"
                / "door_cutting_order"
                / "door_cutting_order.json"
            ).read_text(encoding="utf-8")
        )
        fields = {field["fieldname"]: field for field in doctype["fields"]}
        self.assertEqual(fields["recovery_creation_token"]["hidden"], 1)
        self.assertEqual(fields["recovery_creation_token"]["unique"], 1)
        self.assertEqual(fields["recovery_creation_token"]["no_copy"], 1)
        self.assertEqual(fields["recovery_creation_token"]["read_only"], 1)
        self.assertEqual(fields["recovery_creation_user"]["hidden"], 1)
        self.assertEqual(fields["recovery_creation_user"]["no_copy"], 1)
        self.assertEqual(fields["recovery_creation_user"]["read_only"], 1)
        service = (
            ROOT / "almdina_erp" / "services" / "new_order_recovery_service.py"
        ).read_text(encoding="utf-8")
        controller = (
            ROOT
            / "almdina_erp"
            / "doctype"
            / "door_cutting_order"
            / "door_cutting_order_controller.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def before_insert(self)", controller)
        self.assertIn("apply_new_order_creation_identity(self)", controller)
        self.assertIn("frappe.session.user", service)
        self.assertIn("frappe.has_permission(document, \"read\"", service)
        self.assertNotIn("permanent_name", service)

    def test_unknown_outcome_state_is_persisted_before_cleanup(self) -> None:
        repository = (
            RECOVERY
            / "infrastructure"
            / "door_cutting_order_local_draft_repository.js"
        ).read_text(encoding="utf-8")
        session = (
            RECOVERY
            / "application"
            / "door_cutting_order_checkpoint_session.js"
        ).read_text(encoding="utf-8")
        presentation = (
            RECOVERY
            / "presentation"
            / "door_cutting_order_local_checkpoint.js"
        ).read_text(encoding="utf-8")
        self.assertIn('PENDING_RECONCILIATION: "PENDING_RECONCILIATION"', repository)
        self.assertIn("setOfficialSaveState", repository)
        self.assertIn("beginOfficialSave", session)
        self.assertIn("markPendingReconciliation", session)
        self.assertIn("resumeAfterProvenFailure", session)
        self.assertIn(
            "expected_recovery_revision: expectedRecoveryRevision",
            session,
        )
        self.assertIn('"invalid_expected_revision"', repository)
        self.assertIn(
            "Number(current.recovery_revision) !== expectedRevision",
            repository,
        )
        self.assertIn(
            "Recovery checkpoint cannot advance while official Save is pending",
            repository,
        )
        self.assertIn(
            "Recovery draft changed before confirmed cleanup",
            repository,
        )
        self.assertNotIn(
            "recovery_revision: captureRevision,\n                    official_save_state:",
            session,
        )
        self.assertIn('typeof context.isCurrent === "function"', presentation)
        self.assertIn("context.isCurrent(frm, token)", presentation)
        self.assertIn("if (!isCurrent()) return false;", presentation)
        self.assertIn('INACTIVE_SAVE_ERROR = "recovery_document_inactive"', presentation)
        self.assertIn("clearProvenSaveAttempt", presentation)
        self.assertIn("CLEAR_ATTEMPT_MAX_TRIES", presentation)
        self.assertIn("started.value && started.value.official_save_attempted_at", presentation)
        self.assertIn("bindObservedSaveOperation", presentation)
        self.assertIn("handleOfficialSaveSuccess", presentation)
        self.assertIn("const state = operation && operation.state;", presentation)
        self.assertIn("adoptPersistedOfficialSaveState", presentation)
        self.assertIn("adoptPersistedOfficialSaveState", session)
        self.assertIn("external_revision_conflict", presentation)
        self.assertIn("quarantineExternalRevision", presentation)
        self.assertIn("function flushState(frm, state = currentState(frm))", presentation)
        self.assertIn("setCardActionsDisabled", presentation)
        self.assertIn("let actionInFlight = false;", presentation)
        self.assertIn("setDiscoveryActionsDisabled", presentation)
        self.assertIn("const displayedDraftIds = new Set", presentation)
        self.assertIn("if (!displayedDraftIds.size)", presentation)
        self.assertIn("initializations.get(frm) !== initialization", presentation)
        self.assertIn("if (!ownsDiscovery()) return;", presentation)
        self.assertIn("await initialization.promise;", presentation)
        self.assertIn("if (!state && !discoveryOwnsForm) return;", presentation)
        self.assertIn("اكتمل تجهيز الحفظ المحلي", presentation)
        self.assertGreaterEqual(
            presentation.count('if (initialization.pendingDirty && state) markDirty(frm, "DCO");'),
            5,
        )
        self.assertIn("const current = await repository().read", presentation)
        self.assertIn("quarantineExternalRevision(state, code);", presentation)
        self.assertIn(
            '["stale_revision", "revision_conflict", "save_attempt_conflict"].includes(code)',
            presentation,
        )
        self.assertIn("expectedRevision: operation.attemptedRevision", presentation)
        self.assertIn("expectedAttemptedAt: operation.cleanupAttemptedAt", presentation)
        self.assertIn("expectedRevision: reconciledSnapshot.recovery_revision", presentation)
        self.assertIn(
            "saveOperation.cleanupAttemptedAt = preAttempt.official_save_attempted_at",
            presentation,
        )
        self.assertNotIn(
            "saveOperation.attemptedAt = preAttempt.official_save_attempted_at",
            presentation,
        )
        self.assertIn(
            "saveOperation.attemptedRevision = preAttempt.saved_revision",
            presentation,
        )
        self.assertIn('started.error.code === "stale_revision"', presentation)
        self.assertIn(
            'quarantineExternalRevision(state, "save_attempt_conflict")',
            presentation,
        )
        self.assertIn("record.recovery_revision", presentation)
        self.assertIn("record.official_save_attempted_at", presentation)
        self.assertIn("const current = await repo.read(identity)", presentation)
        self.assertIn('"save_attempt_conflict"', repository)
        self.assertIn("official_save_attempted_at", session)
        self.assertLess(
            presentation.index("state.session.complete();"),
            presentation.index("const result = await repository().delete("),
        )
        self.assertNotIn("frm.save(", presentation)

    def test_recovery_contract_documents_are_indexed(self) -> None:
        index = (REFERENCE / "README.md").read_text(encoding="utf-8")
        ownership = (
            REFERENCE / "16_DCO_RECOVERY_STATE_OWNERSHIP.md"
        ).read_text(encoding="utf-8")
        infrastructure = (
            REFERENCE / "17_DCO_LOCAL_RECOVERY_INFRASTRUCTURE.md"
        ).read_text(encoding="utf-8")
        self.assertIn("17_DCO_LOCAL_RECOVERY_INFRASTRUCTURE.md", index)
        self.assertIn("18_DCO_NEW_RECOVERY.md", index)
        self.assertIn("17_DCO_LOCAL_RECOVERY_INFRASTRUCTURE.md", ownership)
        self.assertIn("ALMADINA-128", infrastructure)
        self.assertIn("ALMADINA-129", infrastructure)
        new_recovery = (
            REFERENCE / "18_DCO_NEW_RECOVERY.md"
        ).read_text(encoding="utf-8")
        self.assertIn("ALMADINA-129", new_recovery)
        self.assertIn("PENDING_RECONCILIATION", new_recovery)


if __name__ == "__main__":
    unittest.main()
