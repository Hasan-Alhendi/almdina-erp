"""P0 regressions for execution safety and the immutable reviewed V3 contract."""
from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from almdina_erp.almdina_erp.application.shop_floor import commands
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts, decide_production_action,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import ProductionRoute, RoutingStage
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.tests.test_shop_floor_command_application import FakeShopFloorCommandRepository
from almdina_erp.tests.test_plan_fingerprint_compatibility import golden_case, FIXTURE
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_workspace as workspace


def pending_case(*, planning=False, status='Pending', stale=True):
    repo = FakeShopFloorCommandRepository()
    route = ProductionRoute('route-random', 'Route', (
        RoutingStage(10, 'area-a', 'Area A', 'role-a', planning),
        RoutingStage(20, 'area-b', 'Area B', 'role-b'),
    ))
    repo.routes[route.name] = route
    repo.orders['ORDER'] = commands.OrderState(
        'ORDER', 'At CNC', route.name, 'STAGE', True, stale,
        has_approved_plan=not stale, approved_plan_name='PLAN',
    )
    repo.stages['STAGE'] = commands.StageState(
        'STAGE', 'ORDER', 'area-a', status, repo.actor, 10,
    )
    return repo


class TestFingerprintManufacturingSafety(unittest.TestCase):
    def test_review_required_runtime_cannot_start_pending_manufacturing(self):
        from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_runtime_repository as runtime
        _, order, plan = golden_case()
        plan.input_fingerprint, plan.validation_status = 'unknown', 'Valid'
        self.assertEqual('REVIEW_REQUIRED', workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).state)
        with patch.object(runtime, 'approved_plan_for_order', return_value=plan):
            facts = runtime.production_plan_facts(order)
        self.assertTrue(facts.plan_needs_recalculation)
        repo = pending_case(stale=facts.plan_needs_recalculation)
        with self.assertRaises(commands.ShopFloorCommandError):
            commands.start_my_stage(repo, 'STAGE')
        self.assertFalse(any(c[0] == 'start_stage' for c in repo.calls))

    def test_review_required_pending_direct_handoff_cannot_bypass_start(self):
        repo = pending_case()
        repo.capabilities = {Capability.HANDOFF_ASSIGNED_STAGE}
        with self.assertRaises(commands.ShopFloorCommandError):
            commands.handoff_to_next(repo, 'STAGE', 'next@example.com')
        self.assertFalse(any(c[0] in {'complete_stage', 'create_stage'} for c in repo.calls))

    def test_planning_can_start_but_cannot_handoff_an_unverified_plan(self):
        repo = pending_case(planning=True)
        commands.start_my_stage(repo, 'STAGE')
        with self.assertRaises(commands.ShopFloorCommandError):
            commands.handoff_to_next(repo, 'STAGE', 'next@example.com')
        self.assertFalse(any(c[0] == 'complete_stage' for c in repo.calls))

    def test_running_work_can_finish_but_the_next_stage_cannot_start(self):
        for status in ('In Progress', 'Paused'):
            with self.subTest(status=status):
                repo = pending_case(status=status)
                result = commands.handoff_to_next(repo, 'STAGE', repo.actor)
                self.assertEqual('Completed', repo.stages['STAGE'].status)
                self.assertEqual('Pending', repo.stages[result['next_stage']].status)
                with self.assertRaises(commands.ShopFloorCommandError):
                    commands.start_my_stage(repo, result['next_stage'])

    def test_administrator_has_no_plan_safety_bypass(self):
        repo = pending_case()
        repo.actor, repo.admin = 'Administrator', True
        with self.assertRaises(commands.ShopFloorCommandError):
            commands.start_my_stage(repo, 'STAGE')

    def test_dispatch_depends_on_dynamic_planning_flag(self):
        for planning in (False, True):
            repo = pending_case(planning=planning)
            repo.orders['ORDER'] = replace(repo.orders['ORDER'], status='Draft', production_path=None, current_stage=None)
            if planning:
                commands.dispatch_order(repo, 'ORDER', 'route-random', repo.actor)
            else:
                with self.assertRaises(commands.ShopFloorCommandError):
                    commands.dispatch_order(repo, 'ORDER', 'route-random', repo.actor)

    def test_planning_can_start_without_a_plan_but_manufacturing_cannot(self):
        for planning in (False, True):
            repo = pending_case(planning=planning)
            repo.orders['ORDER'] = replace(repo.orders['ORDER'], has_cutting_plan=False)
            if planning:
                commands.start_my_stage(repo, 'STAGE')
            else:
                with self.assertRaises(commands.ShopFloorCommandError):
                    commands.start_my_stage(repo, 'STAGE')

    def test_offcut_execution_scope_is_preserved(self):
        for has_factory_work in (False, True):
            for stale in (False, True):
                repo = pending_case(stale=stale)
                repo.orders['ORDER'] = replace(repo.orders['ORDER'], has_factory_work=has_factory_work)
                if has_factory_work and not stale:
                    commands.start_my_stage(repo, 'STAGE')
                else:
                    with self.assertRaises(commands.ShopFloorCommandError):
                        commands.start_my_stage(repo, 'STAGE')

    def test_legacy_http_aliases_use_the_same_gate_and_arabic_translation(self):
        import csv
        import sys
        from almdina_erp.tests.test_shop_floor_command_adapter import AdapterHarness
        from almdina_erp.almdina_erp.services import production_service
        rpc = AdapterHarness().load()
        with (FIXTURE.parents[2] / 'translations/ar.csv').open() as handle:
            catalog = {row[0]: row[1] for row in csv.reader(handle) if len(row) >= 2}
        repo = pending_case()
        rpc._repository = repo
        rpc._ = lambda value: catalog.get(value, value)
        module_name = 'almdina_erp.almdina_erp.services.shop_floor_commands'
        previous = sys.modules.get(module_name)
        sys.modules[module_name] = rpc
        try:
            with self.assertRaisesRegex(RuntimeError, 'راجع خطة القص'):
                production_service.start_stage('STAGE', assigned_to='Administrator')
            repo.capabilities = {Capability.HANDOFF_ASSIGNED_STAGE}
            with patch.object(rpc, '_stage_completion_whatsapp_context', return_value=None):
                with self.assertRaisesRegex(RuntimeError, 'راجع خطة القص'):
                    production_service.finish_stage('STAGE')
        finally:
            # Restore only our seam. Restoring all of sys.modules discards
            # controllers loaded by Frappe while its metadata cache retains them.
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous
        self.assertFalse(any(c[0] in {'start_stage','complete_stage'} for c in repo.calls))

    def test_queries_and_list_use_the_same_dynamic_planning_safety_fact(self):
        from almdina_erp.almdina_erp.application.shop_floor import queries, order_list_query
        from almdina_erp.tests.test_shop_floor_query_application import FakeRepository
        for planning in (False, True):
            repo = pending_case(planning=planning)
            read = FakeRepository()
            read.user, read.routes = repo.actor, repo.routes
            order = dict(name='ORDER', status='At CNC', production_path='route-random',
                         current_production_stage='STAGE', has_cutting_plan=True,
                         plan_needs_recalculation=True)
            stage = {field: getattr(repo.stages['STAGE'], field)
                     for field in ('name','stage_type','status','assigned_to')}
            detail = queries._production_facts(read, order, stage)
            listed = order_list_query._production_facts(actor=repo.actor, actor_roles=(), order=order,
                        stage=stage, operational_role='role-a', route=repo.routes['route-random'])
            for facts in (detail, listed):
                decision = decide_production_action(Capability.START_ASSIGNED_STAGE,
                         capabilities={Capability.START_ASSIGNED_STAGE}, facts=facts)
                self.assertEqual(planning, decision.allowed)
                self.assertEqual(planning, facts.stage_is_planning)

    def test_persisted_stale_compatible_plan_cannot_start_new_manufacturing(self):
        from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_runtime_repository as runtime
        fixture, order, plan = golden_case()
        plan.input_fingerprint = fixture['contracts']['v2_pre_oct22']['sha256']
        plan.validation_status, plan.plan_needs_recalculation = 'Valid', 1
        self.assertTrue(workspace.plan_fingerprint_compatibility(order, plan, plan.input_fingerprint).compatible)
        with patch.object(runtime, 'approved_plan_for_order', return_value=plan):
            facts = runtime.production_plan_facts(order)
        repo = pending_case(stale=facts.plan_needs_recalculation)
        with self.assertRaises(commands.ShopFloorCommandError):
            commands.start_my_stage(repo, 'STAGE')
        self.assertEqual(1, plan.plan_needs_recalculation)


