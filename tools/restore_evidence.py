#!/usr/bin/env python3
"""Restore checksum-pinned raw evidence without replacing differing local files."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def destination(root, name):
    parts = PurePosixPath(name).parts
    if not parts or parts[0] != 'evidence' or '..' in parts or str(PurePosixPath(name)) != name:
        raise ValueError('Unsafe evidence member: ' + name)
    target = root.joinpath(*parts)
    for path in [root, *target.parents, target]:
        if path.is_symlink():
            raise ValueError('Symlink in destination: ' + str(path))
    return target


def restore(archive, manifest, root=ROOT):
    # Check the full archive before creating any evidence directory or file.
    if archive.stat().st_size != manifest['archive_bytes'] or digest(archive) != manifest['archive_sha256']:
        raise ValueError('Archive size or SHA-256 mismatch')
    rows = manifest['files']
    expected = {r['path']: r for r in rows}
    if len(expected) != len(rows) or len(rows) != manifest['member_count']:
        raise ValueError('Duplicate or missing manifest members')
    for name, row in expected.items():
        target = destination(root, name)
        if target.exists() and (not target.is_file() or target.stat().st_size != row['bytes'] or digest(target) != row['sha256']):
            raise ValueError('Refusing to overwrite differing existing file: ' + name)
    seen = set()
    restored = 0
    with tarfile.open(archive, 'r|gz') as source:
        for member in source:
            name = member.name
            if not member.isfile() or name not in expected or name in seen:
                raise ValueError('Unexpected, duplicate or non-regular archive member: ' + name)
            seen.add(name)
            row = expected[name]
            if member.size != row['bytes']:
                raise ValueError('Member size mismatch: ' + name)
            target = destination(root, name)
            stream = source.extractfile(member)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Hash every archive member even when a matching local file exists.
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.restore-', delete=False) as temporary:
                temporary_path = Path(temporary.name)
                value = hashlib.sha256()
                try:
                    while chunk := stream.read(1024 * 1024):
                        value.update(chunk)
                        temporary.write(chunk)
                    temporary.flush()
                    if value.hexdigest() != row['sha256']:
                        raise ValueError('Member SHA-256 mismatch: ' + name)
                    if not target.exists():
                        try:
                            # Hard-linking the new regular file never overwrites.
                            os.link(temporary_path, target)
                            restored += 1
                        except FileExistsError:
                            pass
                    if digest(target) != row['sha256']:
                        raise ValueError('Conflicting destination: ' + name)
                finally:
                    temporary_path.unlink(missing_ok=True)
    if seen != set(expected):
        raise ValueError('Archive member set differs from manifest')
    for name, row in expected.items():
        target = destination(root, name)
        if digest(target) != row['sha256']:
            raise ValueError('Restored file hash mismatch: ' + name)
    print(f'PASS: archive SHA-256 and {len(expected)} member hashes; {restored} new files, {len(expected)-restored} identical existing files preserved')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive', type=Path)
    group.add_argument('--download', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT/'archive/raw-records-manifest.json').read_text())
    try:
        if args.archive:
            restore(args.archive, manifest)
        else:
            print('Downloading reserved Zenodo file URL; it becomes public only after the owner publishes the draft', flush=True)
            with tempfile.TemporaryDirectory(prefix='flybench-evidence-') as directory:
                archive = Path(directory)/manifest['archive_name']
                with urllib.request.urlopen(manifest['public_file_url'], timeout=600) as response, archive.open('wb') as output:
                    while chunk := response.read(1024*1024):
                        output.write(chunk)
                restore(archive, manifest)
    except (ValueError, OSError, tarfile.TarError) as error:
        parser.exit(1, 'STOP: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
