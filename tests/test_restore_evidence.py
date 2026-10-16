"""Restoration checks integrity and protects existing evidence and filesystem paths."""
import hashlib
import io
import tarfile
from pathlib import Path
import pytest
from tools.restore_evidence import restore


def fixture(tmp_path, *, name='evidence/V2F/results/test.json', kind=None):
    data=b'{"recorded":true}\n'
    archive=tmp_path/'evidence.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        entry=tarfile.TarInfo(name);entry.size=len(data)
        if kind:entry.type=kind;entry.linkname='../escape'
        tar.addfile(entry,io.BytesIO(data))
    manifest={'archive_bytes':archive.stat().st_size,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'member_count':1,'files':[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}
    root=tmp_path/'clone';root.mkdir()
    return archive,manifest,root,data


def test_restore_and_identical_files_are_idempotent(tmp_path):
    archive,m,root,data=fixture(tmp_path);restore(archive,m,root)
    target=root/m['files'][0]['path'];assert target.read_bytes()==data
    before=target.stat().st_mtime_ns;restore(archive,m,root)
    assert target.stat().st_mtime_ns==before


def test_archive_hash_checked_before_writes(tmp_path):
    archive,m,root,_=fixture(tmp_path);m['archive_sha256']='0'*64
    with pytest.raises(ValueError,match='Archive size or SHA-256'):restore(archive,m,root)
    assert not (root/'evidence').exists()


def test_existing_conflict_is_preserved(tmp_path):
    archive,m,root,_=fixture(tmp_path);target=root/m['files'][0]['path'];target.parent.mkdir(parents=True);target.write_bytes(b'local')
    with pytest.raises(ValueError,match='Refusing to overwrite'):restore(archive,m,root)
    assert target.read_bytes()==b'local'


@pytest.mark.parametrize('name,kind',[('../escape',None),('/tmp/escape',None),('evidence/link',tarfile.SYMTYPE)])
def test_unsafe_members_rejected(tmp_path,name,kind):
    archive,m,root,_=fixture(tmp_path,name=name,kind=kind)
    with pytest.raises(ValueError):restore(archive,m,root)
    assert not (tmp_path/'escape').exists()


def test_destination_symlink_rejected(tmp_path):
    archive,m,root,_=fixture(tmp_path);other=tmp_path/'other';other.mkdir();(root/'evidence').symlink_to(other,target_is_directory=True)
    with pytest.raises(ValueError,match='Symlink'):restore(archive,m,root)
    assert list(other.iterdir())==[]