class TestV3RequiredRepresentation(unittest.TestCase):
    def test_deleting_a_required_geometry_key_fails_closed(self):
        from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import freeze_geometry_piece, PlanFingerprintContractError
        fixture, _, _ = golden_case()
        original = fixture['contracts']['v3']['payload']['pieces'][0]
        for key in original:
            candidate = dict(original)
            candidate.pop(key)
            with self.subTest(key=key), self.assertRaises(PlanFingerprintContractError):
                freeze_geometry_piece(candidate)

    def test_reviewed_v3_corpus_is_pinned_independently_of_expected_hashes(self):
        from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
        from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import FINGERPRINT_CONTRACT_VERSION
        # Immutable corpus reviewed at 0114e3be. New meanings need a new version
        # and new vectors; preserve this V3 corpus and its independent anchor.
        reviewed_digest = 'cd5fc91b2909b212574e4ec0ddce2016deec35dd770a4393e710b11f5f141ca6'
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(3, FINGERPRINT_CONTRACT_VERSION)
        self.assertEqual(reviewed_digest, fingerprint_payload(fixture))
        changed = copy.deepcopy(fixture)
        changed['contracts']['v3']['sha256'] = '0' * 64
        self.assertNotEqual(reviewed_digest, fingerprint_payload(changed))

    def test_live_adapter_normalization_drift_is_detected_by_existing_goldens(self):
        from almdina_erp.almdina_erp.infrastructure.frappe.orders.cut_dimension_plan_adapter import FrappeCutDimensionPlanAdapter
        fixture, order, plan = golden_case()
        scenario = fixture['scenarios'][0]
        order.pieces[0].__dict__.update(scenario['piece_overrides'])
        original = FrappeCutDimensionPlanAdapter.piece_row_as_dict
        self.assertEqual(scenario['sha256']['v3'], workspace.plan_input_fingerprint(order, plan))
        def rounded(row):
            data = original(row)
            data['width_cm'] = float(round(data['width_cm']))
            return data
        with patch.object(FrappeCutDimensionPlanAdapter, 'piece_row_as_dict', side_effect=rounded):
            self.assertNotEqual(scenario['sha256']['v3'], workspace.plan_input_fingerprint(order, plan))
        self.assertEqual(scenario['sha256']['v3'], workspace.plan_input_fingerprint(order, plan))

    def test_changed_primitive_normalization_and_incomplete_addons_fail_closed(self):
        from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import freeze_geometry_piece, PlanFingerprintContractError
        fixture, order, plan = golden_case()
        original = fixture['contracts']['v3']['payload']['pieces'][0]
        for field, value in [('width_cm', 40), ('qty', 2.0), ('allow_rotation', True)]:
            with self.subTest(field=field), self.assertRaises(PlanFingerprintContractError):
                freeze_geometry_piece({**original, field: value})
        with self.assertRaises(PlanFingerprintContractError):
            freeze_geometry_piece({**original, 'extra_liner': 1})
        with self.assertRaises(PlanFingerprintContractError):
            freeze_geometry_piece({**original, 'piece_type': 'Glass'})
        with self.assertRaises(PlanFingerprintContractError):
            workspace.plan_input_fingerprint(order, plan, version=3, omitted=('qty',))
        with self.assertRaises(PlanFingerprintContractError):
            workspace.plan_input_fingerprint(order, plan, version=4)

    def test_v3_schema_meaning_cannot_change_under_the_same_version(self):
        from almdina_erp.almdina_erp.domain.cutting import plan_fingerprint_contract as contract
        from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
        schema = {
            'version': contract.FINGERPRINT_CONTRACT_VERSION,
            'keys': sorted(contract.GEOMETRY_PIECE_KEYS),
            'required': sorted(contract._REQUIRED_PIECE_KEYS),
            'ints': sorted(contract._INTEGER_PIECE_KEYS),
            'strings': sorted(contract._STRING_PIECE_KEYS),
            'groups': sorted([sorted(group) for group in contract._MACHINING_GROUPS]),
        }
        reviewed_schema = 'cfd5ace5c091d9fe6c0c501a8bf6c7ea286009a71641c8daa5ecf8f5f9153093'
        self.assertEqual(reviewed_schema, fingerprint_payload(schema))
        for field in ('keys', 'required', 'ints', 'strings'):
            changed = copy.deepcopy(schema)
            changed[field].append('new_geometry_field')
            self.assertNotEqual(reviewed_schema, fingerprint_payload(changed))


