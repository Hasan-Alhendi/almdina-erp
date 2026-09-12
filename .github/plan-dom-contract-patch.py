from pathlib import Path

path = Path("almdina_erp/tests/test_frontend_consolidation_contract.py")
source = path.read_text(encoding="utf-8")

replacements = [
    (
        '        self.assertIn(\'.find(".dco-plan-actions-shell").first()\', simplify)\n',
        '        self.assertIn(\'.children(".dco-plan-actions-shell").first()\', simplify)\n'
        '        self.assertNotIn("field.$wrapper.empty()", simplify)\n',
        "action-shell ownership lookup",
    ),
    (
        '            simplify.index("installApprovalAction(frm, field)"),\n',
        '            simplify.index("installApprovalAction(frm, shell)"),\n',
        "approval ownership scope",
    ),
]

for old, new, label in replacements:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one stale assertion, found {count}")
    source = source.replace(old, new, 1)

path.write_text(source, encoding="utf-8")
