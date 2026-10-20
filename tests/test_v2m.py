"""V2M preserves production and science; previews are explicit game physics."""
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = "2cb59c0d6dca6c341c03e83ee5352d8955223f29"

def load(path):
    return json.loads((ROOT / path).read_text())

def test_production_walking_lab_and_frozen_identities():
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", BASE], cwd=ROOT, text=True).splitlines()
    protected = [p for p in paths if p.startswith(("src/", "packages/kernel-ts/src/", "apps/play/public/data/", "profiles/", "decisions/", "docs/design/", "docs/media/anatomy/")) or p in {
        "apps/play/src/game.ts", "apps/play/src/game-runner.ts", "apps/play/src/walking-drive.ts",
        "apps/play/src/coupling-worker.ts", "docs/results-v2e.json", "docs/results-v2f.json", "docs/results-v2e-lab-curves.json",
    }]
    result = subprocess.run(["git", "diff", "--exit-code", BASE, "--", *protected], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout

def test_fixed_presets_and_owner_selected_walking():
    protocol = load("profiles/owner-takeoff-v2m.json")
    assert protocol["measurement"]["validation_seeds"] == list(range(1, 21))
    assert [p["takeoff_speed"] for p in protocol["presets"].values()] == [.018, .036, .040, .045]
    assert [p["takeoff_duration_ms"] for p in protocol["presets"].values()] == [330, 170, 150, 130]
    base = load("profiles/game-v2.9.json")
    selected_path = ROOT / "profiles/owner-takeoff-v2m-selected.json"
    assert selected_path.exists(), "The owner playtest needs its measured offering"
    selection = json.loads(selected_path.read_text())
    for name, entry in selection["presets"].items():
        p = entry["profile"]
        assert entry["offered"] == all(entry["gates"].values())
        assert p["walking_drive"] == base["walking_drive"]
        changed = {"profile_id", "takeoff_speed", "takeoff_duration_ms", "takeoff_path_arena_units", "owner_preset", "physics_disclosure"}
        for key in base:
            if key not in changed:
                assert p[key] == base[key], (name, key)
        assert p["takeoff_duration_ms"] % 10 == 0
        assert abs(p["takeoff_speed"] * p["takeoff_duration_ms"] - 6) <= .15 + 1e-12

def test_same_hero_recording_with_semantic_colors():
    current = load("docs/media/media-provenance.json")
    historical = load("docs/media/history/v2l-provenance.json")
    assert current["game"] == historical["game"]
    assert current["lab"] == historical["lab"]
    assert (ROOT / "docs/media/history/v2l-provenance.json").read_bytes() == subprocess.check_output(
        ["git", "show", BASE + ":docs/media/media-provenance.json"], cwd=ROOT)
    assert len(current["palette_revision"]["source_frames_sha256"]) == 153
    path = ROOT / "docs/media/game-hero.gif"
    assert path.stat().st_size < 8_000_000
    assert hashlib.sha256(path.read_bytes()).hexdigest() == current["assets"]["docs/media/game-hero.gif"]["sha256"]
    im = Image.open(path)
    assert im.n_frames == 153 and im.size == (960, 600)
    for frame, xy in [(65, (171, 156)), (110, (475, 104))]:
        im.seek(frame)
        rgb = im.convert("RGB").getpixel(xy)
        assert max(abs(a-b) for a,b in zip(rgb, (99,242,154))) <= 6, rgb
    im.seek(20)
    r,g,b = im.convert("RGB").getpixel((343,286))
    assert r-g >= 20 and g-b >= 20, (r,g,b)