class TestPersistedStaleEvidence(unittest.TestCase):
    def test_current_compatibility_does_not_prove_the_saved_flags_origin(self):
        from unittest.mock import Mock
        import frappe
        from almdina_erp.almdina_erp.services import cutting_plan_fingerprint_audit as audit
        results = []
        for history in ('contract_update', 'dimensions_changed_then_reverted'):
            fixture, order, plan = golden_case()
            order.check_permission = Mock()
            if history == 'dimensions_changed_then_reverted':
                old = order.pieces[0].cut_width_cm
                order.pieces[0].cut_width_cm += 2
                order.pieces[0].cut_width_cm = old
            plan.input_fingerprint = fixture['contracts']['v2_pre_oct22']['sha256']
            plan.plan_needs_recalculation = 1
            before = copy.deepcopy(vars(plan))
            write = Mock(side_effect=AssertionError('audit must not repair or persist'))
            with patch.object(frappe, 'get_list', side_effect=[[plan], []], create=True), \
                 patch.object(frappe, 'get_doc', side_effect=lambda dt, name: order if dt == 'Door Cutting Order' else plan, create=True), \
                 patch.object(frappe.db, 'set_value', write, create=True), \
                 patch.object(audit, 'require_cutting_plan_capability'):
                results.append(audit.audit_uploaded_plan_fingerprints())
            self.assertEqual(before, vars(plan))
            write.assert_not_called()
        self.assertEqual(results[0], results[1])
        self.assertEqual('PERSISTED_STALE', results[0][0]['classification'])
        self.assertEqual('stale_origin_not_recorded', results[0][0]['reason'])


