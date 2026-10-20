"""Historical V2K contract, pinned to its submitted tree before V2L changes."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='88945ca780d5fc12e59a51e2f5aec1d9d2556377'
SUBMITTED='f30ae501a21c71e714084bd378ae59d6e2144a9e'

def historical(p):return subprocess.check_output(['git','show',f'{SUBMITTED}:{p}'],cwd=ROOT)
def load(p):return json.loads(historical(p))
def digest(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def test_v2k_mechanics_science_and_lab_unchanged():
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    exact={'apps/play/src/game.ts','apps/play/src/game-runner.ts','apps/play/src/walking-drive.ts','apps/play/src/worker.ts','apps/play/src/owner-preview.ts','apps/play/src/lab.ts','apps/play/src/coupling.ts','apps/play/src/coupling-worker.ts','apps/play/src/brain-view.ts','apps/play/src/field.ts','apps/play/src/style.css','docs/media/coupling-hero.gif','docs/media/coupling-still.png','docs/results-v2e.json','docs/results-v2f.json'}
    protected=[p for p in paths if p.startswith(('src/','packages/kernel-ts/src/','apps/play/public/data/','profiles/','decisions/','docs/media/anatomy/')) or p in exact]
    result=subprocess.run(['git','diff','--exit-code',BASE,SUBMITTED,'--',*protected],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stdout
    for manifest in ['profiles/freeze-v2.json','profiles/freeze-v2.1.json']:
        for p,h in load(manifest)['files'].items():assert digest(p)==h,p

def test_v2k_reflex_hero_rule_trials_and_history():
    prior=ROOT/'docs/media/history/v2j-a03-provenance.json'
    assert historical('docs/media/history/v2j-a03-provenance.json')==subprocess.check_output(['git','show',f'{BASE}:docs/media/media-provenance.json'],cwd=ROOT)
    protocol=load('profiles/media-v2k.json');media=load('docs/media/media-provenance.json');g=media['game'];selection=g['selection'];trials=selection['trials']
    assert media['schema']=='flybench.media.v2k.a01'
    assert g['log']['inputs']==[{'tick':3000,**trials[-1]['aim'],'hold_ms':600}]
    assert not g['impact']['caught'] and g['impact']['escape_onset_lead_ms']>0
    assert g['impact']['lead_ms'] is not None and g['gf_lit_frames']
    assert [t['seed'] for t in trials]==list(range(1,g['neural_seed']+1))
    assert all(not t['qualifies'] for t in trials[:-1]) and trials[-1]['qualifies']
    for t in trials:assert t['qualifies']==(not t['caught'] and t['escape_onset_lead_ms'] is not None and t['escape_onset_lead_ms']>0)
    assert g['walk_frames']==30 and g['walk_slowdown_factor']==1 and g['live_slowdown_factor']==5
    assert g['replay_seconds']==3 and g['replay_speed']==0.25
    assert g['og']['source']==protocol['hero']['og_rule']
    for k,v in protocol['hero'].items():assert selection[k]==v,k
    assert g['observed_escape_stamp'] and g['observed_takeoff']
    assert media['lab']==load('docs/media/history/v2j-a03-provenance.json')['lab']
    declared=json.loads(subprocess.check_output(['git','show',f"{media['base_commit']}:profiles/media-v2k.json"],cwd=ROOT))
    assert declared==protocol

def test_v2k_prior_evidence_and_archives_unchanged():
    # V2L pins the old ignored evidence/ZIPs; tracked V2K identities use Git.
    p=ROOT/'evidence/V2L/prior-preservation.json'
    if not p.exists():return
    for file,meta in json.loads(p.read_text())['files'].items():
        assert digest(file)==meta['sha256'],file
        assert (ROOT/file).stat().st_size==meta['bytes'],file
