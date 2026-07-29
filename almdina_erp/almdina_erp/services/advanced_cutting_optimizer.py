"""Backward-compatible facade for the cutting-domain optimizer.

New code must import from ``almdina_erp.almdina_erp.domain.cutting.optimizer``.
"""

from almdina_erp.almdina_erp.domain.cutting.optimizer import *  # noqa: F403
from almdina_erp.almdina_erp.domain.cutting.optimizer import (
    METHOD_CONFIGS,
    __all__ as _optimizer_all,
)

__all__ = [*_optimizer_all, "METHOD_CONFIGS"]
