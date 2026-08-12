from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "workforce_service.py"


def function_block(source: str, name: str, next_name: str | None) -> str:
    start = source.index(f"def {name}(")
    end = source.index(f"def {next_name}(", start) if next_name else len(source)
    return source[start:end]


class TestWorkforceServiceAuthorizationOrder(unittest.TestCase):
    def test_adoption_authorizes_before_lock_and_lookup(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        block = function_block(
            source,
            "adopt_workforce_user",
            "update_workforce_user",
        )
        authorization = block.index("_require_action(WorkforceAction.CREATE)")
        self.assertLess(authorization, block.index("_repository.lock_user"))
        self.assertLess(authorization, block.index("_repository.get_user"))
        self.assertLess(authorization, block.index("_repository.adopt_user"))

    def test_update_authorizes_before_lock_and_lookup(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        block = function_block(
            source,
            "update_workforce_user",
            "set_workforce_user_enabled",
        )
        authorization = block.index("_require_any_action_capability")
        self.assertLess(authorization, block.index("_repository.lock_user"))
        self.assertLess(authorization, block.index("_repository.get_user"))

    def test_enable_disable_authorizes_before_lock_and_lookup(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        block = function_block(
            source,
            "set_workforce_user_enabled",
            "reset_workforce_password",
        )
        authorization = block.index("_require_any_action_capability")
        self.assertLess(authorization, block.index("_repository.lock_user"))
        self.assertLess(authorization, block.index("_repository.get_user"))

    def test_password_reset_authorizes_before_lock_and_lookup(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        block = function_block(
            source,
            "reset_workforce_password",
            "get_workforce_user_audit",
        )
        authorization = block.index("_require_any_action_capability")
        self.assertLess(authorization, block.index("_repository.lock_user"))
        self.assertLess(authorization, block.index("_repository.get_user"))


if __name__ == "__main__":
    unittest.main()