class TestNativeStageActivationBoundary(unittest.TestCase):
    @staticmethod
    def validate(doc):
        # Run the actual controller method without needing a Desk/DB just to
        # construct Document. Real persistence is also exercised by Frappe CI.
        import ast
        import frappe
        from frappe.utils import cint
        source = (FIXTURE.parents[2] / 'almdina_erp/doctype/production_stage/production_stage.py').read_text()
        cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef))
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'validate')
        namespace = {'frappe': frappe, '_': frappe._, 'cint': cint}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'production_stage.validate', 'exec'), namespace)
        namespace['validate'](doc)

    @staticmethod
    def stage(old_status='Pending', target='In Progress'):
        from types import SimpleNamespace
        return SimpleNamespace(sequence=10, status=target, started_by='Administrator',
               start_time='2026-01-01 08:00:00', finish_time='2026-01-01 09:00:00',
               flags={}, is_new=lambda: old_status is None,
               get_doc_before_save=lambda: SimpleNamespace(status=old_status) if old_status else None)

    def test_native_pending_activation_cannot_bypass_central_commands(self):
        import frappe
        for old in ('Pending', 'Cancelled', 'Completed', None):
            for target in ('In Progress', 'Completed'):
                if old == target:
                    continue
                with self.subTest(old=old, target=target), self.assertRaises(frappe.ValidationError):
                    self.validate(self.stage(old, target))

    def test_only_server_owned_context_allows_native_activation_and_is_removed(self):
        from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_command_context import authorized_stage_activation, is_authorized_stage_activation
        import frappe
        for forged in (True, 1, 'Administrator', 'authorized'):
            doc = self.stage()
            doc.flags['_almdina_stage_activation'] = forged
            with self.assertRaises(frappe.ValidationError):
                self.validate(doc)
            with authorized_stage_activation(doc):
                self.assertTrue(is_authorized_stage_activation(doc))
                self.validate(doc)
            self.assertFalse(is_authorized_stage_activation(doc))
            self.assertEqual(forged, doc.flags['_almdina_stage_activation'])
        doc = self.stage()
        with self.assertRaises(RuntimeError):
            with authorized_stage_activation(doc):
                raise RuntimeError('rollback')
        self.assertFalse(is_authorized_stage_activation(doc))
        self.assertEqual({}, doc.flags)

    def test_native_continuation_of_running_work_and_pending_creation_stay_valid(self):
        for old, target in [('In Progress','Completed'), ('Paused','Completed'),
                            ('Paused','In Progress'), (None,'Pending'), ('Pending','Pending')]:
            with self.subTest(old=old, target=target):
                self.validate(self.stage(old, target))

    def test_real_frappe_document_uses_the_same_activation_boundary(self):
        import frappe
        if not hasattr(frappe, 'get_meta'):
            self.skipTest('Real Frappe Document is exercised by the MariaDB integration job')
        from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_command_context import authorized_stage_activation
        doc = frappe.get_doc({
            'doctype': 'Production Stage', 'sequence': 10, 'status': 'In Progress',
            'started_by': 'Administrator', 'start_time': '2026-01-01 08:00:00',
        })
        with self.assertRaises(frappe.ValidationError):
            doc.validate()
        with authorized_stage_activation(doc):
            doc.validate()
        with self.assertRaises(frappe.ValidationError):
            doc.validate()
