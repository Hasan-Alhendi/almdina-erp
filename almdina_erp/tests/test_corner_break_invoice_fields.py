from __future__ import annotations

import ast
import unittest
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[1] / "almdina_erp" / "services"


def _tuple_constant(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return {elt.value for elt in node.value.elts}
    raise AssertionError(f"{name} not found in {path.name}")


class TestCornerBreakInvoiceFields(unittest.TestCase):
    """The invoice builder reads a fixed field whitelist; the corner-break
    strap length/rate must be in it or the invoice silently shows 0."""

    def test_piece_snapshots_carry_break_strap_length_and_rate(self) -> None:
        for filename, constant in (
            ("cost_document_service.py", "PIECE_DOCUMENT_FIELDS"),
            ("cost_permission_service.py", "PIECE_COST_FIELDS"),
        ):
            fields = _tuple_constant(SERVICES / filename, constant)
            self.assertIn("edge_break_length_cm", fields, filename)
            self.assertIn("edge_break_rate_usd", fields, filename)


if __name__ == "__main__":
    unittest.main()
