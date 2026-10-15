"""Immutable protocol identities, independent of local bulk data."""
from pathlib import Path
import hashlib
from flybench.experiment_v21 import verify_freeze


def test_v21_freeze():
    assert verify_freeze() == 'c4ed65c481373d1a3a4a29637878acae93c0a085fdff50914bb9d0f95d6b217d'
    assert hashlib.sha256(Path("profiles/freeze-v2.1.json").read_bytes()).hexdigest() == 'ff29f762295cac5b70496f32a03214812918c36aebf31284dd0d185083ec1f06'
