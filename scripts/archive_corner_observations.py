"""Losslessly gzip large research JSON; retain measured-byte hashes in indexes."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]/'docs/evidence/corner-search'


def main():
    archived = {}
    for path in sorted(ROOT.rglob('*.json')):
        if 'source-snapshot' in path.parts or path.stat().st_size < 100_000:
            continue
        raw = path.read_bytes()
        target = path.with_suffix('.json.gz')
        assert not target.exists(), target
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        target.write_bytes(packed)
        assert gzip.decompress(target.read_bytes()) == raw
        archived[path] = dict(file=target.name, uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
                              sha256=hashlib.sha256(packed).hexdigest())
    for index in ROOT.rglob('index.json'):
        records = json.loads(index.read_text(encoding='utf-8'))
        changed = False
        if not isinstance(records, list):
            continue
        for record in records:
            source = index.parent/record.get('file', '')
            if source in archived:
                assert record.get('sha256') == archived[source]['uncompressed_sha256'], source
                record.update(archived[source])
                changed = True
        if changed:
            index.write_text(json.dumps(records, indent=2), encoding='utf-8')
    for path in archived:
        assert path.resolve().is_relative_to(ROOT.resolve())
        path.unlink()
    print('Archived JSON files:', len(archived))


if __name__ == '__main__':
    main()
