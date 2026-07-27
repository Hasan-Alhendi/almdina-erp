from __future__ import annotations

import unittest
from pathlib import Path


WORKFLOW = Path(".github/workflows/frappe-v16-integration.yml")


class FrappeV16CIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_supported_frappe_v16_runtime_versions_are_used(self) -> None:
        self.assertIn('runs-on: ubuntu-24.04', self.source)
        self.assertIn('image: mariadb:11.8', self.source)
        self.assertIn('python-version: "3.14"', self.source)
        self.assertIn('node-version: "24"', self.source)
        self.assertIn('--python python3.14', self.source)

        self.assertNotIn('image: mariadb:10.6', self.source)
        self.assertNotIn('node-version: "22"', self.source)

    def test_toolchain_is_verified_before_bench_initialization(self) -> None:
        verify_index = self.source.index('- name: Verify Frappe v16 toolchain')
        init_index = self.source.index('- name: Initialize Frappe v16 bench')

        self.assertLess(verify_index, init_index)
        self.assertIn('mariadb-admin ping', self.source)
        self.assertIn('redis-cli -h 127.0.0.1 -p 13000 ping', self.source)
        self.assertIn('redis-cli -h 127.0.0.1 -p 11000 ping', self.source)
        self.assertIn('Expected Node 24+', self.source)

    def test_workflow_exercises_real_application_installation(self) -> None:
        required_steps = (
            'Initialize Frappe v16 bench',
            'Install ERPNext v16 and local app source',
            'Create integration site',
            'Install ERPNext and Almdina ERP',
            'Run migrate twice for idempotency',
            'Run Almdina ERP tests',
        )
        for step in required_steps:
            self.assertIn(f'- name: {step}', self.source)


if __name__ == "__main__":
    unittest.main()
