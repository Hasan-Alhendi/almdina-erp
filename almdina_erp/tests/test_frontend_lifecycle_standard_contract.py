from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT.parent / "docs" / "reference"
STANDARD = REFERENCE / "15_FRONTEND_LIFECYCLE_STANDARD.md"
DATA_UI_MAP = REFERENCE / "06_DATA_UI_MAP.md"
REFERENCE_INDEX = REFERENCE / "README.md"
FRONTEND_ARCHITECTURE = REFERENCE / "13_FRONTEND_ARCHITECTURE.md"
REFACTOR_CLOSURE = REFERENCE / "14_FRONTEND_REFACTOR_CLOSURE.md"
FOUNDATION = ROOT / "public" / "js" / "frontend_foundation.js"
FRONTEND_RUNTIME_ROOTS = (
    ROOT / "public" / "js",
    ROOT / "almdina_erp" / "page",
    ROOT / "almdina_erp" / "doctype",
    ROOT / "almdina_erp" / "report",
)
IGNORED_RUNTIME_DIRECTORIES = frozenset({"node_modules", "vendor", "dist", "build"})
FORBIDDEN_LIFECYCLE_PLATFORM_PATTERNS = (
    re.compile(r"\b(?:window\.)?AlmdinaLifecycle\b"),
    re.compile(r"\bAlmdinaLifecycle(?:Framework|Platform)\b"),
)

COMMON_RULE_IDS = tuple(f"FE-LC-{index:03d}" for index in range(1, 16))
PRIMARY_FAMILIES = (
    ("A", "Cached Frappe Custom Page"),
    ("B", "Frappe Form / Document"),
    ("C", "Collection Surface"),
    ("D", "Stateful Special Workspace"),
    ("E", "Global / Shared Runtime"),
)
COLLECTION_SUBCONTRACT_HEADINGS = (
    "C1 — Collection Surface / List View",
    "C2 — Collection Surface / Query Report",
)
SURFACE_NAMESPACES = (
    "PAGE",
    "FORM",
    "LIST",
    "REPORT",
    "WORKSPACE",
    "GLOBAL",
)
SHARED_PRIMITIVES = (
    "rpc",
    "requireAssets",
    "createLatestRequestGate",
    "createLifecycleScope",
    "ensureStylesheet",
)


def first_party_frontend_runtime_files() -> tuple[Path, ...]:
    files = []
    for root in FRONTEND_RUNTIME_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.js"):
            relative_parts = path.relative_to(root).parts
            if any(part in IGNORED_RUNTIME_DIRECTORIES for part in relative_parts):
                continue
            files.append(path)
    return tuple(sorted(files))


class TestFrontendLifecycleStandardContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.standard = STANDARD.read_text(encoding="utf-8")
        cls.data_ui_map = DATA_UI_MAP.read_text(encoding="utf-8")

    def test_standard_is_canonical_and_discoverable(self) -> None:
        self.assertTrue(STANDARD.is_file())
        self.assertIn("Canonical frontend lifecycle specialization", self.standard)
        self.assertIn("13 — Frontend Architecture", self.standard)

        for reference in (
            REFERENCE_INDEX,
            FRONTEND_ARCHITECTURE,
            REFACTOR_CLOSURE,
        ):
            with self.subTest(reference=reference.name):
                self.assertIn(
                    "15_FRONTEND_LIFECYCLE_STANDARD.md",
                    reference.read_text(encoding="utf-8"),
                )

        self.assertIn(
            "هذه الوثيقة تبقى المرجع الأعلى لتنظيم الواجهة",
            FRONTEND_ARCHITECTURE.read_text(encoding="utf-8"),
        )

    def test_shared_contract_ids_exist_exactly_once(self) -> None:
        for rule_id in COMMON_RULE_IDS:
            with self.subTest(rule_id=rule_id):
                self.assertEqual(self.standard.count(f"`{rule_id}`"), 1)

    def test_five_families_and_collection_subcontracts_are_explicit(self) -> None:
        for family, name in PRIMARY_FAMILIES:
            with self.subTest(family=family):
                self.assertIn(f"| {family} | {name} |", self.standard)

        for heading in COLLECTION_SUBCONTRACT_HEADINGS:
            with self.subTest(heading=heading):
                self.assertIn(f"### {heading}", self.standard)

        self.assertIn("Transient Child Surfaces", self.standard)
        self.assertIn("ليست lifecycle family مستقلة", self.standard)
        self.assertIn("Deactivate != Dispose", self.standard)

    def test_surface_specific_namespaces_are_present(self) -> None:
        identifiers = set(
            re.findall(
                r"`(FE-LC-(?:PAGE|FORM|LIST|REPORT|WORKSPACE|GLOBAL)-\d{3})`",
                self.standard,
            )
        )
        for namespace in SURFACE_NAMESPACES:
            with self.subTest(namespace=namespace):
                self.assertTrue(
                    any(identifier.startswith(f"FE-LC-{namespace}-") for identifier in identifiers),
                    f"Missing lifecycle namespace: {namespace}",
                )

    def test_certification_table_is_explicit_and_does_not_certify_by_helper(self) -> None:
        self.assertIn("## 8. Current Lifecycle Certification Status", self.standard)
        for row in (
            "| Factory Workforce | PAGE | Certified |",
            "| Factory Permissions | PAGE | Certified |",
            "| Factory Production Settings | PAGE | Certified |",
            "| Shop Floor Inbox | PAGE | Certified |",
            "| Factory Master Data | PAGE | Certified |",
            "| Factory Plan Archive | PAGE | Keep; lifecycle migration pending |",
            "| Factory Approval Queue | PAGE | Retired / Removed |",
            "| Factory Stock Settings | PAGE | Retired / Removed |",
            "| Factory System Preflight | PAGE | Retired / Removed |",
            "| Factory Performance Benchmark | PAGE | Retired / Removed |",
            "| Door Cutting Order | FORM | Specialized lifecycle exists; certification pending |",
            "| Door Cutting Order List | LIST | Certification pending |",
            "| Current Query Reports | REPORT | Frappe-owned/declarative; custom lifecycle not currently required |",
            "| Door Drawing | WORKSPACE | Existing lifecycle foundation; hardening/certification pending |",
            "| Global runtimes | GLOBAL | Audit/certification pending |",
        ):
            with self.subTest(row=row):
                self.assertIn(row, self.standard)

        self.assertIn("إثبات read/activation lifecycle فقط", self.standard)
        self.assertIn("لا يكفي لـFull Certification", self.standard)
        self.assertIn("وجود helper أو `requestId` منفرد لا يمنح certification", self.standard)

    def test_estate_policy_does_not_spend_lifecycle_work_on_retired_pages(self) -> None:
        self.assertIn("### 8.1 Frontend estate policy", self.standard)
        self.assertIn("**Temporary migration utility**", self.standard)
        self.assertIn("**Retired / Removed**", self.standard)
        self.assertIn("**Retirement planned; removal pending**", self.standard)
        self.assertIn("ليست مرشحًا للـlifecycle certification", self.standard)
        self.assertIn("runtime/data proof", self.standard)
        self.assertIn("Page-record", self.standard)

        for entry in (
            "`factory_approval_queue`: أزيل Page source",
            "`factory_stock_settings`: أزيل Page source",
            "`factory_system_preflight`: أزيل Page source",
            "`factory_performance_benchmark`: أزيل Page source",
        ):
            with self.subTest(entry=entry):
                self.assertIn(entry, self.data_ui_map)

    def test_retirement_audit_keeps_static_and_runtime_proof_separate(self) -> None:
        for marker in (
            "## 10. Frontend Estate Retirement Closure",
            "Pending Review` يساوي **0**",
            "Caller matrix النهائي",
            "reject_retired_approval_workflow",
            "remove_orphan_entities()",
            "`factory_plan_archive` تبقى مطلوبة",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.data_ui_map)

    def test_existing_foundation_remains_the_shared_primitive_owner(self) -> None:
        foundation = FOUNDATION.read_text(encoding="utf-8")
        for primitive in SHARED_PRIMITIVES:
            with self.subTest(primitive=primitive):
                self.assertIn(primitive, foundation)
                self.assertIn(f"`AlmdinaFrontend.{primitive}`", self.standard)

        self.assertIn("window.AlmdinaFrontend", foundation)
        self.assertIn("لا يوجد قرار بإنشاء lifecycle platform جديدة", self.standard)

    def test_first_party_frontend_has_no_parallel_lifecycle_platform(self) -> None:
        runtime_files = first_party_frontend_runtime_files()
        self.assertTrue(runtime_files)
        for path in runtime_files:
            source = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_LIFECYCLE_PLATFORM_PATTERNS:
                with self.subTest(path=path.relative_to(ROOT.parent), pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(source))

    def test_static_enforcement_does_not_claim_runtime_async_correctness(self) -> None:
        self.assertIn("Static source markers لا تثبت async correctness", self.standard)
        self.assertIn("ما يحتاج Runtime Regression", self.standard)
        self.assertNotIn("كل Page يجب أن تحتوي bindActivationLifecycle", self.standard)


if __name__ == "__main__":
    unittest.main()
