"""Backward-compatible import facade for the pure cutting domain.

New code must import from ``almdina_erp.almdina_erp.domain.cutting``. This
module preserves the historical public API while callers migrate.
"""

from almdina_erp.almdina_erp.domain.cutting import *  # noqa: F403
from almdina_erp.almdina_erp.domain.cutting import __all__
