"""Anonymized regression for V2 schema drift; golden hashes from Git parents."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_workspace as workspace

FIXTURE = Path(__file__).with_name('fixtures') / 'plan_fingerprint_golden.json'


def golden_case():
    fixture = json.loads(FIXTURE.read_text())
    order = SimpleNamespace(**(fixture['order'] | {
        'pieces': [SimpleNamespace(**row) for row in fixture['order']['pieces']],
    }))
    plan = SimpleNamespace(**fixture['plan'])
    plan.snapshot_json = '{}'
    plan.door_cutting_order = order.name
    return fixture, order, plan


class TestPlanFingerprintCompatibility(unittest.TestCase):
    def test_pre_oct22_hash_survives_an_unchanged_order(self):
        fixture, order, plan = golden_case()
        stored = fixture['contracts']['v2_pre_oct22']['sha256']
        self.assertNotEqual(stored, workspace.plan_input_fingerprint(order, plan))
        self.assertEqual(stored, workspace.freshness_expected_fingerprint(order, plan, stored))

    def test_new_fingerprints_have_an_explicit_new_version(self):
        fixture, order, plan = golden_case()
        self.assertEqual(fixture['contracts']['v3']['sha256'], workspace.plan_input_fingerprint(order, plan))

    def test_all_golden_contracts_are_fixed_and_supported(self):
        from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
        fixture, order, plan = golden_case()
        for name, case in fixture['contracts'].items():
            with self.subTest(contract=name):
                self.assertEqual(case['sha256'], fingerprint_payload(case['payload']))
                decision = workspace.plan_fingerprint_compatibility(order, plan, case['sha256'])
                self.assertTrue(decision.compatible)
                self.assertEqual(name if name != 'v2_current' else 'v2_oct22', decision.contract)

    def test_one_liner_json_must_equal_the_hashed_scalar_fields(self):
        from almdina_erp.almdina_erp.domain.orders.liner_specs import door_liner_fields, door_liners_from_source
        _, order, plan = golden_case()
        row = order.pieces[0]
        row.extra_liner, row.liner_reference_side = 1, 'edge_long_left'
        row.liner_width_cm, row.liner_offset_cm = 1.8, 3.0
        row.liner_start_cm, row.liner_length_cm = 2.0, 65.0
        stored = workspace.plan_input_fingerprint(order, plan, version=2, omitted=('liner_specs_json',))
        row.__dict__.update(door_liner_fields(door_liners_from_source(row)))
        self.assertTrue(workspace.plan_fingerprint_compatibility(order, plan, stored).compatible)
        original = row.liner_specs_json
        for field, value in [('offset_cm', 4), ('length_cm', 50), ('start_cm', 8), ('side', 'edge_long_right')]:
            with self.subTest(field=field):
                data = json.loads(original)
                data['liners'][0][field] = value
                row.liner_specs_json = json.dumps(data)
                self.assertEqual('MISMATCH', workspace.plan_fingerprint_compatibility(order, plan, stored).state)
        data = json.loads(original)
        data['liners'].append(data['liners'][0] | {'id': 'liner_2', 'offset_cm': 10})
        row.liner_specs_json = json.dumps(data)
        self.assertEqual('MISMATCH', workspace.plan_fingerprint_compatibility(order, plan, stored).state)
        data = json.loads(original)
        data['width_cm'] = 2.0
        row.liner_specs_json = json.dumps(data)
        self.assertEqual('MISMATCH', workspace.plan_fingerprint_compatibility(order, plan, stored).state)
        row.liner_specs_json = '{invalid'
        self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, stored).state)

    def test_pre_double_contract_cannot_drop_double_or_sides(self):
        fixture, order, plan = golden_case()
        stored = fixture['contracts']['v2_pre_oct21']['sha256']
        for field, value in [('extra_double', 1), ('extra_double_reference_sides', 'edge_long_left')]:
            with self.subTest(field=field):
                setattr(order.pieces[0], field, value)
                self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, stored).state)
                setattr(order.pieces[0], field, fixture['order']['pieces'][0][field])

    def test_new_contract_detects_each_manufacturing_change(self):
        fixture, order, plan = golden_case()
        plan.snapshot_json = json.dumps({'input_fingerprint_contract': 3})
        stored = fixture['contracts']['v3']['sha256']
        changes = dict(width_cm=42, cut_width_cm=42, length_cm=82, cut_length_cm=82,
                       qty=3, allow_rotation=0, extra_full_door_double=1, extra_double=1,
                       extra_double_reference_sides='edge_long_left', edge_long_right=1,
                       edge_long_thickness_mm=2, clipped_corner_width_cm=10,
                       clipped_corner_length_cm=10, clipped_corner_position='Top Right',
                       piece_type='L-Shaped Corner', special_shape_geometry_json='{"outline":[]}',
                       liner_specs_json='{"width_cm":1.8,"liners":[]}',
                       extra_back_groove=1, extra_recessed_handle_cutout=1)
        for field, value in changes.items():
            with self.subTest(field=field):
                candidate = copy.deepcopy(order)
                row = candidate.pieces[0]
                setattr(row, field, value)
                if field == 'extra_back_groove':
                    row.back_groove_reference_side, row.back_groove_width_cm = 'edge_long_left', .7
                if field == 'extra_recessed_handle_cutout':
                    row.recessed_handle_reference_side, row.recessed_handle_width_cm = 'edge_long_left', 2.0
                self.assertEqual('MISMATCH', workspace.plan_fingerprint_compatibility(candidate, plan, stored).state)
        for field, value in [('full_board_width_mm', 1200), ('full_board_length_mm', 2400), ('revision', 3)]:
            candidate = copy.deepcopy(order)
            setattr(candidate, field, value)
            self.assertEqual('MISMATCH', workspace.plan_fingerprint_compatibility(candidate, plan, stored).state)
        plan.kerf_mm = 8
        self.assertEqual('MISMATCH', workspace.plan_fingerprint_compatibility(order, plan, stored).state)

    def test_glass_margin_cannot_disappear_via_legacy_fallback(self):
        _, order, plan = golden_case()
        row = order.pieces[0]
        row.piece_type, row.glass_margin_mm = 'Glass', 50
        stored = workspace.plan_input_fingerprint(order, plan, version=2, omitted=('liner_specs_json',))
        row.glass_margin_mm = 70
        self.assertFalse(workspace.plan_fingerprint_compatibility(order, plan, stored).compatible)

    def test_non_manufacturing_labels_are_excluded(self):
        _, order, plan = golden_case()
        stored = workspace.plan_input_fingerprint(order, plan)
        order.board_description, order.customer, order.edge_color = 'Other', 'Other', 'Other'
        order.pieces[0].notes, order.pieces[0].edge_rate_usd = 'Other', 99
        self.assertEqual(stored, workspace.plan_input_fingerprint(order, plan))

    def test_unverifiable_and_future_contracts_fail_closed_without_mutation(self):
        fixture, order, plan = golden_case()
        before = copy.deepcopy((vars(order), vars(plan)))
        self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, 'unknown').state)
        self.assertEqual(before, (vars(order), vars(plan)))
        for marker in [4, '3', True]:
            plan.snapshot_json = json.dumps({'input_fingerprint_contract': marker})
            self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, fixture['contracts']['v3']['sha256']).state)
            self.assertNotEqual(fixture['contracts']['v3']['sha256'], workspace.freshness_expected_fingerprint(order, plan, fixture['contracts']['v3']['sha256']))
        plan.snapshot_json = 'invalid json'
        self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, 'unknown').state)

    def test_unknown_geometry_field_requires_an_explicit_new_schema(self):
        from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import freeze_geometry_piece, PlanFingerprintContractError
        with self.assertRaises(PlanFingerprintContractError):
            freeze_geometry_piece({'width_cm': 20, 'future_machining_field': 1})

    def test_legacy_dimension_change_has_independent_snapshot_evidence(self):
        fixture, order, plan = golden_case()
        plan.snapshot_json = json.dumps({'manufacturing_requirements': workspace._manufacturing_requirements(order)})
        order.pieces[0].cut_width_cm += 2
        self.assertEqual('MISMATCH', workspace.plan_fingerprint_compatibility(order, plan, fixture['contracts']['v2_pre_oct22']['sha256']).state)

    def test_100_and_500_piece_compatibility_is_bounded(self):
        from time import perf_counter
        for count in (100, 500):
            _, order, plan = golden_case()
            order.pieces = [copy.deepcopy(order.pieces[0]) for _ in range(count)]
            stored = workspace.plan_input_fingerprint(order, plan, version=2, omitted=('liner_specs_json',))
            start = perf_counter()
            self.assertTrue(workspace.plan_fingerprint_compatibility(order, plan, stored).compatible)
            elapsed = perf_counter() - start
            self.assertLess(elapsed, 1.0, f'{count} pieces took {elapsed:.3f}s')


class TestPlanFingerprintServiceIntegration(unittest.TestCase):
    def test_compatible_approved_save_never_writes_or_cancels(self):
        from unittest.mock import patch, Mock
        import frappe
        from almdina_erp.almdina_erp.services import cutting_plan_invalidation_service as service
        fixture, order, plan = golden_case()
        plan.input_fingerprint = fixture['contracts']['v2_pre_oct22']['sha256']
        order.approved_plan = plan.name
        before = copy.deepcopy((vars(order), vars(plan)))
        writes = Mock(side_effect=AssertionError('compatible save wrote to DB'))
        with patch.object(frappe, 'get_doc', return_value=plan, create=True), \
             patch.object(frappe.db, 'exists', return_value=True, create=True), \
             patch.object(frappe.db, 'set_value', writes, create=True):
            self.assertIsNone(service.apply_stale_approved_plan_cancellation(order))
        writes.assert_not_called()
        self.assertEqual(before, (vars(order), vars(plan)))

    def test_genuine_change_cancels_approval_through_existing_lifecycle(self):
        from unittest.mock import patch, Mock
        import frappe
        from almdina_erp.almdina_erp.services import cutting_plan_invalidation_service as service
        fixture, order, plan = golden_case()
        plan.input_fingerprint = fixture['contracts']['v3']['sha256']
        plan.snapshot_json = json.dumps({'input_fingerprint_contract': 3})
        order.approved_plan = plan.name
        order.pieces[0].cut_width_cm += 1
        writes = Mock()
        with patch.object(frappe, 'get_doc', return_value=plan, create=True), \
             patch.object(frappe.db, 'exists', return_value=True, create=True), \
             patch.object(frappe.db, 'set_value', writes, create=True), \
             patch.object(frappe, 'clear_document_cache', create=True):
            self.assertEqual(plan.name, service.apply_stale_approved_plan_cancellation(order))
        self.assertIsNone(order.approved_plan)
        self.assertEqual('status', writes.call_args_list[0].args[2])
        self.assertEqual('Cancelled', writes.call_args_list[0].args[3])
        self.assertTrue(all(call.args[0] == 'Cutting Plan' for call in writes.call_args_list))

    def test_unverifiable_legacy_save_preserves_approval_but_runtime_fails_closed(self):
        from unittest.mock import patch, Mock
        import frappe
        from almdina_erp.almdina_erp.services import cutting_plan_invalidation_service as service
        _, order, plan = golden_case()
        plan.input_fingerprint = 'unknown'
        order.approved_plan = plan.name
        writes = Mock(side_effect=AssertionError('uncertainty rewrote approval'))
        with patch.object(frappe, 'get_doc', return_value=plan, create=True), \
             patch.object(frappe.db, 'exists', return_value=True, create=True), \
             patch.object(frappe.db, 'set_value', writes, create=True):
            self.assertIsNone(service.apply_stale_approved_plan_cancellation(order))
        self.assertEqual(plan.name, order.approved_plan)
        self.assertNotEqual(plan.input_fingerprint, workspace.freshness_expected_fingerprint(order, plan, plan.input_fingerprint))

    def test_cancelled_and_superseded_are_never_reapproved(self):
        from unittest.mock import patch, Mock
        import frappe
        from almdina_erp.almdina_erp.services import cutting_plan_invalidation_service as service
        fixture, order, plan = golden_case()
        plan.input_fingerprint = fixture['contracts']['v2_pre_oct22']['sha256']
        order.approved_plan = plan.name
        for status in ['Cancelled', 'Superseded']:
            plan.status = status
            writes = Mock(side_effect=AssertionError('historical state changed'))
            with patch.object(frappe, 'get_doc', return_value=plan, create=True), \
                 patch.object(frappe.db, 'exists', return_value=True, create=True), \
                 patch.object(frappe.db, 'set_value', writes, create=True):
                self.assertIsNone(service.apply_stale_approved_plan_cancellation(order))
            self.assertEqual(status, plan.status)

    def test_display_save_and_approval_share_the_historical_decision(self):
        from unittest.mock import patch
        from almdina_erp.almdina_erp.services import cutting_plan_command_service as command
        from almdina_erp.almdina_erp.services import cutting_plan_workspace_query_service as query
        fixture, order, plan = golden_case()
        plan.status, plan.validation_status = 'Draft', 'Valid'
        plan.cost_snapshot_version = command.COST_SNAPSHOT_VERSION
        plan.dxf_file, plan.dxf_status, plan.saw_center_status = '/private/files/golden.dxf', 'Validated', 'Absent'
        plan.input_fingerprint = fixture['contracts']['v2_pre_oct22']['sha256']
        before = copy.deepcopy((vars(order), vars(plan)))
        command._assert_plan_ready_for_approval(order, plan)
        with patch.object(query, '_prefer_original_upload_for_row', return_value=True):
            payload = query._plan_row_with_freshness(order, vars(plan), plan.snapshot_json)
        self.assertEqual('COMPATIBLE', payload['validation']['freshness_state'])
        self.assertFalse(payload['validation']['needs_recalculation'])
        self.assertEqual(before, (vars(order), vars(plan)))
        plan.plan_needs_recalculation = 1
        with patch.object(query, '_prefer_original_upload_for_row', return_value=True):
            payload = query._plan_row_with_freshness(order, vars(plan), plan.snapshot_json)
        self.assertTrue(payload['validation']['needs_recalculation'])
        self.assertEqual('PERSISTED_STALE', payload['validation']['freshness_state'])
        import frappe
        with self.assertRaises(frappe.ValidationError):
            command._assert_plan_ready_for_approval(order, plan)
        self.assertEqual(1, plan.plan_needs_recalculation)

    def test_verification_errors_are_visible_and_block_new_approval(self):
        from unittest.mock import patch
        from almdina_erp.almdina_erp.services import cutting_plan_workspace_query_service as query
        fixture, order, plan = golden_case()
        plan.input_fingerprint = fixture['contracts']['v2_pre_oct22']['sha256']
        order.pieces[0].cut_width_cm = None
        with patch.object(query, '_prefer_original_upload_for_row', return_value=True):
            payload = query._plan_row_with_freshness(order, vars(plan), plan.snapshot_json)
        self.assertTrue(payload['validation']['needs_recalculation'])
        self.assertEqual('REVIEW_REQUIRED', payload['validation']['freshness_state'])

    def test_paginated_audit_is_read_only_and_excludes_sensitive_fields(self):
        from unittest.mock import patch, Mock
        import frappe
        from almdina_erp.almdina_erp.services import cutting_plan_fingerprint_audit as audit
        fixture, order, plan = golden_case()
        order.check_permission = Mock()
        plan.input_fingerprint = fixture['contracts']['v2_pre_oct22']['sha256']
        plans = {}
        for i, status in enumerate(['Approved', 'Cancelled', 'Superseded', 'Draft']):
            entry = copy.deepcopy(plan)
            entry.name, entry.status = f'GOLDEN-{i}', status
            entry.plan_needs_recalculation = int(status == 'Draft')
            entry.door_cutting_order = order.name
            plans[entry.name] = entry
        writes = Mock(side_effect=AssertionError('audit wrote to DB'))
        with patch.object(frappe, 'get_list', side_effect=[list(plans.values()), []], create=True) as listing, \
             patch.object(frappe, 'get_doc', side_effect=lambda dt, name: order if dt == 'Door Cutting Order' else plans[name], create=True), \
             patch.object(frappe.db, 'set_value', writes, create=True), \
             patch.object(audit, 'require_cutting_plan_capability') as capability:
            result = audit.audit_uploaded_plan_fingerprints()
        self.assertEqual(['COMPATIBLE', 'HISTORICAL_REVIEW_REQUIRED', 'HISTORICAL_REVIEW_REQUIRED', 'PERSISTED_STALE'], [r['classification'] for r in result])
        self.assertEqual(4, capability.call_count)
        self.assertEqual(4, listing.call_args_list[1].kwargs['limit_start'])
        self.assertTrue(all(set(row) == {'order','plan','revision','status','classification','reason','contract'} for row in result))
        writes.assert_not_called()

    def test_draft_invalidation_uses_the_same_decision_without_resetting_flags(self):
        from unittest.mock import patch, Mock
        import frappe
        from almdina_erp.almdina_erp.services import cutting_plan_invalidation_service as service
        for changed, already_stale in [(False, False), (True, False), (False, True)]:
            fixture, order, plan = golden_case()
            plan.status = 'Draft'
            plan.plan_needs_recalculation = int(already_stale)
            plan.input_fingerprint = fixture['contracts']['v3' if changed else 'v2_pre_oct22']['sha256']
            if changed:
                plan.snapshot_json = json.dumps({'input_fingerprint_contract': 3})
                order.pieces[0].qty += 1
            writes = Mock()
            with patch.object(frappe, 'get_all', side_effect=[[plan.name], []], create=True), \
                 patch.object(frappe, 'get_doc', return_value=plan, create=True), \
                 patch.object(frappe.db, 'set_value', writes, create=True), \
                 patch.object(frappe, 'clear_document_cache', create=True):
                result = service.invalidate_stale_draft_plans(order)
            self.assertEqual((plan.name,) if changed else (), result)
            if changed:
                self.assertEqual(('Cutting Plan', plan.name, 'plan_needs_recalculation', 1), writes.call_args.args)
            else:
                writes.assert_not_called()
