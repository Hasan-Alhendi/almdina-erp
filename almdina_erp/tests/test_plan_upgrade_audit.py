"""Bounded, read-only audit of synthetic mixed-source plan histories."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from almdina_erp.tests.test_plan_fingerprint_compatibility import golden_case
from almdina_erp.almdina_erp.services import cutting_plan_fingerprint_audit as audit
import frappe


class TestPlanUpgradeAudit(unittest.TestCase):
    def test_uploaded_attachment_requires_the_exact_private_plan_link(self):
        from almdina_erp.almdina_erp.services import dxf_export_service as export
        plan = SimpleNamespace(name='SYN-PLAN', dxf_file='/private/files/synthetic.dxf')
        file = SimpleNamespace(is_private=1, attached_to_doctype='Cutting Plan',
                               attached_to_name=plan.name, attached_to_field='dxf_file')
        with patch.object(export, '_dxf_file_row', return_value=file), \
             patch.object(export, '_existing_dxf_disk_path', return_value='/isolated/synthetic.dxf'):
            self.assertEqual('AVAILABLE', audit._dxf_attachment_status(plan, 'Uploaded DXF', verify_files=True))
            file.attached_to_name = 'SOMEONE-ELSE'
            self.assertEqual('UNSCOPED', audit._dxf_attachment_status(plan, 'Uploaded DXF', verify_files=True))
        self.assertEqual('NOT_CHECKED', audit._dxf_attachment_status(plan, 'Uploaded DXF', verify_files=False))

    def test_thousands_of_plans_stream_in_pages_without_database_writes(self):
        from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import FingerprintCompatibility
        _, order, plan = golden_case()
        order.check_permission = Mock()
        plan.status, plan.source_type, plan.plan_needs_recalculation = 'Draft', 'System', 0
        plan.input_fingerprint = 'hash'
        rows = [dict(name=f'SYN-{n:05d}', door_cutting_order=order.name,
                     status='Draft', source_type='System', revision=5000 - n)
                for n in range(5000)]
        calls = []
        def get_list(_doctype, *, limit_start, limit_page_length, **kwargs):
            calls.append(limit_page_length)
            return rows[limit_start:limit_start + limit_page_length]
        with patch.object(frappe, 'get_list', side_effect=get_list, create=True), \
             patch.object(frappe, 'get_doc', side_effect=lambda dt, name: order if dt == 'Door Cutting Order' else plan, create=True), \
             patch.object(frappe.db, 'set_value', side_effect=AssertionError('audit wrote data'), create=True), \
             patch.object(audit, 'cutting_plan_capability_allowed', return_value=True), \
             patch.object(audit, 'plan_fingerprint_compatibility', return_value=FingerprintCompatibility('MATCH', 'hash')):
            summary = audit.audit_cutting_plan_summary(page_size=50)
        self.assertEqual(5000, summary['counts']['plans'])
        self.assertEqual(1, summary['counts']['lifecycle_candidate'])
        self.assertEqual(101, len(calls))
        self.assertEqual({50}, set(calls))

    def test_both_current_drafts_are_classified_and_flags_are_separate(self):
        fixture, order, original = golden_case()
        order.check_permission = Mock()
        order.approved_plan = None
        original.input_fingerprint = fixture['contracts']['v3']['sha256']
        original.plan_needs_recalculation = 0
        original.status = 'Draft'
        original.source_type = 'System'
        original.door_cutting_order = order.name
        uploaded = SimpleNamespace(**vars(original))
        uploaded.name, uploaded.source_type = 'UPLOADED', 'Uploaded DXF'
        uploaded.plan_needs_recalculation = 1
        rows = [original, uploaded]
        reads = []

        def get_list(_doctype, *, limit_start, limit_page_length, **kwargs):
            reads.append((limit_start, limit_page_length))
            return rows[limit_start: limit_start + limit_page_length]

        with patch.object(frappe, 'get_list', side_effect=get_list, create=True), \
             patch.object(frappe, 'get_doc', side_effect=lambda dt, name: order if dt == 'Door Cutting Order' else next(p for p in rows if p.name == name), create=True), \
             patch.object(frappe.db, 'set_value', side_effect=AssertionError('audit wrote data'), create=True), \
             patch.object(audit, 'cutting_plan_capability_allowed', return_value=True):
            result = list(audit.iter_cutting_plan_audit(page_size=1))
        self.assertEqual(2, len(result))
        self.assertTrue(all(entry['lifecycle_candidate'] for entry in result))
        self.assertEqual([True, True], [entry['fingerprint_compatible'] for entry in result])
        self.assertEqual([False, False], [entry['manufacturing_authorized'] for entry in result])
        self.assertEqual('PERSISTED_STALE', result[1]['classification'])
        self.assertEqual([(0, 1), (1, 1), (2, 1)], reads)

    def test_preflight_blocks_new_unexplained_loss(self):
        before = [{'plan': 'P1', 'manufacturing_authorized': True, 'classification': 'MATCH'}]
        after = [{'plan': 'P1', 'manufacturing_authorized': False, 'classification': 'REVIEW_REQUIRED'}]
        self.assertEqual('BLOCKED_BY_REGRESSION', audit.compare_upgrade_audits(before, after)['result'])

    def test_preflight_needs_complete_evidence_and_catches_file_or_lifecycle_loss(self):
        old = {'plan': 'SYN', 'audit_schema_version': 1, 'classification': 'MATCH',
               'status': 'Approved', 'manufacturing_authorized': True,
               'physical_inputs_sha': 'synthetic-physical-digest',
               'saved_layout_sha': 'synthetic-layout-digest',
               'dxf_attachment_status': 'AVAILABLE'}
        self.assertEqual('PASS', audit.compare_upgrade_audits([old], [dict(old)])['result'])
        self.assertEqual('BLOCKED_BY_REGRESSION', audit.compare_upgrade_audits(
            [old], [old | {'dxf_attachment_status': 'MISSING'}])['result'])
        self.assertEqual('REVIEW_REQUIRED', audit.compare_upgrade_audits(
            [old], [old | {'status': 'Cancelled'}])['result'])
        self.assertEqual('BLOCKED_BY_REGRESSION', audit.compare_upgrade_audits(
            [old], [old | {'dxf_attachment_status': 'NOT_CHECKED'}])['result'])
        self.assertEqual('REVIEW_REQUIRED', audit.compare_upgrade_audits(
            [old], [dict(old) | {'audit_schema_version': None}])['result'])
        changed = old | {'classification': 'REVIEW_REQUIRED'}
        result = audit.compare_upgrade_audits([old], [changed])
        self.assertEqual(1, result['contract_only_classification_changes'])
        altered = old | {'physical_inputs_sha': 'different-inputs'}
        result = audit.compare_upgrade_audits([old], [altered])
        self.assertEqual('REVIEW_REQUIRED', result['result'])
        self.assertEqual(1, result['physical_projection_changes'])


if __name__ == '__main__':
    unittest.main()
