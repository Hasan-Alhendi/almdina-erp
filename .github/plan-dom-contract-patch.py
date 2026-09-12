from pathlib import Path

path = Path("almdina_erp/tests/test_frontend_consolidation_contract.py")
source = path.read_text(encoding="utf-8")
old = '        self.assertIn(\'.find(".dco-plan-actions-shell").first()\', simplify)\n'
new = '        self.assertIn(\'.children(".dco-plan-actions-shell").first()\', simplify)\n        self.assertNotIn("field.$wrapper.empty()", simplify)\n'
count = source.count(old)
if count != 1:
    raise SystemExit(f"expected one stale Plan action-shell assertion, found {count}")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
