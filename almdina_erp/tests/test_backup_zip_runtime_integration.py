"""Full ZIP round trip against an isolated Frappe test site; no restore is run."""
from pathlib import Path
from tempfile import TemporaryDirectory

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.backups import get_backup_path

from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import FrappeBackupEngine
from almdina_erp.almdina_erp.infrastructure.backups.history import DOCTYPE, FrappeBackupHistory
from almdina_erp.almdina_erp.infrastructure.backups.zip_transfer import (
    download_response, import_zip, validate_import_restore,
)


class TestBackupZipRuntimeIntegration(FrappeTestCase):
    def test_native_backup_download_import_and_restore_eligibility(self):
        frappe.set_user("Administrator")
        engine = FrappeBackupEngine(ephemeral=True)
        operation_id = ""
        bundle = None
        try:
            bundle = engine.create()  # Real Frappe v16 BackupGenerator, including the site files.
            with TemporaryDirectory(prefix="almdina-zip-test-", dir=frappe.get_site_path("private")) as temp:
                package = Path(temp) / "backup.zip"
                response = download_response(bundle)
                try:
                    with package.open("wb") as stream:
                        for chunk in response.response:
                            stream.write(chunk)
                finally:
                    response.close()
                history = FrappeBackupHistory()
                operation_id = history.create(
                    operation_type="Imported", target="Local", requested_by="Administrator",
                )
                history.mark_running(operation_id)
                imported = import_zip(package, operation_id, history)
                selected = history.resolve_local_bundle(operation_id)
                self.assertEqual(selected.identifier, bundle.identifier)
                self.assertEqual({entry.kind for entry in selected.artifacts},
                                 {"database", "public_files", "private_files", "site_config"})
                validate_import_restore(history.get(operation_id)["import_app_versions"], selected)
                self.assertEqual(imported.total_size, bundle.total_size)
        finally:
            engine.release(bundle) if bundle else None
            if operation_id:
                frappe.db.delete(DOCTYPE, {"operation_id": operation_id})
            if bundle:
                root = Path(get_backup_path())
                for artifact in bundle.artifacts:
                    (root / artifact.filename).unlink(missing_ok=True)
                (root / f".almdina-imported-{bundle.identifier}").unlink(missing_ok=True)
            frappe.db.commit()
