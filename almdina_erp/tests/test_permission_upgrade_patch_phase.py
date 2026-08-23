from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


PERMISSION_PATCHES = (
    "almdina_erp.patches.v1_0.bootstrap_legacy_role_capabilities",
    "almdina_erp.patches.v1_0.migrate_legacy_administration_capabilities",
    "almdina_erp.patches.v1_0.repair_capability_permission_projections",
    "almdina_erp.patches.v1_0.repair_order_input_permissions",
)


def _patch_sections() -> tuple[str, str]:
    patches = (ROOT / "patches.txt").read_text(encoding="utf-8")
    pre, post = patches.split("[post_model_sync]", 1)
    return pre, post


def test_permission_state_patches_run_only_after_model_sync() -> None:
    pre, post = _patch_sections()

    for patch in PERMISSION_PATCHES:
        assert patch not in pre
        assert patch in post


def test_permission_state_migration_finishes_before_canonical_reset() -> None:
    _, post = _patch_sections()
    reset = "almdina_erp.patches.v1_0.reset_canonical_permission_states"
    reset_index = post.index(reset)

    for patch in PERMISSION_PATCHES:
        assert post.index(patch) < reset_index
