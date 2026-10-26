"""Read-only manifest and comparison for an isolated restored Frappe site.

Run this script with the bench Python interpreter. The manifest is written to
an operator-selected local file; it contains order and plan identifiers only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    manifest = sub.add_parser("manifest")
    manifest.add_argument("--site", required=True, help="isolated restored site")
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--page-size", type=int, default=200)
    compare = sub.add_parser("compare")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()

    from almdina_erp.almdina_erp.services.cutting_plan_fingerprint_audit import (
        compare_upgrade_audits, iter_cutting_plan_audit,
    )
    if args.action == "compare":
        result = compare_upgrade_audits(
            json.loads(args.before.read_text()), json.loads(args.after.read_text())
        )
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(0 if result["result"] == "PASS" else 2)

    import frappe
    frappe.init(site=args.site)
    frappe.connect()
    # A partial employee view must never be mistaken for a full-site PASS.
    frappe.set_user("Administrator")
    temporary = args.output.with_suffix(args.output.suffix + ".partial")
    try:
        with temporary.open("w") as stream:
            stream.write("[")
            for index, item in enumerate(iter_cutting_plan_audit(page_size=args.page_size,
                                                                 verify_files=True)):
                if index:
                    stream.write(",")
                json.dump(item, stream, ensure_ascii=False)
            stream.write("]")
        os.replace(temporary, args.output)
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
