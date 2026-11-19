"""Private, site-scoped Redis artifacts; TTL owns cleanup, no public File URLs."""

from __future__ import annotations

import json
import re
import time
import zlib

import frappe

from almdina_erp.almdina_erp.application.cutting.search_report import (
    canonical_json,
    fingerprint,
)

REPORT_TTL_SECONDS = 24 * 60 * 60
_ID = re.compile(r"^[a-f0-9]{32}$")


class FrappeCuttingSearchReportStore:
    @staticmethod
    def _key(report_id):
        if not _ID.fullmatch(str(report_id or "")):
            raise ValueError("invalid_report_id")
        return f"almdina:cutting-search-report:{frappe.local.site}:{report_id}"

    def put(self, data, *, order_name, user):
        key = self._key(data["report_id"])
        envelope = dict(
            site=frappe.local.site,
            user=user,
            order_name=order_name,
            expires_at=time.time() + REPORT_TTL_SECONDS,
            data=data,
        )
        packed = zlib.compress(canonical_json(envelope).encode("utf-8"))
        frappe.cache.set_value(key, packed, expires_in_sec=REPORT_TTL_SECONDS)

    def get(self, report_id, *, order_name, user):
        try:
            packed = frappe.cache.get_value(self._key(report_id))
        except ValueError:
            return None
        if not packed:
            return None
        try:
            envelope = json.loads(zlib.decompress(packed))
            if not isinstance(envelope, dict) or not isinstance(
                envelope.get("data"), dict
            ):
                return None
        except (ValueError, TypeError, zlib.error):
            return None
        if (
            envelope.get("site") != frappe.local.site
            or envelope.get("user") != user
            or envelope.get("order_name") != order_name
            or time.time() >= envelope.get("expires_at", 0)
        ):
            return None
        data = envelope["data"]
        expected = data.get("data_fingerprint")
        if (
            not expected
            or fingerprint({k: v for k, v in data.items() if k != "data_fingerprint"})
            != expected
        ):
            return None
        return data
