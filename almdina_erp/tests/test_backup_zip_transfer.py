"""Focused ZIP round trip tests without a running Frappe site."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import types
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle


@pytest.fixture
def transfer(monkeypatch, tmp_path):
    site = "site.local"
    private = tmp_path / "private"
    root = private / "backups"
    root.mkdir(parents=True)
    frappe = types.ModuleType("frappe")
    frappe.__version__ = "16.17.5"
    frappe.local = SimpleNamespace(site=site)
    frappe.conf = SimpleNamespace(db_type="mariadb", get=lambda key, default=None: {"encryption_key": "key"}.get(key, default))
    frappe.get_installed_apps = lambda: ["frappe"]
    frappe.get_site_path = lambda *args: str(tmp_path.joinpath(*args))
    frappe.db = SimpleNamespace(exists=lambda *_args, **_kwargs: False, commit=lambda: None)
    backups = types.ModuleType("frappe.utils.backups")
    backups.get_backup_path = lambda: str(root)
    utils = types.ModuleType("frappe.utils")
    utils.__path__ = []
    utils.backups = backups
    frappe.utils = utils
    monkeypatch.setitem(sys.modules, "frappe", frappe)
    monkeypatch.setitem(sys.modules, "frappe.utils", utils)
    monkeypatch.setitem(sys.modules, "frappe.utils.backups", backups)
    package_name = "almdina_erp.almdina_erp.infrastructure.backups"
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "almdina_erp" / "infrastructure" / "backups")]
    monkeypatch.setitem(sys.modules, package_name, package)
    history = types.ModuleType(f"{package_name}.history")
    history.FrappeBackupHistory = type("FrappeBackupHistory", (), {})
    monkeypatch.setitem(sys.modules, history.__name__, history)
    path = Path(package.__path__[0]) / "zip_transfer.py"
    spec = importlib.util.spec_from_file_location("backup_zip_transfer_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, root, frappe


def bundle(root):
    prefix = "20261108_120000-site_local"
    values = {
        "database": ("database.sql.gz", gzip.compress(b"-- begin frappe metadata\n-- [frappe]\n-- version = 16.17.5\n-- end frappe metadata\nSELECT 1;")),
        "site_config": ("site_config_backup.json", b'{"encryption_key":"key"}'),
    }
    for kind, folder, suffix in (("public_files", "public", "files.tgz"), ("private_files", "private", "private-files.tgz")):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            data = b"backup contents"
            info = tarfile.TarInfo(f"sites/site.local/{folder}/files/sample.txt")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        values[kind] = (suffix, buffer.getvalue())
    artifacts = []
    for kind, (suffix, data) in values.items():
        path = root / f"{prefix}-{suffix}"
        path.write_bytes(data)
        artifacts.append(BackupArtifact(kind, str(path), path.name, len(data), hashlib.sha256(data).hexdigest()))
    return BackupBundle(prefix, tuple(artifacts))


def exported(module, source):
    response = module.download_response(source)
    try:
        return b"".join(response.response)
    finally:
        response.close()


class History:
    def __init__(self):
        self.completed = None

    def mark_completed(self, operation_id, result):
        self.completed = (operation_id, result)


def test_download_import_round_trip_keeps_current_database_untouched(transfer, tmp_path):
    module, root, _frappe = transfer
    source = bundle(root)
    data = exported(module, source)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert len(archive.infolist()) == 5
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        assert json.loads(archive.read("manifest.json"))["site"] == "site.local"
    target = root.parent / "new-backups"
    target.mkdir()
    module_root = sys.modules["frappe.utils.backups"]
    module_root.get_backup_path = lambda: str(target)
    input_zip = tmp_path / "input.zip"
    input_zip.write_bytes(data)
    history = History()
    result = module.import_zip(input_zip, "op", history)
    assert result.identifier == source.identifier
    assert len(list(target.glob("*.gz"))) == 1
    assert history.completed[0] == "op"
    assert (target / f".almdina-imported-{source.identifier}").exists()
    with pytest.raises(ValueError, match="duplicate"):
        module.import_zip(input_zip, "again", History())


@pytest.mark.parametrize("mutation,expected", [
    ("missing", "artifacts"), ("traversal", "artifacts"), ("wrong_site", "site"),
    ("wrong_version", "versions"), ("corrupt", "not a zip"), ("bad_checksum", "integrity"),
    ("bad_key", "encryption_key"), ("duplicate", "artifacts"),
])
def test_invalid_packages_never_publish(transfer, tmp_path, mutation, expected):
    module, root, _frappe = transfer
    source = bundle(root)
    original = exported(module, source)
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        files = [(name, archive.read(name)) for name in archive.namelist()]
    if mutation == "corrupt":
        content = b"not a zip"
    else:
        manifest = json.loads(files[0][1])
        if mutation == "wrong_site": manifest["site"] = "another.site"
        if mutation == "wrong_version": manifest["apps"]["frappe"] = "99.0.0"
        if mutation == "traversal": manifest["artifacts"][0]["filename"] = "../evil"
        if mutation == "bad_checksum": manifest["artifacts"][0]["sha256"] = "0" * 64
        if mutation == "bad_key":
            files = [(name, b'{"encryption_key":"wrong"}' if name.endswith("site_config_backup.json") else raw) for name, raw in files]
            changed = next(raw for name, raw in files if name.endswith("site_config_backup.json"))
            entry = next(row for row in manifest["artifacts"] if row["kind"] == "site_config")
            entry["size"] = len(changed)
            entry["sha256"] = hashlib.sha256(changed).hexdigest()
        files[0] = ("manifest.json", json.dumps(manifest).encode())
        if mutation == "missing": files.pop()
        if mutation == "duplicate": files.append(files[1])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, raw in files: archive.writestr(name, raw)
        content = buffer.getvalue()
    destination = root.parent / "target"
    destination.mkdir()
    sys.modules["frappe.utils.backups"].get_backup_path = lambda: str(destination)
    path = tmp_path / "input.zip"
    path.write_bytes(content)
    with pytest.raises((ValueError, zipfile.BadZipFile), match=expected):
        module.import_zip(path, "op", History())
    assert not list(destination.glob("*.gz"))


def test_publication_failure_rolls_back_partial_files(transfer, tmp_path, monkeypatch):
    module, root, _frappe = transfer
    source = bundle(root)
    input_zip = tmp_path / "input.zip"
    input_zip.write_bytes(exported(module, source))
    destination = root.parent / "target"
    destination.mkdir()
    sys.modules["frappe.utils.backups"].get_backup_path = lambda: str(destination)
    original_link = module.os.link
    attempts = 0

    def fail_second(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("storage unavailable")
        return original_link(*args)

    monkeypatch.setattr(module.os, "link", fail_second)
    history = History()
    with pytest.raises(OSError, match="storage unavailable"):
        module.import_zip(input_zip, "op", history)
    assert history.completed is None
    assert not list(destination.glob("*.gz"))
    assert not list(destination.glob(".almdina-imported-*"))


def test_inner_archive_with_other_site_path_is_rejected(transfer, tmp_path):
    module, root, _frappe = transfer
    source = bundle(root)
    initial = exported(module, source)
    with zipfile.ZipFile(io.BytesIO(initial)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    name = next(name for name in files if name.endswith("-files.tgz"))
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        content = b"other tenant"
        info = tarfile.TarInfo("sites/other.site/public/files/alien.txt")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    files[name] = buffer.getvalue()
    manifest = json.loads(files["manifest.json"])
    entry = next(row for row in manifest["artifacts"] if row["filename"] == name)
    entry["size"] = len(files[name])
    entry["sha256"] = hashlib.sha256(files[name]).hexdigest()
    files["manifest.json"] = json.dumps(manifest).encode()
    input_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(input_zip, "w", compression=zipfile.ZIP_STORED) as archive:
        for filename, data in files.items():
            archive.writestr(filename, data)
    destination = root.parent / "target"
    destination.mkdir()
    sys.modules["frappe.utils.backups"].get_backup_path = lambda: str(destination)
    with pytest.raises(ValueError, match="files"):
        module.import_zip(input_zip, "op", History())
    assert not list(destination.glob("*.tgz"))


def test_retention_skips_imported_marker_and_fails_closed(transfer, monkeypatch):
    _module, root, frappe = transfer
    package = sys.modules["almdina_erp.almdina_erp.infrastructure.backups"]
    spec = importlib.util.spec_from_file_location("backup_adapter_under_test", Path(package.__path__[0]) / "frappe_backup.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    imported = bundle(root)
    (root / f".almdina-imported-{imported.identifier}").touch()
    other = "20261107_120000-site_local"
    (root / f"{other}-database.sql.gz").write_bytes(b"db")
    calls = []
    cleanup = types.ModuleType("frappe.desk.page.backups.backups")
    cleanup.cleanup_old_backups = lambda groups, limit: calls.append((groups, limit))
    for name in ("frappe.desk", "frappe.desk.page", "frappe.desk.page.backups"):
        part = types.ModuleType(name)
        part.__path__ = []
        monkeypatch.setitem(sys.modules, name, part)
    monkeypatch.setitem(sys.modules, cleanup.__name__, cleanup)
    frappe.get_all = lambda *_args, **_kwargs: []
    adapter.FrappeLocalRetention().apply(1)
    assert set(calls[0][0]) == {other}
    frappe.get_all = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable"))
    with pytest.raises(RuntimeError, match="database unavailable"):
        adapter.FrappeLocalRetention().apply(1)
    assert len(calls) == 1


def test_restore_finalization_preserves_imported_source(transfer, tmp_path, monkeypatch):
    _module, _root, frappe = transfer
    package = sys.modules["almdina_erp.almdina_erp.infrastructure.backups"]
    source = Path(package.__path__[0]) / "restore_runner.py"
    spec = importlib.util.spec_from_file_location("restore_runner_under_test", source)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    folder = tmp_path / "private" / "backup_restore_requests"
    folder.mkdir()
    target = {"identifier": "20261108_120000-site_local", "manifest": [], "total_size": 12}
    path = folder / "restore-op.json"
    path.write_text(json.dumps({
        "site": "site.local", "source_operation_id": "import-op", "source_operation_type": "Imported",
        "safety_operation_id": "safety-op", "operation_id": "restore-op", "target": target,
        "safety": target, "requested_by": "owner@example.com",
    }))
    history_module = sys.modules[f"{package.__name__}.history"]
    history_module.DOCTYPE = "Almdina Backup Operation"
    restore_module = types.ModuleType(f"{package.__name__}.restore")
    restore_module.REQUEST_FOLDER = "backup_restore_requests"
    monkeypatch.setitem(sys.modules, restore_module.__name__, restore_module)
    frappe.utils.now = lambda: "2026-11-08 12:00:00"
    rows = {}
    frappe.db.exists = lambda _doctype, name: name in rows
    frappe.db.set_value = lambda _doctype, name, values, **_kwargs: rows[name].update(values)

    def get_doc(data):
        return SimpleNamespace(insert=lambda **_kwargs: rows.__setitem__(data["operation_id"], data))

    frappe.get_doc = get_doc
    runner.finalize_restore(str(path), "Completed")
    assert rows["import-op"]["operation_type"] == "Imported"
    assert rows["import-op"]["status"] == "Completed"
    assert not path.exists()


def test_chunk_upload_enforces_owner_order_and_separate_restore_capability(transfer, tmp_path, monkeypatch):
    zip_module, _root, frappe = transfer
    package = sys.modules["almdina_erp.almdina_erp.infrastructure.backups"]
    history_module = sys.modules[f"{package.__name__}.history"]
    rows = {}

    class UploadHistory:
        def create(self, *, operation_type, target, requested_by):
            rows["a" * 32] = dict(operation_type=operation_type, target=target, requested_by=requested_by, status="Queued")
            return "a" * 32

        def get(self, operation_id):
            return rows.get(operation_id)

        def set_upload_size(self, operation_id, size):
            rows[operation_id]["total_size"] = size

        def mark_failed(self, operation_id, code):
            rows[operation_id].update(status="Failed", error_summary=code)

        def mark_running(self, operation_id):
            rows[operation_id]["status"] = "Running"

    history_module.FrappeBackupHistory = UploadHistory
    for suffix, attributes in {
        "frappe_backup": {"FrappeBackupEngine": object, "FrappeLocalRetention": object},
        "restore": {"launch_restore_runner": lambda *_: None, "restore_runtime_ready": lambda: False, "write_restore_request": lambda **_: None},
        "sftp": {"SFTPBackupGateway": object, "SFTPGatewayError": ValueError, "SSHConfig": object},
        "zip_transfer": {"download_response": zip_module.download_response, "import_zip": zip_module.import_zip, "upload_limit": lambda: 100},
    }.items():
        stub = types.ModuleType(f"{package.__name__}.{suffix}")
        stub.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, stub.__name__, stub)
    auth = types.ModuleType("almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway")
    auth.doctype_has_capability = lambda *_: True
    auth.require_any_doctype_capability = lambda *_args, **_kwargs: None
    auth.require_doctype_capability = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, auth.__name__, auth)
    frappe._ = lambda message: message
    frappe.whitelist = lambda **_: lambda function: function
    frappe.ValidationError = ValueError
    frappe.PermissionError = PermissionError
    frappe.throw = lambda message, exception=ValueError: (_ for _ in ()).throw(exception(message))
    frappe.session = SimpleNamespace(user="owner@example.com")
    frappe.enqueue = lambda *_args, **_kwargs: None
    frappe.utils.cint = int
    frappe.utils.now = lambda: "2026-11-08"
    frappe.utils.now_datetime = lambda: None
    service_path = Path(__file__).resolve().parents[1] / "almdina_erp" / "services" / "backup_restore_service.py"
    spec = importlib.util.spec_from_file_location("backup_service_under_test", service_path)
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    service.require_doctype_capability = lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("denied"))
    with pytest.raises(PermissionError, match="denied"):
        service.begin_backup_upload(6)
    assert not rows
    service.require_doctype_capability = lambda *_args, **_kwargs: None
    operation = service.begin_backup_upload(6)["operation_id"]
    assert service._upload_path(operation).parent == tmp_path / "private" / "backup_zip_uploads"
    frappe.request = SimpleNamespace(files={"file": SimpleNamespace(stream=io.BytesIO(b"abc"))})
    with pytest.raises(ValueError, match="out of order"):
        service.upload_backup_chunk(operation, 1, 6)
    frappe.request.files["file"].stream.seek(0)
    assert service.upload_backup_chunk(operation, 0, 6)["received"] == 3
    frappe.session.user = "other@example.com"
    with pytest.raises(PermissionError, match="unavailable"):
        service.finish_backup_upload(operation, 6)
    frappe.session.user = "owner@example.com"
    with pytest.raises(ValueError, match="incomplete"):
        service.finish_backup_upload(operation, 6)
    service.cancel_backup_upload(operation)
    assert rows[operation]["status"] == "Failed"
    assert not service._upload_path(operation).exists()
