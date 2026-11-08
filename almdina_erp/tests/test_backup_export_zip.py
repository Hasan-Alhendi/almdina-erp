from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.backups.export import ExportOperation, export_backup_zip
from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle
from almdina_erp.almdina_erp.domain.backups.export_format import (
    EXPORT_FORMAT,
    EXPORT_FORMAT_VERSION,
    build_export_manifest,
)
from almdina_erp.almdina_erp.infrastructure.backups import export_zip as export_zip_module
from almdina_erp.almdina_erp.infrastructure.backups.export_zip import (
    BackupExportError,
    StreamingZipPacker,
    cleanup_export_paths,
)


SITE = "site.local"
IDENTIFIER = "20261108_120000-site_local"
KINDS = (
    ("database", f"{IDENTIFIER}-database.sql.gz", b"db-bytes"),
    ("public_files", f"{IDENTIFIER}-files.tgz", b"public-bytes"),
    ("private_files", f"{IDENTIFIER}-private-files.tgz", b"private-bytes"),
    ("site_config", f"{IDENTIFIER}-site_config_backup.json", b'{"site":"local"}'),
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bundle(directory: Path, *, mutate: dict[str, bytes] | None = None) -> BackupBundle:
    directory.mkdir(parents=True, exist_ok=True)
    artifacts: list[BackupArtifact] = []
    for kind, filename, payload in KINDS:
        content = (mutate or {}).get(kind, payload)
        path = directory / filename
        path.write_bytes(content)
        artifacts.append(
            BackupArtifact(
                kind=kind,
                path=str(path),
                filename=filename,
                size=len(content),
                checksum=_sha(content),
            )
        )
    return BackupBundle(identifier=IDENTIFIER, artifacts=tuple(artifacts))


def _operation(bundle: BackupBundle, *, status: str = "Completed", target: str = "Local") -> ExportOperation:
    manifest = json.dumps(
        [
            {
                "kind": artifact.kind,
                "filename": artifact.filename,
                "size": artifact.size,
                "checksum": artifact.checksum,
            }
            for artifact in bundle.artifacts
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ExportOperation(
        operation_id="op-export-1",
        operation_type="Manual",
        target=target,
        status=status,
        backup_identifier=bundle.identifier,
        completed_on="2026-11-08 12:00:00",
        artifact_manifest=manifest,
    )


def _manifest_for(bundle: BackupBundle, operation: ExportOperation):
    return build_export_manifest(
        backup_id=operation.backup_identifier,
        operation_id=operation.operation_id,
        site=SITE,
        created_at=operation.completed_on,
        database_type="mariadb",
        target=operation.target,
        operation_type=operation.operation_type,
        components=[
            {
                "name": artifact.kind,
                "path": artifact.filename,
                "size": artifact.size,
                "sha256": artifact.checksum,
            }
            for artifact in bundle.artifacts
        ],
    )


def test_streaming_zip_contains_manifest_and_verified_components(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "backups")
    operation = _operation(bundle)
    packed = StreamingZipPacker(work_root=tmp_path / "private").pack(
        bundle=bundle,
        manifest=_manifest_for(bundle, operation),
        download_stem=bundle.identifier,
    )
    try:
        with zipfile.ZipFile(packed.zip_path, "r") as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            payload = json.loads(archive.read("manifest.json"))
            assert payload["format"] == EXPORT_FORMAT
            assert payload["format_version"] == EXPORT_FORMAT_VERSION
            assert all("/" not in component["path"] for component in payload["components"])
            for artifact in bundle.artifacts:
                assert artifact.filename in names
                data = archive.read(artifact.filename)
                assert len(data) == artifact.size
                assert _sha(data) == artifact.checksum
            assert names == {"manifest.json", *(artifact.filename for artifact in bundle.artifacts)}
        for artifact in bundle.artifacts:
            assert Path(artifact.path).stat().st_size == artifact.size
            assert _sha(Path(artifact.path).read_bytes()) == artifact.checksum
    finally:
        cleanup_export_paths(packed.cleanup_paths)
    assert not Path(packed.zip_path).exists()


def test_packer_rejects_path_traversal_member(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "backups")
    evil = BackupArtifact(
        kind="database",
        path=bundle.artifacts[0].path,
        filename="../evil-database.sql.gz",
        size=bundle.artifacts[0].size,
        checksum=bundle.artifacts[0].checksum,
    )
    bad = BackupBundle(identifier=IDENTIFIER, artifacts=(evil, *bundle.artifacts[1:]))
    with pytest.raises(BackupExportError):
        StreamingZipPacker(work_root=tmp_path / "private").pack(
            bundle=bad,
            manifest=_manifest_for(bundle, _operation(bundle)),
            download_stem=IDENTIFIER,
        )


def test_packer_rejects_symlink_components(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "backups")
    target = tmp_path / "backups" / bundle.artifacts[0].filename
    link = tmp_path / "backups" / "link-database.sql.gz"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    linked = BackupArtifact(
        kind="database",
        path=str(link),
        filename=bundle.artifacts[0].filename,
        size=bundle.artifacts[0].size,
        checksum=bundle.artifacts[0].checksum,
    )
    bad = BackupBundle(identifier=IDENTIFIER, artifacts=(linked, *bundle.artifacts[1:]))
    with pytest.raises(BackupExportError):
        StreamingZipPacker(work_root=tmp_path / "private").pack(
            bundle=bad,
            manifest=_manifest_for(bundle, _operation(bundle)),
            download_stem=IDENTIFIER,
        )


def test_export_use_case_cleans_temp_on_packer_failure(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "backups")
    staging = tmp_path / "fetched"
    staging.mkdir()
    marker = staging / "marker.bin"
    marker.write_bytes(b"x")

    class Repo:
        def get_export_operation(self, operation_id: str) -> ExportOperation:
            return _operation(bundle)

    class Resolver:
        def resolve(self, operation: ExportOperation):
            return bundle, (str(staging),)

    class Packer:
        def pack(self, **_kwargs):
            raise ValueError("backup_export_failed")

    with pytest.raises(ValueError):
        export_backup_zip(
            operation_id="op-export-1",
            repository=Repo(),
            resolver=Resolver(),
            packer=Packer(),
            site=SITE,
            database_type="mariadb",
        )
    assert not marker.exists()
    assert not staging.exists()


def test_large_component_uses_chunked_reads_and_zip_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    large = b"x" * (3 * 1024 * 1024)
    bundle = _bundle(tmp_path / "backups", mutate={"database": large})
    max_read = {"value": 0}
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        if str(self).endswith("-database.sql.gz"):
            original_read = handle.read

            def counted_read(size: int = -1):
                data = original_read(size)
                if isinstance(data, (bytes, bytearray)):
                    max_read["value"] = max(max_read["value"], len(data))
                return data

            handle.read = counted_read  # type: ignore[method-assign]
        return handle

    monkeypatch.setattr(Path, "open", tracking_open)
    source = Path(export_zip_module.__file__).read_text(encoding="utf-8")
    assert "archive.write(resolved" in source
    assert "read_bytes()" not in source
    assert "1024 * 1024" in source

    operation = _operation(bundle)
    packed = StreamingZipPacker(work_root=tmp_path / "private").pack(
        bundle=bundle,
        manifest=_manifest_for(bundle, operation),
        download_stem=bundle.identifier,
    )
    try:
        assert 0 < max_read["value"] <= 1024 * 1024
        with zipfile.ZipFile(packed.zip_path, "r") as archive:
            assert len(archive.read(bundle.artifacts[0].filename)) == len(large)
    finally:
        cleanup_export_paths(packed.cleanup_paths)


def test_missing_required_component_fails_before_misleading_zip(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "backups")
    Path(bundle.artifacts[0].path).unlink()
    with pytest.raises(BackupExportError):
        StreamingZipPacker(work_root=tmp_path / "private").pack(
            bundle=bundle,
            manifest=_manifest_for(bundle, _operation(bundle)),
            download_stem=IDENTIFIER,
        )
    assert list((tmp_path / "private").glob("almdina-backup-export-*")) == []
