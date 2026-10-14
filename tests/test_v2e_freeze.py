from pathlib import Path
import hashlib


def test_frozen_protocol_and_all_identities():
    from flybench.experiment_v2 import verify_freeze
    assert verify_freeze() == 'f684489801ec3d5d9af4c9fd845019c79f4daef97cb3533d023b6baf4fce4c8a'
    assert hashlib.sha256(Path("profiles/calibration-v2.json").read_bytes()).hexdigest() == 'f684489801ec3d5d9af4c9fd845019c79f4daef97cb3533d023b6baf4fce4c8a'
