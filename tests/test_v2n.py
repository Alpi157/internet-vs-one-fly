"""README recapture from accepted V2M, with no product or scientific changes."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED = "1b670a9d371ce406a1865aa5c4b91085b4f87fea"
V2N_SUBMITTED = "eb52897ac9006eb058574c8734bbb3cd5da77925"
ASSETS = {"docs/media/" + name for name in (
    "game-hero.gif", "coupling-hero.gif", "game-still.png", "coupling-still.png")}
ALLOWED = ASSETS | {
    "README.md", "docs/readme-v2f.template.md", "ledger.yaml", "docs/media/media-provenance.json",
    "docs/media/history/v2m-provenance.json", "docs/ui-v2n.md",
    "apps/play/test/media.mjs", "apps/play/test/media-gifs.py",
    "apps/play/test/v2m-ui.test.ts", "apps/play/test/walking-a03.ts",
    "tests/test_v2m.py", "tests/test_v2n.py", "tools/acceptance.json",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def load(path):
    return json.loads((ROOT / path).read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def test_readme_assets_match_new_provenance():
    p = load("docs/media/media-provenance.json")
    assert p["schema"] == "flybench.media.v2n" and p["display_only"] is True
    assert set(p["assets"]) == ASSETS
    assert p["viewport"] == {"width": 1440, "height": 900}
    assert p["device_scale_factor"] in (1, 2) and p["scale_factor_reason"]
    for name, meta in p["assets"].items():
        data = (ROOT / name).read_bytes()
        assert len(data) == meta["bytes"] and digest(data) == meta["sha256"], name
        with Image.open(ROOT / name) as im:
            assert list(im.size) == meta["size"]
            if name.endswith(".gif"):
                assert len(data) < 8_000_000 and im.size == (960, 600)
                key = "game" if "game-hero" in name else "lab"
                assert im.n_frames == meta["frames"] == p[key]["frames"]
                assert meta["source_frames"] == im.n_frames
                assert meta["palette_colors"] == 112
                palette = p["palette_record"][Path(name).name]
                assert palette["dither"] == "NONE" and palette["resampling"] == "LANCZOS"
                assert digest(bytes(palette["rgb"])) == palette["palette_sha256"]
                assert im.getpalette()[:len(palette["rgb"])] == palette["rgb"]
                assert palette["sample_frame_indices"] == list(range(0, im.n_frames, 10))
                for i in range(im.n_frames):
                    im.seek(i)
                    assert im.info["duration"] == meta["frame_duration_ms"] == p[key]["frame_duration_ms"]
                    assert digest(im.convert("RGB").tobytes()) == meta["decoded_rgb_sha256"][i]
            else:
                assert im.size == (1440 * p["device_scale_factor"], 900 * p["device_scale_factor"])


def test_all_current_capture_sources_match_accepted_commit():
    p = load("docs/media/media-provenance.json")
    assert git("rev-parse", "v2m-accepted^{commit}").decode().strip() == ACCEPTED == p["capture_source_commit"]
    paths = git("ls-tree", "-r", "--name-only", ACCEPTED, "--", "apps/play/src").decode().splitlines()
    assert set(p["capture_source_sha256"]) == set(paths)
    for name in paths:
        assert digest(git("show", ACCEPTED + ":" + name)) == p["capture_source_sha256"][name]
        assert digest((ROOT / name).read_bytes()) == p["capture_source_sha256"][name]
    assert digest((ROOT / "apps/play/test/media.mjs").read_bytes()) == p["capture_code_sha256"]
    assert digest((ROOT / "apps/play/test/media-gifs.py").read_bytes()) == p["conversion_source_sha256"]


def test_public_sources_frozen_files_and_history_unchanged():
    # The allowlist also catches any changed tracked raw records or preregistrations.
    # Scope of the accepted V2N commit itself, so later commits do not count as V2N changes.
    changed = set(git("diff", "--name-only", ACCEPTED, V2N_SUBMITTED, "--").decode().splitlines())
    assert changed <= ALLOWED
    assert not git("diff", ACCEPTED, "--", "apps/play/src", "apps/play/public", "src", "packages/kernel-ts/src")
    for manifest in ("profiles/freeze-v2.json", "profiles/freeze-v2.1.json"):
        for name, sha in load(manifest)["files"].items():
            assert digest((ROOT / name).read_bytes()) == sha, name
    old_history = git("ls-tree", "-r", "--name-only", ACCEPTED, "--", "docs/media/history").decode().splitlines()
    for name in old_history:
        assert (ROOT / name).read_bytes() == git("show", ACCEPTED + ":" + name)
    assert (ROOT / "docs/media/history/v2m-provenance.json").read_bytes() == git("show", ACCEPTED + ":docs/media/media-provenance.json")


def test_frozen_hero_identities_and_advancing_recorded_replay():
    p = load("docs/media/media-provenance.json")
    old = load("docs/media/history/v2m-provenance.json")
    g = p["game"]
    assert g["selection"] == old["game"]["selection"]
    assert g["log"] == old["game"]["log"] and g["impact"] == old["game"]["impact"]
    assert g["neural_seed"] == 1 and g["environment_seed"] == 8128
    assert g["profile_id"] == "flybench.game.v2.9" and g["takeoff"] == "T0"
    assert not g["impact"]["caught"] and g["impact"]["escape_onset_lead_ms"] > 0
    assert g["walk_frames"] == 30 and g["walk_slowdown_factor"] == 1 and g["live_slowdown_factor"] == 5
    assert g["replay_seconds"] == 3 and g["replay_speed"] == .25 and g["frame_duration_ms"] == 50
    assert g["frames"] == g["live_frames"] + 60
    assert len(g["replay_ticks"]) == len(g["replay_playheads"]) == 60
    assert len(set(g["replay_ticks"])) > 20 and len(set(g["replay_playheads"])) > 20
    assert all(b < a or 0 <= b-a <= 40 for a, b in zip(g["replay_ticks"], g["replay_ticks"][1:]))
    assert g["gf_lit_frames"] and g["replay_controls_visible"]
    assert g["observed_takeoff"] and g["observed_countdown"] and g["observed_escape_stamp"]
    lab = p["lab"]
    for key in ("coupling", "neural_seed", "environment_seed", "sign", "strength", "registered_medians"):
        assert lab[key] == old["lab"][key]
    assert lab["story_steps"] == [1, 2] and lab["frames"] == 80 and lab["frame_duration_ms"] == 100
    assert [s["step"] for s in lab["observations"]] == [1, 2]
    assert all(s["scale"] == .039 for s in lab["observations"])
    assert not p["external_requests"]


def test_historical_recorder_modes_and_readme_text_are_preserved():
    old = git("show", ACCEPTED + ":apps/play/test/media.mjs").decode()
    new = (ROOT / "apps/play/test/media.mjs").read_text()
    assert new.split("async function captureV2N(){")[0] == old.split("if(process.argv.includes('--v2l-review'))")[0]
    old = git("show", ACCEPTED + ":apps/play/test/media-gifs.py").decode()
    new = (ROOT / "apps/play/test/media-gifs.py").read_text()
    marker = "# V2M changes palette encoding only"
    assert new[new.index(marker):] == old[old.index(marker):]
    for path in ("README.md", "docs/readme-v2f.template.md"):
        old = git("show", ACCEPTED + ":" + path).decode().splitlines()
        new = (ROOT / path).read_text().splitlines()
        assert len(old) == len(new)
        for a, b in zip(old, new):
            if a != b:
                assert a.startswith(("![Game v2.9:", "Walking runs at real speed."))
                assert re.findall(r"\d+(?:\.\d+)?", a) == re.findall(r"\d+(?:\.\d+)?", b)


def test_local_source_frames_and_stills_share_the_same_capture():
    p = load("docs/media/media-provenance.json")
    frames = ROOT / "evidence/V2N/source-frames"
    if not frames.exists():
        pytest.skip("Full-size local capture evidence is distributed in the V2N review workspace")
    assert {f.name for f in frames.glob("*.png")} == set(p["source_frames_sha256"])
    for name, sha in p["source_frames_sha256"].items():
        assert digest((frames / name).read_bytes()) == sha, name
    for key, prefix, asset in [("game", "game", "game-still.png"), ("lab", "lab", "coupling-still.png")]:
        source = frames / f"{prefix}-{p[key]['still_source_frame']:03d}.png"
        assert source.read_bytes() == (ROOT / "docs/media" / asset).read_bytes()


def test_local_raw_records_remain_byte_identical():
    p = load("docs/media/media-provenance.json")
    meta = p["preservation"]["raw_inventory"]
    baseline = ROOT / meta["path"]
    if not baseline.exists():
        pytest.skip("Raw scientific records are optional local evidence, outside the offline CI path")
    data = baseline.read_bytes()
    assert len(data) == meta["bytes"] and digest(data) == meta["sha256"]
    files = json.loads(data)["files"]
    assert len(files) == meta["files"]
    actual = {f.relative_to(ROOT).as_posix() for stage in ("V2E", "V2F")
              for f in (ROOT / "evidence" / stage / "results").rglob("*") if f.is_file()}
    assert actual == set(files)
    for name, record in files.items():
        data = (ROOT / name).read_bytes()
        assert len(data) == record["bytes"] and digest(data) == record["sha256"], name
