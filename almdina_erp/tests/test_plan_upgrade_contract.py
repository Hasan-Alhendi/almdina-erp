"""Upgrade replay for a saved manufacturing baseline (synthetic order only)."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from almdina_erp.tests.test_plan_fingerprint_compatibility import golden_case
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_workspace as workspace


class TestUpgradeContract(unittest.TestCase):
    def test_v4_golden_hash_is_pinned_without_editing_the_v3_corpus(self):
        fixture, order, plan = golden_case()
        self.assertEqual('95c0824ba755a389ba279892b83e12586eed5ba630844f986a5570dda2701670',
                         workspace.plan_input_fingerprint(order, plan, version=4))
        self.assertEqual(fixture['contracts']['v3']['sha256'], workspace.plan_input_fingerprint(order, plan))

    def test_new_snapshot_captures_baseline_layout_and_separate_provenance(self):
        import frappe
        _, order, plan = golden_case()
        plan.source_type = 'System'
        plan.set = lambda key, value: setattr(plan, key, value)
        plan.append = lambda key, value: getattr(plan, key).append(value)
        generation = workspace.plan_input_fingerprint(order, plan)
        snapshot = {'sheets': [{'sheet_no': 1, 'pieces': []}],
                    'validation': {'is_valid': True}}
        with patch.object(frappe, 'as_json', side_effect=json.dumps, create=True):
            workspace._apply_snapshot(order, plan, workspace.sanitize_plan_snapshot(snapshot), fingerprint=generation)
        stored = json.loads(plan.snapshot_json)
        self.assertEqual(4, stored['input_fingerprint_contract'])
        self.assertEqual(generation, stored['generation_input_fingerprint'])
        self.assertEqual(plan.input_fingerprint, stored['input_fingerprint'])
        self.assertEqual('MATCH', workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).state)
        self.assertEqual(stored['saved_layout_sha256'], workspace.fingerprint_payload(
            {'sheets': workspace.sanitize_plan_snapshot(stored)['sheets']}))

    def test_exact_preview_commit_checks_v4_and_original_generation_inputs(self):
        from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_preview_commit as commit
        import frappe
        _, order, plan = golden_case()
        settings = {'packing_mode': 'auto_pro', 'cutting_machine_type': 'Auto',
                    'kerf_mm': 3.0, 'trim_margin_mm': 5.0,
                    'optimization_time_limit_sec': 10.0}
        v3 = workspace.plan_input_fingerprint(order, plan)
        v4 = workspace.plan_input_fingerprint(order, plan, version=4)
        snapshot = {'sheets': [{'pieces': []}], 'validation': {'is_valid': True},
                    'generation_input_fingerprint': v3}
        with patch.object(commit, 'apply_calculation_outcome') as apply:
            commit.apply_exact_system_preview(order, plan, settings=settings, snapshot=snapshot,
                                              expected_input_fingerprint=v4)
            self.assertEqual(v3, apply.call_args.kwargs['fingerprint'])
            with self.assertRaisesRegex(frappe.ValidationError, "تغيّرت بيانات الطلب"):
                commit.apply_exact_system_preview(order, plan, settings=settings,
                    snapshot=snapshot | {'generation_input_fingerprint': 'stale'},
                    expected_input_fingerprint=v4)

    def test_revision_and_optimizer_provenance_do_not_invalidate_saved_geometry(self):
        _, order, plan = golden_case()
        baseline = workspace.plan_input_fingerprint(order, plan, version=4)
        order.revision += 1
        plan.optimization_time_limit_sec = 0
        plan.optimization_mode = 'retired_optimizer_mode'
        self.assertEqual(baseline, workspace.plan_input_fingerprint(order, plan, version=4))

    def test_manufacturing_inputs_remain_bound(self):
        _, order, plan = golden_case()
        baseline = workspace.plan_input_fingerprint(order, plan, version=4)
        for target, field, value in [
            ('order', 'full_board_width_mm', 1200),
            ('order', 'board_description', 'Different board material'),
            ('plan', 'kerf_mm', 8),
            ('plan', 'trim_margin_mm', 9),
            ('plan', 'machine_type', 'Panel Saw'),
            ('piece', 'cut_width_cm', 45),
            ('piece', 'extra_double', 1),
        ]:
            candidate_order, candidate_plan = copy.deepcopy(order), copy.deepcopy(plan)
            obj = {'order': candidate_order, 'plan': candidate_plan, 'piece': candidate_order.pieces[0]}[target]
            setattr(obj, field, value)
            with self.subTest(field=field):
                self.assertNotEqual(baseline, workspace.plan_input_fingerprint(candidate_order, candidate_plan, version=4))

    def test_snapshot_baseline_must_match_saved_hash_and_current_inputs(self):
        _, order, plan = golden_case()
        baseline = workspace.manufacturing_baseline_v4(order, plan)
        plan.input_fingerprint = workspace.plan_input_fingerprint(order, plan, version=4)
        from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
        sheets = [{'pieces': [{'piece_instance_id': 'piece:golden:1', 'x': 0, 'y': 0, 'w': 40, 'h': 80}]}]
        valid = {'input_fingerprint_contract': 4, 'manufacturing_baseline': baseline,
                 'sheets': sheets, 'validation': {'is_valid': True},
                 'saved_layout_sha256': fingerprint_payload({'sheets': sheets})}
        plan.snapshot_json = json.dumps(valid)
        self.assertEqual('MATCH', workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).state)
        order.revision += 1
        plan.optimization_time_limit_sec = 25
        self.assertEqual('MATCH', workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).state)
        order.pieces[0].cut_width_cm = 45.0
        self.assertEqual('MISMATCH', workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).state)
        valid['sheets'][0]['pieces'][0]['x'] = 4
        plan.snapshot_json = json.dumps(valid)
        self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).state)
        plan.snapshot_json = json.dumps({'input_fingerprint_contract': 4, 'manufacturing_baseline': {}})
        self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).state)
        future = baseline | {'unreviewed_field': 1}
        plan.input_fingerprint = fingerprint_payload(future)
        valid['manufacturing_baseline'] = future
        valid['sheets'][0]['pieces'][0]['x'] = 0
        plan.snapshot_json = json.dumps(valid)
        self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).state)

    def test_v4_runtime_gate_respects_approval_and_persisted_stale(self):
        from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_runtime_repository as runtime
        _, order, plan = golden_case()
        plan.input_fingerprint = workspace.plan_input_fingerprint(order, plan, version=4)
        plan.snapshot_json = json.dumps({'input_fingerprint_contract': 4,
                                         'manufacturing_baseline': workspace.manufacturing_baseline_v4(order, plan),
                                         'sheets': [{'pieces': []}], 'validation': {'is_valid': True},
                                         'saved_layout_sha256': workspace.fingerprint_payload({'sheets': [{'pieces': []}]})})
        plan.plan_needs_recalculation = 0
        order.approved_plan = plan.name
        order.revision += 1
        with patch.object(runtime, 'approved_plan_for_order', return_value=plan):
            self.assertTrue(runtime.production_plan_facts(order).has_approved_plan)
            plan.plan_needs_recalculation = 1
            self.assertFalse(runtime.production_plan_facts(order).has_approved_plan)

    def test_legacy_revision_only_save_does_not_cancel_approval_without_evidence(self):
        import frappe
        from unittest.mock import Mock
        from almdina_erp.almdina_erp.services import cutting_plan_invalidation_service as service
        _, order, plan = golden_case()
        plan.input_fingerprint = workspace.plan_input_fingerprint(order, plan)
        plan.snapshot_json = json.dumps({'input_fingerprint_contract': 3})
        order.approved_plan = plan.name
        previous = copy.deepcopy(order)
        order.revision += 1
        order.get_doc_before_save = lambda: previous
        with patch.object(frappe, 'get_doc', return_value=plan, create=True), \
             patch.object(frappe.db, 'exists', return_value=True, create=True), \
             patch.object(frappe.db, 'set_value', side_effect=AssertionError('cancelled without manufacturing change'), create=True):
            self.assertIsNone(service.apply_stale_approved_plan_cancellation(order))
        self.assertEqual(plan.name, order.approved_plan)

    def test_v4_approval_survives_provenance_but_cancels_real_cut_change(self):
        import frappe
        from almdina_erp.almdina_erp.services import cutting_plan_invalidation_service as service
        _, order, plan = golden_case()
        plan.input_fingerprint = workspace.plan_input_fingerprint(order, plan, version=4)
        from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
        sheets = [{'pieces': []}]
        plan.snapshot_json = json.dumps({
            'input_fingerprint_contract': 4,
            'manufacturing_baseline': workspace.manufacturing_baseline_v4(order, plan),
            'sheets': sheets, 'validation': {'is_valid': True},
            'saved_layout_sha256': fingerprint_payload({'sheets': sheets}),
        })
        order.approved_plan = plan.name
        order.revision += 1
        plan.optimization_time_limit_sec = 25
        plan.optimization_mode = 'retired_optimizer_mode'
        with patch.object(frappe, 'get_doc', return_value=plan, create=True), \
             patch.object(frappe.db, 'exists', return_value=True, create=True), \
             patch.object(frappe.db, 'set_value', side_effect=AssertionError('provenance cancelled approval'), create=True):
            self.assertIsNone(service.apply_stale_approved_plan_cancellation(order))
        order.pieces[0].cut_width_cm = 45
        writes = []
        with patch.object(frappe, 'get_doc', return_value=plan, create=True), \
             patch.object(frappe.db, 'exists', return_value=True, create=True), \
             patch.object(frappe.db, 'set_value', side_effect=lambda *a, **kw: writes.append(a), create=True), \
             patch.object(frappe, 'clear_document_cache', create=True), \
             patch.object(service, '_sync_drawing_dxf_status'):
            self.assertEqual(plan.name, service.apply_stale_approved_plan_cancellation(order))
        self.assertIsNone(order.approved_plan)
        self.assertTrue(any('status' in call for call in writes))

    def test_v4_detects_machining_and_double_changes(self):
        _, order, plan = golden_case()
        baseline = workspace.plan_input_fingerprint(order, plan, version=4)
        for field, value in [('extra_full_door_double', 1), ('extra_double_reference_sides', 'edge_long_left'),
                             ('liner_specs_json', '{"width_cm":2,"liners":[]}'),
                             ('special_shape_geometry_json', '{"outline":[]}'),
                             ('allow_rotation', 0)]:
            candidate = copy.deepcopy(order)
            setattr(candidate.pieces[0], field, value)
            with self.subTest(field=field):
                self.assertNotEqual(baseline, workspace.plan_input_fingerprint(candidate, plan, version=4))
        glass = copy.deepcopy(order)
        glass.pieces[0].piece_type = 'Glass'
        glass.pieces[0].glass_margin_mm = 50
        before = workspace.plan_input_fingerprint(glass, plan, version=4)
        glass.pieces[0].glass_margin_mm = 55
        self.assertNotEqual(before, workspace.plan_input_fingerprint(glass, plan, version=4))

    def test_historical_reader_is_independent_of_future_adapter_fields(self):
        from almdina_erp.almdina_erp.infrastructure.frappe.orders.cut_dimension_plan_adapter import FrappeCutDimensionPlanAdapter
        fixture, order, plan = golden_case()
        old = fixture['contracts']['v2_pre_oct22']['sha256']
        original = FrappeCutDimensionPlanAdapter.piece_row_as_dict
        def newer_adapter(row):
            return original(row) | {'new_geometry_field': 1}
        with patch.object(FrappeCutDimensionPlanAdapter, 'piece_row_as_dict', side_effect=newer_adapter):
            self.assertEqual('COMPATIBLE', workspace.plan_fingerprint_compatibility(order, plan, old).state)
            # V1's older commercial projection remains stable as well.
            self.assertEqual('COMPATIBLE', workspace.plan_fingerprint_compatibility(
                order, plan, workspace._legacy_plan_input_fingerprint(order, plan)
            ).state)

    def test_legacy_mode_reader_survives_a_future_optimizer_catalog_change(self):
        from almdina_erp.almdina_erp.domain.cutting import plan_settings
        fixture, order, plan = golden_case()
        with patch.object(plan_settings, 'persisted_mode_value', side_effect=ValueError('retired optimizer')):
            self.assertEqual('COMPATIBLE', workspace.plan_fingerprint_compatibility(
                order, plan, fixture['contracts']['v2_pre_oct22']['sha256']).state)

    def test_frozen_historical_settings_match_every_reviewed_mode_and_default(self):
        from almdina_erp.almdina_erp.domain.cutting.catalog import OPTIMIZATION_MODES, LEGACY_ENGINE_MODES
        from almdina_erp.almdina_erp.infrastructure.frappe.historical_plan_piece_reader import historical_plan_settings
        _, _, plan = golden_case()
        # Smart never existed in the frozen v2/v3 historical adapter. Keep all
        # reviewed modes covered and explicitly prove the new mode fails closed.
        reviewed = [mode for mode in OPTIMIZATION_MODES if mode.id != "smart"]
        from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import PlanFingerprintContractError
        for new_mode in ("smart", "Smart Search"):
            plan.optimization_mode = new_mode
            with self.assertRaises(PlanFingerprintContractError):
                historical_plan_settings(plan)
        modes = [mode.id for mode in reviewed]
        modes += [mode.engine_mode for mode in reviewed if mode.engine_mode]
        modes += list(LEGACY_ENGINE_MODES)
        for mode in modes:
            plan.optimization_mode = mode
            with self.subTest(mode=mode):
                self.assertEqual(workspace._plan_settings_payload(plan), historical_plan_settings(plan))
        plan.optimization_mode = None
        plan.optimization_time_limit_sec = None
        plan.kerf_mm = None
        plan.trim_margin_mm = None
        self.assertEqual(workspace._plan_settings_payload(plan), historical_plan_settings(plan))

    def test_historical_row_reader_replays_the_reviewed_adapter_vectors(self):
        from almdina_erp.almdina_erp.infrastructure.frappe.historical_plan_piece_reader import (
            historical_geometry_piece, historical_v1_piece,
        )
        from almdina_erp.almdina_erp.infrastructure.frappe.orders.cut_dimension_plan_adapter import FrappeCutDimensionPlanAdapter
        fixture, order, _ = golden_case()
        for scenario in fixture['scenarios']:
            candidate = copy.deepcopy(order.pieces[0])
            candidate.__dict__.update(scenario['piece_overrides'])
            current = FrappeCutDimensionPlanAdapter.piece_row_as_dict(candidate)
            self.assertEqual(current, historical_v1_piece(candidate))
            self.assertEqual(workspace.freeze_geometry_piece(
                {key: value for key, value in current.items() if key not in workspace._COMMERCIAL_PIECE_KEYS}
            ), historical_geometry_piece(candidate))


if __name__ == '__main__':
    unittest.main()
