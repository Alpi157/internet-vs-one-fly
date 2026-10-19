"""V2I presentation identities, registered chart projection and launch contract."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
import numpy as np
from experiments.v2f_publish import lab_chart

ROOT = Path(__file__).resolve().parents[1]
BASE = '0498868a9470e9be2f9037207e6cc5421b80e299'


def test_v2i_keeps_science_mechanics_runtime_and_anatomy_bytes():
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE], cwd=ROOT, text=True).splitlines()
    protected = [p for p in paths if p.startswith(('src/', 'packages/kernel-ts/src/', 'apps/play/public/data/', 'docs/media/anatomy/')) or p in ('apps/play/src/game.ts', 'apps/play/src/worker.ts', 'docs/results-v2e.json', 'docs/results-v2f.json')]
    for name in protected:
        expected = subprocess.check_output(['git', 'show', f'{BASE}:{name}'], cwd=ROOT)
        assert (ROOT/name).read_bytes() == expected, name
    for manifest in ['profiles/freeze-v2.json', 'profiles/freeze-v2.1.json']:
        for name, digest in json.loads((ROOT/manifest).read_text())['files'].items():
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name


def test_registered_bands_and_missing_tails():
    chart = lab_chart()
    original = json.loads((ROOT/'docs/results-v2e-lab-curves.json').read_text())
    strength = json.loads((ROOT/'docs/results-v2f.json').read_text())['metrics']
    for family in chart['families']:
        curves = [v for k,v in original['metrics'].items() if ':N-SIGN:' in k] if family['family']=='N-SIGN' else [v['curve'] for k,v in strength.items() if k.startswith('H0-STR:T1a:N-STRENGTH:')]
        assert family['n'] == len(curves)
        for point in family['points']:
            values = [p['rate_hz'] for curve in curves for p in curve if p['s']==point['s']]
            assert len(values)==len(curves)
            assert point['band'] == np.percentile(values,[2.5,97.5]).tolist()
        for missing in family['missing']:
            assert missing['s'] not in [p['s'] for p in family['points']]
            assert missing['missing'] == sum(not any(p['s']==missing['s'] for p in curve) for curve in curves)
    public=json.loads((ROOT/'apps/play/public/results-v2f.json').read_text())
    runtime=json.loads((ROOT/'apps/play/public/data/runtime.json').read_text())
    assert public['calibrated_coupling']==runtime['parameters']['s']


def test_pages_manual_only_and_local_assets():
    workflow=(ROOT/'.github/workflows/pages-v2.yml').read_text()
    assert 'workflow_dispatch:' in workflow and not re.search(r'^  (push|pull_request|schedule):',workflow,re.M)
    for name in ['how-it-works.html','model.html','preregistration.html','404.html']:
        text=(ROOT/'apps/play/public'/name).read_text()
        assert 'lang="en"' in text and 'content="#000000"' in text and 'og:image' in text
        assert not re.search(r'(?:src|href)="https?://[^" ]+\.(?:css|js|woff2|png)"',text)
    frozen=set()
    for manifest in ['profiles/freeze-v2.json','profiles/freeze-v2.1.json']:
        frozen.update(json.loads((ROOT/manifest).read_text())['files'])
    frozen.update(['docs/architecture.md','docs/plan-v2.md','docs/history/ledger-v1.yaml','docs/results-v2e.json','docs/results-v2f.json'])
    for path in [ROOT/'README.md',*ROOT.glob('docs/**/*.md'),*ROOT.glob('apps/play/src/*.ts'),*ROOT.glob('apps/play/public/*.html')]:
        if str(path.relative_to(ROOT)) not in frozen:
            assert not re.search('[\u2013\u2014]',path.read_text()),path


def test_recorded_media_provenance():
    from PIL import Image
    manifest=json.loads((ROOT/'docs/media/media-provenance.json').read_text())
    for name,meta in manifest['assets'].items():
        data=(ROOT/name).read_bytes()
        assert len(data)==meta['bytes']
        assert hashlib.sha256(data).hexdigest()==meta['sha256'],name
        if name.endswith('.gif'):
            assert len(data)<8_000_000
            assert Image.open(ROOT/name).n_frames==meta['frames']
    for name,digest in manifest['capture_source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    assert Image.open(ROOT/'apps/play/public/og-image.png').size==(1200,630)
    runtime=json.loads((ROOT/'apps/play/public/data/runtime.json').read_text())
    assert manifest['lab']['coupling']==runtime['parameters']['s']
    assert manifest['game']['log']['inputs']
